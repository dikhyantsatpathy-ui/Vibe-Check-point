"""Evaluation Script for MRZ Detector (Phase 3.3).

Evaluates:
1. MRZ Recall@0.5 and Precision@0.5 on held-out test documents (srb_passport, alb_id, svk_id).
2. End-to-end OCR comparison: MRZ detector crop vs baseline bottom 20% crop parsed through app/mrz.py.
3. Generates report at eval/runs/<ts>_mrz_eval/report.json.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import onnxruntime as ort
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app"))
sys.path.insert(0, str(REPO_ROOT / "eval"))

from metrics import compute_iou
from mrz import parse_mrz
from identity import _get_rapid_ocr
from yolo_roi import _run_rfdetr_onnx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def evaluate_mrz_detector():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_mrz_eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = REPO_ROOT / "ml_service" / "models" / "rfdetr_mrz_int8.onnx"
    test_dir = REPO_ROOT / "data" / "coco_mrz" / "test"
    coco_path = test_dir / "_annotations.coco.json"

    with open(coco_path, "r", encoding="utf-8") as f:
        coco = json.load(f)

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
    rapid_ocr = _get_rapid_ocr()

    anns_by_img = {}
    for a in coco["annotations"]:
        anns_by_img.setdefault(a["image_id"], []).append(a)

    total_images = len(coco["images"])
    tp_count = 0
    total_gts = 0
    total_dets = 0
    ocr_baseline_valid_count = 0
    ocr_detector_valid_count = 0

    results = []

    for img_info in coco["images"]:
        fpath = test_dir / img_info["file_name"]
        if not fpath.exists():
            continue

        with Image.open(fpath) as im:
            pil_img = im.convert("RGB")
        rgb = np.asarray(pil_img, dtype=np.uint8)
        w, h = pil_img.size

        gts = anns_by_img.get(img_info["id"], [])
        total_gts += len(gts)

        # 1. Box IoU Evaluation
        dets = _run_rfdetr_onnx(rgb, session, class_names=["MRZ"], conf_threshold=0.30)
        total_dets += len(dets)

        matched = False
        det_crop_box = None
        if dets:
            d = dets[0]
            d_box = [d["x"] * w, d["y"] * h, (d["x"] + d["w"]) * w, (d["y"] + d["h"]) * h]
            det_crop_box = d_box
            if gts:
                gt = gts[0]
                gt_box = [gt["bbox"][0], gt["bbox"][1], gt["bbox"][0] + gt["bbox"][2], gt["bbox"][1] + gt["bbox"][3]]
                iou = compute_iou(d_box, gt_box)
                if iou >= 0.50:
                    matched = True
                    tp_count += 1

        # 2. End-to-end OCR comparison
        # Method A: Baseline bottom 20% crop
        b20_crop = rgb[int(h * 0.80):, :]
        b20_valid = False
        if rapid_ocr is not None and b20_crop.size > 0:
            try:
                res, _ = rapid_ocr(b20_crop)
                if res:
                    txt = "\n".join([line[1] for line in res])
                    parsed = parse_mrz(txt)
                    if parsed.get("valid"):
                        b20_valid = True
            except Exception:
                pass
        if b20_valid:
            ocr_baseline_valid_count += 1

        # Method B: MRZ Detector Crop (with 3% padding)
        det_valid = False
        if rapid_ocr is not None:
            try:
                if det_crop_box is not None:
                    pad_x = 0.03 * (det_crop_box[2] - det_crop_box[0])
                    pad_y = 0.05 * (det_crop_box[3] - det_crop_box[1])
                    x1 = max(0, int(det_crop_box[0] - pad_x))
                    y1 = max(0, int(det_crop_box[1] - pad_y))
                    x2 = min(w, int(det_crop_box[2] + pad_x))
                    y2 = min(h, int(det_crop_box[3] + pad_y))
                    det_crop = rgb[y1:y2, x1:x2]
                else:
                    det_crop = b20_crop
                if det_crop.size > 0:
                    res, _ = rapid_ocr(det_crop)
                    if res:
                        txt = "\n".join([line[1] for line in res])
                        parsed = parse_mrz(txt)
                        if parsed.get("valid"):
                            det_valid = True
            except Exception:
                pass
        if det_valid:
            ocr_detector_valid_count += 1

        results.append({
            "image": img_info["file_name"],
            "matched": matched,
            "dets_count": len(dets),
            "baseline_valid": b20_valid,
            "detector_valid": det_valid,
        })

    recall = tp_count / max(total_gts, 1)
    precision = tp_count / max(total_dets, 1)
    baseline_valid_rate = ocr_baseline_valid_count / max(total_images, 1)
    detector_valid_rate = ocr_detector_valid_count / max(total_images, 1)

    logger.info("MRZ Evaluation: Total GTs: %d, TP: %d, Recall: %.4f, Precision: %.4f", total_gts, tp_count, recall, precision)
    logger.info("OCR Check Digits Valid: Baseline (bottom 20%%): %.2f%% (%d/%d) | Detector Crop: %.2f%% (%d/%d)",
                baseline_valid_rate * 100, ocr_baseline_valid_count, total_images,
                detector_valid_rate * 100, ocr_detector_valid_count, total_images)

    report = {
        "timestamp": ts,
        "model": "rfdetr_mrz_int8.onnx",
        "test_dataset": "data/coco_mrz/test (srb_passport, alb_id, svk_id)",
        "total_test_images": total_images,
        "total_ground_truth_mrz": total_gts,
        "true_positives": tp_count,
        "recall_at_0_5": round(recall, 4),
        "precision_at_0_5": round(precision, 4),
        "gate_recall_target": 0.95,
        "gate_recall_pass": recall >= 0.95,
        "ocr_end_to_end": {
            "baseline_bottom20_valid_rate": round(baseline_valid_rate, 4),
            "detector_crop_valid_rate": round(detector_valid_rate, 4),
            "gate_ocr_beats_baseline": detector_valid_rate >= baseline_valid_rate,
        },
        "gate_pass": (recall >= 0.95) and (detector_valid_rate >= baseline_valid_rate),
        "note": "Mock document fonts and print resolution in MIDV-2020 differ from real physical passports.",
    }

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Report written to %s", report_path)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    evaluate_mrz_detector()
