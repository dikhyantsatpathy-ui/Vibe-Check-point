#!/usr/bin/env python
"""Three-run Test Suite Stability Runner (Task A3).

Runs the test suite N times, stops on the first failure, and records stability metrics to:
eval/runs/<timestamp>_suite/result.json with fields:
- runs: number of completed runs
- passed: number of passed runs
- failed: number of failed runs
- durations: list of durations in seconds
- flaky_candidates: list of test identifiers that failed in any run
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def parse_failed_tests(output: str) -> list[str]:
    """Extract failed test names from pytest output."""
    failed: list[str] = []
    # Match lines like: FAILED tests/test_foo.py::test_bar - AssertionError...
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("FAILED ") and "::" in line:
            parts = line.split()
            if len(parts) >= 2:
                failed.append(parts[1])
    return sorted(list(set(failed)))


def run_suite_n(
    n: int,
    test_cmd: list[str] | None = None,
    output_dir: pathlib.Path | None = None,
) -> tuple[bool, dict[str, Any], pathlib.Path]:
    """Execute test suite N times, stopping on first failure."""
    if test_cmd is None:
        test_cmd = [sys.executable, "-m", "pytest", "-q", "-m", "not slow"]

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = output_dir or (REPO_ROOT / "eval" / "runs" / f"{ts}_suite")
    out_dir.mkdir(parents=True, exist_ok=True)
    result_file = out_dir / "result.json"

    durations: list[float] = []
    flaky_candidates: list[str] = []
    passed = 0
    failed = 0
    completed_runs = 0

    print(f"Starting stability evaluation for N={n} runs...")
    print(f"Command: {' '.join(test_cmd)}")

    for run_idx in range(1, n + 1):
        print(f"\n--- Run {run_idx}/{n} ---")
        t0 = time.perf_counter()

        # Run test suite
        proc = subprocess.run(
            test_cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        duration = round(time.perf_counter() - t0, 3)
        durations.append(duration)
        completed_runs += 1

        if proc.returncode == 0:
            passed += 1
            print(f"[PASS] Run {run_idx} completed in {duration:.2f}s")
        else:
            failed += 1
            print(f"[FAIL] Run {run_idx} failed with exit code {proc.returncode} in {duration:.2f}s")
            run_failures = parse_failed_tests(proc.stdout)
            if run_failures:
                print(f"Failed tests detected: {run_failures}")
                flaky_candidates.extend(run_failures)
            else:
                # Print tail of output
                lines = proc.stdout.splitlines()
                tail = "\n".join(lines[-20:]) if len(lines) > 20 else proc.stdout
                print(f"Failure output:\n{tail}")
            print(f"Stopping execution on first failure at run {run_idx}/{n}.")
            break

    result_data: dict[str, Any] = {
        "runs": completed_runs,
        "passed": passed,
        "failed": failed,
        "durations": durations,
        "flaky_candidates": sorted(list(set(flaky_candidates))),
        "target_runs": n,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "command": " ".join(test_cmd),
    }

    result_file.write_text(json.dumps(result_data, indent=2), encoding="utf-8")
    print(f"\nStability result written to: {result_file}")

    success = (failed == 0 and passed == n)
    return success, result_data, result_file


def main():
    parser = argparse.ArgumentParser(description="Run test suite N times for stability verification")
    parser.add_argument("n", type=int, nargs="?", default=3, help="Number of suite iterations (default: 3)")
    parser.add_argument("--command", nargs="*", help="Custom pytest command arguments")
    parser.add_argument("--output-dir", type=pathlib.Path, help="Custom output directory")
    args = parser.parse_args()

    cmd = args.command if args.command else None
    success, _, _ = run_suite_n(args.n, test_cmd=cmd, output_dir=args.output_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
