"""S1 Secret Hygiene Scanner (Work Order v5).

Scans working tree and git history for credential patterns.
NEVER prints full match values: prints file, line number, first 4 chars + length only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

PATTERNS = {
    "huggingface_token": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "github_token_classic": re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    "github_pat": re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    "openai_sk": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "postgres_conn_uri": re.compile(r"postgres(?:ql)?://[^\s'\"]+:[^\s'\"@]+@"),
    "generic_assigned_secret": re.compile(r"(?i)(password|secret|api[_-]?key|token)\s*[:=]\s*['\"]([^'\"]{8,})['\"]"),
    "credential_prefix_ellipsis": re.compile(r"\b[a-z]{2,8}_[A-Za-z0-9_]{6,}(?:\.{3}|…)"),
    "pcsk_prefix": re.compile(r"pcsk_"),
}

# Ignore false-positive examples or placeholders
PLACEHOLDER_SUBSTRINGS = [
    "example", "placeholder", "your_", "dummy", "test", "fake", "none", "token_here", "<", "xxxx", "os.getenv", "settings.", "process.env"
]


def mask_match(val: str) -> str:
    if len(val) <= 4:
        return "****"
    return f"{val[:4]}...[{len(val)} chars]"


def scan_file_text(path: Path, rel_str: str) -> list[dict]:
    findings = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    for line_no, line in enumerate(content.splitlines(), start=1):
        for name, regex in PATTERNS.items():
            for m in regex.finditer(line):
                val = m.group(0)
                # Filter obvious mock/placeholder tokens
                val_lower = val.lower()
                if any(p in val_lower for p in PLACEHOLDER_SUBSTRINGS):
                    continue
                if name == "generic_assigned_secret":
                    sec_val = m.group(2)
                    sec_lower = sec_val.lower()
                    if any(p in sec_lower for p in PLACEHOLDER_SUBSTRINGS) or len(sec_val) < 8:
                        continue
                findings.append({
                    "type": name,
                    "file": rel_str,
                    "line": line_no,
                    "masked": mask_match(val),
                })
    return findings


TEXT_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".md", ".toml",
    ".sh", ".bat", ".txt", ".env", ".example", ".cfg", ".ini", ".conf", ".sql"
}

def scan_working_tree() -> list[dict]:
    findings = []
    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", "data", "pics", "temp", "tmp", ".agents"}
    for root, dirs, files in os.walk(_ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            p = Path(root) / f
            ext = p.suffix.lower()
            if ext not in TEXT_EXTENSIONS and not f.startswith(".env"):
                continue
            rel = p.relative_to(_ROOT).as_posix()
            findings.extend(scan_file_text(p, rel))
    return findings


def scan_git_history() -> list[dict]:
    findings = []
    print("Scanning git history with git log -G (all branches, top 200 commits)...")
    for name, regex in PATTERNS.items():
        pat_str = regex.pattern
        try:
            res = subprocess.run(
                ["git", "log", "--all", "-n", "200", f"-G{pat_str}", "--pretty=format:COMMIT:%h", "-p"],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if res.returncode == 0 and res.stdout:
                current_commit = "HEAD"
                current_file = "unknown"
                for line in res.stdout.splitlines():
                    if line.startswith("COMMIT:"):
                        current_commit = line.split(":", 1)[1].strip()
                    elif line.startswith("+++ b/"):
                        current_file = line[6:].strip()
                    elif line.startswith("+") and not line.startswith("+++"):
                        added_line = line[1:]
                        for m in regex.finditer(added_line):
                            val = m.group(0)
                            if any(p in val.lower() for p in PLACEHOLDER_SUBSTRINGS):
                                continue
                            if name == "generic_assigned_secret":
                                sec_val = m.group(2)
                                if any(p in sec_val.lower() for p in PLACEHOLDER_SUBSTRINGS) or len(sec_val) < 8:
                                    continue
                            findings.append({
                                "commit": current_commit,
                                "type": name,
                                "file": current_file,
                                "line": 0,
                                "masked": mask_match(val)
                            })
        except Exception as e:
            print(f"Error scanning pattern {name}: {e}")
    return findings


def check_gitignore() -> dict:
    gi_path = _ROOT / ".gitignore"
    if not gi_path.exists():
        return {"exists": False, "missing_patterns": [".env", "data/", "*.onnx", "*.pth", "runs/", "*.log"]}
    txt = gi_path.read_text(encoding="utf-8", errors="replace")
    required = [".env", "data/", "*.onnx", "*.pth", "runs/", "*.log"]
    missing = []
    for r in required:
        if r not in txt:
            missing.append(r)
    return {
        "exists": True,
        "missing_patterns": missing,
        "has_env_example_exception": "!*.env.example" in txt or ".env.example" in txt
    }


def main():
    out_dir = _ROOT / "eval" / "runs" / "20261007_064553_env"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / "secrets_audit.json"

    print("--- Scanning working tree for secrets ---")
    wt_findings = scan_working_tree()
    print(f"Working tree findings: {len(wt_findings)}")

    print("--- Scanning git history (up to 200 commits) ---")
    gh_findings = scan_git_history()
    print(f"Git history findings: {len(gh_findings)}")

    gi_status = check_gitignore()
    print(f".gitignore status: {gi_status}")

    report = {
        "working_tree_findings": wt_findings,
        "git_history_findings": gh_findings,
        "gitignore_status": gi_status
    }
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written to {report_file}")


if __name__ == "__main__":
    main()
