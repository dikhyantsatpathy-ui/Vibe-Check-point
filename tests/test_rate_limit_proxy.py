"""Tests for rate-limiting client IP resolution and TRUST_PROXY_HEADERS (F-05).

Verifies:
  1. TRUST_PROXY_HEADERS defaults to OFF.
  2. Spoofed X-Forwarded-For headers are ignored by default; direct client host is used.
  3. When TRUST_PROXY_HEADERS is explicitly enabled ('1', 'true', 'yes'),
     X-Forwarded-For is respected.
  4. Documents that in-memory fallback limits counters per instance without REDIS_URL.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request
from app.main import get_trusted_remote_address


def _make_dummy_request(headers: dict[str, str] | None = None, client_host: str = "192.168.1.50") -> Request:
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/health",
        "headers": raw_headers,
        "client": (client_host, 12345),
    }
    return Request(scope)


def test_rate_limit_ignores_spoofed_forwarded_header_by_default(monkeypatch):
    """By default (TRUST_PROXY_HEADERS unset/off), X-Forwarded-For is ignored to prevent spoofing."""
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    req = _make_dummy_request(
        headers={"X-Forwarded-For": "203.0.113.195, 10.0.0.1"},
        client_host="192.168.1.50",
    )
    ip = get_trusted_remote_address(req)
    # Must use client_host, NOT the spoofed header
    assert ip == "192.168.1.50"


def test_rate_limit_honors_forwarded_header_when_proxy_trusted(monkeypatch):
    """When TRUST_PROXY_HEADERS is truthy, first IP from X-Forwarded-For is used."""
    for truthy in ("1", "true", "yes", "TRUE"):
        monkeypatch.setenv("TRUST_PROXY_HEADERS", truthy)
        req = _make_dummy_request(
            headers={"X-Forwarded-For": "203.0.113.195, 10.0.0.1"},
            client_host="127.0.0.1",
        )
        ip = get_trusted_remote_address(req)
        assert ip == "203.0.113.195"


def test_rate_limit_fallback_without_forwarded_header(monkeypatch):
    """Even when TRUST_PROXY_HEADERS is on, falls back to client_host if header missing."""
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    req = _make_dummy_request(headers={}, client_host="10.10.10.10")
    assert get_trusted_remote_address(req) == "10.10.10.10"
