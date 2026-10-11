name: git-hygiene
triggers: git, commit, branch, push, diff, hygiene, gitignore, tracked, weights, history
- `git status` before every commit; `git diff -- <file>` after every edit; full pytest green before commit.
- Commit per task group; message lists finding ids. Push the work branch only. Never touch main, never force-push, never rewrite history.
- Never commit data, images, weights (`.onnx`, `.pth`), tokens, `.env`, `pics/`, `eval/local/`.
- Run `scripts/check_repo_hygiene.py` (if present) before every push.
