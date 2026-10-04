"""
Unit and integration tests for:
1. Aadhaar 5-Class YOLO Field Extraction (/api/screen/aadhaar-fields)
2. Challenge-Response Webcam Liveness Verification (/api/screen/liveness)
3. Forensic Court Dossier rendering
"""

import io
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import main
from main import Base, ScreeningReport, app, make_session_token, now_utc


def _synth_image(w: int = 120, h: int = 120, color: str = "white") -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, w - 10, h - 10], outline="black", fill="lightblue")
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def client(monkeypatch):
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)

    # Set up user session cookie
    sess_token = make_session_token("officer@ssb.gov.in")
    return TestClient(app, cookies={"nischay_session": sess_token})


def test_aadhaar_fields_endpoint(client):
    """POST /api/screen/aadhaar-fields returns detected zones and model metadata."""
    img_data = _synth_image(200, 200)
    files = {"file": ("aadhaar_sample.jpg", img_data, "image/jpeg")}
    resp = client.post("/api/screen/aadhaar-fields", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "fields" in data
    assert "model" in data
    assert isinstance(data["fields"], list)


def test_liveness_endpoint(client):
    """POST /api/screen/liveness analyzes multiple frames and returns challenge-response verdict."""
    frame1 = _synth_image(96, 96, "blue")
    frame2 = _synth_image(96, 96, "white")
    files = [
        ("frames", ("f1.jpg", frame1, "image/jpeg")),
        ("frames", ("f2.jpg", frame2, "image/jpeg")),
    ]
    data = {"challenge": "blink", "client_meta": "{}"}
    resp = client.post("/api/screen/liveness", files=files, data=data)
    assert resp.status_code == 200
    res = resp.json()
    assert "verdict" in res
    assert "liveness_passed" in res
    assert "checks" in res
    assert res["challenge"] == "blink"


def test_dossier_renders(client):
    """Forensic Court Dossier renders screening record, adjudication and latency."""
    SessionLocal = main.SessionLocal
    db = SessionLocal()
    try:
        rep = ScreeningReport(
            id="test_dossier_rep",
            file_hash="deadbeef12345678",
            filename="passport_custody.jpg",
            doc_type="passport",
            checkpoint="Panitanki ICP",
            verdict="CLEAR",
            risk_score=15,
            confidence=0.94,
            extracted_fields='{"passport":"K1234567"}',
            signals='["ICAO TD3 checksums valid"]',
            modules='{"extraction":{"ran":true},"validation":{"verdict":"PASS"},"tampering":{"verdict":"PASS"},"face":{"verdict":"PASS"}}',
            screener="officer@ssb.gov.in",
            created_at=now_utc(),
        )
        db.add(rep)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/screen/dossier/test_dossier_rep")
    assert resp.status_code == 200
    assert "Evidentiary Forensic Dossier" in resp.text
    assert "CRYPTOGRAPHIC CUSTODY SEAL" in resp.text
    assert "Screened By" in resp.text
    assert "officer@ssb.gov.in" in resp.text


def test_health_endpoints(client):
    """GET /health and GET /api/health report service status and database engine."""
    for path in ("/health", "/api/health"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "database" in data
        assert "service" in data


def test_ledger_verify_chain(client):
    """GET /api/screen/ledger/verify verifies the unbroken SHA-256 hash chain."""
    resp = client.get("/api/screen/ledger/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert "valid" in data
    assert "total_blocks" in data
    assert "status" in data


def test_clean_postgres_dsn():
    """clean_postgres_dsn sanitizes malformed query strings and duplicate delimiters."""
    from main import clean_postgres_dsn

    # 1. Double query mark ?
    url1 = "postgresql://user:pass@ep-red.neon.tech/neondb?sslmode=require?sslmode=require"
    clean1 = clean_postgres_dsn(url1)
    assert clean1.count("?") == 1
    assert "sslmode=require" in clean1

    # 2. Duplicate ==
    url2 = "postgresql://user:pass@ep-red.neon.tech/neondb?sslmode==require"
    clean2 = clean_postgres_dsn(url2)
    assert "sslmode=require" in clean2

    # 3. Unencoded = in value (options=endpoint=ep-123)
    url3 = "postgresql://user:pass@ep-red.neon.tech/neondb?sslmode=require&options=endpoint=ep-123"
    clean3 = clean_postgres_dsn(url3)
    assert "options=endpoint%3Dep-123" in clean3

    # 4. Neon auto sslmode
    url4 = "postgresql://user:pass@ep-red.neon.tech/neondb"
    clean4 = clean_postgres_dsn(url4)
    assert clean4.endswith("?sslmode=require")

    # 5. Non-postgres / empty
    assert clean_postgres_dsn("") == ""
    assert clean_postgres_dsn("sqlite:///:memory:") == "sqlite:///:memory:"

    # 6. Multi-variable pasted string (accidentally copied .env block)
    url5 = "postgresql://user:pass@ep-red.neon.tech/neondb?sslmode=require MASTER_VAULT_KEY=my_vault_key FOO_BAR_TEST=123"
    clean5 = clean_postgres_dsn(url5)
    assert clean5 == "postgresql+psycopg2://user:pass@ep-red.neon.tech/neondb?sslmode=require"
    assert os.getenv("FOO_BAR_TEST") == "123"


def test_ledger_anchor_endpoints(client):
    """POST & GET /api/screen/ledger/anchor and cross-verification in verify endpoint."""
    import hashlib
    SessionLocal = main.SessionLocal
    db = SessionLocal()
    try:
        created_at = now_utc()
        block_payload = f"GENESIS:1122334455667788:CLEAR:10:{created_at}:officer@ssb.gov.in"
        valid_hash = hashlib.sha256(block_payload.encode("utf-8")).hexdigest()

        rep = ScreeningReport(
            id="test_anchor_rep_01",
            file_hash="1122334455667788",
            filename="passport_anchor.jpg",
            doc_type="passport",
            checkpoint="Panitanki ICP",
            verdict="CLEAR",
            risk_score=10,
            confidence=0.98,
            extracted_fields='{"passport":"A1234567"}',
            signals='["Valid"]',
            modules='{"validation":"PASS","tampering":"PASS","face":"PASS"}',
            previous_hash="GENESIS",
            ledger_hash=valid_hash,
            screener="officer@ssb.gov.in",
            created_at=created_at,
        )
        db.add(rep)
        db.commit()
    finally:
        db.close()

    # 1. POST /api/screen/ledger/anchor
    anchor_resp = client.post("/api/screen/ledger/anchor")
    assert anchor_resp.status_code == 200
    adata = anchor_resp.json()
    assert adata["ok"] is True
    assert adata["status"] == "ANCHORED"
    assert adata["head_hash"] == valid_hash

    assert adata["total_blocks"] >= 1
    assert "signature" in adata
    assert "public_url" in adata

    # 2. GET /api/screen/ledger/anchor
    get_resp = client.get("/api/screen/ledger/anchor")
    assert get_resp.status_code == 200
    gdata = get_resp.json()
    assert gdata["anchored"] is True
    assert gdata["in_sync"] is True
    assert gdata["anchor_head_hash"] == adata["head_hash"]

    # 3. GET /api/screen/ledger/verify cross-reference
    vresp = client.get("/api/screen/ledger/verify")
    assert vresp.status_code == 200
    vdata = vresp.json()
    assert vdata["valid"] is True
    assert "anchor" in vdata
    assert vdata["anchor"]["anchored"] is True
    assert vdata["anchor"]["in_sync"] is True


def test_manifest_signature():
    """_compute_anchor_manifest produces verified HMAC-SHA256 non-repudiation signature."""
    import hmac
    import hashlib
    from main import _compute_anchor_manifest, MASTER_VAULT_KEY

    manifest = _compute_anchor_manifest(
        head_hash="deadbeef1234",
        total_blocks=42,
        screener="commander@ssb.gov.in",
        checkpoint="Raxaul ICP"
    )
    assert manifest["protocol"] == "SIH26188-LEDGER-ANCHOR-v1"
    assert manifest["head_hash"] == "deadbeef1234"
    assert manifest["total_blocks"] == 42

    # Recompute expected signature
    ts = manifest["anchored_at"]
    payload = f"deadbeef1234:42:{ts}:commander@ssb.gov.in:Raxaul ICP"
    expected = hmac.new(MASTER_VAULT_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    assert manifest["signature"] == expected




