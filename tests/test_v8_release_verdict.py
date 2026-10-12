"""Tests for Task A2: Release Verdict Evaluator.

Verifies:
1. GO condition when all quality gates pass.
2. NO-GO for each distinct failure reason:
   - FALSE claim in claims report
   - OPEN S1 or S2 audit finding
   - Readiness row FAIL
   - BLOCKED task in P/T/K phase (unless flagged owner)
   - Test suite not green 3 consecutive times
3. Invariant: The words "ready" or "release" appear in the report ONLY next to a GO verdict.
4. CLI invocation and report file generation with --write.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import pytest

from scripts.release_verdict import evaluate_release_verdict

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def get_clean_synthetic_inputs():
    """Return synthetic input set that passes all gates."""
    queue_data = {
        "tasks": [
            {"id": "P1", "phase": "P", "status": "DONE"},
            {"id": "P2", "phase": "P", "status": "DONE"},
            {"id": "T1", "phase": "T", "status": "DONE"},
            {"id": "F13", "phase": "F", "status": "BLOCKED", "owner": True},
        ]
    }
    claims_data = {
        "claims": [
            {"claim_id": "CLM-01", "status": "TRUE", "verified": True},
            {"claim_id": "CLM-02", "status": "TRUE", "verified": True},
        ]
    }
    audit_rows = [
        {"id": "F-001", "severity": "S3", "status": "OPEN"},
        {"id": "C-01", "severity": "S2", "status": "RESOLVED"},
        {"id": "C-02", "severity": "S1", "status": "FIXED"},
    ]
    readiness_data = [
        {"name": "Face Biometrics", "verdict": "UNMEASURED"},
        {"name": "MRZ Parser", "verdict": "PASS"},
    ]
    suite_data = {
        "runs": 3,
        "failed": 0,
        "passed": 3,
    }
    test_counts_data = {"total": 436}
    return queue_data, claims_data, audit_rows, readiness_data, suite_data, test_counts_data


def test_release_verdict_go_condition():
    """A2: GO when all gates pass, and includes RELEASE READY."""
    queue, claims, audit, readiness, suite, counts = get_clean_synthetic_inputs()
    verdict, reasons, report = evaluate_release_verdict(
        queue_data=queue,
        claims_data=claims,
        audit_rows=audit,
        readiness_data=readiness,
        suite_data=suite,
        test_counts_data=counts,
    )
    assert verdict == "GO"
    assert len(reasons) == 0
    assert "RELEASE READY" in report


def test_release_verdict_nogo_false_claim():
    """A2: NO-GO when a claim is FALSE; no forbidden words in report."""
    queue, claims, audit, readiness, suite, counts = get_clean_synthetic_inputs()
    claims["claims"].append({"claim_id": "CLM-99", "status": "FALSE", "verified": False})

    verdict, reasons, report = evaluate_release_verdict(
        queue_data=queue,
        claims_data=claims,
        audit_rows=audit,
        readiness_data=readiness,
        suite_data=suite,
        test_counts_data=counts,
    )
    assert verdict == "NO-GO"
    assert any("FALSE claims detected" in r for r in reasons)
    assert "ready" not in report.lower()
    assert "release" not in report.lower()


def test_release_verdict_nogo_open_s1_s2():
    """A2: NO-GO when an S1 or S2 finding is OPEN; no forbidden words in report."""
    queue, claims, audit, readiness, suite, counts = get_clean_synthetic_inputs()
    audit.append({"id": "F-S1-LEAK", "severity": "S1", "status": "OPEN"})

    verdict, reasons, report = evaluate_release_verdict(
        queue_data=queue,
        claims_data=claims,
        audit_rows=audit,
        readiness_data=readiness,
        suite_data=suite,
        test_counts_data=counts,
    )
    assert verdict == "NO-GO"
    assert any("OPEN S1/S2" in r for r in reasons)
    assert "ready" not in report.lower()
    assert "release" not in report.lower()


def test_release_verdict_nogo_readiness_fail():
    """A2: NO-GO when any readiness row is FAIL; no forbidden words in report."""
    queue, claims, audit, readiness, suite, counts = get_clean_synthetic_inputs()
    readiness.append({"name": "Tamper Detection", "verdict": "FAIL"})

    verdict, reasons, report = evaluate_release_verdict(
        queue_data=queue,
        claims_data=claims,
        audit_rows=audit,
        readiness_data=readiness,
        suite_data=suite,
        test_counts_data=counts,
    )
    assert verdict == "NO-GO"
    assert any("Readiness row FAIL detected" in r for r in reasons)
    assert "ready" not in report.lower()
    assert "release" not in report.lower()


def test_release_verdict_nogo_blocked_ptk_task():
    """A2: NO-GO when a task in phase P/T/K is BLOCKED (non-owner)."""
    queue, claims, audit, readiness, suite, counts = get_clean_synthetic_inputs()
    queue["tasks"].append({"id": "P99", "phase": "P", "status": "BLOCKED", "owner": False})

    verdict, reasons, report = evaluate_release_verdict(
        queue_data=queue,
        claims_data=claims,
        audit_rows=audit,
        readiness_data=readiness,
        suite_data=suite,
        test_counts_data=counts,
    )
    assert verdict == "NO-GO"
    assert any("BLOCKED non-owner tasks in P/T/K" in r for r in reasons)
    assert "ready" not in report.lower()
    assert "release" not in report.lower()


def test_release_verdict_owner_blocked_ptk_exempt():
    """A2: BLOCKED task in P/T/K that is owner-flagged does NOT block GO."""
    queue, claims, audit, readiness, suite, counts = get_clean_synthetic_inputs()
    queue["tasks"].append({"id": "P13", "phase": "P", "status": "BLOCKED", "owner": True})

    verdict, reasons, report = evaluate_release_verdict(
        queue_data=queue,
        claims_data=claims,
        audit_rows=audit,
        readiness_data=readiness,
        suite_data=suite,
        test_counts_data=counts,
    )
    assert verdict == "GO"
    assert len(reasons) == 0


def test_release_verdict_nogo_suite_not_three_green():
    """A2: NO-GO when suite has not passed 3 consecutive runs."""
    queue, claims, audit, readiness, suite, counts = get_clean_synthetic_inputs()
    suite["runs"] = 2  # Only 2 runs

    verdict, reasons, report = evaluate_release_verdict(
        queue_data=queue,
        claims_data=claims,
        audit_rows=audit,
        readiness_data=readiness,
        suite_data=suite,
        test_counts_data=counts,
    )
    assert verdict == "NO-GO"
    assert any("Test suite not green 3 consecutive times" in r for r in reasons)
    assert "ready" not in report.lower()
    assert "release" not in report.lower()


def test_release_verdict_cli_write(tmp_path):
    """A2: CLI execution writes report file when --write is specified."""
    out_file = tmp_path / "verdict_report.txt"
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "release_verdict.py"), "--write", str(out_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert out_file.exists(), "Report file must be created"
    content = out_file.read_text(encoding="utf-8")
    assert "DEPLOYMENT GATE ASSESSMENT" in content
