"""Task T1: End-to-end Invariant FS with Face Stage Failure States.

Enforces:
In every degraded, fallback, or error condition of the face biometrics stage:
- model missing
- SHA mismatch
- corrupt model
- ML service timeout
- garbage JSON
- mode 'fallback'
- mode 'unavailable'
The screening outcome is NEVER an automatic CLEAR (verdict != "CLEAR"),
and face_match.mode is truthful (never claimed as 'arcface').
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import pytest
from PIL import Image, ImageDraw

from app.screening import run_screening
from app.face import face_verification
import app.face_match as app_face_match


def _create_synthetic_image_bytes(text: str = "TEST ID") -> bytes:
    img = Image.new("RGB", (400, 300), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(10, 10), (390, 290)], outline=(10, 30, 70), width=3)
    draw.text((25, 30), text, fill=(0, 0, 0))
    # Draw simple synthetic face box
    draw.rectangle([(250, 40), (350, 180)], fill=(200, 180, 160), outline=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture
def synthetic_doc():
    return _create_synthetic_image_bytes("PASSPORT P1234567")


@pytest.fixture
def synthetic_selfie():
    return _create_synthetic_image_bytes("LIVE WEBCAM")


# ---------------------------------------------------------------------------
# Invariant FS: Face Stage Failure State Matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "state_name",
    [
        "model_missing",
        "sha_mismatch",
        "corrupt_model",
        "ml_service_timeout",
        "garbage_json",
        "mode_fallback",
        "mode_unavailable",
    ],
)
def test_invariant_fs_face_states_never_clear(state_name, synthetic_doc, synthetic_selfie, monkeypatch, tmp_path):
    """T1: Screening outcome is NEVER CLEAR across all face failure states, and mode is truthful."""
    # Ensure testing flag is set
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("AUTO_DOWNLOAD_MODELS", "false")

    if state_name == "model_missing":
        # Point to non-existent model path
        fake_path = tmp_path / "non_existent_w600k.onnx"
        monkeypatch.setenv("FACE_EMBED_MODEL", str(fake_path))
        monkeypatch.setenv("ML_SERVICE_URL", "")

    elif state_name == "sha_mismatch":
        # Create a dummy model file with invalid hash
        mismatched_model = tmp_path / "bad_sha_model.onnx"
        mismatched_model.write_bytes(b"dummy onnx content that does not match pinned sha256" * 100)
        monkeypatch.setenv("FACE_EMBED_MODEL", str(mismatched_model))
        monkeypatch.setenv("FACE_MODEL_SHA256", "0000000000000000000000000000000000000000000000000000000000000000")
        monkeypatch.setenv("ML_SERVICE_URL", "")

    elif state_name == "corrupt_model":
        # Create a truncated/corrupted onnx file
        corrupt_model = tmp_path / "corrupt.onnx"
        corrupt_model.write_bytes(b"NOT_A_VALID_ONNX_HEADER_DATA_12345")
        monkeypatch.setenv("FACE_EMBED_MODEL", str(corrupt_model))
        monkeypatch.setenv("ML_SERVICE_URL", "")

    elif state_name == "ml_service_timeout":
        # Mock remote ML call to time out
        import app.remote_ml as rml
        def mock_dispatch_timeout(*args, **kwargs):
            raise TimeoutError("Remote ML service timed out after 30s")
        monkeypatch.setattr(rml, "dispatch_remote_face", mock_dispatch_timeout, raising=False)
        monkeypatch.setenv("ML_SERVICE_URL", "http://test-ml-service:8000")

    elif state_name == "garbage_json":
        # Mock remote ML call returning garbage response
        import app.remote_ml as rml
        def mock_dispatch_garbage(*args, **kwargs):
            return {"corrupt": "data", "status": "unknown_format"}
        monkeypatch.setattr(rml, "dispatch_remote_face", mock_dispatch_garbage, raising=False)
        monkeypatch.setenv("ML_SERVICE_URL", "http://test-ml-service:8000")

    elif state_name == "mode_fallback":
        # Force perceptual hash fallback
        monkeypatch.setenv("FACE_EMBED_MODEL", "")
        monkeypatch.setenv("ML_SERVICE_URL", "")

    elif state_name == "mode_unavailable":
        # Mock face comparison as completely unavailable
        def mock_unavailable(*args, **kwargs):
            return {
                "score": 0,
                "match": None,
                "method": "unavailable",
                "mode": "unavailable",
                "decision": "INCONCLUSIVE",
                "detail": "Face verification unavailable",
                "face_match": {
                    "mode": "unavailable",
                    "loaded": False,
                    "model_sha256_prefix": None,
                    "auto_download": False,
                },
            }
        monkeypatch.setattr(app_face_match, "compare_faces", mock_unavailable)

    # Execute end-to-end screening
    result = run_screening(
        data=synthetic_doc,
        filename="test_passport.jpg",
        doc_type="passport",
        checkpoint="ICP-Raxaul",
        declared={
            "document_type": "passport",
            "passport_number": "P1234567",
            "nationality": "IND",
        },
        live_frame=synthetic_selfie,
    )

    # 1. Invariant FS: Screening verdict is NEVER CLEAR
    assert result["verdict"] != "CLEAR", (
        f"State '{state_name}' produced verdict '{result['verdict']}', violating Invariant FS"
    )
    assert result["screening_verdict"] in ("REVIEW", "REJECT_LIKELY", "REJECT"), (
        f"State '{state_name}' produced unexpected screening_verdict '{result['screening_verdict']}'"
    )

    # 2. Face module verdict is never PASS
    face_module = result.get("modules", {}).get("face", {})
    assert face_module.get("verdict") != "PASS", (
        f"State '{state_name}' produced face module verdict PASS"
    )

    # 3. Mode truthfulness: Never claim 'arcface' when model failed or unavailable
    face_match_info = result.get("face_match") or {}
    mode = face_match_info.get("mode") or face_module.get("mode")
    assert mode != "arcface", (
        f"State '{state_name}' falsely claimed mode 'arcface'"
    )
    assert mode in ("unavailable", "fallback", "phash-dhash", "timeout", "error", None), (
        f"State '{state_name}' returned untruthful mode '{mode}'"
    )


def test_invariant_fs_direct_face_verification_fallback_contract():
    """T1: face_verification directly returns REVIEW and match=None when not arcface."""
    res = face_verification(
        document_bytes=_create_synthetic_image_bytes("DOC"),
        live_frame=_create_synthetic_image_bytes("LIVE"),
    )
    # When default running without onnx arcface model:
    assert res["verdict"] in ("REVIEW", "UNVERIFIED")
    assert res.get("match") is not True
    if res.get("mode") != "arcface":
        assert res.get("verdict") == "REVIEW"
        assert res.get("decision") == "INCONCLUSIVE"
        assert res.get("match") is None
