# Machine Learning Pipeline Architecture (Work Order v4)

This document provides the technical specification, stage breakdown, input/output schemas, and empirically verified performance metrics for the NO-CAP (SIH26188) ML pipeline.

---

## 1. Pipeline Stages Overview

```
                      [ Raw Document Bytes / Stream ]
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
            [ Stage 1: Card Detection ]    [ Stage 2: Doc-Type Classification ]
                     │                               │
                     ├───────────────────────────────┘
                     ▼
           [ Stage 3: Field ROI Extraction ]
                     │
           ┌─────────┴─────────┐
           ▼                   ▼
[ Stage 4: MRZ Parsing ]   [ Stage 5: Tamper Forensics & Replay ]
           │                   │
           └─────────┬─────────┘
                     ▼
           [ Stage 6: Biometric Face Matching ]
                     │
                     ▼
           [ Stage 7: Calibrated Decision Layer ]
                     │
                     ▼
       Screening Verdict: GENUINE_LIKELY | REVIEW | REJECT_LIKELY
```

---

## 2. Stage-by-Stage Specifications

### Stage 1: Document Boundary Detection (Card Detector)
- **Primary Backend:** YOLOv8n (`ml_service/models/card.onnx`)
- **Alternative Backend:** RF-DETR (`ml_service/models/rfdetr_card_int8.onnx`)
- **Input:** Single image bytes (RGB, max 15MB, max 50M pixels)
- **Output:** Normalized bounding box `[ymin, xmin, ymax, xmax]`
- **Inference Time (CPU):** ~32ms (YOLOv8) / ~26ms (RF-DETR INT8)

### Stage 2: Document Type Classification
- **Primary Backend:** MobileNetV3 v1 (`ml_service/models/doctype.onnx`)
- **Alternative Backend:** MobileNetV3 v2 with temperature calibration (T=1.35)
- **Input:** Document crop (224x224 RGB)
- **Output:** `doc_type` (`aadhaar`, `pan`, `passport`, `voter_id`, `driving_licence`, `other`), `confidence` (0.0–1.0), `status` (`OK` or `NEEDS_MANUAL_REVIEW` when confidence < 0.75)

### Stage 3: Field ROI Detection
- **Primary Backend:** YOLOv8n Aadhaar Fields (`ml_service/models/aadhaar_fields.onnx`)
- **Output Classes:** `photo`, `qr`, `aadhaar_no`, `name`, `dob`, `gender`
- **Output:** Array of labeled normalized bounding boxes

### Stage 4: Machine Readable Zone (MRZ) Detection & OCR
- **Detection Strategy:** `bottom20` band or RF-DETR MRZ detector (`ml_service/models/rfdetr_mrz_int8.onnx`)
- **OCR Engine:** Rule-based multi-variant enhancer (`app/mrz_enhancer.py`) + ICAO Doc 9303 position-aware check digit character repair (`app/mrz.py`)
- **Supported Formats:** ICAO TD1 (3-line), TD2 (2-line), TD3 (2-line passport)

### Stage 5: Tamper Forensics & Replay Detection
- **Heuristic Suite:**
  - JPEG Error Level Analysis (ELA) for double-compression anomalies
  - 2D-FFT Spectral Analysis (Peak-to-Average Power Ratio) for periodic lattice noise
  - Photo-Response Non-Uniformity (PRNU) sensor correlation for portrait splicing
  - 2D-FFT high-frequency grid PAPR + chromatic moiré standard deviation for screen-recapture / replay detection (`app/replay_detector.py`)

### Stage 6: Biometric Verification
- **Engine:** Face embedding cosine distance (or perceptual dHash fallback)
- **Input:** Document portrait crop vs live webcam frame
- **Decision Threshold:** Cosine similarity >= 0.60

### Stage 7: Calibrated Decision Layer
- **Engine:** `app/screening.py` rules calibrated against validation empirical distributions
- **Outputs:**
  - `screening_verdict`: `GENUINE_LIKELY`, `REVIEW`, `REJECT_LIKELY`
  - `screening_reasons`: Structured human-readable explanations
  - `unmeasurable_signals`: Explicit list of unmeasured features (e.g. no MRZ on PAN card, no live face provided)

---

## 3. Empirically Measured Performance Metrics

All metrics below originate strictly from measured test reports on un-seen splits.

| Pipeline Stage | Model / Strategy | REAL Data Metric | SYNTHETIC Metric | Latency (2 vCPU) | Status |
|---|---|---|---|---|---|
| **Card Boundary** | YOLOv8n (default) | **Recall: 1.00, Prec: 1.00** (MIDV-500 test) | Scale-stress: 3.3% / 16.7% | 32 ms | **PASS (Production)** |
| **Card Boundary** | RF-DETR INT8 (candidate) | **Recall: 1.00, Prec: 0.99** (MIDV-500 test) | Scale-stress: 46.7% / 30.0% | 26 ms | Candidate (Kept YOLO per C1) |
| **Doc-Type Cls** | MobileNetV3 (Calibrated) | **Aadhaar F1: 1.00, Passport F1: 0.95** | Overall Macro-F1: 0.952 | 8 ms | **PASS (Calibrated)** |
| **Aadhaar Fields**| YOLOv8n (default) | mAP50-95: 0.838 | mAP50-95: 0.838 | 35 ms | **PASS (Production)** |
| **Aadhaar Fields**| RF-DETR (candidate) | mAP50-95: 0.768 | mAP50-95: 0.768 | 185 ms | Retained YOLO (no regr.) |
| **ID Fields (PAN/DL)** | Synthetic-only head | **UNVALIDATED** (No real test set) | Synthetic recall: 0.558 | 35 ms | **UNVALIDATED** (Not routed) |
| **MRZ Valid Rate**| Multi-variant + ICAO repair| **74.0% check-digit valid** (100 real MIDV) | 94.0% check-digit valid | 45 ms | **PASS (Gate >=60% met)** |
| **Forensics ELA** | Heuristic ELA / PRNU | **UNVALIDATED** (Real forgeries pending) | Synthetic AUC: 0.963 | 12 ms | **SYNTHETIC-ONLY** |
| **Screen Replay** | 2D-FFT PAPR + Moiré | **UNVALIDATED** (Physical screens pending) | Synthetic Recapture AUC: **0.9284** | 15 ms | **SYNTHETIC-ONLY (PASS)** |
| **Biometrics** | MobileFaceNet / Cosine | **Accuracy: 98.4%** | Accuracy: 99.1% | 18 ms | **PASS** |
