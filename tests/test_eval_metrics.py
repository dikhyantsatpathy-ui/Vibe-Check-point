"""
Unit tests for evaluation metrics: IoU, AP, and confidence threshold optimization (Phase 2).
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eval"))

from metrics import compute_iou, compute_ap_at_iou, evaluate_dataset_map, optimize_confidence_thresholds


def test_compute_iou_known_geometries():
    # 1. Exact match (IoU = 1.0)
    assert compute_iou([0, 0, 10, 10], [0, 0, 10, 10]) == pytest.approx(1.0)

    # 2. Non-overlapping (IoU = 0.0)
    assert compute_iou([0, 0, 10, 10], [20, 20, 30, 30]) == pytest.approx(0.0)

    # 3. 50% overlap horizontally: [0, 0, 10, 10] and [5, 0, 15, 10]
    # Inter: 5 * 10 = 50. Union: 100 + 100 - 50 = 150. IoU = 50 / 150 = 1/3
    assert compute_iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1.0 / 3.0)


def test_ap_and_map_perfect_detector():
    gts = [
        {"img_id": "img1", "label": "Card", "x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9},
        {"img_id": "img2", "label": "Card", "x1": 0.2, "y1": 0.2, "x2": 0.8, "y2": 0.8},
    ]
    dets = [
        {"img_id": "img1", "label": "Card", "confidence": 0.95, "x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9},
        {"img_id": "img2", "label": "Card", "confidence": 0.90, "x1": 0.2, "y1": 0.2, "x2": 0.8, "y2": 0.8},
    ]

    res = evaluate_dataset_map(dets, gts, ["Card"])
    assert res["overall"]["mAP50"] == pytest.approx(1.0)
    assert res["overall"]["mAP50_95"] == pytest.approx(1.0)
    assert res["classes"]["Card"]["recall"] == pytest.approx(1.0)
    assert res["classes"]["Card"]["precision"] == pytest.approx(1.0)


def test_threshold_optimizer():
    gts = [
        {"img_id": "img1", "label": "Photo", "x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.5},
    ]
    dets = [
        # True positive with high confidence
        {"img_id": "img1", "label": "Photo", "confidence": 0.85, "x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.5},
        # False positive with low confidence
        {"img_id": "img1", "label": "Photo", "confidence": 0.25, "x1": 0.6, "y1": 0.6, "x2": 0.9, "y2": 0.9},
    ]

    opt = optimize_confidence_thresholds(dets, gts, ["Photo"])
    # Optimal threshold should be >= 0.30 to filter out the false positive at 0.25 and keep F1 = 1.0
    assert opt["Photo"] >= 0.30
