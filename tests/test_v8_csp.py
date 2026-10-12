"""Tests for Phase P: Honest Content-Security-Policy (Task P8).

Asserts:
- Enforced header (Content-Security-Policy) and Report-Only header (Content-Security-Policy-Report-Only) differ.
- Baseline enforced header permits unsafe-inline in script-src.
- Report-Only header has NO unsafe-inline in script-src.
- Report-Only header includes sha256 hashes matching all inline <script> tags in app/static/index.html.
- Neither header contains unsafe-eval.
- Setting CSP_STRICT_ENFORCE=1 switches the enforced header to the strict policy (no unsafe-inline).
- Modifying index.html mtime triggers hash recomputation.
"""

from __future__ import annotations

import base64
import hashlib
import os
import pathlib
import re
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_csp_headers_differ_and_enforce_baseline(monkeypatch):
    monkeypatch.delenv("CSP_STRICT_ENFORCE", raising=False)
    from app.main import app

    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200

    enforced = res.headers.get("Content-Security-Policy")
    report_only = res.headers.get("Content-Security-Policy-Report-Only")

    assert enforced is not None, "Content-Security-Policy header must be present"
    assert report_only is not None, "Content-Security-Policy-Report-Only header must be present"
    assert enforced != report_only, "Enforced header and Report-Only header must differ"

    # Enforced baseline permits unsafe-inline in script-src
    assert "'unsafe-inline'" in enforced, "Baseline enforced CSP must contain 'unsafe-inline' in script-src"

    # Report-Only does not permit unsafe-inline in script-src
    # Check specifically within script-src directive
    script_src_ro = [part for part in report_only.split(";") if "script-src" in part]
    assert script_src_ro, "script-src directive must exist in Report-Only header"
    assert "'unsafe-inline'" not in script_src_ro[0], "Report-Only script-src must not contain 'unsafe-inline'"

    # Neither header may contain unsafe-eval
    assert "'unsafe-eval'" not in enforced, "Enforced CSP must not contain 'unsafe-eval'"
    assert "'unsafe-eval'" not in report_only, "Report-Only CSP must not contain 'unsafe-eval'"


def test_report_only_hashes_match_inline_scripts(monkeypatch):
    monkeypatch.delenv("CSP_STRICT_ENFORCE", raising=False)
    from app.main import app

    index_path = REPO_ROOT / "app" / "static" / "index.html"
    assert index_path.exists(), "app/static/index.html must exist"

    # Compute expected hashes directly from file
    html_content = index_path.read_text(encoding="utf-8")
    pattern = re.compile(r"<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
    expected_hashes = []
    for m in pattern.finditer(html_content):
        body = m.group(1)
        digest = hashlib.sha256(body.encode("utf-8")).digest()
        b64 = base64.b64encode(digest).decode("ascii")
        expected_hashes.append(f"'sha256-{b64}'")

    assert len(expected_hashes) > 0, "app/static/index.html must have at least one inline script"

    client = TestClient(app)
    res = client.get("/health")
    report_only = res.headers.get("Content-Security-Policy-Report-Only", "")

    for h in expected_hashes:
        assert h in report_only, f"Expected inline script hash {h} not found in Report-Only header"


def test_strict_enforce_flag_switches_enforced_policy(monkeypatch):
    monkeypatch.setenv("CSP_STRICT_ENFORCE", "1")
    from app.main import app

    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200

    enforced = res.headers.get("Content-Security-Policy", "")
    report_only = res.headers.get("Content-Security-Policy-Report-Only", "")

    # With flag on, enforced header becomes the strict policy
    script_src_enforced = [part for part in enforced.split(";") if "script-src" in part]
    assert script_src_enforced, "script-src directive must exist in enforced header"
    assert "'unsafe-inline'" not in script_src_enforced[0], (
        "With CSP_STRICT_ENFORCE=1, enforced script-src must not contain 'unsafe-inline'"
    )
    assert "'unsafe-eval'" not in enforced
    assert "'unsafe-eval'" not in report_only
    assert "'sha256-" in enforced, "With CSP_STRICT_ENFORCE=1, enforced script-src must contain sha256 hashes"


def test_csp_mtime_recomputation(tmp_path, monkeypatch):
    import time
    from app import main as app_main

    # Create dummy static file in temp dir
    fake_html = tmp_path / "index.html"
    fake_html.write_text("<html><script>var x = 1;</script></html>", encoding="utf-8")

    monkeypatch.setattr(app_main, "_STATIC_INDEX_PATH", fake_html)
    monkeypatch.setattr(app_main, "_CACHED_INDEX_MTIME", None)
    monkeypatch.setattr(app_main, "_CACHED_STRICT_CSP", None)

    _, ro1 = app_main.get_csp_policies()
    h1 = base64.b64encode(hashlib.sha256(b"var x = 1;").digest()).decode("ascii")
    assert f"'sha256-{h1}'" in ro1

    # Modify file and advance mtime
    time.sleep(0.05)
    fake_html.write_text("<html><script>var y = 2;</script></html>", encoding="utf-8")
    new_mtime = fake_html.stat().st_mtime + 2.0
    os.utime(fake_html, (new_mtime, new_mtime))

    _, ro2 = app_main.get_csp_policies()
    h2 = base64.b64encode(hashlib.sha256(b"var y = 2;").digest()).decode("ascii")
    assert f"'sha256-{h2}'" in ro2
    assert f"'sha256-{h1}'" not in ro2
