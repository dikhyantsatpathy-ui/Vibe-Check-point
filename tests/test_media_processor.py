"""Tests for ml_service.media_processor media decoding and stream parsing."""

import io
from PIL import Image
from ml_service.media_processor import extract_motion_photo_streams


def test_heic_header_not_parsed_as_motion_photo():
    """A synthetic HEIC header with ftyp at byte 4 must return unchanged with None video."""
    heic_bytes = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
    still, video = extract_motion_photo_streams(heic_bytes)
    assert still == heic_bytes
    assert video is None


def test_motion_photo_jpeg_with_mp4():
    """JPEG followed by an MP4 container box must return non-empty still and video starting with ftyp."""
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()
    assert jpeg_bytes.endswith(b"\xff\xd9")

    mp4_box = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64
    payload = jpeg_bytes + mp4_box

    still, video = extract_motion_photo_streams(payload)
    assert still == jpeg_bytes
    assert video is not None
    assert video.startswith(mp4_box)


def test_plain_jpeg_returns_none_video():
    """Plain JPEG without an MP4 container returns the exact same bytes and None video."""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    still, video = extract_motion_photo_streams(jpeg_bytes)
    assert still == jpeg_bytes
    assert video is None


def test_validate_upload_bytes_accepts_heic():
    """validate_upload_bytes returns 'heic' when given an ftyp box with an accepted HEIF brand."""
    try:
        from app.main import validate_upload_bytes
    except (ImportError, ModuleNotFoundError):
        from main import validate_upload_bytes

    heic_bytes = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    assert validate_upload_bytes(heic_bytes) == "heic"

    mif1_bytes = b"\x00\x00\x00\x18ftypmif1" + b"\x00" * 32
    assert validate_upload_bytes(mif1_bytes) == "heic"


def test_process_live_photo_heic_decoder_unavailable(monkeypatch):
    """When HEIF_SUPPORTED is False, process_live_photo returns heic_decoder_unavailable error."""
    import ml_service.media_processor as mp

    monkeypatch.setattr(mp, "HEIF_SUPPORTED", False)
    heic_bytes = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    res = mp.process_live_photo(heic_bytes)
    assert res.get("error") == "heic_decoder_unavailable"
    assert res.get("is_live_photo") is False
    assert "unavailable" in res["liveness"]["explanation"]


def test_process_live_photo_corrupted_primary_image():
    """Corrupted primary bytes return primary_image_decode_failed rather than raw bytes."""
    import ml_service.media_processor as mp

    corrupted_bytes = b"not_an_image_at_all" * 10
    res = mp.process_live_photo(corrupted_bytes)
    assert res.get("error") == "primary_image_decode_failed"
    assert "Primary image decode failed" in res.get("detail", "")


def test_api_process_live_photo_raises_415_on_heic_unavailable(monkeypatch):
    """ML service endpoint returns HTTP 415 if HEIC decoder is unavailable."""
    from fastapi.testclient import TestClient
    from ml_service.main import app as ml_app
    import ml_service.media_processor as mp

    monkeypatch.setenv("ML_ALLOW_NO_AUTH", "true")
    monkeypatch.setattr(mp, "HEIF_SUPPORTED", False)
    client = TestClient(ml_app)
    heic_bytes = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    response = client.post(
        "/api/ml/media/process_live_photo",
        files={"file": ("test.heic", io.BytesIO(heic_bytes), "image/heic")},
    )
    assert response.status_code == 415
    assert "HEIC decoding unavailable" in response.json()["detail"]


def test_heic_normalize_via_mocked_ml(monkeypatch):
    """normalize_heic_to_png decodes HEIC via remote ML service when local HEIF is unavailable."""
    import base64
    try:
        from app import heif_support as hs
        from app.main import normalize_heic_to_png
        from app import remote_ml as rm
    except (ImportError, ModuleNotFoundError):
        import heif_support as hs
        from main import normalize_heic_to_png
        import remote_ml as rm

    monkeypatch.setattr(hs, "HEIF_SUPPORTED", False)

    img = Image.new("RGB", (50, 50), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    b64_png = base64.b64encode(png_bytes).decode("ascii")

    def mock_call_ml_media(path, filename, data, content_type):
        if path == "/api/ml/media/process_live_photo":
            return {"primary_image_b64": b64_png, "error": None}
        return None

    monkeypatch.setattr(rm, "call_ml_media", mock_call_ml_media)
    heic_bytes = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    result = normalize_heic_to_png(heic_bytes)
    assert result == png_bytes


def test_heic_normalize_raises_415_when_ml_fails(monkeypatch):
    """normalize_heic_to_png raises HTTP 415 when local HEIF and remote ML are unavailable."""
    import pytest
    from fastapi import HTTPException
    try:
        from app import heif_support as hs
        from app.main import normalize_heic_to_png
        from app import remote_ml as rm
    except (ImportError, ModuleNotFoundError):
        import heif_support as hs
        from main import normalize_heic_to_png
        import remote_ml as rm

    monkeypatch.setattr(hs, "HEIF_SUPPORTED", False)
    monkeypatch.setattr(rm, "call_ml_media", lambda *args, **kwargs: None)

    heic_bytes = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    with pytest.raises(HTTPException) as exc_info:
        normalize_heic_to_png(heic_bytes)
    assert exc_info.value.status_code == 415
    assert "HEIC photos can't be decoded right now" in exc_info.value.detail


def test_pdf_text_or_image_ml_rasterization(monkeypatch):
    """_pdf_text_or_image rasterizes vector-only PDF via ML service when local fitz produces no image."""
    import base64
    from pypdf import PdfWriter
    try:
        from app.extraction import _pdf_text_or_image
        from app import remote_ml as rm
    except (ImportError, ModuleNotFoundError):
        from extraction import _pdf_text_or_image
        import remote_ml as rm

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    blank_pdf = buf.getvalue()

    img = Image.new("RGB", (60, 60), color=(50, 60, 70))
    ibuf = io.BytesIO()
    img.save(ibuf, format="PNG")
    png_bytes = ibuf.getvalue()
    b64_png = base64.b64encode(png_bytes).decode("ascii")

    monkeypatch.setattr(
        rm,
        "call_ml_media",
        lambda path, filename, data, content_type: {
            "render_failed": False,
            "pages": [{"png_b64": b64_png, "text": "Scanned Document", "render_failed": False}],
        },
    )

    text, img_out = _pdf_text_or_image(blank_pdf)
    assert text == "Scanned Document"
    assert img_out == png_bytes


def test_pdf_text_or_image_ml_rasterization_failure(monkeypatch):
    """_pdf_text_or_image returns ('', None) when remote ML rasterization fails."""
    from pypdf import PdfWriter
    try:
        from app.extraction import _pdf_text_or_image
        from app import remote_ml as rm
    except (ImportError, ModuleNotFoundError):
        from extraction import _pdf_text_or_image
        import remote_ml as rm

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    blank_pdf = buf.getvalue()

    monkeypatch.setattr(rm, "call_ml_media", lambda *args, **kwargs: None)

    text, img_out = _pdf_text_or_image(blank_pdf)
    assert text == ""
    assert img_out is None


def test_render_pdf_pages_in_memory_pypdf_no_blank_white(monkeypatch):
    """When pypdfium2 and fitz are unavailable and PDF has no images, returns render_failed: True and None rendered_png."""
    import sys
    from pypdf import PdfWriter
    import ml_service.media_processor as mp

    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    monkeypatch.setitem(sys.modules, "fitz", None)

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    blank_pdf = buf.getvalue()

    pages = mp.render_pdf_pages_in_memory(blank_pdf)
    assert len(pages) == 1
    assert pages[0]["render_failed"] is True
    assert pages[0]["rendered_png"] is None
    assert pages[0]["renderer"] == "pypdf"

    doc_res = mp.process_pdf_document(blank_pdf)
    assert doc_res["render_failed"] is True
    assert doc_res["signature_verified"] is False
    assert "No cryptographic validation" in doc_res["signature_note"]




