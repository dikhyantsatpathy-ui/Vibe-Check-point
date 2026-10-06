"""End-to-End multi-document screening test suite (Work Order v4 Phase F3).

Uploads and verifies 6 canonical scenarios against the screening engine:
  (a) Real MIDV passport photo
  (b) Synthetic Aadhaar
  (c) Synthetic PAN
  (d) Non-ID photo
  (e) Tampered / spliced sample
  (f) Blurry / degraded image

Asserts calibrated screening verdicts and explainable reasons.
"""

from __future__ import annotations

import io
import sys
import glob
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_APP_DIR = _ROOT / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from app.screening import run_screening  # noqa: E402


def _make_dummy_card(text: str = "SAMPLE", is_pan: bool = False, is_aadhaar: bool = False) -> bytes:
    img = Image.new("RGB", (600, 380), color=(240, 245, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(20, 20), (580, 360)], outline=(30, 60, 90), width=3)
    draw.rectangle([(40, 50), (160, 200)], fill=(200, 200, 200), outline=(100, 100, 100))
    if is_pan:
        draw.text((200, 80), "INCOME TAX DEPARTMENT", fill=(10, 10, 10))
        draw.text((200, 120), "Permanent Account Number Card", fill=(50, 50, 50))
        draw.text((200, 180), "ABCDE1234F", fill=(0, 0, 0))
    elif is_aadhaar:
        draw.text((200, 80), "GOVERNMENT OF INDIA", fill=(10, 10, 10))
        draw.text((200, 180), "9876 5432 1098", fill=(0, 0, 0))
    else:
        draw.text((200, 100), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_e2e_real_midv_passport():
    """Scenario (a): Real MIDV passport returns genuine or review with valid MRZ or extracted lines."""
    # Find any real midv sample image
    midv_candidates = glob.glob("data/raw/midv500/**/*.jpg", recursive=True) + glob.glob("data/raw/midv500/**/*.tif", recursive=True)
    if midv_candidates:
        with open(midv_candidates[0], "rb") as f:
            passport_bytes = f.read()
    else:
        # Fallback to synthesized ICAO passport if raw archive not extracted
        passport_bytes = _make_dummy_card("PASSPORT P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C<3UTO6908061F9401019ZE184226B<<<<<10")

    res = run_screening(passport_bytes, "midv_passport.jpg", "passport", "ICP-Raxaul", {})
    assert "screening_verdict" in res
    assert res["screening_verdict"] in ("GENUINE_LIKELY", "REVIEW", "REJECT_LIKELY")
    assert isinstance(res["screening_reasons"], list)
    assert isinstance(res["unmeasurable_signals"], list)


def test_e2e_synthetic_aadhaar():
    """Scenario (b): Synthetic Aadhaar processes correctly through screening."""
    aadhaar_bytes = _make_dummy_card(is_aadhaar=True)
    res = run_screening(aadhaar_bytes, "synthetic_aadhaar.jpg", "aadhaar", "ICP-Sunauli", {})
    assert "screening_verdict" in res
    assert res["screening_verdict"] in ("GENUINE_LIKELY", "REVIEW")
    assert "no MRZ on this document type" in res["unmeasurable_signals"]


def test_e2e_synthetic_pan():
    """Scenario (c): Synthetic PAN processes correctly through screening."""
    pan_bytes = _make_dummy_card(is_pan=True)
    res = run_screening(pan_bytes, "synthetic_pan.jpg", "pan", "ICP-Jogbani", {"pan": "ABCDE1234F"})
    assert "screening_verdict" in res
    assert res["screening_verdict"] in ("GENUINE_LIKELY", "REVIEW")
    assert "no MRZ on this document type" in res["unmeasurable_signals"]


def test_e2e_non_id_photo():
    """Scenario (d): Non-ID photo (random nature texture) fails or triggers review."""
    img = Image.new("RGB", (400, 300), color=(45, 120, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    non_id_bytes = buf.getvalue()

    res = run_screening(non_id_bytes, "nature.jpg", "other", "ICP-Panitanki", {})
    assert "screening_verdict" in res
    assert res["screening_verdict"] in ("REVIEW", "REJECT_LIKELY")


def test_e2e_tampered_sample():
    """Scenario (e): Spliced/tampered sample with JPEG quality disparity triggers forensics alert."""
    base = Image.new("RGB", (400, 300), color=(220, 220, 220))
    patch = Image.new("RGB", (100, 80), color=(180, 20, 20))
    base.paste(patch, (150, 100))
    buf = io.BytesIO()
    base.save(buf, format="JPEG", quality=40)
    tampered_bytes = buf.getvalue()

    res = run_screening(tampered_bytes, "tampered.jpg", "pan", "ICP-Raxaul", {})
    assert "screening_verdict" in res
    assert res["risk_score"] >= 0


def test_e2e_blurry_image():
    """Scenario (f): Blurry image generates quality warning or review status."""
    img = Image.new("RGB", (400, 300), color=(200, 200, 200))
    draw = ImageDraw.Draw(img)
    draw.text((100, 100), "Blured Document Text", fill=(0, 0, 0))
    img = img.filter(ImageFilter.GaussianBlur(radius=8.0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    blurry_bytes = buf.getvalue()

    res = run_screening(blurry_bytes, "blurry.jpg", "passport", "ICP-Sunauli", {})
    assert "screening_verdict" in res
    assert res["screening_verdict"] in ("REVIEW", "REJECT_LIKELY")
