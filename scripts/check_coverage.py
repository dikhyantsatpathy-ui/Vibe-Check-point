#!/usr/bin/env python
"""Code coverage ratchet checker (P12).

Reads a pytest-cov JSON report and docs/coverage_thresholds.json.
Enforces that no module's coverage drops below its ratchet threshold.
Target coverage across modules is 85%.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def normalize_relpath(path_str: str) -> str:
    """Normalize file path to unix relative path (e.g. app/screening.py)."""
    p = pathlib.Path(path_str)
    try:
        rel = p.resolve().relative_to(REPO_ROOT)
        return str(rel).replace("\\", "/")
    except ValueError:
        pass
    norm = str(path_str).replace("\\", "/")
    # If path contains repo name or starts with prefix, take relative app/ or ml_service/
    for prefix in ("app/", "ml_service/"):
        idx = norm.find(prefix)
        if idx != -1:
            return norm[idx:]
    return norm


def check_coverage(coverage_path: pathlib.Path, thresholds_path: pathlib.Path) -> tuple[bool, str]:
    """Check module coverages against ratchet thresholds.
    
    Returns (success, report_text).
    """
    if not coverage_path.exists():
        return False, f"Coverage report not found: {coverage_path}"
    if not thresholds_path.exists():
        return False, f"Thresholds file not found: {thresholds_path}"

    with open(coverage_path, "r", encoding="utf-8") as f:
        cov_data = json.load(f)

    with open(thresholds_path, "r", encoding="utf-8") as f:
        thresh_data = json.load(f)

    target_pct = thresh_data.get("target_coverage", 85)
    modules_thresh = thresh_data.get("modules")
    if not modules_thresh:
        # Flat dict fallback
        modules_thresh = {
            k: v for k, v in thresh_data.items()
            if isinstance(v, (int, float)) and ("/" in k or "\\" in k)
        }

    cov_files = cov_data.get("files", {})
    # Map normalized path -> summary
    normalized_cov: dict[str, dict] = {}
    for filepath, file_info in cov_files.items():
        norm_key = normalize_relpath(filepath)
        normalized_cov[norm_key] = file_info.get("summary", {})

    lines: list[str] = [
        "==================================================",
        f"Coverage Ratchet Gate (Target: {target_pct}%)",
        "==================================================",
    ]

    violations: list[str] = []
    passed_count = 0

    for mod, min_pct in sorted(modules_thresh.items()):
        norm_mod = normalize_relpath(mod)
        summary = normalized_cov.get(norm_mod)

        if summary is None:
            # Check if partial match exists
            for k, s in normalized_cov.items():
                if k.endswith(norm_mod) or norm_mod.endswith(k):
                    summary = s
                    break

        if summary is None:
            if min_pct > 0:
                msg = f"FAIL: {norm_mod} - Missing from coverage report (threshold {min_pct}%)"
                violations.append(msg)
                lines.append(msg)
            else:
                lines.append(f"SKIP: {norm_mod} - Not present in report (threshold 0%)")
            continue

        actual_pct = summary.get("percent_covered", 0.0)
        actual_round = round(actual_pct, 2)

        if actual_pct < min_pct:
            msg = (
                f"FAIL: {norm_mod:<30} {actual_round:>6.2f}% < {min_pct:>2}% required "
                f"(REGRESSION: {actual_round - min_pct:+.2f}%)"
            )
            violations.append(msg)
            lines.append(msg)
        else:
            lines.append(f"PASS: {norm_mod:<30} {actual_round:>6.2f}% >= {min_pct:>2}%")
            passed_count += 1

    total_summary = cov_data.get("totals", {})
    total_pct = total_summary.get("percent_covered", 0.0)
    lines.append("--------------------------------------------------")
    lines.append(f"Overall measured coverage: {total_pct:.2f}% (Target: {target_pct}%)")
    lines.append(f"Ratchet passed: {passed_count}/{len(modules_thresh)} modules evaluated")

    if violations:
        lines.append("--------------------------------------------------")
        lines.append(f"GATE FAILED: {len(violations)} coverage regression(s) detected:")
        for v in violations:
            lines.append(f"  * {v}")
        return False, "\n".join(lines)

    lines.append("GATE PASSED: All module coverages satisfy or exceed ratchet thresholds.")
    return True, "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check coverage ratchet thresholds")
    parser.add_argument(
        "--coverage-json",
        type=pathlib.Path,
        default=REPO_ROOT / "coverage.json",
        help="Path to pytest-cov coverage.json report",
    )
    parser.add_argument(
        "--thresholds-json",
        type=pathlib.Path,
        default=REPO_ROOT / "docs" / "coverage_thresholds.json",
        help="Path to coverage_thresholds.json",
    )
    args = parser.parse_args()

    success, report = check_coverage(args.coverage_json, args.thresholds_json)
    print(report)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
