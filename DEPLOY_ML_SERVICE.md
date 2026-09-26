# Deploying AI/ML Models for Vercel: The Complete Guide

This guide explains how to host your heavy AI/ML models (**YOLOv8 Card Locator**, **Aadhaar Field Detector**, **ArcFace Face Embeddings**, and **ViT Deepfake Forensics**) on a free external container service and link them to your live **Vercel** app with a single environment variable (`ML_SERVICE_URL`).

---

## 1. Why Host Models Externally?

| Environment | Constraint | Solution |
| :--- | :--- | :--- |
| **Vercel Serverless** | Strict **128 MB** bundle & memory limits. Deep learning binaries (`onnxruntime`, `torch`, ~600MB weights) cause build failure or function crashes. | Runs the ultra-fast web UI, database transactions, PDF parsers, and API orchestrator. |
| **External ML Service (`ml_service/`)** | Dedicated Linux container with 512 MB – 16 GB RAM and hardware optimization for ONNX / Computer Vision. | Runs YOLOv8, Aadhaar field detection, ArcFace face biometrics, and Vision Transformer AI forensics. |

The two components communicate over encrypted HTTP:
```
[User Browser / Desk] 
         │
         ▼
[Vercel Serverless (main app)]  ──(HTTPS JSON/multipart)──►  [ML Microservice (HF Spaces / Render)]
   • Web UI & Auth                                                • YOLOv8 Document & ROI Locator
   • OCR & Rules (ICAO 9303 MRZ)                                  • Aadhaar 5-Class Field Detector
   • PostgreSQL / Neon Storage                                    • ArcFace Biometric Embedding
   • Hash Ledger & Audit Chain                                    • ViT-Base AI Image Classifier
```

---

## 2. Option 1: Hugging Face Spaces (Gradio SDK — 100% Free, Zero Cost) — Recommended

Hugging Face Spaces provides **free cloud compute** with Python pre-installed. While Docker has a paid lock on some accounts, the **Gradio** SDK is **100% FREE** with ZeroGPU or CPU Basic!

We created `ml_service/app.py` which automatically mounts our FastAPI backend (`/api/ml/*`, `/health`) on Gradio!

### Step 1: Create a Space
1. Log in to [Hugging Face](https://huggingface.co/) (create a free account if you haven't).
2. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
3. Fill in:
   - **Space name**: `no-cap-ml` (or any name you like)
   - **License**: Apache 2.0
   - **Space SDK**: Select **Gradio** (Choose template: **Blank**) — **100% Free!**
   - **Space hardware**: **Free tier** (`CPU Basic` or `ZeroGPU Free`)
   - **Visibility**: **Public** (required so Vercel can reach the API)

### Step 2: Push the `ml_service` Code
You have two easy ways to push your `ml_service` code:

#### Method A: Push using Git (Direct to HF)
Hugging Face Spaces gives you a Git repository URL (e.g. `https://huggingface.co/spaces/<your-username>/no-cap-ml-service`).
Run these commands in a terminal:
```bash
# 1. Clone your empty space into a temporary folder
git clone https://huggingface.co/spaces/<your-username>/no-cap-ml-service hf_space

# 2. Copy the contents of ml_service into the space
cp -r ml_service/* hf_space/

# 3. Commit and push
cd hf_space
git add .
git commit -m "Deploy no-cap ML microservice"
git push
```

#### Method B: GitHub Action / Subtree Push
If your repository is already on GitHub:
```bash
git subtree push --prefix ml_service https://huggingface.co/spaces/<your-username>/no-cap-ml-service main
```

### Step 3: Get your Live URL
Once pushed, Hugging Face will automatically build the Docker container using `ml_service/Dockerfile`.
When the build says **Running**, your live URL is:
```
https://<your-username>-no-cap-ml-service.hf.space
```
Test it in your browser: open `https://<your-username>-no-cap-ml-service.hf.space/health` — you should see:
```json
{
  "status": "online",
  "service": "no-cap-ml-service",
  "models": {
    "yolo_card": true,
    "aadhaar_fields": true,
    "face_embed": true,
    "ai_detector": false
  }
}
```

---

## 3. Option 2: Render.com (Free Tier Docker Web Service)

Render allows deploying Docker services directly from your GitHub repository.

### Step 1: Create a Web Service
1. Log in to [dashboard.render.com](https://dashboard.render.com/).
2. Click **New +** -> **Web Service**.
3. Select **Build and deploy from a Git repository** and connect your `NO-CAP---SIH` repo.

### Step 2: Configure Service Settings
- **Name**: `no-cap-ml`
- **Region**: Choose the closest region (e.g., Singapore, Frankfurt, Oregon)
- **Branch**: `main`
- **Root Directory**: `ml_service` *(important!)*
- **Runtime**: **Docker**
- **Instance Type**: **Free**
- **Health Check Path**: `/health`

Click **Deploy Web Service**.

> [!NOTE]
> Render dynamically assigns a port via `$PORT` (typically 10000). The updated `ml_service/Dockerfile` automatically detects `$PORT` and binds to it seamlessly!

### Step 3: Get your Render URL
Your live URL will look like:
```
https://no-cap-ml.onrender.com
```

---

## 4. Link the ML Service to Vercel

Now that your ML service is running live, connect it to your main Vercel app:

1. Open your project on the [Vercel Dashboard](https://vercel.com/dashboard).
2. Go to **Settings** -> **Environment Variables**.
3. Add the following environment variable:
   - **Key**: `ML_SERVICE_URL`
   - **Value**: `https://<your-ml-service-host>`  
     *(e.g., `https://username-no-cap-ml-service.hf.space` or `https://no-cap-ml.onrender.com`)*
   - **Environments**: Check `Production`, `Preview`, and `Development`.
4. *(Optional)* Add timeout configuration if using Render free tier (which sleeps after inactivity):
   - **Key**: `ML_SERVICE_TIMEOUT`
   - **Value**: `25.0` (gives the sleeping container 25 seconds to wake up)
5. **Redeploy**: Go to **Deployments** -> click the three dots on your latest deployment -> **Redeploy** (or push a new commit to GitHub).

---

## 5. Verify Everything is Working Live

### Test 1: Health Endpoint Check
Open `https://<your-vercel-app>.vercel.app/api/health` in your browser.
Look for the `ml_service` section:
```json
{
  "status": "ok",
  "service": "SSB Border Screening Desk (SIH26188)",
  "ml_service": {
    "configured": true,
    "url": "https://<your-ml-service-host>"
  }
}
```

### Test 2: Live Desk Screening Pass
1. Open your Vercel web app.
2. Select any specimen document from the dropdown (e.g. Aadhaar Card, Passport, or PAN Card).
3. Click **Screen Identity Document**.
4. Check the results:
   - **Document Boundaries & ROI**: The document preview canvas overlays real green bounding boxes for `document`, `photo`, `signature`, `qr_code`, and `mrz_zone` detected by YOLOv8.
   - **Aadhaar Field Recognition**: Shows detected coordinates for `Aadhaar_No`, `DOB`, `Gender`, `Name`, and `Photo`.
   - **Face Match**: Shows **onnx-embedding** method with ArcFace cosine similarity score (e.g. `cosine 0.84: same person`).
   - **AI Forensics**: Shows **Self-hosted ViT-Base (CIFAKE fine-tune)** with confidence score and class logits.

---

## 6. Cold-Start & Offline Resilience

If your free ML service ever sleeps or is temporarily unreachable:
- The main Vercel app **never crashes or returns a 500 error**.
- It logs a diagnostic warning in your Vercel runtime logs (`Remote ML service call failed ... Falling back to local`).
- It seamlessly falls back to pure-Python heuristics (perceptual dHash face comparison, chromatic skin/contrast zone detection, and heuristic image analysis).
- Once the ML container wakes up, subsequent passes automatically use the full deep learning models!
