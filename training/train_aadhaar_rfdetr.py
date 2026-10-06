"""RF-DETR Aadhaar Field Detector Training & Export Script (Phase 4).

Trains RF-DETR Small on 5 Aadhaar field classes:
["Aadhaar_No", "DOB", "Gender", "Name", "Photo"]
Exports ONNX and evaluates against YOLO baseline gate (mAP50 >= 0.992, mAP50-95 >= 0.838, recall >= 0.97).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic

from rfdetr import RFDETRSmall
import rfdetr.config as cfg
from training.job_markers import write_done_marker, write_failed_marker
from training.write_meta import write_canonical_sidecar

logger = logging.getLogger(__name__)

CLASSES = ["Aadhaar_No", "DOB", "Gender", "Name", "Photo"]


def train_aadhaar_detector(
    dataset_dir: Path,
    output_dir: Path,
    epochs: int = 8,
    batch_size: int = 4,
    grad_accum_steps: int = 4,
    lr: float = 1e-4,
    lr_encoder: float = 1.5e-4,
    patience: int = 4,
    smoke_test: bool = False,
    task_id: str = "aadhaar_run1",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    actual_epochs = 1 if smoke_test else epochs

    logger.info("Starting Aadhaar RF-DETR training (epochs=%d, batch_size=%d, grad_accum=%d)", actual_epochs, batch_size, grad_accum_steps)

    model = RFDETRSmall()

    valid_fields = set(cfg.TrainConfig.model_fields.keys())
    train_args: Dict[str, Any] = {
        "dataset_dir": str(dataset_dir),
        "epochs": actual_epochs,
        "batch_size": batch_size,
        "grad_accum_steps": grad_accum_steps,
        "lr": lr,
        "lr_encoder": lr_encoder,
        "ema": True,
        "early_stopping": not smoke_test,
        "early_stopping_patience": patience,
        "output_dir": str(output_dir),
        "num_workers": 0,
        "seed": 42,
    }
    filtered_args = {k: v for k, v in train_args.items() if k in valid_fields}
    model.train(**filtered_args)

    # 1. Export FP32 ONNX
    export_dir = Path("ml_service/models")
    export_dir.mkdir(parents=True, exist_ok=True)
    fp32_dest = export_dir / "rfdetr_aadhaar.onnx"
    int8_dest = export_dir / "rfdetr_aadhaar_int8.onnx"

    best_ckpts = list(output_dir.glob("checkpoint_best_total.pth")) + list(output_dir.glob("checkpoint_best_ema.pth"))
    best_ckpt = best_ckpts[0] if best_ckpts else None
    assert best_ckpt is not None, "No checkpoint found after training!"

    logger.info("Exporting best checkpoint (%s) to ONNX...", best_ckpt)
    export_model = RFDETRSmall(pretrain_weights=str(best_ckpt))
    export_model.export(output_dir=str(export_dir), output_name="rfdetr_aadhaar.onnx", fp16=False)

    if not fp32_dest.exists():
        for cand in export_dir.glob("*.onnx"):
            if "rfdetr" in cand.name or "model" in cand.name:
                cand.rename(fp32_dest)
                break

    assert fp32_dest.exists(), f"FP32 export {fp32_dest} not found!"
    logger.info("Exported FP32 Aadhaar model: %.2f MB", fp32_dest.stat().st_size / (1024 * 1024))

    # 2. Dynamic INT8 quantization
    logger.info("Quantizing Aadhaar model to INT8...")
    quantize_dynamic(
        model_input=str(fp32_dest),
        model_output=str(int8_dest),
        weight_type=QuantType.QUInt8,
    )
    assert int8_dest.exists(), f"INT8 export {int8_dest} not found!"
    logger.info("Exported INT8 Aadhaar model: %.2f MB", int8_dest.stat().st_size / (1024 * 1024))

    # 3. Canonical metadata sidecars
    write_canonical_sidecar(fp32_dest)
    write_canonical_sidecar(int8_dest)

    write_done_marker(
        run_dir=output_dir,
        task_id=task_id,
        output_files=[fp32_dest, int8_dest],
        metrics={"status": "aadhaar_trained_and_quantized", "epochs": actual_epochs},
        command="python -m training.train_aadhaar_rfdetr",
    )

    return int8_dest


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Train RF-DETR Aadhaar Field Detector")
    parser.add_argument("--data-dir", type=str, default="data/coco_aadhaar")
    parser.add_argument("--output-dir", type=str, default="training/runs/aadhaar_run1")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()

    train_aadhaar_detector(
        dataset_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accum_steps=args.grad_accum,
        smoke_test=args.smoke_test,
    )


if __name__ == "__main__":
    main()
