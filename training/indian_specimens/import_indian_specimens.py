"""Import Indian specimen photos and clicked quads into COCO format.

Conventions matched strictly to convert_midv_to_coco:
1. EXIF orientation corrected via ImageOps.exif_transpose before coordinate computation.
2. Downscaled so long side is 1280 px (preserving aspect ratio).
3. Quadrilaterals converted to bounding boxes and clipped to image boundaries.
4. Separate destination directories:
   - data/coco_card_indian/test/_annotations.coco.json
   - data/coco_card_indian/negatives/_annotations.coco.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageOps

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def convert_quad_to_bbox(
    quad: List[List[float]],
    orig_w: int,
    orig_h: int,
    scale: float,
) -> Optional[List[float]]:
    """Convert arbitrary quadrilateral to clipped, scaled COCO [x, y, w, h] bounding box."""
    if not quad or len(quad) < 3:
        return None

    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]

    x_min = max(0.0, min(xs))
    y_min = max(0.0, min(ys))
    x_max = min(float(orig_w), max(xs))
    y_max = min(float(orig_h), max(ys))

    box_w = x_max - x_min
    box_h = y_max - y_min

    # Discard if zero or inverted area (e.g. off-frame entirely)
    if box_w <= 1.0 or box_h <= 1.0:
        return None

    scaled_x = round(float(x_min * scale), 2)
    scaled_y = round(float(y_min * scale), 2)
    scaled_w = round(float(box_w * scale), 2)
    scaled_h = round(float(box_h * scale), 2)

    return [scaled_x, scaled_y, scaled_w, scaled_h]


def process_single_image(
    image_path: Path,
    quad: Optional[List[List[float]]],
    target_long_side: int = 1280,
) -> Tuple[Image.Image, Optional[List[float]], Tuple[int, int]]:
    """Transpose EXIF, resize to long side 1280, and scale bounding box."""
    with Image.open(image_path) as raw:
        transposed = ImageOps.exif_transpose(raw)
        transposed.load()
        if transposed.mode != "RGB":
            transposed = transposed.convert("RGB")

    orig_w, orig_h = transposed.size
    scale = target_long_side / float(max(orig_w, orig_h)) if max(orig_w, orig_h) > target_long_side else 1.0
    new_w = int(round(orig_w * scale))
    new_h = int(round(orig_h * scale))

    resized = transposed.resize((new_w, new_h), Image.Resampling.BILINEAR)

    coco_box = None
    if quad is not None:
        coco_box = convert_quad_to_bbox(quad, orig_w, orig_h, scale)

    return resized, coco_box, (new_w, new_h)


def import_specimens_to_coco(
    raw_images_dir: Path,
    quads_json_path: Path,
    output_base_dir: Path = Path("data/coco_card_indian"),
    target_long_side: int = 1280,
) -> Dict[str, Any]:
    """Convert raw images + quads into test and negatives COCO datasets."""
    quads_dict: Dict[str, List[List[float]]] = {}
    if quads_json_path.exists():
        try:
            quads_dict = json.loads(quads_json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read quads file %s: %s", quads_json_path, exc)

    raw_files = sorted(
        list(raw_images_dir.glob("*.jpg"))
        + list(raw_images_dir.glob("*.jpeg"))
        + list(raw_images_dir.glob("*.png"))
    )

    test_dir = output_base_dir / "test"
    neg_dir = output_base_dir / "negatives"
    test_dir.mkdir(parents=True, exist_ok=True)
    neg_dir.mkdir(parents=True, exist_ok=True)

    categories = [
        {"id": 1, "name": "Card", "supercategory": "document"}
    ]

    test_images: List[Dict[str, Any]] = []
    test_annotations: List[Dict[str, Any]] = []

    neg_images: List[Dict[str, Any]] = []
    neg_annotations: List[Dict[str, Any]] = []

    ann_id = 1
    test_img_id = 1
    neg_img_id = 1

    for img_path in raw_files:
        is_negative = img_path.name.lower().startswith("neg") or img_path.name not in quads_dict

        quad = quads_dict.get(img_path.name)
        resized_img, box, (w, h) = process_single_image(img_path, quad, target_long_side)

        if is_negative or box is None:
            # Negative photo
            out_path = neg_dir / img_path.name
            resized_img.save(out_path, quality=92)
            neg_images.append({
                "id": neg_img_id,
                "file_name": img_path.name,
                "width": w,
                "height": h,
            })
            neg_img_id += 1
        else:
            # Test photo with card annotation
            out_path = test_dir / img_path.name
            resized_img.save(out_path, quality=92)
            test_images.append({
                "id": test_img_id,
                "file_name": img_path.name,
                "width": w,
                "height": h,
            })
            test_annotations.append({
                "id": ann_id,
                "image_id": test_img_id,
                "category_id": 1,
                "bbox": box,
                "area": round(box[2] * box[3], 2),
                "iscrowd": 0,
            })
            ann_id += 1
            test_img_id += 1

    test_coco = {
        "info": {
            "description": "SIH26188 Indian Specimen Test Set",
            "year": 2026,
            "date_created": datetime.datetime.now().isoformat(),
        },
        "categories": categories,
        "images": test_images,
        "annotations": test_annotations,
    }
    (test_dir / "_annotations.coco.json").write_text(json.dumps(test_coco, indent=2), encoding="utf-8")

    neg_coco = {
        "info": {
            "description": "SIH26188 Indian Specimen Negative Set",
            "year": 2026,
            "date_created": datetime.datetime.now().isoformat(),
        },
        "categories": categories,
        "images": neg_images,
        "annotations": neg_annotations,
    }
    (neg_dir / "_annotations.coco.json").write_text(json.dumps(neg_coco, indent=2), encoding="utf-8")

    summary = {
        "test_images": len(test_images),
        "test_annotations": len(test_annotations),
        "negative_images": len(neg_images),
        "test_json": str(test_dir / "_annotations.coco.json"),
        "negatives_json": str(neg_dir / "_annotations.coco.json"),
    }
    logger.info("Import completed: %s", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Import Indian specimen photos and clicked quads to COCO format.")
    parser.add_argument("--images-dir", type=Path, default=Path("training/indian_specimens/raw"), help="Raw photos directory.")
    parser.add_argument("--quads-file", type=Path, default=Path("training/indian_specimens/quads.json"), help="Clicked quads JSON.")
    parser.add_argument("--out-dir", type=Path, default=Path("data/coco_card_indian"), help="Output dataset directory.")
    args = parser.parse_args()

    import_specimens_to_coco(args.images_dir, args.quads_file, args.out_dir)


if __name__ == "__main__":
    main()
