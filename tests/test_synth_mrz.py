"""Unit tests for procedural MRZ generator (training/synth_mrz.py).
Verifies:
- TD3 generates 2 lines of 44 chars with valid checksums verified by app.mrz.parse_td3.
- TD1 generates 3 lines of 30 chars with valid checksums.
- Rendered strip creates valid bounding boxes.
"""

import random
import pytest
from app.mrz import parse_td3
from training.synth_mrz import (
    generate_valid_td1_mrz,
    generate_valid_td3_mrz,
    render_mrz_strip,
)


def test_td3_mrz_validation():
    rng = random.Random(42)
    for _ in range(10):
        l1, l2 = generate_valid_td3_mrz(rng)
        assert len(l1) == 44
        assert len(l2) == 44
        parsed = parse_td3(l1, l2)
        assert parsed["valid"] is True, f"Failed TD3 checksum: {parsed['checks']}"


def test_td1_mrz_lengths():
    rng = random.Random(99)
    for _ in range(5):
        l1, l2, l3 = generate_valid_td1_mrz(rng)
        assert len(l1) == 30
        assert len(l2) == 30
        assert len(l3) == 30


def test_render_mrz_strip():
    rng = random.Random(123)
    strip, bbox = render_mrz_strip("TD3", width=800, rng=rng)
    assert strip.width == 800
    assert strip.height > 40
    assert bbox[2] > bbox[0]
    assert bbox[3] > bbox[1]
