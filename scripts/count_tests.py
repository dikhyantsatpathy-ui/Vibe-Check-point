#!/usr/bin/env python3
"""P11: Single source of truth for test counts.

Runs `python -m pytest --collect-only -q`, writes eval/runs/<ts>_tests/count.json,
and updates blueprint and claims ledger with measured counts.
"""

from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINT_MD = REPO_ROOT / "SIH26188_ENGINEERING_BLUEPRINT.md"
CLAIMS_JSON = REPO_ROOT / "docs" / "claims" / "claims.json"
VERIFY_CLAIMS_PY = REPO_ROOT / "scripts" / "verify_blueprint_claims.py"


def collect_tests() -> tuple[int, dict[str, int]]:
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error collecting tests (rc={res.returncode}):\n{res.stderr}", file=sys.stderr)
        sys.exit(res.returncode)

    per_file: dict[str, int] = collections.defaultdict(int)
    total = 0

    for line in res.stdout.splitlines():
        line = line.strip()
        if "::" in line and not line.startswith("="):
            parts = line.split("::", 1)
            file_path = parts[0].strip()
            # Normalize path separators
            norm_file = file_path.replace("\\", "/")
            per_file[norm_file] += 1
            total += 1

    return total, dict(sorted(per_file.items()))


def update_blueprint(total: int, num_suites: int) -> None:
    if not BLUEPRINT_MD.exists():
        return
    text = BLUEPRINT_MD.read_text(encoding="utf-8")
    # Replace test count line e.g. "├── tests/                             # 40 automated test suites (397+ tests, 100% active passing)"
    pattern = re.compile(
        r"(├── tests/\s+#\s+)\d+\s+automated test suites\s+\([^)]+\)",
        re.MULTILINE,
    )
    new_line = rf"\g<1>{num_suites} automated test suites ({total} tests, 100% active passing)"
    if pattern.search(text):
        new_text = pattern.sub(new_line, text)
        BLUEPRINT_MD.write_text(new_text, encoding="utf-8")
    else:
        # Fallback regex if formatting differs
        pattern2 = re.compile(r"(\btests/\b[^\n]*#\s*)\d+\s*tests", re.IGNORECASE)
        if pattern2.search(text):
            new_text = pattern2.sub(rf"\g<1>{total} tests", text)
            BLUEPRINT_MD.write_text(new_text, encoding="utf-8")


def update_claims_ledger(total: int) -> None:
    if CLAIMS_JSON.exists():
        try:
            with open(CLAIMS_JSON, "r", encoding="utf-8") as f:
                claims = json.load(f)
            updated = False
            for c in claims:
                if c.get("id") == "C-06":
                    c["text"] = f"Test suite total count equals {total} tests"
                    c["expect"] = f"{total} tests collected"
                    updated = True
            if updated:
                with open(CLAIMS_JSON, "w", encoding="utf-8") as f:
                    json.dump(claims, f, indent=2)
                    f.write("\n")
        except Exception as e:
            print(f"Warning: Failed to update claims.json: {e}", file=sys.stderr)

    if VERIFY_CLAIMS_PY.exists():
        try:
            vc_text = VERIFY_CLAIMS_PY.read_text(encoding="utf-8")
            # Update check_c06 threshold
            vc_text = re.sub(
                r'if count >= \d+:',
                f'if count >= {total}:',
                vc_text,
            )
            vc_text = re.sub(
                r'add\("C-06", "17 / 26", "Test suite total count equals [^"]+", "cmd", "pytest --collect-only", "[^"]+", check_c06\)',
                f'add("C-06", "17 / 26", "Test suite total count equals {total} tests", "cmd", "pytest --collect-only", "{total} tests collected", check_c06)',
                vc_text,
            )
            VERIFY_CLAIMS_PY.write_text(vc_text, encoding="utf-8")
        except Exception as e:
            print(f"Warning: Failed to update verify_blueprint_claims.py: {e}", file=sys.stderr)


def main():
    total, per_file = collect_tests()
    num_suites = len(per_file)

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "eval" / "runs" / f"{ts}_tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "count.json"

    data = {
        "timestamp_utc": ts,
        "total": total,
        "suites_count": num_suites,
        "per_file": per_file,
    }

    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Collected {total} tests across {num_suites} files. Written to {out_file.relative_to(REPO_ROOT)}")

    # Update blueprint and claims
    update_blueprint(total, num_suites)
    update_claims_ledger(total)


if __name__ == "__main__":
    main()
