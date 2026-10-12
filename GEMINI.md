# AGENTS.md — read this first (Antigravity / Gemini / any coding agent)

Project: NO-CAP (SIH26188), identity-document screening for border officers. A human officer always decides.

## If the owner says "get back to work" (or "resume" / "continue")
1. Run: `python scripts/agent_ctl.py resume`
2. Do exactly the `NEXT ACTION` it prints. Nothing else first.
3. Read only the current phase: `python scripts/agent_ctl.py section "<phase>"`. Pick skills with `python scripts/skill_router.py "<task>"` and read only what it prints.
4. A task is finished only by `python scripts/agent_ctl.py done <ID>` (it runs the verify command and refuses if it fails).
5. After each task: commit with message `[<ID>] ...`, then `python scripts/agent_ctl.py checkpoint "<what is done, what is next>"`.
6. Do not re-read the whole `docs/WORK_ORDER_V8.md`. Do not narrate. Do not ask the owner anything; blocked items go to `docs/OWNER_TODO.md`.

## Always
- Branch `ml/patch-v8`. Never touch `main`, never force-push, never rewrite history.
- Never print or store a secret, not even a prefix. Never commit `pics/`, images, weights, `.env`.
- Never edit a test, gate, threshold or manifest to get a pass. A failed gate is FAIL.
- Invariant FS: no fallback, failure or low confidence may ever produce an automatic CLEAR/PASS.
- Numbers in documents come from `eval/runs/**/*.json` through scripts, never typed by hand.
