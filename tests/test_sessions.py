"""
Border SESSION flow tests (SIH26188).

One traveller at the desk = one session. Documents are screened into it one at
a time, identifier values are cross-compared for discrepancies, the desk
approves (signing a chained SHA-256 block into the ledger) or flags the session
into the supervisory review queue. Asserts the zero-storage invariant: only
digests, masks and comparison flags survive — never raw identifier values.

Cross-document comparisons are seeded deterministically (direct report rows
with controlled field digests) so the tests never depend on OCR; one test
screens a real document through /api/screen end-to-end to prove the session
stamping path.
"""

import hashlib
import io
import json
import os
import sys
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import main
sys.modules["app.main"] = main
from main import Base, ScreeningReport, ScreeningSession, SignerIdentity, app, make_session_token, now_utc

import session as session_mod

OFFICER = "officer@ssb.gov.in"
SUPER = "dikhyantsatpathy@gmail.com"


def _h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rec(value: str, script: str = "latin"):
    """field_hashes record: {h: digest of normalized value, s: source script}."""
    return {"h": _h(value), "s": script}


def _synth_image(w: int = 140, h: int = 140) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, w - 10, h - 10], outline="black", fill="lightblue")
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    db = TestSession()
    try:
        db.add(SignerIdentity(email=OFFICER, name="Officer One",
                              institution="SSB", designation="Assistant Commandant",
                              registered_at=now_utc()))
        db.commit()
    finally:
        db.close()
    return TestClient(app, cookies={"nischay_session": make_session_token(OFFICER)})


@pytest.fixture
def super_client():
    return TestClient(app, cookies={"nischay_session": make_session_token(SUPER)})


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _open_session(client, checkpoint="Panitanki ICP") -> str:
    resp = client.post("/api/sessions", data={"checkpoint": checkpoint})
    assert resp.status_code == 200, resp.text
    s = resp.json()
    assert s["status"] == "open"
    assert s["verdict"] == "PENDING"
    return s["id"]


def _ts(seconds_after=0):
    base = datetime.strptime(now_utc(), "%Y-%m-%d %H:%M:%S UTC")
    return (base + timedelta(seconds=seconds_after)).strftime("%Y-%m-%d %H:%M:%S UTC")


def _seed_doc(db, session_id, doc_type, masked, digests, risk=15,
              ledger_hash=None, seconds_after=0):
    """Insert a screening report row with controlled per-field digests + masked
    fields (mirrors what run_screening would persist). Returns its id."""
    rep = ScreeningReport(
        id=uuid.uuid4().hex[:16],
        file_hash=_h(f"{session_id}:{doc_type}:{seconds_after}"),
        filename=f"{doc_type}_{seconds_after}.jpg",
        doc_type=doc_type,
        checkpoint="Panitanki ICP",
        verdict="CLEAR",
        risk_score=risk,
        confidence=0.92,
        extracted_fields=json.dumps(masked),
        signals="[]",
        modules='{"validation":{"verdict":"PASS"},"tampering":{"verdict":"PASS"},"face":{"verdict":"NO_LIVE_FRAME"}}',
        previous_hash=None,
        ledger_hash=ledger_hash,
        session_id=session_id,
        field_hashes=json.dumps(digests),
        screener=OFFICER,
        created_at=_ts(seconds_after),
    )
    db.add(rep)
    return rep.id


def _screen_doc_e2e(client, session_id, doc_type, declared, filename="doc.jpg"):
    """Screening-desk path: POST /api/screen with the bounding session_id."""
    return client.post(
        "/api/screen",
        files={"file": (filename, _synth_image(), "image/jpeg")},
        data={"doc_type": doc_type, "checkpoint": "Panitanki ICP",
              "declared": json.dumps(declared), "session_id": session_id},
    )


# --------------------------------------------------------------------------- #
# Full approve flow
# --------------------------------------------------------------------------- #

def test_session_approve_signs_ledger(client):
    """Two consistent documents -> CONSISTENT comparison -> approve -> signed block."""
    sid = _open_session(client)
    db = main.SessionLocal()
    try:
        _seed_doc(db, sid, "passport",
                  {"name": "ANIL K****", "dob": "1990-04-12", "passport": "****4567"},
                  {"name": _rec("ANIL KUMAR"), "dob": _rec("1990-04-12"), "passport": _rec("K1234567")},
                  ledger_hash=_h("blk-a"), seconds_after=1)
        _seed_doc(db, sid, "visa",
                  {"name": "ANIL K****", "dob": "1990-04-12", "passport": "****4567"},
                  {"name": _rec("ANIL KUMAR"), "dob": _rec("1990-04-12"), "passport": _rec("K1234567")},
                  ledger_hash=_h("blk-b"), seconds_after=2)
        db.commit()
    finally:
        db.close()

    detail = client.get(f"/api/sessions/{sid}").json()
    assert detail["document_count"] == 2
    assert len(detail["documents"]) == 2
    assert detail["comparison"]["verdict"] == "CONSISTENT"
    statuses = {c["field"]: c["status"] for c in detail["comparison"]["checks"]}
    assert statuses["name"] == "agree"
    assert statuses["dob"] == "agree"
    assert statuses["passport"] == "agree"

    resp = client.post(f"/api/sessions/{sid}/close", data={"verdict": "approve"})
    assert resp.status_code == 200, resp.text
    closed = resp.json()
    assert closed["status"] == "approved"
    assert closed["verdict"] == "CLEAR"
    assert closed["block_hash"] and len(closed["block_hash"]) == 64
    assert closed["prev_hash"] == "GENESIS"

    # Zero-storage: no raw identifier values anywhere in the payload.
    assert "ANIL KUMAR" not in json.dumps(resp.json())
    assert "K1234567" not in json.dumps(resp.json())

    lgr = client.get("/api/sessions/ledger/blocks").json()
    assert lgr["total_blocks"] == 1
    assert lgr["head_hash"] == closed["block_hash"]

    verify = client.get("/api/sessions/ledger/verify").json()
    assert verify["valid"] is True
    assert verify["status"] == "CHAIN_VALID_UNBROKEN"


# --------------------------------------------------------------------------- #
# Discrepancy -> flag -> review queue -> supervisory adjudication
# --------------------------------------------------------------------------- #

def test_session_discrepancy_flag_and_adjudicate(client, super_client):
    """Disagreeing DOB -> DISCREPANCY -> approve fails closed -> flag -> queue -> super CLEARED."""
    sid = _open_session(client)
    db = main.SessionLocal()
    try:
        _seed_doc(db, sid, "passport",
                  {"name": "ANIL K****", "dob": "1990-04-12", "passport": "****4567"},
                  {"name": _rec("ANIL KUMAR"), "dob": _rec("1990-04-12"), "passport": _rec("K1234567")}, seconds_after=1)
        _seed_doc(db, sid, "visa",
                  {"name": "ANIL K****", "dob": "1985-09-01", "passport": "****4567"},
                  {"name": _rec("ANIL KUMAR"), "dob": _rec("1985-09-01"), "passport": _rec("K1234567")}, seconds_after=2)
        db.commit()
    finally:
        db.close()

    detail = client.get(f"/api/sessions/{sid}").json()
    assert detail["comparison"]["verdict"] == "DISCREPANCY"
    dob_check = next(c for c in detail["comparison"]["checks"] if c["field"] == "dob")
    assert dob_check["status"] == "disagree"

    # Approving a session with an unresolved discrepancy FAILS CLOSED.
    bad = client.post(f"/api/sessions/{sid}/close", data={"verdict": "approve"})
    assert bad.status_code == 409

    # Flag it into the review queue.
    flag = client.post(f"/api/sessions/{sid}/close", data={"verdict": "flag", "note": "DOB mismatch"})
    assert flag.status_code == 200, flag.text
    assert flag.json()["status"] == "flagged"
    flagged = client.get("/api/sessions", params={"status": "flagged"}).json()
    assert any(s["id"] == sid for s in flagged["sessions"])

    # A lane officer cannot adjudicate.
    denied = client.post(f"/api/sessions/{sid}/adjudicate", data={"decision": "CLEARED"})
    assert denied.status_code == 403

    # The supervisor clears it -> approved and signed into the ledger.
    settled = super_client.post(f"/api/sessions/{sid}/adjudicate",
                                data={"decision": "CLEARED", "note": "Verified over phone"})
    assert settled.status_code == 200, settled.text
    s = settled.json()
    assert s["status"] == "approved"
    assert s["verdict"] == "CLEAR"
    assert s["adjudicator"] == SUPER
    assert s["block_hash"] and len(s["block_hash"]) == 64

    verify = super_client.get("/api/sessions/ledger/verify").json()
    assert verify["valid"] is True


# --------------------------------------------------------------------------- #
# Rejected sessions are signed as evidence; chain stays linked
# --------------------------------------------------------------------------- #

def test_session_rejected_is_signed_evidence(client, super_client):
    """A supervisor-rejected session is still signed (evidence trail) and the chain stays linked."""
    db = main.SessionLocal()
    try:
        sid1 = _open_session(client)
        _seed_doc(db, sid1, "passport",
                  {"name": "RAVI V****", "dob": "1992-06-18", "passport": "****4321"},
                  {"name": _rec("RAVI VERMA"), "dob": _rec("1992-06-18"), "passport": _rec("V7654321")},
                  ledger_hash=_h("blk-1a"), seconds_after=1)
        _seed_doc(db, sid1, "visa",
                  {"name": "RAVI V****", "dob": "1992-06-18", "passport": "****4321"},
                  {"name": _rec("RAVI VERMA"), "dob": _rec("1992-06-18"), "passport": _rec("V7654321")},
                  ledger_hash=_h("blk-1b"), seconds_after=2)
        db.commit()

        appr = client.post(f"/api/sessions/{sid1}/close", data={"verdict": "approve"})
        assert appr.status_code == 200, appr.text
        head1 = appr.json()["block_hash"]

        # Second traveller: flagged, then CONFIRMED_FRAUD.
        sid2 = _open_session(client)
        _seed_doc(db, sid2, "pan",
                  {"pan": "****1234F"}, {"dob": _rec("1975-01-01")},
                  risk=70, ledger_hash=_h("blk-2a"), seconds_after=3)
        db.commit()

        flag = client.post(f"/api/sessions/{sid2}/close", data={"verdict": "flag", "note": "Known fraud cohort"})
        assert flag.status_code == 200
        reject = super_client.post(f"/api/sessions/{sid2}/adjudicate",
                                   data={"decision": "CONFIRMED_FRAUD", "note": "Interpol match"})
        assert reject.status_code == 200
        rej = reject.json()
        assert rej["status"] == "rejected"
        assert rej["verdict"] == "FLAGGED"
        assert rej["block_hash"]
        assert rej["prev_hash"] == head1  # chained onto the first approved block

        lgr = client.get("/api/sessions/ledger/blocks").json()
        assert lgr["total_blocks"] == 2
        assert lgr["blocks"][1]["prev_hash"] == lgr["blocks"][0]["block_hash"]

        verify = client.get("/api/sessions/ledger/verify").json()
        assert verify["valid"] is True
        assert verify["total_blocks"] == 2
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Ledger tamper detection
# --------------------------------------------------------------------------- #

def test_session_ledger_detects_tamper(client):
    """Flipping a stored session block hash is caught by the verify walk."""
    sid = _open_session(client)
    db = main.SessionLocal()
    try:
        _seed_doc(db, sid, "passport",
                  {"name": "SONAL D***", "dob": "1988-03-09", "passport": "****8776"},
                  {"name": _rec("SONAL DAS"), "dob": _rec("1988-03-09"), "passport": _rec("S9988776")},
                  seconds_after=1)
        db.commit()
    finally:
        db.close()

    resp = client.post(f"/api/sessions/{sid}/close", data={"verdict": "approve"})
    assert resp.status_code == 200, resp.text
    assert client.get("/api/sessions/ledger/verify").json()["valid"] is True

    db = main.SessionLocal()
    try:
        s = db.query(ScreeningSession).filter_by(id=sid).first()
        s.ledger_hash = "0" * 64  # tamper
        db.commit()
    finally:
        db.close()

    verify = client.get("/api/sessions/ledger/verify").json()
    assert verify["valid"] is False
    assert verify["broken_at"] == sid
    assert verify["status"] == "CHAIN_BROKEN_TAMPERED_BLOCK"


# --------------------------------------------------------------------------- #
# Ownership + end-to-end /api/screen stamping
# --------------------------------------------------------------------------- #

def test_session_ownership_and_screen_stamping(client, super_client):
    """Supervisors see the whole desk; documents screen into an OPEN session and
    are rejected once it is closed."""
    sid = _open_session(client)

    assert any(s["id"] == sid for s in super_client.get("/api/sessions").json()["sessions"])

    # End-to-end: screen a document into the session via /api/screen.
    resp = _screen_doc_e2e(client, sid, "other",
                           {"name": "ANIL KUMAR", "dob": "1990-04-12", "passport": "K1234567"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("session_id") == sid
    assert body.get("field_hashes")  # per-doc digests persisted for cross-compare

    detail = client.get(f"/api/sessions/{sid}").json()
    assert detail["document_count"] == 1
    assert detail["documents"][0]["id"] == body["id"]
    assert detail["comparison"]["verdict"] == "CONSISTENT"  # single doc: fields present but nothing to disagree

    # Close the session, then a late document must be rejected.
    closed = client.post(f"/api/sessions/{sid}/close", data={"verdict": "approve"})
    assert closed.status_code == 200
    late = _screen_doc_e2e(client, sid, "other", {"dob": "1990-04-12"}, filename="late.jpg")
    assert late.status_code == 409


# --------------------------------------------------------------------------- #
# Cross-script / canonical-name comparison unit tests
# --------------------------------------------------------------------------- #

def test_field_hashes_are_script_aware():
    """Same-script names compare exactly; a Devanagari-sourced name is never a
    hard mismatch against a Latin one — it escalates to human review."""
    latin = session_mod.field_hashes({"mrz_name": "ANIL KUMAR", "dob": "1990-04-12", "passport": "K1234567"})
    assert latin["name"] == {"h": _h("ANILKUMAR"), "s": "latin"}
    assert latin["dob"]["h"] == _h("19900412")  # norm() strips separators
    assert latin["passport"]["h"] == _h("K1234567")

    devanagari = session_mod.field_hashes({"mrz_name": "अनिल कुमार", "dob": "1990-04-12", "passport": "K1234567"})
    assert devanagari["name"]["s"] == "devanagari"
    assert devanagari["dob"] == latin["dob"]  # non-name fields are script-agnostic

    # No name key -> no name record (canonical lookup covers name/holder_name/mrz_name).
    no_name = session_mod.field_hashes({"pan": "ABCDE1234F"})
    assert no_name == {}


def test_build_comparison_verdicts():
    base = {
        "field_hashes": {"name": _rec("ANIL KUMAR"), "dob": _rec("1990-04-12")},
        "masked": {"name": "ANIL K****", "dob": "1990-04-12"},
    }
    agree = session_mod.build_comparison([
        {**base, "doc_type": "passport"},
        {**base, "doc_type": "visa"},
    ])
    assert agree["verdict"] == "CONSISTENT"
    assert agree["risk_bump"] == 0
    assert next(c for c in agree["checks"] if c["field"] == "name")["status"] == "agree"

    disagree = session_mod.build_comparison([
        {**base, "doc_type": "passport"},
        {**base, "doc_type": "visa",
         "field_hashes": {"name": _rec("ANIL KUMAR"), "dob": _rec("1985-09-01")}},
    ])
    assert disagree["verdict"] == "DISCREPANCY"
    assert disagree["risk_bump"] == 30
    assert next(c for c in disagree["checks"] if c["field"] == "dob")["status"] == "disagree"

    cross_script = session_mod.build_comparison([
        {**base, "doc_type": "passport", "masked": {"name": "ANIL K****", "dob": "1990-04-12"}},
        {**base, "doc_type": "visa",
         "field_hashes": {"name": _rec("अनिल कुमार", "devanagari"), "dob": _rec("1990-04-12")},
         "masked": {"name": "अनि********", "dob": "1990-04-12"}},
    ])
    assert cross_script["verdict"] == "CONSISTENT"  # NOT a hard disagreement
    assert cross_script["risk_bump"] == 0
    assert next(c for c in cross_script["checks"] if c["field"] == "name")["status"] == "cross-script"

    single = session_mod.build_comparison([
        {**base, "doc_type": "pan"},
    ])
    assert single["verdict"] == "CONSISTENT"  # single doc: fields marked 'single', nothing to disagree

    empty = session_mod.build_comparison([
        {"doc_type": "pan", "field_hashes": {}, "masked": {}},
        {"doc_type": "pan", "field_hashes": {}, "masked": {}},
    ])
    assert empty["verdict"] == "INCOMPLETE"  # no comparable field on any document