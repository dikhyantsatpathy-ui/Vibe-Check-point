"""
Card corner detection and homography perspective rectification (SIH26188 Phase 3).
Warps skewed handheld card photos to canonical flat perspective (1000x630, ~1.58:1 CR-80 ratio).
Supports pure-Python / Pillow fallback so it runs safely on Vercel without heavy dependencies.
"""

import io
import math
import os
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
from PIL import Image

CANONICAL_CARD_WIDTH = 1000
CANONICAL_CARD_HEIGHT = 630  # CR-80 ratio ~1.587:1


def _order_quad_points(pts: np.ndarray) -> np.ndarray:
    """Sort 4 corner coordinates into canonical order:
    [top-left, top-right, bottom-right, bottom-left].
    """
    pts = np.asarray(pts, dtype=np.float32)
    rect = np.zeros((4, 2), dtype=np.float32)

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect


def find_homography_matrix(src_quad: np.ndarray, dst_quad: np.ndarray) -> np.ndarray:
    """Computes 3x3 homography matrix H such that dst = H * src.
    Uses standard Direct Linear Transformation (DLT) with SVD (pure NumPy).
    """
    src = _order_quad_points(src_quad)
    dst = _order_quad_points(dst_quad)

    A = []
    for i in range(4):
        x, y = src[i][0], src[i][1]
        u, v = dst[i][0], dst[i][1]
        A.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        A.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    A = np.asarray(A, dtype=np.float32)

    _, _, Vh = np.linalg.svd(A)
    H = Vh[-1].reshape((3, 3))
    return H / (H[2, 2] if abs(H[2, 2]) > 1e-7 else 1.0)


def warp_perspective_pillow(image: Image.Image, src_quad: np.ndarray, target_size: Tuple[int, int] = (CANONICAL_CARD_WIDTH, CANONICAL_CARD_HEIGHT)) -> Image.Image:
    """Applies homography perspective warp using Pillow's built-in Image.transform."""
    target_w, target_h = target_size
    dst_quad = np.array([
        [0, 0],
        [target_w - 1, 0],
        [target_w - 1, target_h - 1],
        [0, target_h - 1]
    ], dtype=np.float32)

    H_inv = find_homography_matrix(dst_quad, src_quad)
    coeffs = H_inv.flatten()[:8] / H_inv[2, 2]
    warped = image.transform(
        (target_w, target_h),
        Image.Transform.PERSPECTIVE,
        coeffs,
        Image.Resampling.BILINEAR,
    )
    return warped


def detect_card_quad(image_rgb: np.ndarray) -> Optional[np.ndarray]:
    """Detects 4-corner quadrilateral boundary of an ID card in an image."""
    h, w = image_rgb.shape[:2]
    area_total = w * h

    try:
        import cv2
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        edges = cv2.Canny(blurred, 40, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)

            if len(approx) == 4 and cv2.isContourConvex(approx):
                cnt_area = cv2.contourArea(approx)
                if 0.10 * area_total <= cnt_area <= 0.95 * area_total:
                    pts = approx.reshape(4, 2)
                    return _order_quad_points(pts)
    except Exception:
        pass

    inset_x = w * 0.05
    inset_y = h * 0.05
    fallback_quad = np.array([
        [inset_x, inset_y],
        [w - inset_x, inset_y],
        [w - inset_x, h - inset_y],
        [inset_x, h - inset_y],
    ], dtype=np.float32)
    return fallback_quad


def rectify_card_image(
    image_bytes: bytes,
    force_rectification: bool = False,
) -> Tuple[bytes, bool, Optional[Dict[str, Any]]]:
    """Rectify card boundary to canonical orientation and aspect ratio."""
    enable_flag = os.getenv("ENABLE_CARD_RECTIFICATION", "false").strip().lower() in ("true", "1", "yes")
    if not (enable_flag or force_rectification):
        return image_bytes, False, None

    try:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        rgb_arr = np.asarray(pil_img, dtype=np.uint8)

        quad = detect_card_quad(rgb_arr)
        if quad is None:
            return image_bytes, False, None

        warped = warp_perspective_pillow(pil_img, quad, target_size=(CANONICAL_CARD_WIDTH, CANONICAL_CARD_HEIGHT))

        out_buf = io.BytesIO()
        warped.save(out_buf, format="PNG")
        rectified_bytes = out_buf.getvalue()

        meta = {
            "canonical_width": CANONICAL_CARD_WIDTH,
            "canonical_height": CANONICAL_CARD_HEIGHT,
            "source_quad": quad.tolist(),
            "aspect_ratio": round(CANONICAL_CARD_WIDTH / CANONICAL_CARD_HEIGHT, 3),
        }
        return rectified_bytes, True, meta
    except Exception:
        return image_bytes, False, None
