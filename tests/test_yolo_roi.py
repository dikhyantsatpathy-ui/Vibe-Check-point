"""
Unit tests for YOLO ROI detection, letterboxing, per-class NMS, EXIF handling,
circuit breaker, and ML service authentication hotfixes (Phase 1).
"""

import io
import os
import sys
from unittest.mock import MagicMock
import numpy as np
import pytest
from PIL import Image

# Ensure app and ml_service are accessible
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

from yolo_roi import (
    letterbox,
    scale_boxes_to_original,
    nms_numpy,
    _run_yolo_onnx,
    isolate_document_card,
)
from remote_ml import (
    is_remote_available,
    mark_remote_failed,
    mark_remote_success,
    get_auth_headers,
)


def test_letterbox_and_unscale_roundtrip():
    """Verify that letterbox padding and un-padding projects coordinates exactly
    back to original pixel space regardless of aspect ratio."""
    test_dimensions = [
        (640, 640),    # 1:1 square
        (1011, 638),   # ~1.58:1 typical ID card (landscape)
        (638, 1011),   # 1:1.58 ID card (portrait)
        (1920, 1080),  # 16:9 HD photo
        (800, 600),    # 4:3 standard camera
    ]

    for orig_w, orig_h in test_dimensions:
        rgb_arr = np.full((orig_h, orig_w, 3), 200, dtype=np.uint8)
        canvas, scale, padding, orig_dim = letterbox(rgb_arr, target_shape=(640, 640))

        assert canvas.shape == (640, 640, 3), f"Letterbox failed to output 640x640 for {(orig_w, orig_h)}"

        # Synthesize a known box on the original image: center rectangle [w/4, h/4, 3w/4, 3h/4]
        gt_orig_box = np.array([orig_w * 0.25, orig_h * 0.25, orig_w * 0.75, orig_h * 0.75], dtype=np.float32)

        dw, dh = padding
        # Project gt_orig_box into letterbox coordinate space
        lb_box = np.array([
            gt_orig_box[0] * scale + dw,
            gt_orig_box[1] * scale + dh,
            gt_orig_box[2] * scale + dw,
            gt_orig_box[3] * scale + dh,
        ], dtype=np.float32)

        # Now test inverse projection using scale_boxes_to_original
        boxes_array = np.array([lb_box], dtype=np.float32)
        unscaled = scale_boxes_to_original(boxes_array, scale, padding, orig_dim)

        # Allow at most 0.5px rounding variance
        np.testing.assert_allclose(
            unscaled[0],
            gt_orig_box,
            atol=0.5,
            err_msg=f"Coordinate roundtrip failed for input resolution {(orig_w, orig_h)}"
        )


def test_vectorized_nms():
    """Verify that vectorized NumPy NMS suppresses duplicate overlapping boxes
    while preserving non-overlapping boxes."""
    # Box 0: score 0.95
    # Box 1: almost identical to Box 0 (IoU > 0.9), score 0.60 -> should be suppressed
    # Box 2: distinct region, score 0.80 -> should be kept
    boxes = np.array([
        [100, 100, 300, 300],
        [105, 105, 305, 305],
        [400, 400, 600, 600],
    ], dtype=np.float32)

    scores = np.array([0.95, 0.60, 0.80], dtype=np.float32)
    kept = nms_numpy(boxes, scores, iou_threshold=0.45)

    assert 0 in kept
    assert 2 in kept
    assert 1 not in kept


def test_yolo_onnx_layout_detection():
    """Verify that _run_yolo_onnx correctly handles standard YOLOv8 layout [1, 4+nc, G]
    and end-to-end NMS-free layout [1, 300, 6]."""
    classes = ["Aadhaar_No", "DOB", "Gender", "Name", "Photo"]
    rgb = np.zeros((600, 1000, 3), dtype=np.uint8)

    # 1. Standard YOLOv8 layout: [1, 4 + 5, 8400]
    preds_yolov8 = np.zeros((1, 4 + len(classes), 8400), dtype=np.float32)
    # Put a detection at anchor 100: cx=320, cy=320, w=200, h=50, class 0 (Aadhaar_No) conf 0.90
    preds_yolov8[0, 0, 100] = 320.0
    preds_yolov8[0, 1, 100] = 320.0
    preds_yolov8[0, 2, 100] = 200.0
    preds_yolov8[0, 3, 100] = 50.0
    preds_yolov8[0, 4, 100] = 0.90

    mock_sess_v8 = MagicMock()
    mock_input = MagicMock()
    mock_input.shape = [1, 3, 640, 640]
    mock_input.name = "images"
    mock_output = MagicMock()
    mock_output.name = "output0"
    mock_sess_v8.get_inputs.return_value = [mock_input]
    mock_sess_v8.get_outputs.return_value = [mock_output]
    mock_sess_v8.run.return_value = [preds_yolov8]

    boxes_v8 = _run_yolo_onnx(rgb, mock_sess_v8, class_names=classes)
    assert len(boxes_v8) == 1
    assert boxes_v8[0]["label"] == "Aadhaar_No"
    assert boxes_v8[0]["confidence"] == pytest.approx(0.90, abs=0.01)

    # 2. End-to-end layout: [1, 300, 6]
    preds_e2e = np.zeros((1, 300, 6), dtype=np.float32)
    preds_e2e[0, 0] = [100.0, 150.0, 350.0, 400.0, 0.88, 4.0]  # Photo
    mock_sess_e2e = MagicMock()
    mock_sess_e2e.get_inputs.return_value = [mock_input]
    mock_sess_e2e.get_outputs.return_value = [mock_output]
    mock_sess_e2e.run.return_value = [preds_e2e]

    boxes_e2e = _run_yolo_onnx(rgb, mock_sess_e2e, class_names=classes)
    assert len(boxes_e2e) == 1
    assert boxes_e2e[0]["label"] == "Photo"
    assert boxes_e2e[0]["confidence"] == pytest.approx(0.88, abs=0.01)


def test_circuit_breaker_consecutive_failures(monkeypatch):
    """Verify that circuit breaker only trips after N consecutive failures."""
    import remote_ml
    monkeypatch.setenv("ML_SERVICE_URL", "http://test-ml-service:8000")
    remote_ml._CIRCUIT_BROKEN_UNTIL = 0.0
    remote_ml._CONSECUTIVE_FAILURES = 0

    assert is_remote_available() is True

    # 1st failure: should NOT trip
    mark_remote_failed()
    assert is_remote_available() is True
    assert remote_ml._CONSECUTIVE_FAILURES == 1

    # Success resets failure counter
    mark_remote_success(0.1)
    assert remote_ml._CONSECUTIVE_FAILURES == 0
    assert is_remote_available() is True

    # 3 consecutive failures: should trip
    mark_remote_failed()
    mark_remote_failed()
    assert is_remote_available() is True
    mark_remote_failed()
    assert is_remote_available() is False  # Tripped!


def test_auth_headers_generation(monkeypatch):
    """Verify auth headers generation when ML_SECRET_KEY is configured vs omitted."""
    monkeypatch.delenv("ML_SECRET_KEY", raising=False)
    headers = get_auth_headers()
    assert "X-ML-Secret-Key" not in headers

    monkeypatch.setenv("ML_SECRET_KEY", "test-secret-key-123")
    headers_secured = get_auth_headers()
    assert headers_secured.get("X-ML-Secret-Key") == "test-secret-key-123"


def test_heuristic_fallback_does_not_fabricate_confidence():
    """Verify finding A2: heuristic card detection does not invent 0.85 confidence,
    and returns source='heuristic', is_fallback=True, confidence=None."""
    img = Image.new("RGB", (800, 600), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    crop_bytes, meta = isolate_document_card(raw_bytes)
    assert meta is not None
    assert meta.get("cropped") is True
    assert meta.get("confidence") is None
    assert meta.get("is_fallback") is True
    assert meta.get("source") == "heuristic"


def test_degraded_mode_prevents_clear():
    """Verify finding A3: degraded heuristic detection prevents autonomous CLEAR in screening."""
    from screening import _grade
    verdict = _grade(score=15, hard_flag=False, can_clear=False)
    assert verdict == "REVIEW", f"Expected REVIEW in degraded mode, got {verdict}"

    verdict_clean = _grade(score=15, hard_flag=False, can_clear=True)
    assert verdict_clean == "CLEAR"


def test_yolo_roi_dual_implementation_drift():
    """Verify defect D8: ensure core detection algorithms in app/yolo_roi.py
    and ml_service/yolo_roi.py remain strictly aligned without behavioral drift."""
    import importlib.util

    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "yolo_roi.py")
    ml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml_service", "yolo_roi.py")

    spec_app = importlib.util.spec_from_file_location("app_yolo_roi_drift", app_path)
    mod_app = importlib.util.module_from_spec(spec_app)
    spec_app.loader.exec_module(mod_app)

    spec_ml = importlib.util.spec_from_file_location("ml_yolo_roi_drift", ml_path)
    mod_ml = importlib.util.module_from_spec(spec_ml)
    spec_ml.loader.exec_module(mod_ml)

    # 1. Verify default thresholds match
    assert mod_app.DEFAULT_CONF_THRESHOLDS == mod_ml.DEFAULT_CONF_THRESHOLDS

    # 2. Verify letterbox outputs match exactly
    dummy_rgb = np.arange(100 * 150 * 3, dtype=np.uint8).reshape((100, 150, 3))
    lb_app, s_app, p_app, d_app = mod_app.letterbox(dummy_rgb, (640, 640))
    lb_ml, s_ml, p_ml, d_ml = mod_ml.letterbox(dummy_rgb, (640, 640))

    np.testing.assert_array_equal(lb_app, lb_ml)
    assert s_app == s_ml
    assert p_app == p_ml
    assert d_app == d_ml

    # 3. Verify NMS outputs match exactly
    boxes = np.array([
        [10, 10, 50, 50],
        [12, 12, 52, 52],
        [100, 100, 180, 180],
    ], dtype=np.float32)
    scores = np.array([0.9, 0.85, 0.7], dtype=np.float32)
    assert mod_app.nms_numpy(boxes, scores) == mod_ml.nms_numpy(boxes, scores)

    # 4. Verify postprocessing outputs match exactly
    raw_preds = np.zeros((1, 5, 10), dtype=np.float32)
    raw_preds[0, :4, 0] = [320, 320, 200, 200]
    raw_preds[0, 4, 0] = 0.95
    boxes_app = mod_app._postprocess_yolo_predictions(raw_preds, 1.0, (0.0, 0.0), (640, 640))
    boxes_ml = mod_ml._postprocess_yolo_predictions(raw_preds, 1.0, (0.0, 0.0), (640, 640))
    assert boxes_app == boxes_ml
