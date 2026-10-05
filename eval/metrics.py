"""
Evaluation metrics computation: IoU, Precision, Recall, mAP50, mAP50-95,
and confidence threshold optimization (PR sweep).
"""

import numpy as np
from typing import List, Dict, Tuple, Any


def compute_iou(box1: List[float], box2: List[float]) -> float:
    """Compute IoU between two bounding boxes [x1, y1, x2, y2]."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union_area = area1 + area2 - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def compute_ap_at_iou(
    detections: List[Dict[str, Any]],
    ground_truths: List[Dict[str, Any]],
    iou_thresh: float = 0.50,
) -> float:
    """Calculate Average Precision (AP) for a single class at a given IoU threshold."""
    if not ground_truths:
        return 0.0
    if not detections:
        return 0.0

    # Sort detections by confidence descending
    sorted_dets = sorted(detections, key=lambda d: d.get("confidence", 0.0), reverse=True)
    num_gt = len(ground_truths)
    gt_matched = [False] * num_gt

    tp = np.zeros(len(sorted_dets))
    fp = np.zeros(len(sorted_dets))

    for i, det in enumerate(sorted_dets):
        d_box = [det["x1"], det["y1"], det["x2"], det["y2"]]
        best_iou = 0.0
        best_gt_idx = -1

        for j, gt in enumerate(ground_truths):
            if det.get("img_id") != gt.get("img_id"):
                continue
            g_box = [gt["x1"], gt["y1"], gt["x2"], gt["y2"]]
            iou = compute_iou(d_box, g_box)
            if iou > best_iou:
                best_iou = iou
                best_gt_idx = j

        if best_iou >= iou_thresh and best_gt_idx >= 0:
            if not gt_matched[best_gt_idx]:
                tp[i] = 1.0
                gt_matched[best_gt_idx] = True
            else:
                fp[i] = 1.0  # Duplicate detection
        else:
            fp[i] = 1.0

    tp_cum = np.cumsum(tp)
    fp_cum = np.cumsum(fp)
    recalls = tp_cum / max(num_gt, 1)
    precisions = tp_cum / np.maximum(tp_cum + fp_cum, 1e-6)

    # 101-point interpolated AP calculation
    ap = 0.0
    for t in np.linspace(0.0, 1.0, 101):
        p = precisions[recalls >= t]
        ap += np.max(p) if p.size > 0 else 0.0
    return ap / 101.0


def evaluate_dataset_map(
    all_detections: List[Dict[str, Any]],
    all_ground_truths: List[Dict[str, Any]],
    class_names: List[str],
) -> Dict[str, Any]:
    """Calculate mAP50 and mAP50-95 across all specified classes."""
    iou_thresholds = np.linspace(0.50, 0.95, 10)
    per_class_results: Dict[str, Any] = {}
    map50_list = []
    map50_95_list = []

    for c_name in class_names:
        c_dets = [d for d in all_detections if d.get("label") == c_name]
        c_gts = [g for g in all_ground_truths if g.get("label") == c_name]

        aps = []
        for iou_t in iou_thresholds:
            ap = compute_ap_at_iou(c_dets, c_gts, iou_thresh=float(iou_t))
            aps.append(ap)

        ap50 = aps[0]
        ap50_95 = float(np.mean(aps))

        # Precision & Recall at default conf 0.35 and IoU 0.50
        filtered_dets = [d for d in c_dets if d.get("confidence", 0.0) >= 0.35]
        tp_count = 0
        gt_used = set()
        for d in filtered_dets:
            d_box = [d["x1"], d["y1"], d["x2"], d["y2"]]
            for j, gt in enumerate(c_gts):
                if j in gt_used or d.get("img_id") != gt.get("img_id"):
                    continue
                if compute_iou(d_box, [gt["x1"], gt["y1"], gt["x2"], gt["y2"]]) >= 0.50:
                    tp_count += 1
                    gt_used.add(j)
                    break

        prec = tp_count / max(len(filtered_dets), 1)
        rec = tp_count / max(len(c_gts), 1)
        f1 = 2 * (prec * rec) / max(prec + rec, 1e-6)

        per_class_results[c_name] = {
            "mAP50": round(float(ap50), 4),
            "mAP50_95": round(float(ap50_95), 4),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1": round(float(f1), 4),
            "ground_truths": len(c_gts),
            "detections": len(filtered_dets),
        }
        map50_list.append(ap50)
        map50_95_list.append(ap50_95)

    return {
        "overall": {
            "mAP50": round(float(np.mean(map50_list)), 4) if map50_list else 0.0,
            "mAP50_95": round(float(np.mean(map50_95_list)), 4) if map50_95_list else 0.0,
        },
        "classes": per_class_results,
    }


def optimize_confidence_thresholds(
    all_detections: List[Dict[str, Any]],
    all_ground_truths: List[Dict[str, Any]],
    class_names: List[str],
) -> Dict[str, float]:
    """Sweeps confidence thresholds (0.10 to 0.85) to propose optimal thresholds per class maximizing F1."""
    optimal_thresholds: Dict[str, float] = {}

    for c_name in class_names:
        c_dets = [d for d in all_detections if d.get("label") == c_name]
        c_gts = [g for g in all_ground_truths if g.get("label") == c_name]

        if not c_gts:
            optimal_thresholds[c_name] = 0.35
            continue

        best_f1 = -1.0
        best_thresh = 0.35

        for thresh in np.arange(0.15, 0.85, 0.05):
            thresh = float(round(thresh, 2))
            filtered = [d for d in c_dets if d.get("confidence", 0.0) >= thresh]

            tp = 0
            gt_used = set()
            for d in filtered:
                d_box = [d["x1"], d["y1"], d["x2"], d["y2"]]
                for j, gt in enumerate(c_gts):
                    if j in gt_used or d.get("img_id") != gt.get("img_id"):
                        continue
                    if compute_iou(d_box, [gt["x1"], gt["y1"], gt["x2"], gt["y2"]]) >= 0.50:
                        tp += 1
                        gt_used.add(j)
                        break

            prec = tp / max(len(filtered), 1)
            rec = tp / max(len(c_gts), 1)
            f1 = 2 * (prec * rec) / max(prec + rec, 1e-6)

            if f1 > best_f1:
                best_f1 = f1
                best_thresh = thresh

        optimal_thresholds[c_name] = best_thresh

    return optimal_thresholds
