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
