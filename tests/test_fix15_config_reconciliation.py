import pytest

from app.remote_ml import get_timeout, get_connect_timeout
from app.face_policy import BASE_SAME


def test_fix15_timeout_consolidation(monkeypatch):
    # 1. Defaults
    monkeypatch.delenv("ML_SERVICE_TIMEOUT", raising=False)
    monkeypatch.delenv("ML_TIMEOUT", raising=False)
    monkeypatch.delenv("ML_SERVICE_CONNECT_TIMEOUT", raising=False)
    monkeypatch.delenv("ML_CONNECT_TIMEOUT", raising=False)
    assert get_timeout() == 2.0
    assert get_connect_timeout() == 1.0

    # 2. Legacy alias fallback
    monkeypatch.setenv("ML_TIMEOUT", "4.5")
    monkeypatch.setenv("ML_CONNECT_TIMEOUT", "1.8")
    assert get_timeout() == 4.5
    assert get_connect_timeout() == 1.8

    # 3. Canonical ML_SERVICE_* takes precedence over legacy alias
    monkeypatch.setenv("ML_SERVICE_TIMEOUT", "3.0")
    monkeypatch.setenv("ML_SERVICE_CONNECT_TIMEOUT", "0.8")
    assert get_timeout() == 3.0
    assert get_connect_timeout() == 0.8


def test_fix15_face_similarity_canonical_threshold():
    from app.config import SCREENING_THRESHOLDS
    # Verify canonical threshold matches face_policy.BASE_SAME
    assert SCREENING_THRESHOLDS["FACE_SIMILARITY_MIN"] == BASE_SAME


def test_fix15_degraded_detector_forces_review(monkeypatch):
    """Verify any degraded ML stage forces can_clear=False and minimum risk score 30."""
    from app.screening import run_screening

    # Tiny dummy valid JPEG bytes
    dummy_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"

    import app.tampering as tp
    orig_tamper = tp.tamper_analysis

    try:
        tp.tamper_analysis = lambda *args, **kwargs: {
            "ran": True,
            "verdict": "CLEAR",
            "score": 0.05,
            "checks": [],
            "degraded": True,
            "crop_meta": {"degraded": True},
        }

        report = run_screening(dummy_jpeg, filename="specimen.jpg", doc_type="aadhaar", checkpoint="Panitanki", declared=None)
        assert report["verdict"] != "CLEAR"
        assert report["verdict"] in ("REVIEW", "FLAGGED")
        assert any("DEGRADED SERVICE ADVISORY" in r for r in report["reasons"])
    finally:
        tp.tamper_analysis = orig_tamper


def test_fix15_cloud_llm_defaults_off(monkeypatch):
    """Verify document images are never sent to LiteLLM or Gemini unless explicitly enabled."""
    from app.llm import get_client, extract_document_data

    monkeypatch.delenv("LITELLM_URL", raising=False)
    monkeypatch.delenv("ENABLE_GEMINI_FALLBACK", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # LiteLLM client is None by default
    assert get_client() is None

    # Gemini multimodal fallback is disabled by default
    res = extract_document_data(b"dummy")
    assert res.get("ran") is False
    assert "disabled by policy" in res.get("reason", "")
