name: code-sweep
triggers: ruff, flake8, mypy, bandit, lint, dead code, compileall, npm, tsc, type check, static analysis, refactor
- Run what the repo already configures first (`pyproject.toml`, `setup.cfg`, `.flake8`, `package.json` scripts). Verify tools with `Get-Command` / `pip show`.
- `python -m compileall -q app ml_service api scripts` ; `bandit -r app ml_service api -q` if installed; frontend: `npm run build`, lint script, `npx tsc --noEmit` if configured.
- Fix real defects only (bugs, unsafe patterns, dead branches that hide errors). No mass reformatting, no renames, no refactors beyond the fix. Each fix = one commit-sized change with a test.
- Triage output: real / false positive (with reason) / deferred (OWNER_TODO). Never silence a warning to pass.
