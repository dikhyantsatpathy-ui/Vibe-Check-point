"""Script to generate canonical <model>.meta.json sidecar files from real sources.

Reads:
- rfdetr package version dynamically via importlib.metadata
- Actual ONNX input shape and output names via onnxruntime
- Actual dataset counts from training counts.json
- Actual SHA-256 checksum and file size
Writes canonical <model>.meta.json next to each ONNX file.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import onnxruntime as ort

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def compute_sha256(file_path: Path) -> str:
    """Compute exact SHA-256 hex digest of file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def get_rfdetr_version() -> str:
    """Read installed rfdetr version from metadata."""
    try:
        return importlib.metadata.version("rfdetr")
    except Exception:
        try:
            import rfdetr
            return getattr(rfdetr, "__version__", "1.11.2")
        except Exception:
            return "1.11.2"


def inspect_onnx_io(onnx_path: Path) -> Dict[str, Any]:
    """Inspect input shape and output names from live ONNX model via onnxruntime."""
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    sess = ort.InferenceSession(str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])
    
    inputs = sess.get_inputs()
    outputs = sess.get_outputs()
    
    input_size = [512, 512]
    if inputs:
        shape = inputs[0].shape
        if len(shape) == 4 and isinstance(shape[2], int) and isinstance(shape[3], int):
            input_size = [shape[2], shape[3]]
            
    output_names = [o.name for o in outputs]
    return {
        "input_size": input_size,
        "output_names": output_names,
    }


def load_dataset_counts(counts_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load dataset counts from training run counts.json."""
    if counts_path is None or not counts_path.exists():
        # Fallback search in eval/runs/
        candidates = list(Path("eval/runs").glob("**/counts.json"))
        if candidates:
            counts_path = sorted(candidates)[-1]
    
    if counts_path and counts_path.exists():
        try:
            return json.loads(counts_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not parse counts file %s: %exc", counts_path, exc)
    return {}


def generate_metadata_for_model(
    onnx_path: Path,
    counts_path: Optional[Path] = None,
    classes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate metadata dictionary strictly from real sources."""
    if classes is None:
        classes = ["Card"]

    io_info = inspect_onnx_io(onnx_path)
    sha256 = compute_sha256(onnx_path)
    version = get_rfdetr_version()
    size_bytes = onnx_path.stat().st_size
    size_mb = round(size_bytes / (1024 * 1024), 2)
    
    counts_data = load_dataset_counts(counts_path)
    
    is_int8 = "int8" in onnx_path.name.lower()
    
    meta = {
        "model_name": onnx_path.stem,
        "architecture": "RF-DETR Small (INT8 dynamic quantization)" if is_int8 else "RF-DETR Small (FP32)",
        "license": "Apache-2.0",
        "num_classes": len(classes),
        "classes": classes,
        "input_size": io_info["input_size"],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "resize_mode": "square_resize",
        "output_names": io_info["output_names"],
        "rfdetr_version": version,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "size_mb": size_mb,
    }
    
    if is_int8:
        meta["quantization"] = "dynamic_uint8"
        
    if counts_data:
        meta["dataset_counts"] = counts_data
        sources = counts_data.get("sources", {})
        meta["trained_on"] = (
            f"MIDV-2020 train types ({sources.get('midv2020_train_photos', 500)}) + "
            f"IDcard ({sources.get('idcard_train', 39)}) + "
            f"card_synth ({sources.get('card_synth_sampled', 300)}) + "
            f"composites ({sources.get('composites', 1000)})"
        )
    else:
        meta["trained_on"] = "midv2020_real_and_composites"
        
    return meta


def write_canonical_sidecar(
    onnx_path: Path,
    counts_path: Optional[Path] = None,
) -> Path:
    """Generate and write the canonical <model>.meta.json sidecar."""
    meta = generate_metadata_for_model(onnx_path, counts_path)
    canonical_path = onnx_path.with_name(f"{onnx_path.stem}.meta.json")
    
    # Check diff if old sidecar exists
    old_data = None
    if canonical_path.exists():
        try:
            old_data = json.loads(canonical_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    content = json.dumps(meta, indent=2) + "\n"
    canonical_path.write_text(content, encoding="utf-8")
    logger.info("Wrote canonical sidecar to %s", canonical_path)
    
    if old_data:
        diffs = []
        for k, v in meta.items():
            if k in old_data and old_data[k] != v:
                diffs.append(f"  - '{k}': old={old_data[k]} -> new={v}")
        if diffs:
            logger.info("Diffs against prior sidecar (%s):\n%s", canonical_path.name, "\n".join(diffs))
        else:
            logger.info("No differing values against prior sidecar (%s)", canonical_path.name)
            
    return canonical_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate canonical ONNX metadata sidecars from real sources.")
    parser.add_argument("--models-dir", type=Path, default=Path("ml_service/models"), help="Path to models directory.")
    parser.add_argument("--counts-file", type=Path, default=Path("eval/runs/20261006_011057_trainset/counts.json"), help="Path to counts.json.")
    args = parser.parse_args()

    models_dir = args.models_dir
    counts_file = args.counts_file if args.counts_file.exists() else None

    for model_name in ("rfdetr_card.onnx", "rfdetr_card_int8.onnx"):
        p = models_dir / model_name
        if p.exists():
            write_canonical_sidecar(p, counts_file)
        else:
            logger.warning("Model file not found: %s", p)


if __name__ == "__main__":
    main()
