import io
import os
import sys
import time
import logging
import urllib.request
import numpy as np
from PIL import Image
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from typing import Optional

logger = logging.getLogger("ml_service")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from yolo_roi import extract_roi_boxes
from face_match import compare_faces

app = FastAPI(title="ML Microservice")

# --- Security: Shared-Secret Authentication (Finding C1) ---
_API_KEY_HEADER = APIKeyHeader(name="X-ML-Secret-Key", auto_error=False)


def verify_ml_auth(x_ml_secret_key: Optional[str] = Security(_API_KEY_HEADER)):
    expected = (os.getenv("ML_SECRET_KEY") or "").strip()
    if not expected:
        if os.getenv("ML_ALLOW_NO_AUTH", "").strip().lower() == "true":
            logger.warning(
                "[auth] ML_SECRET_KEY unset. Request permitted because ML_ALLOW_NO_AUTH=true is explicitly set."
            )
            return True
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML microservice auth not configured: ML_SECRET_KEY is required (or set ML_ALLOW_NO_AUTH=true for local dev).",
        )
    if not x_ml_secret_key or x_ml_secret_key.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing X-ML-Secret-Key",
        )
    return True


# --- Security: CORS Origin Restriction (Finding C2) ---
_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if not _allowed_origins:
    _allowed_origins = [
        "https://vibe-check-point.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- ONNX AI Image Detection Code (from core app) ---
MODEL_REPO = "onnx-community/ai-image-detection-ONNX"
MODEL_FILE = "model.onnx"
DEFAULT_URL = f"https://huggingface.co/{MODEL_REPO}/resolve/main/onnx/model.onnx"
DEFAULT_AI_DETECTOR_SHA256 = "44cb205f596f7c9e13d9ea7ea12cb2462d7c92bfaeb55e7fcad51b5c4943fcf3"
_IMG_SIZE = 224

_engine = None

def _model_dir() -> str:
    return os.getenv("AI_DETECTOR_MODEL_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "models")

def _model_path() -> str:
    url = os.getenv("AI_DETECTOR_MODEL_URL")
    if url:
        return os.path.join(_model_dir(), url.rstrip("/").split("/")[-1])
    local = os.path.join(_model_dir(), MODEL_FILE)
    for cand in (local, os.path.join(_model_dir(), "pytorch_model.onnx")):
        if os.path.exists(cand):
            return cand
    return local

def _ensure_model() -> str:
    path = _model_path()
    if os.path.exists(path):
        return path
    os.makedirs(_model_dir(), exist_ok=True)
    url = os.getenv("AI_DETECTOR_MODEL_URL") or DEFAULT_URL
    print(f"[detector] downloading AI model -> {path}  ({url})")
    tmp = path + ".download"
    import hashlib
    hasher = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(tmp, "wb") as out:
        while chunk := resp.read(65536):
            hasher.update(chunk)
            out.write(chunk)
    digest = hasher.hexdigest()
    expected = os.getenv("AI_DETECTOR_MODEL_SHA256", DEFAULT_AI_DETECTOR_SHA256).strip().lower()
    if expected and digest.lower() != expected:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise ValueError(f"Supply-chain check failed: AI detector SHA-256 {digest} != expected {expected}")
    os.replace(tmp, path)
    return path

def _load_engine():
    global _engine
    if _engine is not None:
        return _engine
    import onnxruntime as ort
    path = _ensure_model()
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    _engine = ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])
    return _engine

def _preprocess(img_bytes: bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = img.resize((_IMG_SIZE, _IMG_SIZE))
    a = np.asarray(img, dtype=np.float32) / 255.0
    x = a.transpose(2, 0, 1)[None, ...]
    return x

def onnx_score(output) -> int:
    try:
        out = np.asarray(output)
        logits = out.reshape(-1)
        if logits.size < 2:
            return 0
        e = np.exp(logits - logits.max())
        probs = e / e.sum()
        ai_prob = float(probs[1])
        return int(round(max(0.0, min(100.0, ai_prob * 100.0))))
    except Exception:
        return 0

def onnx_detect(image_bytes: bytes) -> dict:
    try:
        _load_engine()
    except Exception as exc:
        return {
            "ran": False, "ai_suspected": False, "ai_score": 0,
            "model": "Self-hosted ViT (AI vs Real)", "provider": "self-hosted",
            "explanation": f"Model failed to start: {exc.__class__.__name__}",
            "latency_ms": 0, "raw": None,
        }
    start = time.perf_counter()
    try:
        x = _preprocess(image_bytes)
        session = _load_engine()
        input_name = session.get_inputs()[0].name
        output = session.run(None, {input_name: x})[0]
        ms = int((time.perf_counter() - start) * 1000)
        score = onnx_score(output)
        is_ai = score >= 50
        return {
            "ran": True,
            "ai_suspected": is_ai,
            "ai_score": score,
            "model": "Self-hosted ViT-Base (CIFAKE fine-tune)",
            "provider": "self-hosted",
            "explanation": (
                f"The on-device Vision Transformer classified this image as "
                f"{'AI-GENERATED' if is_ai else 'not clearly AI'} with {score}% confidence."),
            "latency_ms": ms,
            "raw": {"logits": [float(x) for x in np.asarray(output).reshape(-1)[:2]]},
        }
    except Exception as exc:
        ms = int((time.perf_counter() - start) * 1000)
        return {
            "ran": False, "ai_suspected": False, "ai_score": 0,
            "model": "Self-hosted ViT (AI vs Real)", "provider": "self-hosted",
            "explanation": f"Failed on this image ({exc.__class__.__name__}).",
            "latency_ms": ms, "raw": None,
        }

# --- API Endpoints ---

@app.get("/")
@app.get("/health")
def health_check():
    models_dir = _model_dir()
    face_model = (
        os.path.exists(os.path.join(models_dir, "w600k_r50.onnx"))
        or os.path.exists(os.path.abspath(os.path.join(models_dir, "..", "..", "data", "models", "w600k_r50.onnx")))
        or bool(os.getenv("FACE_EMBED_MODEL"))
    )
    return {
        "status": "online",
        "service": "no-cap-ml-service",
        "endpoints": [
            "/health",
            "/api/ml/yolo_roi",
            "/api/ml/aadhaar_fields",
            "/api/ml/face_match",
            "/api/ml/detect_image",
            "/api/ml/doctype",
            "/api/ml/doc_forgery",
            "/api/ml/media/process_pdf",
            "/api/ml/media/process_live_photo",
        ],
        "models": {
            "yolo_card": os.path.exists(os.path.join(models_dir, "card.onnx")),
            "aadhaar_fields": os.path.exists(os.path.join(models_dir, "aadhaar_fields.onnx")),
            "doctype": os.path.exists(os.path.join(models_dir, "doctype.onnx")),
            "face_embed": face_model,
            "ai_detector": os.path.exists(_model_path()),
        },
    }


@app.on_event("startup")
def startup_prewarm():
    if os.getenv("PREWARM_MODELS", "true").lower() in ("1", "true", "yes"):
        print("[ml_service] Pre-warming ONNX models on startup...")
        try:
            from yolo_roi import _get_onnx_session, _get_aadhaar_session
            _get_onnx_session()
            _get_aadhaar_session()
            print("[ml_service] Pre-warm complete.")
        except Exception as exc:
            print(f"[ml_service] Pre-warm note: {exc}")


@app.post("/api/ml/yolo_roi", dependencies=[Depends(verify_ml_auth)])
async def api_yolo_roi(file: UploadFile = File(...)):
    data = await file.read()
    boxes = extract_roi_boxes(data)
    return boxes


from yolo_roi import extract_aadhaar_fields
@app.post("/api/ml/aadhaar_fields", dependencies=[Depends(verify_ml_auth)])
async def api_aadhaar_fields(file: UploadFile = File(...)):
    data = await file.read()
    boxes = extract_aadhaar_fields(data)
    return boxes


@app.post("/api/ml/face_match", dependencies=[Depends(verify_ml_auth)])
async def api_face_match(
    doc_face_b64: str = Form(...),
    live_frame: UploadFile = File(...),
    doc_age_years: Optional[float] = Form(None),
    emb_same: Optional[float] = Form(None)
):
    live_bytes = await live_frame.read()
    result = compare_faces(doc_face_b64, live_bytes, doc_age_years, emb_same)
    return result


@app.post("/api/ml/detect_image", dependencies=[Depends(verify_ml_auth)])
async def api_detect_image(file: UploadFile = File(...)):
    data = await file.read()
    result = onnx_detect(data)
    return result


from doctype_cls import classify_document
@app.post("/api/ml/doctype", dependencies=[Depends(verify_ml_auth)])
async def api_doctype(file: UploadFile = File(...)):
    data = await file.read()
    result = classify_document(data)
    return result or {"doc_type": "other", "confidence": 0.0, "scores": {}, "engine": "none"}


from doc_forgery import analyze_doc_forgery
@app.post("/api/ml/doc_forgery", dependencies=[Depends(verify_ml_auth)])
async def api_doc_forgery(file: UploadFile = File(...)):
    data = await file.read()
    result = analyze_doc_forgery(data)
    return result


import base64
from media_processor import process_pdf_document, process_live_photo

@app.post("/api/ml/media/process_pdf", dependencies=[Depends(verify_ml_auth)])
async def api_process_pdf(file: UploadFile = File(...), max_pages: int = 5):
    data = await file.read()
    res = process_pdf_document(data, max_pages=max_pages)
    # Serialize rendered PNG buffers to base64 for JSON response
    serialized_pages = []
    for p in res.get("pages", []):
        p_dict = dict(p)
        raw_png = p_dict.pop("rendered_png", None)
        if raw_png:
            p_dict["png_b64"] = base64.b64encode(raw_png).decode("ascii")
        serialized_pages.append(p_dict)
    res["pages"] = serialized_pages
    return res


@app.post("/api/ml/media/process_live_photo", dependencies=[Depends(verify_ml_auth)])
async def api_process_live_photo(file: UploadFile = File(...)):
    data = await file.read()
    filename = file.filename or ""
    res = process_live_photo(data, filename=filename)
    raw_primary = res.pop("primary_image_png", None)
    if raw_primary:
        res["primary_image_b64"] = base64.b64encode(raw_primary).decode("ascii")
    return res



