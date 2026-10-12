"""Tests for Phase P: Documentation and readiness hygiene (Task P7).

Asserts:
- docs/readiness_rows.json exists and each row has (name, evidence, metric_key, threshold, comparator).
- Every PASS / SHIP row has an existing evidence JSON file containing its metric_key.
- Any row with missing evidence or metric key is UNMEASURED.
- docs/SWITCH_READINESS.md renders directly from docs/readiness_rows.json.
- The strings '98.4' and '99.1' appear nowhere under docs/ (excluding work order) or the blueprint.
"""

from __future__ import annotations

import json
import pathlib
import pytest

from scripts.render_switch_readiness import evaluate_rows, get_nested_key, render_table, resolve_evidence_file

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
READINESS_JSON = REPO_ROOT / "docs" / "readiness_rows.json"
SWITCH_READINESS_MD = REPO_ROOT / "docs" / "SWITCH_READINESS.md"
BLUEPRINT_MD = REPO_ROOT / "SIH26188_ENGINEERING_BLUEPRINT.md"


def test_readiness_rows_schema_and_pass_evidence():
    """P7: Every PASS row in docs/readiness_rows.json has an existing evidence file with its metric key."""
    assert READINESS_JSON.exists(), "docs/readiness_rows.json must exist"

    with open(READINESS_JSON, "r", encoding="utf-8") as f:
        rows = json.load(f)

    assert isinstance(rows, list) and len(rows) > 0, "readiness_rows.json must be a non-empty list"

    required_fields = {"name", "evidence", "metric_key", "threshold", "comparator"}

    for r in rows:
        missing = required_fields - set(r.keys())
        assert not missing, f"Row {r.get('name')} missing fields: {missing}"

        verd = r.get("verdict", "")
        is_pass = ("PASS" in verd or "SHIP" in verd) and "DO-NOT-SHIP" not in verd and "UNMEASURED" not in verd and "NOT MEASURED" not in verd

        if is_pass:
            ev_file = resolve_evidence_file(r["evidence"])
            assert ev_file is not None and ev_file.exists(), (
                f"PASS row '{r['name']}' specifies evidence '{r['evidence']}' which was not found"
            )
            with open(ev_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            val = get_nested_key(data, r["metric_key"])
            assert val is not None, (
                f"PASS row '{r['name']}' metric_key '{r['metric_key']}' not found in {ev_file}"
            )


def test_readiness_unmeasured_when_evidence_missing():
    """P7: Rows with missing evidence or metric key are marked UNMEASURED with no accuracy figure."""
    with open(READINESS_JSON, "r", encoding="utf-8") as f:
        rows = json.load(f)

    evaluated = evaluate_rows(rows)
    face_row = next((r for r in evaluated if "Face" in r.get("name", "")), None)
    assert face_row is not None, "Face Biometrics row must exist in readiness_rows.json"
    assert face_row["resolved_verdict"] == "**UNMEASURED**"
    assert "98.4" not in face_row["resolved_real_metric"]
    assert "99.1" not in face_row["resolved_real_metric"]


def test_readiness_table_rendered_sync():
    """P7: docs/SWITCH_READINESS.md table matches the render output of readiness_rows.json."""
    assert SWITCH_READINESS_MD.exists()
    with open(READINESS_JSON, "r", encoding="utf-8") as f:
        rows = json.load(f)

    evaluated = evaluate_rows(rows)
    table_md = render_table(evaluated)

    content = SWITCH_READINESS_MD.read_text(encoding="utf-8")
    assert table_md in content, "docs/SWITCH_READINESS.md does not contain the rendered table from readiness_rows.json"


def test_readiness_no_unsupported_face_accuracy_strings_in_docs_and_blueprint():
    """P7: The strings '98.4' and '99.1' appear nowhere under docs/ or the blueprint."""
    docs_dir = REPO_ROOT / "docs"
    candidates = [p for p in docs_dir.rglob("*") if p.is_file() and p.name != "WORK_ORDER_V8.md"]
    if BLUEPRINT_MD.exists():
        candidates.append(BLUEPRINT_MD)

    violators = []
    for p in candidates:
        try:
            txt = p.read_text(encoding="utf-8")
            if "98.4" in txt or "99.1" in txt:
                violators.append(str(p.relative_to(REPO_ROOT)))
        except UnicodeDecodeError:
            pass

    assert not violators, f"Found ungrounded face accuracy strings '98.4' or '99.1' in: {violators}"
