"""Unit tests for perspective composite generator."""

from PIL import Image
import pytest
from training.make_composites import generate_perspective_composite


def test_perspective_composite_valid_bounds():
    """Verify composite generation produces valid normalized bounding boxes [0, 1]."""
    card = Image.new("RGB", (300, 200), color=(255, 0, 0))
    bg = Image.new("RGB", (640, 640), color=(50, 50, 50))

    for seed in [1, 42, 999]:
        comp, (cx, cy, w, h) = generate_perspective_composite(card, bg, seed=seed)
        assert comp.size == (640, 640)
        assert 0.0 < cx < 1.0
        assert 0.0 < cy < 1.0
        assert 0.0 < w <= 1.0
        assert 0.0 < h <= 1.0
        # Check box corners stay within image boundaries
        x1 = cx - w / 2.0
        y1 = cy - h / 2.0
        x2 = cx + w / 2.0
        y2 = cy + h / 2.0
        assert x1 >= 0.0
        assert y1 >= 0.0
        assert x2 <= 1.0
        assert y2 <= 1.0
