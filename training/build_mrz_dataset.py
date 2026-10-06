"""Builder script for MRZ Detector Dataset (Phase 3).

Classes: ["MRZ"]
Combines:
1. Real passport and ID card MRZ crops from MIDV-2020:
   - Train: grc_passport, lva_passport, rus_internalpassport, esp_id, est_id
   - Valid: aze_passport, fin_id
   - Test: srb_passport, alb_id, svk_id
2. Synthetic valid ICAO 9303 TD3 and TD1 MRZ strips rendered on real backgrounds (TRAIN extras only).
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from training.synth_mrz import render_mrz_strip

logger = logging.getLogger(__name__)


def build_mrz_dataset(
    coco_card_dir: Path,
    output_dir: Path,
    num_synth_train: int = 500,
    seed: int = 42,
) -> Dict[str, Any]:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    splits = ["train", "valid", "test"]
    for s in splits:
        (output_dir / s).mkdir(parents=True, exist_ok=True)

    category = [{"id": 1, "name": "MRZ", "supercategory": "mrz"}]

    summary = {}

    for s in splits:
        coco_path = coco_card_dir / s / "_annotations.coco.json"
        with open(coco_path, "r", encoding="utf-8") as f:
            coco_data = json.load(f)

        s_images = []
        s_annotations = []
        next_img_id = 1
        next_ann_id = 1

        anns_by_img = {}
        for a in coco_data.get("annotations", []):
            anns_by_img.setdefault(a["image_id"], []).append(a)

        for img_info in coco_data.get("images", []):
            fname = img_info["file_name"]
            # Filter for passport or ID card types that have MRZ
            is_passport = "passport" in fname
            is_id_card = any(k in fname for k in ["alb_id", "svk_id", "esp_id", "est_id", "fin_id"])
            if not (is_passport or is_id_card):
                continue

            src_img_path = coco_card_dir / s / fname
            if not src_img_path.exists():
                continue

            # Copy image to MRZ split
            dest_img_path = output_dir / s / fname
            dest_img_path.write_bytes(src_img_path.read_bytes())

            w, h = img_info["width"], img_info["height"]
            img_entry = {
                "id": next_img_id,
                "file_name": fname,
                "width": w,
                "height": h,
            }
            s_images.append(img_entry)

            for a in anns_by_img.get(img_info["id"], []):
                bx, by, bw, bh = a["bbox"]
                # MRZ is at bottom of document
                # On TD3 passports: bottom ~22%
                # On TD1 ID cards: bottom ~30%
                fraction = 0.22 if is_passport else 0.30
                mrz_h = bh * fraction
                mrz_y = (by + bh) - mrz_h
                # Slightly inset x
                mrz_x = bx + bw * 0.04
                mrz_w = bw * 0.92

                s_annotations.append({
                    "id": next_ann_id,
                    "image_id": next_img_id,
                    "category_id": 1,
                    "bbox": [round(mrz_x, 1), round(mrz_y, 1), round(mrz_w, 1), round(mrz_h, 1)],
                    "area": round(mrz_w * mrz_h, 1),
                    "iscrowd": 0,
                    "segmentation": [],
                })
                next_ann_id += 1

            next_img_id += 1

        # Add synthetic MRZ train-only extras
        if s == "train":
            bg_colors = [(160, 160, 160), (200, 190, 180), (120, 130, 140), (220, 220, 220)]
            for i in range(num_synth_train):
                fmt = "TD3" if i % 2 == 0 else "TD1"
                strip, bbox = render_mrz_strip(fmt, width=640, rng=rng)
                canvas = Image.new("RGB", (800, 600), color=rng.choice(bg_colors))
                px = rng.randint(20, 800 - strip.width - 20)
                py = rng.randint(20, 600 - strip.height - 20)
                canvas.paste(strip, (px, py))

                synth_fname = f"synth_mrz_{i:04d}.jpg"
                canvas.save(output_dir / s / synth_fname, quality=88)

                s_images.append({
                    "id": next_img_id,
                    "file_name": synth_fname,
                    "width": 800,
                    "height": 600,
                })
                s_annotations.append({
                    "id": next_ann_id,
                    "image_id": next_img_id,
                    "category_id": 1,
                    "bbox": [float(px + bbox[0]), float(py + bbox[1]), float(bbox[2] - bbox[0]), float(bbox[3] - bbox[1])],
                    "area": float((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])),
                    "iscrowd": 0,
                    "segmentation": [],
                })
                next_img_id += 1
                next_ann_id += 1

        mrz_coco = {
            "images": s_images,
            "annotations": s_annotations,
            "categories": category,
        }
        with open(output_dir / s / "_annotations.coco.json", "w", encoding="utf-8") as f:
            json.dump(mrz_coco, f, indent=2)

        summary[s] = {"images": len(s_images), "annotations": len(s_annotations)}

    logger.info("MRZ dataset built: %s", json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_mrz_dataset(Path("data/coco_card"), Path("data/coco_mrz"))
