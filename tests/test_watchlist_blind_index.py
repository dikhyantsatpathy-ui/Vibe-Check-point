"""Watchlist blind-index regression tests.

Watchlist identifiers (PAN, phone, DOB, ...) are low-entropy: a plain SHA-256
of the value is brute-forceable offline and links the same person across
database leaks. These tests pin the replacement behaviour:

  * new entries store HMAC-SHA256 under the vault-derived key, never plain SHA;
  * a legacy plain-SHA row still matches and is upgraded in place on first hit;
  * duplicate adds (in any normalisation) collapse to one row.
"""

import hashlib
import hmac
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import app.keys as app_keys
import main
import screening
from main import Base, SignerIdentity, WatchlistEntry, app, make_session_token, now_utc

SUPER = os.environ.get("SUPER_ADMINS", "").split(",")[0].strip() or "test-superadmin@example.com"

PAN = "ABCDE1234F"


@pytest.fixture
def db_session(monkeypatch):
    """In-memory DB wired into main's session factory for this test only."""
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    # Skip the startup migration pass: it targets the module-level engine and
    # SQLite has no `ADD COLUMN IF NOT EXISTS`.
    monkeypatch.setattr(main, "_db_initialized", True)
    db = TestSession()
    try:
        # A session token only authenticates if the officer still exists.
        db.add(SignerIdentity(
            email=SUPER, name="Super", institution="SSB",
            designation="Inspector", registered_at=now_utc(),
        ))
        db.commit()
        yield db
    finally:
        db.close()


@pytest.fixture
def super_client(db_session):
    return TestClient(app, cookies={"nischay_session": make_session_token(SUPER)})


def test_add_stores_hmac_not_plain_sha(super_client, db_session):
    resp = super_client.post(
        "/api/screen/watchlist/add",
        data={"category": "pan", "value": PAN, "reason": "test"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("ok") is True

    row = db_session.query(WatchlistEntry).one()
    expected = screening.watchlist_hmacs(PAN)[0]
    assert row.identifier_hash == expected
    assert row.hash_algo == screening.WATCHLIST_HMAC_ALGO
    # The old, brute-forceable digest must not be what is stored.
    assert row.identifier_hash != screening.sha256(PAN)
    assert row.mask == screening.mask(PAN)


def test_duplicate_add_is_deduped_across_normalisation(super_client, db_session):
    first = super_client.post(
        "/api/screen/watchlist/add", data={"category": "pan", "value": PAN}
    )
    assert first.status_code == 200, first.text
    assert first.json().get("already") is not True

    # Same identifier, different spacing/case: norm() must collapse it.
    second = super_client.post(
        "/api/screen/watchlist/add", data={"category": "pan", "value": "abcde-1234f"}
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body.get("already") is True
    assert body.get("id") == first.json().get("id")
    assert db_session.query(WatchlistEntry).count() == 1


def test_legacy_plain_sha_row_matches_and_upgrades(db_session):
    legacy = WatchlistEntry(
        identifier_hash=screening.sha256(PAN),
        hash_algo=None,
        category="pan",
        mask=screening.mask(PAN),
        added_by="legacy@example.com",
        created_at=now_utc(),
    )
    db_session.add(legacy)
    db_session.commit()

    hits = screening.watchlist_matches(db_session, {"pan": PAN})
    assert hits == [{"field": "pan", "mask": screening.mask(PAN)}]

    db_session.expire_all()
    row = db_session.query(WatchlistEntry).one()
    assert row.identifier_hash == screening.watchlist_hmacs(PAN)[0]
    assert row.hash_algo == screening.WATCHLIST_HMAC_ALGO


def test_legacy_plain_sha_row_upgrades_on_add(super_client, db_session):
    legacy = WatchlistEntry(
        identifier_hash=screening.sha256(PAN),
        category="pan",
        mask=screening.mask(PAN),
        added_by="legacy@example.com",
        created_at=now_utc(),
    )
    db_session.add(legacy)
    db_session.commit()

    resp = super_client.post(
        "/api/screen/watchlist/add", data={"category": "pan", "value": PAN}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("already") is True

    db_session.expire_all()
    row = db_session.query(WatchlistEntry).one()
    assert row.identifier_hash == screening.watchlist_hmacs(PAN)[0]
    assert row.hash_algo == screening.WATCHLIST_HMAC_ALGO


def test_unlisted_identifier_does_not_match(db_session):
    db_session.add(
        WatchlistEntry(
            identifier_hash=screening.watchlist_hmacs(PAN)[0],
            hash_algo=screening.WATCHLIST_HMAC_ALGO,
            category="pan",
            mask=screening.mask(PAN),
            added_by="legacy@example.com",
            created_at=now_utc(),
        )
    )
    db_session.commit()

    assert screening.watchlist_matches(db_session, {"pan": "ZZZZZ9999Z"}) == []
    assert screening.watchlist_matches(db_session, {"passport": "QQQQQ1111Q"}) == []


def _seed_under_key(db_session, key: bytes) -> str:
    digest = hmac.new(key, screening.norm(PAN).encode("utf-8"), hashlib.sha256).hexdigest()
    db_session.add(
        WatchlistEntry(
            identifier_hash=digest,
            hash_algo=screening.WATCHLIST_HMAC_ALGO,
            category="pan",
            mask=screening.mask(PAN),
            added_by="legacy@example.com",
            created_at=now_utc(),
        )
    )
    db_session.commit()
    return digest


def test_previous_key_rows_still_match(db_session, monkeypatch):
    """Rows indexed before a key rotation must keep matching via the key ring."""
    old_key = hashlib.sha256(b"outgoing-watchlist-key").digest()
    monkeypatch.setattr(app_keys, "_WATCHLIST_KEYS", [app_keys.WATCHLIST_KEY, old_key])
    _seed_under_key(db_session, old_key)

    assert screening.watchlist_matches(db_session, {"pan": PAN}) == [
        {"field": "pan", "mask": screening.mask(PAN)}
    ]


def test_add_finds_row_indexed_under_previous_key(super_client, db_session, monkeypatch):
    old_key = hashlib.sha256(b"outgoing-watchlist-key").digest()
    monkeypatch.setattr(app_keys, "_WATCHLIST_KEYS", [app_keys.WATCHLIST_KEY, old_key])
    _seed_under_key(db_session, old_key)

    resp = super_client.post(
        "/api/screen/watchlist/add", data={"category": "pan", "value": PAN}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("already") is True
    assert db_session.query(WatchlistEntry).count() == 1
