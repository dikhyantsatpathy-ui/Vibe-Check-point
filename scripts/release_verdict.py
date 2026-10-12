#!/usr/bin/env python
"""Release Verdict Validator (Task A2).

Computes the final GO / NO-GO deployment verdict from project gates:
Inputs:
1. docs/QUEUE.json
2. newest eval/runs/*_claims/report.json
3. findings table in newest docs/AUDIT_V*.md
4. docs/readiness_rows.json results
5. newest eval/runs/*_suite/result.json
6. newest eval/runs/*_tests/count.json (optional summary)

Rules:
- GO only if:
  * no FALSE claim
  * no OPEN S1/S2 audit findings
  * no readiness row FAIL
  * no BLOCKED task in phases P, T, or K (unless flagged as owner)
  * suite green three times (runs >= 3, failed == 0)
- Otherwise: NO-GO with exact reasons.
- Invariant: The words "ready" or "release" appear in the report ONLY next to a GO verdict.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def evaluate_release_verdict(
    queue_data: dict[str, Any],
    claims_data: dict[str, Any] | list[Any] | None,
    audit_rows: list[dict[str, Any]],
    readiness_data: list[dict[str, Any]],
    suite_data: dict[str, Any] | None,
    test_counts_data: dict[str, Any] | None = None,
) -> tuple[str, list[str], str]:
    """Evaluate GO / NO-GO verdict based on quality gates.
    
    Returns (verdict, reasons, report_text).
    """
    reasons: list[str] = []

    # 1. Claims gate: No FALSE claims
    if claims_data is None:
        reasons.append("Missing claims verification artifact")
    else:
        claims_list = claims_data.get("claims", []) if isinstance(claims_data, dict) else claims_data
        false_claims: list[str] = []
        for c in claims_list:
            if not isinstance(c, dict):
                continue
            status_val = str(c.get("status", "")).upper()
            verified_val = c.get("verified")
            if status_val == "FALSE" or verified_val is False:
                cid = str(c.get("claim_id") or c.get("id") or "unnamed_claim")
                false_claims.append(cid)
        if false_claims:
            reasons.append(f"FALSE claims detected: {', '.join(false_claims)}")

    # 2. Audit findings gate: No OPEN S1 or S2 findings
    open_s1_s2: list[str] = []
    for row in audit_rows:
        sev = str(row.get("severity", "")).upper()
        stat = str(row.get("status", "")).upper()
        if sev in ("S1", "S2") and stat in ("OPEN", "ACTION REQUIRED"):
            fid = str(row.get("id") or "unnamed_finding")
            open_s1_s2.append(f"{fid} ({sev})")
    if open_s1_s2:
        reasons.append(f"OPEN S1/S2 audit findings: {', '.join(open_s1_s2)}")

    # 3. Readiness gate: No FAIL rows
    readiness_fails: list[str] = []
    for r in readiness_data:
        verd = str(r.get("verdict", "")).upper()
        if "FAIL" in verd:
            readiness_fails.append(str(r.get("name") or "unnamed_row"))
    if readiness_fails:
        reasons.append(f"Readiness row FAIL detected: {', '.join(readiness_fails)}")

    # 4. Queue gate: No BLOCKED tasks in P, T, or K unless owner flagged
    blocked_ptk: list[str] = []
    for task in queue_data.get("tasks", []):
        t_id = str(task.get("id", ""))
        t_phase = str(task.get("phase", ""))
        t_status = str(task.get("status", "")).upper()

        if t_status == "BLOCKED" and t_phase in ("P", "T", "K"):
            is_owner = (
                task.get("owner") is True
                or "owner" in task.get("title", "").lower()
                or "owner" in str(task.get("flags", "")).lower()
                or "owner" in str(task.get("reason", "")).lower()
            )
            if not is_owner:
                blocked_ptk.append(f"{t_id} (Phase {t_phase})")
    if blocked_ptk:
        reasons.append(f"BLOCKED non-owner tasks in P/T/K: {', '.join(blocked_ptk)}")

    # 5. Suite stability gate: 3 consecutive green runs
    if suite_data is None:
        reasons.append("Missing test suite stability artifact")
    else:
        runs_val = suite_data.get("runs", 0)
        runs_count = len(runs_val) if isinstance(runs_val, list) else int(runs_val)
        failed_count = int(suite_data.get("failed", 0))

        if runs_count < 3 or failed_count > 0:
            reasons.append(
                f"Test suite not green 3 consecutive times: runs={runs_count} (min 3), failed={failed_count} (max 0)"
            )

    # Invariant: The words "ready" or "release" appear in the report ONLY next to a GO verdict.
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if reasons:
        verdict = "NO-GO"
        lines = [
            "==================================================",
            "DEPLOYMENT GATE ASSESSMENT",
            "==================================================",
            f"Timestamp: {timestamp}",
            f"Verdict: {verdict}",
            "--------------------------------------------------",
            f"GATES FAILED: {len(reasons)} blocker(s) found:",
        ]
        for r in reasons:
            lines.append(f"  * {r}")
        lines.append("--------------------------------------------------")
        report_text = "\n".join(lines)

        # Enforce invariant
        lower_report = report_text.lower()
        if "ready" in lower_report or "release" in lower_report:
            raise RuntimeError("Invariant violation: NO-GO report contains forbidden words 'ready'/'release'")
    else:
        verdict = "GO"
        lines = [
            "==================================================",
            "DEPLOYMENT GATE ASSESSMENT",
            "==================================================",
            f"Timestamp: {timestamp}",
            f"Verdict: {verdict}",
            "STATUS: RELEASE READY",
            "--------------------------------------------------",
            "All deployment quality gates satisfied:",
            "  * Claims verified: 100% true",
            "  * Audit findings: zero open S1/S2",
            "  * Switch readiness: zero failed indicators",
            "  * Work queue: zero blocking P/T/K items",
            "  * Suite stability: green across 3 consecutive iterations",
            "--------------------------------------------------",
        ]
        if test_counts_data:
            lines.append(f"Verified test count: {test_counts_data.get('total', 'unknown')}")
        report_text = "\n".join(lines)

    return verdict, reasons, report_text


def parse_audit_findings(audit_path: pathlib.Path) -> list[dict[str, Any]]:
    """Parse findings table from markdown audit file."""
    if not audit_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    text = audit_path.read_text(encoding="utf-8")

    # Match rows like: | F-001 | S3 | ML Backend | ... | OPEN | ... |
    # or: | C-01 | S2 | claims/... | ... | RESOLVED | ... |
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line or "Severity" in line:
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 5:
            f_id = parts[0]
            f_sev = parts[1]
            f_status = parts[4]
            if re.match(r"^[A-Z0-9_\-]+$", f_id) and re.match(r"^S[1-4]$", f_sev):
                rows.append({
                    "id": f_id,
                    "severity": f_sev,
                    "status": f_status,
                })

    return rows


def find_newest_file(dir_path: pathlib.Path, pattern: str) -> pathlib.Path | None:
    """Find the newest file matching glob pattern in directory."""
    if not dir_path.exists():
        return None
    files = list(dir_path.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(description="Evaluate release verdict")
    parser.add_argument("--write", type=pathlib.Path, help="Path to write verdict report file")
    args = parser.parse_args()

    # Load queue
    queue_file = REPO_ROOT / "docs" / "QUEUE.json"
    queue_data = json.loads(queue_file.read_text(encoding="utf-8")) if queue_file.exists() else {}

    # Load newest claims report
    claims_file = find_newest_file(REPO_ROOT / "eval" / "runs", "*_claims/report.json")
    claims_data = json.loads(claims_file.read_text(encoding="utf-8")) if claims_file else None

    # Load newest audit findings
    audit_files = sorted(list((REPO_ROOT / "docs").glob("AUDIT_V*.md")), reverse=True)
    audit_rows: list[dict[str, Any]] = []
    for af in audit_files:
        rows = parse_audit_findings(af)
        if rows:
            audit_rows = rows
            break

    # Load readiness rows
    readiness_file = REPO_ROOT / "docs" / "readiness_rows.json"
    readiness_data = json.loads(readiness_file.read_text(encoding="utf-8")) if readiness_file.exists() else []

    # Load suite result
    suite_file = find_newest_file(REPO_ROOT / "eval" / "runs", "*_suite/result.json")
    suite_data = json.loads(suite_file.read_text(encoding="utf-8")) if suite_file else None

    # Load test count
    count_file = find_newest_file(REPO_ROOT / "eval" / "runs", "*_tests/count.json")
    test_counts = json.loads(count_file.read_text(encoding="utf-8")) if count_file else None

    verdict, reasons, report = evaluate_release_verdict(
        queue_data=queue_data,
        claims_data=claims_data,
        audit_rows=audit_rows,
        readiness_data=readiness_data,
        suite_data=suite_data,
        test_counts_data=test_counts,
    )

    print(report)

    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(report, encoding="utf-8")
        print(f"Report written to: {args.write}")

    sys.exit(0 if verdict == "GO" else 1)


if __name__ == "__main__":
    main()
