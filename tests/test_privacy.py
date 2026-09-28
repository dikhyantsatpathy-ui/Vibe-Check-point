"""
Zero-storage / PII-at-rest regression tests.

`screening_reports.ephemeral_raw_fields` held the UNMASKED extraction result
(holder name, full DOB, complete document numbers, address) so the desk could
cross-compare documents within an open session. Its column comment claimed it
was "wiped when session closes" -- nothing ever did that, so every completed
screening left a plaintext identity record in the database forever.

That contradicted the README's zero-storage claim and, more seriously, the
declaration printed on the BSA Section 65B court certificate. These tests pin
the corrected behaviour.
"""

import hashlib
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import main
from main import Base, ScreeningReport, ScreeningSession, SignerIdentity, app, make_session_token, now_utc

OFFICER = "officer@ssb.gov.in"
SUPER = os.environ.get("SUPER_ADMINS", "").split(",")[0].strip() or "test-superadmin@example.com"

# Unmasked values, i.e. exactly what must not survive a settled session.
RAW_FIELDS = {
    "name": "ARJUN SINHA",
    "dob": "1990-08-15",
    "pan": "ABCPS1234F",
    "aadhaar": "234512345670",
    "address": "12 Sahid Nagar, Patna 800001",
}


@pytest.fixture
def env(monkeypatch):
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


def _seed_session_with_docs(db, sid, *, raw, status="open", docs=1):
    s = db.query(ScreeningSession).filter_by(id=sid).first()
    if not s:
        s = ScreeningSession(
            id=sid, status=status, verdict="PENDING" if status == "open" else "CLEAR",
            risk_score=10, checkpoint="Raxaul", screener=OFFICER,
            comparison="{}", note="", created_at=now_utc(), updated_at=now_utc(),
        )
        db.add(s)
    for i in range(docs):
        fhash = f"{i:02d}" * 32
        prev = "GENESIS" if i == 0 else f"{i - 1:02d}" * 32
        block = hashlib.sha256(
            f"{prev}:{fhash}:CLEAR:10:{now_utc()}:{OFFICER}".encode("utf-8")
        ).hexdigest()
        db.add(ScreeningReport(
            id=f"{sid}-doc{i}", file_hash=fhash, filename="doc.jpg",
            doc_type="pan", checkpoint="Raxaul", verdict="CLEAR", risk_score=10,
            confidence=0.9,
            # masked, as the report always stores
            extracted_fields='{"pan":"****234F"}',
            signals="[]", screener=OFFICER, created_at=now_utc(),
            session_id=sid,
            # each document signs its own hash-chain block
            previous_hash=prev, ledger_hash=block,
            # unmasked, present only while the session is open
            ephemeral_raw_fields=None if raw is None else json.dumps(raw),
        ))
    db.commit()


# --------------------------------------------------------------------------- #
# Wipe on settlement
# --------------------------------------------------------------------------- #

def test_approve_wipes_raw_fields(env):
    with env() as db:
        _seed_session_with_docs(db, "s-approve", raw=RAW_FIELDS)
    client = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    resp = client.post("/api/sessions/s-approve/close", data={"verdict": "approve"})
    assert resp.status_code == 200, resp.text
    with env() as db:
        rows = db.query(ScreeningReport).filter_by(session_id="s-approve").all()
        assert rows, "documents should still exist for the audit trail"
        for r in rows:
            assert r.ephemeral_raw_fields is None, (
                "unmasked identity fields survived an approved session"
            )
            # The audit row itself must remain intact.
            assert r.file_hash and r.ledger_hash


def test_flag_for_review_wipes_raw_fields(env):
    with env() as db:
        _seed_session_with_docs(db, "s-flag", raw=RAW_FIELDS)
    client = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    resp = client.post("/api/sessions/s-flag/close", data={"verdict": "flag"})
    assert resp.status_code == 200, resp.text
    with env() as db:
        for r in db.query(ScreeningReport).filter_by(session_id="s-flag").all():
            assert r.ephemeral_raw_fields is None


def test_adjudicate_wipes_raw_fields(env):
    with env() as db:
        _seed_session_with_docs(db, "s-adj", raw=RAW_FIELDS, status="flagged")
    client = TestClient(app, cookies={"nischay_session": make_session_token(SUPER)})
    resp = client.post("/api/sessions/s-adj/adjudicate", data={"decision": "CLEARED"})
    assert resp.status_code == 200, resp.text
    with env() as db:
        for r in db.query(ScreeningReport).filter_by(session_id="s-adj").all():
            assert r.ephemeral_raw_fields is None


def test_remove_document_wipes_raw_fields(env):
    with env() as db:
        _seed_session_with_docs(db, "s-rm", raw=RAW_FIELDS)
    client = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    resp = client.post("/api/sessions/s-rm/documents/s-rm-doc0/remove")
    assert resp.status_code == 200, resp.text
    with env() as db:
        r = db.query(ScreeningReport).filter_by(id="s-rm-doc0").first()
        assert r.removed_at is not None
        assert r.ephemeral_raw_fields is None, (
            "a document detached from its session must not keep its raw fields"
        )


def test_open_session_keeps_raw_fields_for_comparison(env):
    """The wipe must not be so eager that cross-document comparison breaks."""
    with env() as db:
        _seed_session_with_docs(db, "s-open", raw=RAW_FIELDS)
    with env() as db:
        r = db.query(ScreeningReport).filter_by(id="s-open-doc0").first()
        assert r.ephemeral_raw_fields is not None
        assert "ARJUN SINHA" in r.ephemeral_raw_fields


# --------------------------------------------------------------------------- #
# TTL sweep
# --------------------------------------------------------------------------- #

def test_ttl_sweep_clears_idle_sessions(env, monkeypatch):
    """An abandoned session must not keep raw fields forever."""
    from datetime import datetime, timedelta, timezone

    with env() as db:
        _seed_session_with_docs(db, "s-stale", raw=RAW_FIELDS)
        s = db.query(ScreeningSession).filter_by(id="s-stale").first()
        # Backdate well past the TTL.
        s.updated_at = (
            datetime.now(timezone.utc) - timedelta(hours=48)
        ).strftime("%Y-%m-%d %H:%M:%S UTC")
        db.commit()

    monkeypatch.setattr(main, "RAW_FIELD_TTL_MINUTES", 240)
    client = TestClient(app, cookies={"nischay_session": make_session_token(SUPER)})
    resp = client.post("/api/sessions/sweep-raw-fields")
    assert resp.status_code == 200, resp.text
    assert resp.json()["sessions_swept"] >= 1
    with env() as db:
        for r in db.query(ScreeningReport).filter_by(session_id="s-stale").all():
            assert r.ephemeral_raw_fields is None


def test_ttl_sweep_leaves_fresh_sessions_alone(env):
    client = TestClient(app, cookies={"nischay_session": make_session_token(SUPER)})
    with env() as db:
        _seed_session_with_docs(db, "s-fresh", raw=RAW_FIELDS)
    resp = client.post("/api/sessions/sweep-raw-fields")
    assert resp.status_code == 200
    assert resp.json()["sessions_swept"] == 0
    with env() as db:
        r = db.query(ScreeningReport).filter_by(id="s-fresh-doc0").first()
        assert r.ephemeral_raw_fields is not None


def test_sweep_requires_supervisor(env):
    client = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    assert client.post("/api/sessions/sweep-raw-fields").status_code == 403


# --------------------------------------------------------------------------- #
# Response redaction
# --------------------------------------------------------------------------- #

def test_non_supervisor_does_not_receive_raw_fields(env):
    """A supervisory queue is about verdicts, not identity records."""
    with env() as db:
        _seed_session_with_docs(db, "s-resp", raw=RAW_FIELDS)
    officer = TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})
    detail = officer.get("/api/sessions/s-resp")
    assert detail.status_code == 200
    docs = detail.json()["documents"]
    assert docs
    for d in docs:
        assert not d.get("raw_fields"), "raw fields leaked to a line officer"
        assert d.get("raw_fields_withheld") is True
        # Masked fields and digests are still there -- the desk needs them.
        assert d.get("masked") is not None
    assert "ARJUN SINHA" not in detail.text


def test_report_row_helper_does_not_emit_raw_fields_by_default(env):
    with env() as db:
        _seed_session_with_docs(db, "s-row", raw=RAW_FIELDS)
        row = db.query(ScreeningReport).filter_by(id="s-row-doc0").first()
        assert "raw_fields" not in main._screen_row(row)
        # Explicit opt-in still works for an authorised caller.
        assert "raw_fields" in main._screen_row(row, include_raw_fields=True)
