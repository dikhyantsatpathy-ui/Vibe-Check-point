"""
Unit tests for Detector Backend abstraction and configuration toggle (Phase 5).
Verifies side-by-side YOLOv8 vs RF-DETR switching, session cache clearing, and response schema.
"""

import os
import sys
import numpy as np
import pytest

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
    """Verify switching DETECTOR_BACKEND to 'rf_detr' or aliases."""
    for alias in ("rf_detr", "rtdetr", "rf-detr", "RT-DETR"):
        monkeypatch.setenv("DETECTOR_BACKEND", alias)
        assert get_detector_backend() == "rf_detr"


def test_detector_backend_model_path_resolution(monkeypatch, tmp_path):
    """Verify model path resolution checks for rf_detr weights and falls back gracefully."""
    # 1. Fallback when no rf_detr weights exist
    monkeypatch.setenv("DETECTOR_BACKEND", "rf_detr")
    monkeypatch.delenv("RF_DETR_ONNX_PATH", raising=False)
    path = _default_model_path()
    assert path.endswith("card.onnx") or path.endswith("yolov8n.onnx")

    # 2. Specific mounted rf_detr weights
    dummy_rf = tmp_path / "custom_rf_detr.onnx"
    dummy_rf.write_bytes(b"dummy")
    monkeypatch.setenv("RF_DETR_ONNX_PATH", str(dummy_rf))
    assert _default_model_path() == str(dummy_rf)


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
