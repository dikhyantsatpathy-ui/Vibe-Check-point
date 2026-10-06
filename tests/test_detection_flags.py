"""Unit and integration tests for detection flags and fallbacks (Phase 7.4).

Verifies:
  1. Flag validation & environment variable handling (fail-loud on invalid values).
  2. Missing weights fail-loud without fallback when flag is enabled.
  3. SHA-256 sidecar verification & fail-closed behavior on tampered weights.
  4. EXIF-rotated input handling.
  5. Box coordinate normalization & clipping within [0.0, 1.0].
  6. Model fetch mock verification for Hugging Face downloads.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.yolo_roi import (
    crop_region_to_bytes,
    extract_roi_boxes,
    extract_mrz_zone,
    get_card_detector_backend,
    get_detector_backend,
    get_field_detector_backend,
    get_mrz_detector_backend,
    scale_boxes_to_original,
)
from app.doctype_cls import classify_document, get_doctype_backend
from ml_service.model_fetch import compute_sha256, verify_model_integrity


def test_flag_parsing_defaults(monkeypatch):
    """Verify default values when environment variables are unset."""
    monkeypatch.delenv("DETECTOR_BACKEND", raising=False)
    monkeypatch.delenv("CARD_DETECTOR_BACKEND", raising=False)
    monkeypatch.delenv("FIELD_DETECTOR_BACKEND", raising=False)
    monkeypatch.delenv("MRZ_DETECTOR_BACKEND", raising=False)
    monkeypatch.delenv("DOCTYPE_BACKEND", raising=False)

    assert get_detector_backend() == "yolov8"
    assert get_card_detector_backend() == "yolov8"
    assert get_field_detector_backend() == "yolov8"
    assert get_mrz_detector_backend() == "bottom20"
    assert get_doctype_backend() == "v1"


def test_flag_parsing_overrides(monkeypatch):
    """Verify explicit override values for all backend flags."""
    monkeypatch.setenv("CARD_DETECTOR_BACKEND", "rf_detr")
    assert get_card_detector_backend() == "rf_detr"

    monkeypatch.setenv("FIELD_DETECTOR_BACKEND", "rf_detr")
    assert get_field_detector_backend() == "rf_detr"

    monkeypatch.setenv("MRZ_DETECTOR_BACKEND", "rf_detr")
    assert get_mrz_detector_backend() == "rf_detr"

    monkeypatch.setenv("DOCTYPE_BACKEND", "v2")
    assert get_doctype_backend() == "v2"


def test_flag_invalid_values_raise_value_error(monkeypatch):
    """Verify invalid flag configurations fail loudly with ValueError."""
    monkeypatch.setenv("CARD_DETECTOR_BACKEND", "invalid_backend")
    with pytest.raises(ValueError, match="Unsupported CARD_DETECTOR_BACKEND"):
        get_card_detector_backend()

    monkeypatch.setenv("MRZ_DETECTOR_BACKEND", "magic_wand")
    with pytest.raises(ValueError, match="Unsupported MRZ_DETECTOR_BACKEND"):
        get_mrz_detector_backend()

    monkeypatch.setenv("DOCTYPE_BACKEND", "v3_unreleased")
    with pytest.raises(ValueError, match="Unsupported DOCTYPE_BACKEND"):
        get_doctype_backend()


def test_missing_weights_fail_loudly(monkeypatch):
    """When a model backend is enabled but weights file is missing, fail loudly."""
    monkeypatch.setenv("MRZ_DETECTOR_BACKEND", "rf_detr")
    with patch("app.yolo_roi._get_mrz_session", return_value=None):
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), (255, 255, 255)).save(buf, format="PNG")
        img_bytes = buf.getvalue()
        with pytest.raises(FileNotFoundError, match="MRZ_DETECTOR_BACKEND='rf_detr' configured but MRZ weights could not be loaded"):
            extract_mrz_zone(img_bytes)


def test_tampered_model_fails_closed(tmp_path):
    """Verify that a modified model file with mismatched SHA-256 fails closed."""
    fake_model = tmp_path / "model.onnx"
    fake_model.write_bytes(b"original model content")

    fake_meta = tmp_path / "model.meta.json"
    fake_meta.write_text(json.dumps({"sha256": compute_sha256(fake_model)}), encoding="utf-8")

    # Initial verification should pass
    assert verify_model_integrity(fake_model, fake_meta) is True

    # Tamper with the model content
    fake_model.write_bytes(b"tampered model payload")
    assert verify_model_integrity(fake_model, fake_meta) is False


def test_exif_rotated_input_handling():
    """Verify that images with EXIF orientation tags are handled safely."""
    img = Image.new("RGB", (200, 100), color=(180, 180, 180))
    # Add EXIF orientation tag (6 = 90 deg CW rotation)
    exif = img.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    raw_bytes = buf.getvalue()

    boxes = extract_roi_boxes(raw_bytes)
    assert isinstance(boxes, list)
    for b in boxes:
        assert 0.0 <= b["x"] <= 1.0
        assert 0.0 <= b["y"] <= 1.0
        assert 0.0 <= b["w"] <= 1.0
        assert 0.0 <= b["h"] <= 1.0


def test_clip_to_image_and_crop():
    """Verify normalized bounding boxes never produce out-of-bounds crops."""
    img = Image.new("RGB", (500, 300), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    # Bounding box near edge with generous padding
    box = {"x": 0.05, "y": 0.05, "w": 0.20, "h": 0.20}
    crop = crop_region_to_bytes(raw_bytes, box, padding=0.10)
    assert crop is not None
    assert len(crop) > 0

    cropped_img = Image.open(io.BytesIO(crop))
    assert cropped_img.width > 0
    assert cropped_img.height > 0


def test_model_fetch_hf_mock(tmp_path, monkeypatch):
    """Verify fetch_models_from_hf handles downloads and validation correctly."""
    from ml_service.model_fetch import fetch_models_from_hf

    fake_downloaded = tmp_path / "rfdetr_card_int8.onnx"
    fake_downloaded.write_bytes(b"fake model data")
    expected_sha = compute_sha256(fake_downloaded)

    fake_meta = tmp_path / "rfdetr_card_int8.meta.json"
    fake_meta.write_text(json.dumps({"sha256": expected_sha}), encoding="utf-8")

    def mock_download(repo_id, filename, token, local_dir):
        return str(tmp_path / filename)

    with patch("huggingface_hub.hf_hub_download", side_effect=mock_download):
        status = fetch_models_from_hf(
            repo_id="test/repo",
            dest_dir=tmp_path,
            model_filenames=["rfdetr_card_int8.onnx", "rfdetr_card_int8.meta.json"]
        )
        assert status.get("rfdetr_card_int8.onnx") is True
        assert status.get("rfdetr_card_int8.meta.json") is True
