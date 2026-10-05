"""YOLO to COCO conversion utility.

Converts standard YOLO format annotation text files and images to COCO JSON format.
Ensures zero-indexed or continuous category mappings without phantom super-categories.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image

logger = logging.getLogger(__name__)


def yolo_to_coco_box(
    cx: float, cy: float, w: float, h: float, img_width: int, img_height: int
) -> Tuple[float, float, float, float]:
    """Convert normalized YOLO bounding box (cx, cy, w, h) to COCO pixel coordinates (x, y, w, h).

    Clips box coordinates to image boundaries.
    """
    box_w = w * img_width
    box_h = h * img_height
    box_x = (cx * img_width) - (box_w / 2.0)
    box_y = (cy * img_height) - (box_h / 2.0)

    # Clip to boundaries
    x1 = max(0.0, min(float(img_width), box_x))
    y1 = max(0.0, min(float(img_height), box_y))
    x2 = max(0.0, min(float(img_width), box_x + box_w))
    y2 = max(0.0, min(float(img_height), box_y + box_h))

    clipped_w = max(0.0, x2 - x1)
    clipped_h = max(0.0, y2 - y1)
    return round(x1, 2), round(y1, 2), round(clipped_w, 2), round(clipped_h, 2)


def coco_to_yolo_box(
    x: float, y: float, w: float, h: float, img_width: int, img_height: int
) -> Tuple[float, float, float, float]:
    """Convert COCO pixel coordinates (x, y, w, h) back to normalized YOLO (cx, cy, w, h)."""
    cx = (x + (w / 2.0)) / img_width
    cy = (y + (h / 2.0)) / img_height
    norm_w = w / img_width
    norm_h = h / img_height
    return round(cx, 6), round(cy, 6), round(norm_w, 6), round(norm_h, 6)


def convert_yolo_split_to_coco(
    images_dir: Path,
    labels_dir: Path,
    class_names: List[str],
    output_json_path: Path,
    category_id_start: int = 1,
) -> Dict:
    """Convert a YOLO split directory (images + text labels) into a single COCO JSON file.

    Args:
        images_dir: Path to image directory
        labels_dir: Path to label directory with .txt files
        class_names: Ordered list of category names
        output_json_path: Output file path for COCO JSON
        category_id_start: Start index for category IDs (typically 1 for COCO)
    """
    categories = [
        {"id": idx + category_id_start, "name": name, "supercategory": "none"}
        for idx, name in enumerate(class_names)
    ]

    images: List[Dict] = []
    annotations: List[Dict] = []
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    img_files = sorted([p for p in images_dir.iterdir() if p.suffix.lower() in image_extensions])
    annotation_id = 1

    for img_idx, img_path in enumerate(img_files, start=1):
        try:
            with Image.open(img_path) as im:
                width, height = im.size
        except Exception as exc:
            logger.warning("Could not open image %s: %s", img_path, exc)
            continue

        images.append(
            {
                "id": img_idx,
                "file_name": img_path.name,
                "width": width,
                "height": height,
            }
        )

        label_path = labels_dir / f"{img_path.stem}.txt"
        if not label_path.exists():
            continue

        lines = label_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines:
            parts = line.strip().split()
            if len(parts) < 5:
                continue

            try:
                class_idx = int(parts[0])
                cx, cy, w, h = map(float, parts[1:5])
            except ValueError:
                continue

            if class_idx < 0 or class_idx >= len(class_names):
                logger.warning(
                    "Skipping out-of-range class ID %d (known classes %d) in %s",
                    class_idx,
                    len(class_names),
                    label_path,
                )
                continue

            x, y, box_w, box_h = yolo_to_coco_box(cx, cy, w, h, width, height)
            if box_w <= 0.0 or box_h <= 0.0:
                continue

            area = round(box_w * box_h, 2)
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": img_idx,
                    "category_id": class_idx + category_id_start,
                    "bbox": [x, y, box_w, box_h],
                    "area": area,
                    "iscrowd": 0,
                    "segmentation": [],
                }
            )
            annotation_id += 1

    coco_dict = {
        "images": images,
        "annotations": annotations,
        "categories": categories,
    }

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(coco_dict, indent=2), encoding="utf-8")
    return coco_dict
