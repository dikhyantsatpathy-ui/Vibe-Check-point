"""
Unit tests for Detector Backend abstraction and configuration toggle (Phase 5).
Verifies side-by-side YOLOv8 vs RF-DETR switching, session cache clearing, and response schema.
"""

import io
import os
import sys
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from yolo_roi import (
    get_detector_backend,
    _default_model_path,
    clear_session_cache,
    extract_roi_boxes,
)


def test_detector_backend_default(monkeypatch):
    """Verify detector backend defaults to 'yolov8' when unset."""
    monkeypatch.delenv("DETECTOR_BACKEND", raising=False)
    assert get_detector_backend() == "yolov8"


def test_detector_backend_rf_detr_toggle(monkeypatch):
    """Verify switching DETECTOR_BACKEND to 'rf_detr' succeeds, but RT-DETR raises ValueError."""
    for alias in ("rf_detr", "rf-detr"):
        monkeypatch.setenv("DETECTOR_BACKEND", alias)
        assert get_detector_backend() == "rf_detr"

    for disallowed in ("rtdetr", "rt-detr", "RT-DETR"):
        monkeypatch.setenv("DETECTOR_BACKEND", disallowed)
        with pytest.raises(ValueError, match="RT-DETR and RF-DETR are distinct models"):
            get_detector_backend()


def test_detector_backend_model_path_resolution(monkeypatch, tmp_path):
    """Verify model path resolution fails loud when rf_detr weights are missing (no silent fallback)."""
    # 1. No silent fallback to YOLO when rf_detr weights do not exist
    monkeypatch.setenv("DETECTOR_BACKEND", "rf_detr")
    monkeypatch.delenv("RF_DETR_ONNX_PATH", raising=False)
    monkeypatch.setattr("yolo_roi._MODEL_DIR", str(tmp_path))
    path = _default_model_path()
    assert path == "", "Must return empty string and fail loud rather than loading YOLO card.onnx"

    # 2. Specific mounted rf_detr weights are loaded properly
    dummy_rf = tmp_path / "custom_rf_detr.onnx"
    dummy_rf.write_bytes(b"dummy")
    monkeypatch.setenv("RF_DETR_ONNX_PATH", str(dummy_rf))
    assert _default_model_path() == str(dummy_rf)


def test_bakeoff_aborts_without_rf_detr_weights(monkeypatch, tmp_path):
    """Verify bakeoff function strictly fails if RF-DETR weights are not mounted."""
    from eval.evaluate import run_detector_bakeoff
    monkeypatch.setenv("RF_DETR_ONNX_PATH", str(tmp_path / "nonexistent.onnx"))
    with pytest.raises(FileNotFoundError, match="RF-DETR weights not found"):
        run_detector_bakeoff()


def test_clear_session_cache_allows_instant_backend_switching(monkeypatch):
    """Verify clear_session_cache resets session state cleanly."""
    monkeypatch.setenv("DETECTOR_BACKEND", "yolov8")
    clear_session_cache()

    monkeypatch.setenv("DETECTOR_BACKEND", "rf_detr")
    clear_session_cache()
    assert get_detector_backend() == "rf_detr"


def test_boxes_carry_backend_tagging(monkeypatch):
    """Verify detected boxes carry backend identifier without breaking schema."""
    import io
    from PIL import Image

    img = Image.new("RGB", (640, 640), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    # Disable remote ML so it tests local pipeline
    monkeypatch.delenv("ML_SERVICE_URL", raising=False)
    monkeypatch.setenv("DETECTOR_BACKEND", "yolov8")
    clear_session_cache()

    boxes = extract_roi_boxes(raw)
    assert isinstance(boxes, list)
    for b in boxes:
        # Check required schema keys
        assert "label" in b
        assert "x" in b and "y" in b and "w" in b and "h" in b
        assert "source" in b
        # Model predictions include backend tag
        if b.get("source") == "model":
            assert b.get("backend") == "yolov8"


def test_per_stage_backend_switches(monkeypatch):
    """Verify CARD_DETECTOR_BACKEND and FIELD_DETECTOR_BACKEND defaults and independent overrides."""
    from yolo_roi import get_card_detector_backend, get_field_detector_backend

    # 1. Defaults inherit from DETECTOR_BACKEND
    monkeypatch.setenv("DETECTOR_BACKEND", "yolov8")
    monkeypatch.delenv("CARD_DETECTOR_BACKEND", raising=False)
    monkeypatch.delenv("FIELD_DETECTOR_BACKEND", raising=False)
    assert get_card_detector_backend() == "yolov8"
    assert get_field_detector_backend() == "yolov8"

    # 2. Independent overrides
    monkeypatch.setenv("CARD_DETECTOR_BACKEND", "rf_detr")
    monkeypatch.setenv("FIELD_DETECTOR_BACKEND", "yolov8")
    assert get_card_detector_backend() == "rf_detr"
    assert get_field_detector_backend() == "yolov8"

    # 3. Invalid options fail loudly
    monkeypatch.setenv("CARD_DETECTOR_BACKEND", "invalid_backend")
    with pytest.raises(ValueError, match="Unsupported CARD_DETECTOR_BACKEND"):
        get_card_detector_backend()

    monkeypatch.setenv("FIELD_DETECTOR_BACKEND", "rtdetr")
    with pytest.raises(ValueError, match="RT-DETR and RF-DETR are distinct models"):
        get_field_detector_backend()


def test_missing_weights_fails_loudly(monkeypatch, tmp_path):
    """Verify missing weights under rf_detr fail loudly and never silently fall back."""
    from yolo_roi import extract_aadhaar_fields

    dummy_img = Image.new("RGB", (640, 640), color=(128, 128, 128))
    buf = io.BytesIO()
    dummy_img.save(buf, format="JPEG")
    raw = buf.getvalue()

    monkeypatch.delenv("ML_SERVICE_URL", raising=False)

    # Missing card weights
    monkeypatch.setenv("CARD_DETECTOR_BACKEND", "rf_detr")
    monkeypatch.setattr("yolo_roi._MODEL_DIR", str(tmp_path))
    monkeypatch.delenv("RF_DETR_ONNX_PATH", raising=False)
    clear_session_cache()
    with pytest.raises(FileNotFoundError, match="CARD_DETECTOR_BACKEND='rf_detr' configured but"):
        extract_roi_boxes(raw)

    # Missing field weights
    monkeypatch.setenv("CARD_DETECTOR_BACKEND", "yolov8")
    monkeypatch.setenv("FIELD_DETECTOR_BACKEND", "rf_detr")
    monkeypatch.delenv("RF_DETR_FIELDS_ONNX_PATH", raising=False)
    clear_session_cache()
    with pytest.raises(FileNotFoundError, match="FIELD_DETECTOR_BACKEND='rf_detr' configured but"):
        extract_aadhaar_fields(raw)


def test_sha256_pin_verification_tamper_fails(tmp_path):
    """Verify loader checks ONNX SHA-256 against sidecar and rejects tampered weights (fail-closed)."""
    import hashlib
    import json
    from yolo_roi import _load_model_metadata

    model_file = tmp_path / "test_model.onnx"
    model_file.write_bytes(b"original neural model weights content")
    correct_sha = hashlib.sha256(b"original neural model weights content").hexdigest()

    sidecar = tmp_path / "test_model.meta.json"
    sidecar.write_text(json.dumps({
        "classes": ["Card"],
        "sha256": correct_sha,
    }), encoding="utf-8")

    # 1. Valid metadata passes
    loaded = _load_model_metadata(str(model_file), expected_num_classes=1)
    assert loaded["sha256"] == correct_sha

    # 2. Tampered model weights fail loudly
    model_file.write_bytes(b"tampered adversarial content")
    with pytest.raises(ValueError, match="Supply-chain SHA-256 check failed"):
        _load_model_metadata(str(model_file), expected_num_classes=1)

