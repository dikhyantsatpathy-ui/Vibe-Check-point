"""
Document-type classifier (SIH26188) — local ONNX inference for ml_service.

Distinguishes the identity/travel documents SSB screens at every Indian
checkpoint: passport, aadhaar, pan, driving_licence, voter_id,
nepali_citizenship, bhutan_cid, and a catch-all `other`.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image

logger = logging.getLogger("ml_service.doctype_cls")

CLASSES_V1 = [
    "aadhaar", "driving_licence", "nepali_citizenship", "other",
    "pan", "passport", "voter_id",
]

CLASSES_V2 = [
    "aadhaar", "pan", "voter_id", "driving_licence",
    "passport", "nepali_citizenship", "bhutan_cid", "other",
]

CLASSES = CLASSES_V1

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
_IMG_SIZE = 224


def get_doctype_backend() -> str:
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
    app_models = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "models"))
    if app_models not in [os.path.abspath(d) for d in model_dirs]:
        model_dirs.append(app_models)

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
    w, h = img.size
    if w <= h:
        nw, nh = size, int(round(h * size / w))
    else:
        nh, nw = size, int(round(w * size / h))
    return img.resize((nw, nh), Image.BILINEAR)


def _center_crop(img: Image.Image, tw: int, th: int) -> Image.Image:
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


def classify_document(data: bytes) -> Optional[Dict[str, Any]]:
    sess = _get_session()
    if sess is None:
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = _resize_keep_aspect(img, _IMG_SIZE)
        img = _center_crop(img, _IMG_SIZE, _IMG_SIZE)
        arr = np.asarray(img, dtype=np.float32) / 255.0
        tensor = arr.transpose(2, 0, 1)[None, ...]
        (logits,) = sess.run(None, {sess.get_inputs()[0].name: tensor})
        raw = logits[0]

        # Temperature scaling calibration (Phase C4)
        temperature = float(os.getenv("DOCTYPE_TEMPERATURE", "1.35"))
        review_threshold = float(os.getenv("DOCTYPE_REVIEW_THRESHOLD", "0.75"))

        scaled = raw / max(temperature, 0.1)
        scaled_shifted = scaled - scaled.max()
        exps = np.exp(scaled_shifted)
        probs = exps / exps.sum()

        active_classes = CLASSES_V2 if len(raw) == len(CLASSES_V2) or "doctype_v2" in str(_MODEL_PATH) else CLASSES_V1
        is_v2 = len(active_classes) == 8

        idx = int(probs.argmax())
        top_conf = round(float(probs[idx]), 4)
        scores = {active_classes[i]: round(float(probs[i]), 4) for i in range(len(active_classes))}
        model_name = os.path.basename(_MODEL_PATH) if _MODEL_PATH else "doctype.onnx"

        needs_review = bool(top_conf < review_threshold)
        predicted_class = active_classes[idx] if idx < len(active_classes) else "other"

        return {
            "doc_type": predicted_class,
            "confidence": top_conf,
            "calibrated_confidence": top_conf,
            "temperature": temperature,
            "review_threshold": review_threshold,
            "needs_review": needs_review,
            "status": "NEEDS_MANUAL_REVIEW" if needs_review else "CONFIRMED",
            "scores": scores,
            "engine": model_name,
            "doctype_backend": "v2" if is_v2 else "v1",
            "effective_backend": "v2" if is_v2 else "v1",
        }
    except Exception as exc:
        logger.warning("doctype classify failed: %s", exc)
        return None