"""TASK 4f: 'Does it help' check.
Runs 30 test photos through the real pipeline entry point with CARD_DETECTOR_BACKEND=rf_detr.
Saves a contact sheet of crops (rectified if ENABLE_CARD_RECTIFICATION is on) under eval/runs/.
"""

import datetime
import io
import json
import os
import random
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Ensure environment
os.environ["CARD_DETECTOR_BACKEND"] = "rf_detr"
os.environ["DETECTOR_BACKEND"] = "rf_detr"

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from yolo_roi import (
    clear_session_cache,
    extract_roi_boxes,
    isolate_document_card,
    get_card_detector_backend,
)


def run_crop_check():
    clear_session_cache()
    backend = get_card_detector_backend()
    assert backend == "rf_detr", f"Expected backend rf_detr, got {backend}"

    test_dir = Path("data/coco_card/test")
    test_images = sorted(list(test_dir.glob("*.jpg")) + list(test_dir.glob("*.png")))
    assert len(test_images) >= 30, f"Expected >= 30 test images in {test_dir}, found {len(test_images)}"

    # Group by doc type (alb_id, srb_passport, svk_id)
    by_type: Dict[str, List[Path]] = {}
    for p in test_images:
        prefix = p.name.split("_")[0]
        if "srb" in p.name:
            prefix = "srb_passport"
        elif "alb" in p.name:
            prefix = "alb_id"
        elif "svk" in p.name:
            prefix = "svk_id"
        by_type.setdefault(prefix, []).append(p)

    rng = random.Random(42)
    selected_paths: List[Path] = []
    for dt, paths in sorted(by_type.items()):
        selected_paths.extend(rng.sample(paths, 10))

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"eval/runs/{ts}_task4f_crops")
    out_dir.mkdir(parents=True, exist_ok=True)

    crops_info: List[Dict[str, Any]] = []
    pil_crops: List[Image.Image] = []

    for idx, img_path in enumerate(selected_paths):
        raw_bytes = img_path.read_bytes()
        
        # Test pipeline entry points
        boxes = extract_roi_boxes(raw_bytes)
        card_box = next((b for b in boxes if b.get("label") in ("Card", "card", "document")), None)
        
        cropped_bytes, meta = isolate_document_card(raw_bytes)
        
        if cropped_bytes and len(cropped_bytes) > 100:
            crop_img = Image.open(io.BytesIO(cropped_bytes)).convert("RGB")
        else:
            # Fallback to manual crop if isolate_document_card didn't crop
            if card_box:
                full_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                w, h = full_img.size
                bx = int(card_box["x"] * w)
                by = int(card_box["y"] * h)
                bw = int(card_box["w"] * w)
                bh = int(card_box["h"] * h)
                crop_img = full_img.crop((bx, by, bx + bw, by + bh))
            else:
                crop_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")

        # Resize to fixed thumbnail for contact sheet
        thumb = crop_img.resize((320, 200), Image.Resampling.BILINEAR)
        draw = ImageDraw.Draw(thumb)
        tag = f"{img_path.name[:18]} | conf={card_box.get('confidence') if card_box else 'None'}"
        draw.rectangle([0, 0, 320, 20], fill=(0, 0, 0))
        draw.text((4, 2), tag, fill=(255, 255, 255))
        pil_crops.append(thumb)

        crops_info.append({
            "image": img_path.name,
            "card_box": card_box,
            "crop_meta": meta,
            "crop_size": [crop_img.width, crop_img.height],
        })

    # Assemble 6x5 contact sheet (30 images)
    cols = 5
    rows = 6
    sheet = Image.new("RGB", (cols * 320, rows * 200), color=(30, 30, 30))
    for i, thumb in enumerate(pil_crops):
        r = i // cols
        c = i % cols
        sheet.paste(thumb, (c * 320, r * 200))

    contact_sheet_path = out_dir / "contact_sheet_crops.jpg"
    sheet.save(contact_sheet_path, quality=90)
    print(f"[task4f] Saved 30-crop contact sheet to {contact_sheet_path}")

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps({
        "timestamp": ts,
        "backend": backend,
        "num_crops": len(crops_info),
        "crops": crops_info,
        "contact_sheet": str(contact_sheet_path),
    }, indent=2), encoding="utf-8")
    print(f"[task4f] Saved report to {report_path}")

    return contact_sheet_path, report_path


if __name__ == "__main__":
    run_crop_check()
