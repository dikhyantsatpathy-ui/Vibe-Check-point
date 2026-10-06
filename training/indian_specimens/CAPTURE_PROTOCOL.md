# NO-CAP (SIH26188) — Indian Specimen Photo Capture Protocol

**Target:** Collect a realistic benchmark dataset of ~150 phone photos of printed Indian specimen identity cards plus 50 negative photos without cards, allowing empirical evaluation of card detection models on authentic Indian document layouts.

---

## 1. Printing the Specimen Sheets

1. **File to Print:** `training/indian_specimens/out/indian_specimen_sheets_300dpi.pdf` (2-page PDF).
2. **Printer Settings:**
   - Paper Size: **A4**.
   - Scale: **100% / Actual Size** (⚠️ **DO NOT SELECT** "Fit to Page" or "Shrink to Fit").
   - Quality: Standard Color Print on standard white copy paper (80–100 GSM) or cardstock.
3. **Cutting:** Cut along the hairline corner tick marks using scissors or a paper cutter to yield individual cards of physical ID-1 size (85.6 mm × 54.0 mm).

---

## 2. Hardware Requirements

- **At least 2 different smartphone cameras** (e.g., iPhone + Android phone, or Samsung + Redmi).
- Standard camera app. Default settings. **Do not use beauty filters, portrait blur, or HDR enhance.**

---

## 3. The 8 Capture Conditions (Plus Edge Cases)

For each card design, take photos under the following diverse real-world conditions:

| Condition Code | Environment / Background | Description |
| :--- | :--- | :--- |
| `table` | Plain desk / table | Wood, laminate, or solid color table surface. |
| `keyboard` | Office / desk clutter | Placed next to or partially resting on a laptop keyboard, mousepad, or pens. |
| `cloth` | Fabric texture | Bedspread, jeans / denim, towel, or textured tablecloth. |
| `text_paper` | Printed text background | Placed on top of an open book, newspaper, printed form, or magazine page. |
| `outdoors` | Outdoor natural light | Direct sunlight or natural daylight on concrete, bench, or grass. |
| `low_light` | Dim ambient light | Evening indoor lighting, room light turned off, or shadowy corner. |
| `glare` | Specular glare / reflection | Direct overhead lamp or phone flashlight causing bright glare across card. |
| `angle` | Perspective tilt | Camera angled at 30°–45° steep angle rather than directly flat overhead. |
| `hand_held` | In-hand capture | Card held between fingers against background room. |
| `partial_edge`| Partially out of frame | Card slightly clipped by frame border (90% visible). |

---

## 4. Test Set Design Split (Zero Leakage)

To maintain an uncompromised evaluation set, the 5 designs are partitioned:

- **Train / Diagnostic Designs (3):**
  - `aadhaar_pvc`
  - `pan_card`
  - `driving_licence`
- **Reserved Held-Out Test Only Designs (2):**
  - `voter_id`
  - `aadhaar_letter`
  *(These 2 designs must NEVER be seen in any future training run; they measure zero-shot generalization across distinct Indian card layouts).*

---

## 5. File Naming Convention & EXIF Rules

- **Format:** `<design>_<phone>_<condition>_<nn>.jpg`
  - Examples:
    - `aadhaar_pvc_pixel7_table_01.jpg`
    - `pan_card_iphone13_glare_03.jpg`
    - `voter_id_pixel7_keyboard_02.jpg`
    - `aadhaar_letter_iphone13_angle_01.jpg`
- **Negative Photos (50 required):**
  - Name as: `neg_<phone>_<condition>_<nn>.jpg`
  - Photos of empty tables, open books, cloth, keyboards, receipts, or plain rectangular paper slips with **NO identity card present**.
- **CRITICAL CAMERA INSTRUCTIONS:**
  - ⚠️ **DO NOT CROP, ROTATE, OR EDIT** the photos in software.
  - ⚠️ **KEEP EXIF METADATA INTACT** (original camera orientation and sensor tags must remain untouched).
  - Transfer files via USB cable or cloud drive (Google Drive / AirDrop) as original uncompressed files (do NOT send via WhatsApp/Telegram which strips EXIF and compresses images).

---

## 6. Photo Target Count Summary

- **Specimen Card Photos:** ≥ 150 photos (approx. 15 photos per condition across the 5 designs).
- **Negative Photos:** ≥ 50 photos (no cards present).
- **Total Photo Kit:** ≥ 200 raw photos placed in `training/indian_specimens/raw/`.
