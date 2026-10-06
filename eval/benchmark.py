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
    from yolo_roi import (
        letterbox,
        _postprocess_yolo_predictions,
        _run_yolo_onnx,
        preprocess_rfdetr,
        _postprocess_rfdetr_predictions,
        _run_rfdetr_onnx,
    )

    inp = session.get_inputs()[0]
    inp_h = inp.shape[2] if len(inp.shape) == 4 and isinstance(inp.shape[2], int) else 640
    inp_w = inp.shape[3] if len(inp.shape) == 4 and isinstance(inp.shape[3], int) else 640
    input_name = inp.name

    sess_outputs = session.get_outputs()
    is_rfdetr = len(sess_outputs) > 1 or any(
        "det" in o.name.lower() or "label" in o.name.lower() for o in sess_outputs
    )

    # 1. Warm-up
    for _ in range(num_warmup):
        if is_rfdetr:
            _run_rfdetr_onnx(sample_rgb, session, max_boxes=4, class_names=["Card"], conf_threshold=0.25)
        else:
            _run_yolo_onnx(sample_rgb, session)

    latencies_total = []
    latencies_pre = []
    latencies_inf = []
    latencies_post = []

    out_names = [o.name for o in sess_outputs]

    for _ in range(num_runs):
        if is_rfdetr:
            # RF-DETR Preprocessing (Square resize + ImageNet normalize)
            t_pre0 = time.perf_counter()
            input_tensor, orig_dim = preprocess_rfdetr(sample_rgb, (inp_w, inp_h))
            t_pre1 = time.perf_counter()

            # Inference
            t_inf0 = time.perf_counter()
            outputs = session.run(out_names, {input_name: input_tensor})
            t_inf1 = time.perf_counter()

            # Postprocessing (Query parsing + thresholding + unscale)
            t_post0 = time.perf_counter()
            boxes_tensor, logits_tensor = None, None
            for name, arr in zip(out_names, outputs):
                name_lower = name.lower()
                if "box" in name_lower or "det" in name_lower or (arr.ndim == 3 and arr.shape[-1] == 4):
                    boxes_tensor = arr
                elif "logit" in name_lower or "score" in name_lower or "label" in name_lower or (arr.ndim == 3 and arr.shape[-1] != 4):
                    logits_tensor = arr
            _postprocess_rfdetr_predictions(
                boxes=boxes_tensor,
                logits=logits_tensor,
                orig_dim=orig_dim,
                class_names=["Card"],
                conf_threshold=0.25,
            )
            t_post1 = time.perf_counter()
        else:
            # YOLO Preprocessing (Letterbox + Transpose + Normalize)
            t_pre0 = time.perf_counter()
            canvas, scale, padding, orig_dim = letterbox(sample_rgb, (inp_w, inp_h))
            input_tensor = canvas.astype(np.float32).transpose(2, 0, 1) / 255.0
            input_tensor = np.expand_dims(input_tensor, axis=0)
            t_pre1 = time.perf_counter()

            # Inference (ONNX Session)
            t_inf0 = time.perf_counter()
            raw_preds = session.run(out_names[:1], {input_name: input_tensor})[0]
            t_inf1 = time.perf_counter()

            # Postprocessing (Candidate thresholding + Per-class NMS + Coordinate unscaling)
            t_post0 = time.perf_counter()
            _postprocess_yolo_predictions(
                raw_preds=raw_preds,
                scale=scale,
                padding=padding,
                orig_dim=orig_dim,
                conf_threshold=0.25,
                iou_threshold=0.45,
            )
            t_post1 = time.perf_counter()

        pre_ms = (t_pre1 - t_pre0) * 1000.0
        inf_ms = (t_inf1 - t_inf0) * 1000.0
        post_ms = (t_post1 - t_post0) * 1000.0
        total_ms = pre_ms + inf_ms + post_ms

        latencies_total.append(total_ms)
        latencies_pre.append(pre_ms)
        latencies_inf.append(inf_ms)
        latencies_post.append(post_ms)

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
