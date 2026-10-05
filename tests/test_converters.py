"""Unit tests for YOLO and MIDV to COCO converters."""

import json
from pathlib import Path
from PIL import Image
import pytest

from training.convert_yolo_to_coco import (
    coco_to_yolo_box,
    convert_yolo_split_to_coco,
    yolo_to_coco_box,
)
from training.convert_midv_to_coco import (
    get_split_for_midv_type,
    parse_midv500_frame_json,
    parse_midv2020_via_json,
    quad_to_axis_aligned_box,
)


def test_yolo_coco_coordinate_roundtrip():
    """Verify coordinate math between normalized YOLO cx,cy,w,h and COCO pixel x,y,w,h."""
    img_w, img_h = 640, 480
    cx, cy, w, h = 0.5, 0.5, 0.4, 0.3
    coco_x, coco_y, coco_w, coco_h = yolo_to_coco_box(cx, cy, w, h, img_w, img_h)

    # Center box: cx=320, cy=240, w=256, h=144 -> x=192, y=168
    assert coco_x == 192.0
    assert coco_y == 168.0
    assert coco_w == 256.0
    assert coco_h == 144.0

    # Round trip back
    rcx, rcy, rw, rh = coco_to_yolo_box(coco_x, coco_y, coco_w, coco_h, img_w, img_h)
    assert pytest.approx(rcx, abs=1e-4) == cx
    assert pytest.approx(rcy, abs=1e-4) == cy
    assert pytest.approx(rw, abs=1e-4) == w
    assert pytest.approx(rh, abs=1e-4) == h


def test_convert_yolo_split_to_coco(tmp_path: Path):
    """Test converting a mock YOLO split with 3 synthetic test images."""
    img_dir = tmp_path / "images"
    lbl_dir = tmp_path / "labels"
    out_json = tmp_path / "annotations.json"
    img_dir.mkdir()
    lbl_dir.mkdir()

    # Create 3 synthetic sample images and labels
    for i in range(3):
        im = Image.new("RGB", (200, 100), color=(i * 40, i * 40, i * 40))
        im_path = img_dir / f"sample_{i}.jpg"
        im.save(im_path)

        # Label: class 0, centered box
        lbl_path = lbl_dir / f"sample_{i}.txt"
        lbl_path.write_text(f"0 0.5 0.5 0.5 0.5\n", encoding="utf-8")

    class_names = ["Card"]
    result = convert_yolo_split_to_coco(img_dir, lbl_dir, class_names, out_json, category_id_start=1)

    assert out_json.exists()
    assert len(result["images"]) == 3
    assert len(result["annotations"]) == 3
    assert result["categories"] == [{"id": 1, "name": "Card", "supercategory": "none"}]

    first_ann = result["annotations"][0]
    assert first_ann["bbox"] == [50.0, 25.0, 100.0, 50.0]
    assert first_ann["category_id"] == 1


def test_midv_quad_to_axis_aligned_box_fully_visible():
    """Verify conversion of fully visible quad to axis-aligned box."""
    # A tilted quad inside a 1000x800 image
    quad = [[100.0, 100.0], [500.0, 150.0], [450.0, 400.0], [80.0, 350.0]]
    box = quad_to_axis_aligned_box(quad, img_width=1000, img_height=800)
    assert box is not None
    x, y, w, h = box
    assert x == 80.0
    assert y == 100.0
    assert w == 420.0  # max_x(500) - min_x(80)
    assert h == 300.0  # max_y(400) - min_y(100)


def test_midv_quad_to_axis_aligned_box_partly_off_frame():
    """Verify that partly off-frame quads are properly clipped to frame boundaries."""
    # Box extends to negative X (-50) and beyond height (850)
    quad = [[-50.0, 200.0], [300.0, 200.0], [300.0, 850.0], [-50.0, 850.0]]
    box = quad_to_axis_aligned_box(quad, img_width=500, img_height=600)
    assert box is not None
    x, y, w, h = box
    assert x == 0.0
    assert y == 200.0
    assert w == 300.0
    assert h == 400.0  # 600 - 200


def test_midv_quad_to_axis_aligned_box_fully_off_frame():
    """Verify that quads completely outside the frame return None (treated as negative)."""
    quad = [[-200.0, -100.0], [-50.0, -100.0], [-50.0, -10.0], [-200.0, -10.0]]
    box = quad_to_axis_aligned_box(quad, img_width=500, img_height=500)
    assert box is None


def test_midv_quad_downscaled():
    """Verify that box coordinates are scaled correctly when downscaling."""
    quad = [[100.0, 100.0], [300.0, 100.0], [300.0, 200.0], [100.0, 200.0]]
    # Scale factor 0.5 downscale
    box = quad_to_axis_aligned_box(quad, img_width=500, img_height=500, scale_factor=0.5)
    assert box is not None
    x, y, w, h = box
    assert x == 50.0
    assert y == 50.0
    assert w == 100.0
    assert h == 50.0


def test_parse_midv500_frame_json():
    """Verify parsing MIDV-500 quad format."""
    raw = '{"quad": [[10, 20], [110, 20], [110, 80], [10, 80]]}'
    quad = parse_midv500_frame_json(raw)
    assert quad == [[10, 20], [110, 20], [110, 80], [10, 80]]


def test_parse_midv2020_via_json():
    """Verify parsing MIDV-2020 VIA format with doc_quad."""
    via_data = {
        "img01.jpg12345": {
            "filename": "img01.jpg",
            "regions": [
                {
                    "shape_attributes": {
                        "name": "polygon",
                        "all_points_x": [15, 215, 215, 15],
                        "all_points_y": [25, 25, 125, 125],
                    },
                    "region_attributes": {"type": "doc_quad"},
                }
            ],
        }
    }
    quad = parse_midv2020_via_json(via_data, "img01.jpg12345")
    assert quad == [[15.0, 25.0], [215.0, 25.0], [215.0, 125.0], [15.0, 125.0]]


def test_midv_type_split_leakage_safety():
    """Verify type splits allocate test, val, and train according to Section 5.3 rules."""
    assert get_split_for_midv_type("alb_id") == "test"
    assert get_split_for_midv_type("grc_passport") == "test"
    assert get_split_for_midv_type("fin_id") == "val"
    assert get_split_for_midv_type("aze_passport") == "val"
    assert get_split_for_midv_type("esp_id") == "train"
    assert get_split_for_midv_type("unknown_type") == "train"
