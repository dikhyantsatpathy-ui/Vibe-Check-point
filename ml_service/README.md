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
| **Card Detector v2** | RF-DETR Small INT8 (`rfdetr_card_int8.onnx`) | Apache 2.0 | **ACCEPTED.** Recall@0.5: 1.0000, Precision: 1.0000, Hard Negative FP: 0.63% (1/160; 0% on receipts & plain paper). Latency (2 threads CPU): p50 = 333.0 ms (`eval/runs/20261006_171449_card_v2_eval/report.json`). |
| **Card Detector (Baseline)** | YOLOv8s (`card.onnx`) | AGPL-3.0 | **Baseline.** Evaluated on synthetic mockups. Retained for full rollback compatibility. |
| **MRZ Detector** | RF-DETR Small INT8 (`rfdetr_mrz_int8.onnx`) | Apache 2.0 | **ACCEPTED.** Recall@0.5: 1.0000, Valid OCR check-digit rate: 20.67% vs bottom20 baseline 2.00% (>10x improvement). Latency (2 threads CPU): p50 = 317.4 ms (`eval/runs/20261006_173109_mrz_eval/report.json`). |
| **Document-Type Classifier v2** | MobileNetV3-Small FP32 (`doctype_v2.onnx`) | Apache 2.0 | **ACCEPTED.** 8 classes. Accuracy: 99.69%, Macro-F1: 0.9977. Latency (2 threads CPU): p50 = 1.75 ms (`eval/runs/20261006_175055_doctype_v2_eval/report.json`). |
| **Aadhaar Field Detector (Model B)** | RF-DETR Small INT8 (`rfdetr_aadhaar_int8.onnx`) | Apache 2.0 | **REJECTED.** Regressed on mAP50-95 (0.7678 vs YOLO baseline 0.8380). Production pipeline retains 5-class YOLOv8 (`aadhaar_fields.onnx`). |
| **Unified ID-Fields Detector** | RF-DETR Small INT8 (`rfdetr_id_fields_int8.onnx`) | Apache 2.0 | **REJECTED.** Recall@0.5 was 0.5583 (failed $\ge 0.90$ gate). Production pipeline retains existing OCR heuristics. |
| **Facial Biometrics** | ArcFace / InsightFace (`w600k_r50.onnx`) | MIT / Permissive | 512-D cosine face embedding & age-aware thresholding. SHA-256 pinned. |
| **AI Image Detection** | ViT-Base CIFAKE Fine-Tuned (`model.onnx`) | Apache 2.0 | Discriminates synthetic / generative AI portrait fakes. SHA-256 pinned. |
| **Visual Forensics Suite** | SRM ResNet + ELA + 2D-FFT PAPR + Clone Matcher | Apache 2.0 | Multi-algorithm suite evaluated on genuine vs manipulated ID cards: AUC = 1.0000 across face-swap, inpainting, and copy-move (`eval/runs/20261006_193416_forensics_benchmark/report.json`). |

---

## 2. API Endpoints

All POST endpoints require the shared secret header `X-ML-Secret-Key`. If `ML_SECRET_KEY` is unset, the service fails closed with `HTTP 503` unless `ML_ALLOW_NO_AUTH=true` is explicitly configured for local development.

### Core Endpoints
- `GET /health` — Service readiness, endpoint registry, and model checkpoint presence.
- `POST /api/ml/yolo_roi` — Document card boundary and ROI extraction (normalized `[x, y, w, h]`). Returns additive provenance fields: `stage: "card"`, `card_backend`, `field_backend`, `effective_backend`, and `backend`.
- `POST /api/ml/aadhaar_fields` — 5-class semantic field zone detection. Returns additive field tags: `stage: "field"`, `effective_backend`.
- `POST /api/ml/face_match` — Compares document portrait crop (Base64) against live webcam frame (`live_frame` upload).
- `POST /api/ml/detect_image` — Vision Transformer classification for AI-generated / deepfake imagery.
- `POST /api/ml/doctype` — Visual document type classification (Passport, Aadhaar, PAN, Voter ID, DL, etc.).
- `POST /api/ml/doc_forgery` — SRM residual noise seam and tampering analysis.

### Mixed-Media & In-Memory Processing Endpoints
- `POST /api/ml/media/process_pdf` — In-memory PDF digital signature structural inspection and multi-tier rasterization.
- `POST /api/ml/media/process_live_photo` — Slices embedded MP4 burst from Motion Photos, normalizes primary still image, and analyzes inter-frame micro-motion delta.

---

## 3. Configuration & Environment Variables

| Variable | Default | Allowed Values | Purpose |
|:---|:---:|:---:|:---|
| `DETECTOR_BACKEND` | `yolov8` | `yolov8`, `rf_detr` | Master default detector backend switch. |
| `CARD_DETECTOR_BACKEND` | `yolov8` | `yolov8`, `rf_detr` | Stage 1 (card boundary localization) switch. |
| `FIELD_DETECTOR_BACKEND` | `yolov8` | `yolov8`, `rf_detr` | Stage 2 (Aadhaar field extraction) switch. Retains `yolov8`. |
| `MRZ_DETECTOR_BACKEND` | `bottom20` | `bottom20`, `rf_detr` | MRZ band detector switch. |
| `DOCTYPE_BACKEND` | `v1` | `v1`, `v2` | Document-type classifier backend switch (`v2` = 8-class MobileNetV3). |
| `HF_MODEL_REPO` | `koropanda/no-cap-detectors` | string | Target private repository for fetching weights at startup. |
| `HF_TOKEN` | *(secret)* | string | Hugging Face access token for private model repository access. |
| `ML_SECRET_KEY` | `""` | string | Shared authentication secret enforced via `X-ML-Secret-Key` header. |
| `ML_ALLOW_NO_AUTH` | `false` | `true`, `false` | Explicit opt-in for unauthenticated local testing. |
| `ALLOWED_ORIGINS` | `https://vibe-check-point.vercel.app,...` | URLs | Allowed CORS origins. |
| `ENABLE_CARD_RECTIFICATION` | `false` | `true`, `false` | Enable homography perspective warp to canonical CR-80 card ratio (1000x630). |
| `PREWARM_MODELS` | `true` | `true`, `false` | Pre-warm ONNX sessions on startup to eliminate cold-start latency spikes. |

### Immediate Rollback Procedure
If any operational anomaly occurs:
```bash
export DETECTOR_BACKEND="yolov8"
export CARD_DETECTOR_BACKEND="yolov8"
export FIELD_DETECTOR_BACKEND="yolov8"
export MRZ_DETECTOR_BACKEND="bottom20"
export DOCTYPE_BACKEND="v1"
```
Or invoke `clear_session_cache()` in Python. The system instantly reverts to baseline YOLOv8 + geometric heuristics.

---

## 4. Model Weights Supply-Chain & Hugging Face Repository

Model weights and canonical metadata sidecars are hosted in the private repository [`koropanda/no-cap-detectors`](https://huggingface.co/koropanda/no-cap-detectors):

| Model File | Size | SHA-256 Checksum | Sidecar Path |
|:---|:---:|:---|:---|
| `rfdetr_card_int8.onnx` | 37.16 MB | `ccab01630e53389387738a5af0c9456fb1aa6f3d68e3a0f1128ebe78b7f6b179` | `ml_service/models/rfdetr_card_int8.meta.json` |
| `rfdetr_card.onnx` (FP32) | 117.43 MB | `3c0209185d095e8dee05b122536dbe565f675f3f05dee1c056245177ac4190a3` | `ml_service/models/rfdetr_card.meta.json` |
| `rfdetr_mrz_int8.onnx` | 37.23 MB | `3c597ee3e6f96615b3a4a0dbff1e01f09cb8b512c1451f28b2be7fa222c8c6a2` | `ml_service/models/rfdetr_mrz_int8.meta.json` |
| `doctype_v2.onnx` | 6.14 MB | `0953a992cfd8350567e972f3fa143717df305d2c67feea93e3d489b4f74d081b` | `ml_service/models/doctype_v2.meta.json` |
| `card.onnx` (YOLO) | 21.5 MB | `c1c9c8e1e79ee883e0e7a2b9e6443a9d949437a3c3c78a101fce0d86b9eaeb79` | `ml_service/models/card.onnx` |
| `aadhaar_fields.onnx` | 21.5 MB | `295a7065963f25c78673a968600118eb13c41551a141a5dffca3428d0111ef6c` | `ml_service/models/aadhaar_fields.onnx` |

The startup loader (`ml_service/model_fetch.py`) verifies the SHA-256 checksum against the canonical sidecar before initializing any session. Any tampered or corrupted weights file causes an immediate fail-closed error.

---

## 5. Hugging Face Space Deployment

1. Create a Space on Hugging Face:
   - **SDK**: `Docker` or `Gradio`
   - **Hardware**: CPU Basic (Free) or 2 vCPU
2. In Space **Settings $\rightarrow$ Variables and Secrets**:
   - Add `HF_TOKEN` (fine-grained token with read access to `koropanda/no-cap-detectors`).
   - Add `HF_MODEL_REPO="koropanda/no-cap-detectors"`.
   - Add `ML_SECRET_KEY` (secret string matching `ML_SERVICE_SECRET` on Vercel).
   - Set `CARD_DETECTOR_BACKEND="rf_detr"`, `MRZ_DETECTOR_BACKEND="rf_detr"`, `DOCTYPE_BACKEND="v2"`.
3. Connect the Space URL to the Vercel backend via:
   ```bash
   ML_SERVICE_URL="https://<your-username>-<your-space-name>.hf.space"
   ML_SERVICE_SECRET="<your-secret-key>"
   ```


