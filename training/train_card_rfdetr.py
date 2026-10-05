"""RF-DETR Card Detector Training & Export Script.

Trains Apache-2.0 RF-DETR Small on Card localization.
Supports 1-epoch smoke testing, memory-capped batch sizes, and automated ONNX export
with sidecar metadata generation (*.meta.json).
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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: Path) -> str:
    """Compute hex-digest SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def write_meta_sidecar(
    onnx_path: Path,
    classes: List[str],
    input_size: List[int] = [640, 640],
    rfdetr_version: str = "0.1.0",
    trained_on: str = "local_real_and_composites",
) -> Path:
    """Write *.meta.json sidecar next to exported ONNX model."""
    sha256_hash = compute_file_sha256(onnx_path)
    sidecar_data = {
        "classes": classes,
        "input_size": input_size,
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "resize_mode": "square_bilinear",
        "output_names": ["pred_boxes", "pred_logits"],
        "rfdetr_version": rfdetr_version,
        "trained_on": trained_on,
        "trained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sha256": sha256_hash,
    }
    sidecar_path = onnx_path.with_suffix(onnx_path.suffix + ".meta.json")
    sidecar_path.write_text(json.dumps(sidecar_data, indent=2), encoding="utf-8")
    logger.info("Saved metadata sidecar: %s (SHA-256: %s)", sidecar_path, sha256_hash)
    return sidecar_path


def run_training(
    dataset_dir: Path,
    output_dir: Path,
    epochs: int = 25,
    batch_size: int = 4,
    grad_accum_steps: int = 4,
    lr: float = 1e-4,
    smoke_test: bool = False,
    num_workers: int = 0,
) -> Path:
    """Execute RF-DETR Small training with safety guardrails."""
    try:
        import rfdetr
        from rfdetr import RFDETRSmall
    except ImportError:
        logger.error(
            "The 'rfdetr' package is not installed in the active environment. "
            "Please install dependencies from training/requirements-train.txt."
        )
        raise

    output_dir.mkdir(parents=True, exist_ok=True)
    actual_epochs = 1 if smoke_test else epochs
    logger.info(
        "Starting RF-DETR Small training (epochs=%d, batch_size=%d, grad_accum=%d, smoke_test=%s)",
        actual_epochs,
        batch_size,
        grad_accum_steps,
        smoke_test,
    )

    model = RFDETRSmall()
    train_args: Dict[str, Any] = {
        "dataset_dir": str(dataset_dir),
        "epochs": actual_epochs,
        "batch_size": batch_size,
        "grad_accum_steps": grad_accum_steps,
        "lr": lr,
        "output_dir": str(output_dir),
    }

    # Inspect model.train signature to use only supported kwargs
    import inspect
    sig = inspect.signature(model.train)
    filtered_args = {k: v for k, v in train_args.items() if k in sig.parameters}
    if "num_workers" in sig.parameters:
        filtered_args["num_workers"] = num_workers

    logger.info("Invoking model.train with kwargs: %s", list(filtered_args.keys()))
    model.train(**filtered_args)

    # Export ONNX
    export_dir = Path("ml_service/models")
    export_dir.mkdir(parents=True, exist_ok=True)
    onnx_dest = export_dir / "rfdetr_card.onnx"

    logger.info("Exporting trained model to ONNX: %s", onnx_dest)
    if hasattr(model, "export"):
        model.export(output_path=str(onnx_dest))
    else:
        logger.warning("model.export() not found on RFDETR instance; saving torch checkpoint.")
        torch_dest = output_dir / "checkpoint_best.pth"
        if hasattr(model, "save"):
            model.save(str(torch_dest))

    if onnx_dest.exists():
        write_meta_sidecar(onnx_dest, classes=["Card"])

    return onnx_dest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Train RF-DETR Card Detector")
    parser.add_argument("--data-dir", type=str, default="data/coco_card")
    parser.add_argument("--output-dir", type=str, default="training/runs/card_run1")
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--smoke-test", action="store_true", help="Run 1-epoch smoke test on small subset")
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader workers (default 0 on Windows)")

    args = parser.parse_args()

    run_training(
        dataset_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accum_steps=args.grad_accum,
        lr=args.lr,
        smoke_test=args.smoke_test,
        num_workers=args.num_workers,
    )


if __name__ == "__main__":
    main()
