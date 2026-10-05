"""Unit tests for RF-DETR preprocessing, metadata validation, and decode postprocessing.

Uses synthetic tensors to verify coordinate unscaling, clipping, confidence thresholding,
and metadata validation before weights are trained.
"""

import json
from pathlib import Path
import numpy as np
import pytest

from app.yolo_roi import (
    _load_model_metadata,
    _postprocess_rfdetr_predictions,
    preprocess_rfdetr,
)


def test_preprocess_rfdetr_shapes_and_normalization():
    """Verify RF-DETR plain resize (no letterbox) and ImageNet mean/std normalization."""
    # Create synthetic RGB image (1200 x 800)
    rgb = np.zeros((800, 1200, 3), dtype=np.uint8)
    rgb[:, :, 0] = 120  # R
    rgb[:, :, 1] = 150  # G
    rgb[:, :, 2] = 180  # B

    tensor, (orig_w, orig_h) = preprocess_rfdetr(rgb, target_shape=(640, 640))
    assert tensor.shape == (1, 3, 640, 640)
    assert orig_w == 1200
    assert orig_h == 800
    assert tensor.dtype == np.float32

    # Check that normalization matches (pixel/255.0 - mean) / std
    expected_r = ((120 / 255.0) - 0.485) / 0.229
    assert pytest.approx(tensor[0, 0, 10, 10], abs=1e-3) == expected_r


def test_postprocess_rfdetr_synthetic_boxes():
    """Verify conversion of normalized cx,cy,w,h to original image pixels with clipping."""
    orig_dim = (1000, 500)  # w=1000, h=500

    # 3 query boxes:
    # 0: center box cx=0.5, cy=0.5, w=0.4, h=0.6 (valid, high score)
    # 1: off-screen box cx=1.2, cy=1.2, w=0.4, h=0.4 (clipped/dropped)
    # 2: zero-area box w=0, h=0
    boxes = np.array([
        [0.5, 0.5, 0.4, 0.6],
        [1.1, 1.1, 0.2, 0.2],
        [0.2, 0.2, 0.0, 0.0],
    ], dtype=np.float32)

    # Logits: high logit for box 0 (+5.0 -> prob ~0.993), low logit for box 1 (-5.0), high for box 2
    logits = np.array([
        [5.0],
        [-5.0],
        [5.0],
    ], dtype=np.float32)

    res = _postprocess_rfdetr_predictions(
        boxes=boxes,
        logits=logits,
        orig_dim=orig_dim,
        class_names=["Card"],
        conf_threshold=0.25,
        max_boxes=5,
    )

    assert len(res) == 1
    top = res[0]
    assert top["label"] == "Card"
    assert top["class_name"] == "Card"
    assert top["confidence"] > 0.95
    assert top["backend"] == "rf_detr"
    assert top["source"] == "model"

    # Box 0: cx=500, cy=250, w=400, h=300 -> x1=300, y1=100, bw=400, bh=300
    # Normalized: x=0.3, y=0.2, w=0.4, h=0.6
    assert pytest.approx(top["x"], abs=1e-3) == 0.3
    assert pytest.approx(top["y"], abs=1e-3) == 0.2
    assert pytest.approx(top["w"], abs=1e-3) == 0.4
    assert pytest.approx(top["h"], abs=1e-3) == 0.6
    assert top["box"] == [0.3, 0.2, 0.4, 0.6]


def test_postprocess_rfdetr_multiclass_aadhaar():
    """Verify multi-class argmax and per-class confidence thresholding."""
    orig_dim = (800, 600)
    classes = ["Aadhaar_No", "DOB", "Gender", "Name", "Photo"]

    # 2 queries: Query 0 is Photo (class index 4), Query 1 is Name (class index 3)
    boxes = np.array([
        [0.8, 0.3, 0.2, 0.3],
        [0.3, 0.4, 0.4, 0.1],
    ], dtype=np.float32)

    logits = np.zeros((2, 5), dtype=np.float32) - 10.0
    logits[0, 4] = 4.0  # Photo high
    logits[1, 3] = 4.0  # Name high

    res = _postprocess_rfdetr_predictions(
        boxes=boxes,
        logits=logits,
        orig_dim=orig_dim,
        class_names=classes,
        conf_threshold=0.25,
    )

    assert len(res) == 2
    labels = [b["label"] for b in res]
    assert "Photo" in labels
    assert "Name" in labels


def test_metadata_sidecar_validation(tmp_path: Path):
    """Verify sidecar metadata loading and class count mismatch validation."""
    model_file = tmp_path / "rfdetr_card.onnx"
    model_file.write_bytes(b"dummy onnx bytes")

    sidecar = tmp_path / "rfdetr_card.meta.json"
    sidecar_data = {
        "classes": ["Card"],
        "input_size": [640, 640],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "resize_mode": "square_bilinear",
        "output_names": ["pred_boxes", "pred_logits"],
        "rfdetr_version": "0.1.0",
        "sha256": "abcdef123456",
    }
    sidecar.write_text(json.dumps(sidecar_data), encoding="utf-8")

    # Matching class count passes
    meta = _load_model_metadata(str(model_file), expected_num_classes=1)
    assert meta["classes"] == ["Card"]
    assert meta["resize_mode"] == "square_bilinear"

    # Mismatched class count must raise ValueError
    with pytest.raises(ValueError, match="Model metadata classes count mismatch"):
        _load_model_metadata(str(model_file), expected_num_classes=5)


def test_rfdetr_parity_harness_skips_when_no_weights():
    """Verify parity test cleanly skips when weights are not present."""
    weights_path = Path("ml_service/models/rfdetr_card.onnx")
    if not weights_path.exists():
        pytest.skip("RF-DETR card weights not present on disk (pending Phase 4 training)")
