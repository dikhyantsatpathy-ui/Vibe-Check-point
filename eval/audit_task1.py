"""
Task 1 Audit Harness (NO-CAP / SIH26188 Autonomous Work Order v3.1).
Executes:
  1a. Unified evaluation across YOLO, RF-DETR FP32, and RF-DETR INT8 through eval/evaluate.py
  1b. Visual verification contact sheet (GT in green, Pred in red on 24 test photos)
"""

import os
import sys
import json
import random
import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Ensure app & ml_service paths are imported
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app"))
sys.path.insert(0, str(REPO_ROOT / "ml_service"))
sys.path.insert(0, str(REPO_ROOT / "eval"))

from yolo_roi import clear_session_cache, _get_onnx_session, _run_rfdetr_onnx, _run_yolo_onnx
from evaluate import run_full_evaluation

def run_task1a_unified_evaluations(ts: str) -> dict:
    reports = {}
    models_to_test = [
        ("yolo", "yolov8", str(REPO_ROOT / "ml_service" / "models" / "card.onnx")),
        ("rfdetr_fp32", "rf_detr", str(REPO_ROOT / "ml_service" / "models" / "rfdetr_card.onnx")),
        ("rfdetr_int8", "rf_detr", str(REPO_ROOT / "ml_service" / "models" / "rfdetr_card_int8.onnx")),
    ]

    for model_key, backend, weights_path in models_to_test:
        print(f"\n{'='*70}\n[TASK 1a] Running evaluation for {model_key} (backend={backend})...\n{'='*70}")
        out_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_audit_{model_key}"
        out_dir.mkdir(parents=True, exist_ok=True)

        os.environ["DETECTOR_BACKEND"] = backend
        if backend == "yolov8":
            os.environ["YOLO_ROI_ONNX_PATH"] = weights_path
            os.environ.pop("RF_DETR_ONNX_PATH", None)
        else:
            os.environ["RF_DETR_ONNX_PATH"] = weights_path
            os.environ.pop("YOLO_ROI_ONNX_PATH", None)

        os.environ["EVAL_RUN_DIR"] = str(out_dir)
        clear_session_cache()

        rep = run_full_evaluation()
        reports[model_key] = rep

    return reports


def run_task1b_visual_contact_sheet(ts: str) -> Path:
    print(f"\n{'='*70}\n[TASK 1b] Generating 24-image GT vs Pred contact sheet...\n{'='*70}")
    audit_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet_path = audit_dir / "contact_gt_pred.jpg"

    test_dir = REPO_ROOT / "data" / "coco_card" / "test"
    coco_ann_file = test_dir / "_annotations.coco.json"
    with open(coco_ann_file, "r", encoding="utf-8") as f:
        coco = json.load(f)

    anns_by_img = {}
    for a in coco["annotations"]:
        anns_by_img.setdefault(a["image_id"], []).append(a)

    images_by_type = {}
    for img_info in coco["images"]:
        dt = img_info["doc_type"]
        images_by_type.setdefault(dt, []).append(img_info)

    # Pick 8 random per document type with fixed seed
    rng = random.Random(42)
    selected_images = []
    for dt, img_list in sorted(images_by_type.items()):
        picked = rng.sample(img_list, min(8, len(img_list)))
        selected_images.extend(picked)

    # Use RF-DETR INT8 for visual predictions
    os.environ["DETECTOR_BACKEND"] = "rf_detr"
    os.environ["RF_DETR_ONNX_PATH"] = str(REPO_ROOT / "ml_service" / "models" / "rfdetr_card_int8.onnx")
    clear_session_cache()
    session = _get_onnx_session()

    thumb_w, thumb_h = 320, 480
    grid_cols = 6
    grid_rows = 4  # 6x4 = 24 images
    sheet = Image.new("RGB", (grid_cols * thumb_w, grid_rows * thumb_h), color=(30, 30, 30))

    for idx, img_info in enumerate(selected_images):
        fname = img_info["file_name"]
        fpath = test_dir / "images" / fname
        if not fpath.exists():
            fpath = test_dir / fname

        with Image.open(fpath) as im:
            im_rgb = im.convert("RGB")
            draw_im = im_rgb.copy()
            draw = ImageDraw.Draw(draw_im)

            orig_w, orig_h = im_rgb.size

            # Draw Ground Truth in GREEN
            gts = anns_by_img.get(img_info["id"], [])
            for g in gts:
                gx, gy, gw, gh = g["bbox"]
                # line width 6
                for offset in range(4):
                    draw.rectangle([gx - offset, gy - offset, gx + gw + offset, gy + gh + offset], outline=(0, 255, 0))

            # Run inference and draw Pred in RED
            rgb_arr = np.asarray(im_rgb, dtype=np.uint8)
            dets = _run_rfdetr_onnx(rgb_arr, session, max_boxes=2, class_names=["Card"], conf_threshold=0.35)
            for d in dets:
                dx1 = d["x"] * orig_w
                dy1 = d["y"] * orig_h
                dw = d["w"] * orig_w
                dh = d["h"] * orig_h
                conf = d.get("confidence", 0.0)
                for offset in range(4):
                    draw.rectangle([dx1 - offset, dy1 - offset, dx1 + dw + offset, dy1 + dh + offset], outline=(255, 0, 0))
                draw.text((dx1 + 10, dy1 + 10), f"Pred: {conf:.2f}", fill=(255, 255, 255))

            # Resize to thumbnail
            thumb = draw_im.resize((thumb_w, thumb_h - 30), Image.Resampling.BILINEAR)

            # Paste into contact sheet
            c = idx % grid_cols
            r = idx // grid_cols
            x_pos = c * thumb_w
            y_pos = r * thumb_h

            sheet.paste(thumb, (x_pos, y_pos + 30))
            sheet_draw = ImageDraw.Draw(sheet)
            sheet_draw.text((x_pos + 10, y_pos + 8), f"{img_info['doc_type']}_{img_info['condition']}", fill=(220, 220, 220))

    # Add header/legend
    sheet.save(contact_sheet_path, quality=92)
    print(f"[TASK 1b] Contact sheet successfully generated at: {contact_sheet_path}")
    return contact_sheet_path


if __name__ == "__main__":
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    reps = run_task1a_unified_evaluations(ts)
    cs_path = run_task1b_visual_contact_sheet(ts)
    print("\nTask 1a & 1b completed successfully.")
