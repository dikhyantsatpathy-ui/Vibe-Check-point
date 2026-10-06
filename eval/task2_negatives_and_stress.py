"""
Task 2 Harness: Negative Sets & Scale Stress Diagnostics (SIH26188 Work Order v3.1).
Evaluates:
  2a. Negative set (>=100 background-only crops from test-type photos + >=50 non-card rectangles).
      Computes False Positive Rate (FPR per image) at threshold 0.40. Gate: <= 0.05.
  2b. Scale stress diagnostic: 2x and 3x canvas reflection padding on the 300 test photos.
"""

import os
import sys
import json
import random
import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import onnxruntime as ort

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app"))
sys.path.insert(0, str(REPO_ROOT / "eval"))

from yolo_roi import _run_rfdetr_onnx, clear_session_cache
from metrics import compute_iou

def generate_negative_set(output_dir: Path, num_photo_bg: int = 100, num_synth_neg: int = 60, seed: int = 42) -> List[dict]:
    rng = random.Random(seed)
    np_rng = np.random.RandomState(seed)

    test_coco_path = REPO_ROOT / "data" / "coco_card" / "test" / "_annotations.coco.json"
    test_img_dir = REPO_ROOT / "data" / "coco_card" / "test"

    with open(test_coco_path, "r", encoding="utf-8") as f:
        coco = json.load(f)

    anns_by_img = {}
    for a in coco["annotations"]:
        anns_by_img.setdefault(a["image_id"], []).append(a)

    negatives = []
    bg_crops_dir = output_dir / "negatives_test_bg"
    bg_crops_dir.mkdir(parents=True, exist_ok=True)
    synth_neg_dir = output_dir / "negatives_synth_non_card"
    synth_neg_dir.mkdir(parents=True, exist_ok=True)

    # 1. Background crops from test-type photos outside card bbox
    valid_test_imgs = [img for img in coco["images"] if anns_by_img.get(img["id"])]
    crop_count = 0
    attempts = 0

    while crop_count < num_photo_bg and attempts < 1000:
        attempts += 1
        img_info = rng.choice(valid_test_imgs)
        fpath = test_img_dir / "images" / img_info["file_name"]
        if not fpath.exists():
            fpath = test_img_dir / img_info["file_name"]
        if not fpath.exists():
            continue

        try:
            with Image.open(fpath) as im:
                w, h = im.size
                gt_bbox = anns_by_img[img_info["id"]][0]["bbox"]
                gx, gy, gw, gh = gt_bbox

                # Choose crop size
                cw = rng.randint(250, min(500, w - 50))
                ch = rng.randint(250, min(500, h - 50))

                # Check 4 non-overlapping quadrants relative to card
                candidates = []
                if gy > ch + 20:  # Above
                    candidates.append((rng.randint(0, max(0, w - cw)), rng.randint(0, max(0, int(gy - ch)))))
                if (h - (gy + gh)) > ch + 20:  # Below
                    candidates.append((rng.randint(0, max(0, w - cw)), rng.randint(int(gy + gh), max(int(gy + gh), h - ch))))
                if gx > cw + 20:  # Left
                    candidates.append((rng.randint(0, max(0, int(gx - cw))), rng.randint(0, max(0, h - ch))))
                if (w - (gx + gw)) > cw + 20:  # Right
                    candidates.append((rng.randint(int(gx + gw), max(int(gx + gw), w - cw)), rng.randint(0, max(0, h - ch))))

                if not candidates:
                    continue

                cx1, cy1 = rng.choice(candidates)
                crop_im = im.crop((cx1, cy1, cx1 + cw, cy1 + ch)).resize((640, 640))
                crop_fname = f"neg_bg_{crop_count:03d}.jpg"
                save_p = bg_crops_dir / crop_fname
                crop_im.save(save_p, quality=90)

                negatives.append({
                    "file_name": crop_fname,
                    "path": str(save_p),
                    "source": "test_photo_background",
                    "doc_type": img_info.get("doc_type", "unknown"),
                })
                crop_count += 1
        except Exception:
            continue

    # 2. Synthetic non-card rectangles (plain colored papers, receipts, textured wood, cloth)
    for i in range(num_synth_neg):
        bg_type = rng.choice(["receipt", "plain_color", "lined_paper", "noise_texture"])
        im = Image.new("RGB", (640, 640), color=(rng.randint(180, 240), rng.randint(180, 240), rng.randint(180, 240)))
        draw = ImageDraw.Draw(im)

        if bg_type == "receipt":
            # Draw gray paper with horizontal text-like lines
            rx = rng.randint(80, 160)
            ry = rng.randint(80, 160)
            rw = rng.randint(240, 400)
            rh = rng.randint(300, 440)
            draw.rectangle([rx, ry, rx + rw, ry + rh], fill=(245, 245, 240), outline=(180, 180, 180))
            for line_y in range(ry + 20, ry + rh - 20, 18):
                lw = rng.randint(rw // 3, rw - 30)
                draw.line([(rx + 15, line_y), (rx + 15 + lw, line_y)], fill=(80, 80, 80), width=2)
        elif bg_type == "plain_color":
            # Random colored rectangles
            rx = rng.randint(60, 150)
            ry = rng.randint(60, 150)
            rw = rng.randint(200, 420)
            rh = rng.randint(150, 350)
            fill_col = (rng.randint(50, 220), rng.randint(50, 220), rng.randint(50, 220))
            draw.rectangle([rx, ry, rx + rw, ry + rh], fill=fill_col, outline=(30, 30, 30))
        elif bg_type == "lined_paper":
            for ly in range(40, 600, 25):
                draw.line([(30, ly), (610, ly)], fill=(180, 200, 230), width=1)
        elif bg_type == "noise_texture":
            noise_arr = np_rng.randint(100, 220, (640, 640, 3), dtype=np.uint8)
            im = Image.fromarray(noise_arr)

        synth_fname = f"neg_synth_{i:03d}.jpg"
        save_p = synth_neg_dir / synth_fname
        im.save(save_p, quality=90)

        negatives.append({
            "file_name": synth_fname,
            "path": str(save_p),
            "source": f"synth_{bg_type}",
        })

    print(f"[task2] Generated {len(negatives)} negative test images ({crop_count} photo bg crops, {num_synth_neg} synthetic non-cards).")
    return negatives


def run_task2a_negative_evaluation(negatives: List[dict], session: ort.InferenceSession, conf_threshold: float = 0.40) -> dict:
    fps_by_source = {}
    total_fp = 0

    for neg in negatives:
        src = neg["source"]
        fps_by_source.setdefault(src, {"total_images": 0, "false_positives": 0, "detections": []})
        fps_by_source[src]["total_images"] += 1

        with Image.open(neg["path"]) as im:
            rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
            dets = _run_rfdetr_onnx(rgb, session, max_boxes=4, class_names=["Card"], conf_threshold=conf_threshold)

            if len(dets) > 0:
                fps_by_source[src]["false_positives"] += 1
                total_fp += 1
                fps_by_source[src]["detections"].append({
                    "file": neg["file_name"],
                    "top_conf": dets[0].get("confidence", 0.0),
                    "count": len(dets),
                })

    summary = {
        "total_negative_images": len(negatives),
        "confidence_threshold": conf_threshold,
        "total_false_positives": total_fp,
        "overall_fp_rate": round(total_fp / max(1, len(negatives)), 4),
        "provisional_gate_max_fp_rate": 0.05,
        "gate_pass": (total_fp / max(1, len(negatives))) <= 0.05,
        "breakdown_by_source": {},
    }

    for src, st in fps_by_source.items():
        summary["breakdown_by_source"][src] = {
            "total_images": st["total_images"],
            "false_positives": st["false_positives"],
            "fp_rate": round(st["false_positives"] / max(1, st["total_images"]), 4),
        }

    return summary


def run_task2b_scale_stress_diagnostic(session: ort.InferenceSession, conf_threshold: float = 0.40) -> dict:
    """Scale stress diagnostic (2x and 3x reflect padding)."""
    test_coco_path = REPO_ROOT / "data" / "coco_card" / "test" / "_annotations.coco.json"
    test_img_dir = REPO_ROOT / "data" / "coco_card" / "test"

    with open(test_coco_path, "r", encoding="utf-8") as f:
        coco = json.load(f)

    anns_by_img = {}
    for a in coco["annotations"]:
        anns_by_img.setdefault(a["image_id"], []).append(a)

    scales = [2, 3]
    results = {}

    for factor in scales:
        hits = 0
        total = 0

        for img_info in coco["images"]:
            fpath = test_img_dir / "images" / img_info["file_name"]
            if not fpath.exists():
                fpath = test_img_dir / img_info["file_name"]
            if not fpath.exists():
                continue

            gts = anns_by_img.get(img_info["id"], [])
            if not gts:
                continue

            total += 1
            with Image.open(fpath) as im:
                orig_w, orig_h = im.size
                arr = np.asarray(im.convert("RGB"), dtype=np.uint8)

                # Pad canvas by factor (reflect padding)
                # target dimensions: orig_w * factor, orig_h * factor
                pad_w = orig_w * (factor - 1) // 2
                pad_h = orig_h * (factor - 1) // 2

                padded_arr = np.pad(arr, ((pad_h, pad_h), (pad_w, pad_w), (0, 0)), mode="reflect")
                padded_im = Image.fromarray(padded_arr).resize((orig_w, orig_h), Image.Resampling.BILINEAR)
                input_arr = np.asarray(padded_im, dtype=np.uint8)

                # Adjusted GT box after padding and resizing back to (orig_w, orig_h)
                gx, gy, gw, gh = gts[0]["bbox"]
                padded_total_w = orig_w + 2 * pad_w
                padded_total_h = orig_h + 2 * pad_h

                adj_x1 = (gx + pad_w) / padded_total_w
                adj_y1 = (gy + pad_h) / padded_total_h
                adj_w = gw / padded_total_w
                adj_h = gh / padded_total_h
                gt_box_norm = [adj_x1, adj_y1, adj_x1 + adj_w, adj_y1 + adj_h]

                dets = _run_rfdetr_onnx(input_arr, session, max_boxes=2, class_names=["Card"], conf_threshold=conf_threshold)
                matched = False
                for d in dets:
                    d_box = [d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]]
                    if compute_iou(d_box, gt_box_norm) >= 0.50:
                        matched = True
                        break
                if matched:
                    hits += 1

        rec = round(hits / max(1, total), 4)
        results[f"scale_{factor}x"] = {
            "total_tested": total,
            "detected_tp": hits,
            "recall": rec,
            "label": "SYNTHETIC DIAGNOSTIC",
        }

    return results


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_task2_negatives_and_stress"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load INT8 model session
    model_path = str(REPO_ROOT / "ml_service" / "models" / "rfdetr_card_int8.onnx")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])

    print("=== TASK 2a: GENERATING & EVALUATING NEGATIVE TEST SET ===")
    negatives = generate_negative_set(out_dir, num_photo_bg=100, num_synth_neg=60)
    neg_results = run_task2a_negative_evaluation(negatives, session, conf_threshold=0.40)

    print("\n=== TASK 2b: SCALE STRESS DIAGNOSTIC (2x, 3x CANVAS PADDING) ===")
    stress_results = run_task2b_scale_stress_diagnostic(session, conf_threshold=0.40)

    task2_report = {
        "timestamp": ts,
        "model": "rfdetr_card_int8.onnx",
        "task2a_negatives": neg_results,
        "task2b_scale_stress": stress_results,
    }

    report_path = out_dir / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(task2_report, f, indent=2)

    print("\n" + "=" * 70)
    print("[TASK 2] SUMMARY RESULTS:")
    print(f"  Negatives Tested:     {neg_results['total_negative_images']}")
    print(f"  False Positives:      {neg_results['total_false_positives']}")
    print(f"  FP Rate:              {neg_results['overall_fp_rate']:.2%} (Gate: <= 5.00%) -> {'PASS' if neg_results['gate_pass'] else 'FAIL'}")
    print(f"  2x Scale Stress Recall: {stress_results['scale_2x']['recall']:.2%}")
    print(f"  3x Scale Stress Recall: {stress_results['scale_3x']['recall']:.2%}")
    print(f"Report saved to: {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
