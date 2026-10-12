"""Tests for Phase R: agent_ctl.py resume system (Task R2).

Asserts:
- init builds the queue and a second init preserves statuses.
- done on a failing task (exit 3) leaves task in DOING and exits 1.
- done on a passing task marks it DONE.
- done on a manual task ('-') requires --evidence.
- resume after a simulated crash (task left DOING) prints NEXT ACTION mentioning the task.
- reconcile marks passing TODO tasks DONE after QUEUE.json is rebuilt or recovered.
- section prints exactly one section.
- the Windows branch of pid_alive never calls os.kill.
- test_agents_files: AGENTS.md and GEMINI.md exist and contain required resume phrases.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _run_ctl(temp_dir: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(temp_dir / "scripts" / "agent_ctl.py"), *args],
        cwd=str(temp_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def repo_skeleton(tmp_path: pathlib.Path) -> pathlib.Path:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / "agent_ctl.py", scripts_dir / "agent_ctl.py")

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)

    sample_work_order = (
        "# DUMMY WORK ORDER\n\n"
        "## 1. CONTROL LAYER\n"
        "Control section text line 1.\n"
        "Control section text line 2.\n\n"
        "## 2. PHASE T — TESTS\n"
        "Test section text.\n\n"
        "## 8. QUEUE\n"
        "```queue\n"
        "T1 | P | task one passing | python -c \"import sys; sys.exit(0)\"\n"
        "T2 | P | task two failing | python -c \"import sys; sys.exit(3)\"\n"
        "T3 | P | task three manual | -\n"
        "```\n"
    )
    (docs_dir / "WORK_ORDER_V8.md").write_text(sample_work_order, encoding="utf-8")

    # git init
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True, check=True)

    return tmp_path


def test_ctl_init_and_idempotence(repo_skeleton: pathlib.Path):
    res1 = _run_ctl(repo_skeleton, "init")
    assert res1.returncode == 0
    assert "queue ready: 3 tasks" in res1.stdout

    q_file = repo_skeleton / "docs" / "QUEUE.json"
    assert q_file.exists()
    q_data = json.loads(q_file.read_text(encoding="utf-8"))
    assert len(q_data["tasks"]) == 3

    # Start T1 and complete it
    _run_ctl(repo_skeleton, "start", "T1")
    _run_ctl(repo_skeleton, "done", "T1")

    q_data = json.loads(q_file.read_text(encoding="utf-8"))
    assert any(t["id"] == "T1" and t["status"] == "DONE" for t in q_data["tasks"])

    # Second init should preserve DONE status of T1
    res2 = _run_ctl(repo_skeleton, "init")
    assert res2.returncode == 0
    q_data2 = json.loads(q_file.read_text(encoding="utf-8"))
    t1_status = [t["status"] for t in q_data2["tasks"] if t["id"] == "T1"][0]
    assert t1_status == "DONE"


def test_ctl_done_exit_3_failure_leaves_doing(repo_skeleton: pathlib.Path):
    _run_ctl(repo_skeleton, "init")
    _run_ctl(repo_skeleton, "start", "T2")

    res = _run_ctl(repo_skeleton, "done", "T2")
    assert res.returncode == 1
    assert "NOT DONE: verify command failed" in res.stdout

    q_data = json.loads((repo_skeleton / "docs" / "QUEUE.json").read_text(encoding="utf-8"))
    t2 = [t for t in q_data["tasks"] if t["id"] == "T2"][0]
    assert t2["status"] == "DOING"


def test_ctl_done_passing_marks_done(repo_skeleton: pathlib.Path):
    _run_ctl(repo_skeleton, "init")
    _run_ctl(repo_skeleton, "start", "T1")

    res = _run_ctl(repo_skeleton, "done", "T1")
    assert res.returncode == 0
    assert "DONE T1" in res.stdout

    q_data = json.loads((repo_skeleton / "docs" / "QUEUE.json").read_text(encoding="utf-8"))
    t1 = [t for t in q_data["tasks"] if t["id"] == "T1"][0]
    assert t1["status"] == "DONE"


def test_ctl_manual_task_requires_evidence(repo_skeleton: pathlib.Path):
    _run_ctl(repo_skeleton, "init")
    _run_ctl(repo_skeleton, "start", "T3")

    res_no_ev = _run_ctl(repo_skeleton, "done", "T3")
    assert res_no_ev.returncode == 1
    assert "manual task: --evidence is required" in res_no_ev.stdout

    res_with_ev = _run_ctl(repo_skeleton, "done", "T3", "--evidence", "manual receipt verified")
    assert res_with_ev.returncode == 0
    assert "DONE T3" in res_with_ev.stdout


def test_ctl_resume_after_simulated_crash(repo_skeleton: pathlib.Path):
    _run_ctl(repo_skeleton, "init")
    _run_ctl(repo_skeleton, "start", "T2")

    res_resume = _run_ctl(repo_skeleton, "resume")
    assert res_resume.returncode == 0
    assert "task T2 was interrupted" in res_resume.stdout
    assert "NEXT ACTION:" in res_resume.stdout


def test_ctl_reconcile_marks_passing_tasks_done(repo_skeleton: pathlib.Path):
    _run_ctl(repo_skeleton, "init")
    # Delete QUEUE.json simulating state loss, then re-init
    q_file = repo_skeleton / "docs" / "QUEUE.json"
    q_file.unlink()

    # Re-init fresh (all tasks TODO)
    _run_ctl(repo_skeleton, "init")

    # Run reconcile: T1 passes, T2 fails, T3 is manual (no verify)
    res_recon = _run_ctl(repo_skeleton, "reconcile")
    assert res_recon.returncode == 0
    assert "reconciled DONE T1" in res_recon.stdout

    q_data = json.loads(q_file.read_text(encoding="utf-8"))
    t1 = [t for t in q_data["tasks"] if t["id"] == "T1"][0]
    t2 = [t for t in q_data["tasks"] if t["id"] == "T2"][0]
    assert t1["status"] == "DONE"
    assert t2["status"] == "TODO"


def test_ctl_section_prints_exactly_one_section(repo_skeleton: pathlib.Path):
    res = _run_ctl(repo_skeleton, "section", "CONTROL")
    assert res.returncode == 0
    assert "## 1. CONTROL LAYER" in res.stdout
    assert "Control section text line 1." in res.stdout
    assert "## 2. PHASE T" not in res.stdout


def test_pid_alive_windows_branch_never_calls_os_kill():
    ctl_source = (REPO_ROOT / "scripts" / "agent_ctl.py").read_text(encoding="utf-8")
    fn_idx = ctl_source.find("def pid_alive(pid):")
    assert fn_idx != -1
    fn_end = ctl_source.find("\ndef ", fn_idx + 1)
    fn_body = ctl_source[fn_idx:fn_end]

    # Verify that in os.name == 'nt' branch, os.kill is never called
    lines = fn_body.splitlines()
    in_nt = False
    for line in lines:
        if 'if os.name == "nt":' in line or "if os.name == 'nt':" in line:
            in_nt = True
        elif in_nt and (line.startswith("    try:") or line.startswith("    os.") or line.startswith("    if ")):
            # We reached the non-nt branch
            in_nt = False
        code_only = line.split("#")[0].strip()
        if in_nt:
            assert "os.kill" not in code_only, "os.kill must never be called in Windows pid_alive branch"


def test_agents_files():
    agents_path = REPO_ROOT / "AGENTS.md"
    gemini_path = REPO_ROOT / "GEMINI.md"

    assert agents_path.exists(), "AGENTS.md must exist in root"
    assert gemini_path.exists(), "GEMINI.md must exist in root"

    agents_content = agents_path.read_text(encoding="utf-8")
    gemini_content = gemini_path.read_text(encoding="utf-8")

    assert "get back to work" in agents_content
    assert "agent_ctl.py resume" in agents_content

    assert "get back to work" in gemini_content
    assert "agent_ctl.py resume" in gemini_content
