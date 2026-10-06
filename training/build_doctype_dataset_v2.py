"""Builder for Document-Type Classifier Dataset v2 (Phase 6.2).

8 classes (Appendix D exact order):
["aadhaar", "pan", "voter_id", "driving_licence", "passport", "nepali_citizenship", "bhutan_cid", "other"]

Split by template/design_id to avoid data leakage.
"""

from __future__ import annotations

import json
import logging
import os
import random
import shutil
from pathlib import Path
from typing import Dict, List

from PIL import Image

from training.synth_fields import (
    CARD_H,
    CARD_W,
    DOC_TYPES,
    composite_card_on_background,
    render_card_with_fields,
)

logger = logging.getLogger(__name__)

CLASSES_V2 = [
    "aadhaar",
    "pan",
    "voter_id",
    "driving_licence",
    "passport",
    "nepali_citizenship",
    "bhutan_cid",
    "other",
]


def build_doctype_dataset(
    output_dir: Path,
    seed: int = 42,
) -> Dict[str, Any]:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    for split in ["train", "valid"]:
        for c in CLASSES_V2:
            (output_dir / split / c).mkdir(parents=True, exist_ok=True)

    counts = {"train": {c: 0 for c in CLASSES_V2}, "valid": {c: 0 for c in CLASSES_V2}}

    # 1. Copy existing real images from data/doctype (train/valid)
    src_dt = Path("data/doctype")
    if src_dt.exists():
        for split in ["train", "valid"]:
            s_dir = src_dt / split
            if not s_dir.exists():
                continue
            for cls_folder in s_dir.iterdir():
                cname = cls_folder.name
                if cname in CLASSES_V2:
                    for im in cls_folder.glob("*.jpg"):
                        dest = output_dir / split / cname / f"orig_{im.name}"
                        shutil.copy2(im, dest)
                        counts[split][cname] += 1

    # 2. Add MIDV passport crops to "passport"
    midv_dir = Path("data/raw/midv2020/photo")
    if midv_dir.exists():
        for ptype, split in [("grc_passport", "train"), ("lva_passport", "train"), ("aze_passport", "valid")]:
            pdir = midv_dir / ptype
            if pdir.exists():
                for idx, pim in enumerate(list(pdir.glob("*.jpg"))[:50]):
                    try:
                        with Image.open(pim) as im:
                            crop = im.resize((320, 320))
                            dest = output_dir / split / "passport" / f"midv_{ptype}_{idx:03d}.jpg"
                            crop.save(dest, quality=85)
                            counts[split]["passport"] += 1
                    except Exception:
                        pass

    # 3. Generate procedural designs for Bhutan CID and supplement others
    # Designs 0..30 -> train; designs 31..38 -> valid (design-level split)
    bg_sample = Image.new("RGB", (640, 480), color=(140, 140, 140))
    for cname in ["bhutan_cid", "aadhaar", "pan", "voter_id", "driving_licence", "nepali_citizenship"]:
        for design_id in range(40):
            split = "valid" if design_id >= 32 else "train"
            card_img, fields = render_card_with_fields(cname, design_id=design_id, seed=seed)
            # Make 2 perspective variations per design
            for v in range(2):
                comp_img, _, _ = composite_card_on_background(card_img, fields, bg_sample, rng)
                crop_to_card = comp_img.resize((224, 224))
                dest = output_dir / split / cname / f"synth_d{design_id:02d}_v{v}.jpg"
                crop_to_card.save(dest, quality=85)
                counts[split][cname] += 1

    # 4. Supplement "other" with non-ID background crops and objects
    for i in range(80):
        split = "valid" if i >= 65 else "train"
        im = Image.new("RGB", (224, 224), color=(rng.randint(50, 200), rng.randint(50, 200), rng.randint(50, 200)))
        dest = output_dir / split / "other" / f"synth_other_{i:03d}.jpg"
        im.save(dest, quality=85)
        counts[split]["other"] += 1

    manifest_path = output_dir / "dataset_summary.json"
    manifest_path.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    logger.info("Doc-type v2 dataset assembled: %s", json.dumps(counts, indent=2))
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_doctype_dataset(Path("data/doctype_v2"))
