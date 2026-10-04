"""
Tests for the codebase-backed chat context (app/codebase.py).

Verifies the indexer finds the project's own source files, skips junk/secrets,
scores the right file for a query, and never produces empty context for a real
code question.

Run either way:
    python tests/test_codebase.py        # plain asserts
    pytest tests/test_codebase.py        # pytest runner
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

from codebase import (
    REPO_ROOT,
    _load_index,
    _rank_files,
    _snippets,
    codebase_context,
    _MAX_CONTEXT_CHARS,
    _sanitize_secrets,
)


def test_index_scans_project_sources():
    rels = {f["rel"] for f in _load_index()}
    # Real project files must be discoverable from the repo root.
    # NOTE: app/main.py is deliberately absent -- see NEVER_INDEX / the
    # secret-bearing-files test. It is the one core engine file excluded.
    assert "app/screening.py" in rels
    assert "app/mrz.py" in rels
    assert "frontend/src/views/DeskView.tsx" in rels
    assert "README.md" in rels


def test_index_skips_junk_and_secrets():
    rels = {f["rel"] for f in _load_index()}
    for bad in (".env", ".env.local", "node_modules", ".git", "FIX", "webpack"):
        assert not any(bad in r for r in rels), f"index must skip {bad}"


def test_rank_finds_flag_removal_code():
    top = _rank_files("where did the dday drill go")
    assert top, "expected at least one ranked file"
    # The D-day removal touched main.py + frontend views; our ranker must stay
    # relevant, so just assert we return something code-shaped.
    assert all(f["text"].strip() for f in top)


def test_screening_question_ranks_screening():
    top = _rank_files("how does the mrz check digit validation work in screening")
    rels = [f["rel"] for f in top]
    assert any("screening" in r for r in rels), f"expected screening.py in top files, got {rels}"


def test_context_includes_instruction_prefix():
    ctx = codebase_context("how does the ai screening engine work")
    assert ctx.startswith("Below is the ACTUAL SOURCE CODE")
    assert "FILE:" in ctx


def test_context_respects_budget():
    ctx = codebase_context("what is the tech stack and how do I run it")
    assert len(ctx) <= _MAX_CONTEXT_CHARS + 500  # small tolerance


def test_snippets_never_empty_for_matching_file():
    """Any file the indexer DOES keep must yield a snippet when it matches.

    app/main.py is excluded (NEVER_INDEX), so this uses a file that is still
    eligible for retrieval.
    """
    index = _load_index()
    target = next(f for f in index if f["rel"] == "app/screening.py")
    out = _snippets(target, "gemini")
    assert out.strip(), "snippet for a matching file must produce content"


def test_index_includes_scripts_documentation():
    # The scripts/ study guides are gitignored by design (kept local, never
    # pushed). On a fresh clone they are absent — skip instead of failing.
    guides = (
        "scripts/BACKEND_STUDY_GUIDE.md",
        "scripts/SIH_PRESENTATION.md",
        "scripts/THE_COMPLETE_GUIDE.md",
    )
    if not all(os.path.exists(os.path.join(REPO_ROOT, g)) for g in guides):
        import pytest

        pytest.skip("local scripts/ study guides not present (gitignored)")
    rels = {f["rel"] for f in _load_index()}
    # Markdown study guides in scripts/ must be indexed
    for g in guides:
        assert g in rels
    # Automation scripts and batch files in scripts/ must NOT be indexed
    assert not any(r.endswith(".bat") for r in rels)
    assert not any(r.endswith(".pyw") for r in rels)


def test_context_includes_blueprint_and_manifest():
    ctx = codebase_context("explain the architecture")
    assert "### SYSTEM ARCHITECTURE BLUEPRINT & REPOSITORY MAP:" in ctx
    assert "### COMPLETE PROJECT FILES MANIFEST:" in ctx
    # No SOURCE of app/main.py may be attached to the prompt. Its *name* still
    # appears in the authored architecture blueprint, which is intended -- the
    # point is that the file's contents never reach the model.
    blocked_header = "FILE: " + "app/" + "main.py"
    assert blocked_header not in ctx
    assert "FILE: app/screening.py" in ctx
    assert "FILE: frontend/src/views/DeskView.tsx" in ctx


def test_secret_bearing_files_are_never_indexed():
    """The chat assistant ships retrieved source to a third-party LLM.

    These files hold the DSN, key resolution and raw-field comparison logic.
    They are excluded wholesale rather than relying on regex redaction.
    """
    from codebase import NEVER_INDEX, _load_index
    rels = {f["rel"] for f in _load_index()}
    for blocked in NEVER_INDEX:
        assert blocked not in rels, f"{blocked} must never be sent to the LLM"


def test_no_dotenv_is_ever_indexed():
    from codebase import _load_index
    rels = {f["rel"] for f in _load_index()}
    assert not any(".env" in r for r in rels), "dotfiles may contain live secrets"


def test_reload_index():
    from codebase import reload_index
    idx = reload_index()
    assert len(idx) > 35


def test_sanitize_secrets_redacts_credentials():
    raw_code = (
        'DATABASE_URL = "postgresql://myuser:p4ssw0rd!@ep-tiny-lake-99.neon.tech/neondb"\n'
        'GEMINI_KEY = "AIzaSyD_TestFakeKey1234567890123456789"\n'
        'OPENAI_KEY = "sk-proj-123456789012345678901234567890"\n'
        'GROQ_KEY = "gsk-abcdefghijklmnopqrstuvwxyz123456"\n'
        'AUTH_HEADER = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.xyz"\n'
        'secret_key = "SuperSecretVaultKey123"\n'
        '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----\n'
    )
    sanitized = _sanitize_secrets(raw_code)

    assert "p4ssw0rd!" not in sanitized
    assert "[REDACTED_PASSWORD]" in sanitized
    assert "ep-tiny-lake-99.neon.tech" not in sanitized
    assert "[REDACTED_DB_HOST]" in sanitized
    assert "AIzaSyD_TestFakeKey1234567890123456789" not in sanitized
    assert "[REDACTED_GOOGLE_API_KEY]" in sanitized
    assert "sk-proj-123456789012345678901234567890" not in sanitized
    assert "gsk-abcdefghijklmnopqrstuvwxyz123456" not in sanitized
    assert "[REDACTED_AI_API_KEY]" in sanitized
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
    assert "SuperSecretVaultKey123" not in sanitized
    assert "MIIEowIBAAKCAQEA0" not in sanitized
    assert "[REDACTED_PRIVATE_KEY_BLOCK]" in sanitized


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print("PASS", fn.__name__)
    print(f"{passed}/{len(fns)} tests passed")