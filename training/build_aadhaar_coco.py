"""Builder for COCO Aadhaar Dataset (Phase 4.1).

Converts data/AADHAR (YOLO format) to data/coco_aadhaar (COCO format).
Classes in exact order: ["Aadhaar_No", "DOB", "Gender", "Name", "Photo"].
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List

from PIL import Image

logger = logging.getLogger(__name__)

CLASSES = ["Aadhaar_No", "DOB", "Gender", "Name", "Photo"]


def convert_split(src_dir: Path, dest_dir: Path, split_name: str) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    img_dir = src_dir / "images"
    lbl_dir = src_dir / "labels"

    categories = [
        {"id": idx + 1, "name": name, "supercategory": "none"}
        for idx, name in enumerate(CLASSES)
    ]

    images: List[Dict] = []
    annotations: List[Dict] = []
    ann_id = 1

    img_files = sorted(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))
    for img_id, img_path in enumerate(img_files, start=1):
        try:
            with Image.open(img_path) as im:
                w, h = im.size
        except Exception:
            continue

        dest_img_path = dest_dir / img_path.name
        if not dest_img_path.exists():
            shutil.copy2(img_path, dest_img_path)

        images.append({
            "id": img_id,
            "file_name": img_path.name,
            "width": w,
            "height": h,
        })

        lbl_path = lbl_dir / f"{img_path.stem}.txt"
        if not lbl_path.exists():
            continue

        for line in lbl_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            try:
                c_idx = int(parts[0])
                cx, cy, bw, bh = map(float, parts[1:5])
            except ValueError:
                continue

            if c_idx < 0 or c_idx >= len(CLASSES):
                continue

            box_w = bw * w
            box_h = bh * h
            box_x = (cx * w) - (box_w / 2.0)
            box_y = (cy * h) - (box_h / 2.0)

            x1 = max(0.0, min(float(w), box_x))
            y1 = max(0.0, min(float(h), box_y))
            x2 = max(0.0, min(float(w), box_x + box_w))
            y2 = max(0.0, min(float(h), box_y + box_h))
            cw = max(0.0, x2 - x1)
            ch = max(0.0, y2 - y1)

            if cw <= 0.0 or ch <= 0.0:
                continue

            annotations.append({
                "id": ann_id,
                "image_id": img_id,
                "category_id": c_idx + 1,
                "bbox": [round(x1, 2), round(y1, 2), round(cw, 2), round(ch, 2)],
                "area": round(cw * ch, 2),
                "iscrowd": 0,
                "segmentation": [],
            })
            ann_id += 1

    coco_dict = {
        "images": images,
        "annotations": annotations,
        "categories": categories,
    }
    json_path = dest_dir / "_annotations.coco.json"
    json_path.write_text(json.dumps(coco_dict, indent=2), encoding="utf-8")
    logger.info("Split %s converted: %d images, %d annotations -> %s", split_name, len(images), len(annotations), json_path)
    return len(images)


def build_coco_aadhaar(src_root: Path = Path("data/AADHAR"), dest_root: Path = Path("data/coco_aadhaar")):
    dest_root.mkdir(parents=True, exist_ok=True)
    counts = {}
    for split in ["train", "valid", "test"]:
        s_src = src_root / split
        s_dest = dest_root / split
        if s_src.exists():
            n = convert_split(s_src, s_dest, split)
            counts[split] = n
    logger.info("All splits converted: %s", counts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_coco_aadhaar()
