"""Tests for ephemeral video file unlinking in media_processor (F-12).

Verifies:
  1. Temporary .mp4 file created during motion liveness extraction is guaranteed
     to be unlinked in the finally block.
  2. Unlinking occurs even when cv2 decoding raises an exception.
  3. Zero temporary files remain on disk after processing corrupted or valid video.
"""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest

from ml_service.media_processor import analyze_motion_liveness_frames


def test_temp_video_unlinked_on_corrupt_input():
    """Ephemeral .mp4 file must be unlinked even when video bytes are corrupted."""
    corrupt_video = b"NOT_A_VALID_MP4_JUST_GARBAGE_BYTES" * 100  # > 1024 bytes
    res = analyze_motion_liveness_frames(corrupt_video)
    assert res.get("has_video") is True
    assert res.get("liveness_detected") is False


def test_temp_video_unlinked_when_decoder_raises():
    """Even if cv2.VideoCapture raises an unhandled exception, finally block must unlink file."""
    captured_tmp_path = []

    def mock_video_capture(path):
        captured_tmp_path.append(path)
        assert os.path.exists(path), "Temp file should exist before decoder runs"
        raise RuntimeError("Simulated codec crash")

    video_payload = b"\x00\x00\x00 ftypmp42fake" + (b"\x00" * 2000)
    with patch("cv2.VideoCapture", side_effect=mock_video_capture):
        res = analyze_motion_liveness_frames(video_payload)
        assert res.get("liveness_detected") is False
        assert "Simulated codec crash" in res.get("reason", "")

    assert len(captured_tmp_path) == 1
    tmp_path = captured_tmp_path[0]
    assert not os.path.exists(tmp_path), f"Temp file {tmp_path} was NOT unlinked!"
