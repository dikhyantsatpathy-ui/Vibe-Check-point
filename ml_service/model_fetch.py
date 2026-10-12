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
MANIFEST_PATH = DEFAULT_MODELS_DIR / "MODEL_MANIFEST.json"


def load_manifest(manifest_path: Optional[Path] = None) -> Dict[str, dict]:
    """Load model manifest with sha256, size, and source metadata."""
    p = manifest_path or MANIFEST_PATH
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "models" in data and isinstance(data["models"], dict):
            return data["models"]
        if "models" in data and isinstance(data["models"], list):
            return {m["name"]: m for m in data["models"] if "name" in m}
        if isinstance(data, list):
            return {m["name"]: m for m in data if "name" in m}
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.error("Failed to load model manifest %s: %s", p, exc)
    return {}


def get_manifest_entry(name: str, manifest_path: Optional[Path] = None) -> Optional[dict]:
    """Get metadata for a specific model from manifest."""
    manifest = load_manifest(manifest_path)
    return manifest.get(name)


def compute_sha256(file_path: Path | str) -> str:
    """Compute exact hex-digest SHA-256 checksum of a file."""
    p = Path(file_path)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def verify_model_integrity(
    model_path: Path | str,
    meta_path: Optional[Path] = None,
    expected_sha: Optional[str] = None,
) -> bool:
    """Verify SHA-256 checksum of model against expected SHA, sidecar, or manifest.
    Fails closed: returns False and logs error on missing/empty SHA or checksum mismatch.
    """
    p = Path(model_path)
    if not p.exists():
        logger.error("Model file %s does not exist", p)
        return False

    sha_to_check = (expected_sha or "").strip().lower()

    if not sha_to_check:
        if meta_path is None:
            meta_path = p.with_name(f"{p.name}.meta.json")
            if not meta_path.exists():
                meta_path = p.with_name(f"{p.stem}.meta.json")

        if meta_path and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                sha_to_check = (meta.get("sha256") or "").strip().lower()
            except Exception as exc:
                logger.error("Error reading sidecar %s: %s", meta_path, exc)
                return False

    if not sha_to_check:
        entry = get_manifest_entry(p.name)
        if entry and entry.get("sha256"):
            sha_to_check = entry["sha256"].strip().lower()

    if not sha_to_check:
        logger.error("Empty or missing SHA-256 for %s! Refusing to load.", p.name)
        return False

    try:
        actual_sha = compute_sha256(p)
        if actual_sha != sha_to_check:
            logger.critical(
                "SHA-256 MISMATCH for %s! Expected: %s, Actual: %s. FAILING CLOSED.",
                p.name, sha_to_check, actual_sha
            )
            return False
        logger.info("SHA-256 verified for %s (%s)", p.name, actual_sha[:12])
        return True
    except Exception as exc:
        logger.error("Error computing checksum for %s: %s", p.name, exc)
        return False


def fetch_models_from_hf(
    repo_id: Optional[str] = None,
    revision: Optional[str] = None,
    token: Optional[str] = None,
    dest_dir: Optional[Path] = None,
    model_filenames: Optional[List[str]] = None,
    max_retries: int = 3,
    timeout: float = 30.0,
) -> Dict[str, bool]:
    """Fetch weights and sidecars from Hugging Face with backoff retry, timeout, size cap, and cache support."""
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
        entry = get_manifest_entry(fname)

        # If model is already cached locally, verify integrity first
        if dest_file.exists():
            if dest_file.suffix.lower() == ".onnx":
                sidecar_cand = dest_file.with_name(f"{dest_file.name}.meta.json")
                if not sidecar_cand.exists():
                    sidecar_cand = dest_file.with_name(f"{dest_file.stem}.meta.json")
                if verify_model_integrity(dest_file, meta_path=sidecar_cand if sidecar_cand.exists() else None):
                    logger.info("Using cached model %s (integrity verified)", fname)
                    status[fname] = True
                    continue
                else:
                    logger.warning("Cached model %s failed integrity check; refetching", fname)
                    dest_file.unlink(missing_ok=True)
            else:
                logger.info("Using cached file %s", fname)
                status[fname] = True
                continue

        # Download with exponential backoff
        success = False
        for attempt in range(1, max_retries + 1):
            try:
                logger.info("Fetching %s from %s (attempt %d/%d)...", fname, repo, attempt, max_retries)
                dl_kwargs = {
                    "repo_id": repo,
                    "filename": fname,
                    "token": hf_token,
                    "local_dir": str(target_dir),
                }
                if rev:
                    dl_kwargs["revision"] = rev
                try:
                    hf_hub_download(**dl_kwargs, etag_timeout=min(10.0, timeout))
                except TypeError:
                    # Fallback if mock or older huggingface_hub doesn't take etag_timeout
                    hf_hub_download(**dl_kwargs)

                # Check size cap: 1.05 x manifest bytes
                if entry and "bytes" in entry and entry["bytes"]:
                    max_allowed = int(entry["bytes"] * 1.05)
                    actual_size = dest_file.stat().st_size
                    if actual_size > max_allowed:
                        dest_file.unlink(missing_ok=True)
                        logger.error(
                            "Oversize model %s: %d bytes exceeds 1.05x cap (%d bytes)",
                            fname, actual_size, max_allowed
                        )
                        raise ValueError(f"Oversize model {fname}: {actual_size} exceeds 1.05x cap {max_allowed}")

                if dest_file.suffix.lower() == ".onnx":
                    sidecar_cand = dest_file.with_name(f"{dest_file.name}.meta.json")
                    if not sidecar_cand.exists():
                        sidecar_cand = dest_file.with_name(f"{dest_file.stem}.meta.json")
                    if not verify_model_integrity(dest_file, meta_path=sidecar_cand if sidecar_cand.exists() else None):
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
            sidecar_cand = dest_file.with_name(f"{dest_file.name}.meta.json")
            if not sidecar_cand.exists():
                sidecar_cand = dest_file.with_name(f"{dest_file.stem}.meta.json")
            success = verify_model_integrity(dest_file, meta_path=sidecar_cand if sidecar_cand.exists() else None) if dest_file.suffix == ".onnx" else True

        status[fname] = success

    return status
