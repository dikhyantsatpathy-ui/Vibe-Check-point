"""
Document-type classifier (SIH26188) — local ONNX inference.

Distinguishes the identity/travel documents SSB screens at every Indian
checkpoint: passport, aadhaar, pan, driving_licence, voter_id,
nepali_citizenship, and a catch-all `other`. Powering:
  * live-image extraction (`POST /api/extract`) auto-detect doc type
  * guidance when the officer doesn't declare a document type

Trained offline (data/doctype + runs/classify) and exported to ONNX
(app/models/doctype.onnx, ~5.5 MB). Zero deps beyond onnxruntime + Pillow;
degrades to `None` (caller falls back to declared type) when the model is
absent or inference fails — an offline desk must still screen.
"""

import io
import logging
import os

import numpy as np
from PIL import Image

logger = logging.getLogger("doctype_cls")

# ultralytics classify export uses alphabetical class order — matches model metadata
CLASSES_V1 = [
    "aadhaar", "driving_licence", "nepali_citizenship", "other",
    "pan", "passport", "voter_id",
]

# Appendix D exact order for v2 classifier (8 classes)
CLASSES_V2 = [
    "aadhaar", "pan", "voter_id", "driving_licence",
    "passport", "nepali_citizenship", "bhutan_cid", "other",
]

CLASSES = CLASSES_V1

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
_IMG_SIZE = 224


def get_doctype_backend() -> str:
    """Return active doctype classifier backend: 'v1' (default) or 'v2'."""
    val = os.getenv("DOCTYPE_BACKEND")
    if val is None or not val.strip():
        return "v1"
    v = val.strip().lower()
    if v in ("v1", "baseline"):
        return "v1"
    if v in ("v2", "mobilenet", "mobilenetv3"):
        return "v2"
    raise ValueError(f"Unsupported DOCTYPE_BACKEND='{val}'. Use 'v1' or 'v2'.")


def _default_model_path() -> str:
    env = os.getenv("DOCTYPE_ONNX_PATH")
    if env and os.path.exists(env):
        return env
    backend = get_doctype_backend()
    model_dirs = [_MODEL_DIR]
    ml_models = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ml_service", "models"))
    if ml_models not in [os.path.abspath(d) for d in model_dirs]:
        model_dirs.append(ml_models)

    if backend == "v2":
        for mdir in model_dirs:
            for name in ("doctype_v2.onnx", "doctype_v2_int8.onnx"):
                cand = os.path.join(mdir, name)
                if os.path.exists(cand):
                    return cand
        logger.warning("DOCTYPE_BACKEND='v2' configured but doctype_v2.onnx not found. Failing loudly without fallback.")
        return ""

    for mdir in model_dirs:
        cand = os.path.join(mdir, "doctype.onnx")
        if os.path.exists(cand):
            return cand
    return ""


_MODEL_PATH = _default_model_path()
_session = None
_session_attempted = False


def _resize_keep_aspect(img: Image.Image, size: int) -> Image.Image:
    """torchvision Resize(size) equivalent: scale so the SHORTER edge == size,
    preserving aspect ratio (ultralytics classify_transforms convention)."""
    w, h = img.size
    if w <= h:
        nw, nh = size, int(round(h * size / w))
    else:
        nh, nw = size, int(round(w * size / h))
    return img.resize((nw, nh), Image.BILINEAR)


def _center_crop(img: Image.Image, tw: int, th: int) -> Image.Image:
    """torchvision CenterCrop((th, tw)) equivalent: centre square crop."""
    w, h = img.size
    x0 = max(0, (w - tw) // 2)
    y0 = max(0, (h - th) // 2)
    return img.crop((x0, y0, x0 + tw, y0 + th))


def model_available() -> bool:
    return bool(_MODEL_PATH)


def _get_session():
    global _session, _session_attempted
    if _session_attempted:
        return _session
    _session_attempted = True
    if not _MODEL_PATH:
        return None
    try:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(
            _MODEL_PATH, sess_options=opts,
            providers=["CPUExecutionProvider"])
        return _session
    except Exception as exc:
        logger.warning("doctype ONNX load failed: %s", exc)
        return None


def classify_document(data: bytes) -> dict | None:
    """Classify raw image bytes -> {doc_type, confidence, scores}.

    Matches the exported ONNX (doctype.onnx) letterbox convention model training
    used: Resize(224 keep-aspect) -> CenterCrop(224x224) -> ToTensor (/255).
    Returns None on decode/inference failure (caller falls back to declared).
    """
    try:
        from remote_ml import is_remote_available, mark_remote_failed, mark_remote_success, get_timeout, prepare_payload
    except ImportError:
        try:
            from app.remote_ml import is_remote_available, mark_remote_failed, mark_remote_success, get_timeout, prepare_payload
        except ImportError:
            is_remote_available = lambda: bool(os.getenv("ML_SERVICE_URL"))
            mark_remote_failed = lambda: None
            mark_remote_success = lambda: None
            get_timeout = lambda: 2.0
            prepare_payload = lambda b: b

    if is_remote_available():
        ml_url = os.getenv("ML_SERVICE_URL")
        try:
            timeout_sec = get_timeout()
            base = ml_url.rstrip("/")
            payload = prepare_payload(data)
            candidate_urls = (
                [f"{base}/api/ml/doctype", f"{base}/gradio_api/api/ml/doctype"]
                if "/gradio_api" not in base else [f"{base}/api/ml/doctype"]
            )
            for target_url in candidate_urls:
                files = {"file": ("image.jpg", payload, "image/jpeg")}
                try:
                    import httpx
                    with httpx.Client(timeout=timeout_sec) as client:
                        res = client.post(target_url, files=files)
                except ImportError:
                    import requests
                    res = requests.post(target_url, files=files, timeout=timeout_sec)
                if res is not None and res.status_code == 200:
                    mark_remote_success()
                    return res.json()
        except Exception as exc:
            mark_remote_failed()
            logger.warning("remote doctype classify failed: %s", exc)

    sess = _get_session()
    if sess is None:
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        # Match ultralytics classify_transforms: Resize to 224 keeping aspect,
        # then CenterCrop to 224x224, then ToTensor (which divides by 255).
        img = _resize_keep_aspect(img, _IMG_SIZE)
        img = _center_crop(img, _IMG_SIZE, _IMG_SIZE)
        arr = np.asarray(img, dtype=np.float32) / 255.0
        tensor = arr.transpose(2, 0, 1)[None, ...]
        (logits,) = sess.run(None, {sess.get_inputs()[0].name: tensor})
        raw = logits[0]

        # If model already outputs normalized probabilities (summing to ~1),
        # use directly; otherwise apply softmax.
        if np.isclose(float(raw.sum()), 1.0, atol=0.05) and np.all(raw >= 0):
            probs = raw
        else:
            probs = raw - raw.max()
            exps = np.exp(probs)
            probs = exps / exps.sum()

        active_classes = CLASSES_V2 if len(raw) == len(CLASSES_V2) or "doctype_v2" in str(_MODEL_PATH) else CLASSES_V1
        is_v2 = len(active_classes) == 8

        idx = int(probs.argmax())
        scores = {active_classes[i]: round(float(probs[i]), 4) for i in range(len(active_classes))}
        model_name = os.path.basename(_MODEL_PATH) if _MODEL_PATH else "doctype.onnx"
        return {
            "doc_type": active_classes[idx] if idx < len(active_classes) else "other",
            "confidence": round(float(probs[idx]), 4),
            "scores": scores,
            "engine": model_name,
            "doctype_backend": "v2" if is_v2 else "v1",
            "effective_backend": "v2" if is_v2 else "v1",
        }
    except Exception as exc:
        logger.warning("doctype classify failed: %s", exc)
        return None