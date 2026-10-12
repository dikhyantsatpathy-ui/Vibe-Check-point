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


def test_secrets_audit_patterns_flag_prefix_and_pcsk():
    """P9: scripts/audit_secrets_s1.py flags short prefix + key + ellipsis and pcsk_."""
    from scripts import audit_secrets_s1 as scanner

    assert "credential_prefix_ellipsis" in scanner.PATTERNS
    assert "pcsk_prefix" in scanner.PATTERNS

    # Test detection of prefix with ellipsis
    findings = scanner.scan_file_text(
        REPO_ROOT / "docs" / "OWNER_TODO.md",
        "docs/OWNER_TODO.md"
    )
    # The active OWNER_TODO.md must be clean
    assert not any(f["type"] in ("credential_prefix_ellipsis", "pcsk_prefix") for f in findings)

    # Synthetic check: ensure pattern actually matches prohibited string
    pat_ellip = scanner.PATTERNS["credential_prefix_ellipsis"]
    assert pat_ellip.search("pcsk_6P9BVB_...")
    assert pat_ellip.search("key_ABC123xyz...")
    assert pat_ellip.search("sk_live123456…")

    pat_pcsk = scanner.PATTERNS["pcsk_prefix"]
    assert pat_pcsk.search("pcsk_test")


def test_secrets_no_credentials_in_tracked_docs():
    """P9: Every tracked *.md, *.json, *.txt under docs/, eval/ and repo root is free of credentials and prefixes."""
    import subprocess
    from scripts import audit_secrets_s1 as scanner

    cmd = [
        "git", "ls-files",
        "*.md", "*.json", "*.txt",
        "docs/*.md", "docs/*.json", "docs/*.txt",
        "eval/*.md", "eval/*.json", "eval/*.txt",
    ]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=True)
    tracked_files = [REPO_ROOT / line.strip() for line in res.stdout.splitlines() if line.strip()]

    violators = []
    for f in tracked_files:
        if f.name == "WORK_ORDER_V8.md":
            continue
        findings = scanner.scan_file_text(f, str(f.relative_to(REPO_ROOT)))
        if findings:
            violators.extend(findings)

    assert not violators, f"Found credential-looking strings or prefixes in tracked documents: {violators}"


def test_secrets_owner_todo_roboflow_clean():
    """P9: docs/OWNER_TODO.md uses 'Roboflow API key (value not recorded)' and has no pcsk_."""
    owner_todo = REPO_ROOT / "docs" / "OWNER_TODO.md"
    assert owner_todo.exists()
    content = owner_todo.read_text(encoding="utf-8")
    assert "Roboflow API key (value not recorded)" in content
    assert "pcsk_" not in content


def test_fake_secrets_in_reverify_logs_unmistakably_fake():
    """P10: Test secrets in scripts/reverify_logs_v4.py are unmistakably fake."""
    from scripts import reverify_logs_v4 as rlog

    assert hasattr(rlog, "FAKE_SECRETS")
    for sec in rlog.FAKE_SECRETS:
        assert ("FAKE-TOKEN-NOT-REAL" in sec or "FAKE-PASSWORD-NOT-REAL" in sec), (
            f"Test secret '{sec}' must be unmistakably fake containing FAKE-TOKEN-NOT-REAL or FAKE-PASSWORD-NOT-REAL"
        )

    # Check script source file
    script_path = REPO_ROOT / "scripts" / "reverify_logs_v4.py"
    script_text = script_path.read_text(encoding="utf-8")
    assert "supersecretpass123" not in script_text
    assert "AIzaSyFakeGoogleApiKey1234567890abcdef" not in script_text
    assert "sk-proj-FAKESECRETINPASSPORT123456" not in script_text


def test_fake_secrets_redaction_behavior_verified():
    """P10: Redaction test in scripts/reverify_logs_v4.py executes and passes."""
    from scripts import reverify_logs_v4 as rlog

    # Run test
    rlog.test_log_redaction()

    # Verify report JSON
    report_file = REPO_ROOT / "eval" / "runs" / "20261011_reverify_v1" / "log_redaction_test.json"
    assert report_file.exists()
    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("verdict") == "PASS"
    assert data.get("pipeline_logger_leak_detected") is False
    for res in data.get("redaction_sanitizer_tests", []):
        assert res.get("secret_leaked") is False


# ---------------------------------------------------------------------------
# Task P12: Coverage Ratchet Gate and CI Step
# ---------------------------------------------------------------------------


def test_coverage_ci_workflow_has_coverage_commands():
    """P12: .github/workflows/ci.yml runs pytest --cov and scripts/check_coverage.py."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists(), "CI workflow file .github/workflows/ci.yml must exist"
    content = ci_path.read_text(encoding="utf-8")

    assert "pytest --cov=app --cov=ml_service --cov-report=json" in content, (
        "CI workflow must run pytest --cov=app --cov=ml_service --cov-report=json"
    )
    assert "python scripts/check_coverage.py" in content, (
        "CI workflow must run python scripts/check_coverage.py"
    )


def test_coverage_ci_stability_docstring_notice():
    """P12: tests/test_coverage_stability_t7.py has non-gating smoke test notice."""
    test_path = REPO_ROOT / "tests" / "test_coverage_stability_t7.py"
    assert test_path.exists(), "tests/test_coverage_stability_t7.py must exist"
    content = test_path.read_text(encoding="utf-8")

    expected_notice = "non-gating smoke test; the coverage gate is scripts/check_coverage.py"
    assert expected_notice in content, (
        f"tests/test_coverage_stability_t7.py must contain '{expected_notice}' in docstring"
    )


def test_coverage_ci_thresholds_file_and_check_script():
    """P12: docs/coverage_thresholds.json exists with target 85, and scripts/check_coverage.py passes."""
    thresh_path = REPO_ROOT / "docs" / "coverage_thresholds.json"
    assert thresh_path.exists(), "docs/coverage_thresholds.json must exist"

    with open(thresh_path, "r", encoding="utf-8") as f:
        thresh = json.load(f)

    assert thresh.get("target_coverage") == 85, "target_coverage must be documented as 85"
    modules = thresh.get("modules", {})
    assert len(modules) >= 10, "Must contain module ratchet thresholds"

    script_path = REPO_ROOT / "scripts" / "check_coverage.py"
    assert script_path.exists(), "scripts/check_coverage.py must exist"

    cov_file = REPO_ROOT / "coverage.json"
    if cov_file.exists():
        from scripts.check_coverage import check_coverage
        success, report = check_coverage(cov_file, thresh_path)
        assert success, f"Coverage check failed:\n{report}"


# ---------------------------------------------------------------------------
# Task P13: Owner Isolation Script
# ---------------------------------------------------------------------------


def test_owner_script_exists_and_safe():
    """P13: scripts/owner_check_isolation.ps1 exists, lists required names, no raw Write-Host."""
    script_path = REPO_ROOT / "scripts" / "owner_check_isolation.ps1"
    assert script_path.exists(), "scripts/owner_check_isolation.ps1 must exist"

    content = script_path.read_text(encoding="utf-8")

    # Required variable names
    required_names = [
        "DATABASE_URL",
        "MASTER_VAULT_KEY",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "ML_SERVICE_SECRET",
        "ML_SECRET_KEY",
        "HF_TOKEN",
    ]
    for name in required_names:
        assert name in content, f"owner_check_isolation.ps1 must list variable '{name}'"

    # Must contain no Write-Host of a raw value
    # Check each Write-Host line: must only output static text or status token
    import re
    write_hosts = re.findall(r"Write-Host\s+(.*)", content)
    for wh in write_hosts:
        wh_clean = wh.strip()
        # Disallow printing raw environment values or tokens
        assert "$prodVal" not in wh_clean, f"Unsafe Write-Host printing prod value: {wh}"
        assert "$testVal" not in wh_clean, f"Unsafe Write-Host printing test value: {wh}"
        assert "$cleanVal" not in wh_clean, f"Unsafe Write-Host printing clean value: {wh}"
        assert "$val" not in wh_clean, f"Unsafe Write-Host printing val: {wh}"
        assert "$bytes" not in wh_clean, f"Unsafe Write-Host printing bytes: {wh}"
        assert "$hex" not in wh_clean, f"Unsafe Write-Host printing hex: {wh}"

    # Must clean up temporary files
    assert "Remove-Item" in content, "owner_check_isolation.ps1 must clean up temporary files with Remove-Item"

