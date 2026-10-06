#!/usr/bin/env python3
"""
scripts/check_repo_hygiene.py — Repository hygiene enforcement for NO-CAP (SIH26188)

Fails if:
  1. Any tracked file exceeds 500 KB (unless in the explicit legacy baseline allowlist).
  2. Any tracked file has forbidden model/image/dataset extensions (.jpg, .png, .webp,
     .tif, .onnx, .pt, .pth, .parquet, .tar, .zip, etc., outside the baseline allowlist).
  3. Any files under data/, training/runs/, or specimen photos are tracked.
"""

import os
import subprocess
import sys
from pathlib import Path

MAX_FILE_SIZE_BYTES = 500 * 1024  # 500 KB

FORBIDDEN_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff",
    ".onnx", ".pt", ".pth", ".bin", ".safetensors",
    ".parquet", ".tar", ".gz", ".zip", ".bz2", ".7z"
}

# The only pre-existing models on main prior to the RF-DETR refactor
LEGACY_BASELINE_ALLOWLIST = {
    "app/models/doctype.onnx",
    "ml_service/models/card.onnx",
    "ml_service/models/aadhaar_fields.onnx",
}


def get_tracked_files():
    """Retrieve all files tracked by git in the current working tree."""
    try:
        res = subprocess.check_output(["git", "ls-tree", "-r", "HEAD"], stderr=subprocess.PIPE)
        lines = res.decode("utf-8").splitlines()
        tracked = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                sha = parts[2]
                path = " ".join(parts[3:])
                tracked.append((path, sha))
        return tracked
    except Exception as e:
        print(f"[HYGIENE ERROR] Failed to run git ls-tree: {e}", file=sys.stderr)
        sys.exit(1)


def check_hygiene():
    tracked = get_tracked_files()
    violations = []

    for path, sha in tracked:
        norm_path = path.replace("\\", "/")
        p = Path(norm_path)
        ext = p.suffix.lower()

        # Check legacy allowlist
        if norm_path in LEGACY_BASELINE_ALLOWLIST:
            continue

        # Check forbidden extensions
        if ext in FORBIDDEN_EXTENSIONS:
            violations.append(f"Forbidden extension '{ext}': {norm_path}")

        # Check forbidden directories
        if norm_path.startswith("data/") or norm_path.startswith("training/runs/") or "specimen_photos" in norm_path:
            violations.append(f"Forbidden directory tracking: {norm_path}")

        # Check file size in git object store
        try:
            sz_str = subprocess.check_output(["git", "cat-file", "-s", sha], stderr=subprocess.PIPE).decode("utf-8").strip()
            sz = int(sz_str)
            if sz > MAX_FILE_SIZE_BYTES:
                violations.append(f"File size {sz / 1024:.1f} KB exceeds 500 KB limit: {norm_path}")
        except Exception:
            pass

    return violations


def main():
    print("Running repository hygiene check...")
    violations = check_hygiene()
    if violations:
        print(f"\n[FAIL] Found {len(violations)} hygiene violation(s):", file=sys.stderr)
        for v in violations:
            print(f"  • {v}", file=sys.stderr)
        sys.exit(1)
    else:
        print("[PASS] Repository hygiene verified: zero unauthorized large files, images, or weight binaries tracked.")
        sys.exit(0)


if __name__ == "__main__":
    main()
