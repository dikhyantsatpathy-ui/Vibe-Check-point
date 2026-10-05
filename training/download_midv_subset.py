"""Helper script to download MIDV-2020 and MIDV-500 subsets with resume and timeout handling.

Target archives:
- MIDV-2020: photo.tar (~12-15 GB uncompressed, contains photos for 10 document types)
- Optional: templates.tar
"""

from __future__ import annotations

import argparse
import logging
import ssl
import sys
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# Primary targets for evaluation and training
DEFAULT_TARGETS = {
    "midv2020_photo": {
        "filename": "photo.tar",
        "description": "MIDV-2020 smartphone photos (10 document types, 100 documents each)",
        "mirrors": [
            "https://l3i-share.univ-lr.fr/MIDV2020/photo.tar",
            "ftp://smartengines.com/midv-2020/dataset/photo.tar",
        ],
    },
    "midv500_clips": {
        "filename": "midv500_sample.tar",
        "description": "MIDV-500 video clip frames",
        "mirrors": [
            "ftp://smartengines.com/midv-500/dataset/",
        ],
    },
}


def download_file_with_resume(
    url: str,
    dest_path: Path,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
    max_retries: int = 5,
) -> bool:
    """Download a file with HTTP Range resume support and retry loop."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    ctx = ssl._create_unverified_context()
    existing_bytes = temp_path.stat().st_size if temp_path.exists() else 0

    headers = {"User-Agent": "NO-CAP-DatasetDownloader/1.0"}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"
        logger.info("Resuming download from byte %d", existing_bytes)

    req = urllib.request.Request(url, headers=headers)

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Connecting to %s (attempt %d/%d)...", url, attempt, max_retries)
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
                total_size = response.headers.get("Content-Length")
                total_bytes = int(total_size) + existing_bytes if total_size else None

                mode = "ab" if existing_bytes > 0 else "wb"
                with open(temp_path, mode) as out_f:
                    downloaded = existing_bytes
                    start_t = time.time()
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = max(1e-3, time.time() - start_t)
                        speed_mb = (downloaded - existing_bytes) / (1024 * 1024 * elapsed)
                        if total_bytes:
                            pct = (downloaded / total_bytes) * 100
                            print(f"\rDownloaded {downloaded / 1e6:.1f}/{total_bytes / 1e6:.1f} MB ({pct:.1f}%) @ {speed_mb:.2f} MB/s", end="", flush=True)
                        else:
                            print(f"\rDownloaded {downloaded / 1e6:.1f} MB @ {speed_mb:.2f} MB/s", end="", flush=True)

                print()
                temp_path.rename(dest_path)
                logger.info("Successfully downloaded %s to %s", url, dest_path)
                return True
        except Exception as exc:
            logger.warning("Attempt %d failed: %s", attempt, exc)
            time.sleep(attempt * 2)

    return False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Download MIDV subset helper")
    parser.add_argument("--target", choices=list(DEFAULT_TARGETS.keys()), default="midv2020_photo")
    parser.add_argument("--out-dir", type=str, default="data/downloads")
    args = parser.parse_args()

    info = DEFAULT_TARGETS[args.target]
    out_file = Path(args.out_dir) / info["filename"]
    print(f"Target: {args.target} ({info['description']})")
    print(f"Output: {out_file}")
    print("Available mirrors:")
    for m in info["mirrors"]:
        print(f" - {m}")


if __name__ == "__main__":
    main()
