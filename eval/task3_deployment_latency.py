"""
Task 3 Deployment Latency & Parity Benchmark (SIH26188 Work Order v3.1).
Measures:
  1. YOLO card, RF-DETR FP32, and RF-DETR INT8 at intra_op_num_threads = 1 and 2.
  2. 5 warmups + 30 timed runs with pre/infer/post breakdown, peak RAM, and CPU model name.
  3. Re-runs INT8 parity harness with IoU >= 0.95.
Saves results to eval/runs/<ts>_task3_deployment_latency/report.json.
"""

import os
import sys
import json
import time
import datetime
import platform
import tracemalloc
from pathlib import Path
from PIL import Image
import numpy as np
import onnxruntime as ort

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app"))
sys.path.insert(0, str(REPO_ROOT / "training"))
sys.path.insert(0, str(REPO_ROOT / "eval"))

from yolo_roi import (
    letterbox,
    _postprocess_yolo_predictions,
    _run_yolo_onnx,
    preprocess_rfdetr,
    _postprocess_rfdetr_predictions,
    _run_rfdetr_onnx,
)
from train_card_rfdetr import run_parity_harness
from rfdetr import RFDETRSmall

def benchmark_deployment_latency(
    model_path: str,
    is_rfdetr: bool,
    threads: int,
    sample_rgb: np.ndarray,
    num_warmup: int = 5,
    num_runs: int = 30,
) -> dict:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])
    inp = session.get_inputs()[0]
    inp_h = inp.shape[2] if len(inp.shape) == 4 and isinstance(inp.shape[2], int) else 640
    inp_w = inp.shape[3] if len(inp.shape) == 4 and isinstance(inp.shape[3], int) else 640
    input_name = inp.name
    out_names = [o.name for o in session.get_outputs()]

    # Warmup
    for _ in range(num_warmup):
        if is_rfdetr:
            _run_rfdetr_onnx(sample_rgb, session, max_boxes=4, class_names=["Card"], conf_threshold=0.25)
        else:
            _run_yolo_onnx(sample_rgb, session)

    latencies_pre = []
    latencies_inf = []
    latencies_post = []
    latencies_total = []

    tracemalloc.start()

    for _ in range(num_runs):
        if is_rfdetr:
            t0 = time.perf_counter()
            input_tensor, orig_dim = preprocess_rfdetr(sample_rgb, (inp_w, inp_h))
            t1 = time.perf_counter()

            outputs = session.run(out_names, {input_name: input_tensor})
            t2 = time.perf_counter()

            boxes_tensor, logits_tensor = None, None
            for name, arr in zip(out_names, outputs):
                name_l = name.lower()
                if "box" in name_l or "det" in name_l or (arr.ndim == 3 and arr.shape[-1] == 4):
                    boxes_tensor = arr
                elif "logit" in name_l or "score" in name_l or "label" in name_l or (arr.ndim == 3 and arr.shape[-1] != 4):
                    logits_tensor = arr
            _postprocess_rfdetr_predictions(
                boxes=boxes_tensor,
                logits=logits_tensor,
                orig_dim=orig_dim,
                class_names=["Card"],
                conf_threshold=0.25,
            )
            t3 = time.perf_counter()
        else:
            t0 = time.perf_counter()
            canvas, scale, padding, orig_dim = letterbox(sample_rgb, (inp_w, inp_h))
            input_tensor = canvas.astype(np.float32).transpose(2, 0, 1) / 255.0
            input_tensor = np.expand_dims(input_tensor, axis=0)
            t1 = time.perf_counter()

            raw_preds = session.run(out_names[:1], {input_name: input_tensor})[0]
            t2 = time.perf_counter()

            _postprocess_yolo_predictions(
                raw_preds=raw_preds,
                scale=scale,
                padding=padding,
                orig_dim=orig_dim,
                conf_threshold=0.25,
                iou_threshold=0.45,
            )
            t3 = time.perf_counter()

        pre_ms = (t1 - t0) * 1000.0
        inf_ms = (t2 - t1) * 1000.0
        post_ms = (t3 - t2) * 1000.0
        total_ms = pre_ms + inf_ms + post_ms

        latencies_pre.append(pre_ms)
        latencies_inf.append(inf_ms)
        latencies_post.append(post_ms)
        latencies_total.append(total_ms)

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "threads": threads,
        "runs": num_runs,
        "p50_total_ms": round(float(np.percentile(latencies_total, 50)), 2),
        "p95_total_ms": round(float(np.percentile(latencies_total, 95)), 2),
        "mean_total_ms": round(float(np.mean(latencies_total)), 2),
        "breakdown_ms": {
            "preprocess_mean": round(float(np.mean(latencies_pre)), 2),
            "inference_mean": round(float(np.mean(latencies_inf)), 2),
            "postprocess_mean": round(float(np.mean(latencies_post)), 2),
        },
        "peak_ram_mb": round(peak_mem / (1024 * 1024), 2),
    }


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_task3_deployment_latency"
    out_dir.mkdir(parents=True, exist_ok=True)

    cpu_model = os.environ.get("PROCESSOR_IDENTIFIER", platform.processor() or platform.machine())
    sample_rgb = np.zeros((800, 1200, 3), dtype=np.uint8)

    models = [
        ("yolo_card", str(REPO_ROOT / "ml_service" / "models" / "card.onnx"), False),
        ("rfdetr_fp32", str(REPO_ROOT / "ml_service" / "models" / "rfdetr_card.onnx"), True),
        ("rfdetr_int8", str(REPO_ROOT / "ml_service" / "models" / "rfdetr_card_int8.onnx"), True),
    ]

    benchmark_results = {}

    for name, path, is_rf in models:
        benchmark_results[name] = {}
        for threads in [1, 2]:
            print(f"[task3] Benchmarking {name} with {threads} thread(s)...")
            res = benchmark_deployment_latency(path, is_rf, threads, sample_rgb)
            benchmark_results[name][f"{threads}_thread"] = res

    # Re-run INT8 parity with IoU >= 0.95
    ckpt_path = REPO_ROOT / "training" / "runs" / "card_run2" / "checkpoint_best_ema.pth"
    if not ckpt_path.exists():
        ckpt_path = REPO_ROOT / "training" / "runs" / "card_run1" / "checkpoint_best_ema.pth"
    model_pt = RFDETRSmall(pretrain_weights=str(ckpt_path))
    val_dir = REPO_ROOT / "data" / "coco_card" / "valid"
    parity_out = out_dir / "int8_parity_iou95.json"

    parity_res = run_parity_harness(model_pt, Path(REPO_ROOT / "ml_service" / "models" / "rfdetr_card_int8.onnx"), val_dir, parity_out, num_samples=20, iou_threshold=0.95)

    full_report = {
        "timestamp": ts,
        "environment": {
            "cpu_model": cpu_model,
            "target_space_spec": "Small CPU Space (~2 vCPU, marked UNVERIFIED)",
        },
        "benchmarks": benchmark_results,
        "parity_int8_iou95": parity_res,
    }

    report_path = out_dir / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    print("\n" + "=" * 70)
    print("[TASK 3] DEPLOYMENT LATENCY BENCHMARK (1 & 2 threads):")
    print(f"  CPU: {cpu_model}")
    print("-" * 70)
    for m_name in ["yolo_card", "rfdetr_fp32", "rfdetr_int8"]:
        t1 = benchmark_results[m_name]["1_thread"]["p50_total_ms"]
        t2 = benchmark_results[m_name]["2_thread"]["p50_total_ms"]
        inf2 = benchmark_results[m_name]["2_thread"]["breakdown_ms"]["inference_mean"]
        ram2 = benchmark_results[m_name]["2_thread"]["peak_ram_mb"]
        print(f"  {m_name:<14} | 1T p50={t1:6.1f} ms | 2T p50={t2:6.1f} ms (infer={inf2:5.1f} ms, RAM={ram2} MB)")
    print("-" * 70)
    print(f"  INT8 Parity (IoU >= 0.95): {parity_res.get('passed_count')}/{parity_res.get('total_tested')} Passed (all_passed={parity_res.get('all_passed')})")
    print(f"Report saved to: {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
