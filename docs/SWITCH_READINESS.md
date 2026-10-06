# NO-CAP (SIH26188) — SWITCH READINESS CHECKLIST

**Document Status:** Complete Audit & Verification  
**Date:** October 2026  
**Repository Branch:** `ml/detector-v3`  
**Current Default:** `DETECTOR_BACKEND=yolov8` (Preserved by default; no automatic switch)

This checklist provides the decision-support evaluation required before any production switch from YOLOv8 to RF-DETR / MobileNetV3 backends. Every claim and metric is grounded strictly in evidence files generated during autonomous test-suite runs.

---

## 1. Gate & Readiness Checklist

| Checklist Item | Status | Measured Metric / Gate Target | Evidence File Path | Notes / Rationale |
|---|:---:|---|---|---|
| **Card Detector v2: Positive Recall** | [x] PASS | **Recall@0.5: 1.0000**<br>(Gate: $\ge 0.98$) | [`eval/runs/20261006_171449_card_v2_eval/report.json`](../eval/runs/20261006_171449_card_v2_eval/report.json) | 600/600 multi-scale positive cards localized. |
| **Card Detector v2: Precision** | [x] PASS | **Precision: 1.0000**<br>(Gate: $\ge 0.95$) | [`eval/runs/20261006_171449_card_v2_eval/report.json`](../eval/runs/20261006_171449_card_v2_eval/report.json) | Zero spurious false card boxes. |
| **Card Detector v2: Hard Negative FP Rate** | [x] PASS | **FP Rate: 0.63%** (1/160)<br>(Gate: $\le 5.0%$) | [`eval/runs/20261006_171449_card_v2_eval/report.json`](../eval/runs/20261006_171449_card_v2_eval/report.json) | 0% FP on store receipts & plain paper rectangles. Single border case on tablet screen. |
| **Card Detector v2: Scale Generalization** | [x] PASS | **Scale Coverage: 8%–95%** | [`eval/runs/20261006_171449_card_v2_eval/report.json`](../eval/runs/20261006_171449_card_v2_eval/report.json) | Multi-scale composites correctly bounded across distance extremes. |
| **Indian Specimen Validation** | [ ] NOT MEASURED | **Physical Specimen Test: NOT MEASURED** | [`docs/RESUME_AFTER_SPECIMENS.md`](RESUME_AFTER_SPECIMENS.md) | `data/indian_specimens_photos/` was absent. Printable 300 DPI specimen sheets generated. |
| **MRZ Detector Gate** | [x] PASS | **Recall@0.5: 1.0000**<br>**Valid OCR: 20.67%** (vs 2.0% baseline) | [`eval/runs/20261006_173109_mrz_eval/report.json`](../eval/runs/20261006_173109_mrz_eval/report.json) | >10x gain in end-to-end check-digit valid rate on raw passport phone photos. |
| **Document-Type Classifier Gate** | [x] PASS | **Accuracy: 99.69%**<br>**Macro-F1: 0.9977** (Gate: $\ge 0.95$) | [`eval/runs/20261006_175055_doctype_v2_eval/report.json`](../eval/runs/20261006_175055_doctype_v2_eval/report.json) | 8-class MobileNetV3-Small (FP32). 323/324 test images correct. |
| **Aadhaar Field Detector (Model B)** | [ ] REJECTED | **mAP50-95: 0.7678** (vs YOLO **0.8380**)<br>(Gate: Non-regression on mAP50-95) | [`eval/runs/20261006_182700_aadhaar_eval/report.json`](../eval/runs/20261006_182700_aadhaar_eval/report.json) | FAILED gate. Retain YOLOv8 (`FIELD_DETECTOR_BACKEND=yolov8`). |
| **Unified ID-Fields Detector** | [ ] REJECTED | **Mean Recall@0.5: 0.5583**<br>(Gate: $\ge 0.90$) | [`eval/runs/20261006_184931_id_fields_eval/report.json`](../eval/runs/20261006_184931_id_fields_eval/report.json) | FAILED gate. Retain existing OCR heuristics. |
| **End-to-End Latency: Passport/MRZ** | [x] PASS | **p50: 657.53 ms**<br>(Budget: $\le 900$ ms) | [`eval/runs/20261006_190335_pipeline_latency/report.json`](../eval/runs/20261006_190335_pipeline_latency/report.json) | 2 CPU threads: Card v2 $\to$ DocType v2 $\to$ MRZ Detector. |
| **End-to-End Latency: Aadhaar** | [x] PASS | **p50: 503.25 ms**<br>(Budget: $\le 900$ ms) | [`eval/runs/20261006_190335_pipeline_latency/report.json`](../eval/runs/20261006_190335_pipeline_latency/report.json) | 2 CPU threads: Card v2 $\to$ DocType v2 $\to$ YOLOv8 Field Detector. |
| **End-to-End Latency: Generic ID** | [x] PASS | **p50: 321.85 ms**<br>(Budget: $\le 900$ ms) | [`eval/runs/20261006_190335_pipeline_latency/report.json`](../eval/runs/20261006_190335_pipeline_latency/report.json) | 2 CPU threads: Card v2 $\to$ DocType v2. |
| **Visual Forensics Benchmark** | [x] PASS | **AUC = 1.0000** on face-swap, inpainting, copy-move | [`eval/runs/20261006_193416_forensics_benchmark/report.json`](../eval/runs/20261006_193416_forensics_benchmark/report.json) | Multi-algorithm forensics passes $> 0.70$ gate; no learned patch classifier required. |
| **Parity & Cryptographic SHA Pins** | [x] PASS | SHA-256 sidecars validated fail-closed | [`ml_service/models/`](../ml_service/models/) | Canonical metadata sidecars match all model weights. |
| **Weights Uploaded to Hugging Face** | [x] PASS | Private repository active | `https://huggingface.co/koropanda/no-cap-detectors` | INT8 weights, FP32, sidecars, and generated model card. |
| **Full Pytest Suite Status** | [x] PASS | **285 passed, 3 skipped, 0 failed** | Test run logs (`task-5146`) | 100% passing across all unit, integration, and drift tests. |
| **Rollback Capability** | [x] PASS | Verified with `DETECTOR_BACKEND=yolov8` | [`tests/test_detection_flags.py`](../tests/test_detection_flags.py) | Unsetting flags retains clean YOLOv8 baseline without regressions. |

---

## 2. Recommendation for Owner

- **Recommended Stance:** **HYBRID SWITCH**
  1. **Enable Card Detector v2** (`CARD_DETECTOR_BACKEND=rf_detr`): Substantially reduces negative false-alarm rate (0.63% vs baseline 3.75%) and covers wide-angle scale ranges.
  2. **Enable MRZ Detector** (`MRZ_DETECTOR_BACKEND=rf_detr`): Delivers >10x valid OCR check-digit improvements for passport/travel documents.
  3. **Enable Doc-Type Classifier v2** (`DOCTYPE_BACKEND=v2`): Provides 99.69% accuracy across 8 classes in 1.75 ms.
  4. **Retain YOLOv8 for Aadhaar Fields** (`FIELD_DETECTOR_BACKEND=yolov8`): Do NOT switch to RF-DETR for Aadhaar fields due to mAP50-95 regression.
  5. **Global Default Remains `yolov8`**: Until the owner explicitly tests and signs off on the physical Indian specimens, keep default `DETECTOR_BACKEND=yolov8`.
