"""Regression: the upload filename must never trigger the forgery watermark check.

The fake/synthetic watermark scan runs over extracted document text and the
holder name. It previously also included `filename`, which is caller-controlled
metadata: uploading a genuine document as `sample.jpg` hard-flagged it as a
synthetic forgery (risk 95, FLAGGED). The scan must still fire on the actual
document text.
"""

import io
import os
import sys

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

import app.extraction as app_extraction  # noqa: E402
import app.face as app_face  # noqa: E402
import app.tampering as app_tampering  # noqa: E402
import extraction as top_extraction  # noqa: E402
import face as top_face  # noqa: E402
import main  # noqa: E402
import screening  # noqa: E402
import tampering as top_tampering  # noqa: E402
from main import Base  # noqa: E402


def _jpeg() -> bytes:
    img = Image.new("RGB", (320, 200), color=(240, 240, 245))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture
def isolated_pipeline(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    monkeypatch.setattr(main, "_db_initialized", True)

    def fake_extract(text: str):
        def _inner(data, filename="", doc_type="", declared=None):
            return {
                "fields": {"pan": "ABCDP2234A"},
                "text": text,
                "medium": "image",
                "ocr": {"ran": True},
                "mrz": None,
                "qr": None,
                "aadhaar_photo": None,
            }
        return _inner

    def fake_tamper(*args, **kwargs):
        return {"ran": True, "verdict": "PASS", "score": 0.05, "checks": [],
                "ela": {"status": "ok"}, "degraded": False}

    def fake_face(*args, **kwargs):
        return {"ran": False, "verdict": "UNVERIFIED", "match": None,
                "score": 0.0, "method": "test", "signals": []}

    def fake_detect(*args, **kwargs):
        return {"ran": False, "ai_suspected": False, "ai_score": 0,
                "model": None, "provider": None, "explanation": "test",
                "latency_ms": 0, "document_aware": None}

    def install(text: str):
        extract = fake_extract(text)
        monkeypatch.setattr(app_extraction, "extract_document", extract)
        monkeypatch.setattr(top_extraction, "extract_document", extract)
        monkeypatch.setattr(app_tampering, "tamper_analysis", fake_tamper)
        monkeypatch.setattr(top_tampering, "tamper_analysis", fake_tamper)
        monkeypatch.setattr(app_face, "face_verification", fake_face)
        monkeypatch.setattr(top_face, "face_verification", fake_face)
        monkeypatch.setattr(main, "detect_image", fake_detect)
        monkeypatch.setattr(main, "looks_like_scanned_document", lambda _data: True)

    return install


def test_filename_sample_does_not_flag_clean_document(isolated_pipeline):
    isolated_pipeline("INCOME TAX DEPARTMENT PERMANENT ACCOUNT NUMBER")
    res = screening.run_screening(
        _jpeg(), "sample.jpg", "pan", "Panitanki", {}, screener="officer@ssb.gov.in"
    )
    reasons = " ".join(res.get("reasons") or [])
    assert "SYNTHETIC WATERMARK" not in reasons
    assert res.get("verdict") != "FLAGGED"


def test_document_text_sample_still_flags(isolated_pipeline):
    isolated_pipeline("INCOME TAX DEPARTMENT SAMPLE CARD")
    res = screening.run_screening(
        _jpeg(), "document.jpg", "pan", "Panitanki", {}, screener="officer@ssb.gov.in"
    )
    reasons = " ".join(res.get("reasons") or [])
    assert "SYNTHETIC WATERMARK" in reasons
    assert res.get("verdict") == "FLAGGED"
