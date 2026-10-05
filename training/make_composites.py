"""Synthetic Perspective Composite Generator for Document Detection.

Generates realistic perspective-distorted document images on diverse backgrounds
with glare, shadow gradients, blur, JPEG compression artifacts, and partial occlusions.
Labels are mathematically derived from transformed 4-corner perspective coordinates.

Strict Rule: NO horizontal or vertical flipping (preserves text orientation).
"""

from __future__ import annotations

import argparse
import logging
import math
import random
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


def generate_perspective_composite(
    card_img: Image.Image,
    bg_img: Image.Image,
    seed: Optional[int] = None,
    scale_range: Tuple[float, float] = (0.4, 0.9),
    rotation_range: Tuple[float, float] = (-35.0, 35.0),
    perspective_jitter: float = 0.12,
    add_glare: bool = True,
    add_shadow: bool = True,
    add_occlusion: bool = True,
) -> Tuple[Image.Image, Tuple[float, float, float, float]]:
    """Compose card onto background with perspective distortion and realistic artifacts.

    Returns:
        (composite_image, (norm_cx, norm_cy, norm_w, norm_h))
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    bg_w, bg_h = bg_img.size
    card_w, card_h = card_img.size

    # Scale target dimensions
    target_scale = random.uniform(scale_range[0], scale_range[1])
    scale_factor = (min(bg_w, bg_h) * target_scale) / max(card_w, card_h)
    new_card_w = max(40, int(card_w * scale_factor))
    new_card_h = max(25, int(card_h * scale_factor))
    resized_card = card_img.resize((new_card_w, new_card_h), Image.Resampling.BILINEAR)

    # 4 Source corners
    src_pts = np.float32([
        [0, 0],
        [new_card_w, 0],
        [new_card_w, new_card_h],
        [0, new_card_h],
    ])

    # Rotation and placement
    angle = random.uniform(rotation_range[0], rotation_range[1])
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    # Center placement inside background bounds with safety margin
    margin_x = int(bg_w * 0.1)
    margin_y = int(bg_h * 0.1)
    cx = random.randint(margin_x, max(margin_x + 1, bg_w - margin_x))
    cy = random.randint(margin_y, max(margin_y + 1, bg_h - margin_y))

    # Base rotated corners around center
    half_w = new_card_w / 2.0
    half_h = new_card_h / 2.0
    base_offsets = [
        (-half_w, -half_h),
        (half_w, -half_h),
        (half_w, half_h),
        (-half_w, half_h),
    ]

    dst_pts_list = []
    for ox, oy in base_offsets:
        rx = ox * cos_a - oy * sin_a
        ry = ox * sin_a + oy * cos_a
        # Add perspective jitter per corner
        jx = random.uniform(-perspective_jitter, perspective_jitter) * new_card_w
        jy = random.uniform(-perspective_jitter, perspective_jitter) * new_card_h
        dst_pts_list.append([cx + rx + jx, cy + ry + jy])

    dst_pts = np.float32(dst_pts_list)

    # Homography matrix
    H = cv2.getPerspectiveTransform(src_pts, dst_pts)

    card_cv = cv2.cvtColor(np.array(resized_card), cv2.COLOR_RGB2BGR)
    bg_cv = cv2.cvtColor(np.array(bg_img), cv2.COLOR_RGB2BGR)

    # Mask for warped card
    mask_src = np.full((new_card_h, new_card_w), 255, dtype=np.uint8)
    warped_card = cv2.warpPerspective(card_cv, H, (bg_w, bg_h), borderMode=cv2.BORDER_CONSTANT)
    warped_mask = cv2.warpPerspective(mask_src, H, (bg_w, bg_h), borderMode=cv2.BORDER_CONSTANT)

    # Shadow gradient under the card
    if add_shadow and random.random() < 0.7:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        shadow_mask = cv2.dilate(warped_mask, kernel, iterations=1)
        shadow_mask = cv2.GaussianBlur(shadow_mask, (21, 21), 0)
        shadow_layer = np.zeros_like(bg_cv, dtype=np.float32)
        alpha_shadow = (shadow_mask.astype(np.float32) / 255.0) * random.uniform(0.15, 0.45)
        for c in range(3):
            bg_cv[:, :, c] = bg_cv[:, :, c] * (1.0 - alpha_shadow)

    # Blend warped card into background
    norm_mask = (warped_mask.astype(np.float32) / 255.0)[:, :, np.newaxis]
    comp_cv = (warped_card.astype(np.float32) * norm_mask) + (bg_cv.astype(np.float32) * (1.0 - norm_mask))
    comp_cv = np.clip(comp_cv, 0, 255).astype(np.uint8)

    # Add realistic glare blob
    if add_glare and random.random() < 0.5:
        gx = random.randint(int(min(dst_pts[:, 0])), int(max(dst_pts[:, 0])))
        gy = random.randint(int(min(dst_pts[:, 1])), int(max(dst_pts[:, 1])))
        if 0 <= gx < bg_w and 0 <= gy < bg_h:
            glare_r = random.randint(15, 45)
            glare_overlay = np.zeros((bg_h, bg_w), dtype=np.uint8)
            cv2.circle(glare_overlay, (gx, gy), glare_r, 255, -1)
            glare_overlay = cv2.GaussianBlur(glare_overlay, (31, 31), 0)
            glare_alpha = (glare_overlay.astype(np.float32) / 255.0)[:, :, np.newaxis] * random.uniform(0.3, 0.7)
            comp_cv = np.clip(comp_cv.astype(np.float32) + (glare_alpha * 220), 0, 255).astype(np.uint8)

    # Partial occlusion (finger or object blob <= 15% of card area)
    if add_occlusion and random.random() < 0.35:
        edge_pt = dst_pts[random.randint(0, 3)]
        occ_x = int(edge_pt[0])
        occ_y = int(edge_pt[1])
        occ_r = random.randint(12, int(min(new_card_w, new_card_h) * 0.28))
        color = (random.randint(120, 210), random.randint(100, 180), random.randint(90, 160))
        cv2.circle(comp_cv, (occ_x, occ_y), occ_r, color, -1)

    # Convert back to PIL for color/filter tweaks
    comp_pil = Image.fromarray(cv2.cvtColor(comp_cv, cv2.COLOR_BGR2RGB))

    # Brightness / Contrast jitter
    if random.random() < 0.6:
        comp_pil = ImageEnhance.Brightness(comp_pil).enhance(random.uniform(0.85, 1.15))
    if random.random() < 0.6:
        comp_pil = ImageEnhance.Contrast(comp_pil).enhance(random.uniform(0.85, 1.2))

    # Defocus or slight motion blur
    if random.random() < 0.3:
        comp_pil = comp_pil.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 1.2)))

    # Compute bounding box from dst_pts clipped to image boundaries
    min_x = max(0.0, float(np.min(dst_pts[:, 0])))
    min_y = max(0.0, float(np.min(dst_pts[:, 1])))
    max_x = min(float(bg_w), float(np.max(dst_pts[:, 0])))
    max_y = min(float(bg_h), float(np.max(dst_pts[:, 1])))

    box_w = max_x - min_x
    box_h = max_y - min_y
    cx_norm = (min_x + box_w / 2.0) / bg_w
    cy_norm = (min_y + box_h / 2.0) / bg_h
    w_norm = box_w / bg_w
    h_norm = box_h / bg_h

    return comp_pil, (
        round(cx_norm, 6),
        round(cy_norm, 6),
        round(w_norm, 6),
        round(h_norm, 6),
    )


def generate_composite_batch(
    card_images: List[Path],
    bg_images: List[Path],
    output_dir: Path,
    num_samples: int = 500,
    seed: int = 42,
) -> int:
    """Generate a batch of composites saved with standard YOLO label text files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    labels_dir = output_dir / "labels"
    images_dir.mkdir(exist_ok=True)
    labels_dir.mkdir(exist_ok=True)

    random.seed(seed)
    count = 0

    for i in range(num_samples):
        card_p = random.choice(card_images)
        bg_p = random.choice(bg_images) if bg_images else None

        try:
            with Image.open(card_p) as c_im:
                card = c_im.convert("RGB")
        except Exception:
            continue

        if bg_p and bg_p.exists():
            try:
                with Image.open(bg_p) as b_im:
                    bg = b_im.convert("RGB").resize((640, 640))
            except Exception:
                bg = Image.new("RGB", (640, 640), color=(random.randint(60, 200), random.randint(60, 200), random.randint(60, 200)))
        else:
            bg = Image.new("RGB", (640, 640), color=(random.randint(60, 200), random.randint(60, 200), random.randint(60, 200)))

        comp, (cx, cy, w, h) = generate_perspective_composite(card, bg, seed=seed + i)
        out_name = f"comp_{i:05d}"
        comp.save(images_dir / f"{out_name}.jpg", quality=random.randint(60, 95))
        (labels_dir / f"{out_name}.txt").write_text(f"0 {cx} {cy} {w} {h}\n", encoding="utf-8")
        count += 1

    return count
