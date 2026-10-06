"""
tests/test_repo_hygiene.py — Test automated enforcement of repository hygiene.
"""

from scripts.check_repo_hygiene import check_hygiene


def test_repo_hygiene_clean():
    """Ensure git working tree contains zero forbidden large files, datasets, or weights."""
    violations = check_hygiene()
    assert len(violations) == 0, f"Repository hygiene failed with violations: {violations}"
