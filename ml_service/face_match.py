"""
Face match: document portrait vs live selfie (closes "valid document, wrong
person").

The desk uploads the identity document (or a scanner provides its portrait
region) and the live webcam capture of the holder. This module compares the
two and returns a conservative 3-state verdict:

    match True   — near-duplicate (same capture pipeline / photocopy)
    match False  — clearly different people
    match None   — inconclusive (no portrait, undecodable bytes, middle band)

Two engines, best available wins:
  1. An ONNX face-embedding model when FACE_EMBED_MODEL points at an .onnx
     file and onnxruntime imports (cosine similarity on L2-normalized
     embeddings; >= 0.60 same, <= 0.40 different, between inconclusive).
  2. Otherwise a whole-image perceptual dHash via Pillow — Pillow already
      ships with the app, so this works on Vercel TODAY
      (Hamming distance <= 8 same, >= 20 different, between inconclusive).

dHash is coarse (a card portrait and a selfie differ in background, lighting,
crop), so the middle band is wide ON PURPOSE and every verdict names its
method. Confirm by eye; point FACE_EMBED_MODEL at an ArcFace/FaceNet-style
graph for production use.
"""

import base64
import io
import os

_DHASH_SAME = 8
_DHASH_DIFF = 20
_EMB_SAME = 0.60
_EMB_DIFF = 0.40

_embed_session = None
_embed_failed: str | None = None  # stores the model path that last failed, or None
_embed_model_path: str | None = None  # model path currently loaded in _embed_session


def _pil():
    try:
        from PIL import Image
        return Image
    except Exception:
        return None


def _coerce_image_bytes(data) -> bytes | None:
    """Accept raw image bytes OR a base64 string (the document-portrait form).
    Returns decodable image bytes or None."""
    if not data:
        return None
    if isinstance(data, str):
        data = data.strip()
        try:
            data = base64.b64decode(data)
        except Exception:
            return None
    if not isinstance(data, (bytes, bytearray)) or len(data) < 64:
        return None
    return bytes(data)


def _load_rgb(data: bytes):
    Image = _pil()
    if Image is None:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.convert("RGB")
    except Exception:
        return None


def dhash(image) -> int | None:
    """64-bit difference hash: 9x8 grayscale, one bit per horizontal step."""
    try:
        small = image.convert("L").resize((9, 8))
        px = list(small.tobytes())  # raw 'L' pixels — no deprecated getdata
        bits = 0
        for y in range(8):
            row = y * 9
            for x in range(8):
                bits = (bits << 1) | (1 if px[row + x] > px[row + x + 1] else 0)
        return bits
    except Exception:
        return None


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


DEFAULT_FACE_URL = "https://huggingface.co/maze/faceX/resolve/main/w600k_r50.onnx"
DEFAULT_FACE_SHA256 = "4c06341c33c2a6f3b79361ad22872322307fe959a7a9cb52de9ae3a246835a09"


def _resolve_face_model_path() -> str | None:
    """Resolve ArcFace model path from env, local models/ dir, repo data/models/, or auto-download."""
    env_path = (os.getenv("FACE_EMBED_MODEL", "") or "").strip()
    if env_path and os.path.exists(env_path):
        return env_path

    local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    local_model = os.path.join(local_dir, "w600k_r50.onnx")
    if os.path.exists(local_model):
        return local_model

    repo_model = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "models", "w600k_r50.onnx")
    )
    if os.path.exists(repo_model):
        return repo_model

    if os.getenv("AUTO_DOWNLOAD_MODELS", "true").lower() in ("1", "true", "yes"):
        try:
            os.makedirs(local_dir, exist_ok=True)
            print(f"[face_match] downloading ArcFace model -> {local_model} ({DEFAULT_FACE_URL})")
            import hashlib
            import shutil
            import urllib.request

            tmp = local_model + ".download"
            req = urllib.request.Request(
                DEFAULT_FACE_URL,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            hasher = hashlib.sha256()
            with urllib.request.urlopen(req) as resp, open(tmp, "wb") as out:
                while chunk := resp.read(65536):
                    hasher.update(chunk)
                    out.write(chunk)
            digest = hasher.hexdigest()
            expected_sha = os.getenv("FACE_MODEL_SHA256", DEFAULT_FACE_SHA256).strip().lower()
            if expected_sha and digest.lower() != expected_sha:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise ValueError(f"Supply-chain check failed: ArcFace SHA-256 {digest} != expected {expected_sha}")

            os.replace(tmp, local_model)
            return local_model
        except Exception as exc:
            print(f"[face_match] failed to download ArcFace model: {exc}")
            if os.path.exists(local_model + ".download"):
                try:
                    os.remove(local_model + ".download")
                except Exception:
                    pass
    return None


def _embed_image(image):
    """ONNX embedding path. Returns an L2-normalized vector or None (model
    missing/unloadable -> caller falls back to dHash, never crashes).
    """
    global _embed_session, _embed_failed, _embed_model_path
    model_path = _resolve_face_model_path()
    if not model_path or not os.path.exists(model_path):
        return None
    # Reset cached state when the configured model changes
    if _embed_model_path != model_path:
        _embed_session = None
        _embed_failed = None
        _embed_model_path = model_path
    if _embed_failed == model_path:
        return None
    try:
        import numpy as np
        import onnxruntime as ort
        if _embed_session is None:
            _embed_session = ort.InferenceSession(
                model_path, providers=["CPUExecutionProvider"])
        sess = _embed_session
        inp = sess.get_inputs()[0]
        shape = inp.shape
        h = int(shape[2]) if len(shape) > 2 and isinstance(shape[2], int) else 112
        w = int(shape[3]) if len(shape) > 3 and isinstance(shape[3], int) else 112
        arr = np.asarray(image.resize((w, h)), dtype=np.float32)
        arr = (arr - 127.5) / 128.0  # ArcFace/FaceNet-style (0-255 -> ~[-1, 1])
        arr = arr.transpose(2, 0, 1)[None, ...]
        vec = np.asarray(sess.run(None, {inp.name: arr})[0]).reshape(-1)
        n = float((vec ** 2).sum() ** 0.5)
        return vec / n if n > 0 else None
    except Exception as exc:
        print(f"[face_match] ONNX embedding failed: {exc}")
        _embed_failed = model_path
        _embed_session = None
        return None


def compare_faces(document_photo, selfie, doc_age_years: float | None = None, emb_same: float | None = None) -> dict:
    """Compare a document portrait against a selfie. Inputs may be raw bytes or
    base64 strings. Never raises; inconclusive inputs yield match None.
    
    When doc_age_years is provided and > 4.0 (or emb_same is specified), dynamically
    adapts the threshold to account for natural physiological aging across long-validity
    documents (e.g., 10-year passports).
    """
    qr_bytes = _coerce_image_bytes(document_photo)
    sl_bytes = _coerce_image_bytes(selfie)
    if qr_bytes is None or sl_bytes is None:
        return {"score": 0, "match": None, "method": "unavailable",
                "detail": "Need a QR portrait and a readable selfie image."}
    qr_img = _load_rgb(qr_bytes)
    sl_img = _load_rgb(sl_bytes)
    if qr_img is None or sl_img is None:
        return {"score": 0, "match": None, "method": "unavailable",
                "detail": "One of the images could not be decoded."}

    # Age-aware adaptive threshold scaling:
    # A 5-10 year old passport photo exhibits natural physiological aging.
    # We adaptively relax the threshold slightly while guarding against spoofing.
    emb_same_threshold = float(emb_same) if emb_same is not None else _EMB_SAME
    age_note = ""
    is_age_adjusted = emb_same is not None
    if doc_age_years is not None and doc_age_years > 4.0:
        relax = min(0.12, (doc_age_years - 4.0) * 0.015)
        if emb_same is None:
            emb_same_threshold = max(0.48, _EMB_SAME - relax)
        is_age_adjusted = True
        age_note = f" (age-adapted threshold: {emb_same_threshold:.2f} for ~{int(round(doc_age_years))}y old document portrait)"
    elif emb_same is not None and emb_same != _EMB_SAME:
        age_note = f" (adapted threshold: {emb_same_threshold:.2f})"

    emb_a, emb_b = _embed_image(qr_img), _embed_image(sl_img)
    if emb_a is not None and emb_b is not None:
        import numpy as np
        sim = float(np.dot(emb_a, emb_b))
        score = int(round(max(0.0, min(1.0, (sim + 1.0) / 2.0)) * 100))
        match = True if sim >= emb_same_threshold else (False if sim <= _EMB_DIFF else None)
        verdict = "same person" if match is True else ("different person" if match is False
                                                       else "inconclusive — confirm by eye")
        return {
            "score": score,
            "match": match,
            "method": "onnx-embedding",
            "age_adjusted": is_age_adjusted,
            "threshold_used": round(emb_same_threshold, 2),
            "detail": f"Face-embedding cosine {sim:.2f}: {verdict}{age_note}.",
        }

    dhash_same_threshold = _DHASH_SAME
    if doc_age_years is not None and doc_age_years > 4.0:
        dhash_relax = min(4, int((doc_age_years - 4.0) * 0.5))
        dhash_same_threshold = min(12, _DHASH_SAME + dhash_relax)
        is_age_adjusted = True
        age_note = f" (age-adapted threshold: <= {dhash_same_threshold} for ~{int(round(doc_age_years))}y old portrait)"

    ha, hb = dhash(qr_img), dhash(sl_img)
    if ha is None or hb is None:
        return {"score": 0, "match": None, "method": "unavailable",
                "detail": "Perceptual hash failed on one of the images."}
    dist = _hamming(ha, hb)
    score = int(round((1.0 - dist / 64.0) * 100))
    match = True if dist <= dhash_same_threshold else (False if dist >= _DHASH_DIFF else None)
    verdict = ("near-duplicate portraits" if match is True
               else ("clearly different portraits" if match is False
                     else "inconclusive — confirm by eye"))
    return {
        "score": score,
        "match": match,
        "method": "phash-dhash",
        "age_adjusted": is_age_adjusted,
        "threshold_used": dhash_same_threshold,
        "detail": f"Perceptual-hash distance {dist}/64 ({verdict}){age_note}. Coarse "
                  f"whole-image comparison — set FACE_EMBED_MODEL for production.",
    }


def face_match_capabilities() -> dict:
    """Backend status for /api/identity/meta."""
    Image = _pil()
    onnx = bool(os.getenv("FACE_EMBED_MODEL", "")) and os.path.exists(
        os.getenv("FACE_EMBED_MODEL", ""))
    return {"available": Image is not None,
            "method": "onnx-embedding" if (Image is not None and onnx) else (
                "phash-dhash" if Image is not None else "none"),
            "onnx_configured": onnx}
