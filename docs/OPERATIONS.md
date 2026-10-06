# Operational Guide: Deployment, Rollback, and Maintenance (Work Order v4)

This runbook details operational procedures for running, monitoring, deploying, rolling back, and extending the NO-CAP (SIH26188) screening platform.

---

## 1. Local & Production Deployment

### Option A: Local Bare-Metal / Development
```bash
# 1. Activate environment
source .venv/bin/activate  # Or on Windows: .venv\Scripts\Activate.ps1

# 2. Start ML Microservice (Port 8001)
export ML_SECRET_KEY="production-secret-token"
export ML_PORT=8001
uvicorn ml_service.main:app --host 0.0.0.0 --port 8001 --workers 2

# 3. Start Core Screening App (Port 8000)
export ML_SERVICE_URL="http://localhost:8001"
export ML_SECRET_KEY="production-secret-token"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Option B: Docker Container Deployment
The ML service can be packaged into an isolated OCI container:
```bash
# Build the ML service container
docker build -t nocap-ml-service:v4 -f ml_service/Dockerfile .

# Run with resource limits (2 vCPU, 2GB RAM)
docker run -d \
  --name nocap-ml \
  --cpus 2 \
  --memory 2g \
  -p 8001:8001 \
  -e ML_SECRET_KEY="production-secret-token" \
  nocap-ml-service:v4
```

### Option C: Hugging Face Space (Private Microservice)
1. Create a private Hugging Face Space (SDK: Docker).
2. Push repository with `ml_service/Dockerfile` as the root Dockerfile.
3. In Space Settings -> Secrets, configure `ML_SECRET_KEY` and `HF_TOKEN`.
4. Point the main FastAPI app by setting:
   ```env
   ML_SERVICE_URL=https://<your-username>-no-cap-ml.hf.space
   ML_SECRET_KEY=<your-secret-key>
   ```

---

## 2. Zero-Downtime Rollback Procedure

If any anomaly occurs with new candidate backends (`rf_detr` or `v2`), the entire system can be reverted instantaneously via a single environment variable change:

### Instant Rollback to Proven YOLOv8 Baseline:
```bash
# One-line rollback: restores baseline YOLOv8 and v1 classifiers across all stages
export DETECTOR_BACKEND=yolov8
export CARD_DETECTOR_BACKEND=yolov8
export FIELD_DETECTOR_BACKEND=yolov8
export DOCTYPE_BACKEND=v1
```

Restart the service process or container. The `/ml/health` endpoint will immediately verify:
```json
{
  "status": "online",
  "stages": {
    "card": { "effective_backend": "yolov8", "loaded": true },
    "field": { "effective_backend": "yolov8", "loaded": true },
    "doctype": { "effective_backend": "v1", "loaded": true }
  }
}
```

---

## 3. How to Add a New Document Type

To add support for a new bilateral or international travel document (e.g. Bhutan Work Permit, SAARC Visa):

1. **Register Document Type:**
   Add entry to `DOCUMENT_CATALOG` in `app/config.py`:
   ```python
   "bhutan_permit": {
       "label": "Bhutan Entry/Work Permit",
       "category": "bilateral",
       "has_mrz": False,
       "hint": "Check immigration seal and expiry date"
   }
   ```

2. **Add Identifier Validation & Checksums:**
   In `app/validation.py`, add format regex and mathematical checksum validators.

3. **Update Guided Screening Protocol:**
   In `app/config.py:guided_steps`, define the officer verification and traveller instruction steps.

4. **Retrain Doc-Type Classifier:**
   Add sample scans to `data/raw_doctypes/bhutan_permit/`, re-run `training/train_doctype.py`, and export ONNX model to `ml_service/models/doctype_v2.onnx`.
