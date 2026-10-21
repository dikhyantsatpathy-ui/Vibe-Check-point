import os
import pytest
from fastapi.testclient import TestClient

from app.main import app, is_demo_pass_enabled


@pytest.fixture
def client():
    return TestClient(app)


def test_is_demo_pass_enabled_default_and_production_block(monkeypatch):
    # 1. Unset -> False
    monkeypatch.delenv("DEMO_PASS_ENABLED", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert is_demo_pass_enabled() is False

    # 2. Enabled in dev -> True
    monkeypatch.setenv("DEMO_PASS_ENABLED", "1")
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert is_demo_pass_enabled() is True

    # 3. Enabled in production by default -> False
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DEMO_PASS_ALLOW_PRODUCTION", raising=False)
    assert is_demo_pass_enabled() is False

    # 4. Explicit override in production -> True
    monkeypatch.setenv("DEMO_PASS_ALLOW_PRODUCTION", "1")
    assert is_demo_pass_enabled() is True


def test_is_demo_pass_expiry(monkeypatch):
    monkeypatch.setenv("DEMO_PASS_ENABLED", "1")
    monkeypatch.setenv("ENVIRONMENT", "development")

    # Past expiry -> False
    monkeypatch.setenv("DEMO_PASS_EXPIRES_AT", "2020-01-01T00:00:00Z")
    assert is_demo_pass_enabled() is False

    # Future expiry -> True
    monkeypatch.setenv("DEMO_PASS_EXPIRES_AT", "2099-01-01T00:00:00Z")
    assert is_demo_pass_enabled() is True


def test_demo_login_endpoint_scenarios(client, monkeypatch):
    # Scenario A: Production blocked (returns 404)
    monkeypatch.setenv("DEMO_PASS_ENABLED", "1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DEMO_PASS_ALLOW_PRODUCTION", raising=False)
    monkeypatch.delenv("DEMO_PASS_EXPIRES_AT", raising=False)
    res = client.post("/api/admin/demo_login")
    assert res.status_code == 404

    # Scenario B: Expired (returns 404)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEMO_PASS_EXPIRES_AT", "2020-01-01T00:00:00Z")
    res = client.post("/api/admin/demo_login")
    assert res.status_code == 404

    # Scenario C: Enabled in development (returns 200)
    monkeypatch.delenv("DEMO_PASS_EXPIRES_AT", raising=False)
    res = client.post("/api/admin/demo_login")
    assert res.status_code == 200
    assert res.json().get("status") == "SUCCESS"
    assert "nischay_session" in res.cookies
