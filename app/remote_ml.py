"""
Circuit-breaker and optimized payload dispatcher for remote ML microservice (SIH26188).
Ensures zero-hang fallback to local inference when the remote endpoint experiences latency.
"""
import io
import logging
import os
import time

logger = logging.getLogger("app.remote_ml")

_CIRCUIT_BROKEN_UNTIL = 0.0
_CONSECUTIVE_FAILURES = 0
_FAILURE_THRESHOLD = int(os.getenv("ML_CONSECUTIVE_FAILURES", "3"))
_BREAKER_BACKOFF_SEC = float(os.getenv("ML_BREAKER_BACKOFF", "45.0"))


def is_remote_available(endpoint: str = "") -> bool:
    """Returns False if ML_SERVICE_URL is not set or if circuit-breaker is active."""
    url = os.getenv("ML_SERVICE_URL")
    if not url:
        return False
    global _CIRCUIT_BROKEN_UNTIL
    if time.monotonic() < _CIRCUIT_BROKEN_UNTIL:
        return False
    return True


def mark_remote_failed(endpoint: str = "") -> None:
    """Increment consecutive failures; trip circuit breaker only when threshold is reached."""
    global _CONSECUTIVE_FAILURES, _CIRCUIT_BROKEN_UNTIL
    _CONSECUTIVE_FAILURES += 1
    if _CONSECUTIVE_FAILURES >= _FAILURE_THRESHOLD:
        _CIRCUIT_BROKEN_UNTIL = time.monotonic() + _BREAKER_BACKOFF_SEC
        logger.warning(
            f"[remote_ml] Remote ML tripped circuit breaker ({_CONSECUTIVE_FAILURES} consecutive failures). "
            f"Disabled for {_BREAKER_BACKOFF_SEC:.0f}s."
        )
    else:
        logger.info(
            f"[remote_ml] Remote ML call failed ({_CONSECUTIVE_FAILURES}/{_FAILURE_THRESHOLD} before tripping breaker)."
        )


def mark_remote_success(latency_sec: float = 0.0) -> None:
    """Reset failure counter and clear any active circuit-breaker on success."""
    global _CONSECUTIVE_FAILURES, _CIRCUIT_BROKEN_UNTIL
    _CONSECUTIVE_FAILURES = 0
    _CIRCUIT_BROKEN_UNTIL = 0.0
    if latency_sec > 3.0:
        logger.warning(
            f"[remote_ml] Remote ML response slow ({latency_sec:.2f}s) but succeeded within SLA window."
        )


def get_timeout() -> float:
    """Max network budget per call (default 2.0s for total request budget)."""
    try:
        return float(os.getenv("ML_SERVICE_TIMEOUT", "2.0"))
    except Exception:
        return 2.0


def get_connect_timeout() -> float:
    """Max connection handshake budget before assuming cold-start or offline (default 1.0s)."""
    try:
        return float(os.getenv("ML_SERVICE_CONNECT_TIMEOUT", "1.0"))
    except Exception:
        return 1.0


def get_auth_headers() -> dict[str, str]:
    """Supply shared authentication secret header to remote ML endpoints."""
    secret = (os.getenv("ML_SERVICE_SECRET") or os.getenv("ML_SECRET_KEY") or "").strip()
    headers = {"User-Agent": "NoCap-ScreeningDesk/3.0"}
    if secret:
        headers["X-ML-Secret-Key"] = secret
    return headers


def prepare_payload(image_bytes: bytes, max_dim: int = 800) -> bytes:
    """Normalize EXIF orientation unconditionally and downscale multi-megabyte photos."""
    if not image_bytes:
        return image_bytes
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(image_bytes))
        # Unconditionally apply EXIF transpose so rotated mobile captures are right-side-up
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max(img.size) > max_dim:
            scale = max_dim / max(img.size)
            new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return image_bytes
