"""Tests for upload limits, magic-byte checking, streaming hard caps, and decompression bomb protection (F-03).

Verifies:
  1. Content-Length and streaming hard cap (413).
  2. Server-side PDF max_pages cap (413).
  3. Magic-byte type verification (400 / 415).
  4. Explicit lower Image.MAX_IMAGE_PIXELS (50,000,000).
  5. 1x60000 PNG, huge sparse image decompression bomb, zero bytes,
     JPEG-header+text polyglot, corrupt PDF, over-cap upload.
"""

from __future__ import annotations

import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import main
from main import Base, SignerIdentity, app as main_app, validate_upload_bytes, make_session_token, now_utc
from ml_service.main import app as ml_app


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("SUPER_ADMINS", "officer@ssb.gov.in")
    test_engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    monkeypatch.setattr(main, "engine", test_engine)
    import sys
    if "main" in sys.modules:
        monkeypatch.setattr(sys.modules["main"], "SessionLocal", TestSession)
        monkeypatch.setattr(sys.modules["main"], "engine", test_engine)

    db = TestSession()
    try:
        db.add(SignerIdentity(
            email="officer@ssb.gov.in", name="Officer", institution="SSB",
            designation="Inspector", registered_at=now_utc(),
        ))
        db.commit()
    finally:
        db.close()

    client = TestClient(main_app)
    token = make_session_token("officer@ssb.gov.in")
    client.cookies.set("nischay_session", token)
    return client


@pytest.fixture
def ml_client(monkeypatch):
    monkeypatch.setenv("ML_ALLOW_NO_AUTH", "true")
    return TestClient(ml_app)


def test_zero_bytes_rejected(auth_client, ml_client):
    """Empty payload (0 bytes) is rejected with 400 Bad Request."""
    res_app = auth_client.post("/api/screen", files={"file": ("empty.jpg", b"", "image/jpeg")})
    assert res_app.status_code == 400

    res_ml = ml_client.post("/detect/card", files={"file": ("empty.jpg", b"", "image/jpeg")})
    assert res_ml.status_code == 400


def test_over_cap_upload_rejected(auth_client, ml_client):
    """Upload exceeding byte limit is rejected with 413."""
    fake_huge = b"0" * (9 * 1024 * 1024)  # 9 MB > 8 MB app limit
    res_app = auth_client.post("/api/screen", files={"file": ("huge.jpg", fake_huge, "image/jpeg")})
    assert res_app.status_code == 413

    fake_huge_ml = b"0" * (16 * 1024 * 1024)  # 16 MB > 15 MB ml limit
    res_ml = ml_client.post("/detect/card", files={"file": ("huge.jpg", fake_huge_ml, "image/jpeg")})
    assert res_ml.status_code in (400, 413)


def test_corrupt_pdf_rejected(auth_client, ml_client):
    """Corrupt PDF bytes starting with %PDF but having invalid structure trigger 400."""
    corrupt_pdf = b"%PDF-1.4\nCorrupted binary garbage not a valid pdf cross-reference table."
    res_app = auth_client.post("/api/screen", files={"file": ("corrupt.pdf", corrupt_pdf, "application/pdf")})
    assert res_app.status_code == 400

    res_ml = ml_client.post("/api/ml/media/process_pdf", files={"file": ("corrupt.pdf", corrupt_pdf, "application/pdf")})
    assert res_ml.status_code == 400


def test_pdf_over_page_cap_rejected(auth_client, ml_client):
    """PDF exceeding server-side page cap (10 pages) is rejected with 413."""
    writer = PdfWriter()
    for _ in range(15):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_15_pages = buf.getvalue()

    res_app = auth_client.post("/api/screen", files={"file": ("multi.pdf", pdf_15_pages, "application/pdf")})
    assert res_app.status_code == 413
    assert "page limit" in res_app.json().get("detail", "").lower()

    res_ml = ml_client.post("/api/ml/media/process_pdf", files={"file": ("multi.pdf", pdf_15_pages, "application/pdf")})
    assert res_ml.status_code == 413
    assert "limit of 10 pages" in res_ml.json().get("detail", "").lower()


def test_polyglot_jpeg_header_plus_text_rejected(auth_client, ml_client):
    """JPEG-header followed by arbitrary text/HTML polyglot is rejected as corrupt/invalid."""
    polyglot = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00<script>alert('xss')</script>POLYGLOT_ATTACK"
    res_app = auth_client.post("/api/screen", files={"file": ("polyglot.jpg", polyglot, "image/jpeg")})
    assert res_app.status_code == 400

    res_ml = ml_client.post("/detect/card", files={"file": ("polyglot.jpg", polyglot, "image/jpeg")})
    assert res_ml.status_code == 400


def test_decompression_bomb_sparse_image_rejected(auth_client, ml_client):
    """Huge sparse image exceeding 50,000,000 pixels is rejected with 413 (decompression bomb protection)."""
    # 10,000 x 6,000 = 60,000,000 pixels (> 50,000,000 limit)
    # Mode '1' compresses to a very small byte size
    bomb = Image.new("1", (10000, 6000), color=0)
    buf = io.BytesIO()
    bomb.save(buf, format="PNG")
    bomb_bytes = buf.getvalue()
    assert len(bomb_bytes) < 100_000  # Small compressed payload

    res_app = auth_client.post("/api/screen", files={"file": ("bomb.png", bomb_bytes, "image/png")})
    assert res_app.status_code == 413
    assert "decompression bomb" in res_app.json().get("detail", "").lower() or "exceed" in res_app.json().get("detail", "").lower()

    res_ml = ml_client.post("/detect/card", files={"file": ("bomb.png", bomb_bytes, "image/png")})
    assert res_ml.status_code == 413
    assert "decompression bomb" in res_ml.json().get("detail", "").lower()


def test_1x60000_png_extreme_aspect_ratio():
    """1x60000 PNG is structurally handled without crash or unbounded allocation."""
    img_1x60k = Image.new("1", (1, 60000), color=0)
    buf = io.BytesIO()
    img_1x60k.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    # 1x60,000 = 60,000 pixels (< 50,000,000), valid PNG structure
    ext = validate_upload_bytes(img_bytes, "tall.png")
    assert ext == "png"
