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
import logging
import os

logger = logging.getLogger("face_match")

_DHASH_SAME = 8
_DHASH_DIFF = 20

try:
    from app.face_policy import (
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


def get_face_health() -> dict:
    """Return health/metadata dict for face matching (Task P5)."""
    model_path = (os.getenv("FACE_EMBED_MODEL", "") or "").strip()
    loaded = bool(model_path and os.path.exists(model_path))
    auto_download = os.getenv("AUTO_DOWNLOAD_MODELS", "false").lower() in ("1", "true", "yes")

    if loaded:
        mode = "arcface"
        try:
            import hashlib
            with open(model_path, "rb") as f:
                sha_prefix = hashlib.sha256(f.read(1024 * 1024)).hexdigest()[:12]
        except Exception:
            sha_prefix = None
    else:
        mode = "fallback"
        sha_prefix = None

    return {
        "mode": mode,
        "loaded": loaded,
        "model_sha256_prefix": sha_prefix,
        "auto_download": auto_download,
    }


def _embed_image(image):
    """ONNX embedding path. Returns an L2-normalized vector or None (model
    missing/unloadable -> caller falls back to dHash, never crashes).

    Only an explicitly configured FACE_EMBED_MODEL path is used. The function
    never downloads a model: production servers must stay deterministic and
    must not fetch artifacts from the network during a screening pass.
    """
    global _embed_session, _embed_failed, _embed_model_path
    model_path = (os.getenv("FACE_EMBED_MODEL", "") or "").strip()
    if not model_path or not os.path.exists(model_path):
        return None
    # Reset cached state when the configured model changes — success and
    # failure are both tracked per path.
    if _embed_model_path != model_path:
        _embed_session = None
        _embed_failed = None
        _embed_model_path = model_path
    # Only skip if the same path failed before — retry when path changes.
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
    except Exception:
        _embed_failed = model_path  # remember path, not a boolean
        _embed_session = None
        return None


def get_age_aware_threshold(
    issue_year: int | None = None,
    doc_age_years: float | None = None,
    screening_year: int = 2026,
    base_threshold: float = 0.65,
    min_threshold: float = 0.50,
) -> float:
    """Age-aware adaptive verification thresholding (SIH26188 Phase A / Module 4).
    
    Dynamically adjusts the ArcFace match threshold to prevent false rejections
    for older valid documents (e.g. 10-year passports) while maintaining a strict floor.
    """
    delta_age = 0.0
    if doc_age_years is not None and doc_age_years > 0:
        delta_age = float(doc_age_years)
    elif issue_year is not None:
        delta_age = max(0.0, float(screening_year - issue_year))
    else:
        return base_threshold

    discount = min(delta_age * 0.015, 0.15)
    return round(max(min_threshold, base_threshold - discount), 3)


def evaluate_liveness_frames(frames: list[dict], challenge: str) -> dict:
    """Evaluates multi-frame biometric stream for challenge fulfillment.

    WARNING: Inputs must be computed server-side from raw frames. Client-supplied
    metrics (such as eye aspect ratio, pitch, or yaw) must not be trusted in
    production to prevent client spoofing. This function is currently a prototype
    and not integrated into active screening routes.

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
    ml_url = os.getenv("ML_SERVICE_URL")
    if ml_url:
        try:
            try:
                from app.remote_ml import get_auth_headers, is_remote_available, mark_remote_failed, mark_remote_success
            except ImportError:
                from remote_ml import get_auth_headers, is_remote_available, mark_remote_failed, mark_remote_success

            if not is_remote_available():
                logger.warning("Remote ML circuit breaker is active; failing closed for face_match.")
                return {
                    "score": 0,
                    "match": None,
                    "method": "unavailable",
                    "mode": "unavailable",
                    "decision": "INCONCLUSIVE",
                    "detail": "Remote ML circuit breaker active: fail-closed to inconclusive.",
                    "face_match": {
                        "mode": "unavailable",
                        "similarity": None,
                        "threshold": float(emb_same) if emb_same is not None else _EMB_SAME,
                        "decision": "INCONCLUSIVE",
                    },
                }

            timeout_sec = float(os.getenv("ML_SERVICE_TIMEOUT", "6.0"))
            payload = {}
            if isinstance(document_photo, bytes):
                import base64
                payload["doc_face_b64"] = base64.b64encode(document_photo).decode("ascii")
            else:
                payload["doc_face_b64"] = str(document_photo)
                
            if doc_age_years is not None:
                payload["doc_age_years"] = str(doc_age_years)
            if emb_same is not None:
                payload["emb_same"] = str(emb_same)
                
            files = {}
            if isinstance(selfie, bytes):
                files["live_frame"] = ("live.png", selfie, "image/png")
            else:
                import base64
                files["live_frame"] = ("live.png", base64.b64decode(selfie.strip()), "image/png")
                
            base = ml_url.rstrip("/")
            candidate_urls = (
                [f"{base}/api/ml/face_match", f"{base}/gradio_api/api/ml/face_match"]
                if "/gradio_api" not in base else [f"{base}/api/ml/face_match"]
            )
            headers = get_auth_headers()
            last_err = None
            res = None
            for target_url in candidate_urls:
                try:
                    try:
                        import httpx
                        with httpx.Client(timeout=timeout_sec) as client:
                            res = client.post(target_url, data=payload, files=files, headers=headers)
                    except ImportError:
                        import requests
                        res = requests.post(target_url, data=payload, files=files, headers=headers, timeout=timeout_sec)

                    if res is not None:
                        if res.status_code == 200:
                            mark_remote_success()
                            data = res.json()
                            if "face_match" not in data:
                                data["face_match"] = {
                                    "mode": data.get("mode", "arcface"),
                                    "similarity": data.get("similarity"),
                                    "threshold": data.get("threshold_used", _EMB_SAME),
                                    "decision": data.get("decision", "MATCH" if data.get("match") is True else "INCONCLUSIVE"),
                                }
                            return data
                        if res.status_code in (403, 404, 405) and target_url != candidate_urls[-1]:
                            continue
                        logger.warning(
                            f"Remote face_match returned HTTP {res.status_code}: {res.text[:200]}"
                        )
                except Exception as exc:
                    last_err = exc
                    continue

            mark_remote_failed()
            # Invariant FS / A7: Never silently fall back to dHash on remote ML failure.
            # Fail closed with mode="unavailable", decision="INCONCLUSIVE".
            err_msg = f"HTTP {res.status_code}" if res is not None else str(last_err or "connection failed")
            return {
                "score": 0,
                "match": None,
                "method": "unavailable",
                "mode": "unavailable",
                "decision": "INCONCLUSIVE",
                "detail": f"Remote face_match failed ({err_msg}): fail-closed to inconclusive.",
                "face_match": {
                    "mode": "unavailable",
                    "similarity": None,
                    "threshold": float(emb_same) if emb_same is not None else _EMB_SAME,
                    "decision": "INCONCLUSIVE",
                },
            }
        except Exception as exc:
            try:
                mark_remote_failed()
            except Exception:
                pass
            return {
                "score": 0,
                "match": None,
                "method": "unavailable",
                "mode": "unavailable",
                "decision": "INCONCLUSIVE",
                "detail": f"Remote face_match exception ({exc}): fail-closed to inconclusive.",
                "face_match": {
                    "mode": "unavailable",
                    "similarity": None,
                    "threshold": float(emb_same) if emb_same is not None else _EMB_SAME,
                    "decision": "INCONCLUSIVE",
                },
            }

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

    fh = get_face_health()
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
                "loaded": fh["loaded"],
                "model_sha256_prefix": fh["model_sha256_prefix"],
                "auto_download": fh["auto_download"],
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
                "loaded": fh["loaded"],
                "model_sha256_prefix": fh["model_sha256_prefix"],
                "auto_download": fh["auto_download"],
            },
        }
    dist = _hamming(ha, hb)
    score = int(round((1.0 - dist / 64.0) * 100))
    # Phase P3: Fallback methods never decide.
    # For any mode other than arcface: decision is INCONCLUSIVE always, match is None always.
    match = None
    decision = "INCONCLUSIVE"
    verdict = "inconclusive (fallback perceptual-hash — confirm by eye)"
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
            "loaded": fh["loaded"],
            "model_sha256_prefix": fh["model_sha256_prefix"],
            "auto_download": fh["auto_download"],
        },
    }


def face_match_capabilities() -> dict:
    """Backend status for /api/identity/meta."""
    Image = _pil()
    ml_url = bool(os.getenv("ML_SERVICE_URL"))
    onnx = bool(os.getenv("FACE_EMBED_MODEL", "")) and os.path.exists(
        os.getenv("FACE_EMBED_MODEL", ""))
    
    if ml_url:
        method = "onnx-embedding (remote)"
    elif Image is not None and onnx:
        method = "onnx-embedding"
    elif Image is not None:
        method = "phash-dhash"
    else:
        method = "none"

    return {
        "available": Image is not None or ml_url,
        "method": method,
        "onnx_configured": onnx or ml_url,
    }
