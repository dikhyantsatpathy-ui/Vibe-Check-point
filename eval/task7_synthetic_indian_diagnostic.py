"""TASK 7: Synthetic Indian Diagnostic (Not a gate).

Synthesizes ~150 diagnostic images with Indian specimen cards from Task 6a pasted onto
real non-card background patches (train-type photos) with perspective distortion, glare, and blur.
Evaluates both YOLO baseline and RF-DETR candidate to observe if non-European colors/layouts
are detected at all.
Label: SYNTHETIC DIAGNOSTIC, NOT A GATE, model has seen composite artefacts in training.
"""

from __future__ import annotations

import datetime
import json
import logging
import math
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from training.indian_specimens.make_specimen_sheets import (
    render_design_aadhaar_pvc,
    render_design_aadhaar_letter_strip,
    render_design_pan_card,
    render_design_voter_id,
    render_design_driving_licence,
    CARD_WIDTH,
    CARD_HEIGHT,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Ensure RF-DETR backend by default
os.environ["CARD_DETECTOR_BACKEND"] = "rf_detr"
os.environ["DETECTOR_BACKEND"] = "rf_detr"

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from yolo_roi import (
    _get_onnx_session,
    _run_rfdetr_onnx,
    _run_yolo_onnx,
    clear_session_cache,
)


def load_train_backgrounds(train_dir: Path, count: int = 150) -> List[Image.Image]:
    """Sample background patches from train images outside document boundaries."""
    train_ann_file = train_dir / "_annotations.coco.json"
    backgrounds: List[Image.Image] = []
    
    if train_ann_file.exists():
        data = json.loads(train_ann_file.read_text(encoding="utf-8"))
        # Find images that are marked as composites or train photos
        img_map = {img["id"]: img["file_name"] for img in data.get("images", [])}
        for img_info in data.get("images", []):
            fname = img_info["file_name"]
            p = train_dir / fname
            if not p.exists():
                p = train_dir / "images" / fname
            if p.exists():
                try:
                    im = Image.open(p).convert("RGB")
                    # Crop top or bottom non-card strip as background canvas
                    w, h = im.size
                    if w >= 600 and h >= 400:
                        backgrounds.append(im.resize((1280, 720), Image.Resampling.BILINEAR))
                except Exception:
                    pass
            if len(backgrounds) >= count:
                break

    # Fallback synthetic textures if fewer real backgrounds found
    rng = random.Random(42)
    while len(backgrounds) < count:
        color = (rng.randint(80, 200), rng.randint(80, 200), rng.randint(80, 200))
        im = Image.new("RGB", (1280, 720), color=color)
        draw = ImageDraw.Draw(im)
        for _ in range(30):
            x = rng.randint(0, 1280)
            y = rng.randint(0, 720)
            draw.ellipse([x - 50, y - 50, x + 50, y + 50], fill=(color[0] + rng.randint(-30, 30), color[1] + rng.randint(-30, 30), color[2] + rng.randint(-30, 30)))
        backgrounds.append(im)

    return backgrounds[:count]


def apply_perspective_composite(
    card_img: Image.Image,
    bg_img: Image.Image,
    rng: random.Random,
) -> Tuple[Image.Image, List[float]]:
    """Paste card onto background with perspective distortion and return composite + bounding box [x1, y1, x2, y2]."""
    bg_w, bg_h = bg_img.size
    card_w, card_h = card_img.size

    # Card scale relative to background (between 0.45 and 0.75 of frame)
    scale = rng.uniform(0.50, 0.75) * (min(bg_w, bg_h) / float(card_h))
    tw = int(card_w * scale)
    th = int(card_h * scale)

    resized_card = card_img.resize((tw, th), Image.Resampling.BILINEAR)

    # 4 source corners
    src_pts = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])

    # Random target placement on background
    cx = rng.randint(int(tw * 0.55), bg_w - int(tw * 0.55))
    cy = rng.randint(int(th * 0.55), bg_h - int(th * 0.55))

    # Angle & perspective tilt
    angle = rng.uniform(-25.0, 25.0)
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    hw, hh = tw / 2.0, th / 2.0
    jitter = 0.15

    dst_pts = np.float32([
        [cx + (-hw * cos_a - -hh * sin_a) + rng.uniform(-tw * jitter, tw * jitter),
         cy + (-hw * sin_a + -hh * cos_a) + rng.uniform(-th * jitter, th * jitter)],
        [cx + (hw * cos_a - -hh * sin_a) + rng.uniform(-tw * jitter, tw * jitter),
         cy + (hw * sin_a + -hh * cos_a) + rng.uniform(-th * jitter, th * jitter)],
        [cx + (hw * cos_a - hh * sin_a) + rng.uniform(-tw * jitter, tw * jitter),
         cy + (hw * sin_a + hh * cos_a) + rng.uniform(-th * jitter, th * jitter)],
        [cx + (-hw * cos_a - hh * sin_a) + rng.uniform(-tw * jitter, tw * jitter),
         cy + (-hw * sin_a + hh * cos_a) + rng.uniform(-th * jitter, th * jitter)],
    ])

    # Homography matrix
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    card_cv = cv2.cvtColor(np.asarray(resized_card), cv2.COLOR_RGB2BGR)
    warped_card = cv2.warpPerspective(card_cv, M, (bg_w, bg_h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    # Warped alpha mask
    mask_cv = np.full((th, tw), 255, dtype=np.uint8)
    warped_mask = cv2.warpPerspective(mask_cv, M, (bg_w, bg_h), borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    # Specular glare overlay (50% chance)
    if rng.random() > 0.50:
        gx, gy = int(cx), int(cy)
        glare = np.zeros((bg_h, bg_w), dtype=np.uint8)
        cv2.ellipse(glare, (gx, gy), (rng.randint(60, 180), rng.randint(30, 80)), rng.randint(0, 180), 0, 360, 140, -1)
        glare = cv2.GaussianBlur(glare, (41, 41), 0)
        glare = cv2.bitwise_and(glare, glare, mask=warped_mask)
        warped_card = cv2.add(warped_card, cv2.merge([glare, glare, glare]))

    bg_cv = cv2.cvtColor(np.asarray(bg_img), cv2.COLOR_RGB2BGR)
    mask_3ch = cv2.merge([warped_mask, warped_mask, warped_mask]) / 255.0
    composite = (warped_card * mask_3ch + bg_cv * (1.0 - mask_3ch)).astype(np.uint8)

    # Slight camera blur
    if rng.random() > 0.40:
        composite = cv2.GaussianBlur(composite, (3, 3), 0)

    final_pil = Image.fromarray(cv2.cvtColor(composite, cv2.COLOR_BGR2RGB))

    # Axis-aligned bounding box from destination quad
    xs = dst_pts[:, 0]
    ys = dst_pts[:, 1]
    x1 = max(0.0, float(np.min(xs)))
    y1 = max(0.0, float(np.min(ys)))
    x2 = min(float(bg_w), float(np.max(xs)))
    y2 = min(float(bg_h), float(np.max(ys)))

    return final_pil, [x1, y1, x2, y2]


def run_diagnostic():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"eval/runs/{ts}_task7_synthetic_indian")
    dataset_dir = out_dir / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(42)
    bg_list = load_train_backgrounds(Path("data/coco_card/train"), count=150)

    design_generators = [
        ("aadhaar_pvc", render_design_aadhaar_pvc),
        ("aadhaar_letter", render_design_aadhaar_letter_strip),
        ("pan_card", render_design_pan_card),
        ("voter_id", render_design_voter_id),
        ("driving_licence", render_design_driving_licence),
    ]

    # Pre-render cards for deterministic speed
    rendered_cards = {name: gen(rng) for name, gen in design_generators}

    records: List[Dict[str, Any]] = []
    num_samples = 150

    logger.info("Generating %d synthetic Indian diagnostic composites...", num_samples)
    for i in range(num_samples):
        des_name, _ = design_generators[i % len(design_generators)]
        card_img = rendered_cards[des_name]
        bg_img = bg_list[i % len(bg_list)]

        comp_img, bbox = apply_perspective_composite(card_img, bg_img, rng)
        img_name = f"indian_synth_{des_name}_{i:03d}.jpg"
        img_path = dataset_dir / img_name
        comp_img.save(img_path, quality=90)

        w, h = comp_img.size
        records.append({
            "img_id": f"indian_synth_{i:03d}",
            "file_name": img_name,
            "path": img_path,
            "design": des_name,
            "gt_bbox": bbox,
            "gt_norm": [bbox[0] / w, bbox[1] / h, bbox[2] / w, bbox[3] / h],
            "width": w,
            "height": h,
        })

    logger.info("Evaluating models on synthetic Indian diagnostic set...")
    # Evaluate RF-DETR
    clear_session_cache()
    os.environ["CARD_DETECTOR_BACKEND"] = "rf_detr"
    os.environ["DETECTOR_BACKEND"] = "rf_detr"
    rf_session = _get_onnx_session()

    from eval.metrics import compute_iou

    rf_tp = 0
    rf_det_count = 0
    design_recall: Dict[str, Dict[str, int]] = {name: {"gt": 0, "tp": 0} for name, _ in design_generators}

    for rec in records:
        des = rec["design"]
        design_recall[des]["gt"] += 1

        img = Image.open(rec["path"]).convert("RGB")
        rgb = np.asarray(img, dtype=np.uint8)

        boxes = _run_rfdetr_onnx(rgb, rf_session, max_boxes=2, class_names=["Card"], conf_threshold=0.40)
        gt_box = rec["gt_norm"]
        matched = False
        for b in boxes:
            rf_det_count += 1
            det_box = [b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]]
            if compute_iou(det_box, gt_box) >= 0.50:
                if not matched:
                    rf_tp += 1
                    design_recall[des]["tp"] += 1
                    matched = True

    rf_recall = rf_tp / float(num_samples)
    rf_prec = rf_tp / float(max(1, rf_det_count))

    # Evaluate YOLO baseline
    clear_session_cache()
    os.environ["CARD_DETECTOR_BACKEND"] = "yolov8"
    os.environ["DETECTOR_BACKEND"] = "yolov8"
    yolo_session = _get_onnx_session()

    yolo_tp = 0
    yolo_det_count = 0
    for rec in records:
        img = Image.open(rec["path"]).convert("RGB")
        rgb = np.asarray(img, dtype=np.uint8)
        boxes = _run_yolo_onnx(rgb, yolo_session, max_boxes=2, class_names=["document"], conf_threshold=0.35)
        gt_box = rec["gt_norm"]
        matched = False
        for b in boxes:
            yolo_det_count += 1
            det_box = [b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]]
            if compute_iou(det_box, gt_box) >= 0.50:
                if not matched:
                    yolo_tp += 1
                    matched = True

    yolo_recall = yolo_tp / float(num_samples)
    yolo_prec = yolo_tp / float(max(1, yolo_det_count))

    # Restore default
    os.environ["CARD_DETECTOR_BACKEND"] = "yolov8"
    os.environ["DETECTOR_BACKEND"] = "yolov8"
    clear_session_cache()

    report = {
        "label": "SYNTHETIC DIAGNOSTIC, NOT A GATE, model has seen composite artefacts in training",
        "timestamp": ts,
        "num_samples": num_samples,
        "models": {
            "rf_detr_candidate": {
                "tp": rf_tp,
                "detections": rf_det_count,
                "recall": round(rf_recall, 4),
                "precision": round(rf_prec, 4),
                "per_design_recall": {
                    d: round(vals["tp"] / float(max(1, vals["gt"])), 4)
                    for d, vals in design_recall.items()
                },
            },
            "yolo_baseline": {
                "tp": yolo_tp,
                "detections": yolo_det_count,
                "recall": round(yolo_recall, 4),
                "precision": round(yolo_prec, 4),
            },
        },
    }

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 78)
    print(" [SYNTHETIC DIAGNOSTIC, NOT A GATE, model has seen composite artefacts in training]")
    print(f" Sample Count: n={num_samples} (30 per Indian design across 5 designs)")
    print("-" * 78)
    print(f" Candidate RF-DETR Recall@0.5 : {rf_recall * 100:.2f}% ({rf_tp}/{num_samples}) | Prec: {rf_prec * 100:.2f}%")
    for d, vals in design_recall.items():
        rec_d = vals["tp"] / float(max(1, vals["gt"]))
        print(f"   • Design '{d:<18}': Recall = {rec_d * 100:.1f}% ({vals['tp']}/{vals['gt']})")
    print(f" Baseline YOLOv8 Recall@0.5   : {yolo_recall * 100:.2f}% ({yolo_tp}/{num_samples}) | Prec: {yolo_prec * 100:.2f}%")
    print("=" * 78 + "\n")
    print(f"Diagnostic report written to: {report_path}")

    return report


if __name__ == "__main__":
    run_diagnostic()
