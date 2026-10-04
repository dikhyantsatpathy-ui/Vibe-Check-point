"""
Tests for the session-token scheme (app/main.py).

The session cookie is a self-contained HMAC token `email::exp::sig`:
fresh tokens authenticate, tampered/expired/legacy tokens get 401.

Run either way:
    python tests/test_auth.py        # plain asserts
    pytest tests/test_auth.py        # pytest runner
"""

import hashlib
import hmac
import os
import sys
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import main
from main import MASTER_VAULT_KEY, get_current_admin, make_session_token

# Reach the key module through the SAME module object main.py loaded.
# app/main.py imports it as `app.keys`; a bare `import keys` here would create
# a second module instance with its own random key, so every signature computed
# in a test would disagree with the one main.py verifies.
_vault_keys = main._vault_keys


def _req_with_cookie(token):
    scope = {"type": "http", "headers": [(b"cookie", f"nischay_session={token}".encode())]}
    return Request(scope)


def _req_without_cookie():
    return Request({"type": "http", "headers": []})


def _expect_401(request):
    try:
        get_current_admin(request)
    except HTTPException as e:
        assert e.status_code == 401, f"expected 401, got {e.status_code}"
        return e.detail
    raise AssertionError("expected HTTPException(401)")


@pytest.fixture(autouse=True)
def _officer_exists(monkeypatch):
    """get_current_admin() now requires a surviving SignerIdentity row.

    A valid signature alone is not authorisation: without this check, deleting
    an officer's row (the `remove_officer` path) would leave their cookie
    working until it expired. These tests exercise signature handling in
    isolation, so they stub the database rather than standing one up.
    """
    import main as _main

    def _fake_db_factory(exists=True, revoked=False):
        @contextmanager
        def _fake_db():
            class _Query:
                def filter_by(self, **kw):
                    return self

                def first(self):
                    if not exists:
                        return None
                    ident = _main.SignerIdentity(
                        email="officer@example.com", name="Officer",
                        institution="SSB", designation="Inspector",
                        registered_at=_main.now_utc(),
                    )
                    ident.is_revoked = 1 if revoked else 0
                    return ident

            class _DB:
                def query(self, *a, **kw):
                    return _Query()

            yield _DB()
        return _fake_db

    monkeypatch.setattr(_main, "get_db", _fake_db_factory())
    return _fake_db_factory


def test_fresh_token_authenticates():
    token = make_session_token("Officer@Example.com")
    assert token.count("::") == 2
    assert get_current_admin(_req_with_cookie(token)) == "officer@example.com"


def test_tampered_signature_rejected():
    token = make_session_token("officer@example.com")
    email, exp, _sig = token.split("::")
    bad = f"{email}::{exp}::{'0' * 64}"
    _expect_401(_req_with_cookie(bad))


def test_tampered_email_rejected():
    token = make_session_token("officer@example.com")
    _email, exp, sig = token.split("::")
    _expect_401(_req_with_cookie(f"attacker@example.com::{exp}::{sig}"))


def test_expired_token_rejected():
    """A correctly-signed token whose expiry has passed must be rejected.

    Minted through make_session_token and then back-dated, so the signature is
    genuinely valid -- this specifically covers the expiry branch rather than
    re-testing signature verification.
    """
    email = "officer@example.com"
    # Re-sign with a past expiry so only the expiry check can reject it.
    past = str(int(time.time()) - 60)
    sig = _vault_keys.sign(_vault_keys.session_key(), f"{email}::{past}")
    detail = _expect_401(_req_with_cookie(f"{email}::{past}::{sig}"))
    assert "expired" in detail.lower()


def test_session_token_signed_with_raw_master_key_is_rejected():
    """Session tokens must be signed with the derived session sub-key.

    If they were signed with the raw master, then a master-key signature -- the
    kind used for evidence seals -- would authenticate as a session.
    """
    email = "officer@example.com"
    exp = str(int(time.time()) + 3600)
    sig = hmac.new(MASTER_VAULT_KEY, f"{email}::{exp}".encode(), hashlib.sha256).hexdigest()
    _expect_401(_req_with_cookie(f"{email}::{exp}::{sig}"))


def test_absent_identity_row_is_rejected(_officer_exists):
    """Deleting an officer's identity row must kill their live cookie."""
    import main as _main
    _main.get_db = _officer_exists(exists=False)
    _expect_401(_req_with_cookie(make_session_token("officer@example.com")))


def test_revoked_officer_is_rejected(_officer_exists):
    import main as _main
    _main.get_db = _officer_exists(exists=True, revoked=True)
    try:
        get_current_admin(_req_with_cookie(make_session_token("officer@example.com")))
    except HTTPException as e:
        assert e.status_code == 403
        assert "REVOKED" in str(e.detail).upper()
    else:
        raise AssertionError("a revoked officer must not authenticate")


def test_legacy_two_part_token_rejected():
    email = "officer@example.com"
    sig = hmac.new(MASTER_VAULT_KEY, email.encode(), hashlib.sha256).hexdigest()
    _expect_401(_req_with_cookie(f"{email}::{sig}"))


def test_missing_cookie_rejected():
    _expect_401(_req_without_cookie())


def test_super_admins_come_only_from_the_environment(monkeypatch):
    """Admin rights must be configuration, never code.

    The old implementation granted super-admin to any address containing
    'dikhyant' / 'asutosh' / 'ayush' / 'cryptoknight', which meant
    `attacker-dikhyant.evil.com` was an administrator. It also shipped a
    hardcoded list of real personal Gmail addresses.
    """
    from main import SUPER_ADMINS, is_super_admin, get_super_admins

    # The module-level constant is now an empty compatibility shim; the real
    # list is read from the environment on every call.
    assert SUPER_ADMINS == [], "no admin addresses may be hardcoded in source"

    monkeypatch.setenv("SUPER_ADMINS", "")
    # No substring / pattern-based elevation, whatever the address looks like.
    for lookalike in (
        "attacker-dikhyant.evil.com",
        "ayush123@gmail.com",
        "x-cryptoknight@yopmail.com",
        "asutosh@gmail.com",
        "evaluator@ssb.gov.in",
        "sushumnameghavaram@gmail.com",
        "cryptoknights14@gmail.com",
    ):
        assert is_super_admin(lookalike) is False, f"{lookalike} must not be an admin"

    # Exact-address match, case-insensitive, straight from SUPER_ADMINS.
    monkeypatch.setenv("SUPER_ADMINS", "dynamic_admin@test.gov.in, another@test.gov.in")
    assert set(get_super_admins()) == {"dynamic_admin@test.gov.in", "another@test.gov.in"}
    assert is_super_admin("dynamic_admin@test.gov.in") is True
    assert is_super_admin("DYNAMIC_ADMIN@TEST.GOV.IN") is True
    # A prefix/suffix of a listed address is still not a match.
    assert is_super_admin("dynamic_admin@test.gov.in.evil.com") is False
    assert is_super_admin("nobody@example.com") is False


def test_unset_super_admins_grants_nobody_admin_rights():
    """Fail closed: with no configuration, no address is an admin."""
    from main import is_super_admin, get_super_admins
    old_env = os.environ.get("SUPER_ADMINS")
    try:
        os.environ["SUPER_ADMINS"] = ""
        assert get_super_admins() == []
        assert is_super_admin("anyone@example.com") is False
        assert is_super_admin("root@ssb.gov.in") is False
    finally:
        if old_env is not None:
            os.environ["SUPER_ADMINS"] = old_env
        else:
            os.environ.pop("SUPER_ADMINS", None)


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print("PASS", fn.__name__)
    print(f"{passed}/{len(fns)} tests passed")
