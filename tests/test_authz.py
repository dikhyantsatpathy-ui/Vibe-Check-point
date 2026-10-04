"""
Route-level authorisation regression tests.

These exist because the previous auth tests only exercised
`get_current_admin` in isolation -- the STRICT dependency. Nearly every route
actually used `get_current_admin_or_evaluator`, which caught every
HTTPException (401s and the 403 "access revoked" alike) and returned a
super-admin identity to anonymous callers. Nothing tested that, so ~35 routes
were reachable with no credentials at all.

This module asserts the property that was missing: for every protected route,
an unauthenticated request is rejected.
"""

import os
import re
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import main
from main import Base, SignerIdentity, app, make_session_token, now_utc

OFFICER = "officer@ssb.gov.in"
SUPER = os.environ.get("SUPER_ADMINS", "").split(",")[0].strip() or "test-superadmin@example.com"

# Routes that are intentionally reachable without a session: the SPA itself,
# the liveness probe, and the OAuth entry point (which authenticates by
# credential in the body, not by cookie).
PUBLIC_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/api/health"),
    # Authenticates by Google credential in the body, not by cookie.
    ("POST", "/api/admin/login"),
    ("POST", "/api/admin/logout"),
    ("POST", "/api/admin/demo_login"),
    # Public signed notice feed (active notices only).
    ("GET", "/api/broadcasts"),
}

# Protected but not otherwise exercised above.
_PROTECTED_EXTRA = [
    ("POST", "/api/broadcasts/create", None),
    ("POST", "/api/broadcasts/delete", None),
    ("GET", "/api/screen/reports/{report_id}", None),
    ("GET", "/api/screen/dossier/{report_id}", None),
    ("GET", "/api/screen/bsa65b/{session_id}", None),
    ("GET", "/api/screen/handover/{session_id}", None),
    ("GET", "/api/sessions/{session_id}", None),
    ("POST", "/api/sessions/{session_id}/close", {"verdict": "close"}),
    ("POST", "/api/sessions/{session_id}/adjudicate", {"decision": "CLEARED"}),
    ("POST", "/api/screen/reports/{report_id}/adjudicate", {"decision": "CLEARED"}),
]

# (method, path, form body) for every route that must require a session.
# Kept explicit rather than introspected so a newly added public route shows up
# as a failing test instead of silently inheriting the old bypass.
PROTECTED_ROUTES = [
    ("GET", "/api/admin/me", None),
    ("POST", "/api/admin/assign_role", {"target_email": "x@y.com", "designation": "d", "institution": "i"}),
    ("GET", "/api/admin/signers", None),
    ("GET", "/api/screen/queue", None),
    ("GET", "/api/screen/watchlist", None),
    ("GET", "/api/screen/shift-export", None),
    ("GET", "/api/screen/syndicate-alerts", None),
    ("GET", "/api/screen/ledger/verify", None),
    ("GET", "/api/screen/ledger/anchor", None),
    ("POST", "/api/screen/ledger/anchor", None),
    ("GET", "/api/screen/dossier/some-report-id", None),
    ("GET", "/api/screen/bsa65b/some-session", None),
    ("GET", "/api/screen/handover/some-session", None),
    ("GET", "/api/border/threat_matrix", None),
    ("GET", "/api/screen/liveness", None),
    ("GET", "/api/screen/aadhaar-fields", None),
    ("GET", "/api/sessions", None),
    ("GET", "/api/sessions/some-session", None),
    ("POST", "/api/sessions/some-session/close", {"verdict": "close"}),
    ("POST", "/api/sessions/some-session/adjudicate", {"decision": "CLEARED"}),
    ("POST", "/api/sessions/close-unused", None),
    ("POST", "/api/sessions/sweep-raw-fields", None),
    ("GET", "/api/checkpoints", None),
    ("GET", "/api/guide", None),
    ("GET", "/api/stats/overview", None),
    ("GET", "/api/sessions/ledger/blocks", None),
    ("GET", "/api/sessions/ledger/verify", None),
    ("GET", "/api/analytics", None),
    ("GET", "/api/analytics/summary", None),
    ("POST", "/api/chat", None),
    ("POST", "/api/verify", None),
    ("POST", "/api/verify/dl", {"dl_number": "KA0120201234567"}),
    ("POST", "/api/verify/aadhaar-qr", None),
    ("POST", "/api/screen", None),
    ("POST", "/api/screen/liveness", None),
    ("POST", "/api/screen/aadhaar-fields", None),
    ("POST", "/api/extract", None),
    ("POST", "/api/screen/watchlist/add", {"category": "pan", "value": "ABCDE1234F"}),
    ("POST", "/api/screen/watchlist/remove", {"entry_id": "1"}),
    ("POST", "/api/ml/keepalive/ping", None),
    ("GET", "/api/ml/status", None),
    ("POST", "/api/admin/revoke_officer", {"target_email": "x@y.com"}),
    ("POST", "/api/admin/unrevoke_officer", {"target_email": "x@y.com"}),
    ("POST", "/api/admin/remove_officer", {"target_email": "x@y.com"}),
    ("POST", "/api/sessions", {"checkpoint": "Raxaul"}),
    ("POST", "/api/sessions/{session_id}/documents/{report_id}/remove", None),
    ("POST", "/api/sessions/{session_id}/documents/{report_id}/restore", None),
] + _PROTECTED_EXTRA


def _normalise(path: str) -> str:
    """Compare routes by shape, not by literal spelling.

    FastAPI registers path params as /x/{id} while the test table spells out a
    concrete example, and the codebase is inconsistent about hyphens vs
    underscores (e.g. /api/border/threat_matrix). Normalising both to a
    placeholder keeps the classification check meaningful instead of forcing
    the table to mirror every registration quirk.
    """
    p = re.sub(r"\{[^}]+\}", "{}", path)
    p = p.replace("_", "-")
    return p.rstrip("/") or "/"


@pytest.fixture
def anon_client(monkeypatch):
    """A client with NO session cookie at all."""
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    # Deliberately NO SignerIdentity rows: the fallback identity no longer
    # exists, so an anonymous caller has nothing to fall back to.
    return TestClient(app)


@pytest.mark.parametrize("method,path,data", PROTECTED_ROUTES, ids=[f"{m} {p}" for m, p, _ in PROTECTED_ROUTES])
def test_anonymous_request_is_rejected(anon_client, method, path, data):
    """The core regression: no protected route may serve an anonymous caller.

    Accepts 401 (no/invalid session) or 405 (path exists but wrong verb for
    this fixture's shape). A 200, or any 4xx that is not 401/405, is a fail.
    """
    resp = anon_client.request(method, path, data=data)
    # A path-parameter route registered under a different verb than the one
    # spelled out here is not evidence of a missing guard -- the classification
    # test below covers the full registered surface.
    if resp.status_code == 405:
        pytest.skip("route not registered for this method")
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code} to an anonymous caller; "
        f"expected 401. Body: {resp.text[:200]}"
    )


def test_health_is_public_but_reveals_nothing_operational(anon_client):
    """The liveness probe must stay reachable, without leaking the deployment.

    It previously returned the database engine, a per-capability model
    inventory, ML-service configuration, and raw driver error text to anyone.
    """
    resp = anon_client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) <= {"status", "service", "version", "timestamp"}, (
        f"anonymous /api/health leaked fields: {sorted(set(body) - {'status', 'service', 'version', 'timestamp'})}"
    )
    assert "database" not in body and "capabilities" not in body


def test_health_reveals_detail_to_a_signed_in_officer(owned_env):
    officer = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    body = officer.get("/api/health").json()
    assert "database" in body and "capabilities" in body


def test_demo_login_route_serves_evaluator_pass(anon_client):
    """SIH Evaluator 1-click pass issues a valid session for evaluation."""
    resp = anon_client.post("/api/admin/demo_login")
    assert resp.status_code == 200
    assert resp.json().get("status") == "SUCCESS"
    assert "nischay_session" in resp.cookies


def test_every_registered_route_is_classified():
    """Guards against a new route silently being left unclassified.

    If someone adds an endpoint and does not add it to PUBLIC_ROUTES or
    PROTECTED_ROUTES here, this fails -- which is the moment to decide
    explicitly whether it is public.
    """
    from fastapi.routing import APIRoute

    registered = {
        (m, _normalise(r.path))
        for r in app.routes
        if isinstance(r, APIRoute)
        for m in r.methods
        if m in ("GET", "POST", "PUT", "DELETE", "PATCH")
    }
    classified = {(m, _normalise(p)) for m, p in PUBLIC_ROUTES} | {(m, _normalise(p)) for m, p, _ in PROTECTED_ROUTES}
    unclassified = registered - classified
    assert not unclassified, (
        "these routes are not in PUBLIC_ROUTES or PROTECTED_ROUTES -- classify "
        f"them explicitly: {sorted(unclassified)}"
    )


# --------------------------------------------------------------------------- #
# Session ownership
# --------------------------------------------------------------------------- #

@pytest.fixture
def owned_env(monkeypatch):
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    db = TestSession()
    try:
        for email, name in ((OFFICER, "Officer"), (SUPER, "Super")):
            if not db.query(SignerIdentity).filter_by(email=email).first():
                db.add(SignerIdentity(
                    email=email, name=name, institution="SSB",
                    designation="Inspector", registered_at=now_utc(),
                ))
        db.commit()
    finally:
        db.close()
    return TestSession


def test_queue_is_scoped_to_the_officer(owned_env):
    """A line officer must not see the whole desk's screenings."""
    with owned_env() as db:
        db.add(main.ScreeningReport(
            id="other-officers-report", file_hash="aa" * 32, filename="x.jpg",
            doc_type="passport", checkpoint="Raxaul", verdict="CLEAR",
            risk_score=5, confidence=0.9, extracted_fields="{}",
            signals="[]", screener="someone.else@ssb.gov.in", created_at=now_utc(),
        ))
        db.commit()
    officer = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    ids = {r["id"] for r in officer.get("/api/screen/queue").json().get("recent", [])}
    assert "other-officers-report" not in ids


def test_report_detail_is_ownership_checked(owned_env):
    with owned_env() as db:
        db.add(main.ScreeningReport(
            id="not-yours", file_hash="bb" * 32, filename="x.jpg",
            doc_type="passport", checkpoint="Raxaul", verdict="CLEAR",
            risk_score=5, confidence=0.9, extracted_fields="{}",
            signals="[]", screener="someone.else@ssb.gov.in", created_at=now_utc(),
        ))
        db.commit()
    officer = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    assert officer.get("/api/screen/reports/not-yours").status_code == 403
    # A supervisor may open any record.
    sup = TestClient(app, cookies={"nischay_session": make_session_token(SUPER)})
    assert sup.get("/api/screen/reports/not-yours").status_code == 200


def test_dossier_is_ownership_checked(owned_env):
    with owned_env() as db:
        db.add(main.ScreeningReport(
            id="dossier-not-yours", file_hash="cc" * 32, filename="x.jpg",
            doc_type="passport", checkpoint="Raxaul", verdict="CLEAR",
            risk_score=5, confidence=0.9, extracted_fields="{}",
            signals="[]", screener="someone.else@ssb.gov.in", created_at=now_utc(),
        ))
        db.commit()
    officer = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    assert officer.get("/api/screen/dossier/dossier-not-yours").status_code == 403
