"""
Unit tests for card boundary quadrilateral detection and homography perspective rectification (Phase 3).
"""

import io
import os
import sys
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from rectification import (
    _order_quad_points,
    find_homography_matrix,
    warp_perspective_pillow,
    rectify_card_image,
    CANONICAL_CARD_WIDTH,
    CANONICAL_CARD_HEIGHT,
)


def test_order_quad_points():
    """Verify that arbitrary unordered corner coordinates are canonicalized to
    [top-left, top-right, bottom-right, bottom-left]."""
    # Define an unordered quad
    unordered = np.array([
        [800, 500],  # BR
        [100, 120],  # TL
        [120, 520],  # BL
        [780, 110],  # TR
    ], dtype=np.float32)

    ordered = _order_quad_points(unordered)

    # Top-Left: [100, 120]
    np.testing.assert_allclose(ordered[0], [100, 120], atol=1e-3)
    # Top-Right: [780, 110]
    np.testing.assert_allclose(ordered[1], [780, 110], atol=1e-3)
    # Bottom-Right: [800, 500]
    np.testing.assert_allclose(ordered[2], [800, 500], atol=1e-3)
    # Bottom-Left: [120, 520]
    np.testing.assert_allclose(ordered[3], [120, 520], atol=1e-3)


def test_homography_matrix_projection():
    """Verify that computed homography matrix projects source vertices to destination vertices."""
    src = np.array([
        [50, 60],
        [850, 40],
        [880, 560],
        [40, 580],
    ], dtype=np.float32)

    dst = np.array([
        [0, 0],
        [CANONICAL_CARD_WIDTH, 0],
        [CANONICAL_CARD_WIDTH, CANONICAL_CARD_HEIGHT],
        [0, CANONICAL_CARD_HEIGHT],
    ], dtype=np.float32)

    H = find_homography_matrix(src, dst)
    assert H.shape == (3, 3)

    for i in range(4):
        p_src = np.array([src[i][0], src[i][1], 1.0])
        p_dst_proj = H @ p_src
        p_dst_proj /= p_dst_proj[2]

        np.testing.assert_allclose(
            p_dst_proj[:2],
            dst[i],
            atol=0.5,
            err_msg=f"Homography failed to project vertex {i}"
        )


def test_warp_perspective_pillow():
    """Verify that Pillow perspective warp produces expected dimensions."""
    img = Image.new("RGB", (1200, 800), color=(100, 150, 200))
    src_quad = np.array([
        [100, 100],
        [1000, 120],
        [980, 680],
        [80, 650],
    ], dtype=np.float32)

    warped = warp_perspective_pillow(img, src_quad)
    assert warped.size == (CANONICAL_CARD_WIDTH, CANONICAL_CARD_HEIGHT)
    assert warped.mode == "RGB"


def test_rectify_card_image_feature_flag(monkeypatch):
    """Verify that rectification stays disabled by default behind feature flag,
    and activates when enabled or forced."""
    img = Image.new("RGB", (800, 600), color=(220, 220, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    # 1. Default (flag unset): should not rectify
    monkeypatch.delenv("ENABLE_CARD_RECTIFICATION", raising=False)
    out_bytes, was_rectified, meta = rectify_card_image(raw_bytes, force_rectification=False)
    assert was_rectified is False
    assert out_bytes == raw_bytes
    assert meta is None

    # 2. Flag enabled: should rectify and return PNG bytes
    monkeypatch.setenv("ENABLE_CARD_RECTIFICATION", "true")
    out_rect, was_rect, meta_rect = rectify_card_image(raw_bytes)
    assert was_rect is True
    assert meta_rect is not None
    assert meta_rect["canonical_width"] == CANONICAL_CARD_WIDTH
    assert meta_rect["canonical_height"] == CANONICAL_CARD_HEIGHT

    # Check that output is valid PNG
    rect_img = Image.open(io.BytesIO(out_rect))
    assert rect_img.size == (CANONICAL_CARD_WIDTH, CANONICAL_CARD_HEIGHT)


def test_isolate_document_card_integration_with_rectification(monkeypatch):
    """Verify isolate_document_card applies rectification when ENABLE_CARD_RECTIFICATION is set."""
    from yolo_roi import isolate_document_card

    img = Image.new("RGB", (1000, 700), color=(180, 180, 180))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    # When flag is enabled, isolate_document_card should return rectified metadata
    monkeypatch.setenv("ENABLE_CARD_RECTIFICATION", "true")
    out_bytes, meta = isolate_document_card(raw_bytes)
    assert meta is not None
    assert meta.get("rectified") is True
    assert "rectification" in meta
    rect_img = Image.open(io.BytesIO(out_bytes))
    assert rect_img.size == (CANONICAL_CARD_WIDTH, CANONICAL_CARD_HEIGHT)

