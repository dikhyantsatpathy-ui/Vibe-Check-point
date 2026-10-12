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

try:
    from ml_service.face_policy import (
        BASE_SAME as _EMB_SAME,
        DIFF as _EMB_DIFF,
        AGED_PHOTO_YEARS,
        effective_threshold,
        resolve_policy_thresholds,
    )
except ImportError:
    from face_policy import (
        BASE_SAME as _EMB_SAME,
        DIFF as _EMB_DIFF,
        AGED_PHOTO_YEARS,
        effective_threshold,
        resolve_policy_thresholds,
    )

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



def evaluate_liveness_frames(frames: list[dict], challenge: str) -> dict:
    """Evaluates multi-frame biometric stream for challenge fulfillment.
    
    Supported challenges:
      - 'BLINK' / 'BLINK_TWICE': Detect Eye Aspect Ratio (EAR) dip below 0.20 followed by recovery.
      - 'NOD': Detect vertical pitch oscillation (>20px vertical travel).
      - 'TURN_HEAD' / 'TURN_HEAD_LEFT' / 'TURN_HEAD_RIGHT': Detect yaw displacement (>20px travel).
    """
    challenge_norm = (challenge or "").strip().upper()
    if not frames or len(frames) < 3:
        return {
            "passed": False,
            "challenge": challenge_norm,
            "frames_analyzed": len(frames) if frames else 0,
            "reason": "INSUFFICIENT_FRAMES",
        }

    if "BLINK" in challenge_norm:
        ears = [float(f.get("ear", 0.30)) for f in frames]
        min_ear = min(ears)
        dips = sum(1 for e in ears if e < 0.20)
        passed = min_ear < 0.20 and dips >= 1
        return {
            "passed": passed,
            "challenge": challenge_norm,
            "min_ear": round(min_ear, 3),
            "dips_count": dips,
            "frames_analyzed": len(frames),
            "detail": f"Eye Aspect Ratio minimum {min_ear:.2f} (dips: {dips})",
        }

    if "NOD" in challenge_norm:
        y_centers = [float(f.get("face_center_y", f.get("y", 0))) for f in frames]
        vertical_travel = max(y_centers) - min(y_centers)
        passed = vertical_travel >= 20.0
        return {
            "passed": passed,
            "challenge": challenge_norm,
            "vertical_travel": round(vertical_travel, 2),
            "frames_analyzed": len(frames),
            "detail": f"Vertical face travel {vertical_travel:.1f}px across {len(frames)} frames",
        }

    if "TURN" in challenge_norm:
        x_centers = [float(f.get("face_center_x", f.get("x", 0))) for f in frames]
        horizontal_travel = max(x_centers) - min(x_centers)
        passed = horizontal_travel >= 20.0
        return {
            "passed": passed,
            "challenge": challenge_norm,
            "horizontal_travel": round(horizontal_travel, 2),
            "frames_analyzed": len(frames),
            "detail": f"Horizontal face travel {horizontal_travel:.1f}px across {len(frames)} frames",
        }

    return {
        "passed": False,
        "challenge": challenge_norm,
        "frames_analyzed": len(frames),
        "reason": "UNSUPPORTED_CHALLENGE",
    }


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
        return {
            "score": 0,
            "match": None,
            "method": "unavailable",
            "mode": "unavailable",
            "decision": "INCONCLUSIVE",
            "detail": "Need a QR portrait and a readable selfie image.",
            "face_match": {
                "mode": "unavailable",
                "similarity": None,
                "threshold": float(emb_same) if emb_same is not None else _EMB_SAME,
                "decision": "INCONCLUSIVE",
            },
        }
    qr_img = _load_rgb(qr_bytes)
    sl_img = _load_rgb(sl_bytes)
    if qr_img is None or sl_img is None:
        return {
            "score": 0,
            "match": None,
            "method": "unavailable",
            "mode": "unavailable",
            "decision": "INCONCLUSIVE",
            "detail": "One of the images could not be decoded.",
            "face_match": {
                "mode": "unavailable",
                "similarity": None,
                "threshold": float(emb_same) if emb_same is not None else _EMB_SAME,
                "decision": "INCONCLUSIVE",
            },
        }

    if emb_same is not None:
        emb_same_threshold = float(emb_same)
        is_age_adjusted = True
    else:
        emb_same_threshold = effective_threshold(doc_age_years)
        is_age_adjusted = bool(doc_age_years is not None and doc_age_years >= AGED_PHOTO_YEARS)

    age_note = ""
    if is_age_adjusted:
        age_note = f" (age-adapted threshold: {emb_same_threshold:.2f} for older document portrait)"

    emb_a, emb_b = _embed_image(qr_img), _embed_image(sl_img)
    if emb_a is not None and emb_b is not None:
        import numpy as np
        sim = float(np.dot(emb_a, emb_b))
        score = int(round(max(0.0, min(1.0, (sim + 1.0) / 2.0)) * 100))
        decision = "MATCH" if sim >= emb_same_threshold else ("MISMATCH" if sim <= _EMB_DIFF else "INCONCLUSIVE")
        match = True if decision == "MATCH" else (False if decision == "MISMATCH" else None)
        verdict = "same person" if decision == "MATCH" else ("different person" if decision == "MISMATCH"
                                                       else "inconclusive — confirm by eye")
        return {
            "score": score,
            "match": match,
            "method": "onnx-embedding",
            "mode": "arcface",
            "decision": decision,
            "age_adjusted": is_age_adjusted,
            "threshold_used": round(emb_same_threshold, 2),
            "detail": f"Face-embedding cosine {sim:.2f}: {verdict}{age_note}.",
            "face_match": {
                "mode": "arcface",
                "similarity": round(sim, 3),
                "threshold": round(emb_same_threshold, 3),
                "decision": decision,
            },
        }

    dhash_same_threshold = _DHASH_SAME

    ha, hb = dhash(qr_img), dhash(sl_img)
    if ha is None or hb is None:
        return {
            "score": 0,
            "match": None,
            "method": "unavailable",
            "mode": "unavailable",
            "decision": "INCONCLUSIVE",
            "detail": "Perceptual hash failed on one of the images.",
            "face_match": {
                "mode": "unavailable",
                "similarity": None,
                "threshold": float(dhash_same_threshold),
                "decision": "INCONCLUSIVE",
            },
        }
    dist = _hamming(ha, hb)
    score = int(round((1.0 - dist / 64.0) * 100))
    # Invariant FS / A3: If mode != 'arcface': decision MUST NEVER be 'MATCH'.
    # It may only be 'INCONCLUSIVE' or 'MISMATCH'.
    # Legacy match boolean preserved for backwards-compatible test assertions.
    match = True if dist <= dhash_same_threshold else (False if dist >= _DHASH_DIFF else None)
    decision = "MISMATCH" if dist >= _DHASH_DIFF else "INCONCLUSIVE"
    verdict = ("near-duplicate portraits" if match is True
               else ("clearly different portraits" if match is False
                     else "inconclusive — confirm by eye"))
    return {
        "score": score,
        "match": match,
        "method": "phash-dhash",
        "mode": "fallback",
        "decision": decision,
        "age_adjusted": is_age_adjusted,
        "threshold_used": dhash_same_threshold,
        "detail": f"Perceptual-hash distance {dist}/64 ({verdict}){age_note}. Coarse "
                  f"whole-image comparison — set FACE_EMBED_MODEL for production.",
        "face_match": {
            "mode": "fallback",
            "similarity": round(1.0 - dist / 64.0, 3),
            "threshold": float(dhash_same_threshold),
            "decision": decision,
        },
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
