# Model Cards — NO-CAP (SIH26188)

This document contains standardized model cards for all computer vision and machine learning models deployed or evaluated in the NO-CAP border checkpoint defense pipeline.

---

## Model 1: Card Boundary Detector (YOLOv8n) — Production Default

- **Model Identifier:** `card.onnx`
- **Architecture:** YOLOv8n (Ultralytics)
- **Input Resolution:** 640x640x3 RGB (normalized 0.0 - 1.0)
- **Output:** Normalized bounding box `[ymin, xmin, ymax, xmax]` + confidence
- **Quantization:** FP32 ONNX
- **File Size:** ~11.8 MB
- **Training Data:** MIDV-500, MIDV-2020, synthetic composited travel documents on diverse surfaces. Document-type clean split.
- **Performance (Clean MIDV-500 Test):**
  - Recall: **1.0000**
  - Precision: **1.0000**
  - False Positive Rate on Negatives: **0.0000** (0/160 false alarms on receipts, books, phones)
  - Latency (2 vCPU CPU): **32 ms**
- **License:** AGPL-3.0 / Research Use

---

## Model 2: Card Boundary Detector (RF-DETR INT8) — Candidate

- **Model Identifier:** `rfdetr_card_int8.onnx`
- **Architecture:** RT-DETR / RF-DETR Transformer Detector
- **Input Resolution:** 640x640x3 RGB
- **Output:** Bounding box coordinates + logits
- **Quantization:** Static INT8 (ONNX Runtime dynamic/static quant)
- **File Size:** ~29.4 MB
- **Performance:**
  - Recall: **1.0000**
  - Precision: **0.9912**
  - Negative FPR: **0.0062** (1/160)
  - Latency (2 vCPU CPU): **26 ms**
- **Evaluation Status:** Candidate stage. Retained YOLOv8 as default per Rule 7 due to comparable production metrics and established stability.

---

## Model 3: Aadhaar Field ROI Detector (YOLOv8n)

- **Model Identifier:** `aadhaar_fields.onnx`
- **Architecture:** YOLOv8n Multi-Class Object Detector
- **Input Resolution:** 640x640x3 RGB
- **Output Classes (6):** `photo`, `qr`, `aadhaar_no`, `name`, `dob`, `gender`
- **Quantization:** FP32 ONNX
- **Performance:**
  - mAP50-95: **0.838** (Validation set)
  - Inference Latency: **35 ms**
- **Evaluation Status:** **PASS** (Accepted as default field detector).

---

## Model 4: Document Type Classifier (MobileNetV3)

- **Model Identifier:** `doctype.onnx` / `doctype_v2.onnx`
- **Architecture:** MobileNetV3-Small Classifier
- **Input Resolution:** 224x224x3 RGB
- **Output Classes (6):** `aadhaar`, `driving_licence`, `other`, `pan`, `passport`, `voter_id`
- **Calibration:** Temperature scaling (T = 1.35) with review threshold at 0.75 confidence.
- **Performance:**
  - Real Aadhaar F1: **1.00**
  - Real Passport F1: **0.95**
  - Overall Macro-F1: **0.952**
  - Inference Latency: **8 ms**
- **Status:** **PASS** (Calibrated with automatic human-in-the-loop fallback).

---

## Model 5: Screen Recapture / Moiré Replay Detector

- **Model Identifier:** `app/replay_detector.py`
- **Methodology:** Dual-stream 2D-FFT high-frequency periodic peak energy (PAPR) + chromatic moiré color fringing standard deviation.
- **Input:** Document crop image bytes
- **Output:** Replay risk score (0.0–1.0) + indicator flags (`fft_peak_detected`, `moire_detected`)
- **Performance (Synthetic Recapture Benchmark):**
  - ROC AUC: **0.9284**
  - TPR @ threshold 0.63: **0.8600**
  - FPR @ threshold 0.63: **0.0600**
- **Status:** **SYNTHETIC-ONLY (PASS)**.
