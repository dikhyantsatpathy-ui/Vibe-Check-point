# NO-CAP (SIH26188) — AUDIT V5 FINDINGS REGISTER

This document is the single source of truth for all audit findings across Work Order v5.
Severity rules:
- **S1 (Critical)**: Secret exposure, auth bypass, data leak, or any path that can auto-clear a traveller.
- **S2 (High)**: Wrong or unreproducible headline metric used for a go/no-go.
- **S3 (Medium)**: Missing test, logic defect, or weak control.
- **S4 (Low)**: Hygiene, documentation, or minor inconsistency.

Status values: `OPEN`, `FIXED`, `ACCEPTED-RISK`, `BLOCKED`.

| ID | Severity | Area | Evidence Path | Status | Fix Commit | Description |
|---|---|---|---|---|---|---|
| F-001 | S3 | ML Backend / Fail-safe | eval/runs/20261007_064553_env/pytest_baseline.txt | OPEN | | `_default_model_path()` in `yolo_roi.py` falls back to `yolov8n.onnx` when `DETECTOR_BACKEND=rf_detr` and RF-DETR weights are missing instead of failing loud with `""`. |
| F-002 | S2 | Eval / Truth Audit | eval/run_all.py:L38-51 | OPEN | | `eval/run_all.py` hardcoded card detector metrics (recall 1.0, precision 1.0) and marked "PASS" rather than computing real model inference metrics. |
