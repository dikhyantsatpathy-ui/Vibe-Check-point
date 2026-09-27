"""
Revamp feature tests (SIH26188 production-grade backend pass):
  * IST timezone serialization (UTC store -> IST display)
  * guided-flow catalog endpoints (checkpoints / guide / nationalities)
  * soft-remove of a document from an open session (ledger preserved)
  * stats overview aggregation (privacy-preserving)
  * live-image extraction endpoint (zero-storage, in-memory fields)
"""

import hashlib
import io
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
sys.modules["app.main"] = main
from main import Base, ScreeningReport, ScreeningSession, SignerIdentity, app, make_session_token, now_utc

from config import to_ist, DOCUMENT_CATALOG, CHECKPOINT_CLUSTERS, SUPPORTED_CHECKPOINTS
from guide import flow_for, expected_documents, checkpoint_catalog

OFFICER = "officer@ssb.gov.in"
SUPER = "dikhyantsatpathy@gmail.com"


def _synth_image(w: int = 160, h: int = 120) -> bytes:
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


# --------------------------------------------------------------------------- #
# IST timezone
# --------------------------------------------------------------------------- #

def test_to_ist_converts_utc_store_to_ist_display():
    assert to_ist("2026-09-23 10:00:00 UTC") == "2026-09-23 15:30:00 IST"
    assert to_ist("2026-01-01 18:30:00 UTC") == "2026-01-02 00:00:00 IST"
    assert to_ist("2026-09-23T10:00:00Z") == "2026-09-23 15:30:00 IST"
    assert to_ist(None) is None
    assert to_ist("not-a-date") == "not-a-date"


def test_session_pub_carries_ist_timestamps(client):
    r = client.post("/api/sessions", data={"checkpoint": "Sunauli",
                                           "nationality": "NP", "purpose": "trade"})
    assert r.status_code == 200
    s = r.json()
    assert s["created_at"].endswith("UTC")
    assert s["created_at_ist"].endswith("IST")
    assert s["nationality"] == "NP"
    assert s["guide"]["cluster"] == "LAND_NEPAL"
    # treaty national at a land checkpoint: passport OR nepali citizenship
    assert set(s["guide"]["expected_documents"]) & {"passport", "nepali_citizenship"}


# --------------------------------------------------------------------------- #
# Guided flow
# --------------------------------------------------------------------------- #

def test_flow_for_land_checkpoint_nepali_traveller():
    flow = flow_for(checkpoint="Raxaul", doc_type="nepali_citizenship", nationality="NP")
    assert flow["cluster"] == "LAND_NEPAL"
    assert flow["mode"] == "land"
    assert "nepali_citizenship" in flow["expected_documents"]
    assert flow["nationality_label"] == "Nepal"
    assert flow["officer_steps"][0]["phase"] == "intake"
    assert flow["traveller_steps"]


def test_flow_international_passport_requires_biometric():
    flow = flow_for(checkpoint="IGI Delhi", doc_type="passport", nationality="US")
    assert flow["cluster"] == "AIR"
    assert flow["mode"] == "air"
    assert any(st["phase"] == "biometric" for st in flow["officer_steps"])


def test_expected_documents_nationality_defaults():
    assert "passport" in expected_documents("US")
    assert "passport" in expected_documents("NP") or "nepali_citizenship" in expected_documents("NP")
    assert all(d in DOCUMENT_CATALOG for d in DOCUMENT_CATALOG)


def test_catalog_endpoints(client):
    r = client.get("/api/checkpoints")
    assert r.status_code == 200
    body = r.json()
    assert body["checkpoints"]["clusters"]
    assert "Sunauli" in body["checkpoints"]["all"]
    assert body["documents"]["passport"]["label"]
    assert any(n["code"] == "NP" for n in body["nationalities"])
    g = client.get("/api/guide?checkpoint=Panitanki&doc_type=passport&nationality=BT")
    assert g.status_code == 200
    assert g.json()["mode"] == "land"


# --------------------------------------------------------------------------- #
# Soft-remove a document from a session
# --------------------------------------------------------------------------- #

def _seed_report(db, session_id, doc_type="passport", value="L898902C",
                 created_at=None):
    fh = hashlib.sha256(value.encode()).hexdigest()
    rid = hashlib.sha256((session_id or "standalone" + value).encode()).hexdigest()[:16]
    r = ScreeningReport(
        id=rid,
        file_hash=hashlib.sha256(value.encode()).hexdigest(),
        filename="passport.jpg", doc_type=doc_type,
        checkpoint="Sunauli", verdict="CLEAR", risk_score=20,
        confidence=0.9, extracted_fields="{}", signals="[]",
        ai_detection="{}", modules='{"validation":"PASS"}',
        screener=OFFICER, created_at=created_at or now_utc(),
        session_id=session_id,
        field_hashes=json.dumps({"passport": {"h": fh, "s": "latin"}}),
    )
    db.add(r)
    return r


def test_remove_document_soft_removes_and_preserves_ledger(client):
    with main.SessionLocal() as db:
        s = ScreeningSession(id="sess1", status="open", verdict="PENDING",
                             risk_score=0, checkpoint="Sunauli", screener=OFFICER,
                             comparison="{}", note="", created_at=now_utc(),
                             updated_at=now_utc())
        db.add(s)
        r = _seed_report(db, "sess1")
        db.commit()
        rid = r.id
    resp = client.post(f"/api/sessions/sess1/documents/{rid}/remove")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    detail = client.get("/api/sessions/sess1")
    assert detail.status_code == 200
    assert detail.json()["document_count"] == 0  # removed excluded from compare
    # audit row still exists (immutability): query the raw table
    with main.SessionLocal() as db:
        row = db.query(ScreeningReport).filter_by(id=rid).first()
        assert row is not None
        assert row.removed_at is not None
        assert row.removed_by == OFFICER
        assert row.session_id is None
    # restore re-links
    resp = client.post(f"/api/sessions/sess1/documents/{rid}/restore")
    assert resp.status_code == 200
    with main.SessionLocal() as db:
        row = db.query(ScreeningReport).filter_by(id=rid).first()
        assert row.removed_at is None
        assert row.session_id == "sess1"
    assert client.get("/api/sessions/sess1").json()["document_count"] == 1


def test_remove_document_requires_open_owned_session(client):
    # closed session -> 409
    with main.SessionLocal() as db:
        s = ScreeningSession(id="closed1", status="approved", verdict="CLEAR",
                             risk_score=10, checkpoint="Raxaul", screener=OFFICER,
                             comparison="{}", note="", created_at=now_utc(),
                             updated_at=now_utc(), closed_at=now_utc())
        db.add(s)
        r = _seed_report(db, "closed1")
        db.commit()
        rid = r.id
    resp = client.post(f"/api/sessions/closed1/documents/{rid}/remove")
    assert resp.status_code == 409


# --------------------------------------------------------------------------- #
# Stats + live extraction
# --------------------------------------------------------------------------- #

def test_stats_overview(client):
    with main.SessionLocal() as db:
        _seed_report(db, None, doc_type="passport", value="P1234567X")
        db.commit()
    # also via a session so session docs get stamped
    r = client.post("/api/sessions", data={"checkpoint": "Sunauli"})
    sid = r.json()["id"]
    with main.SessionLocal() as db:
        _seed_report(db, sid, doc_type="aadhaar", value="234512345670")
        db.commit()
    resp = client.get("/api/stats/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reports"]["total_screens"] >= 2
    assert body["reports"]["verdicts"]
    # latency percentile keys always present; may be None when no seeds carry latency
    assert "min" in body["reports"]["latency_ms"]
    assert body["reports"]["generated_at_ist"].endswith("IST")
    assert body["sessions"]["total_sessions"] >= 1


def test_extract_live_image_zero_storage(client):
    img = _synth_image()
    r = client.post("/api/extract", files={
        "file": ("live.jpg", img, "image/jpeg"),
        "live_frame": ("frame.jpg", img, "image/jpeg"),
    }, data={"doc_type": "aadhaar"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["medium"] in ("image", "unknown")
    assert body["has_face_frame"] is True
    assert isinstance(body["masked_fields"], dict)
    # nothing persisted
    with main.SessionLocal() as db:
        assert db.query(ScreeningReport).count() == 0


def test_extract_rejects_bad_type(client):
    r = client.post("/api/extract", files={"file": ("x.txt", b"plain", "text/plain")})
    assert r.status_code == 415


def test_extract_autoclassifies_doctype(client):
    img = _synth_image()
    r = client.post("/api/extract", files={
        "file": ("live.jpg", img, "image/jpeg"),
    }, data={"doc_type": "other"})
    assert r.status_code == 200
    body = r.json()
    assert "detected_doc_type" in body
    assert "detected_confidence" in body
    assert "detected_scores" in body


def test_doctype_cls_direct():
    from doctype_cls import classify_document, model_available
    if not model_available():
        pytest.skip("doctype.onnx not present")
    img = _synth_image()
    res = classify_document(img)
    assert res is not None
    assert "doc_type" in res
    assert "confidence" in res
    assert "scores" in res


def test_screen_auto_heals_missing_session(client):
    img = _synth_image()
    # Provide a session ID that doesn't exist in the database yet
    ghost_session_id = "ghost_session_99"
    r = client.post("/api/screen", files={
        "file": ("pan_sample.jpg", img, "image/jpeg"),
    }, data={
        "doc_type": "pan",
        "checkpoint": "Raxaul",
        "session_id": ghost_session_id,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == ghost_session_id
    with main.SessionLocal() as db:
        sess = db.query(ScreeningSession).filter_by(id=ghost_session_id).first()
        assert sess is not None
        assert sess.status == "open"
        assert sess.label.startswith("Session ")