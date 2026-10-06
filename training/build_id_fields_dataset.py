"""Dataset Builder for Unified ID-Fields Model (Phase 5).

Unified Schema (Appendix D exact order):
["Photo", "Name", "ID_No", "DOB", "Gender", "Address", "Father_Name", "Issue_Date", "Expiry_Date", "Signature"]

Generates synthetic and composited data with strict DESIGN_ID splits:
- 40 distinct designs per document type:
  - Designs 0..31 -> train
  - Designs 32..35 -> valid
  - Designs 36..39 -> test
- Bounding boxes tracked through homography warping.
- Saves COCO JSON format ready for RF-DETR training.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from training.synth_fields import (
    CARD_H,
    CARD_W,
    DOC_TYPES,
    FIELD_CLASSES,
    composite_card_on_background,
    render_card_with_fields,
)

logger = logging.getLogger(__name__)


def build_id_fields_dataset(
    output_dir: Path,
    num_designs: int = 40,
    composites_per_design: int = 8,
    seed: int = 42,
) -> Dict[str, Any]:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    splits = ["train", "valid", "test"]
    for s in splits:
        (output_dir / s).mkdir(parents=True, exist_ok=True)

    category_map = {name: idx + 1 for idx, name in enumerate(FIELD_CLASSES)}
    categories = [{"id": idx + 1, "name": name, "supercategory": "id_field"} for idx, name in enumerate(FIELD_CLASSES)]

    split_images: Dict[str, List[Dict[str, Any]]] = {s: [] for s in splits}
    split_annotations: Dict[str, List[Dict[str, Any]]] = {s: [] for s in splits}
    split_counts: Dict[str, int] = {s: 0 for s in splits}

    next_img_id = 1
    next_ann_id = 1

    # Base background textures
    bg_colors = [(180, 180, 175), (140, 120, 100), (90, 100, 110), (210, 210, 215), (70, 75, 80)]
    bgs = [Image.new("RGB", (1280, 720), color=c) for c in bg_colors]

    doc_types = ["aadhaar", "pan", "voter_id", "driving_licence", "nepali_citizenship", "bhutan_cid"]

    for dtype in doc_types:
        for did in range(num_designs):
            # Design-level split assignment
            if did < 32:
                target_split = "train"
            elif did < 36:
                target_split = "valid"
            else:
                target_split = "test"

            card_img, fields = render_card_with_fields(dtype, design_id=did, seed=seed)

            for comp_idx in range(composites_per_design):
                bg = rng.choice(bgs)
                comp_img, comp_fields, _ = composite_card_on_background(card_img, fields, bg, rng)

                fname = f"{dtype}_d{did:02d}_c{comp_idx:02d}.jpg"
                dest_path = output_dir / target_split / fname
                comp_img.save(dest_path, quality=88)

                img_id = next_img_id
                next_img_id += 1
                split_images[target_split].append({
                    "id": img_id,
                    "file_name": fname,
                    "width": comp_img.width,
                    "height": comp_img.height,
                    "doc_type": dtype,
                    "design_id": did,
                })

                for f in comp_fields:
                    cat_id = category_map[f["label"]]
                    bx, by, bw, bh = f["x"], f["y"], f["w"], f["h"]
                    split_annotations[target_split].append({
                        "id": next_ann_id,
                        "image_id": img_id,
                        "category_id": cat_id,
                        "bbox": [round(bx, 1), round(by, 1), round(bw, 1), round(bh, 1)],
                        "area": round(bw * bh, 1),
                        "iscrowd": 0,
                        "segmentation": [],
                    })
                    next_ann_id += 1

                split_counts[target_split] += 1

    # Save COCO JSON per split
    for s in splits:
        coco_dict = {
            "images": split_images[s],
            "annotations": split_annotations[s],
            "categories": categories,
        }
        with open(output_dir / s / "_annotations.coco.json", "w", encoding="utf-8") as f:
            json.dump(coco_dict, f, indent=2)

    summary = {
        "output_dir": str(output_dir),
        "classes": FIELD_CLASSES,
        "doc_types": doc_types,
        "total_images": sum(split_counts.values()),
        "splits": split_counts,
        "design_split_rule": "designs 0..31 train, 32..35 valid, 36..39 test",
    }
    with open(output_dir / "dataset_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("ID-fields dataset assembled: %s", json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_id_fields_dataset(Path("data/coco_id_fields"))
