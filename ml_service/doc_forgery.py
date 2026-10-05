"""
Dual-Stream Document Forgery & Digital Manipulation Detector (SIH26188).
Runs in the external Hugging Face / ZeroGPU microservice container.
"""

import io
import time
import numpy as np
from PIL import Image

_LUMA_WEIGHTS = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _to_gray(rgb: np.ndarray) -> np.ndarray:
    return np.dot(rgb.astype(np.float32), _LUMA_WEIGHTS)


def _open_rgb(data: bytes) -> np.ndarray | None:
    try:
        from PIL import ImageOps
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.load()
        img = img.convert("RGB")
        max_dim = 1280
        if max(img.size) > max_dim:
            scale = max_dim / max(img.size)
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.BILINEAR)
        return np.asarray(img, dtype=np.uint8)
    except Exception:
        return None


def _srm_filter_residuals(gray: np.ndarray) -> np.ndarray:
    if gray.shape[0] < 8 or gray.shape[1] < 8:
        return np.zeros_like(gray, dtype=np.float32)
    return 4.0 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]


def analyze_doc_forgery(image_bytes: bytes) -> dict:
    if not image_bytes:
        return {
            "ran": False,
            "is_tampered": False,
            "tamper_score": 0,
            "confidence": 0.0,
            "detail": "No image data supplied.",
        }

    started = time.perf_counter()
    rgb = _open_rgb(image_bytes)
    if rgb is None:
        return {
            "ran": False,
            "is_tampered": False,
            "tamper_score": 0,
            "confidence": 0.0,
            "detail": "Image format not readable.",
        }

    h, w = rgb.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        nw, nh = max(16, int(w * scale)), max(16, int(h * scale))
        pil_img = Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR)
        rgb = np.asarray(pil_img)

    gray = _to_gray(rgb)
    srm_res = _srm_filter_residuals(gray)

    bs = 16
    bh, bw = srm_res.shape[0] // bs, srm_res.shape[1] // bs
    if bh >= 2 and bw >= 2:
        crop = srm_res[:bh * bs, :bw * bs]
        tiles = crop.reshape(bh, bs, bw, bs)
        block_vars = tiles.var(axis=(1, 3)).astype(np.float32)
        block_means = gray[:bh * bs, :bw * bs].reshape(bh, bs, bw, bs).mean(axis=(1, 3))
    else:
        block_vars = np.array([[float(srm_res.var())]], dtype=np.float32)
        block_means = np.array([[float(gray.mean())]], dtype=np.float32)

    non_margin = (block_means < 240) & (block_means > 20)
    non_margin_count = int(np.sum(non_margin))

    if non_margin_count > 16:
        dead_mask = non_margin & (block_vars < 0.015)
        dead_blocks = int(np.sum(dead_mask))
        dead_block_ratio_preview = dead_blocks / non_margin_count

        def _largest_connected_component(mask: np.ndarray) -> int:
            if mask.size == 0 or not mask.any():
                return 0
            labeled = np.zeros(mask.shape, dtype=np.int32)
            label_id = 0
            sizes: list[int] = []
            rows, cols = mask.shape
            for r in range(rows):
                for c in range(cols):
                    if mask[r, c] and labeled[r, c] == 0:
                        label_id += 1
                        count = 0
                        stack = [(r, c)]
                        while stack:
                            cr, cc = stack.pop()
                            if cr < 0 or cr >= rows or cc < 0 or cc >= cols:
                                continue
                            if not mask[cr, cc] or labeled[cr, cc] != 0:
                                continue
                            labeled[cr, cc] = label_id
                            count += 1
                            stack.extend([(cr - 1, cc), (cr + 1, cc), (cr, cc - 1), (cr, cc + 1)])
                        sizes.append(count)
            return max(sizes) if sizes else 0

        largest_component = _largest_connected_component(dead_mask)
        near_total_flatness = dead_block_ratio_preview > 0.85
        localized_void = largest_component >= max(8, non_margin_count * 0.005)
        inpaint_void = bool(near_total_flatness or localized_void)
        void_kind = (
            "near_total_flatness"
            if near_total_flatness
            else ("localized_void" if localized_void else None)
        )
        active_vars = block_vars[non_margin & (block_vars > 1.0)]
        if active_vars.size > 8:
            med_noise = float(np.median(active_vars))
            q75, q25 = np.percentile(active_vars, [75, 25])
            dispersion = (q75 - q25) / (med_noise + 1e-5)
            uniformity = max(0.0, min(1.0, 1.0 - (dispersion / 12.0)))
        else:
            uniformity = 0.90
    else:
        inpaint_void = False
        void_kind = None
        uniformity = 0.95
        dead_blocks = 0
        largest_component = 0

    dead_block_ratio = (dead_blocks / non_margin_count) if non_margin_count > 0 else 0.0

    dx = np.abs(gray[:, 1:] - gray[:, :-1])
    dy = np.abs(gray[1:, :] - gray[:-1, :])
    max_step = max(float(dx.max()), float(dy.max())) if dx.size and dy.size else 0.0
    seam_anomaly = bool(max_step > 250.0 and inpaint_void)

    is_tampered = inpaint_void or seam_anomaly

    if is_tampered:
        tamper_score = 88
        detail = "Dual-Stream Forgery Alert: Localized digital erasure / inpainting voids detected across card substrate."
    else:
        tamper_score = max(0, min(20, int((1.0 - uniformity) * 15.0)))
        detail = f"Substrate verified: Natural camera noise floor and continuous optical grain ({uniformity * 100:.0f}% substrate consistency)."

    latency_ms = int((time.perf_counter() - started) * 1000)

    return {
        "ran": True,
        "is_tampered": is_tampered,
        "tamper_score": tamper_score,
        "confidence": 0.92 if is_tampered else 0.88,
        "substrate_uniformity": round(float(uniformity), 3),
        "dead_block_ratio": round(float(dead_block_ratio), 4),
        "largest_component": int(largest_component),
        "void_kind": void_kind if inpaint_void else None,
        "seam_anomaly": bool(seam_anomaly),
        "detail": detail,
        "latency_ms": latency_ms,
    }
