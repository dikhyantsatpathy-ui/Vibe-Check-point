"""Script to build the Step 5 Model A training dataset.

Combines:
1. Real MIDV-2020 train-types photos (500 images)
2. Real data/IDcard train photos (39 images)
3. Synthetic data/card_synth train sample (300 images)
4. Realistic composites made from train-type card cutouts and backgrounds (1,000 images)
Total: 1,839 images.

Strict rules:
- Exclusively train-types used for cutouts and backgrounds (zero leakage from val/test).
- Fixed seed (42).
- Strictly NO flips.
- Saves counts to eval/runs/<ts>_trainset/counts.json.
- Generates 20-image contact sheet to eval/runs/<ts>_trainset/composite_contact_sheet.jpg.
"""

from __future__ import annotations

import datetime
import json
import logging
import math
import os
import random
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

from training.make_composites import generate_perspective_composite

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def extract_card_and_backgrounds_from_train_photos(
    train_coco_path: Path,
    train_images_dir: Path,
    seed: int = 42,
) -> Tuple[List[Image.Image], List[Image.Image]]:
    """Extract card cutouts and non-overlapping background patches from train-type photos."""
    random.seed(seed)
    with open(train_coco_path, "r", encoding="utf-8") as f:
        coco_data = json.load(f)

    anns_by_img = {}
    for ann in coco_data.get("annotations", []):
        anns_by_img.setdefault(ann["image_id"], []).append(ann)

    card_cutouts: List[Image.Image] = []
    bg_patches: List[Image.Image] = []

    for img_info in coco_data.get("images", []):
        img_p = train_images_dir / img_info["file_name"]
        if not img_p.exists():
            continue

        try:
            with Image.open(img_p) as im:
                pil_im = im.convert("RGB")
        except Exception:
            continue

        w, h = pil_im.size
        anns = anns_by_img.get(img_info["id"], [])
        if not anns:
            continue

        for ann in anns:
            bx, by, bw, bh = ann["bbox"]
            x1 = max(0, int(bx))
            y1 = max(0, int(by))
            x2 = min(w, int(bx + bw))
            y2 = min(h, int(by + bh))

            if (x2 - x1) >= 40 and (y2 - y1) >= 40:
                card_crop = pil_im.crop((x1, y1, x2, y2))
                card_cutouts.append(card_crop)

            # Sample background patch outside card bbox
            # Try top, bottom, left, right non-overlapping zones
            bg_candidate = None
            if y1 >= 250:  # Space above card
                bg_candidate = pil_im.crop((0, 0, w, y1))
            elif (h - y2) >= 250:  # Space below card
                bg_candidate = pil_im.crop((0, y2, w, h))
            elif x1 >= 250:  # Space left of card
                bg_candidate = pil_im.crop((0, 0, x1, h))
            elif (w - x2) >= 250:  # Space right of card
                bg_candidate = pil_im.crop((x2, 0, w, h))

            if bg_candidate and bg_candidate.width >= 100 and bg_candidate.height >= 100:
                bg_patches.append(bg_candidate.resize((640, 640)))

    logger.info("Extracted %d card cutouts and %d background patches from train photos.", len(card_cutouts), len(bg_patches))
    return card_cutouts, bg_patches


def build_training_set(
    coco_card_dir: Path,
    idcard_dir: Path,
    card_synth_dir: Path,
    output_run_dir: Path,
    num_composites: int = 1000,
    synth_sample_limit: int = 300,
    seed: int = 42,
) -> Dict[str, Any]:
    """Assemble the unified Model A training set with provenance tracking."""
    random.seed(seed)
    np.random.seed(seed)

    train_dir = coco_card_dir / "train"
    train_images_dir = train_dir / "images"
    train_ann_path = train_dir / "_annotations.coco.json"

    # 1. Load existing MIDV-2020 train annotations
    with open(train_ann_path, "r", encoding="utf-8") as f:
        base_coco = json.load(f)

    merged_images = list(base_coco.get("images", []))
    merged_annotations = list(base_coco.get("annotations", []))
    categories = [{"id": 1, "name": "Card", "supercategory": "document"}]

    next_image_id = max((im["id"] for im in merged_images), default=0) + 1
    next_ann_id = max((ann["id"] for ann in merged_annotations), default=0) + 1

    counts: Dict[str, Any] = {
        "sources": {
            "midv2020_train_photos": len(merged_images),
            "idcard_train": 0,
            "card_synth_sampled": 0,
            "composites": 0,
        },
        "total_images": 0,
        "total_annotations": 0,
        "seed": seed,
        "no_flips": True,
    }

    # 2. Add real data/IDcard train photos
    idcard_images_dir = idcard_dir / "train" / "images"
    idcard_labels_dir = idcard_dir / "train" / "labels"
    if idcard_images_dir.exists():
        id_files = sorted(list(idcard_images_dir.glob("*.jpg")) + list(idcard_images_dir.glob("*.png")))
        for fpath in id_files:
            lpath = idcard_labels_dir / f"{fpath.stem}.txt"
            if not lpath.exists():
                continue

            try:
                with Image.open(fpath) as im:
                    w, h = im.size
            except Exception:
                continue

            dest_fname = f"idcard_{fpath.name}"
            shutil.copy2(fpath, train_images_dir / dest_fname)

            img_entry = {
                "id": next_image_id,
                "file_name": dest_fname,
                "width": w,
                "height": h,
                "source": "data/IDcard/train",
            }
            merged_images.append(img_entry)

            with open(lpath, "r", encoding="utf-8") as lf:
                for line in lf:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                        bx = (cx - bw / 2.0) * w
                        by = (cy - bh / 2.0) * h
                        box_w = bw * w
                        box_h = bh * h
                        merged_annotations.append({
                            "id": next_ann_id,
                            "image_id": next_image_id,
                            "category_id": 1,
                            "bbox": [round(bx, 2), round(by, 2), round(box_w, 2), round(box_h, 2)],
                            "area": round(box_w * box_h, 2),
                            "iscrowd": 0,
                            "segmentation": [],
                        })
                        next_ann_id += 1

            next_image_id += 1
            counts["sources"]["idcard_train"] += 1

    # 3. Add sampled synthetic data (max 300)
    synth_images_dir = card_synth_dir / "train" / "images"
    synth_labels_dir = card_synth_dir / "train" / "labels"
    if synth_images_dir.exists():
        synth_files = sorted(list(synth_images_dir.glob("*.jpg")) + list(synth_images_dir.glob("*.png")))
        sample_size = min(synth_sample_limit, len(synth_files))
        sampled_synth = random.sample(synth_files, sample_size)

        for fpath in sampled_synth:
            lpath = synth_labels_dir / f"{fpath.stem}.txt"
            if not lpath.exists():
                continue

            try:
                with Image.open(fpath) as im:
                    w, h = im.size
            except Exception:
                continue

            dest_fname = f"synth_{fpath.name}"
            shutil.copy2(fpath, train_images_dir / dest_fname)

            img_entry = {
                "id": next_image_id,
                "file_name": dest_fname,
                "width": w,
                "height": h,
                "source": "data/card_synth/train",
            }
            merged_images.append(img_entry)

            with open(lpath, "r", encoding="utf-8") as lf:
                for line in lf:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                        bx = (cx - bw / 2.0) * w
                        by = (cy - bh / 2.0) * h
                        box_w = bw * w
                        box_h = bh * h
                        merged_annotations.append({
                            "id": next_ann_id,
                            "image_id": next_image_id,
                            "category_id": 1,
                            "bbox": [round(bx, 2), round(by, 2), round(box_w, 2), round(box_h, 2)],
                            "area": round(box_w * box_h, 2),
                            "iscrowd": 0,
                            "segmentation": [],
                        })
                        next_ann_id += 1

            next_image_id += 1
            counts["sources"]["card_synth_sampled"] += 1

    # 4. Generate ~1000 realistic composites from train photos
    card_cutouts, bg_patches = extract_card_and_backgrounds_from_train_photos(
        train_coco_path=train_ann_path,
        train_images_dir=train_images_dir,
        seed=seed,
    )

    composite_samples_for_contact_sheet: List[Tuple[Image.Image, List[float]]] = []

    for i in range(num_composites):
        card = random.choice(card_cutouts)
        if bg_patches:
            bg = random.choice(bg_patches)
        else:
            bg = Image.new("RGB", (640, 640), color=(random.randint(60, 200), random.randint(60, 200), random.randint(60, 200)))

        comp_img, (cx_norm, cy_norm, w_norm, h_norm) = generate_perspective_composite(
            card_img=card,
            bg_img=bg,
            seed=seed + i,
            scale_range=(0.45, 0.88),
            rotation_range=(-30.0, 30.0),
            perspective_jitter=0.10,
            add_glare=True,
            add_shadow=True,
            add_occlusion=True,
        )

        dest_fname = f"comp_{i:04d}.jpg"
        comp_dest = train_images_dir / dest_fname
        comp_img.save(comp_dest, quality=random.randint(70, 95))

        w, h = comp_img.size
        bx = (cx_norm - w_norm / 2.0) * w
        by = (cy_norm - h_norm / 2.0) * h
        box_w = w_norm * w
        box_h = h_norm * h

        bbox = [round(bx, 2), round(by, 2), round(box_w, 2), round(box_h, 2)]

        merged_images.append({
            "id": next_image_id,
            "file_name": dest_fname,
            "width": w,
            "height": h,
            "source": "make_composites",
        })

        merged_annotations.append({
            "id": next_ann_id,
            "image_id": next_image_id,
            "category_id": 1,
            "bbox": bbox,
            "area": round(box_w * box_h, 2),
            "iscrowd": 0,
            "segmentation": [],
        })

        if len(composite_samples_for_contact_sheet) < 20:
            composite_samples_for_contact_sheet.append((comp_img, bbox))

        next_image_id += 1
        next_ann_id += 1
        counts["sources"]["composites"] += 1

    # 5. Write updated merged _annotations.coco.json
    final_coco_data = {
        "images": merged_images,
        "annotations": merged_annotations,
        "categories": categories,
    }
    train_ann_path.write_text(json.dumps(final_coco_data, indent=2), encoding="utf-8")
    logger.info("Updated train annotations at %s: %d images, %d annotations", train_ann_path, len(merged_images), len(merged_annotations))

    counts["total_images"] = len(merged_images)
    counts["total_annotations"] = len(merged_annotations)

    # 6. Save 20-image composite contact sheet
    output_run_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet_path = output_run_dir / "composite_contact_sheet.jpg"
    generate_composite_contact_sheet(composite_samples_for_contact_sheet, contact_sheet_path)

    # 7. Write counts.json
    counts_path = output_run_dir / "counts.json"
    counts_path.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    logger.info("Saved trainset counts to %s", counts_path)

    return counts


def generate_composite_contact_sheet(
    samples: List[Tuple[Image.Image, List[float]]],
    output_path: Path,
) -> Path:
    """Render a 4x5 grid contact sheet with bounding boxes drawn."""
    cols, rows = 4, 5
    cell_w, cell_h = 320, 320
    grid_im = Image.new("RGB", (cols * cell_w, rows * cell_h), color=(25, 25, 28))

    for idx, (img, bbox) in enumerate(samples[:20]):
        c = idx % cols
        r = idx // cols

        # Draw box on thumbnail
        cell_img = img.copy()
        draw = ImageDraw.Draw(cell_img)
        bx, by, bw, bh = bbox
        draw.rectangle([bx, by, bx + bw, by + bh], outline=(0, 255, 64), width=4)

        cell_thumb = cell_img.resize((cell_w - 4, cell_h - 4))
        grid_im.paste(cell_thumb, (c * cell_w + 2, r * cell_h + 2))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    grid_im.save(output_path, quality=90)
    logger.info("Saved composite verification contact sheet to %s", output_path)
    return output_path


def main():
    coco_card_dir = Path("data/coco_card")
    idcard_dir = Path("data/IDcard")
    card_synth_dir = Path("data/card_synth")

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(f"eval/runs/{ts}_trainset")

    counts = build_training_set(
        coco_card_dir=coco_card_dir,
        idcard_dir=idcard_dir,
        card_synth_dir=card_synth_dir,
        output_run_dir=run_dir,
        num_composites=1000,
        synth_sample_limit=300,
        seed=42,
    )

    print("\n[STEP 5] MODEL A TRAINING SET ASSEMBLED:")
    for src, cnt in counts["sources"].items():
        print(f"  • {src:<25}: {cnt} images")
    print(f"  • Total Images:             {counts['total_images']}")
    print(f"  • Total Annotations:        {counts['total_annotations']}")
    print(f"  • Contact Sheet:            {run_dir / 'composite_contact_sheet.jpg'}")
    print(f"  • Counts Record:            {run_dir / 'counts.json'}")


if __name__ == "__main__":
    main()
