"""
CPU latency benchmarking tool for ONNX Runtime models: p50/p95 breakdown (SIH26188).
Measures Pre-processing (letterbox), Inference (ONNX), and Post-processing (NMS + unscale).
"""

import time
import numpy as np
from typing import Dict, Any, Tuple


def benchmark_model_latency(
    session,
    sample_rgb: np.ndarray,
    num_warmup: int = 3,
    num_runs: int = 25,
) -> Dict[str, Any]:
    """Measure p50 and p95 CPU execution latency for an ONNX model session."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
    from yolo_roi import letterbox, _run_yolo_onnx

    # 1. Warm-up
    for _ in range(num_warmup):
        _run_yolo_onnx(sample_rgb, session)

    latencies_total = []
    latencies_pre = []
    latencies_inf = []
    latencies_post = []

    inp = session.get_inputs()[0]
    inp_h = inp.shape[2] if len(inp.shape) == 4 and isinstance(inp.shape[2], int) else 640
    inp_w = inp.shape[3] if len(inp.shape) == 4 and isinstance(inp.shape[3], int) else 640
    input_name = inp.name
    output_name = session.get_outputs()[0].name

    for _ in range(num_runs):
        t0 = time.perf_counter()

        # Preprocessing
        t_pre0 = time.perf_counter()
        canvas, scale, padding, orig_dim = letterbox(sample_rgb, (inp_w, inp_h))
        input_tensor = canvas.astype(np.float32).transpose(2, 0, 1) / 255.0
        input_tensor = np.expand_dims(input_tensor, axis=0)
        t_pre1 = time.perf_counter()

        # Inference
        t_inf0 = time.perf_counter()
        raw_preds = session.run([output_name], {input_name: input_tensor})[0]
        t_inf1 = time.perf_counter()

        # Postprocessing
        t_post0 = time.perf_counter()
        # Parse outputs via _run_yolo_onnx
        _run_yolo_onnx(sample_rgb, session)
        t_post1 = time.perf_counter()

        t_total = time.perf_counter() - t0

        latencies_total.append(t_total * 1000.0)
        latencies_pre.append((t_pre1 - t_pre0) * 1000.0)
        latencies_inf.append((t_inf1 - t_inf0) * 1000.0)
        latencies_post.append((t_post1 - t_post0) * 1000.0)

    p50 = float(np.percentile(latencies_total, 50))
    p95 = float(np.percentile(latencies_total, 95))
    mean = float(np.mean(latencies_total))

    return {
        "runs": num_runs,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "mean_ms": round(mean, 2),
        "min_ms": round(float(np.min(latencies_total)), 2),
        "max_ms": round(float(np.max(latencies_total)), 2),
        "breakdown": {
            "preprocess_ms": round(float(np.mean(latencies_pre)), 2),
            "inference_ms": round(float(np.mean(latencies_inf)), 2),
            "postprocess_ms": round(float(np.mean(latencies_post)), 2),
        },
    }
