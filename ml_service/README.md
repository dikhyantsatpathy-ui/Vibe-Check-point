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

| Model Component | Architecture / Weights | License | Primary Function |
|:---|:---|:---:|:---|
| **Card Detector** | YOLOv8s (`card.onnx`) / RF-DETR (`rf_detr.onnx`) | Apache 2.0 / AGPL-3.0 | Card boundary localization & aspect-ratio normalization. |
| **Field Zone Detector** | 5-Class YOLO (`aadhaar_fields.onnx`) | Apache 2.0 | Isolates `Aadhaar_No`, `DOB`, `Gender`, `Name`, `Photo`. |
| **Facial Biometrics** | ArcFace / InsightFace (`w600k_r50.onnx`) | MIT / Permissive | 512-D cosine face embedding & age-aware thresholding. |
| **AI Image Detection** | ViT-Base CIFAKE Fine-Tuned (`model.onnx`) | Apache 2.0 | Discriminates synthetic / generative AI portrait fakes. |
| **Document Forgery** | Dual-Stream SRM ResNet (`doctype.onnx`) | Apache 2.0 | Spatial noise residuals & dead-block seam detection. |

---

## 2. API Endpoints

All POST endpoints require the shared secret header `X-ML-Secret-Key` when `ML_SECRET_KEY` is configured in the environment.

### Core Endpoints
- `GET /health` — Service readiness, endpoint registry, and model checkpoint presence.
- `POST /api/ml/yolo_roi` — Document card boundary and ROI extraction (normalized `[x, y, w, h]`).
- `POST /api/ml/aadhaar_fields` — 5-class semantic field zone detection.
- `POST /api/ml/face_match` — Compares document portrait crop (Base64) against live webcam frame (`live_frame` upload).
- `POST /api/ml/detect_image` — Vision Transformer classification for AI-generated / deepfake imagery.
- `POST /api/ml/doctype` — Visual document type classification (Passport, Aadhaar, PAN, Voter ID, DL).
- `POST /api/ml/doc_forgery` — SRM residual noise seam and tampering analysis.

### Mixed-Media & In-Memory Processing Endpoints (Phase 4)
- `POST /api/ml/media/process_pdf` — In-memory PDF digital signature inspection (`/ByteRange`, `/SubFilter /adbe.pkcs7.detached`, signer name, signing timestamp) and multi-tier vector/embedded page rasterization.
- `POST /api/ml/media/process_live_photo` — Slices embedded MP4 burst from Google/Apple Motion Photos, normalizes the primary still image, and analyzes inter-frame micro-motion delta for physiological liveness.

---

## 3. Configuration & Environment Variables

| Variable | Default | Purpose |
|:---|:---:|:---|
| `ML_SECRET_KEY` | `""` | Shared authentication secret enforced via `X-ML-Secret-Key`. |
| `ALLOWED_ORIGINS` | `https://vibe-check-point.vercel.app,...` | Comma-separated list of allowed CORS origins. |
| `DETECTOR_BACKEND` | `yolov8` | Switchable detector backend: `"yolov8"` or `"rf_detr"` (Apache 2.0). |
| `ENABLE_CARD_RECTIFICATION` | `false` | Enable homography perspective warp to canonical CR-80 card ratio (1000x630). |
| `PREWARM_MODELS` | `true` | Pre-warm ONNX sessions on startup to eliminate cold-start latency spikes. |
| `AI_DETECTOR_MODEL_SHA256` | `44cb205f...` | Pinned SHA-256 supply-chain verification hash for ViT model. |
| `FACE_MODEL_SHA256` | `4c06341c...` | Pinned SHA-256 supply-chain verification hash for ArcFace model. |

---

## 4. Zero-Storage Invariant & Privacy Compliance

In strict compliance with the **Digital Personal Data Protection Act, 2023 (DPDP)**:
- **Zero Raw Storage**: Uploaded files, PDF pages, portrait crops, and video bursts are processed entirely in volatile RAM buffers (`io.BytesIO`).
- **Immediate Scrubbing**: Any temporary decoding handles are scrubbed in `finally:` blocks. No PII or raw pixels are logged or written to persistent disk.
- **Explainable Verdicts**: Models provide decision support for border officers; unreadable inputs or timeouts degrade gracefully to `REVIEW` with clear explainability, never autonomous `CLEAR`.

---

## 5. Hugging Face Space Deployment

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
