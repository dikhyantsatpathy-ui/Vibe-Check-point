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
    from app.main import validate_upload_bytes

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

