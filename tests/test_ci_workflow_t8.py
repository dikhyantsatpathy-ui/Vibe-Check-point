"""Phase T8 — Test Hardening: CI Workflow Audit Suite.

Validates:
1. Presence and syntax of GitHub Actions workflows in .github/workflows/.
2. Coverage of linting, security invariants, regression testing, and model auditing steps.
3. Produces eval/runs/20261011_reverify_v1/ci_audit_t8.json artifact.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import pytest


def test_t8_ci_workflow_structure_and_coverage(tmp_path):
    """Audit .github/workflows/ci.yml for mandatory quality gates."""
    wf_path = Path(".github/workflows/ci.yml")
    assert wf_path.exists(), "CI workflow file .github/workflows/ci.yml must exist"

    content = wf_path.read_text(encoding="utf-8")
    assert "name: CI" in content
    assert "runs-on: ubuntu-latest" in content

    # Mandatory quality gates
    mandatory_checks = {
        "python_setup": "actions/setup-python",
        "lint_gate": "ruff check",
        "hygiene_gate": "scripts/check_repo_hygiene.py",
        "security_invariants_gate": "test_invariants_t1.py",
        "contract_snapshots_gate": "test_contract_snapshots_t2.py",
        "drift_gate": "test_yolo_roi_dual_implementation_drift",
        "test_suite_gate": "pytest -v",
        "model_card_gate": "MODEL_CARD.md",
    }

    results = {}
    for gate_name, pattern in mandatory_checks.items():
        present = pattern in content
        assert present, f"Mandatory CI gate '{gate_name}' ({pattern}) missing from ci.yml"
        results[gate_name] = present

    # Write evaluation artifact
    out_dir = Path("eval/runs/20261011_reverify_v1") if os.getenv("UPDATE_GOLDEN") == "1" else tmp_path
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "ci_audit_t8.json"

    report = {
        "phase": "T8",
        "workflow_file": str(wf_path),
        "ci_configured": True,
        "gates_verified": results,
    }
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert out_file.exists()
