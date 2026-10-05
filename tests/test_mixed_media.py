"""
Unit tests for PDF digital signature inspection, in-memory rendering,
and Live/Motion Photo burst liveness processing (SIH26188 Phase 4).
"""

import io
import os
import sys
import pytest
import importlib.util
from PIL import Image
from fastapi.testclient import TestClient

_ML_MAIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml_service", "main.py")
_ml_spec = importlib.util.spec_from_file_location("ml_service_main", _ML_MAIN_PATH)
_ml_mod = importlib.util.module_from_spec(_ml_spec)
if os.path.dirname(_ML_MAIN_PATH) not in sys.path:
    sys.path.insert(0, os.path.dirname(_ML_MAIN_PATH))
_ml_spec.loader.exec_module(_ml_mod)
ml_app = _ml_mod.app

from media_processor import (
    inspect_pdf_signatures,
    render_pdf_pages_in_memory,
    process_pdf_document,
    extract_motion_photo_streams,
    process_live_photo,
)



def _create_minimal_pdf(with_text: str = "Test Identity Document") -> bytes:
    """Create a syntactically valid minimal PDF in memory."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _create_signed_pdf_specimen() -> bytes:
    """Create a minimal PDF containing a standard PKCS#7 digital signature ByteRange."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    buf = io.BytesIO()
    writer.write(buf)
    raw = buf.getvalue()

    sig_block = (
        b"\n10 0 obj\n<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /adbe.pkcs7.detached "
        b"/Name (UIDAI Digital Authority) /M (D:20261005120000+05'30') "
        b"/Reason (Authentic e-Aadhaar Verification) "
        b"/ByteRange [ 0 200 250 50 ] /Contents <00000000> >>\nendobj\n"
    )
    eof_idx = raw.rfind(b"%%EOF")
    if eof_idx != -1:
        signed = raw[:eof_idx] + sig_block + raw[eof_idx:]
    else:
        signed = raw + sig_block
    return signed


def test_pdf_signature_detection():
    """Verify that digitally signed PDFs are detected with signer metadata and valid ByteRange."""
    signed_bytes = _create_signed_pdf_specimen()
    sigs = inspect_pdf_signatures(signed_bytes)
    assert len(sigs) >= 1
    sig = sigs[0]
    assert sig["is_digitally_signed"] is True
    assert sig["cryptographically_verified"] is False
    assert "UIDAI" in (sig.get("signer_name") or "")
    assert "adbe.pkcs7.detached" in sig.get("subfilter", "")
    assert sig["is_range_valid"] is True


def test_unsigned_pdf_signature_detection():
    """Verify that standard unsigned PDFs return empty signature list."""
    plain_pdf = _create_minimal_pdf("Plain Unsigned Passport")
    sigs = inspect_pdf_signatures(plain_pdf)
    assert sigs == []


def test_process_pdf_document_pipeline():
    """Verify full PDF document processing pipeline with text extraction and page metadata."""
    pdf_bytes = _create_minimal_pdf("Officer Verified Identity Specimen")
    res = process_pdf_document(pdf_bytes, max_pages=3)
    assert res["is_pdf"] is True
    assert res["page_count"] >= 1
    assert "signatures" in res
    assert "pages" in res


def test_extract_motion_photo_streams():
    """Verify separating a motion photo into its primary JPEG and embedded MP4 stream."""
    img = Image.new("RGB", (400, 300), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    # Create dummy MP4 box header: 4-byte size (32 bytes) + 'ftyp' + 'mp42' + major/minor
    mp4_box = (
        b"\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00mp42isom"
        b"\x00\x00\x00\x08mdat" + (b"\xaa" * 128)
    )
    motion_photo_bytes = jpeg_bytes + mp4_box

    still_out, video_out = extract_motion_photo_streams(motion_photo_bytes)
    assert still_out == jpeg_bytes
    assert video_out is not None
    assert video_out.startswith(mp4_box)


def test_process_live_photo_static_image():
    """Verify processing a static image without video burst degrades cleanly to static format."""
    img = Image.new("RGB", (320, 240), color=(200, 150, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    static_bytes = buf.getvalue()

    res = process_live_photo(static_bytes)
    assert res["is_live_photo"] is False
    assert res["photo_format"] == "standard_image"
    assert res["primary_image_width"] == 320
    assert res["primary_image_height"] == 240
    assert "primary_image_png" in res
    assert res["liveness"]["liveness_detected"] is False
    assert res["liveness"]["experimental"] is True


def test_api_media_endpoints_via_testclient(monkeypatch):
    """Verify /api/ml/media/process_pdf and /api/ml/media/process_live_photo with auth checks."""
    client = TestClient(ml_app)
    pdf_bytes = _create_signed_pdf_specimen()

    # 1. Unset ML_SECRET_KEY and ML_ALLOW_NO_AUTH -> 503 Service Unavailable (Fail closed, D4)
    monkeypatch.delenv("ML_SECRET_KEY", raising=False)
    monkeypatch.delenv("ML_ALLOW_NO_AUTH", raising=False)
    res_fail = client.post(
        "/api/ml/media/process_pdf",
        files={"file": ("specimen.pdf", pdf_bytes, "application/pdf")},
    )
    assert res_fail.status_code == 503

    # 2. Set ML_ALLOW_NO_AUTH=true -> succeeds without key
    monkeypatch.setenv("ML_ALLOW_NO_AUTH", "true")
    res_dev = client.post(
        "/api/ml/media/process_pdf",
        files={"file": ("specimen.pdf", pdf_bytes, "application/pdf")},
    )
    assert res_dev.status_code == 200

    # 3. Enforce ML_SECRET_KEY
    monkeypatch.delenv("ML_ALLOW_NO_AUTH", raising=False)
    monkeypatch.setenv("ML_SECRET_KEY", "secure_border_key_42")

    # Missing header -> 401
    res_unauth = client.post(
        "/api/ml/media/process_pdf",
        files={"file": ("specimen.pdf", pdf_bytes, "application/pdf")},
    )
    assert res_unauth.status_code == 401

    # Valid header -> 200
    headers = {"X-ML-Secret-Key": "secure_border_key_42"}
    res_pdf = client.post(
        "/api/ml/media/process_pdf",
        files={"file": ("specimen.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert res_pdf.status_code == 200
    pdf_data = res_pdf.json()
    assert pdf_data["is_pdf"] is True
    assert pdf_data["is_digitally_signed"] is True
    assert len(pdf_data["signatures"]) >= 1
    assert pdf_data["signatures"][0]["cryptographically_verified"] is False

    # 4. Live photo processing endpoint with auth
    img = Image.new("RGB", (200, 200), color=(100, 120, 140))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_img = buf.getvalue()

    res_live = client.post(
        "/api/ml/media/process_live_photo",
        files={"file": ("live.jpg", raw_img, "image/jpeg")},
        headers=headers,
    )
    assert res_live.status_code == 200
    live_data = res_live.json()
    assert "primary_image_b64" in live_data
    assert "liveness" in live_data
    assert live_data["liveness"].get("experimental") is True
