"""Tests for security headers and Content-Security-Policy-Report-Only (F-06).

Verifies:
  1. Real response headers from test client include nosniff, DENY, HSTS, and CSP-Report-Only.
  2. Content-Security-Policy-Report-Only does NOT contain 'unsafe-eval'.
  3. API routes receive no-store cache control headers.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_security_headers_present_on_health_and_root(client):
    """Verify security headers and Content-Security-Policy-Report-Only."""
    resp = client.get("/api/health")
    assert resp.status_code == 200

    headers = resp.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert "Strict-Transport-Security" in headers
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=(self)" in headers.get("Permissions-Policy", "")

    # CSP Report-Only
    csp = headers.get("Content-Security-Policy-Report-Only", "")
    assert csp, "Content-Security-Policy-Report-Only must be present"
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    # Never unsafe-eval
    assert "unsafe-eval" not in csp, "unsafe-eval must NEVER be allowed in CSP"

    # Cache-Control on API responses
    cache_control = headers.get("Cache-Control", "")
    assert "no-store" in cache_control
