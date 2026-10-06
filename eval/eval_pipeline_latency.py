"""Pipeline Latency Benchmark (Phase 7.3).

Measures end-to-end detector chain latency per document type at 2 threads CPU:
  Chain 1 (Passport / Travel doc): Card Detector v2 -> Doc-Type Classifier v2 -> MRZ Detector
  Chain 2 (Aadhaar): Card Detector v2 -> Doc-Type Classifier v2 -> Aadhaar Field Detector (YOLOv8)
  Chain 3 (Generic ID / PAN): Card Detector v2 -> Doc-Type Classifier v2

Budget constraint: detector chain <= 900 ms.
"""

from __future__ import annotations

import datetime
import io
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import onnxruntime as ort
import psutil
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_pipeline_latency")

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "ml_service" / "models"
CARD_MODEL = MODELS_DIR / "rfdetr_card_int8.onnx"
DOCTYPE_MODEL = MODELS_DIR / "doctype_v2.onnx"
MRZ_MODEL = MODELS_DIR / "rfdetr_mrz_int8.onnx"
AADHAAR_MODEL = MODELS_DIR / "aadhaar_fields.onnx"
if not AADHAAR_MODEL.exists():
    AADHAAR_MODEL = REPO_ROOT / "app" / "models" / "aadhaar_fields.onnx"


def create_2thread_session(model_path: Path) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])


def letterbox_prep(img: Image.Image, target_size: int = 512) -> np.ndarray:
    w, h = img.size
    scale = min(target_size / w, target_size / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = img.resize((nw, nh), Image.Resampling.BILINEAR)
    pad_w = (target_size - nw) // 2
    pad_h = (target_size - nh) // 2
    canvas = Image.new("RGB", (target_size, target_size), (114, 114, 114))
    canvas.paste(resized, (pad_w, pad_h))
    arr = np.array(canvas, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))
    return np.expand_dims(arr, 0)


def doctype_prep(img: Image.Image) -> np.ndarray:
    resized = img.resize((224, 224), Image.Resampling.BILINEAR)
    arr = np.array(resized, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    arr = np.transpose(arr, (2, 0, 1))
    return np.expand_dims(arr, 0)


def benchmark_chain(
    chain_name: str,
    steps: List[Any],
    test_img: Image.Image,
    warmup: int = 5,
    runs: int = 30,
) -> Dict[str, Any]:
    # Warmup
    for _ in range(warmup):
        for step_fn in steps:
            _ = step_fn(test_img)

    times_ms = []
    for _ in range(runs):
        t0 = time.perf_counter()
        for step_fn in steps:
            _ = step_fn(test_img)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        times_ms.append(dt_ms)

    times_ms.sort()
    p50 = float(np.percentile(times_ms, 50))
    p95 = float(np.percentile(times_ms, 95))
    p99 = float(np.percentile(times_ms, 99))
    mean = float(np.mean(times_ms))

    logger.info(
        "Chain %s (%d runs): p50 = %.2f ms, p95 = %.2f ms, mean = %.2f ms (Budget <= 900 ms: %s)",
        chain_name, runs, p50, p95, mean, "PASS" if p50 <= 900.0 else "FAIL"
    )

    return {
        "chain_name": chain_name,
        "runs": runs,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "mean_ms": round(mean, 2),
        "min_ms": round(float(times_ms[0]), 2),
        "max_ms": round(float(times_ms[-1]), 2),
        "budget_ms": 900.0,
        "passed": bool(p50 <= 900.0),
    }


def main():
    logger.info("Initializing Pipeline Latency Benchmark (2 CPU Threads)...")
    process = psutil.Process()
    ram_initial_mb = process.memory_info().rss / (1024 * 1024)

    # 1. Load ONNX sessions with 2 threads
    card_sess = create_2thread_session(CARD_MODEL)
    doctype_sess = create_2thread_session(DOCTYPE_MODEL)
    mrz_sess = create_2thread_session(MRZ_MODEL)
    aadhaar_sess = create_2thread_session(AADHAAR_MODEL) if AADHAAR_MODEL.exists() else None

    # Step functions
    def step_card(img: Image.Image):
        tensor = letterbox_prep(img, 512)
        inp_name = card_sess.get_inputs()[0].name
        return card_sess.run(None, {inp_name: tensor})

    def step_doctype(img: Image.Image):
        tensor = doctype_prep(img)
        inp_name = doctype_sess.get_inputs()[0].name
        return doctype_sess.run(None, {inp_name: tensor})

    def step_mrz(img: Image.Image):
        tensor = letterbox_prep(img, 512)
        inp_name = mrz_sess.get_inputs()[0].name
        return mrz_sess.run(None, {inp_name: tensor})

    def step_aadhaar(img: Image.Image):
        if aadhaar_sess is None:
            return None
        tensor = letterbox_prep(img, 640)
        inp_name = aadhaar_sess.get_inputs()[0].name
        return aadhaar_sess.run(None, {inp_name: tensor})

    # Test sample image
    test_img = Image.new("RGB", (1280, 800), (200, 200, 200))

    results = {}

    # Benchmark Chain 1: Passport / Visa (Card -> DocType -> MRZ)
    c1 = benchmark_chain(
        "passport_mrz_chain",
        [step_card, step_doctype, step_mrz],
        test_img,
    )
    results["passport_mrz_chain"] = c1

    # Benchmark Chain 2: Aadhaar (Card -> DocType -> Aadhaar Fields)
    if aadhaar_sess is not None:
        c2 = benchmark_chain(
            "aadhaar_field_chain",
            [step_card, step_doctype, step_aadhaar],
            test_img,
        )
        results["aadhaar_field_chain"] = c2

    # Benchmark Chain 3: Generic ID / PAN (Card -> DocType)
    c3 = benchmark_chain(
        "generic_id_chain",
        [step_card, step_doctype],
        test_img,
    )
    results["generic_id_chain"] = c3

    ram_final_mb = process.memory_info().rss / (1024 * 1024)
    logger.info("RAM Initial: %.2f MB | RAM Final: %.2f MB", ram_initial_mb, ram_final_mb)

    all_passed = all(r["passed"] for r in results.values())

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_pipeline_latency"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / "report.json"

    report_data = {
        "timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "cpu_threads": 2,
        "gate_budget_ms": 900.0,
        "all_chains_passed": all_passed,
        "ram_initial_mb": round(ram_initial_mb, 2),
        "ram_final_mb": round(ram_final_mb, 2),
        "chains": results,
    }

    report_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    logger.info("Latency benchmark report saved to: %s", report_file)


if __name__ == "__main__":
    main()
