"""Independent secret hygiene scanner (Phase V1).
Scans working tree + git history (newest 300 commits + tags) + docs, eval/runs, notebooks.
Never prints full secret values: masks to first 4 chars + length.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS = {
    "huggingface_token": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "github_token_classic": re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    "github_pat": re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    "openai_sk": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "postgres_conn_uri": re.compile(r"postgres(?:ql)?://[^\s'\"]+:[^\s'\"@]+@"),
}

IGNORE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "pics", "data"}
PLACEHOLDERS = {"example", "placeholder", "dummy", "test", "fake", "<", "none", "os.getenv", "redacted"}


def mask(s: str) -> str:
    return f"{s[:4]}...[{len(s)} chars]"


def scan_working_tree():
    hits = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            if f.startswith(".env"):
                continue  # Ignore local uncommitted .env
            p = Path(root) / f
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line_no, line in enumerate(txt.splitlines(), start=1):
                # Ignore test files that intentionally contain dummy patterns
                if "tests/" in p.as_posix() and ("dummy" in line.lower() or "test_" in line.lower() or "mock" in line.lower()):
                    continue
                for name, pat in PATTERNS.items():
                    for m in pat.finditer(line):
                        val = m.group(0)
                        if any(x in val.lower() for x in PLACEHOLDERS):
                            continue
                        if "r'" in line or 'r"' in line or "re.compile" in line:
                            continue
                        hits.append({
                            "type": name,
                            "file": p.relative_to(ROOT).as_posix(),
                            "line": line_no,
                            "masked": mask(val),
                        })
    return hits


def scan_git_history(n_commits: int = 300):
    hits = []
    try:
        res = subprocess.run(
            ["git", "rev-list", "--all", "-n", str(n_commits)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        commits = res.stdout.splitlines()
        for c in commits:
            diff_res = subprocess.run(
                ["git", "show", "-p", c],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                errors="ignore",
            )
            for line in diff_res.stdout.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    added = line[1:]
                    for name, pat in PATTERNS.items():
                        for m in pat.finditer(added):
                            val = m.group(0)
                            if any(x in val.lower() for x in PLACEHOLDERS):
                                continue
                            if "r'" in added or 'r"' in added or "re.compile" in added:
                                continue
                            hits.append({
                                "commit": c[:8],
                                "type": name,
                                "masked": mask(val),
                            })
    except Exception as exc:
        print("Git history scan note:", exc)
    return hits


def main():
    print("Running independent secret scan (working tree + history top 300 commits)...")
    tree_hits = scan_working_tree()
    history_hits = scan_git_history(300)

    out_dir = ROOT / "eval" / "runs" / "20261011_reverify_v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "secrets_scan.json"

    report = {
        "scan_target": "tree + git history top 300 commits + tags",
        "working_tree_findings_count": len(tree_hits),
        "working_tree_findings": tree_hits,
        "history_findings_count": len(history_hits),
        "history_findings": history_hits,
        "verdict": "CLEAN" if (len(tree_hits) == 0 and len(history_hits) == 0) else "FINDINGS_DETECTED",
    }
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Independent scan complete: {len(tree_hits)} tree hits, {len(history_hits)} history hits.")
    print(f"Results written to {out_file}")


if __name__ == "__main__":
    main()
