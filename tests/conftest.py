"""
Test bootstrap. Runs before pytest imports any test module.

This exists to make it structurally impossible for a test run to touch a real
database or a real key. `app/main.py` executes at import time: it builds a
SQLAlchemy engine, starts a Neon keep-alive daemon thread, and previously
resolved a *hardcoded production* Postgres DSN when DATABASE_URL was unset. Any
of those would have pointed a local `pytest` at the live audit database.

So the environment is pinned here, before a single application import happens.
If you are reading this while debugging a test that "can't find its database",
the throwaway SQLite file is created under the system temp directory and
deleted on teardown.

That throwaway database is TEST-ONLY. The application itself refuses to start
on a SQLite URL -- see the `_IS_TEST_SQLITE` guard in app/main.py -- because
SQLite serialises all writes behind one lock and cannot hold the append-only
audit chain across concurrent officers or a cold start. Using it here just
means the suite needs no Postgres server; nothing about it is reachable in a
deployment.
"""

import os
import sys
import tempfile
import atexit

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)
_APP_DIR = os.path.join(_REPO_ROOT, "app")

# 1. Make `import main` / `import screening` resolve the way the app does.
for _p in (_REPO_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 2. Mark the process as a test run BEFORE app.keys is imported, so it
#    generates an ephemeral random key rather than demanding a real one.
os.environ["TESTING"] = "1"

# 3. Pin a throwaway database. Explicitly overrides any DATABASE_URL that may
#    be sitting in the developer's real .env -- load_dotenv() in main.py will
#    not overwrite a variable that is already set.
_TMP_DB = os.path.join(tempfile.gettempdir(), "sih26188_pytest.db")
for _suffix in ("", "-wal", "-shm"):
    _p = _TMP_DB + _suffix
    if os.path.exists(_p):
        try:
            os.remove(_p)
        except OSError:
            pass
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"


def _cleanup():
    for _suffix in ("", "-wal", "-shm"):
        _p = _TMP_DB + _suffix
        try:
            if os.path.exists(_p):
                os.remove(_p)
        except OSError:
            pass


atexit.register(_cleanup)

# 4. Deterministic, obviously-fake credentials for anything that would
#    otherwise dial out during a test.
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
os.environ.setdefault("SUPER_ADMINS", "test-superadmin@example.com")
os.environ.setdefault("ALLOWED_DOMAINS", "")
os.environ.setdefault("ALLOWED_EMAILS", "")
# Never let a developer's real .env turn a unit test into a billed API call.
for _var in (
    "GEMINI_API_KEY",
    "GEMINI_KEY",
    "LITELLM_URL",
    "LITELLM_API_KEY",
    "AI_DETECTOR_KEY",
    "GITHUB_TOKEN",
    "ML_SERVICE_URL",
    "FACE_EMBED_MODEL",
):
    os.environ.pop(_var, None)

# Keep the SQLite writer lock tight rather than waiting 15s per contended
# write, so the suite stays fast.
os.environ.setdefault("KEEPALIVE_INTERVAL", "0")
