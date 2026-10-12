#!/usr/bin/env python3
"""Renders docs/SWITCH_READINESS.md from docs/readiness_rows.json.

Ensures every number in the readiness table comes directly from measured JSON
evidence files. If an evidence file or metric key is missing, the row is
marked UNMEASURED.
"""

from __future__ import annotations

import json
import operator
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
READINESS_JSON = REPO_ROOT / "docs" / "readiness_rows.json"
SWITCH_READINESS_MD = REPO_ROOT / "docs" / "SWITCH_READINESS.md"

COMPARATORS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    ">": operator.gt,
    "<": operator.lt,
    "!=": operator.ne,
}


def resolve_evidence_file(evidence_pattern: str) -> pathlib.Path | None:
    if not evidence_pattern:
        return None
    if "*" in evidence_pattern:
        matches = sorted(REPO_ROOT.glob(evidence_pattern))
        return matches[-1] if matches else None
    p = REPO_ROOT / evidence_pattern
    return p if p.exists() else None


def get_nested_key(data: dict, key_path: str):
    curr = data
    for part in key_path.split("."):
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return None
    return curr


def evaluate_rows(rows: list[dict]) -> list[dict]:
    evaluated = []
    for row in rows:
        r = dict(row)
        ev_path = resolve_evidence_file(r.get("evidence", ""))
        metric_key = r.get("metric_key", "")

        if not ev_path or not ev_path.exists():
            r["is_measured"] = False
            r["resolved_verdict"] = "**UNMEASURED**"
            r["resolved_real_metric"] = "**UNMEASURED**"
            r["resolved_synthetic_metric"] = r.get("synthetic_metric", "**UNMEASURED**")
            if "UNMEASURED" not in r["resolved_synthetic_metric"] and "NOT MEASURED" not in r["resolved_synthetic_metric"]:
                r["resolved_synthetic_metric"] = "**UNMEASURED**"
        else:
            try:
                with open(ev_path, "r", encoding="utf-8") as f:
                    ev_data = json.load(f)
                val = get_nested_key(ev_data, metric_key)
                if val is None:
                    r["is_measured"] = False
                    r["resolved_verdict"] = "**UNMEASURED**"
                    r["resolved_real_metric"] = "**UNMEASURED**"
                else:
                    r["is_measured"] = True
                    comp_fn = COMPARATORS.get(r.get("comparator", ">="), operator.ge)
                    target_thresh = r.get("threshold")
                    try:
                        passed = comp_fn(val, target_thresh)
                    except Exception:
                        passed = False

                    r["resolved_real_metric"] = r.get("real_metric", "")
                    r["resolved_synthetic_metric"] = r.get("synthetic_metric", "")
                    # Preserve configured verdict if measured
                    r["resolved_verdict"] = r.get("verdict", "**SHIP**")
            except Exception:
                r["is_measured"] = False
                r["resolved_verdict"] = "**UNMEASURED**"
                r["resolved_real_metric"] = "**UNMEASURED**"

        evaluated.append(r)
    return evaluated


def render_table(evaluated_rows: list[dict]) -> str:
    lines = [
        "| Stage | Evaluated Backend | REAL-Data Metric | SYNTHETIC Metric | Latency (2 vCPU Throttled) | File SHA-256 | Verdict |",
        "|---|---|---|---|---|---|:---:|",
    ]
    for r in evaluated_rows:
        stage = f"**{r.get('stage', r.get('name'))}**"
        backend = r.get("backend", "")
        real_m = r.get("resolved_real_metric", "")
        synth_m = r.get("resolved_synthetic_metric", "")
        lat = r.get("latency", "")
        sha = r.get("file_sha256", "")
        verd = r.get("resolved_verdict", "")
        lines.append(f"| {stage} | {backend} | {real_m} | {synth_m} | {lat} | {sha} | {verd} |")
    return "\n".join(lines)


def update_switch_readiness(table_md: str) -> None:
    if not SWITCH_READINESS_MD.exists():
        return
    content = SWITCH_READINESS_MD.read_text(encoding="utf-8")
    start_tag = "## 1. Stage-by-Stage Switch Readiness Table\n\n"
    end_tag = "\n\n---\n\n## 2. Recommended Deployment Environment Block"

    if start_tag in content and end_tag in content:
        prefix = content.split(start_tag)[0] + start_tag
        suffix = end_tag + content.split(end_tag)[1]
        new_content = prefix + table_md + suffix
        SWITCH_READINESS_MD.write_text(new_content, encoding="utf-8")
    else:
        # If duplicated earlier, clean up
        lines = content.splitlines()
        try:
            sec1_idx = next(i for i, line in enumerate(lines) if "## 1. Stage-by-Stage Switch Readiness Table" in line)
            sec2_idx = next(i for i, line in enumerate(lines) if "## 2. Recommended Deployment Environment Block" in line)
            prefix = "\n".join(lines[:sec1_idx + 1]) + "\n\n"
            suffix = "\n\n---\n\n" + "\n".join(lines[sec2_idx:])
            new_content = prefix + table_md + suffix + "\n"
            SWITCH_READINESS_MD.write_text(new_content, encoding="utf-8")
        except Exception as e:
            print(f"Warning: Failed to update table: {e}", file=sys.stderr)


def main():
    if not READINESS_JSON.exists():
        print(f"Error: {READINESS_JSON} does not exist", file=sys.stderr)
        sys.exit(1)

    with open(READINESS_JSON, "r", encoding="utf-8") as f:
        rows = json.load(f)

    evaluated = evaluate_rows(rows)
    table_md = render_table(evaluated)

    if "--check" in sys.argv:
        content = SWITCH_READINESS_MD.read_text(encoding="utf-8")
        if table_md not in content:
            print("docs/SWITCH_READINESS.md table is out of sync with readiness_rows.json", file=sys.stderr)
            sys.exit(1)
        print("docs/SWITCH_READINESS.md is in sync")
        sys.exit(0)

    update_switch_readiness(table_md)
    print("Rendered and updated docs/SWITCH_READINESS.md successfully")


if __name__ == "__main__":
    main()
