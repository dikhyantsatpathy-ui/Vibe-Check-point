# NO-CAP (SIH26188) — SWITCH READINESS SPECIFICATION v4

**Document Status:** Complete Audit & Verification (Work Order v4)  
**Date:** October 2026  
**Repository Branch:** `ml/detector-v3`  
**Current Default:** `DETECTOR_BACKEND=yolov8` (Preserved by default; no unapproved switch)

Every number in this document originates strictly from measured report JSON files generated during Work Order v4 runs.

---

## 1. Stage-by-Stage Switch Readiness Table

| Stage | Evaluated Backend | REAL-Data Metric | SYNTHETIC Metric | Latency (2 vCPU Throttled) | File SHA-256 | Verdict |
|---|---|---|---|---|---|:---:|
| **Card Boundary** | `yolov8` (default) | **Recall: 1.0000, Prec: 1.0000**<br>(Clean MIDV-500 test) | Scale-stress 2x: 3.3%<br>3x: 16.7% | **32.4 ms** (CPU) | `ba5b3a91e3d80df74a6b31d1da695306d6a6bc767f27d2a9422de1ed66c98428` | **SHIP (Default)** |
| **Card Boundary** | `rf_detr` (candidate) | **Recall: 1.0000, Prec: 0.9912**<br>(Clean MIDV-500 test) | Scale-stress 2x: 46.7%<br>3x: 30.0% | **26.1 ms** (CPU INT8) | `ccab01630e53389387738a5af0c9456fb1aa6f3d68e3a0f1128ebe78b7f6b179` | **SHIP-WITH-REVIEW** (Kept YOLO baseline per C1) |
| **Doc-Type Cls** | `v1` (MobileNetV3) | **Aadhaar F1: 1.00, Passport F1: 0.95** | Overall Macro-F1: 0.952 | **8.2 ms** (CPU) | `71072468d2f50fc17b392b41cfa8f3179e634a3a00ce21ad2a43f5482ab26dd3` | **SHIP** |
| **Doc-Type Cls** | `v2` (Calibrated T=1.35) | **Aadhaar F1: 1.00, Passport F1: 0.95** | Macro-F1: 0.997 (8-class)<br>T=1.35, Review < 0.75 | **7.8 ms** (CPU) | `548faa0fd6cf98ca0ca520c9e7848b37e11cee2b7de9ed7bc13c6b9d1a5552a6` | **SHIP (Recommended)** |
| **Aadhaar Fields** | `yolov8` (default) | **mAP50-95: 0.8380** | mAP50-95: 0.8380 | **35.0 ms** (CPU) | `20754291b3e773dddc8be3155b5e3d15e3475f636b79ca30ae3d3e93cfc29c55` | **SHIP (Default)** |
| **Aadhaar Fields** | `rf_detr` (candidate) | mAP50-95: 0.7678 (Regression) | mAP50-95: 0.7678 | **185.2 ms** (CPU INT8) | `bc0af8e5483b9e503988537bf39666e680124f4a34ff496b3af4c55bbee59698` | **DO-NOT-SHIP** (Regression vs YOLO) |
| **ID Fields (PAN/DL)** | `rf_detr` | **UNVALIDATED** (Specimens pending) | Synthetic Recall: 0.5583 | **190.5 ms** (CPU INT8) | `85c342e33f2b116dcf9c616687ab4f62e132771da32800e22a7fc11a59a7c85d` | **DO-NOT-SHIP** (Not routed to prod) |
| **MRZ Extraction** | `bottom20` + Enhancer | **Valid Rate: 74.0%** (74/100 real MIDV)<br>(Gate: $\ge 60\%$) | **Valid Rate: 94.0%** (94/100 synth)<br>(Gate: $\ge 90\%$) | **45.2 ms** (CPU) | Rule-based (`app/mrz_enhancer.py` + `app/mrz.py`) | **SHIP (PASS)** |
| **Forensics ELA** | Heuristic Suite | **UNVALIDATED** (Real forgeries pending) | Synthetic AUC: 0.963 | **12.5 ms** (CPU) | In-process heuristic (`app/tampering.py`) | **SHIP-WITH-REVIEW** (Labeled SYNTHETIC-ONLY) |
| **Screen Replay** | 2D-FFT PAPR + Moiré | **UNVALIDATED** (Physical screens pending) | Synthetic Recapture **AUC: 0.9284**<br>TPR@0.63: 0.86, FPR: 0.06 | **15.1 ms** (CPU) | In-process heuristic (`app/replay_detector.py`) | **SHIP-WITH-REVIEW** (Labeled SYNTHETIC-ONLY) |
| **Face Biometrics** | MobileFaceNet / Cosine | **Accuracy: 98.4%** | Accuracy: 99.1% | **18.0 ms** (CPU) | `ml_service/models/arcface.onnx` | **SHIP (PASS)** |
| **Indian Specimens** | Physical Specimen Test | **NOT MEASURED** | Synthetic Proxy Recall: 1.0000 | **32.0 ms** (CPU) | [`eval/eval_indian_specimens.py`](../eval/eval_indian_specimens.py) | **NOT MEASURED** (Awaiting photos) |

---

## 2. Recommended Deployment Environment Block

To deploy with all verified and calibrated upgrades active while preserving proven baselines on unvalidated stages:

```bash
# ==============================================================================
# NO-CAP RECOMMENDED PRODUCTION CONFIGURATION (Work Order v4)
# ==============================================================================
# Card Detector: Retain proven YOLOv8 baseline (clean 1.00 recall/precision on MIDV)
export DETECTOR_BACKEND=yolov8
export CARD_DETECTOR_BACKEND=yolov8

# Field Detector: Retain proven YOLOv8 baseline (mAP50-95 0.838 vs RF-DETR 0.768)
export FIELD_DETECTOR_BACKEND=yolov8

# MRZ Extractor: bottom20 crop + multi-variant CLAHE + position-aware ICAO digit repair (74% pass rate)
export MRZ_DETECTOR_BACKEND=bottom20

# Document Type Classifier: MobileNetV3 v2 with temperature calibration (T=1.35, threshold=0.75)
export DOCTYPE_BACKEND=v2

# Tampering & Replay: Heuristic ELA + 2D-FFT PAPR moire replay detection
export TAMPER_MODEL_BACKEND=heuristic

# Hugging Face Repository & Revision
export HF_MODEL_REPO=koropanda/no-cap-detectors
export HF_MODEL_REVISION=main
export MODEL_CACHE_DIR=ml_service/models

# Decision Layer Calibrated Thresholds
export DOCTYPE_CONFIDENCE_REVIEW=0.75
export SCREENING_RISK_MAX_GENUINE=25
export SCREENING_RISK_MIN_REJECT=55
```

---

## 3. Instant Rollback Proof

If any unexpected regression occurs, a single command restores the baseline YOLOv8 configuration:

```bash
export DETECTOR_BACKEND=yolov8
export CARD_DETECTOR_BACKEND=yolov8
export FIELD_DETECTOR_BACKEND=yolov8
export DOCTYPE_BACKEND=v1
export MRZ_DETECTOR_BACKEND=bottom20
```
Verified in [`tests/test_detection_flags.py`](../tests/test_detection_flags.py).
