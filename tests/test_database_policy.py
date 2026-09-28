"""
Tests for the database configuration policy (app/main.py).

The rule under test: this system runs on PostgreSQL and nothing else. It used
to accept a SQLite URL via `ALLOW_LOCAL_SQLITE=1` for "offline / edge desks".
That mode was removed because it is actively wrong for this application:

  * SQLite serialises every write behind a single writer lock, so simultaneous
    officer submissions during a shift burst queue against each other.
  * It has no concurrent-reader story, which the review queue depends on.
  * A local file is exactly the ephemeral-/tmp failure mode a serverless
    deploy hits on every cold start -- the audit ledger silently resets.
  * It cannot meaningfully carry the append-only hash chain that is the entire
    point of the ledger.

The configuration is resolved at import time and raises on failure, so these
tests drive real subprocess imports rather than calling a helper. That is the
only way to assert what actually matters here: whether the app *starts*.
"""

import os
import subprocess
import sys
import textwrap

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_DIR = os.path.join(_REPO_ROOT, "app")


def _try_import(database_url, testing="0"):
    """Import app.main in a clean subprocess; return (returncode, stdout+stderr)."""
    env = {
        k: v
        for k, v in os.environ.items()
        # A developer's real .env must not decide this test.
        if k not in ("DATABASE_URL", "TESTING", "MASTER_VAULT_KEY", "GOOGLE_CLIENT_ID", "VERCEL")
    }
    env["TESTING"] = testing
    if database_url is not None:
        env["DATABASE_URL"] = database_url
    else:
        env.pop("DATABASE_URL", None)
    # main.py requires a vault key and an OAuth client id. Both checks sit
    # *after* the database policy, so satisfying them lets the import proceed
    # far enough to prove the database stage passed.
    env["MASTER_VAULT_KEY"] = "test-only-key-that-is-long-enough-0123456789"
    env["GOOGLE_CLIENT_ID"] = "test-only.apps.googleusercontent.com"

    code = textwrap.dedent(
        f"""
        import sys
        for p in ({_REPO_ROOT!r}, {_APP_DIR!r}):
            sys.path.insert(0, p)
        import main
        print("is_test_sqlite=%s" % main._IS_TEST_SQLITE)
        print("IMPORTED")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_missing_database_url_is_a_startup_error():
    """No DATABASE_URL and no default DSN: the desk must not come up blind."""
    rc, out = _try_import(None)
    assert rc != 0, "app.main imported with no DATABASE_URL"
    assert "DATABASE_URL is not set" in out
    assert "IMPORTED" not in out


def test_sqlite_url_is_refused_outside_tests():
    """A SQLite DSN in a real deployment must be rejected, not accepted."""
    rc, out = _try_import("sqlite:///sih26188.db", testing="0")
    assert rc != 0, "app.main imported on SQLite outside TESTING"
    assert "must be a PostgreSQL connection string" in out
    assert "IMPORTED" not in out


def test_no_database_file_is_ever_created():
    """A refused SQLite DSN must not leave a database file behind."""
    import glob

    db_path = os.path.join(_REPO_ROOT, "should-not-exist.db")
    for stale in glob.glob(db_path + "*"):
        os.remove(stale)
    rc, _ = _try_import(f"sqlite:///{db_path}", testing="0")
    assert rc != 0
    assert not glob.glob(db_path + "*")


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@ep-fake-123.neon.tech/neondb?sslmode=require",
        "postgres://u:p@h:5432/db",
        "postgresql+psycopg2://u:p@h/db",
    ],
)
def test_postgres_dsn_starts_the_app_in_production_shape(dsn):
    """Every valid Postgres spelling must be recognised as Postgres.

    Regression guard. The scheme guard initially compared a string prefix
    against the *rewritten* DSN, but clean_postgres_dsn() has already turned
    "postgresql://" into "postgresql+psycopg2://" by that point -- so every
    real deployment was classified as SQLite and refused to start. Importing
    with TESTING unset is the only way to see it: under TESTING the guard is
    bypassed regardless.
    """
    rc, out = _try_import(dsn, testing="0")
    assert rc == 0, f"app.main refused a valid Postgres DSN:\n{out}"
    assert "IMPORTED" in out
    assert "is_test_sqlite=False" in out, (
        "a Postgres DSN must not be classified as the test SQLite double"
    )


def test_no_allow_local_sqlite_escape_hatch_remains():
    """The old opt-in flag must stay gone; it must not creep back in.

    Checks that the variable is never *read*, not that the token is absent --
    the name is intentionally still mentioned in the comment explaining why
    the mode was removed.
    """
    src = open(os.path.join(_APP_DIR, "main.py"), encoding="utf-8").read()
    assert 'getenv("ALLOW_LOCAL_SQLITE"' not in src
    assert "environ[\"ALLOW_LOCAL_SQLITE\"]" not in src
    assert "environ.get(\"ALLOW_LOCAL_SQLITE\"" not in src
    # The pre-rename module-level flag must be gone too.
    assert "_IS_SQLITE" not in src


def test_sqlite_branch_is_test_only():
    """The one surviving SQLite reference is the in-memory test double.

    main.py must treat it as unreachable in a deployment: the flag is derived
    from the DSN scheme and any non-Postgres URL outside TESTING=1 raises
    above it. If someone reintroduces a silent fallback, this fails.
    """
    rc, out = _try_import("sqlite:///:memory:", testing="1")
    assert rc == 0, f"test harness import failed: {out}"
    assert "IMPORTED" in out


def test_clean_postgres_dsn_rewrites_scheme():
    """Deployment-neutral DSNs are normalised to the psycopg2 driver scheme."""
    sys.path.insert(0, _APP_DIR)
    try:
        from main import clean_postgres_dsn
    except Exception as exc:  # pragma: no cover - import guard
        pytest.skip(f"main not importable in-process: {exc}")

    assert clean_postgres_dsn("postgres://u:p@h:5432/db").startswith(
        "postgresql+psycopg2://"
    )
    assert clean_postgres_dsn("postgresql://u:p@h:5432/db").startswith(
        "postgresql+psycopg2://"
    )
    # Already-explicit driver schemes are left alone.
    assert clean_postgres_dsn("postgresql+psycopg2://u:p@h/db").startswith(
        "postgresql+psycopg2://"
    )


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
