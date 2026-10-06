"""Hugging Face Model Fetcher & Integrity Verifier (Phase E2).

Downloads model weights from a private or public Hugging Face model repository,
verifies SHA-256 against canonical metadata sidecars, supports atomic writing,
exponential backoff retry, and works offline when cached models are valid.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("model_fetch")

DEFAULT_REPO = "koropanda/no-cap-detectors"
DEFAULT_MODELS_DIR = Path(__file__).resolve().parent / "models"


def compute_sha256(file_path: Path) -> str:
    """Compute exact hex-digest SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def verify_model_integrity(model_path: Path, meta_path: Optional[Path] = None) -> bool:
    """Verify SHA-256 checksum of model against its metadata sidecar.
    Fails closed: returns False and logs critical error on checksum mismatch.
    """
    if not model_path.exists():
        logger.error("Model file %s does not exist", model_path)
        return False

    if meta_path is None:
        meta_path = model_path.with_name(f"{model_path.name}.meta.json")
        if not meta_path.exists():
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
    revision: Optional[str] = None,
    token: Optional[str] = None,
    dest_dir: Optional[Path] = None,
    model_filenames: Optional[List[str]] = None,
    max_retries: int = 3,
) -> Dict[str, bool]:
    """Fetch weights and sidecars from Hugging Face with backoff retry and cache support."""
    repo = repo_id or os.getenv("HF_MODEL_REPO", DEFAULT_REPO)
    rev = revision or os.getenv("HF_MODEL_REVISION")
    hf_token = token or os.getenv("HF_TOKEN")
    target_dir = dest_dir or Path(os.getenv("MODEL_CACHE_DIR", str(DEFAULT_MODELS_DIR)))
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
        logger.warning("huggingface_hub is not installed; verifying local cache only.")
        for fname in model_filenames:
            dest_file = target_dir / fname
            if dest_file.exists():
                status[fname] = True if dest_file.suffix != ".onnx" else verify_model_integrity(dest_file)
            else:
                status[fname] = False
        return status

    for fname in model_filenames:
        dest_file = target_dir / fname
        
        # If model is already cached locally, verify integrity first
        if dest_file.exists():
            if dest_file.suffix.lower() == ".onnx":
                if verify_model_integrity(dest_file):
                    logger.info("Using cached model %s (integrity verified)", fname)
                    status[fname] = True
                    continue
            else:
                logger.info("Using cached file %s", fname)
                status[fname] = True
                continue

        # Download with exponential backoff
        success = False
        for attempt in range(1, max_retries + 1):
            try:
                logger.info("Fetching %s from %s (attempt %d/%d)...", fname, repo, attempt, max_retries)
                hf_hub_download(
                    repo_id=repo,
                    filename=fname,
                    revision=rev,
                    token=hf_token,
                    local_dir=str(target_dir),
                )
                if dest_file.suffix.lower() == ".onnx":
                    sidecar_cand = dest_file.with_name(f"{dest_file.name}.meta.json")
                    if not sidecar_cand.exists():
                        sidecar_cand = dest_file.with_name(f"{dest_file.stem}.meta.json")
                    if sidecar_cand.exists():
                        if not verify_model_integrity(dest_file, sidecar_cand):
                            dest_file.unlink(missing_ok=True)
                            raise ValueError(f"Integrity check failed for {fname}")
                success = True
                break
            except Exception as exc:
                err_msg = str(exc)
                if "401" in err_msg or "403" in err_msg or "Unauthorized" in err_msg:
                    logger.critical("Hugging Face AUTHENTICATION FAILED for repo %s: Check HF_TOKEN.", repo)
                    break
                logger.warning("Download error on %s attempt %d: %s", fname, attempt, exc)
                if attempt < max_retries:
                    time.sleep(2.0 ** attempt)

        # If download failed, check if offline fallback exists
        if not success and dest_file.exists():
            logger.warning("Download failed but found local cache for %s. Operating in offline mode.", fname)
            success = verify_model_integrity(dest_file) if dest_file.suffix == ".onnx" else True

        status[fname] = success

    return status
