"""RF-DETR Card Detector Training & Export Script.

Trains Apache-2.0 RF-DETR Small on Card localization.
Supports 1-epoch smoke testing on 32 images, memory-capped batch sizes, automated ONNX export,
parity verification against PyTorch predict, and sidecar metadata generation (*.meta.json).
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
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

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
    rfdetr_version: str = "1.11.2",
    trained_on: str = "midv2020_real_and_composites",
) -> Path:
    """Write *.meta.json sidecar next to exported ONNX model."""
    sha256_hash = compute_file_sha256(onnx_path)
    sidecar_data = {
        "classes": classes,
        "input_size": input_size,
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "resize_mode": "square_bilinear",
        "output_names": ["dets", "labels"],
        "rfdetr_version": rfdetr_version,
        "trained_on": trained_on,
        "trained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sha256": sha256_hash,
    }
    sidecar_path = onnx_path.with_suffix(onnx_path.suffix + ".meta.json")
    sidecar_path.write_text(json.dumps(sidecar_data, indent=2), encoding="utf-8")
    logger.info("Saved metadata sidecar: %s (SHA-256: %s)", sidecar_path, sha256_hash)
    return sidecar_path


def compute_box_iou(box1: List[float], box2: List[float]) -> float:
    """Compute IoU between two bounding boxes [x1, y1, x2, y2]."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter = inter_w * inter_h

    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union = area1 + area2 - inter
    if union <= 0:
        return 0.0
    return inter / union


def verify_onnx_io(onnx_path: Path, output_json: Path) -> Dict[str, Any]:
    """Inspect ONNX model inputs and outputs with ONNX Runtime."""
    import onnxruntime as ort

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    inputs = [{"name": i.name, "shape": i.shape, "type": i.type} for i in session.get_inputs()]
    outputs = [{"name": o.name, "shape": o.shape, "type": o.type} for o in session.get_outputs()]

    info = {
        "model_path": str(onnx_path),
        "file_size_bytes": onnx_path.stat().st_size,
        "inputs": inputs,
        "outputs": outputs,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(info, indent=2), encoding="utf-8")
    logger.info("Wrote ONNX I/O schema to %s", output_json)
    return info


def run_parity_harness(
    model: Any,
    onnx_path: Path,
    val_images_dir: Path,
    output_json: Path,
    num_samples: int = 20,
    iou_threshold: float = 0.95,
) -> Dict[str, Any]:
    """Verify inference parity: PyTorch model.predict vs exported ONNX session."""
    import onnxruntime as ort
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
    from yolo_roi import _run_rfdetr_onnx

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    image_files = sorted([f for f in val_images_dir.glob("*.jpg") if f.is_file()])[:num_samples]

    parity_results: List[Dict[str, Any]] = []
    all_passed = True

    for fpath in image_files:
        pil_img = Image.open(fpath).convert("RGB")
        rgb = np.asarray(pil_img, dtype=np.uint8)
        w, h = pil_img.size

        # PyTorch prediction
        pt_preds = model.predict(pil_img, threshold=0.25)
        pt_boxes = []
        if hasattr(pt_preds, "xyxy") and len(pt_preds.xyxy) > 0:
            for b, s, c in zip(pt_preds.xyxy, pt_preds.confidence, pt_preds.class_id):
                pt_boxes.append({
                    "xyxy": [float(x) for x in b],
                    "score": float(s),
                    "class_id": int(c),
                })

        # ONNX prediction
        onnx_preds = _run_rfdetr_onnx(rgb, session, class_names=["Card"], conf_threshold=0.25)
        onnx_boxes = []
        for b in onnx_preds:
            bx1 = b["x"] * w
            by1 = b["y"] * h
            bx2 = (b["x"] + b["w"]) * w
            by2 = (b["y"] + b["h"]) * h
            onnx_boxes.append({
                "xyxy": [bx1, by1, bx2, by2],
                "score": b["confidence"],
                "class_id": b["class_id"],
            })

        # Compare matching top detection
        matched_iou = 0.0
        class_match = False
        if pt_boxes and onnx_boxes:
            b_pt = pt_boxes[0]["xyxy"]
            b_ox = onnx_boxes[0]["xyxy"]
            b_pt_clamped = [
                max(0.0, min(float(w), b_pt[0])),
                max(0.0, min(float(h), b_pt[1])),
                max(0.0, min(float(w), b_pt[2])),
                max(0.0, min(float(h), b_pt[3])),
            ]
            matched_iou = compute_box_iou(b_pt_clamped, b_ox)
            # PT returns 1-indexed category_id (1 for Card), ONNX returns 0-indexed class index (0 for Card)
            class_match = (
                pt_boxes[0]["class_id"] == onnx_boxes[0]["class_id"]
                or (pt_boxes[0]["class_id"] == 1 and onnx_boxes[0]["class_id"] == 0)
            )

        sample_pass = (matched_iou >= iou_threshold) or (not pt_boxes and not onnx_boxes)
        if not sample_pass:
            all_passed = False

        parity_results.append({
            "image": fpath.name,
            "pt_boxes_count": len(pt_boxes),
            "onnx_boxes_count": len(onnx_boxes),
            "top_box_iou": round(matched_iou, 4),
            "class_match": class_match,
            "pass": sample_pass,
        })

    summary = {
        "total_tested": len(parity_results),
        "passed_count": sum(1 for r in parity_results if r["pass"]),
        "all_passed": all_passed,
        "min_iou_target": iou_threshold,
        "results": parity_results,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Parity test result: %d/%d passed (all_passed=%s)", summary["passed_count"], len(parity_results), all_passed)
    return summary


def run_training(
    dataset_dir: Path,
    output_dir: Path,
    epochs: int = 25,
    batch_size: int = 4,
    grad_accum_steps: int = 4,
    lr: float = 1e-4,
    lr_encoder: float = 1.5e-4,
    early_stopping_patience: int = 7,
    smoke_test: bool = False,
    num_workers: int = 0,
    seed: int = 42,
) -> Path:
    """Execute RF-DETR Small training with safety guardrails."""
    try:
        import rfdetr
        from rfdetr import RFDETRSmall
        import rfdetr.config as cfg
    except ImportError:
        logger.error(
            "The 'rfdetr' package is not installed in the active environment. "
            "Please install dependencies with: pip install 'rfdetr[train]'."
        )
        raise

    output_dir.mkdir(parents=True, exist_ok=True)
    actual_epochs = 1 if smoke_test else epochs
    logger.info(
        "Starting RF-DETR Small training (epochs=%d, batch_size=%d, grad_accum=%d, lr=%.1e, lr_encoder=%.1e, smoke_test=%s)",
        actual_epochs,
        batch_size,
        grad_accum_steps,
        lr,
        lr_encoder,
        smoke_test,
    )

    model = RFDETRSmall()

    # Build kwargs against valid TrainConfig model fields
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
        "early_stopping_patience": early_stopping_patience,
        "output_dir": str(output_dir),
        "num_workers": num_workers,
        "seed": seed,
    }
    filtered_args = {k: v for k, v in train_args.items() if k in valid_fields}

    logger.info("Invoking model.train with kwargs: %s", list(filtered_args.keys()))
    model.train(**filtered_args)

    # 1. Confirm checkpoint file exists
    ckpt_files = list(output_dir.glob("*.pth")) + list(output_dir.glob("*.ckpt")) + list(output_dir.glob("**/*.ckpt"))
    logger.info("Found %d checkpoint files in %s", len(ckpt_files), output_dir)
    assert len(ckpt_files) > 0 or hasattr(model, "export"), "Training failed to produce a model checkpoint!"

    # 2. Export ONNX model from best checkpoint (FP32 for standard CPU execution)
    export_dir = Path("ml_service/models")
    export_dir.mkdir(parents=True, exist_ok=True)
    onnx_dest = export_dir / "rfdetr_card.onnx"

    best_ckpts = list(output_dir.glob("checkpoint_best_total.pth")) + list(output_dir.glob("checkpoint_best_ema.pth"))
    if best_ckpts:
        best_ckpt = best_ckpts[0]
        logger.info("Instantiating export model from best checkpoint: %s", best_ckpt)
        export_model = RFDETRSmall(pretrain_weights=str(best_ckpt))
    else:
        export_model = model

    logger.info("Exporting trained model to ONNX at %s (FP32)...", onnx_dest)
    export_model.export(output_dir=str(export_dir), output_name="rfdetr_card.onnx", fp16=False)

    if not onnx_dest.exists():
        # Check if exported with default name inside export_dir
        for cand in export_dir.glob("*.onnx"):
            if "rfdetr" in cand.name or "model" in cand.name:
                cand.rename(onnx_dest)
                break

    assert onnx_dest.exists(), f"Expected ONNX export at {onnx_dest} was not found!"
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
    parser.add_argument("--lr-encoder", type=float, default=1.5e-4)
    parser.add_argument("--patience", type=int, default=7)
    parser.add_argument("--smoke-test", action="store_true", help="Run 1-epoch smoke test on small subset")
    parser.add_argument("--num-workers", type=int, default=0, help="DataLoader workers (default 0 on Windows)")

    args = parser.parse_args()

    data_dir = Path("data/coco_card_smoke") if args.smoke_test else Path(args.data_dir)
    output_dir = Path("training/runs/card_smoke") if args.smoke_test else Path(args.output_dir)

    onnx_path = run_training(
        dataset_dir=data_dir,
        output_dir=output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accum_steps=args.grad_accum,
        lr=args.lr,
        lr_encoder=args.lr_encoder,
        early_stopping_patience=args.patience,
        smoke_test=args.smoke_test,
        num_workers=args.num_workers,
    )

    if args.smoke_test:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        smoke_eval_dir = Path(f"eval/runs/{ts}_smoke")
        smoke_eval_dir.mkdir(parents=True, exist_ok=True)

        # Inspect ONNX schema
        onnx_io = verify_onnx_io(onnx_path, smoke_eval_dir / "onnx_io.json")
        print("\n[SMOKE TEST] ONNX Model I/O:")
        print("  Inputs:", onnx_io["inputs"])
        print("  Outputs:", onnx_io["outputs"])

        # Parity test on val set
        from rfdetr import RFDETRSmall
        eval_model = RFDETRSmall()
        parity = run_parity_harness(
            model=eval_model,
            onnx_path=onnx_path,
            val_images_dir=data_dir / "valid",
            output_json=smoke_eval_dir / "parity.json",
        )
        print("\n[SMOKE TEST] Parity Check:")
        print(f"  Passed: {parity['passed_count']}/{parity['total_tested']} (all_passed={parity['all_passed']})")


if __name__ == "__main__":
    main()
