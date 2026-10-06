"""MRZ Image Preprocessing and Multi-Variant OCR Enhancer (Phase C2).

Enhances Machine Readable Zone (MRZ) OCR quality:
1. Generous padding around detector crop (8% horizontal, 12% vertical).
2. Deskew based on minimum-area bounding box angle or Hough transform.
3. Upscaling to ~64 px per line height (optimal for OCR-B character segmentation).
4. Multi-variant preprocessing:
   - Variant 0: Scaled bicubic RGB
   - Variant 1: CLAHE (Contrast-Limited Adaptive Histogram Equalization) on L channel
   - Variant 2: Unsharp masking / contrast boost
   - Variant 3: Adaptive thresholding binarization
5. Multi-line candidate fusion and position-aware verification via app/mrz.py.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

try:
    from app.mrz import parse_mrz, _clean_mrz_lines
except ImportError:
    from mrz import parse_mrz, _clean_mrz_lines

logger = logging.getLogger(__name__)


def deskew_mrz_crop(image: np.ndarray) -> np.ndarray:
    """Detect line skew angle in MRZ crop and deskew."""
    if image is None or image.size == 0:
        return image
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image
        # High-pass or Sobel to find horizontal text lines
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(grad_x, grad_y)
        thresh = cv2.threshold(mag.astype(np.uint8), 50, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) < 50:
            return image
        
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        elif angle > 45:
            angle = 90 - angle
        else:
            angle = -angle
            
        if abs(angle) > 0.5 and abs(angle) < 15.0:
            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            deskewed = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            return deskewed
    except Exception:
        pass
    return image


def generate_mrz_variants(crop: np.ndarray, num_lines: int = 2) -> List[np.ndarray]:
    """Generate 3-4 preprocessing variants for robust OCR-B character recognition."""
    if crop is None or crop.size == 0:
        return []

    deskewed = deskew_mrz_crop(crop)
    h, w = deskewed.shape[:2]
    
    # Target height: ~64 px per line
    target_line_h = 64
    target_h = max(target_line_h * num_lines, int(h * 1.5))
    scale = target_h / max(h, 1)
    target_w = int(w * scale)
    
    # Variant 0: Scaled bicubic RGB
    v0 = cv2.resize(deskewed, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    variants = [v0]

    # Variant 1: CLAHE on luminance (handles low contrast / passport background patterns)
    if len(v0.shape) == 3:
        lab = cv2.cvtColor(v0, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        v1 = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2RGB)
        variants.append(v1)
    
    # Variant 2: Unsharp masking to sharpen OCR-B character edges
    gaussian = cv2.GaussianBlur(v0, (0, 0), 2.0)
    v2 = cv2.addWeighted(v0, 1.6, gaussian, -0.6, 0)
    variants.append(v2)

    # Variant 3: High-contrast binarization
    gray = cv2.cvtColor(v0, cv2.COLOR_RGB2GRAY) if len(v0.shape) == 3 else v0
    binarized = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10
    )
    v3 = cv2.cvtColor(binarized, cv2.COLOR_GRAY2RGB)
    variants.append(v3)

    return variants


def extract_and_parse_mrz_enhanced(
    rgb_img: np.ndarray,
    ocr_runner,
    mrz_box: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute robust multi-candidate MRZ extraction and verification pipeline.
    
    Returns parsed MRZ dict matching app.mrz.parse_mrz structure with added 'variant' metadata.
    """
    h, w = rgb_img.shape[:2]
    candidate_crops: List[Tuple[str, np.ndarray]] = []

    # 1. Detected MRZ crop with generous padding (prevents character border clipping)
    if mrz_box:
        pad_x = int(0.08 * mrz_box["w"] * w)
        pad_y = int(0.12 * mrz_box["h"] * h)
        x1 = max(0, int(mrz_box["x"] * w - pad_x))
        y1 = max(0, int(mrz_box["y"] * h - pad_y))
        x2 = min(w, int((mrz_box["x"] + mrz_box["w"]) * w + pad_x))
        y2 = min(h, int((mrz_box["y"] + mrz_box["h"]) * h + pad_y))
        if y2 > y1 and x2 > x1:
            candidate_crops.append(("detector_padded", rgb_img[y1:y2, x1:x2]))

    # 2. Heuristic bottom 25% crop (standard ICAO physical location)
    candidate_crops.append(("bottom_25pct", rgb_img[int(h * 0.75):, :]))

    # Run variants across candidate crops
    best_candidate: Optional[Dict[str, Any]] = None

    for crop_name, crop_mat in candidate_crops:
        variants = generate_mrz_variants(crop_mat, num_lines=2)
        for var_idx, var_img in enumerate(variants):
            try:
                res, _ = ocr_runner(var_img)
            except Exception:
                continue

            if not res:
                continue

            lines = [line[1] for line in res]
            text = "\n".join(lines)
            parsed = parse_mrz(text)

            if parsed.get("valid"):
                parsed["extraction_method"] = f"{crop_name}_var{var_idx}"
                return parsed

            if best_candidate is None and parsed.get("format"):
                best_candidate = parsed
                best_candidate["extraction_method"] = f"{crop_name}_var{var_idx}"

    return best_candidate or {"valid": False, "error": "MRZ could not be parsed with valid check digits."}
