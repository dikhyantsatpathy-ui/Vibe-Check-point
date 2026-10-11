"""Phase T2 — Test Hardening: Contract Snapshots Suite.

Verifies schema invariants and backward-compatible additive contract snapshots
for all public and core API endpoints and core pipeline interfaces.
"""

from __future__ import annotations

import io
import os
import sys
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main
from app.main import app, Base, SignerIdentity, make_session_token, now_utc
from app.screening import run_screening
from app.face_match import compare_faces

OFFICER = "officer@ssb.gov.in"


@pytest.fixture
def auth_client(monkeypatch):
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    db = TestSession()
    try:
        if not db.query(SignerIdentity).filter_by(email=OFFICER).first():
            db.add(SignerIdentity(
                email=OFFICER, name="Officer", institution="SSB",
                designation="Inspector", registered_at=now_utc(),
            ))
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    token = make_session_token(OFFICER)
    client.cookies.set("nischay_session", token)
    return client


def test_t2_snapshot_health(auth_client):
    """GET /health and GET /api/health contract schema."""
    resp = auth_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "status" in data
    assert data["status"] == "ok"

    resp_api = auth_client.get("/api/health")
    assert resp_api.status_code == 200
    data_api = resp_api.json()
    assert isinstance(data_api, dict)
    assert "status" in data_api
    assert data_api["status"] == "ok"


def test_t2_snapshot_checkpoints(auth_client):
    """GET /api/checkpoints contract schema."""
    resp = auth_client.get("/api/checkpoints")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "checkpoints" in data
    assert "documents" in data
    assert "nationalities" in data
    cps = data["checkpoints"]
    assert isinstance(cps, dict)
    assert "clusters" in cps
    assert "all" in cps
    assert "modes" in cps
    assert isinstance(cps["clusters"], list)
    assert len(cps["clusters"]) > 0
    for cl in cps["clusters"]:
        assert {"key", "label", "mode", "checkpoints"}.issubset(cl.keys())


def test_t2_snapshot_guide(auth_client):
    """GET /api/guide contract schema."""
    resp = auth_client.get("/api/guide?checkpoint=ICP-Raxaul&doc_type=passport")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_t2_snapshot_threat_matrix(auth_client):
    """GET /api/border/threat_matrix contract schema."""
    resp = auth_client.get("/api/border/threat_matrix")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "checkpoints" in data


def test_t2_snapshot_screening_output_contract():
    """Verify screening response contains all canonical contract keys (additive schema)."""
    img = Image.new("RGB", (400, 250), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "PASSPORT SAMPLE", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    doc_bytes = buf.getvalue()

    res = run_screening(
        doc_bytes,
        filename="passport_test.jpg",
        doc_type="passport",
        checkpoint="ICP-Raxaul",
        declared={"passport": "M1234567"},
    )

    expected_canonical_keys = {
        "id",
        "file_hash",
        "filename",
        "doc_type",
        "checkpoint",
        "verdict",
        "screening_verdict",
        "screening_reasons",
        "unmeasurable_signals",
        "travel_validity",
        "syndicate_alerts",
        "risk_score",
        "confidence",
        "degraded",
        "masked_fields",
        "raw_fields",
        "field_hashes",
        "session_id",
        "watchlist_hits",
        "reasons",
        "ai_detection",
        "modules",
        "latency_ms",
        "created_at",
        "block_hash",
        "prev_hash",
    }
    missing_keys = expected_canonical_keys - set(res.keys())
    assert not missing_keys, f"Contract broken: missing keys in screening output: {missing_keys}"

    # Verify modules sub-schema
    modules = res["modules"]
    assert isinstance(modules, dict)
    expected_modules = {"extraction", "validation", "tampering", "face"}
    assert expected_modules.issubset(modules.keys())

    # Verify face module structure
    face_mod = modules["face"]
    assert "verdict" in face_mod
    assert "checks" in face_mod


def test_t2_snapshot_face_match_contract():
    """Verify face matching output contains both legacy and structured face_match keys."""
    img1 = Image.new("RGB", (100, 100), color=(100, 100, 100))
    img2 = Image.new("RGB", (100, 100), color=(120, 120, 120))
    buf1 = io.BytesIO()
    img1.save(buf1, format="JPEG")
    buf2 = io.BytesIO()
    img2.save(buf2, format="JPEG")

    res = compare_faces(buf1.getvalue(), buf2.getvalue())

    # Top-level contract keys
    required_top = {"score", "match", "method", "detail", "face_match"}
    assert required_top.issubset(res.keys()), f"Missing keys in face match: {required_top - set(res.keys())}"

    # Structured face_match contract keys
    fm = res["face_match"]
    assert isinstance(fm, dict)
    required_fm = {"mode", "similarity", "threshold", "decision"}
    assert required_fm.issubset(fm.keys()), f"Missing keys in face_match dict: {required_fm - set(fm.keys())}"
    assert fm["mode"] in ("arcface", "fallback", "unavailable")
    assert fm["decision"] in ("MATCH", "MISMATCH", "INCONCLUSIVE")
