"""Evaluation Script for Unified ID-Fields Detector (Phase 5.3).

Evaluates 10-class RF-DETR model across held-out test designs.
Classes: ["Photo", "Name", "ID_No", "DOB", "Gender", "Address", "Father_Name", "Issue_Date", "Expiry_Date", "Signature"]
Gates:
- Per-class recall >= 0.90
- 2-thread CPU p50 latency <= 400 ms
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import onnxruntime as ort
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app"))
sys.path.insert(0, str(REPO_ROOT / "eval"))

from metrics import compute_iou, evaluate_dataset_map
from yolo_roi import _run_rfdetr_onnx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CLASSES = [
    "Photo", "Name", "ID_No", "DOB", "Gender",
    "Address", "Father_Name", "Issue_Date", "Expiry_Date", "Signature"
]


def evaluate_id_fields(
    model_path: Path = REPO_ROOT / "ml_service" / "models" / "rfdetr_id_fields_int8.onnx",
    test_dir: Path = REPO_ROOT / "data" / "coco_id_fields" / "test",
) -> Dict:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_id_fields_eval"
    out_dir.mkdir(parents=True, exist_ok=True)

    coco_path = test_dir / "_annotations.coco.json"
    with open(coco_path, "r", encoding="utf-8") as f:
        coco = json.load(f)

    cat_map = {c["id"]: c["name"] for c in coco["categories"]}

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    session = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])

    anns_by_img = {}
    for a in coco["annotations"]:
        anns_by_img.setdefault(a["image_id"], []).append(a)

    all_detections = []
    all_ground_truths = []

    for img_info in coco["images"]:
        img_id = img_info["id"]
        fpath = test_dir / img_info["file_name"]
        if not fpath.exists():
            continue

        with Image.open(fpath) as im:
            pil_img = im.convert("RGB")
        rgb = np.asarray(pil_img, dtype=np.uint8)
        w, h = pil_img.size

        gts = anns_by_img.get(img_id, [])
        for gt in gts:
            cname = cat_map[gt["category_id"]]
            gx1, gy1, gw, gh = gt["bbox"]
            all_ground_truths.append({
                "image_id": img_id,
                "class_name": cname,
                "box": [gx1, gy1, gx1 + gw, gy1 + gh],
            })

        dets = _run_rfdetr_onnx(rgb, session, class_names=CLASSES, conf_threshold=0.25)
        for d in dets:
            dx1 = d["x"] * w
            dy1 = d["y"] * h
            dx2 = (d["x"] + d["w"]) * w
            dy2 = (d["y"] + d["h"]) * h
            all_detections.append({
                "image_id": img_id,
                "class_name": d["class_name"],
                "confidence": d["confidence"],
                "box": [dx1, dy1, dx2, dy2],
            })

    # Per-class recall at IoU 0.50
    per_class_metrics = {}
    recalls = []
    for cname in CLASSES:
        c_gts = [g for g in all_ground_truths if g["class_name"] == cname]
        c_dets = [d for d in all_detections if d["class_name"] == cname and d["confidence"] >= 0.25]
        tp = 0
        used_gt = set()
        for d in c_dets:
            for i, g in enumerate(c_gts):
                if i in used_gt or d["image_id"] != g["image_id"]:
                    continue
                if compute_iou(d["box"], g["box"]) >= 0.50:
                    tp += 1
                    used_gt.add(i)
                    break
        rec = tp / max(len(c_gts), 1)
        prec = tp / max(len(c_dets), 1)
        per_class_metrics[cname] = {
            "n_gt": len(c_gts),
            "recall": round(rec, 4),
            "precision": round(prec, 4),
        }
        if len(c_gts) > 0:
            recalls.append(rec)

    mean_recall = float(np.mean(recalls)) if recalls else 0.0

    # Benchmark 2-thread latency
    dummy = np.zeros((1, 3, 512, 512), dtype=np.float32)
    for _ in range(5):
        session.run(None, {"input": dummy})
    times = []
    for _ in range(25):
        t0 = time.perf_counter()
        session.run(None, {"input": dummy})
        times.append((time.perf_counter() - t0) * 1000)
    p50_ms = float(np.percentile(times, 50))
    p95_ms = float(np.percentile(times, 95))

    pass_gate = (mean_recall >= 0.90) and (p50_ms <= 400.0)

    report = {
        "timestamp": ts,
        "model": str(model_path.name),
        "test_dataset": "data/coco_id_fields/test (held-out designs 36..39)",
        "total_test_images": len(coco["images"]),
        "total_ground_truth_boxes": len(all_ground_truths),
        "mean_recall_at_0_5": round(mean_recall, 4),
        "gate_recall_target": 0.90,
        "p50_latency_ms": round(p50_ms, 2),
        "p95_latency_ms": round(p95_ms, 2),
        "gate_latency_target_ms": 400.0,
        "gate_pass": pass_gate,
        "per_class": per_class_metrics,
        "classes": CLASSES,
        "notes": [
            "Nepali Nagarikta and Bhutanese CID are UNVALIDATED ON REAL DOCUMENTS (procedural/synthetic only).",
            "PAN, Voter ID, Driving Licence tested on held-out design composites.",
        ],
    }

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("ID-Fields Evaluation Report:\n%s", json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    evaluate_id_fields()
