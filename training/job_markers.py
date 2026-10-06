"""Helper module for writing DONE.json and FAILED.txt markers for background jobs.
Adheres strictly to Autonomous Work Order v3.1 / Appendix B specifications.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def compute_file_sha256(path: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def write_done_marker(
    run_dir: Path | str,
    task_id: str,
    output_files: Optional[List[Path | str]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    seed: int = 42,
    command: str = "",
) -> Path:
    """Write DONE.json marker into run_dir according to Appendix B schema."""
    target_dir = Path(run_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    file_entries = []
    if output_files:
        for f in output_files:
            fp = Path(f)
            if fp.exists():
                file_entries.append({
                    "path": str(fp).replace("\\", "/"),
                    "bytes": fp.stat().st_size,
                    "sha256": compute_file_sha256(fp),
                })
            else:
                file_entries.append({
                    "path": str(fp).replace("\\", "/"),
                    "bytes": 0,
                    "sha256": "",
                })

    data = {
        "task": task_id,
        "finished_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "output_files": file_entries,
        "metrics": metrics or {},
        "seed": seed,
        "command": command,
    }

    done_file = target_dir / "DONE.json"
    done_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Wrote job success marker: %s", done_file)
    return done_file


def write_failed_marker(
    run_dir: Path | str,
    command: str,
    exit_code: int = 1,
    stderr_lines: Optional[List[str]] = None,
) -> Path:
    """Write FAILED.txt marker into run_dir according to Appendix B schema."""
    target_dir = Path(run_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"COMMAND: {command}",
        f"EXIT CODE: {exit_code}",
        f"TIMESTAMP UTC: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        "--- STDERR (LAST 60 LINES) ---",
    ]
    if stderr_lines:
        lines.extend(stderr_lines[-60:])

    failed_file = target_dir / "FAILED.txt"
    failed_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.error("Wrote job failure marker: %s", failed_file)
    return failed_file
