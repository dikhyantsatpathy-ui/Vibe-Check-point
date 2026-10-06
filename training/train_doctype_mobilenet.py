"""Training and ONNX Export Script for Document-Type Classifier v2 (Phase 6).

Architecture: MobileNetV3-Small (lightweight CPU-optimized backbone).
Classes: ["aadhaar", "pan", "voter_id", "driving_licence", "passport", "nepali_citizenship", "bhutan_cid", "other"]
Input Size: 224x224 (Resize keep-aspect + CenterCrop 224)
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
from typing import Any, Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models

logger = logging.getLogger(__name__)

CLASSES = [
    "aadhaar",
    "pan",
    "voter_id",
    "driving_licence",
    "passport",
    "nepali_citizenship",
    "bhutan_cid",
    "other",
]


class DoctypeDataset(Dataset):
    def __init__(self, root_dir: Path, split: str = "train", img_size: int = 224):
        self.samples: List[Tuple[Path, int]] = []
        self.img_size = img_size
        split_dir = root_dir / split
        for idx, cname in enumerate(CLASSES):
            cdir = split_dir / cname
            if cdir.exists():
                for im in cdir.glob("*.jpg"):
                    self.samples.append((im, idx))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        im_path, label = self.samples[idx]
        with Image.open(im_path) as im:
            img = im.convert("RGB")

        # Resize keeping aspect ratio
        w, h = img.size
        size = self.img_size
        if w <= h:
            nw, nh = size, int(round(h * size / w))
        else:
            nh, nw = size, int(round(w * size / h))
        img = img.resize((nw, nh), Image.BILINEAR)

        # Center crop 224x224
        x0 = max(0, (nw - size) // 2)
        y0 = max(0, (nh - size) // 2)
        img = img.crop((x0, y0, x0 + size, y0 + size))

        arr = np.asarray(img, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(arr.transpose(2, 0, 1))
        return tensor, label


def train_doctype_model(
    dataset_dir: Path,
    output_dir: Path,
    epochs: int = 15,
    batch_size: int = 16,
    lr: float = 1e-3,
    device: str = "cuda" if torch.cuda.is_available() else "cpu",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    train_ds = DoctypeDataset(dataset_dir, split="train")
    val_ds = DoctypeDataset(dataset_dir, split="valid")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, len(CLASSES))
    model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    best_val_acc = 0.0
    best_ckpt = output_dir / "doctype_best.pt"

    if best_ckpt.exists() and epochs == 0:
        logger.info("Using existing checkpoint %s without re-training.", best_ckpt)
    else:
        for epoch in range(epochs):
            model.train()
            total_loss, correct, total = 0.0, 0, 0
            for x, y in train_loader:
                x, y = x.to(device), y.to(device)
                optimizer.zero_grad()
                out = model(x)
                loss = criterion(out, y)
                loss.backward()
                optimizer.step()

                total_loss += loss.item() * len(y)
                correct += (out.argmax(dim=-1) == y).sum().item()
                total += len(y)

            train_acc = correct / max(total, 1)

            model.eval()
            v_correct, v_total = 0, 0
            with torch.no_grad():
                for x, y in val_loader:
                    x, y = x.to(device), y.to(device)
                    out = model(x)
                    v_correct += (out.argmax(dim=-1) == y).sum().item()
                    v_total += len(y)
            val_acc = v_correct / max(v_total, 1)

            logger.info(
                "Epoch %02d/%02d: Train Loss: %.4f, Train Acc: %.4f | Val Acc: %.4f",
                epoch + 1, epochs, total_loss / max(total, 1), train_acc, val_acc
            )

            if val_acc >= best_val_acc:
                best_val_acc = val_acc
                torch.save(model.state_dict(), best_ckpt)

        logger.info("Training complete. Best validation accuracy: %.4f. Saved to %s", best_val_acc, best_ckpt)

    # 1. Export to ONNX
    model.load_state_dict(torch.load(best_ckpt, map_location="cpu"))
    model.cpu().eval()

    onnx_dest = output_dir / "doctype_v2.onnx"
    dummy_input = torch.zeros(1, 3, 224, 224, dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_dest),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        opset_version=14,
        dynamo=False,
    )
    logger.info("Exported ONNX model to %s (size: %.2f MB)", onnx_dest, onnx_dest.stat().st_size / (1024 * 1024))

    # 2. Dynamic INT8 Quantization
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8_dest = output_dir / "doctype_v2_int8.onnx"
    quantize_dynamic(
        model_input=str(onnx_dest),
        model_output=str(int8_dest),
        weight_type=QuantType.QUInt8,
    )
    logger.info("Quantized INT8 model to %s (size: %.2f MB)", int8_dest, int8_dest.stat().st_size / (1024 * 1024))

    # Copy models to ml_service/models and app/models
    ml_models = Path("ml_service/models")
    ml_models.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(onnx_dest, ml_models / "doctype_v2.onnx")
    shutil.copy2(int8_dest, ml_models / "doctype_v2_int8.onnx")

    app_models = Path("app/models")
    app_models.mkdir(parents=True, exist_ok=True)
    shutil.copy2(onnx_dest, app_models / "doctype_v2.onnx")

    # 3. Comprehensive Evaluation on Validation Set via ONNX FP32
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    sess = ort.InferenceSession(str(onnx_dest), sess_options=opts, providers=["CPUExecutionProvider"])

    y_true, y_pred = [], []
    for x, y in val_loader:
        x_np = x.numpy()
        outs = sess.run(None, {"input": x_np})[0]
        preds = outs.argmax(axis=-1)
        y_true.extend(y.tolist())
        y_pred.extend(preds.tolist())

    y_true_np = np.array(y_true)
    y_pred_np = np.array(y_pred)

    overall_acc = float((y_true_np == y_pred_np).mean())

    per_class_metrics = {}
    f1_list = []
    for idx, cname in enumerate(CLASSES):
        tp = int(((y_pred_np == idx) & (y_true_np == idx)).sum())
        fp = int(((y_pred_np == idx) & (y_true_np != idx)).sum())
        fn = int(((y_pred_np != idx) & (y_true_np == idx)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = (2 * prec * rec) / max(prec + rec, 1e-6)
        n_true = int((y_true_np == idx).sum())
        per_class_metrics[cname] = {
            "n_true": n_true,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "status": "VALIDATED" if n_true >= 30 else "INDICATIVE ONLY",
        }
        f1_list.append(f1)

    macro_f1 = float(np.mean(f1_list))
    logger.info("Doctype v2 Evaluation: Overall Acc: %.4f, Macro-F1: %.4f", overall_acc, macro_f1)
    for cname, m in per_class_metrics.items():
        logger.info("  %s (n=%d): Prec=%.4f, Rec=%.4f, F1=%.4f [%s]", cname, m["n_true"], m["precision"], m["recall"], m["f1"], m["status"])

    # 4. Latency benchmark on 2 threads
    import time
    dummy = np.zeros((1, 3, 224, 224), dtype=np.float32)
    for _ in range(5):
        sess.run(None, {"input": dummy})
    latencies = []
    for _ in range(30):
        t0 = time.perf_counter()
        sess.run(None, {"input": dummy})
        latencies.append((time.perf_counter() - t0) * 1000)
    p50_ms = float(np.percentile(latencies, 50))
    p95_ms = float(np.percentile(latencies, 95))
    logger.info("Doctype v2 FP32 2-thread latency: p50=%.2f ms, p95=%.2f ms", p50_ms, p95_ms)

    # 5. Write metadata sidecars
    for target in [ml_models / "doctype_v2.onnx"]:
        h = hashlib.sha256(target.read_bytes()).hexdigest().lower()
        meta = {
            "model_name": target.name,
            "architecture": "MobileNetV3-Small (FP32)",
            "classes": CLASSES,
            "num_classes": len(CLASSES),
            "input_size": [224, 224],
            "sha256": h,
            "size_bytes": target.stat().st_size,
            "macro_f1": round(macro_f1, 4),
            "p50_latency_ms": round(p50_ms, 2),
            "gate_macro_f1_target": 0.95,
            "gate_pass": macro_f1 >= 0.95,
            "note": "Classes learned only from procedural generator (bhutan_cid) can look perfect on synthetic data and fail on real cards.",
        }
        target.with_name(f"{target.stem}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # 6. Evaluation report in eval/runs/
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    eval_dir = Path(f"eval/runs/{ts}_doctype_v2_eval")
    eval_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp": ts,
        "model": "doctype_v2.onnx",
        "total_val_samples": len(y_true),
        "overall_accuracy": round(overall_acc, 4),
        "macro_f1": round(macro_f1, 4),
        "gate_macro_f1_target": 0.95,
        "gate_pass": macro_f1 >= 0.95,
        "p50_latency_ms": round(p50_ms, 2),
        "p95_latency_ms": round(p95_ms, 2),
        "per_class": per_class_metrics,
        "classes": CLASSES,
        "note": "Classes learned only from our own generator can look perfect on synthetic data and fail on real cards.",
    }
    report_path = eval_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # 7. Write DONE.json marker
    from training.job_markers import write_done_marker
    output_files = [
        str(ml_models / "doctype_v2.onnx"),
    ]
    write_done_marker(
        run_dir=output_dir,
        task_id="task_phase6_doctype",
        output_files=output_files,
        metrics={"overall_acc": overall_acc, "macro_f1": macro_f1, "p50_latency_ms": p50_ms},
        command="python -m training.train_doctype_mobilenet",
    )

    return onnx_dest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, default="data/doctype_v2")
    parser.add_argument("--output-dir", type=str, default="training/runs/doctype_v2")
    parser.add_argument("--epochs", type=int, default=12)
    args = parser.parse_args()
    train_doctype_model(Path(args.data_dir), Path(args.output_dir), epochs=args.epochs)
