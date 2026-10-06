"""Shared Procedural Synthetic Field Generator (NO-CAP / SIH26188).

Renders synthetic cards with EXACT field bounding boxes for:
- Aadhaar-style
- PAN card
- Voter ID (EPIC)
- Driving Licence
- Nepali Nagarikta (Citizenship, Devanagari + Latin)
- Bhutanese CID (Citizenship Identity Card, Dzongkha + Latin)

Schema (Appendix D - ID-fields detector):
["Photo", "Name", "ID_No", "DOB", "Gender", "Address", "Father_Name", "Issue_Date", "Expiry_Date", "Signature"]

Privacy & Compliance:
- Obvious fake data only ("SAMPLE NAME", "0000 0000 0000")
- Prominent "SPECIMEN – NOT A VALID DOCUMENT" watermark
- Zero government emblems or official seals (geometric placeholders only)
- Uses local Windows fonts (Nirmala UI for Devanagari, Microsoft Himalaya for Tibetan/Dzongkha, Arial/Segoe for Latin)
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ID-1 dimensions at 300 DPI
CARD_W = 1011
CARD_H = 638

FIELD_CLASSES = [
    "Photo",
    "Name",
    "ID_No",
    "DOB",
    "Gender",
    "Address",
    "Father_Name",
    "Issue_Date",
    "Expiry_Date",
    "Signature",
]

DOC_TYPES = [
    "aadhaar",
    "pan",
    "voter_id",
    "driving_licence",
    "passport",
    "nepali_citizenship",
    "bhutan_cid",
    "other",
]


def _get_font(font_name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Safely load font from Windows Fonts or fallback to default."""
    candidates = [
        font_name,
        f"C:/Windows/Fonts/{font_name}",
        f"C:/Windows/Fonts/{font_name}.ttf",
        f"C:/Windows/Fonts/{font_name}.ttc",
        "arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if os.path.exists(c) or not c.startswith("C:/"):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_watermark(im: Image.Image) -> None:
    """Diagonal translucent watermark."""
    overlay = Image.new("RGBA", im.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    font = _get_font("arialbd.ttf", 36)
    text = "SPECIMEN – NOT A VALID DOCUMENT"

    cx, cy = im.width / 2.0, im.height / 2.0
    txt_layer = Image.new("RGBA", (im.width * 2, 160), (255, 255, 255, 0))
    tdraw = ImageDraw.Draw(txt_layer)
    bbox = tdraw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (txt_layer.width - tw) / 2.0
    ty = (txt_layer.height - th) / 2.0

    tdraw.rectangle([tx - 20, ty - 6, tx + tw + 20, ty + th + 6], fill=(220, 30, 30, 45), outline=(200, 20, 20, 180), width=3)
    tdraw.text((tx, ty), text, font=font, fill=(180, 20, 20, 210))

    rotated = txt_layer.rotate(-26.0, resample=Image.Resampling.BILINEAR, expand=True)
    rx = int(cx - rotated.width / 2.0)
    ry = int(cy - rotated.height / 2.0)

    im_rgba = im.convert("RGBA")
    im_rgba.alpha_composite(rotated, (rx, ry))
    im.paste(im_rgba.convert("RGB"))


def _draw_placeholder_photo(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], rng: random.Random) -> None:
    x1, y1, x2, y2 = box
    draw.rectangle([x1, y1, x2, y2], fill=(215, 225, 235), outline=(100, 120, 140), width=2)
    w = x2 - x1
    h = y2 - y1
    cx = x1 + w // 2
    r_head = int(min(w, h) * 0.22)
    cy_head = y1 + int(h * 0.35)
    draw.ellipse([cx - r_head, cy_head - r_head, cx + r_head, cy_head + r_head], fill=(120, 140, 160))
    sh_top = cy_head + r_head + int(h * 0.05)
    draw.chord([x1 + int(w * 0.15), sh_top, x2 - int(w * 0.15), y2 - 2], start=0, end=180, fill=(90, 110, 130))


def _draw_placeholder_signature(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], rng: random.Random) -> None:
    x1, y1, x2, y2 = box
    draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255, 230), outline=(160, 160, 160), width=1)
    pts = []
    w = x2 - x1
    h = y2 - y1
    num_pts = rng.randint(6, 12)
    cur_x = x1 + 10
    cur_y = y1 + h // 2
    for _ in range(num_pts):
        nxt_x = min(x2 - 10, cur_x + rng.randint(15, 45))
        nxt_y = y1 + rng.randint(int(h * 0.2), int(h * 0.8))
        pts.append((cur_x, cur_y))
        cur_x, cur_y = nxt_x, nxt_y
    if len(pts) >= 2:
        draw.line(pts, fill=(20, 40, 100), width=3)


def render_card_with_fields(
    doc_type: str,
    design_id: int,
    seed: int,
) -> Tuple[Image.Image, List[Dict[str, Any]]]:
    """Render a card specimen for a specific document type and return (image, list of field bounding boxes).
    Field box format: {"label": str, "x": int, "y": int, "w": int, "h": int, "text": str} in pixel coordinates.
    """
    rng = random.Random(seed + design_id * 1000)
    card = Image.new("RGB", (CARD_W, CARD_H), color=(248, 249, 250))
    draw = ImageDraw.Draw(card)
    fields: List[Dict[str, Any]] = []

    def record_text_field(label: str, x: int, y: int, text: str, font: Any, color: Tuple[int, int, int]) -> None:
        draw.text((x, y), text, font=font, fill=color)
        bbox = draw.textbbox((x, y), text, font=font)
        # Pad by 2px
        bx = max(0, bbox[0] - 2)
        by = max(0, bbox[1] - 2)
        bw = (bbox[2] - bbox[0]) + 4
        bh = (bbox[3] - bbox[1]) + 4
        fields.append({"label": label, "x": bx, "y": by, "w": bw, "h": bh, "text": text})

    if doc_type == "aadhaar":
        # Header banner
        tint = (rng.randint(230, 255), rng.randint(235, 255), rng.randint(230, 250))
        draw.rectangle([0, 0, CARD_W, CARD_H], fill=tint)
        draw.rectangle([0, 0, CARD_W, 75], fill=(230, 85, 25))
        draw.rectangle([0, CARD_H - 45, CARD_W, CARD_H], fill=(40, 130, 50))
        
        f_title = _get_font("arialbd.ttf", 26)
        draw.text((CARD_W // 2 - 120, 22), "UNIQUE IDENTITY", font=f_title, fill=(255, 255, 255))

        # Photo
        photo_box = (65, 125, 285, 395)
        _draw_placeholder_photo(draw, photo_box, rng)
        fields.append({"label": "Photo", "x": photo_box[0], "y": photo_box[1], "w": photo_box[2] - photo_box[0], "h": photo_box[3] - photo_box[1], "text": ""})

        f_name = _get_font("arialbd.ttf", 28)
        f_body = _get_font("arial.ttf", 24)
        f_num = _get_font("arialbd.ttf", 36)

        record_text_field("Name", 325, 140, "SAMPLE CITIZEN NAME", f_name, (20, 20, 20))
        record_text_field("DOB", 325, 195, "DOB: 01/01/1990", f_body, (30, 30, 30))
        record_text_field("Gender", 325, 240, "GENDER: MALE", f_body, (30, 30, 30))
        record_text_field("Address", 325, 285, "ADDRESS: SAMPLE STREET, NEW DELHI, 110001", f_body, (40, 40, 40))

        # Aadhaar number
        num_str = f"{rng.randint(2000, 9999)} {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}"
        record_text_field("ID_No", 330, 435, num_str, f_num, (180, 20, 20))

    elif doc_type == "pan":
        # Blue gradient / cyan tint
        bg = (rng.randint(215, 235), rng.randint(235, 250), rng.randint(245, 255))
        draw.rectangle([0, 0, CARD_W, CARD_H], fill=bg)
        draw.rectangle([0, 0, CARD_W, 65], fill=(30, 75, 140))
        
        f_hdr = _get_font("arialbd.ttf", 24)
        draw.text((CARD_W // 2 - 130, 18), "INCOME TAX DEPARTMENT", font=f_hdr, fill=(255, 255, 255))

        photo_box = (60, 110, 260, 360)
        _draw_placeholder_photo(draw, photo_box, rng)
        fields.append({"label": "Photo", "x": photo_box[0], "y": photo_box[1], "w": photo_box[2] - photo_box[0], "h": photo_box[3] - photo_box[1], "text": ""})

        f_id = _get_font("arialbd.ttf", 34)
        f_body = _get_font("arial.ttf", 24)
        f_bld = _get_font("arialbd.ttf", 26)

        pan_no = f"ABCDE{rng.randint(1000, 9999)}F"
        record_text_field("ID_No", 295, 115, pan_no, f_id, (10, 30, 80))
        record_text_field("Name", 295, 180, "SAMPLE CITIZEN NAME", f_bld, (20, 20, 20))
        record_text_field("Father_Name", 295, 235, "FATHER: SAMPLE FATHER", f_body, (30, 30, 30))
        record_text_field("DOB", 295, 290, "DOB: 15/08/1985", f_body, (30, 30, 30))

        # Signature
        sig_box = (60, 410, 280, 485)
        _draw_placeholder_signature(draw, sig_box, rng)
        fields.append({"label": "Signature", "x": sig_box[0], "y": sig_box[1], "w": sig_box[2] - sig_box[0], "h": sig_box[3] - sig_box[1], "text": ""})

    elif doc_type == "voter_id":
        # White/cream with burgundy or maroon header
        bg = (rng.randint(240, 255), rng.randint(240, 255), rng.randint(235, 250))
        draw.rectangle([0, 0, CARD_W, CARD_H], fill=bg)
        draw.rectangle([0, 0, CARD_W, 70], fill=(130, 25, 35))

        f_hdr = _get_font("arialbd.ttf", 24)
        draw.text((CARD_W // 2 - 120, 20), "ELECTION COMMISSION", font=f_hdr, fill=(255, 255, 255))

        photo_box = (60, 120, 270, 380)
        _draw_placeholder_photo(draw, photo_box, rng)
        fields.append({"label": "Photo", "x": photo_box[0], "y": photo_box[1], "w": photo_box[2] - photo_box[0], "h": photo_box[3] - photo_box[1], "text": ""})

        f_epic = _get_font("arialbd.ttf", 32)
        f_bld = _get_font("arialbd.ttf", 24)
        f_body = _get_font("arial.ttf", 22)

        epic_no = f"XYZ{rng.randint(1000000, 9999999)}"
        record_text_field("ID_No", 310, 110, epic_no, f_epic, (120, 20, 30))
        record_text_field("Name", 310, 175, "NAME: SAMPLE ELECTOR", f_bld, (20, 20, 20))
        record_text_field("Father_Name", 310, 225, "FATHER: SAMPLE GUARDIAN", f_body, (30, 30, 30))
        record_text_field("Gender", 310, 270, "GENDER: FEMALE", f_body, (30, 30, 30))
        record_text_field("DOB", 310, 315, "DOB / AGE: 28 YEARS", f_body, (30, 30, 30))
        record_text_field("Address", 310, 360, "POLLING STATION: WARD 14, SECTOR 2", f_body, (40, 40, 40))

    elif doc_type == "driving_licence":
        # Green / yellow smartcard tint
        bg = (rng.randint(235, 250), rng.randint(245, 255), rng.randint(230, 245))
        draw.rectangle([0, 0, CARD_W, CARD_H], fill=bg)
        draw.rectangle([0, 0, CARD_W, 70], fill=(20, 100, 60))

        f_hdr = _get_font("arialbd.ttf", 24)
        draw.text((CARD_W // 2 - 140, 20), "UNION OF INDIA DRIVING LICENCE", font=f_hdr, fill=(255, 255, 255))

        photo_box = (60, 110, 250, 350)
        _draw_placeholder_photo(draw, photo_box, rng)
        fields.append({"label": "Photo", "x": photo_box[0], "y": photo_box[1], "w": photo_box[2] - photo_box[0], "h": photo_box[3] - photo_box[1], "text": ""})

        f_dl = _get_font("arialbd.ttf", 30)
        f_bld = _get_font("arialbd.ttf", 24)
        f_body = _get_font("arial.ttf", 22)

        dl_no = f"DL{rng.randint(10, 99)} 2020{rng.randint(1000000, 9999999)}"
        record_text_field("ID_No", 280, 105, dl_no, f_dl, (10, 60, 30))
        record_text_field("Name", 280, 160, "NAME: DRIVER SAMPLE NAME", f_bld, (20, 20, 20))
        record_text_field("DOB", 280, 210, "DOB: 12/04/1988", f_body, (30, 30, 30))
        record_text_field("Issue_Date", 280, 255, "ISSUE DATE: 10/01/2015", f_body, (30, 30, 30))
        record_text_field("Expiry_Date", 280, 300, "VALID TILL: 09/01/2035", f_body, (180, 20, 20))
        record_text_field("Address", 280, 345, "ADDRESS: HOUSE 54, ROAD 12, STATE", f_body, (30, 30, 30))

        sig_box = (60, 400, 250, 470)
        _draw_placeholder_signature(draw, sig_box, rng)
        fields.append({"label": "Signature", "x": sig_box[0], "y": sig_box[1], "w": sig_box[2] - sig_box[0], "h": sig_box[3] - sig_box[1], "text": ""})

    elif doc_type == "nepali_citizenship":
        # Nepali Nagarikta Pramanpatra (bilingual Devanagari + Latin)
        bg = (250, 245, 235)
        draw.rectangle([0, 0, CARD_W, CARD_H], fill=bg)
        draw.rectangle([0, 0, CARD_W, 80], fill=(160, 20, 40))

        f_dev = _get_font("Nirmala.ttc", 26)
        f_dev_sub = _get_font("Nirmala.ttc", 22)
        f_body = _get_font("arial.ttf", 22)
        f_bld = _get_font("arialbd.ttf", 26)

        draw.text((CARD_W // 2 - 130, 12), "नेपाल सरकार (GOVT OF NEPAL)", font=f_dev, fill=(255, 255, 255))
        draw.text((CARD_W // 2 - 140, 45), "नागरिकता प्रमाणपत्र (CITIZENSHIP)", font=f_dev_sub, fill=(255, 255, 255))

        photo_box = (60, 115, 260, 365)
        _draw_placeholder_photo(draw, photo_box, rng)
        fields.append({"label": "Photo", "x": photo_box[0], "y": photo_box[1], "w": photo_box[2] - photo_box[0], "h": photo_box[3] - photo_box[1], "text": ""})

        dist_code = f"27-01-{rng.randint(70, 80)}-{rng.randint(10000, 99999)}"
        record_text_field("ID_No", 290, 110, f"CERT NO: {dist_code}", f_bld, (140, 20, 30))
        record_text_field("Name", 290, 165, "नाम / NAME: SAMPLE THAPA", f_dev, (20, 20, 20))
        record_text_field("Father_Name", 290, 215, "बाबुको नाम: SAMPLE FATHER", f_dev, (30, 30, 30))
        record_text_field("DOB", 290, 265, "DOB (BS): 2045/05/12", f_body, (30, 30, 30))
        record_text_field("Gender", 290, 310, "लिङ्ग / SEX: MALE", f_dev, (30, 30, 30))
        record_text_field("Address", 290, 355, "जिल्ला: KATHMANDU, NEPAL", f_body, (30, 30, 30))
        record_text_field("Issue_Date", 290, 400, "जारी मिति: 2065/08/10", f_dev, (30, 30, 30))

    elif doc_type == "bhutan_cid":
        # Bhutanese Citizenship Identity Card (11-digit CID, Tibetan/Dzongkha + Latin)
        bg = (245, 240, 250)
        draw.rectangle([0, 0, CARD_W, CARD_H], fill=bg)
        draw.rectangle([0, 0, CARD_W, 80], fill=(210, 140, 20))

        f_dz = _get_font("himalaya.ttf", 28)
        f_bld = _get_font("arialbd.ttf", 26)
        f_body = _get_font("arial.ttf", 22)

        draw.text((CARD_W // 2 - 150, 15), "ROYAL GOVERNMENT OF BHUTAN", font=f_bld, fill=(255, 255, 255))
        draw.text((CARD_W // 2 - 100, 48), "CITIZENSHIP CARD", font=f_body, fill=(255, 255, 255))

        photo_box = (60, 115, 260, 365)
        _draw_placeholder_photo(draw, photo_box, rng)
        fields.append({"label": "Photo", "x": photo_box[0], "y": photo_box[1], "w": photo_box[2] - photo_box[0], "h": photo_box[3] - photo_box[1], "text": ""})

        # 11-digit CID starting with 1 or 2
        cid_no = f"{rng.choice([1, 2])}{rng.randint(1000000000, 9999999999)}"
        record_text_field("ID_No", 290, 115, f"CID NO: {cid_no}", f_bld, (160, 90, 10))
        record_text_field("Name", 290, 175, "NAME: DORJI WANGCHUK", f_bld, (20, 20, 20))
        record_text_field("DOB", 290, 230, "DOB: 05/11/1992", f_body, (30, 30, 30))
        record_text_field("Gender", 290, 280, "SEX: MALE", f_body, (30, 30, 30))
        record_text_field("Issue_Date", 290, 330, "ISSUED: 12/02/2012", f_body, (30, 30, 30))
        record_text_field("Expiry_Date", 290, 380, "VALID TILL: 11/02/2032", f_body, (30, 30, 30))

    else:
        # Generic ID-1 document
        draw.rectangle([0, 0, CARD_W, CARD_H], fill=(240, 242, 245), outline=(100, 100, 100), width=4)
        f_bld = _get_font("arialbd.ttf", 26)
        record_text_field("ID_No", 50, 50, f"ID-{rng.randint(10000, 99999)}", f_bld, (10, 10, 10))

    # Apply diagonal watermark
    _draw_watermark(card)
    return card, fields


def composite_card_on_background(
    card_img: Image.Image,
    field_boxes: List[Dict[str, Any]],
    bg_img: Image.Image,
    rng: random.Random,
) -> Tuple[Image.Image, List[Dict[str, Any]], List[float]]:
    """Warp card onto background with perspective distortion, updating all field bounding boxes and card bounding box."""
    bg_w, bg_h = bg_img.size
    cw, ch = card_img.size

    scale = rng.uniform(0.50, 0.75) * (min(bg_w, bg_h) / float(ch))
    tw = int(cw * scale)
    th = int(ch * scale)
    card_resized = card_img.resize((tw, th), Image.Resampling.BILINEAR)

    # Perspective source points
    src_pts = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])

    cx = rng.randint(int(tw * 0.55), bg_w - int(tw * 0.55))
    cy = rng.randint(int(th * 0.55), bg_h - int(th * 0.55))
    angle = rng.uniform(-20.0, 20.0)
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    hw, hh = tw / 2.0, th / 2.0
    jitter = 0.12

    dst_pts = np.float32([
        [cx + (-hw * cos_a - -hh * sin_a) + rng.uniform(-tw * jitter, tw * jitter),
         cy + (-hw * sin_a + -hh * cos_a) + rng.uniform(-th * jitter, th * jitter)],
        [cx + (hw * cos_a - -hh * sin_a) + rng.uniform(-tw * jitter, tw * jitter),
         cy + (hw * sin_a + -hh * cos_a) + rng.uniform(-th * jitter, th * jitter)],
        [cx + (hw * cos_a - hh * sin_a) + rng.uniform(-tw * jitter, tw * jitter),
         cy + (hw * sin_a + hh * cos_a) + rng.uniform(-th * jitter, th * jitter)],
        [cx + (-hw * cos_a - hh * sin_a) + rng.uniform(-tw * jitter, tw * jitter),
         cy + (-hw * sin_a + hh * cos_a) + rng.uniform(-th * jitter, th * jitter)],
    ])

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    card_cv = cv2.cvtColor(np.asarray(card_resized), cv2.COLOR_RGB2BGR)
    warped_card = cv2.warpPerspective(card_cv, M, (bg_w, bg_h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    mask_cv = np.full((th, tw), 255, dtype=np.uint8)
    warped_mask = cv2.warpPerspective(mask_cv, M, (bg_w, bg_h), borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    # Specular glare overlay
    if rng.random() > 0.50:
        gx, gy = int(cx), int(cy)
        glare = np.zeros((bg_h, bg_w), dtype=np.uint8)
        cv2.ellipse(glare, (gx, gy), (rng.randint(60, 160), rng.randint(30, 80)), rng.randint(0, 180), 0, 360, 130, -1)
        glare = cv2.GaussianBlur(glare, (41, 41), 0)
        glare = cv2.bitwise_and(glare, glare, mask=warped_mask)
        warped_card = cv2.add(warped_card, cv2.merge([glare, glare, glare]))

    bg_cv = cv2.cvtColor(np.asarray(bg_img), cv2.COLOR_RGB2BGR)
    mask_3ch = cv2.merge([warped_mask, warped_mask, warped_mask]) / 255.0
    composite = (warped_card * mask_3ch + bg_cv * (1.0 - mask_3ch)).astype(np.uint8)

    if rng.random() > 0.40:
        composite = cv2.GaussianBlur(composite, (3, 3), 0)

    final_pil = Image.fromarray(cv2.cvtColor(composite, cv2.COLOR_BGR2RGB))

    # Transform overall card bounding box
    xs = dst_pts[:, 0]
    ys = dst_pts[:, 1]
    card_box = [max(0.0, float(np.min(xs))), max(0.0, float(np.min(ys))), min(float(bg_w), float(np.max(xs))), min(float(bg_h), float(np.max(ys)))]

    # Transform each individual field box via homography M
    scale_x = tw / float(cw)
    scale_y = th / float(ch)
    transformed_fields = []

    for f in field_boxes:
        # 4 corners in resized card coordinates
        fx1 = f["x"] * scale_x
        fy1 = f["y"] * scale_y
        fx2 = (f["x"] + f["w"]) * scale_x
        fy2 = (f["y"] + f["h"]) * scale_y
        pts_in = np.float32([[[fx1, fy1]], [[fx2, fy1]], [[fx2, fy2]], [[fx1, fy2]]])
        pts_out = cv2.perspectiveTransform(pts_in, M)
        pxs = pts_out[:, 0, 0]
        pys = pts_out[:, 0, 1]

        rx1 = max(0.0, float(np.min(pxs)))
        ry1 = max(0.0, float(np.min(pys)))
        rx2 = min(float(bg_w), float(np.max(pxs)))
        ry2 = min(float(bg_h), float(np.max(pys)))
        rw = rx2 - rx1
        rh = ry2 - ry1

        if rw >= 4.0 and rh >= 4.0:
            transformed_fields.append({
                "label": f["label"],
                "x": rx1,
                "y": ry1,
                "w": rw,
                "h": rh,
                "text": f["text"],
            })

    return final_pil, transformed_fields, card_box
