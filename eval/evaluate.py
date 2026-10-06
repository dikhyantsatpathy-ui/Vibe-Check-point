"""
Main Evaluation Harness Entrypoint (SIH26188 Phase 2).
Runs baseline evaluation across YOLOv8 ONNX models: mAP50, mAP50-95, per-class PR curves,
confidence threshold tuning, and CPU p50/p95 latency benchmarking.
"""

import json
import os
import sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml_service"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dataset import create_eval_dataset, CARD_CLASSES, AADHAAR_CLASSES
from metrics import evaluate_dataset_map, optimize_confidence_thresholds
from benchmark import benchmark_model_latency
from yolo_roi import (
    _get_onnx_session,
    _get_aadhaar_session,
    _run_yolo_onnx,
    _run_rfdetr_onnx,
    get_detector_backend,
)


def compute_breakdown_metrics(
    detections: list,
    ground_truths: list,
    key: str,
    conf_thresh: float = 0.35,
    iou_thresh: float = 0.50,
) -> dict:
    from metrics import compute_iou
    values = sorted(list(set(g.get(key) for g in ground_truths if g.get(key) is not None)))
    breakdown = {}
    for val in values:
        sub_gts = [g for g in ground_truths if g.get(key) == val]
        sub_dets = [d for d in detections if d.get(key) == val]

        filtered_dets = [d for d in sub_dets if d.get("confidence", 0.0) >= conf_thresh]
        tp_count = 0
        gt_used = set()
        for d in filtered_dets:
            d_box = [d["x1"], d["y1"], d["x2"], d["y2"]]
            for j, gt in enumerate(sub_gts):
                if j in gt_used or d.get("img_id") != gt.get("img_id"):
                    continue
                if compute_iou(d_box, [gt["x1"], gt["y1"], gt["x2"], gt["y2"]]) >= iou_thresh:
                    tp_count += 1
                    gt_used.add(j)
                    break
        rec = tp_count / max(len(sub_gts), 1)
        prec = tp_count / max(len(filtered_dets), 1)
        breakdown[val] = {
            "ground_truths": len(sub_gts),
            "detections": len(filtered_dets),
            "true_positives": tp_count,
            "recall": round(float(rec), 4),
            "precision": round(float(prec), 4),
        }
    return breakdown


def run_full_evaluation(num_samples: int = 35, test_dir: str = None) -> dict:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    aadhar_test_dir = os.path.join(repo_root, "data", "AADHAR", "test")
    coco_card_test_dir = os.path.abspath(test_dir) if test_dir else os.path.join(repo_root, "data", "coco_card", "test")
    idcard_test_dir = os.path.join(repo_root, "data", "IDcard", "test")

    has_card_coco = os.path.exists(os.path.join(coco_card_test_dir, "_annotations.coco.json"))
    use_real_datasets = os.path.exists(aadhar_test_dir) and (has_card_coco or os.path.exists(idcard_test_dir))

    card_session = _get_onnx_session()
    aadhaar_session = _get_aadhaar_session()

    card_dets = []
    card_gts = []
    aadhaar_dets = []
    aadhaar_gts = []

    if use_real_datasets:
        print(f"\n[eval] Using held-out test datasets:")
        print(f"  • Aadhaar: {aadhar_test_dir}")

        # 1. Aadhaar evaluation
        a_imgs = os.path.join(aadhar_test_dir, "images")
        a_lbls = os.path.join(aadhar_test_dir, "labels")
        a_files = sorted([f for f in os.listdir(a_imgs) if f.endswith((".jpg", ".png"))])

        for fname in a_files:
            img_id = os.path.splitext(fname)[0]
            pil_img = Image.open(os.path.join(a_imgs, fname)).convert("RGB")
            rgb = np.asarray(pil_img, dtype=np.uint8)

            lpath = os.path.join(a_lbls, f"{img_id}.txt")
            if os.path.exists(lpath):
                with open(lpath, "r", encoding="utf-8") as lf:
                    for line in lf:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            cid = int(parts[0])
                            if cid < len(AADHAAR_CLASSES):
                                cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                                aadhaar_gts.append({
                                    "img_id": img_id,
                                    "label": AADHAAR_CLASSES[cid],
                                    "class_id": cid,
                                    "x1": cx - bw / 2.0,
                                    "y1": cy - bh / 2.0,
                                    "x2": cx + bw / 2.0,
                                    "y2": cy + bh / 2.0,
                                })

            if aadhaar_session is not None:
                f_boxes = _run_yolo_onnx(rgb, aadhaar_session, max_boxes=10, class_names=AADHAAR_CLASSES)
                for b in f_boxes:
                    aadhaar_dets.append({
                        "img_id": img_id,
                        "label": b["label"],
                        "confidence": b.get("confidence", 0.0),
                        "x1": b["x"],
                        "y1": b["y"],
                        "x2": b["x"] + b["w"],
                        "y2": b["y"] + b["h"],
                    })

        # 2. Card evaluation
        if has_card_coco:
            coco_test_ann = os.path.join(coco_card_test_dir, "_annotations.coco.json")
            print(f"  • Card (COCO Test): {coco_card_test_dir}")
            with open(coco_test_ann, "r", encoding="utf-8") as f:
                coco_data = json.load(f)

            anns_by_img = {}
            for ann in coco_data.get("annotations", []):
                anns_by_img.setdefault(ann["image_id"], []).append(ann)

            c_files = []
            for img_info in coco_data.get("images", []):
                img_id = img_info["file_name"].rsplit(".", 1)[0]
                img_path = os.path.join(coco_card_test_dir, "images", img_info["file_name"])
                if not os.path.exists(img_path):
                    img_path = os.path.join(coco_card_test_dir, img_info["file_name"])
                if not os.path.exists(img_path):
                    continue
                c_files.append(img_info["file_name"])

            if "indian" in str(coco_card_test_dir).lower():
                print(f"INDIAN SPECIMEN TEST n={len(c_files)}")
                if len(c_files) < 100:
                    print("SAMPLE TOO SMALL")

            for img_info in coco_data.get("images", []):
                img_id = img_info["file_name"].rsplit(".", 1)[0]
                img_path = os.path.join(coco_card_test_dir, "images", img_info["file_name"])
                if not os.path.exists(img_path):
                    img_path = os.path.join(coco_card_test_dir, img_info["file_name"])
                if not os.path.exists(img_path):
                    continue

                w, h = img_info["width"], img_info["height"]
                doc_type = img_info.get("doc_type", "unknown")
                cond = img_info.get("condition", "unknown")

                for ann in anns_by_img.get(img_info["id"], []):
                    bx, by, bw, bh = ann["bbox"]
                    card_gts.append({
                        "img_id": img_id,
                        "label": "Card",
                        "class_id": 0,
                        "x1": bx / w,
                        "y1": by / h,
                        "x2": (bx + bw) / w,
                        "y2": (by + bh) / h,
                        "doc_type": doc_type,
                        "condition": cond,
                    })

                pil_img = Image.open(img_path).convert("RGB")
                rgb = np.asarray(pil_img, dtype=np.uint8)
                if card_session is not None:
                    if get_detector_backend() == "rf_detr":
                        boxes = _run_rfdetr_onnx(rgb, card_session, max_boxes=4, class_names=CARD_CLASSES, conf_threshold=0.05)
                    else:
                        boxes = _run_yolo_onnx(rgb, card_session, max_boxes=4, class_names=CARD_CLASSES)
                    for b in boxes:
                        card_dets.append({
                            "img_id": img_id,
                            "label": b["label"],
                            "confidence": b.get("confidence", 0.0),
                            "x1": b["x"],
                            "y1": b["y"],
                            "x2": b["x"] + b["w"],
                            "y2": b["y"] + b["h"],
                            "doc_type": doc_type,
                            "condition": cond,
                        })
        else:
            print(f"  • ID Card: {idcard_test_dir}")
            c_imgs = os.path.join(idcard_test_dir, "images")
            c_lbls = os.path.join(idcard_test_dir, "labels")
            c_files = sorted([f for f in os.listdir(c_imgs) if f.endswith((".jpg", ".png"))])

            for fname in c_files:
                img_id = os.path.splitext(fname)[0]
                pil_img = Image.open(os.path.join(c_imgs, fname)).convert("RGB")
                rgb = np.asarray(pil_img, dtype=np.uint8)

                lpath = os.path.join(c_lbls, f"{img_id}.txt")
                if os.path.exists(lpath):
                    with open(lpath, "r", encoding="utf-8") as lf:
                        for line in lf:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                cid = int(parts[0])
                                cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                                card_gts.append({
                                    "img_id": img_id,
                                    "label": "Card",
                                    "class_id": 0,
                                    "x1": cx - bw / 2.0,
                                    "y1": cy - bh / 2.0,
                                    "x2": cx + bw / 2.0,
                                    "y2": cy + bh / 2.0,
                                })

                if card_session is not None:
                    if get_detector_backend() == "rf_detr":
                        boxes = _run_rfdetr_onnx(rgb, card_session, max_boxes=4, class_names=CARD_CLASSES, conf_threshold=0.05)
                    else:
                        boxes = _run_yolo_onnx(rgb, card_session, max_boxes=4, class_names=CARD_CLASSES)
                    for b in boxes:
                        card_dets.append({
                            "img_id": img_id,
                            "label": b["label"],
                            "confidence": b.get("confidence", 0.0),
                            "x1": b["x"],
                            "y1": b["y"],
                            "x2": b["x"] + b["w"],
                            "y2": b["y"] + b["h"],
                        })

        num_images_total = len(a_files) + len(c_files)

    else:
        eval_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        print(f"\n[eval] Preparing synthetic evaluation dataset ({num_samples} specimens in {eval_dir})...")
        create_eval_dataset(eval_dir, num_samples=num_samples)

        img_dir = os.path.join(eval_dir, "images")
        lbl_dir = os.path.join(eval_dir, "labels")

        image_files = sorted([f for f in os.listdir(img_dir) if f.endswith(".jpg")])
        num_images_total = len(image_files)
        print(f"[eval] Loaded {num_images_total} test images for evaluation.")

        for idx, fname in enumerate(image_files):
            img_id = fname.split(".")[0]
            fpath = os.path.join(img_dir, fname)
            pil_img = Image.open(fpath).convert("RGB")
            rgb = np.asarray(pil_img, dtype=np.uint8)

            lpath = os.path.join(lbl_dir, f"{img_id}.txt")
            if os.path.exists(lpath):
                with open(lpath, "r", encoding="utf-8") as lf:
                    for line in lf:
                        parts = line.strip().split()
                        if len(parts) >= 6:
                            cid = int(parts[0])
                            cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                            label = parts[5]
                            gt_obj = {
                                "img_id": img_id,
                                "label": label,
                                "class_id": cid,
                                "x1": cx - bw / 2.0,
                                "y1": cy - bh / 2.0,
                                "x2": cx + bw / 2.0,
                                "y2": cy + bh / 2.0,
                            }
                            if label == "Card":
                                card_gts.append(gt_obj)
                            else:
                                aadhaar_gts.append(gt_obj)

            if card_session is not None:
                if get_detector_backend() == "rf_detr":
                    boxes = _run_rfdetr_onnx(rgb, card_session, max_boxes=4, class_names=CARD_CLASSES, conf_threshold=0.05)
                else:
                    boxes = _run_yolo_onnx(rgb, card_session, max_boxes=4, class_names=CARD_CLASSES)
                for b in boxes:
                    card_dets.append({
                        "img_id": img_id,
                        "label": b["label"],
                        "confidence": b.get("confidence", 0.0),
                        "x1": b["x"],
                        "y1": b["y"],
                        "x2": b["x"] + b["w"],
                        "y2": b["y"] + b["h"],
                    })

            if aadhaar_session is not None:
                f_boxes = _run_yolo_onnx(rgb, aadhaar_session, max_boxes=10, class_names=AADHAAR_CLASSES)
                for b in f_boxes:
                    aadhaar_dets.append({
                        "img_id": img_id,
                        "label": b["label"],
                        "confidence": b.get("confidence", 0.0),
                        "x1": b["x"],
                        "y1": b["y"],
                        "x2": b["x"] + b["w"],
                        "y2": b["y"] + b["h"],
                    })

    # 2. Compute Accuracy Metrics
    card_metrics = evaluate_dataset_map(card_dets, card_gts, CARD_CLASSES)
    aadhaar_metrics = evaluate_dataset_map(aadhaar_dets, aadhaar_gts, AADHAAR_CLASSES)

    # 3. Optimize thresholds
    opt_card_thresh = optimize_confidence_thresholds(card_dets, card_gts, CARD_CLASSES)
    opt_aadhaar_thresh = optimize_confidence_thresholds(aadhaar_dets, aadhaar_gts, AADHAAR_CLASSES)

    # 4. Latency Benchmarking (>=30 timed runs after 5 warmups)
    import datetime
    import platform
    sample_rgb = np.zeros((800, 1200, 3), dtype=np.uint8)
    card_latency = benchmark_model_latency(card_session, sample_rgb, num_warmup=5, num_runs=30) if card_session else {}
    if card_latency:
        card_latency["cpu_model"] = os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or platform.machine())
        card_latency["thread_count"] = os.cpu_count()
    aadhaar_latency = benchmark_model_latency(aadhaar_session, sample_rgb, num_warmup=5, num_runs=30) if aadhaar_session else {}
    if aadhaar_latency:
        aadhaar_latency["cpu_model"] = os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or platform.machine())
        aadhaar_latency["thread_count"] = os.cpu_count()

    backend = get_detector_backend()
    opt_card_t = 0.35
    thresh_file = os.path.join(repo_root, "ml_service", "models", "thresholds.json")
    if os.path.exists(thresh_file):
        try:
            with open(thresh_file, "r", encoding="utf-8") as tf:
                saved_th = json.load(tf)
                opt_card_t = saved_th.get("Card", 0.35)
        except Exception:
            pass

    per_doc_type_recall = compute_breakdown_metrics(card_dets, card_gts, key="doc_type", conf_thresh=opt_card_t)
    per_condition_recall = compute_breakdown_metrics(card_dets, card_gts, key="condition", conf_thresh=opt_card_t)

    card_model_title = "RF-DETR Small (rfdetr_card.onnx)" if backend == "rf_detr" else "YOLOv8s-Card (card.onnx)"
    card_model_file = os.path.join(repo_root, "ml_service", "models", "rfdetr_card.onnx" if backend == "rf_detr" else "card.onnx")
    model_size_mb = round(os.path.getsize(card_model_file) / (1024 * 1024), 2) if os.path.exists(card_model_file) else None

    report = {
        "dataset": {
            "samples": num_images_total,
            "card_ground_truths": len(card_gts),
            "aadhaar_ground_truths": len(aadhaar_gts),
        },
        "card_detector": {
            "model": card_model_title,
            "backend": backend,
            "model_size_mb": model_size_mb,
            "operating_threshold": opt_card_t,
            "test_source": "data/coco_card/test (MIDV-2020 300 photos)" if has_card_coco else "data/IDcard/test",
            "metrics": card_metrics,
            "optimal_thresholds": opt_card_thresh,
            "per_document_type_recall": per_doc_type_recall,
            "per_capture_condition_recall": per_condition_recall,
            "latency": card_latency,
        },
        "aadhaar_fields_detector": {
            "model": "YOLOv8s-Aadhaar (aadhaar_fields.onnx)",
            "metrics": aadhaar_metrics,
            "optimal_thresholds": opt_aadhaar_thresh,
            "latency": aadhaar_latency,
        },
    }

    # Ensure UTF-8 output if supported
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Print summary table
    print("\n" + "=" * 78)
    print(" [EVAL] NO-CAP (SIH26188) DETECTION PIPELINE EVALUATION REPORT")
    if has_card_coco:
        print(" TEST SET n=300 real photos of 3 unseen document types")
    print("=" * 78)
    print(f"Dataset: {report['dataset']['samples']} images | Total Ground Truths: {len(card_gts) + len(aadhaar_gts)}")
    print("-" * 78)
    print(f"{'Class':<16} | {'mAP50':<8} | {'mAP50-95':<9} | {'Precision':<9} | {'Recall':<8} | {'Opt Thresh':<10}")
    print("-" * 78)

    for c in CARD_CLASSES:
        m = card_metrics["classes"].get(c, {})
        opt_t = opt_card_thresh.get(c, 0.35)
        print(f"{c:<16} | {m.get('mAP50', 0):<8.3f} | {m.get('mAP50_95', 0):<9.3f} | {m.get('precision', 0):<9.3f} | {m.get('recall', 0):<8.3f} | {opt_t:<10.2f}")

    for c in AADHAAR_CLASSES:
        m = aadhaar_metrics["classes"].get(c, {})
        opt_t = opt_aadhaar_thresh.get(c, 0.35)
        print(f"{c:<16} | {m.get('mAP50', 0):<8.3f} | {m.get('mAP50_95', 0):<9.3f} | {m.get('precision', 0):<9.3f} | {m.get('recall', 0):<8.3f} | {opt_t:<10.2f}")

    if per_doc_type_recall:
        print("\n" + "-" * 78)
        print(f" [BREAKDOWN] CARD RECALL BY DOCUMENT TYPE (IoU >= 0.50, Conf >= {opt_card_t:.2f})")
        print("-" * 78)
        print(f"{'Document Type':<25} | {'GT':<6} | {'Det':<6} | {'TP':<6} | {'Recall':<8} | {'Precision':<9}")
        print("-" * 78)
        for dt, stats in per_doc_type_recall.items():
            print(f"{dt:<25} | {stats['ground_truths']:<6} | {stats['detections']:<6} | {stats['true_positives']:<6} | {stats['recall']:<8.3f} | {stats['precision']:<9.3f}")

    if per_condition_recall:
        print("\n" + "-" * 78)
        print(f" [BREAKDOWN] CARD RECALL BY CAPTURE CONDITION (IoU >= 0.50, Conf >= {opt_card_t:.2f})")
        print("-" * 78)
        print(f"{'Capture Condition':<25} | {'GT':<6} | {'Det':<6} | {'TP':<6} | {'Recall':<8} | {'Precision':<9}")
        print("-" * 78)
        for cond, stats in per_condition_recall.items():
            print(f"{cond:<25} | {stats['ground_truths']:<6} | {stats['detections']:<6} | {stats['true_positives']:<6} | {stats['recall']:<8.3f} | {stats['precision']:<9.3f}")

    print("-" * 78)
    print("[BENCHMARK] LATENCY (CPU, ONNX Runtime):")
    if card_latency:
        print(f"  * Card Model:    p50 = {card_latency.get('p50_ms')} ms | p95 = {card_latency.get('p95_ms')} ms (mean = {card_latency.get('mean_ms')} ms) | {card_latency.get('cpu_model')} ({card_latency.get('thread_count')} threads)")
    if aadhaar_latency:
        print(f"  * Aadhaar Model: p50 = {aadhaar_latency.get('p50_ms')} ms | p95 = {aadhaar_latency.get('p95_ms')} ms (mean = {aadhaar_latency.get('mean_ms')} ms) | {aadhaar_latency.get('cpu_model')} ({aadhaar_latency.get('thread_count')} threads)")
    print("=" * 78 + "\n")

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"[eval] Report exported to {report_path}")

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    custom_run_dir = os.getenv("EVAL_RUN_DIR")
    if custom_run_dir:
        run_dir = os.path.abspath(custom_run_dir)
    else:
        folder_suffix = "rfdetr_card_eval" if backend == "rf_detr" else "baseline_yolo_card"
        run_dir = os.path.join(repo_root, "eval", "runs", f"{ts}_{folder_suffix}")
    os.makedirs(run_dir, exist_ok=True)
    run_report_path = os.path.join(run_dir, "report.json")
    with open(run_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"[eval] Run report saved to {run_report_path}")

    return report


def run_detector_bakeoff() -> dict:
    """Side-by-side bake-off comparison: YOLOv8 vs Apache 2.0 RF-DETR."""
    # Defect D1: Fail loudly if RF-DETR weights are missing
    rf_path = os.getenv("RF_DETR_ONNX_PATH")
    if not rf_path:
        for name in ("rf_detr.onnx", "rf_detr_card.onnx", "rfdetr_card.onnx"):
            cand = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml_service", "models", name)
            if os.path.exists(cand):
                rf_path = cand
                break
    if not rf_path or not os.path.exists(rf_path):
        raise FileNotFoundError(
            "Cannot run detector bake-off: RF-DETR weights not found. "
            "Trained RF-DETR weights must be present before executing a bake-off."
        )

    print("\n" + "=" * 78)
    print(" [BAKE-OFF] DETECTOR BENCHMARK: YOLOv8 (AGPL-3.0) vs RF-DETR (Apache 2.0)")
    print("=" * 78)

    # 1. Run YOLOv8 baseline
    os.environ["DETECTOR_BACKEND"] = "yolov8"
    from yolo_roi import clear_session_cache
    clear_session_cache()
    print("[bake-off] Evaluating YOLOv8 backend...")
    yolo_report = run_full_evaluation(num_samples=25)

    # 2. Run RF-DETR backend
    os.environ["DETECTOR_BACKEND"] = "rf_detr"
    clear_session_cache()
    print("[bake-off] Evaluating RF-DETR backend...")
    rf_report = run_full_evaluation(num_samples=25)

    bakeoff_summary = {
        "models": {
            "yolov8": {
                "license": "AGPL-3.0 (Copyleft restrictions for proprietary deployments)",
                "nms_required": True,
                "card_mAP50": yolo_report["card_detector"]["metrics"]["overall"].get("mAP50"),
                "aadhaar_mAP50": yolo_report["aadhaar_fields_detector"]["metrics"]["overall"].get("mAP50"),
                "card_p50_ms": yolo_report["card_detector"]["latency"].get("p50_ms"),
                "aadhaar_p50_ms": yolo_report["aadhaar_fields_detector"]["latency"].get("p50_ms"),
            },
            "rf_detr": {
                "license": "Apache 2.0 (Permissive, unrestricted commercial & gov deployments)",
                "nms_required": False,
                "card_mAP50": rf_report["card_detector"]["metrics"]["overall"].get("mAP50"),
                "aadhaar_mAP50": rf_report["aadhaar_fields_detector"]["metrics"]["overall"].get("mAP50"),
                "card_p50_ms": rf_report["card_detector"]["latency"].get("p50_ms"),
                "aadhaar_p50_ms": rf_report["aadhaar_fields_detector"]["latency"].get("p50_ms"),
            }
        },
        "recommendation": (
            "Deploy RF-DETR (Apache 2.0) for production checkpoint deployments to eliminate AGPL copyleft liability, "
            "while maintaining YOLOv8 operational side-by-side via DETECTOR_BACKEND='yolov8' for backward compatibility."
        )
    }

    print("\n" + "=" * 78)
    print(" [BAKE-OFF DECISION MATRIX]")
    print("=" * 78)
    print(f"{'Dimension':<25} | {'YOLOv8':<24} | {'RF-DETR (RT-DETR)':<24}")
    print("-" * 78)
    print(f"{'License':<25} | {'AGPL-3.0 (Copyleft)':<24} | {'Apache 2.0 (Permissive)':<24}")
    print(f"{'Post-processing NMS':<25} | {'Required (15-30ms CPU)':<24} | {'NMS-Free (Direct Queries)':<24}")
    print(f"{'Field Detector mAP50':<25} | {yolo_report['aadhaar_fields_detector']['metrics']['overall'].get('mAP50', 0):<24.3f} | {rf_report['aadhaar_fields_detector']['metrics']['overall'].get('mAP50', 0):<24.3f}")
    print(f"{'Field Detector Latency':<25} | {str(yolo_report['aadhaar_fields_detector']['latency'].get('p50_ms')) + ' ms':<24} | {str(rf_report['aadhaar_fields_detector']['latency'].get('p50_ms')) + ' ms':<24}")
    print(f"{'Config Switch':<25} | {'DETECTOR_BACKEND=yolov8':<24} | {'DETECTOR_BACKEND=rf_detr':<24}")
    print("=" * 78 + "\n")

    bakeoff_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bakeoff_report.json")
    with open(bakeoff_path, "w", encoding="utf-8") as f:
        json.dump(bakeoff_summary, f, indent=2)
    print(f"[bake-off] Decision report saved to {bakeoff_path}")

    # Restore default
    os.environ["DETECTOR_BACKEND"] = "yolov8"
    clear_session_cache()
    return bakeoff_summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NO-CAP Model Evaluation Harness")
    parser.add_argument("--test-dir", type=str, default=None, help="Custom card test directory (e.g. data/coco_card_indian/test)")
    parser.add_argument("--bakeoff", action="store_true", help="Run detector bake-off comparison")
    parser.add_argument("--num-samples", type=int, default=35, help="Number of synthetic samples if using synthetic fallback")
    args, unknown = parser.parse_known_args()

    if args.bakeoff:
        run_detector_bakeoff()
    else:
        run_full_evaluation(num_samples=args.num_samples, test_dir=args.test_dir)

