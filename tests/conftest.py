"""
Test bootstrap. Runs before pytest imports any test module.

Isolates tests from developer environment leaks and ensures deterministic test runs.
"""

import os
import sys
import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)
_APP_DIR = os.path.join(_REPO_ROOT, "app")

# 1. Make `import main` / `import screening` resolve the way the app does.
for _p in (_REPO_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 2. Mark the process as a test run BEFORE app.keys is imported.
os.environ["TESTING"] = "1"

# 3. Deterministic test defaults for credentials and flags
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
os.environ.setdefault("SUPER_ADMINS", "test-superadmin@example.com")
os.environ.setdefault("ALLOWED_DOMAINS", "")
os.environ.setdefault("ALLOWED_EMAILS", "")
os.environ.setdefault("KEEPALIVE_INTERVAL", "0")


@pytest.fixture(autouse=True)
def _isolate_detector_backends(monkeypatch):
    """Ensure stage backend variables are clean unless explicitly set by a test."""
    for var in (
        "CARD_DETECTOR_BACKEND",
        "DETECTOR_BACKEND",
        "FIELD_DETECTOR_BACKEND",
        "MRZ_DETECTOR_BACKEND",
        "ID_FIELD_DETECTOR_BACKEND",
    ):
        monkeypatch.delenv(var, raising=False)
