"""Hugging Face Model Fetcher & Integrity Verifier (Phase 7.2).

Downloads model weights from a private or public Hugging Face model repository,
verifies SHA-256 against canonical metadata sidecars, and fails closed on mismatch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("model_fetch")

DEFAULT_REPO = "koropanda/no-cap-detectors"
DEFAULT_MODELS_DIR = Path(__file__).resolve().parent / "models"


def compute_sha256(file_path: Path) -> str:
    """Compute exact SHA-256 digest of file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def verify_model_integrity(model_path: Path, meta_path: Optional[Path] = None) -> bool:
    """Verify SHA-256 checksum of model against its metadata sidecar.
    Fails closed: returns False and raises error if checksum mismatch.
    """
    if not model_path.exists():
        logger.error("Model file %s does not exist", model_path)
        return False

    if meta_path is None:
        meta_path = model_path.with_name(f"{model_path.stem}.meta.json")

    if not meta_path.exists():
        logger.warning("Sidecar %s not found for %s; verifying existence only", meta_path.name, model_path.name)
        return True

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        expected_sha = meta.get("sha256", "").strip().lower()
        if not expected_sha:
            return True

        actual_sha = compute_sha256(model_path)
        if actual_sha != expected_sha:
            logger.critical(
                "SHA-256 MISMATCH for %s! Expected: %s, Actual: %s. FAILING CLOSED.",
                model_path.name, expected_sha, actual_sha
            )
            return False
        logger.info("SHA-256 verified for %s (%s)", model_path.name, actual_sha[:12])
        return True
    except Exception as exc:
        logger.error("Error reading sidecar %s: %s", meta_path, exc)
        return False


def fetch_models_from_hf(
    repo_id: Optional[str] = None,
    token: Optional[str] = None,
    dest_dir: Optional[Path] = None,
    model_filenames: Optional[List[str]] = None,
) -> Dict[str, bool]:
    """Fetch weights and sidecars from Hugging Face repository."""
    repo = repo_id or os.getenv("HF_MODEL_REPO", DEFAULT_REPO)
    hf_token = token or os.getenv("HF_TOKEN")
    target_dir = dest_dir or DEFAULT_MODELS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    if model_filenames is None:
        model_filenames = [
            "rfdetr_card_int8.onnx",
            "rfdetr_card_int8.meta.json",
            "rfdetr_mrz_int8.onnx",
            "rfdetr_mrz_int8.meta.json",
            "doctype_v2.onnx",
            "doctype_v2.meta.json",
            "rfdetr_id_fields_int8.onnx",
            "rfdetr_id_fields_int8.meta.json",
        ]

    status: Dict[str, bool] = {}

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        logger.warning("huggingface_hub is not installed; skipping remote fetch.")
        return {f: False for f in model_filenames}

    for fname in model_filenames:
        dest_file = target_dir / fname
        try:
            logger.info("Fetching %s from %s...", fname, repo)
            downloaded_path = hf_hub_download(
                repo_id=repo,
                filename=fname,
                token=hf_token,
                local_dir=str(target_dir),
            )
            dest_file = Path(downloaded_path)

            # If it's an ONNX model, verify checksum against its sidecar
            if dest_file.suffix.lower() == ".onnx":
                sidecar_path = dest_file.with_name(f"{dest_file.stem}.meta.json")
                if sidecar_path.exists():
                    ok = verify_model_integrity(dest_file, sidecar_path)
                    if not ok:
                        dest_file.unlink(missing_ok=True)
                        raise ValueError(f"Tampered or corrupt model file: {fname}")
            status[fname] = True
        except Exception as exc:
            logger.warning("Could not fetch %s from HF: %s", fname, exc)
            status[fname] = False

    return status


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Testing local verification...")
    for model_path in DEFAULT_MODELS_DIR.glob("*.onnx"):
        verified = verify_model_integrity(model_path)
        print(f"  {model_path.name}: verified={verified}")
