---
title: No Cap ML Microservice
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
---

# NO-CAP ML Microservice (SIH26188 Border Screening AI)

High-performance computer vision, biometric authentication, and document forensics microservice for the NO-CAP Border Screening Desk. Deployed as a dedicated Hugging Face Space or Docker container, completely decoupling heavy neural inference from the serverless Vercel frontend.

---

## 1. Supported Neural Models & Backends

| Model Component | Architecture / Checkpoint | License | Status & Measured Performance |
|:---|:---|:---:|:---|
| **Card Detector (Candidate)** | RF-DETR Small INT8 (`rfdetr_card_int8.onnx`) | Apache 2.0 | **Evaluated.** MIDV-2020 test set mAP50: 1.000, Recall: 1.000 (Report: `eval/runs/20261006_094311_audit_rfdetr_int8/eval_report.json`). Latency (2 threads CPU): p50 = 335.8 ms (Report: `eval/runs/20261006_100236_task3_latency/latency_report.json`). |
| **Card Detector (Baseline)** | YOLOv8s (`card.onnx`) | AGPL-3.0 | **Evaluated.** Trained on synthetic 2D mockups (`card_synth`). Real MIDV-2020 test set mAP50: 0.000, Recall: 0.000 (Report: `eval/runs/20261006_094311_audit_yolo/eval_report.json`). Synthetic-to-real domain gap. |
| **Field Zone Detector** | 5-Class YOLOv8s (`aadhaar_fields.onnx`) | AGPL-3.0 | **Frozen.** Trained on `data/AADHAR`. Isolates `Aadhaar_No`, `DOB`, `Gender`, `Name`, `Photo`. **Model B not retrained.** *Note: AGPL-3.0 copyleft persists for field detector even in hybrid mode.* |
| **Facial Biometrics** | ArcFace / InsightFace (`w600k_r50.onnx`) | MIT / Permissive | 512-D cosine face embedding & age-aware thresholding. SHA-256 pinned. |
| **AI Image Detection** | ViT-Base CIFAKE Fine-Tuned (`model.onnx`) | Apache 2.0 | Discriminates synthetic / generative AI portrait fakes. SHA-256 pinned. |
| **Document Forgery** | Dual-Stream SRM ResNet (`doctype.onnx`) | Apache 2.0 | Spatial noise residuals & dead-block seam detection. |

> **Important Licensing Note on Hybrid Mode**: Operating in hybrid mode (`CARD_DETECTOR_BACKEND=rf_detr`, `FIELD_DETECTOR_BACKEND=yolov8`) replaces the card detector with Apache 2.0 code, but because field detection remains backed by `aadhaar_fields.onnx` (YOLOv8), **hybrid mode does NOT eliminate AGPL-3.0 copyleft obligations** for the overall service. Full AGPL elimination requires training an Apache 2.0 field detector.

---

## 2. API Endpoints

All POST endpoints require the shared secret header `X-ML-Secret-Key`. If `ML_SECRET_KEY` is unset, the service fails closed with `HTTP 503` unless `ML_ALLOW_NO_AUTH=true` is explicitly configured for local development.

### Core Endpoints
- `GET /health` — Service readiness, endpoint registry, and model checkpoint presence.
- `POST /api/ml/yolo_roi` — Document card boundary and ROI extraction (normalized `[x, y, w, h]`). Returns additive provenance fields: `stage: "card"`, `card_backend`, `field_backend`, `effective_backend`, and `backend`.
- `POST /api/ml/aadhaar_fields` — 5-class semantic field zone detection. Returns additive field tags: `stage: "field"`, `effective_backend`.
- `POST /api/ml/face_match` — Compares document portrait crop (Base64) against live webcam frame (`live_frame` upload).
- `POST /api/ml/detect_image` — Vision Transformer classification for AI-generated / deepfake imagery.
- `POST /api/ml/doctype` — Visual document type classification (Passport, Aadhaar, PAN, Voter ID, DL).
- `POST /api/ml/doc_forgery` — SRM residual noise seam and tampering analysis.

### Mixed-Media & In-Memory Processing Endpoints
- `POST /api/ml/media/process_pdf` — In-memory PDF digital signature structural presence inspection (`/ByteRange`, `/SubFilter`, signer name, signing timestamp; note: does not verify cryptographic certificate chain) and multi-tier vector/embedded page rasterization.
- `POST /api/ml/media/process_live_photo` — Slices embedded MP4 burst from Google/Apple Motion Photos, normalizes the primary still image, and analyzes inter-frame micro-motion delta for physiological liveness (experimental).

---

## 3. Configuration & Environment Variables

| Variable | Default | Allowed Values | Purpose |
|:---|:---:|:---:|:---|
| `DETECTOR_BACKEND` | `yolov8` | `yolov8`, `rf_detr` | Global default detector backend. |
| `CARD_DETECTOR_BACKEND` | *(inherits `DETECTOR_BACKEND`)* | `yolov8`, `rf_detr` | Stage 1 (card boundary localization) backend switch. |
| `FIELD_DETECTOR_BACKEND` | *(inherits `DETECTOR_BACKEND`)* | `yolov8`, `rf_detr` | Stage 2 (field extraction) backend switch. Note: `rf_detr` field model not yet trained; setting to `rf_detr` fails loudly. |
| `RF_DETR_ONNX_PATH` | `models/rfdetr_card_int8.onnx` | file path | Path to RF-DETR ONNX weights. Verified against sidecar SHA-256 before inference. |
| `CARD_THRESHOLDS_PATH` | *(none / default)* | JSON file path | Optional external per-class confidence thresholds JSON file. |
| `ML_SECRET_KEY` | `""` | string | Shared authentication secret enforced via `X-ML-Secret-Key` header (fail-closed if unset). |
| `ML_ALLOW_NO_AUTH` | `false` | `true`, `false` | Explicit opt-in for unauthenticated local development. |
| `ALLOWED_ORIGINS` | `https://vibe-check-point.vercel.app,...` | comma-separated URLs | Allowed CORS origins. |
| `ENABLE_CARD_RECTIFICATION` | `false` | `true`, `false` | Enable homography perspective warp to canonical CR-80 card ratio (1000x630). |
| `PREWARM_MODELS` | `true` | `true`, `false` | Pre-warm ONNX sessions on startup to eliminate cold-start latency spikes. |
| `AI_DETECTOR_MODEL_SHA256` | `44cb205f...` | hex string | Pinned SHA-256 supply-chain verification hash for ViT model. |
| `FACE_MODEL_SHA256` | `4c06341c...` | hex string | Pinned SHA-256 supply-chain verification hash for ArcFace model. |

### Immediate Rollback Procedure
If any operational anomaly occurs with the candidate model:
```bash
export DETECTOR_BACKEND="yolov8"
export CARD_DETECTOR_BACKEND="yolov8"
export FIELD_DETECTOR_BACKEND="yolov8"
```
Or call `clear_session_cache()` in Python. The system instantly reverts to legacy YOLOv8 inference without restarting the container.

---

## 4. Model Weights Supply-Chain & Hugging Face Upload

Large `.onnx` model weights are strictly **git-ignored** to prevent repository bloat and comply with open-source licensing guidelines. Model weights are pinned via SHA-256 in `<model>.meta.json` sidecars:

| Model File | Size | SHA-256 Checksum | Sidecar Path |
|:---|:---:|:---|:---|
| `rfdetr_card_int8.onnx` | 31.2 MB | `2f6269fba9b9deb74ec81c6cae3f5856812c18d39a09e9d0571ef4f0624e008a` | `ml_service/models/rfdetr_card_int8.meta.json` |
| `rfdetr_card.onnx` (FP32) | 117.5 MB | `65f81e834888c459066ea6f3251fbe18b2c585a1555274e170f36b520b92575f` | `ml_service/models/rfdetr_card.meta.json` |
| `card.onnx` (YOLO) | 21.5 MB | `c1c9c8e1e79ee883e0e7a2b9e6443a9d949437a3c3c78a101fce0d86b9eaeb79` | `ml_service/models/card.onnx` |
| `aadhaar_fields.onnx` | 21.5 MB | `295a7065963f25c78673a968600118eb13c41551a141a5dffca3428d0111ef6c` | `ml_service/models/aadhaar_fields.onnx` |

### Publishing Weights to Hugging Face
To distribute model weights without committing them to Git:
```bash
# 1. Install huggingface_hub CLI
pip install huggingface_hub

# 2. Login to Hugging Face with write token
huggingface-cli login

# 3. Upload weights to dedicated model repository
huggingface-cli upload <organization>/nocap-card-detector ml_service/models/rfdetr_card_int8.onnx rfdetr_card_int8.onnx
huggingface-cli upload <organization>/nocap-card-detector ml_service/models/rfdetr_card.onnx rfdetr_card.onnx
```

The loader verifies the SHA-256 checksum at startup before initializing any ONNX runtime session. If a file is tampered with or corrupted, the loader fails closed immediately.

---

## 5. Test Set Scope & Measured Limitations

### Empirical Test Set Characteristics
- **Dataset**: MIDV-2020 held-out test split (300 photos total: 100 Albanian ID, 100 Slovakian ID, 100 Greek Passport).
- **Structure**: Exactly **one large card per photograph**, centered or occupying majority of the frame, captured across 8 physical conditions.
- **Negatives**: The core test set contains **0 negative images** (photos without cards).
- **Geography & Demographics**: The test set contains **only European mock documents**. Non-Indian layouts, scripts, and colors.
- **Indian-layout performance**: **NOT MEASURED** on real physical captures. Specimen test kit was generated in `training/indian_specimens/out/indian_specimen_sheets_300dpi.pdf` pending physical field photography.
- **Synthetic Indian Diagnostic (Not a Gate)**: On 150 synthetic perspective/glare composites of Indian specimen cards on background patches (`eval/runs/20261006_102938_task7_synthetic_indian/report.json`), RF-DETR achieved 93.33% recall (140/150) and 82.84% precision, whereas YOLOv8 achieved 0.00% recall.
- **Negative & Clutter Evaluation**: On a synthetic negative set of 160 non-card images (background crops, receipt-like paper, colored shapes; `eval/runs/20261006_095642_task2/report.json`), RF-DETR had an overall false-positive rate of 18.12% (background crops: 6.00%, non-card paper/shapes: 100%), failing the provisional $\le 5\%$ gate. This highlights that RF-DETR triggers proposals on high-contrast card-sized rectangular paper.
- **Scale Stress Diagnostic**: Padding test photos with 2x canvas reduced recall to 65.33%; 3x canvas reduced recall to 20.67%, showing sensitivity to small cards in distant frames.

---

## 6. Zero-Storage Invariant & Privacy Compliance

In strict compliance with the **Digital Personal Data Protection Act, 2023 (DPDP)**:
- **Zero Raw Storage**: Uploaded files, PDF pages, portrait crops, and video bursts are processed entirely in volatile RAM buffers (`io.BytesIO`).
- **Immediate Scrubbing**: Any temporary decoding handles are scrubbed in `finally:` blocks. No PII or raw pixels are logged or written to persistent disk.
- **Explainable Verdicts**: Models provide decision support for border officers; unreadable inputs or timeouts degrade gracefully to `REVIEW` with clear explainability, never autonomous `CLEAR`.

---

## 7. Hugging Face Space Deployment

1. Create a new Space on Hugging Face:
   - **SDK**: `Gradio` or `Docker`
   - **Hardware**: CPU Basic (Free) or ZeroGPU
2. In Space **Settings $\rightarrow$ Variables and Secrets**:
   - Add `ML_SECRET_KEY` (secret string matching `ML_SERVICE_SECRET` on Vercel).
   - Set `DETECTOR_BACKEND` (`yolov8` or `rf_detr`).
3. Connect the Space URL to the Vercel backend via:
   ```bash
   ML_SERVICE_URL="https://<your-username>-<your-space-name>.hf.space"
   ML_SERVICE_SECRET="<your-secret-key>"
   ```


