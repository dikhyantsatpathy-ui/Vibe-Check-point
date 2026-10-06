"""Unit tests for Indian specimen import pipeline (Task 6).

Tests:
1. Quad to bounding box conversion and clipping on off-frame corners.
2. EXIF orientation handling (e.g. orientation tag 6).
3. End-to-end COCO conversion and negative image handling.
"""

import json
from pathlib import Path
from PIL import Image
import pytest

from training.indian_specimens.import_indian_specimens import (
    convert_quad_to_bbox,
    process_single_image,
    import_specimens_to_coco,
)


def test_quad_to_bbox_off_frame_corner_clipping():
    """Verify that off-frame corners are clipped to image bounds and scaled accurately."""
    orig_w, orig_h = 2000, 1000
    scale = 0.5

    # Quad with off-frame top-left (-100, -50) and off-frame bottom-right (2100, 1050)
    quad_off_frame = [
        [-100.0, -50.0],
        [1500.0, -20.0],
        [2100.0, 1050.0],
        [200.0, 900.0],
    ]

    box = convert_quad_to_bbox(quad_off_frame, orig_w, orig_h, scale)
    assert box is not None
    x, y, w, h = box

    # Must be clipped to [0, orig_w] and [0, orig_h], then scaled by 0.5
    assert x == 0.0
    assert y == 0.0
    assert w == 1000.0  # 2000 * 0.5
    assert h == 500.0   # 1000 * 0.5


def test_quad_to_bbox_completely_outside():
    """Verify that a quad entirely outside the image boundary returns None."""
    orig_w, orig_h = 1000, 1000
    scale = 1.0

    quad_outside = [
        [-500.0, -500.0],
        [-100.0, -500.0],
        [-100.0, -100.0],
        [-500.0, -100.0],
    ]
    box = convert_quad_to_bbox(quad_outside, orig_w, orig_h, scale)
    assert box is None


def test_exif_rotated_fixture(tmp_path):
    """Verify that process_single_image applies ImageOps.exif_transpose before scaling."""
    # Create a 400x200 image
    raw_img = Image.new("RGB", (400, 200), color=(200, 100, 50))
    img_path = tmp_path / "rotated.jpg"

    # Add EXIF orientation 6 (indicates 90 deg rotation, so physical is 200x400)
    exif = raw_img.getexif()
    exif[0x0112] = 6  # 0x0112 is standard EXIF tag for Orientation
    raw_img.save(img_path, "JPEG", exif=exif)

    quad = [[20.0, 30.0], [150.0, 30.0], [150.0, 300.0], [20.0, 300.0]]
    resized, box, (w, h) = process_single_image(img_path, quad, target_long_side=1280)

    # After EXIF transpose, dimensions should be portrait (width < height)
    assert h > w, f"Expected height > width after EXIF orientation 6 transpose, got {w}x{h}"
    assert box is not None
    assert len(box) == 4


def test_import_specimens_to_coco_end_to_end(tmp_path):
    """Verify end-to-end COCO conversion with test and negative images."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    # 1. Test image with card
    img1 = Image.new("RGB", (1000, 600), color=(220, 220, 220))
    p1 = raw_dir / "pan_card_test_01.jpg"
    img1.save(p1)

    # 2. Negative image without card
    img_neg = Image.new("RGB", (1000, 600), color=(100, 100, 100))
    p_neg = raw_dir / "neg_table_01.jpg"
    img_neg.save(p_neg)

    quads_file = tmp_path / "quads.json"
    quads_file.write_text(json.dumps({
        "pan_card_test_01.jpg": [[100, 50], [900, 50], [900, 550], [100, 550]],
    }), encoding="utf-8")

    out_base = tmp_path / "coco_out"
    summary = import_specimens_to_coco(raw_dir, quads_file, out_base, target_long_side=1280)

    assert summary["test_images"] == 1
    assert summary["test_annotations"] == 1
    assert summary["negative_images"] == 1

    # Verify JSON contents
    test_json = json.loads(Path(summary["test_json"]).read_text(encoding="utf-8"))
    assert len(test_json["images"]) == 1
    assert len(test_json["annotations"]) == 1
    assert test_json["annotations"][0]["category_id"] == 1

    neg_json = json.loads(Path(summary["negatives_json"]).read_text(encoding="utf-8"))
    assert len(neg_json["images"]) == 1
    assert len(neg_json["annotations"]) == 0
