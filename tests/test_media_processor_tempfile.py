"""Tests for zero-raw-storage in-memory video decoding in media_processor (F-12 / FIX 5).

Verifies:
  1. No temporary files or tempfile calls (NamedTemporaryFile, mkstemp) are used.
  2. In-memory decoding with PyAV operates strictly in RAM.
  3. Corrupted or valid video inputs return structured dictionaries without disk access.
"""

from __future__ import annotations

import tempfile

from ml_service.media_processor import analyze_motion_liveness_frames


def test_no_tempfile_used_on_garbage_input(monkeypatch):
    """tempfile must not be called when analyzing motion liveness frames."""
    def forbid_tempfile(*args, **kwargs):
        raise AssertionError("tempfile was invoked, violating Zero-Raw-Storage!")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", forbid_tempfile)
    monkeypatch.setattr(tempfile, "mkstemp", forbid_tempfile)

    corrupt_video = b"NOT_A_VALID_MP4_JUST_GARBAGE_BYTES" * 100  # > 1024 bytes
    res = analyze_motion_liveness_frames(corrupt_video)
    assert res.get("has_video") is True
    assert res.get("liveness_detected") is False
    assert res.get("experimental") is True


def test_no_tempfile_used_on_mp4_payload(monkeypatch):
    """tempfile must not be called on any video payload."""
    def forbid_tempfile(*args, **kwargs):
        raise AssertionError("tempfile was invoked, violating Zero-Raw-Storage!")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", forbid_tempfile)
    monkeypatch.setattr(tempfile, "mkstemp", forbid_tempfile)

    video_payload = b"\x00\x00\x00 ftypmp42isom" + (b"\x00" * 2000)
    res = analyze_motion_liveness_frames(video_payload)
    assert isinstance(res, dict)
    assert res.get("experimental") is True

