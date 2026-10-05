"""
Dataset loader and synthetic specimen generator for ML pipeline evaluation (SIH26188).
Generates realistic identity card specimens with optical distortions, glare, and background clutter
without using or persisting any real citizen personal data.
"""

import os
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from typing import List, Dict, Tuple, Any

CARD_CLASSES = ["Card"]
AADHAAR_CLASSES = ["Aadhaar_No", "DOB", "Gender", "Name", "Photo"]


def generate_synthetic_specimen(
    width: int = 1200,
    height: int = 800,
    distortions: bool = True,
) -> Tuple[Image.Image, List[Dict[str, Any]]]:
    """Generate a synthetic identity card against realistic background clutter.
    Returns (image, ground_truth_boxes_normalized).
    """
    # 1. Background (desk, laminate, or textured surface)
    bg_type = random.choice(["wood", "desk", "gray", "white"])
    if bg_type == "wood":
        bg_color = (random.randint(110, 160), random.randint(70, 110), random.randint(40, 70))
    elif bg_type == "desk":
        bg_color = (random.randint(180, 220), random.randint(180, 220), random.randint(190, 230))
    else:
        bg_color = (random.randint(220, 245), random.randint(220, 245), random.randint(220, 245))

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # 2. Card placement (aspect ratio ~1.58:1 typical CR-80 card)
    card_scale = random.uniform(0.65, 0.88)
    card_w = int(width * card_scale)
    card_h = int(card_w / 1.586)

    # Ensure card fits in canvas
    card_x1 = random.randint(20, max(21, width - card_w - 20))
    card_y1 = random.randint(20, max(21, height - card_h - 20))
    card_x2 = card_x1 + card_w
    card_y2 = card_y1 + card_h

    # Card background (white/off-white with subtle government banner header)
    draw.rounded_rectangle(
        [card_x1, card_y1, card_x2, card_y2],
        radius=14,
        fill=(250, 252, 255),
        outline=(180, 180, 180),
        width=2,
    )

    # Header banner (tricolor / empanelment strip)
    header_h = int(card_h * 0.16)
    draw.rectangle([card_x1 + 4, card_y1 + 4, card_x2 - 4, card_y1 + header_h], fill=(230, 240, 255))

    boxes: List[Dict[str, Any]] = []

    # Card boundary ground truth
    boxes.append({
        "label": "Card",
        "class_id": 0,
        "model_type": "card",
        "x1": card_x1 / width,
        "y1": card_y1 / height,
        "x2": card_x2 / width,
        "y2": card_y2 / height,
    })

    # 3. Field placements on card
    # Photo: Left side
    photo_w = int(card_w * 0.22)
    photo_h = int(photo_w * 1.25)
    photo_x1 = card_x1 + int(card_w * 0.08)
    photo_y1 = card_y1 + int(card_h * 0.26)
    photo_x2 = photo_x1 + photo_w
    photo_y2 = photo_y1 + photo_h

    draw.rectangle([photo_x1, photo_y1, photo_x2, photo_y2], fill=(160, 175, 190), outline=(100, 100, 100))
    boxes.append({
        "label": "Photo",
        "class_id": 4,
        "model_type": "aadhaar",
        "x1": photo_x1 / width,
        "y1": photo_y1 / height,
        "x2": photo_x2 / width,
        "y2": photo_y2 / height,
    })

    # Name: Right of photo, top
    name_x1 = photo_x2 + int(card_w * 0.05)
    name_y1 = photo_y1 + int(card_h * 0.04)
    name_w = int(card_w * 0.48)
    name_h = int(card_h * 0.12)
    name_x2 = name_x1 + name_w
    name_y2 = name_y1 + name_h

    draw.rectangle([name_x1, name_y1, name_x2, name_y2], fill=(240, 240, 240))
    boxes.append({
        "label": "Name",
        "class_id": 3,
        "model_type": "aadhaar",
        "x1": name_x1 / width,
        "y1": name_y1 / height,
        "x2": name_x2 / width,
        "y2": name_y2 / height,
    })

    # DOB: Below Name
    dob_x1 = name_x1
    dob_y1 = name_y2 + int(card_h * 0.04)
    dob_w = int(card_w * 0.38)
    dob_h = int(card_h * 0.10)
    dob_x2 = dob_x1 + dob_w
    dob_y2 = dob_y1 + dob_h

    draw.rectangle([dob_x1, dob_y1, dob_x2, dob_y2], fill=(240, 240, 240))
    boxes.append({
        "label": "DOB",
        "class_id": 1,
        "model_type": "aadhaar",
        "x1": dob_x1 / width,
        "y1": dob_y1 / height,
        "x2": dob_x2 / width,
        "y2": dob_y2 / height,
    })

    # Gender: Below DOB
    gender_x1 = dob_x1
    gender_y1 = dob_y2 + int(card_h * 0.03)
    gender_w = int(card_w * 0.22)
    gender_h = int(card_h * 0.09)
    gender_x2 = gender_x1 + gender_w
    gender_y2 = gender_y1 + gender_h

    draw.rectangle([gender_x1, gender_y1, gender_x2, gender_y2], fill=(240, 240, 240))
    boxes.append({
        "label": "Gender",
        "class_id": 2,
        "model_type": "aadhaar",
        "x1": gender_x1 / width,
        "y1": gender_y1 / height,
        "x2": gender_x2 / width,
        "y2": gender_y2 / height,
    })

    # Aadhaar_No: Bottom center
    aadhaar_w = int(card_w * 0.58)
    aadhaar_h = int(card_h * 0.14)
    aadhaar_x1 = card_x1 + int((card_w - aadhaar_w) / 2)
    aadhaar_y1 = card_y2 - int(card_h * 0.20)
    aadhaar_x2 = aadhaar_x1 + aadhaar_w
    aadhaar_y2 = aadhaar_y1 + aadhaar_h

    draw.rectangle([aadhaar_x1, aadhaar_y1, aadhaar_x2, aadhaar_y2], fill=(235, 235, 235))
    boxes.append({
        "label": "Aadhaar_No",
        "class_id": 0,
        "model_type": "aadhaar",
        "x1": aadhaar_x1 / width,
        "y1": aadhaar_y1 / height,
        "x2": aadhaar_x2 / width,
        "y2": aadhaar_y2 / height,
    })

    # 4. Optional Optical Distortions (glare, subtle blur, noise)
    if distortions:
        if random.random() < 0.4:
            # Glare reflection
            glare = Image.new("RGBA", (width, height), (255, 255, 255, 0))
            g_draw = ImageDraw.Draw(glare)
            gx = random.randint(card_x1, card_x2)
            gy = random.randint(card_y1, card_y2)
            gr_rad = random.randint(60, 160)
            g_draw.ellipse([gx - gr_rad, gy - gr_rad, gx + gr_rad, gy + gr_rad], fill=(255, 255, 255, 75))
            glare = glare.filter(ImageFilter.GaussianBlur(radius=25))
            img.paste(glare, (0, 0), glare)

        if random.random() < 0.3:
            # Slight camera lens softness
            img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 1.2)))

    return img, boxes


def create_eval_dataset(output_dir: str, num_samples: int = 40) -> str:
    """Generates synthetic test specimens into output_dir/images and output_dir/labels."""
    img_dir = os.path.join(output_dir, "images")
    lbl_dir = os.path.join(output_dir, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)

    for i in range(num_samples):
        # Varying resolutions: standard phone camera, HD, and 4:3
        resolutions = [(1280, 720), (1080, 1080), (1000, 650), (1600, 1200)]
        w, h = random.choice(resolutions)
        img, boxes = generate_synthetic_specimen(width=w, height=h, distortions=True)

        base_name = f"specimen_{i:04d}"
        img_path = os.path.join(img_dir, f"{base_name}.jpg")
        img.save(img_path, format="JPEG", quality=90)

        # Write YOLO label format: class_id cx cy w h
        lbl_path = os.path.join(lbl_dir, f"{base_name}.txt")
        with open(lbl_path, "w", encoding="utf-8") as f:
            for b in boxes:
                cx = (b["x1"] + b["x2"]) / 2.0
                cy = (b["y1"] + b["y2"]) / 2.0
                bw = b["x2"] - b["x1"]
                bh = b["y2"] - b["y1"]
                f.write(f"{b['class_id']} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} {b['label']}\n")

    return output_dir
