"""Generate print-ready A4 PDF specimen sheets at 300 DPI (ID-1 size 85.6 x 54 mm).

Features:
- Exact ID-1 physical dimensions (85.6 mm x 54.0 mm = 1011 x 638 px @ 300 DPI)
- 8 cards per A4 sheet (2 columns x 4 rows) with cutting guides
- 5 generic Indian document layouts:
  1. Aadhaar PVC style
  2. Aadhaar letter strip style
  3. PAN card style
  4. Voter ID (EPIC) style
  5. Driving Licence (MoRTH smart card) style
- Every card carries a prominent diagonal "SPECIMEN – NOT A VALID DOCUMENT" watermark.
- Zero real citizen data (obvious sample strings: "SAMPLE NAME", "0000 0000 0000").
- Zero government emblems or protected insignia: purely geometric placeholder shapes.
- Deterministic output (seed=42). Output saved to training/indian_specimens/out/.
"""

from __future__ import annotations

import math
import os
import random
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# A4 dimensions at 300 DPI
A4_WIDTH = 2480
A4_HEIGHT = 3508

# ID-1 Card dimensions at 300 DPI (85.6 mm x 53.98 mm)
CARD_WIDTH = 1011
CARD_HEIGHT = 638

OUT_DIR = Path(__file__).resolve().parent / "out"


def _draw_diagonal_watermark(card: Image.Image, text: str = "SPECIMEN – NOT A VALID DOCUMENT") -> None:
    """Overlay a bold, semi-transparent diagonal red watermark across the card."""
    overlay = Image.new("RGBA", card.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = 38
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    # Calculate center and diagonal angle
    cx, cy = card.width / 2.0, card.height / 2.0
    angle_deg = -28.0

    # Draw text onto a rotated canvas
    txt_layer = Image.new("RGBA", (card.width * 2, 200), (255, 255, 255, 0))
    tdraw = ImageDraw.Draw(txt_layer)
    # Bounding box for center
    bbox = tdraw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (txt_layer.width - tw) / 2.0
    ty = (txt_layer.height - th) / 2.0
    
    # Red translucent banner
    tdraw.rectangle([tx - 20, ty - 6, tx + tw + 20, ty + th + 6], fill=(220, 20, 20, 45), outline=(200, 0, 0, 180), width=3)
    tdraw.text((tx, ty), text, font=font, fill=(180, 0, 0, 210))

    rotated_layer = txt_layer.rotate(angle_deg, resample=Image.Resampling.BILINEAR, expand=True)
    rx = int(cx - rotated_layer.width / 2.0)
    ry = int(cy - rotated_layer.height / 2.0)
    
    card_rgba = card.convert("RGBA")
    card_rgba.alpha_composite(rotated_layer, (rx, ry))
    card.paste(card_rgba.convert("RGB"))


def _draw_placeholder_photo(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int]) -> None:
    """Draw a neutral geometric silhouette placeholder in place of a human face photo."""
    x1, y1, x2, y2 = box
    draw.rectangle([x1, y1, x2, y2], fill=(230, 235, 240), outline=(120, 130, 140), width=2)
    pw = x2 - x1
    ph = y2 - y1
    # Silhouette head
    head_r = int(pw * 0.22)
    hx = x1 + pw // 2
    hy = y1 + int(ph * 0.35)
    draw.ellipse([hx - head_r, hy - head_r, hx + head_r, hy + head_r], fill=(160, 175, 190))
    # Silhouette shoulders
    sw = int(pw * 0.38)
    sh = int(ph * 0.35)
    draw.ellipse([hx - sw, y1 + int(ph * 0.55), hx + sw, y1 + int(ph * 1.15)], fill=(160, 175, 190))
    # Photo label
    draw.text((x1 + 10, y2 - 24), "SAMPLE PHOTO", fill=(100, 110, 120))


def _draw_placeholder_qr(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], rng: random.Random) -> None:
    """Draw a generic QR code / 2D barcode placeholder."""
    x1, y1, x2, y2 = box
    draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255), outline=(60, 60, 60), width=2)
    qw = x2 - x1
    cell_size = max(4, qw // 18)
    for row in range(y1 + 4, y2 - 4, cell_size):
        for col in range(x1 + 4, x2 - 4, cell_size):
            if rng.random() > 0.45:
                draw.rectangle([col, row, col + cell_size - 1, row + cell_size - 1], fill=(20, 20, 20))
    # Finder patterns at 3 corners
    for fx, fy in [(x1 + 6, y1 + 6), (x2 - cell_size * 5 - 6, y1 + 6), (x1 + 6, y2 - cell_size * 5 - 6)]:
        draw.rectangle([fx, fy, fx + cell_size * 5, fy + cell_size * 5], fill=(20, 20, 20))
        draw.rectangle([fx + cell_size, fy + cell_size, fx + cell_size * 4, fy + cell_size * 4], fill=(255, 255, 255))
        draw.rectangle([fx + cell_size * 2, fy + cell_size * 2, fx + cell_size * 3, fy + cell_size * 3], fill=(20, 20, 20))


def render_design_aadhaar_pvc(rng: random.Random) -> Image.Image:
    """Design 1: Generic Aadhaar PVC card layout with top banner, photo, and 12-digit mock UID."""
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(252, 252, 250))
    draw = ImageDraw.Draw(card)
    
    # Outer border & subtle guilloche lines
    draw.rounded_rectangle([4, 4, CARD_WIDTH - 4, CARD_HEIGHT - 4], radius=24, outline=(180, 180, 180), width=3)
    
    # Top banner strip (tricolor motif: saffron, white, green bars)
    draw.rectangle([6, 6, CARD_WIDTH - 6, 40], fill=(255, 153, 51))
    draw.rectangle([6, 40, CARD_WIDTH - 6, 74], fill=(255, 255, 255))
    draw.rectangle([6, 74, CARD_WIDTH - 6, 108], fill=(19, 136, 8))
    
    # Header placeholder text
    draw.text((120, 44), "UNIQUE IDENTIFICATION AUTHORITY OF INDIA - SPECIMEN", fill=(40, 40, 40))
    
    # Geometric shield emblem placeholder (NOT Ashoka pillar)
    draw.polygon([(40, 20), (80, 20), (80, 70), (60, 95), (40, 70)], fill=(0, 0, 128), outline=(255, 255, 255), width=2)
    draw.ellipse([50, 40, 70, 60], fill=(255, 255, 255))
    
    # Photo box
    photo_box = (60, 150, 290, 450)
    _draw_placeholder_photo(draw, photo_box)
    
    # Textual fields
    draw.text((340, 170), "Name / नाम :", fill=(100, 100, 100))
    draw.text((340, 200), "SAMPLE CITIZEN NAME", fill=(10, 10, 10))
    
    draw.text((340, 250), "DOB / जन्म तिथि :", fill=(100, 100, 100))
    draw.text((340, 280), "01/01/1990", fill=(10, 10, 10))
    
    draw.text((340, 330), "Gender / लिंग :", fill=(100, 100, 100))
    draw.text((340, 360), "MALE / पुरुष", fill=(10, 10, 10))
    
    # QR code placeholder on right
    qr_box = (CARD_WIDTH - 280, 170, CARD_WIDTH - 60, 390)
    _draw_placeholder_qr(draw, qr_box, rng)
    
    # Large 12-digit mock UID at bottom
    draw.rectangle([60, CARD_HEIGHT - 120, CARD_WIDTH - 60, CARD_HEIGHT - 40], fill=(240, 244, 250), outline=(200, 210, 220), width=2)
    draw.text((280, CARD_HEIGHT - 105), "0000  0000  0000", fill=(180, 0, 0))
    draw.text((310, CARD_HEIGHT - 65), "आधार - आम आदमी का अधिकार (SPECIMEN)", fill=(80, 80, 80))
    
    _draw_diagonal_watermark(card)
    return card


def render_design_aadhaar_letter_strip(rng: random.Random) -> Image.Image:
    """Design 2: Generic Aadhaar letter strip cut-out layout with address and UID."""
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(255, 255, 253))
    draw = ImageDraw.Draw(card)
    
    # Cut dashed line border
    draw.rectangle([4, 4, CARD_WIDTH - 4, CARD_HEIGHT - 4], outline=(150, 150, 150), width=2)
    
    # Red top stripe
    draw.rectangle([6, 6, CARD_WIDTH - 6, 60], fill=(180, 20, 20))
    draw.text((80, 20), "GOVERNMENT OF INDIA - SPECIMEN ENROLMENT SLIP", fill=(255, 255, 255))
    
    # Photo box
    photo_box = (60, 120, 280, 410)
    _draw_placeholder_photo(draw, photo_box)
    
    # Left details
    draw.text((320, 130), "To:", fill=(100, 100, 100))
    draw.text((320, 160), "SAMPLE BENEFICIARY", fill=(20, 20, 20))
    draw.text((320, 200), "S/O SAMPLE PARENT", fill=(50, 50, 50))
    draw.text((320, 230), "HOUSE NO 000, SAMPLE STREET", fill=(50, 50, 50))
    draw.text((320, 260), "SAMPLE CITY, STATE - 000000", fill=(50, 50, 50))
    
    # QR box
    qr_box = (CARD_WIDTH - 270, 130, CARD_WIDTH - 60, 340)
    _draw_placeholder_qr(draw, qr_box, rng)
    
    # Barcode placeholder across middle
    for bx in range(320, CARD_WIDTH - 300, 6):
        w = rng.choice([1, 2, 4])
        draw.rectangle([bx, 310, bx + w, 360], fill=(0, 0, 0))
        
    # Big UID at bottom
    draw.rectangle([60, CARD_HEIGHT - 130, CARD_WIDTH - 60, CARD_HEIGHT - 35], fill=(245, 245, 245), outline=(180, 180, 180), width=2)
    draw.text((290, CARD_HEIGHT - 110), "0000  0000  0000", fill=(0, 0, 0))
    draw.text((350, CARD_HEIGHT - 65), "VID : 0000 0000 0000 0000", fill=(100, 100, 100))
    
    _draw_diagonal_watermark(card)
    return card


def render_design_pan_card(rng: random.Random) -> Image.Image:
    """Design 3: Generic Permanent Account Number (PAN) card layout with cyan tint."""
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(228, 244, 248))
    draw = ImageDraw.Draw(card)
    
    # Guilloche wave background simulation
    for y in range(0, CARD_HEIGHT, 16):
        draw.line([(0, y), (CARD_WIDTH, y + int(math.sin(y / 20.0) * 10))], fill=(215, 235, 240), width=1)
        
    draw.rounded_rectangle([4, 4, CARD_WIDTH - 4, CARD_HEIGHT - 4], radius=24, outline=(140, 170, 190), width=3)
    
    # Header: Income Tax Department
    draw.rectangle([6, 6, CARD_WIDTH - 6, 70], fill=(20, 60, 110))
    draw.text((80, 24), "INCOME TAX DEPARTMENT - GOVT OF INDIA (SPECIMEN)", fill=(255, 255, 255))
    
    # QR code placeholder top-right
    qr_box = (CARD_WIDTH - 220, 100, CARD_WIDTH - 60, 260)
    _draw_placeholder_qr(draw, qr_box, rng)
    
    # Photo top-left
    photo_box = (60, 120, 270, 390)
    _draw_placeholder_photo(draw, photo_box)
    
    # Details
    draw.text((310, 120), "Permanent Account Number Card / स्थायी लेखा संख्या कार्ड", fill=(60, 70, 80))
    draw.text((310, 160), "ABCDE1234F", fill=(10, 30, 90))
    
    draw.text((310, 220), "Name / नाम :", fill=(100, 110, 120))
    draw.text((310, 250), "SAMPLE TAXPAYER NAME", fill=(10, 10, 10))
    
    draw.text((310, 300), "Father's Name / पिता का नाम :", fill=(100, 110, 120))
    draw.text((310, 330), "SAMPLE FATHER NAME", fill=(10, 10, 10))
    
    draw.text((310, 380), "Date of Birth / जन्म की तारीख :", fill=(100, 110, 120))
    draw.text((310, 410), "01/01/1990", fill=(10, 10, 10))
    
    # Signature box bottom right
    draw.rectangle([CARD_WIDTH - 360, CARD_HEIGHT - 130, CARD_WIDTH - 60, CARD_HEIGHT - 40], fill=(255, 255, 255), outline=(160, 160, 160), width=2)
    draw.text((CARD_WIDTH - 320, CARD_HEIGHT - 100), "Sample Signature", fill=(120, 120, 140))
    draw.text((CARD_WIDTH - 340, CARD_HEIGHT - 35), "हस्ताक्षर / Signature", fill=(80, 80, 80))
    
    _draw_diagonal_watermark(card)
    return card


def render_design_voter_id(rng: random.Random) -> Image.Image:
    """Design 4: Generic Voter ID (EPIC) smart card layout."""
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(248, 250, 252))
    draw = ImageDraw.Draw(card)
    
    draw.rounded_rectangle([4, 4, CARD_WIDTH - 4, CARD_HEIGHT - 4], radius=24, outline=(170, 175, 180), width=3)
    
    # Top header bar
    draw.rectangle([6, 6, CARD_WIDTH - 6, 80], fill=(30, 40, 55))
    draw.text((90, 28), "ELECTION COMMISSION OF INDIA - SPECIMEN IDENTITY CARD", fill=(255, 255, 255))
    
    # Silver hologram strip placeholder
    draw.rectangle([CARD_WIDTH - 140, 100, CARD_WIDTH - 60, CARD_HEIGHT - 100], fill=(210, 215, 225), outline=(160, 170, 180), width=2)
    draw.text((CARD_WIDTH - 130, 260), "HOLO", fill=(130, 140, 150))
    
    # Photo box
    photo_box = (60, 130, 280, 420)
    _draw_placeholder_photo(draw, photo_box)
    
    # EPIC number box
    draw.rectangle([320, 120, 680, 170], fill=(235, 240, 245), outline=(180, 190, 200), width=2)
    draw.text((340, 132), "EPIC NO:  XYZ0000000", fill=(10, 10, 10))
    
    draw.text((320, 200), "Elector Name / निर्वाचक का नाम :", fill=(100, 100, 100))
    draw.text((320, 230), "SAMPLE ELECTOR NAME", fill=(10, 10, 10))
    
    draw.text((320, 280), "Relation Name / संबंध का नाम :", fill=(100, 100, 100))
    draw.text((320, 310), "SAMPLE RELATION", fill=(10, 10, 10))
    
    draw.text((320, 360), "Gender / लिंग :", fill=(100, 100, 100))
    draw.text((320, 390), "FEMALE / महिला    Age: 32", fill=(10, 10, 10))
    
    # Bottom footer
    draw.line([(60, CARD_HEIGHT - 70), (CARD_WIDTH - 160, CARD_HEIGHT - 70)], fill=(200, 200, 200), width=2)
    draw.text((120, CARD_HEIGHT - 55), "ELECTORAL REGISTRATION OFFICER - NOT VALID FOR IDENTITY", fill=(120, 120, 120))
    
    _draw_diagonal_watermark(card)
    return card


def render_design_driving_licence(rng: random.Random) -> Image.Image:
    """Design 5: Generic Driving Licence smart card layout with chip placeholder."""
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(250, 252, 248))
    draw = ImageDraw.Draw(card)
    
    draw.rounded_rectangle([4, 4, CARD_WIDTH - 4, CARD_HEIGHT - 4], radius=24, outline=(160, 175, 160), width=3)
    
    # Dual color header band (Indian MoRTH style: green & yellow)
    draw.rectangle([6, 6, CARD_WIDTH - 6, 45], fill=(20, 110, 50))
    draw.rectangle([6, 45, CARD_WIDTH - 6, 85], fill=(230, 180, 30))
    draw.text((100, 15), "UNION OF INDIA - DRIVING LICENCE SPECIMEN", fill=(255, 255, 255))
    draw.text((100, 54), "TRANSPORT DEPARTMENT - FORM 7 SMART CARD", fill=(20, 30, 20))
    
    # Photo box
    photo_box = (60, 130, 270, 410)
    _draw_placeholder_photo(draw, photo_box)
    
    # Smart Card Microchip Contact Pad placeholder
    chip_x1, chip_y1, chip_x2, chip_y2 = (300, 140, 440, 250)
    draw.rounded_rectangle([chip_x1, chip_y1, chip_x2, chip_y2], radius=10, fill=(215, 185, 95), outline=(160, 135, 60), width=2)
    draw.line([(chip_x1 + 45, chip_y1), (chip_x1 + 45, chip_y2)], fill=(160, 135, 60), width=2)
    draw.line([(chip_x2 - 45, chip_y1), (chip_x2 - 45, chip_y2)], fill=(160, 135, 60), width=2)
    draw.line([(chip_x1, chip_y1 + 55), (chip_x2, chip_y1 + 55)], fill=(160, 135, 60), width=2)
    
    # Licence No
    draw.text((470, 140), "DL NO:", fill=(100, 100, 100))
    draw.text((470, 170), "DL-0120230000001", fill=(10, 60, 20))
    draw.text((470, 210), "VALIDITY: 01/01/2040", fill=(80, 80, 80))
    
    # Holder details
    draw.text((300, 280), "Name:", fill=(100, 100, 100))
    draw.text((380, 280), "SAMPLE DRIVER HOLDER", fill=(10, 10, 10))
    
    draw.text((300, 320), "DOB:", fill=(100, 100, 100))
    draw.text((380, 320), "01/01/1990    Blood: O+", fill=(10, 10, 10))
    
    draw.text((300, 360), "Vehicle Class:", fill=(100, 100, 100))
    draw.text((440, 360), "MCWG, LMV-NT", fill=(10, 10, 10))
    
    # QR code placeholder on right
    qr_box = (CARD_WIDTH - 240, 230, CARD_WIDTH - 60, 410)
    _draw_placeholder_qr(draw, qr_box, rng)
    
    _draw_diagonal_watermark(card)
    return card


def build_specimen_sheet_a4(cards: List[Image.Image], sheet_num: int = 1) -> Image.Image:
    """Compose 8 ID-1 cards onto a 300 DPI A4 canvas with cutting guides."""
    sheet = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), color=(255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    
    # 2 columns x 4 rows
    col_spacing = (A4_WIDTH - (2 * CARD_WIDTH)) // 3
    row_spacing = (A4_HEIGHT - (4 * CARD_HEIGHT)) // 5
    
    positions = []
    for r in range(4):
        for c in range(2):
            x = col_spacing + c * (CARD_WIDTH + col_spacing)
            y = row_spacing + r * (CARD_HEIGHT + row_spacing)
            positions.append((x, y))
            
    # Page header text (outside cards)
    draw.text((col_spacing, 30), f"SIH26188 INDIAN SPECIMEN CARD SHEET #{sheet_num} - PRINT AT 100% SCALE (DO NOT FIT TO PAGE)", fill=(80, 80, 80))
    draw.text((col_spacing, 65), "Each card is calibrated to standard ID-1 format (85.6 mm x 54.0 mm). Cut along guidelines.", fill=(120, 120, 120))
    
    for idx, (x, y) in enumerate(positions):
        if idx >= len(cards):
            break
        card = cards[idx]
        sheet.paste(card, (x, y))
        
        # Draw cutting crop marks around each card (hairline corner ticks)
        tick_len = 25
        # Top-left corner
        draw.line([(x - tick_len, y), (x - 2, y)], fill=(120, 120, 120), width=2)
        draw.line([(x, y - tick_len), (x, y - 2)], fill=(120, 120, 120), width=2)
        # Top-right corner
        draw.line([(x + CARD_WIDTH + 2, y), (x + CARD_WIDTH + tick_len, y)], fill=(120, 120, 120), width=2)
        draw.line([(x + CARD_WIDTH, y - tick_len), (x + CARD_WIDTH, y - 2)], fill=(120, 120, 120), width=2)
        # Bottom-left corner
        draw.line([(x - tick_len, y + CARD_HEIGHT), (x - 2, y + CARD_HEIGHT)], fill=(120, 120, 120), width=2)
        draw.line([(x, y + CARD_HEIGHT + 2), (x, y + CARD_HEIGHT + tick_len)], fill=(120, 120, 120), width=2)
        # Bottom-right corner
        draw.line([(x + CARD_WIDTH + 2, y + CARD_HEIGHT), (x + CARD_WIDTH + tick_len, y + CARD_HEIGHT)], fill=(120, 120, 120), width=2)
        draw.line([(x + CARD_WIDTH, y + CARD_HEIGHT + 2), (x + CARD_WIDTH, y + CARD_HEIGHT + tick_len)], fill=(120, 120, 120), width=2)
        
    return sheet


def generate_all_sheets(out_dir: Path = OUT_DIR) -> List[Path]:
    """Generate print-ready A4 PDF specimen sheets."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    
    renderers = [
        ("aadhaar_pvc", render_design_aadhaar_pvc),
        ("aadhaar_letter", render_design_aadhaar_letter_strip),
        ("pan_card", render_design_pan_card),
        ("voter_id", render_design_voter_id),
        ("driving_licence", render_design_driving_licence),
    ]
    
    # Sheet 1: Contains 8 cards across the 5 designs (repeating some for 8 cards)
    sheet1_cards = [
        render_design_aadhaar_pvc(rng),
        render_design_pan_card(rng),
        render_design_aadhaar_letter_strip(rng),
        render_design_voter_id(rng),
        render_design_driving_licence(rng),
        render_design_aadhaar_pvc(rng),
        render_design_pan_card(rng),
        render_design_driving_licence(rng),
    ]
    sheet1 = build_specimen_sheet_a4(sheet1_cards, sheet_num=1)
    
    # Sheet 2: Second sheet with variations
    sheet2_cards = [
        render_design_voter_id(rng),
        render_design_aadhaar_letter_strip(rng),
        render_design_driving_licence(rng),
        render_design_pan_card(rng),
        render_design_aadhaar_pvc(rng),
        render_design_voter_id(rng),
        render_design_aadhaar_letter_strip(rng),
        render_design_pan_card(rng),
    ]
    sheet2 = build_specimen_sheet_a4(sheet2_cards, sheet_num=2)
    
    pdf_path = out_dir / "indian_specimen_sheets_300dpi.pdf"
    sheet1.save(
        pdf_path,
        "PDF",
        resolution=300.0,
        save_all=True,
        append_images=[sheet2],
    )
    print(f"[make_specimen_sheets] Wrote 2-page print-ready A4 PDF (16 cards total, 300 DPI) to {pdf_path}")
    
    # Also save page 1 and page 2 as preview JPEGs
    sheet1_jpg = out_dir / "sheet_1_preview.jpg"
    sheet1.save(sheet1_jpg, quality=85)
    sheet2_jpg = out_dir / "sheet_2_preview.jpg"
    sheet2.save(sheet2_jpg, quality=85)
    
    return [pdf_path, sheet1_jpg, sheet2_jpg]


if __name__ == "__main__":
    generate_all_sheets()
