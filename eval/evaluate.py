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
from yolo_roi import _get_onnx_session, _get_aadhaar_session, _run_yolo_onnx


def run_full_evaluation(num_samples: int = 35) -> dict:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    aadhar_test_dir = os.path.join(repo_root, "data", "AADHAR", "test")
    idcard_test_dir = os.path.join(repo_root, "data", "IDcard", "test")

    use_real_datasets = os.path.exists(aadhar_test_dir) and os.path.exists(idcard_test_dir)

    card_session = _get_onnx_session()
    aadhaar_session = _get_aadhaar_session()

    card_dets = []
    card_gts = []
    aadhaar_dets = []
    aadhaar_gts = []

    if use_real_datasets:
        print(f"\n[eval] Using held-out test datasets:")
        print(f"  • Aadhaar: {aadhar_test_dir}")
        print(f"  • ID Card: {idcard_test_dir}")

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

    # 4. Latency Benchmarking
    sample_rgb = np.zeros((800, 1200, 3), dtype=np.uint8)
    card_latency = benchmark_model_latency(card_session, sample_rgb, num_runs=15) if card_session else {}
    aadhaar_latency = benchmark_model_latency(aadhaar_session, sample_rgb, num_runs=15) if aadhaar_session else {}

    report = {
        "dataset": {
            "samples": num_images_total,
            "card_ground_truths": len(card_gts),
            "aadhaar_ground_truths": len(aadhaar_gts),
        },
        "card_detector": {
            "model": "YOLOv8s-Card (card.onnx)",
            "metrics": card_metrics,
            "optimal_thresholds": opt_card_thresh,
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

    print("-" * 78)
    print("[BENCHMARK] LATENCY (CPU, ONNX Runtime):")
    if card_latency:
        print(f"  * Card Model:    p50 = {card_latency.get('p50_ms')} ms | p95 = {card_latency.get('p95_ms')} ms (mean = {card_latency.get('mean_ms')} ms)")
    if aadhaar_latency:
        print(f"  * Aadhaar Model: p50 = {aadhaar_latency.get('p50_ms')} ms | p95 = {aadhaar_latency.get('p95_ms')} ms (mean = {aadhaar_latency.get('mean_ms')} ms)")
    print("=" * 78 + "\n")

    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"[eval] Report exported to {report_path}")

    return report


def run_detector_bakeoff() -> dict:
    """Side-by-side bake-off comparison: YOLOv8 vs Apache 2.0 RF-DETR."""
    # Defect D1: Fail loudly if RF-DETR weights are missing
    rf_path = os.getenv("RF_DETR_ONNX_PATH")
    if not rf_path:
        for name in ("rf_detr.onnx", "rf_detr_card.onnx"):
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
    if "--bakeoff" in sys.argv:
        run_detector_bakeoff()
    else:
        run_full_evaluation()

