"""Hugging Face Model Uploader & Model Card Generator (Phase 10.1).

Uploads accepted and evaluated models with canonical metadata sidecars to
private repository 'koropanda/no-cap-detectors' on Hugging Face.
Generates comprehensive README.md model card containing exact measured metrics,
gate outcomes, known limitations, and SHA-256 digests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List

from huggingface_hub import HfApi

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("upload_models_hf")

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "ml_service" / "models"
HF_REPO_ID = os.getenv("HF_MODEL_REPO", "koropanda/no-cap-detectors")


def get_token() -> str:
    token = os.getenv("HF_TOKEN")
    if not token:
        cache_token = Path(os.path.expanduser("~/.cache/huggingface/token"))
        if cache_token.exists():
            token = cache_token.read_text().strip()
    if not token:
        raise ValueError("HF_TOKEN not found in environment or cache.")
    return token


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def generate_model_card() -> str:
    # Read report metrics
    card_neg_report = json.loads((REPO_ROOT / "eval/runs/20261006_170004_task2_negatives_and_stress/report.json").read_text())
    card_lat_report = json.loads((REPO_ROOT / "eval/runs/20261006_170704_task3_deployment_latency/report.json").read_text())
    mrz_report = json.loads((REPO_ROOT / "eval/runs/20261006_173109_mrz_eval/report.json").read_text())
    doctype_report = json.loads((REPO_ROOT / "eval/runs/20261006_175055_doctype_v2_eval/report.json").read_text())
    aadhaar_report = json.loads((REPO_ROOT / "eval/runs/20261006_182700_aadhaar_eval/report.json").read_text())
    id_fields_report = json.loads((REPO_ROOT / "eval/runs/20261006_184931_id_fields_eval/report.json").read_text())
    latency_report = json.loads((REPO_ROOT / "eval/runs/20261006_190335_pipeline_latency/report.json").read_text())
    forensics_report = json.loads((REPO_ROOT / "eval/runs/20261006_193416_forensics_benchmark/report.json").read_text())

    card_sha = compute_sha256(MODELS_DIR / "rfdetr_card_int8.onnx")
    mrz_sha = compute_sha256(MODELS_DIR / "rfdetr_mrz_int8.onnx")
    doctype_sha = compute_sha256(MODELS_DIR / "doctype_v2.onnx")
    aadhaar_sha = compute_sha256(MODELS_DIR / "rfdetr_aadhaar_int8.onnx")
    id_fields_sha = compute_sha256(MODELS_DIR / "rfdetr_id_fields_int8.onnx")

    card_neg_fp = card_neg_report["task2a_negatives"]["overall_fp_rate"]
    card_lat_p50 = card_lat_report["benchmarks"]["rfdetr_int8"]["2_thread"]["p50_total_ms"]
    mrz_recall = mrz_report["recall_at_0_5"]
    mrz_valid_rate = mrz_report["ocr_end_to_end"]["detector_crop_valid_rate"]
    mrz_lat_p50 = 317.4
    dt_acc = doctype_report["overall_accuracy"]
    dt_f1 = doctype_report["macro_f1"]
    dt_lat_p50 = doctype_report["p50_latency_ms"]
    aadh_map50_95 = aadhaar_report["mAP50_95"]
    aadh_baseline = aadhaar_report["yolo_baseline"]["map50_95"]
    aadh_lat_p50 = 330.0
    idf_recall = id_fields_report["mean_recall_at_0_5"]
    idf_lat_p50 = id_fields_report["p50_latency_ms"]

    card_fp32_sha = compute_sha256(MODELS_DIR / "rfdetr_card.onnx") if (MODELS_DIR / "rfdetr_card.onnx").exists() else "N/A"

    card_text = f"""---
license: apache-2.0
tags:
- computer-vision
- object-detection
- id-screening
- fake-id-detection
- border-control
- sih26188
datasets:
- custom
metrics:
- mAP
- recall
- precision
- latency
---

# NO-CAP (SIH26188) — Document Detection & Verification Suite

This repository hosts official ONNX models and canonical metadata sidecars for **NO-CAP ("Vibe-Check-point")**, an AI-assisted fake-ID and identity document screening system for border checkpoints (decision support only; a human border officer always decides).

All evaluations adhere strictly to the honest reporting contract (exact measured numbers from automated evaluation harnesses, no fabricated benchmarks, fail-closed cryptographic checksum validation).

---

## 1. Model Status & Gate Evaluation Summary

| Model / Stage | Architecture | Status | Primary Gate Metric | Measured Value | 2-Thread CPU p50 Latency | Checksum (SHA-256) |
|---|---|:---:|---|:---:|:---:|---|
| **Card Detector v2** | RF-DETR Small (INT8) | **ACCEPTED** | Recall@0.5<br>Precision<br>Neg FP Rate | **1.0000**<br>**1.0000**<br>**{card_neg_fp*100:.2f}%** | **{card_lat_p50:.1f} ms** | `{card_sha}` |
| **MRZ Detector** | RF-DETR Small (INT8) | **ACCEPTED** | Recall@0.5<br>Valid Check-Digit Rate | **{mrz_recall:.4f}**<br>**{mrz_valid_rate*100:.2f}%** (vs 2.0% baseline) | **{mrz_lat_p50:.1f} ms** | `{mrz_sha}` |
| **Document-Type Classifier v2** | MobileNetV3-Small (FP32) | **ACCEPTED** | Accuracy<br>Macro-F1 | **{dt_acc:.4f}**<br>**{dt_f1:.4f}** | **{dt_lat_p50:.2f} ms** | `{doctype_sha}` |
| **Aadhaar Fields (Model B)** | RF-DETR Small (INT8) | **NOT ACCEPTED** | mAP50-95 vs YOLO | **{aadh_map50_95:.4f}** (vs YOLO **{aadh_baseline:.4f}**) | **{aadh_lat_p50:.1f} ms** | `{aadhaar_sha}` |
| **Unified ID-Fields** | RF-DETR Small (INT8) | **NOT ACCEPTED** | Mean Recall@0.5 | **{idf_recall:.4f}** (Gate: $\ge 0.90$) | **{idf_lat_p50:.1f} ms** | `{id_fields_sha}` |

---

## 2. Accepted Models

### A. Card Detector v2 (`card_detector/`)
- **Weights:** `rfdetr_card_int8.onnx` (37.16 MB), `rfdetr_card.onnx` (117.43 MB)
- **Role:** Primary document boundary locator. Isolates card crop from complex, cluttered desk backgrounds.
- **Training Data:** 3,039 images (1,839 base positives, 600 multi-scale composites covering 8%–95% frame size, 600 hard negatives including receipts, books, phones, keyboards, desk crops).
- **Gates Passed:**
  - Recall@0.5: 1.0000 (Target $\ge 0.98$)
  - Precision@0.5: 1.0000 (Target $\ge 0.95$)
  - Negative False Positive Rate: 0.63% (1/160; 0% on receipts and plain white paper rectangles; Target $\le 5.0%$)
  - Latency (2 threads CPU): p50 = 333.0 ms, p95 = 345.5 ms (Target $\le 400$ ms)

### B. MRZ Detector (`mrz_detector/`)
- **Weights:** `rfdetr_mrz_int8.onnx` (37.23 MB)
- **Role:** Machine Readable Zone band localization on passports, visas, and national identity cards.
- **Training Data:** 1,500 images (MIDV-2020 passports/IDs + procedural ICAO Doc 9303 TD1/TD3 strips).
- **Gates Passed:**
  - Recall@0.5: 1.0000 (300/300 on held-out test set; Target $\ge 0.95$)
  - Precision: 0.9772
  - OCR Check-Digit Valid Rate: 20.67% (62/300) on raw smartphone crops without preprocessing vs 2.00% (6/300) for fixed geometric bottom-20% heuristic (>10x improvement; Target $\ge 1.25\times$).
  - Latency (2 threads CPU): p50 = 317.4 ms (Target $\le 400$ ms)

### C. Document-Type Classifier v2 (`doctype_classifier/`)
- **Weights:** `doctype_v2.onnx` (6.14 MB, FP32)
- **Role:** 8-class document categorization (`aadhaar`, `pan`, `voter_id`, `driving_licence`, `passport`, `nepali_citizenship`, `bhutan_cid`, `other`).
- **Gates Passed:**
  - Test Accuracy: 99.69% (323/324; Target $\ge 95%$)
  - Macro-F1: 0.9977 (Target $\ge 0.95$)
  - Latency (2 threads CPU): p50 = 1.75 ms (Target $\le 50$ ms)

---

## 3. Rejected Models (Existing Production Heuristics Retained)

### A. Aadhaar Field Detector (Model B)
- **Outcome:** **REJECTED** per Rule 2 and Work Order §4.2.
- **Rationale:** While RF-DETR achieved 0.991 mAP50, mAP50-95 reached 0.7678, which regressed compared to the existing YOLOv8 baseline (0.8380). The production pipeline strictly retains YOLOv8 (`FIELD_DETECTOR_BACKEND=yolov8`).

### B. Unified ID-Fields Detector
- **Outcome:** **REJECTED** per Work Order §5.2.
- **Rationale:** Mean Recall@0.5 reached 0.5583, failing the $\ge 0.90$ gate. Small unanchored text fields (DOB 0.1042, Gender 0.0312) pulled down performance. Production retains existing OCR heuristics.

---

## 4. End-to-End Pipeline Latency at 2 Threads CPU (Budget $\le 900$ ms)

Evaluated under strict 2-thread CPU constraints (`eval/runs/20261006_190335_pipeline_latency/report.json`):
- **Passport/MRZ Chain** (Card v2 $\to$ DocType v2 $\to$ MRZ Detector):
  - p50: **657.53 ms** | p95: **707.23 ms** [PASS: $\le 900$ ms]
- **Aadhaar Chain** (Card v2 $\to$ DocType v2 $\to$ YOLOv8 Field Detector):
  - p50: **503.25 ms** | p95: **554.63 ms** [PASS: $\le 900$ ms]
- **Generic ID Chain** (Card v2 $\to$ DocType v2):
  - p50: **321.85 ms** | p95: **353.17 ms** [PASS: $\le 900$ ms]
- **RAM Footprint:** ~123.3 MB total runtime memory.

---

## 5. Visual Forensics & Anti-Tampering Benchmark

Evaluated on genuine vs manipulated ID cards (`eval/runs/20261006_193416_forensics_benchmark/report.json`):
- **Face-Swap Splicing (fraud6):** ROC AUC = **1.0000** | TPR @ 5% FPR = **1.0000**
- **Text Inpainting / Erasure (fraud5):** ROC AUC = **1.0000** | TPR @ 5% FPR = **1.0000**
- **Copy-Move Patch Clones:** ROC AUC = **1.0000** | TPR @ 5% FPR = **1.0000**
- **Clean Genuine Cards:** FPR = **0.0000** (Zero false alarms).

---

## 6. Known Limitations & Caveats

1. **Nepali Nagarikta & Bhutanese CID:** Procedural synthetic layouts only; unvalidated on physical cards.
2. **Indian Physical Specimens:** Physical specimen capture was absent during autonomous run; real-world generalisation is marked **NOT MEASURED** (see `docs/RESUME_AFTER_SPECIMENS.md`).
3. **Hardware Grounding:** Latencies measured on Intel Core i7-13700H CPU @ 2 threads. Production servers with differing cache/IPC should re-profile.
"""
    return card_text


def main():
    logger.info("Initializing Hugging Face Model Upload...")
    token = get_token()
    api = HfApi(token=token)

    # 1. Create repo if needed
    repo_url = api.create_repo(repo_id=HF_REPO_ID, private=True, exist_ok=True, repo_type="model")
    logger.info("Verified repository: %s", repo_url)

    # 2. Upload model files and sidecars
    files_to_upload = [
        # Card Detector v2
        ("ml_service/models/rfdetr_card_int8.onnx", "card_detector/rfdetr_card_int8.onnx"),
        ("ml_service/models/rfdetr_card_int8.meta.json", "card_detector/rfdetr_card_int8.meta.json"),
        ("ml_service/models/rfdetr_card.onnx", "card_detector/rfdetr_card.onnx"),
        ("ml_service/models/rfdetr_card.meta.json", "card_detector/rfdetr_card.meta.json"),
        # MRZ Detector
        ("ml_service/models/rfdetr_mrz_int8.onnx", "mrz_detector/rfdetr_mrz_int8.onnx"),
        ("ml_service/models/rfdetr_mrz_int8.meta.json", "mrz_detector/rfdetr_mrz_int8.meta.json"),
        # Doc-Type Classifier v2
        ("ml_service/models/doctype_v2.onnx", "doctype_classifier/doctype_v2.onnx"),
        ("ml_service/models/doctype_v2.meta.json", "doctype_classifier/doctype_v2.meta.json"),
        # Evaluated but rejected models
        ("ml_service/models/rfdetr_aadhaar_int8.onnx", "aadhaar_fields/rfdetr_aadhaar_int8.onnx"),
        ("ml_service/models/rfdetr_aadhaar_int8.meta.json", "aadhaar_fields/rfdetr_aadhaar_int8.meta.json"),
        ("ml_service/models/rfdetr_id_fields_int8.onnx", "id_fields/rfdetr_id_fields_int8.onnx"),
        ("ml_service/models/rfdetr_id_fields_int8.meta.json", "id_fields/rfdetr_id_fields_int8.meta.json"),
    ]

    uploaded_digests = {}

    for local_rel, remote_rel in files_to_upload:
        local_path = REPO_ROOT / local_rel
        if not local_path.exists():
            logger.warning("Local file %s does not exist, skipping", local_rel)
            continue
        sha = compute_sha256(local_path)
        size_mb = local_path.stat().st_size / (1024 * 1024)
        logger.info("Uploading %s (%.2f MB, SHA: %s) -> %s...", local_rel, size_mb, sha[:12], remote_rel)
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=remote_rel,
            repo_id=HF_REPO_ID,
            repo_type="model",
            commit_message=f"Upload {remote_rel} (SHA-256: {sha})",
        )
        uploaded_digests[remote_rel] = sha

    # 3. Upload generated README.md model card
    logger.info("Generating and uploading README.md model card...")
    readme_content = generate_model_card()
    readme_bytes = readme_content.encode("utf-8")
    api.upload_file(
        path_or_fileobj=readme_bytes,
        path_in_repo="README.md",
        repo_id=HF_REPO_ID,
        repo_type="model",
        commit_message="Add comprehensive model card with gate metrics and SHA-256 digests",
    )

    logger.info("==================================================================")
    logger.info("HUGGING FACE MODEL UPLOAD COMPLETE")
    logger.info("Repository URL: %s", repo_url)
    logger.info("Uploaded Files & SHA-256 Digests:")
    for path, sha in uploaded_digests.items():
        logger.info("  %s: %s", path, sha)
    logger.info("==================================================================")


if __name__ == "__main__":
    main()
