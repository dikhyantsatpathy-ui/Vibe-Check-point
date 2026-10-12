# NO-CAP (SIH26188) — WORK ORDER v8 (patch, test, document, resumable)

You are the executing engineer on this repo (NO-CAP "Vibe-Check-point": decision-support screening of identity documents for border officers; a human officer always decides). This file is **self-contained**. It lives in the repo as `docs/WORK_ORDER_V8.md` (the owner puts it there; if it is missing, ask nobody: search `Get-ChildItem -Recurse -Filter "WORK_ORDER_V8*"`).

Earlier work orders (v3–v7) already ran. A review of the result found real progress and real defects. This order **patches the defects, adds what is missing, adds tests, rewrites the blueprint, and makes the whole process resumable.** The owner is away and will not answer. Never wait, never ask permission. Anything only the owner can do goes to `docs/OWNER_TODO.md` as BLOCKED with the exact PowerShell command; then continue with the next task.

---

## 0. HOW TO START, STOP AND RESUME (read first, every session)

The owner may stop you at any moment and later type only **"get back to work"** (or "resume", "continue"). That phrase means exactly this:
1. Run `python scripts/agent_ctl.py resume`. (If `scripts/agent_ctl.py` is missing: this is a first run, do task R1 below, then run it.)
2. Do the `NEXT ACTION` it prints. Nothing else first.
3. Never re-read this whole file. Read only the current phase with `python scripts/agent_ctl.py section "<phase name>"`, plus the skills the router returns (§1.9).
4. A task is finished **only** by `python scripts/agent_ctl.py done <ID>`; that command runs the task's verify command and refuses to mark DONE if it fails. You cannot declare a task done by writing it in a document.
5. Before each task: `agent_ctl.py start <ID>`. After each task: `git add` / commit (message starts `[<ID>]`), then `agent_ctl.py checkpoint "<one line: what is done, what is next>"`.
6. The state lives in files, never in your memory: `docs/QUEUE.json` (tasks), `docs/AGENT_STATE.json` (session, checkpoint), `docs/JOURNAL.jsonl` (append-only log), git history, `docs/DECISIONS.md`, `docs/OWNER_TODO.md`. Edit them only through `agent_ctl.py` (QUEUE/STATE/JOURNAL) so they cannot be corrupted.
7. Details for odd situations (stopped mid-edit, mid-training, lost state): Appendix B.

---

## 1. CONTROL LAYER

**1.1 Loop per task:** `start` → `READ` (only what the task needs) → `ROUTE` (skill router) → `TEST FIRST` (for a bug fix, write the test and run it on the old code; it must FAIL; record that) → `ACT` (smallest change) → `VERIFY` (`agent_ctl.py done`) → `ADVERSARY` (3 ways it could be wrong or break something; test each cheaply) → commit → `checkpoint`.
**1.2 Receipts.** Every "I fixed / ran / verified X" needs the command and its real output, or `git diff --stat` plus the hunk. No receipt → write `UNVERIFIED`. After EVERY edit: `git diff -- <file>`; after every Python edit: `python -m py_compile <file>`.
**1.3 Anti-cheat (breaking any = task FAILED):** never edit a test's expected value, a gate, a threshold, an eval manifest or a test set to get a pass (if a test is wrong: finding + separate `test-fix` commit quoting the old assertion). Never add `skip`, `xfail`, `# noqa`, `# type: ignore`, `try/except: pass`, `--no-verify`. Never delete tests, reports, data or files (candidates go to OWNER_TODO). Never type a metric into a document: numbers come from `eval/runs/**/*.json` through scripts. A failed gate is **FAIL**. Verdict words only: `PASS`, `FAIL`, `UNMEASURED`, `INDICATIVE ONLY (n<30)`, `UNVERIFIABLE`. Banned unless a command/JSON proves them in the same evidence block: "solved", "production-ready", "ready for release", "bulletproof", "verified" (only VERIFIED inside the claims ledger), "zero risk", "100% secure", "perfect". Never invent file names, APIs, arguments, URLs, model names, library behaviour or numbers: list files with `Get-ChildItem`, learn APIs with `pip show` / `inspect.signature` / reading installed source, otherwise write `UNVERIFIED`.
**1.4 Output discipline (the owner pays per token).** No narration, no restating rules, no apologies, no "shall I proceed?". Write only: evidence blocks, queue/state updates, findings, OWNER_TODO lines, the final report. Do not re-view a file range twice; use `Select-String`; batch commands; do not open whole files over 400 lines.
**1.5 Long jobs (> 2 min): never poll.** Launch once with `Start-Process python -ArgumentList "-m","<module>","<args>" -RedirectStandardOutput <run>\job.log -RedirectStandardError <run>\job.err -PassThru -WindowStyle Hidden`, write the PID to `<run>\pid.txt`, then ONE `Wait-Process -Id <pid> -Timeout 1500`; afterwards read only `Get-Content <run>\job.log -Tail 5` and look for `DONE.json` / `FAILED.txt`. At most one check per 25–30 minutes. Every long script writes `DONE.json` (`{"task","finished_utc","command","seed","output_files":[{"path","bytes","sha256"}],"metrics":{}}`) or `FAILED.txt` (command, exit code, last 60 stderr lines). Training: ≤ 30 epochs, patience 7, ≤ 4 h, ≤ 2 attempts, one GPU job at a time.
**1.6 Two-strike rule.** Same command fails twice with the same error → `agent_ctl.py block <ID> --reason ...`, move on. A tool timeout counts as a failure. No retry loops.
**1.7 Secrets and privacy.** Secrets only from environment variables or a library's own login cache; never in any file, log, report or terminal output; **never print an env var value** (names only, or the first 8 hex chars of its SHA-256 when comparing). A Hugging Face token was once pasted in chat: treat as compromised, never use or search for it. Documents must never contain even a **prefix** of a credential. The folder `pics/` holds the owner's private unlabeled images (possibly real people/real IDs): never commit, upload, describe, or put file names of them into tracked files; originals are read-only; outputs only in git-ignored `eval/local/`; tracked reports get aggregates only. Fixtures are synthetic ("TEST USER", fake numbers, "SPECIMEN").
**1.8 Git.** Branch `ml/patch-v8`, created from `ml/blueprint-sync-v7` (if v7 branch is missing: from the newest of `ml/hardening-v5`, `ml/detector-v3`; check `git branch -a`). On resume use the existing branch. Commit after each task, push after each phase. **Never touch `main`, never force-push, never rewrite history.** Full `python -m pytest -q` green before every push.
**1.9 Skill router (do not read skills one by one).** At the start of every task run `python scripts/skill_router.py "<one-line task>"`; read ONLY the (≤ 2) files it prints; `NONE` means read no skill. Skills are checklists; this file wins on conflict.
**1.10 Hard constraints.** No DB schema/migration changes. Do not touch OCR engines, risk-score weight constants, or any production threshold **except the face thresholds, only as specified in P1–P3**. Root `requirements.txt` gets no `torch`, `rfdetr`, `onnxruntime`, `opencv`, `pycocotools`, `ultralytics`. Zero-raw-storage of uploads stays. API responses stay backward compatible (add fields only; the one exception is P3, a deliberate safety change). **No default backend is flipped** (`DETECTOR_BACKEND`, `CARD_DETECTOR_BACKEND`, `FIELD_DETECTOR_BACKEND` stay as they are).
**1.11 Invariant FS.** No failure, timeout, missing model, degraded mode, fallback algorithm, parse error, low confidence or missing evidence may ever produce an automatic CLEAR/PASS. Every such path yields REVIEW or REJECT-with-reason. **Invariant AUTH:** unauthenticated/unauthorised requests fail closed (401/403).
**1.12 Working alone.** Ambiguity → do not ask: choose the option that (1) keeps both invariants, (2) is reversible, (3) has the smallest blast radius, (4) is more conservative; log it in `docs/DECISIONS.md` (date, options, choice, reason); continue.
**1.13 Scope.** No drive-by refactors, no mass reformatting, no renames, no splitting of large files (recommend in OWNER_TODO). Every behaviour change ships with a test that failed on the old code.
**1.14 PowerShell.** No `&&` in PowerShell (use `;`); never end a quoted path with a backslash; `python -m ...`; `pathlib`; `$env:PYTHONUTF8=1`; `Get-Command <tool>` before using one; guard entry points with `if __name__ == "__main__":`. Verify commands in the queue run through `cmd`/shell, so keep them simple (`python -m pytest ...`).

---

## 2. PHASE R — RESUME SYSTEM (do first)

R1 Create `scripts/agent_ctl.py` byte for byte from Appendix C (unless it exists and `python scripts/agent_ctl.py selftest` passes). Create `AGENTS.md` and `GEMINI.md` byte for byte from Appendix D. Run `python scripts/agent_ctl.py init`.
R2 `tests/test_v8_resume.py`: in a temp copy of the repo skeleton (temp dir with `scripts/agent_ctl.py`, `docs/WORK_ORDER_V8.md` containing a small `queue` block, `git init`), assert: `init` builds the queue and a second `init` keeps statuses; `done` on a task whose verify exits 3 leaves it DOING and exits 1; `done` on a passing task marks DONE; a manual task (`-`) needs `--evidence`; `resume` after a simulated crash (task left DOING) prints `NEXT ACTION` mentioning that task; `reconcile` marks passing TODO tasks DONE after QUEUE.json is deleted; `section` prints exactly one section; the Windows branch of `pid_alive` never calls `os.kill` (read the source). Also `-k agents_files`: `AGENTS.md` and `GEMINI.md` exist and contain the phrase `get back to work` and `agent_ctl.py resume`.
R3 Windows check (cannot be tested on Linux): start a short job with `Start-Process python -ArgumentList "-c","import time;time.sleep(60)"`, write its PID to `eval/runs/_ctl_test/pid.txt`, run `python scripts/agent_ctl.py resume`, confirm it reports `RUNNING`, then end that process with `Stop-Process -Id <pid>` and remove only that test folder you created. Record the output.

---

## 3. PHASE P — PATCHES (defects found by the review)

For each patch: write the test first (file names below), run it on the old code (must fail), patch, run again. Skills: `face-embedding`, `fastapi-hardening`, `secret-scan`, per router.

**P1 One face-threshold policy (replaces three inconsistent ones).** Today: `app/face.py` relaxes 0.60 → 0.52 for photos older than 5 years (the owner's original "Feature 3"); `ml_service/face_match.py` adds a second sliding formula (0.015/year, floor 0.48, cap 0.12), plus an unused third function `get_age_aware_threshold` (cap 0.15, floor 0.50), plus a perceptual-hash relaxation up to 12. Create `app/face_policy.py` and a **byte-identical** copy `ml_service/face_policy.py` (pure Python, no heavy imports): constants `BASE_SAME = 0.60` (env `FACE_EMBED_SAME`), `AGED_PHOTO_YEARS = 5.0`, `AGED_SAME = 0.52` (env `FACE_EMBED_SAME_AGED`), `DIFF = 0.40`; env overrides are accepted only if `0.30 <= AGED_SAME <= BASE_SAME <= 0.90`, otherwise the defaults are used and a warning is logged. One function `effective_threshold(photo_age_years)` (aged → `AGED_SAME`, else `BASE_SAME`, unknown age → `BASE_SAME`). Make `app/face.py`, `app/face_match.py`, `ml_service/face_match.py` use it; remove the sliding formulas and `get_age_aware_threshold` (edit the code; do not delete files). Log the decision in DECISIONS.md ("single step policy = owner's original Feature 3; sliding relaxations removed because no impostor measurement supports them"). Tests `tests/test_v8_face_policy.py -k policy`: step behaviour at 4.9 / 5.0 / 5.1 years; invalid env → defaults; the two copies are byte-identical; no other function in `app/` or `ml_service/` computes a face threshold (grep-based test).
**P2 A relaxed-threshold match can never auto-PASS.** In `app/face.py` the verdict `PASS` requires mode `arcface` AND decision `MATCH` AND `similarity >= BASE_SAME`. A MATCH that exists only because of the aged threshold (`AGED_SAME <= similarity < BASE_SAME`) becomes verdict `REVIEW` with the signal "Aged-photo match at relaxed threshold — officer to confirm". Tests `-k cap`: similarity 0.55 with an old photo → REVIEW; 0.61 → PASS; 0.55 with a young photo → INCONCLUSIVE/REVIEW (never PASS).
**P3 Fallback methods never decide.** For any mode other than `arcface` (perceptual hash, unavailable): decision is `INCONCLUSIVE` always; verdict is `REVIEW` always (today a hash "mismatch" produces `FAIL`, which is overconfident in the other direction); the legacy field `match` is `None` (today it can be `True` for near-duplicate hashes); the perceptual-hash threshold is constant (no age relaxation). Update tests that asserted the old legacy values in a separate `test-fix` commit and record each changed assertion in the findings register. Tests `-k fallback`.
**P4 Face-model provisioning.** Today `ml_service/face_match.py` auto-downloads `w600k_r50.onnx` by default from a third-party Hugging Face account using `urllib` with a spoofed browser User-Agent, no timeout, no size cap, and setting `FACE_MODEL_SHA256` to an empty string disables verification. Fix: (a) `AUTO_DOWNLOAD_MODELS` default becomes **false** (truthy parse unchanged); (b) delete the `urllib` download code path; model files are obtained only through `ml_service/model_fetch.py` from the configured private `HF_MODEL_REPO` (read its real signature first); (c) add `ml_service/models/MODEL_MANIFEST.json` with, per model, `name`, `sha256`, `bytes`, `source_repo`, `revision`, `origin_hint` (text only, never fetched; for the face model write the current third-party URL as a hint and the licence heads-up); the pinned SHA-256 for the face model is the existing `DEFAULT_FACE_SHA256` constant; (d) an empty or missing SHA means **refuse to load**, an `FACE_MODEL_SHA256` override that is empty is treated as "use the manifest value"; (e) timeouts and a size cap of 1.05 × manifest bytes on any fetch; (f) a missing/unverifiable face model means face mode `unavailable` (INCONCLUSIVE → REVIEW), and `OWNER_TODO.md` gets the exact steps to upload the file to the private repo (`huggingface-cli upload` with the signature verified from `--help`) and set `HF_MODEL_REPO`. No network call may happen when the flag is off. Tests `-k provisioning` with monkeypatched network functions (assert zero calls when off; mismatching SHA refuses; empty SHA refuses; oversize refuses).
**P5 Face metadata and health.** `ml_service/models/face_embed.meta.json` generated by script from the real ONNX when present (input name/shape, output size, SHA-256, bytes, preprocessing text taken from the code actually used, `preprocessing_verified: false` until A1 proves it); `/ml/health` and the screening response show `face_match.mode`, `loaded`, `model_sha256_prefix`, `auto_download`. Tests `-k health`.
**P6 Liveness is not wired.** `evaluate_liveness_frames` takes client-style values (eye-aspect ratio etc.). Add a docstring warning that inputs must be computed server-side, and a test `-k liveness` that no route in `app/main.py` or `ml_service/main.py` references it. Blueprint wording: "not integrated".
**P7 Readiness table without hand-typed numbers.** `docs/SWITCH_READINESS.md` currently lists face biometrics as "SHIP (PASS)" with 98.4 % / 99.1 %, "MobileFaceNet" and `arcface.onnx`; no script, dataset or file supports it (the code uses `w600k_r50.onnx`). Create `docs/readiness_rows.json` (one entry per row: name, evidence JSON path, metric key, threshold, comparator) and `scripts/render_switch_readiness.py` that renders the table; any row whose evidence file or key is missing is **UNMEASURED**. The face row evidence is `eval/runs/*_face_proxy/report.json` (A1); until it exists the row is UNMEASURED with no accuracy figure. Tests `-k readiness`: every PASS row has an existing evidence file containing its metric key; the strings `98.4` and `99.1` appear nowhere under `docs/` or the blueprint.
**P8 Honest CSP.** Today the same policy is sent as both `Content-Security-Policy` and `Content-Security-Policy-Report-Only`, and `script-src` contains `'unsafe-inline'`, so the "strict CSP" claim is false. Fix: keep the current policy as the **enforced** baseline (documented as "baseline: script-src allows unsafe-inline"); send a **stricter** policy as Report-Only (no `unsafe-inline` in `script-src`; `'sha256-…'` hashes of every inline `<script>` in the served static HTML, computed at startup and recomputed when the file's mtime changes; no `unsafe-eval`). If the static HTML contains inline event handlers (`onclick=` etc.) or `javascript:` URLs, list them in `docs/CSP_NOTES.md` (they block hash-based enforcement). Env `CSP_STRICT_ENFORCE=1` switches the enforced policy to the strict one (default off, because nobody has checked the UI in a browser). OWNER_TODO: open the site with DevTools console, look for CSP violation messages, then set the flag. Tests `tests/test_v8_csp.py`: enforced header and Report-Only header differ; Report-Only has no `unsafe-inline` in `script-src`; hashes match the actual inline scripts; with the flag on the enforced header has no `unsafe-inline` in `script-src`; no header contains `unsafe-eval`.
**P9 No credential prefixes in documents.** `docs/OWNER_TODO.md` contains the start of a Roboflow key. Edit it to "Roboflow API key (value not recorded)". Extend `scripts/audit_secrets_s1.py` (and its test) to flag the pattern "short lowercase prefix + underscore + ≥ 6 key characters + ellipsis" and the string `pcsk_`; tests `tests/test_v8_docs_hygiene.py -k secrets` scan every tracked `*.md`, `*.json`, `*.txt` under `docs/`, `eval/` and the repo root for credential-looking strings and prefixes.
**P10 Fake secrets used as test inputs** (`scripts/reverify_logs_v4.py`) must be unmistakably fake (`FAKE-TOKEN-NOT-REAL…`) so scanners do not need an allow-list; keep the redaction behaviour under test by using the redactor's own documented patterns. `-k fake`.
**P11 One source for test counts.** `scripts/count_tests.py` runs `python -m pytest --collect-only -q` and writes `eval/runs/<ts>_tests/count.json` (`total`, `per_file`). The blueprint and the claims ledger read it (the old claim "305 tests" is false; the current count is whatever the collector prints).
**P12 Coverage ratchet.** Add `scripts/check_coverage.py` reading a `coverage json` report and `docs/coverage_thresholds.json` (module → minimum percent; initial values = currently measured values rounded down; target 85 documented). CI runs `pytest --cov=app --cov=ml_service --cov-report=json` then the checker. Add a real coverage-gated check; keep `tests/test_coverage_stability_t7.py` but add a docstring line "non-gating smoke test; the coverage gate is scripts/check_coverage.py" (it only loops five times and writes a file). `-k coverage_ci` checks the workflow file contains both commands.
**P13 Owner isolation script.** Write `scripts/owner_check_isolation.ps1` that the OWNER runs (the agent cannot): for the production and test Vercel projects it pulls environment values into temporary files (read `vercel env pull --help` and `vercel link --help` first; do not guess flags), computes the first 8 hex characters of the SHA-256 of each of `DATABASE_URL`, the vault/master key variable name used by the code, the OAuth client id, the OAuth client secret, `ML_SERVICE_SECRET`/`ML_SECRET_KEY`, `HF_TOKEN`, prints only `NAME: SAME|DIFFERENT|MISSING`, never a value, and deletes the temporary files. Variable names come from `.env.example` and the code (verify with `Select-String`). `-k owner_script` only checks the file exists, contains no `Write-Host` of a raw value, and lists those names. F-13/F-14 stay BLOCKED for the owner.

---

## 4. PHASE A — ADDITIONS

**A1 Face proxy evaluation.** `eval/eval_face_proxy.py`: when the face model is present and `pics/` exists: face-detection hit rate; embedding norm (= 1 ± 1e-3), determinism, self-similarity ≥ 0.999; robustness distribution under JPEG q30 / blur / brightness ±40 % / rotation ±10° / downscale ×0.5; impostor-pair similarity quantiles between different images and the false-accept rate at `BASE_SAME` and `AGED_SAME`, **reporting possible same-person pairs separately (never silently dropping them)**; preprocessing variants (RGB vs BGR, (x−127.5)/128 vs x/255, aligned vs unaligned) with their genuine/impostor separation, and which variant the code uses. Output `eval/runs/<ts>_face_proxy/report.json` with `label: "PROXY (no identity labels)"`, aggregates only. `--selftest` runs the metric code on synthetic embeddings (no model, no `pics`) and is the task's verify command. Model missing → BLOCKED with the exact owner step, not a failure of the task's code.
**A2 Release verdict by code.** `scripts/release_verdict.py` prints and (with `--write PATH`) writes the final report. Inputs: `docs/QUEUE.json`, the newest `eval/runs/*_claims/report.json`, the findings table in the newest `docs/AUDIT_V*.md` (rows `| F-xx | S1..S4 | … | OPEN/FIXED/ACCEPTED-RISK/BLOCKED | … |`), `docs/readiness_rows.json` results, the newest `eval/runs/*_tests/count.json` and suite result file. **GO only if:** no FALSE claim; no OPEN S1/S2; no readiness row FAIL; no BLOCKED task whose phase is `P`/`T`/`K` unless it is flagged `owner`; suite green three times (A3). Otherwise NO-GO with the exact reasons. The words "ready" / "release" appear in the report only next to a GO verdict. Tests `tests/test_v8_release_verdict.py` with synthetic inputs for GO and for each NO-GO reason.
**A3 Three-run stability.** `scripts/run_suite_n.py N` runs the full suite N times, stops on the first failure, writes `eval/runs/<ts>_suite/result.json` (`runs`, `passed`, `failed`, `durations`, `flaky_candidates`).
**A4 Skills.** Apply Appendix E (three new skill files; one edited).

---

## 5. PHASE T — TESTS

Dev-only tools are installed by CI (`pytest`, `pytest-cov`, `coverage`, `ruff`); no new runtime dependency. Every P-task test file is named above. Additional required tests:
T1 `tests/test_v8_invariants.py`: end-to-end Invariant FS with the face stage in every state: model missing, SHA mismatch, corrupt model, ML service timeout, garbage JSON, mode `fallback`, mode `unavailable` → the screening outcome is never an automatic CLEAR and `face_match.mode` is truthful.
T2 `tests/test_v8_merkle.py`: independent recomputation of the ledger Merkle root with your own `hashlib` implementation over fixed leaves (even count, odd count, single leaf, empty) equals `compute_merkle_root` in `app/session.py`; tampering with any leaf changes the root. If they differ → finding, fix code or correct the blueprint to "hash chain" (decide by evidence).
T3 `tests/test_v8_docs_hygiene.py`: blueprint contains no unresolved `{{…}}`; the claims ledger has 0 FALSE; the required blueprint sections of §6 exist; skills router returns the right skill for six sample tasks and `NONE` for an unrelated task; `docs/WORK_ORDER_V8.md`'s queue block parses to the same task ids as `docs/QUEUE.json`.
T4 Full suite three times: `python scripts/run_suite_n.py 3`.
T5 `python -m compileall -q app ml_service api scripts` clean; `ruff check` with the repo's own configuration if present (no new config); real findings are fixed with tests, false positives are logged in DECISIONS.md.

---

## 6. PHASE K — BLUEPRINT AND CLAUDE HANDOFF

**K1 Claims ledger back to zero FALSE.** Re-run `scripts/verify_blueprint_claims.py` (make it exit non-zero when any FALSE claim exists). Currently FALSE: C-05 ArcFace 512-D matching, C-06 test count 305, C-08 card detector "accepted" with 0.63 % FP. For each: fix the code if small and safe, otherwise correct the document. C-08: reproduce on the frozen card manifest (if `eval/manifests/card_v7.json` or the newest card manifest exists; otherwise UNVERIFIABLE with owner action) and state the production default per stage read from code/env.
**K2 Template and renderer.** The blueprint source is the newest `SIH26188_ENGINEERING_BLUEPRINT.md` (repo root; also check for a newer copy anywhere under the repo by `LastWriteTime`). Create `docs/blueprint_template.md` = that blueprint with every measured number replaced by `{{metric:<json path>:<key>}}` (test totals and per-file counts from `count.json`, model sizes and SHA-256 prefixes from `MODEL_MANIFEST.json`, latencies and metrics from `eval/runs/**`). `scripts/render_blueprint.py` renders to `SIH26188_ENGINEERING_BLUEPRINT.md` at the repo root, exits non-zero on any unresolved placeholder, and has `--check` (render in memory and compare to the file on disk). Required corrections, each backed by the claims ledger:
  - §8.1/§30 demo pass: an **opt-in demo feature** (`DEMO_PASS_ENABLED`, default off, evaluator cannot create notices or watchlist entries); say the jury deployment must set it and real deployments must not.
  - §9: one consistent test count (placeholder); CSP row: "enforced baseline (script-src allows unsafe-inline) + stricter Report-Only policy; strict enforcement behind `CSP_STRICT_ENFORCE`, UI not browser-verified".
  - Face section: "ArcFace-style 512-D embedding when the model is present and SHA-verified; otherwise face matching is INCONCLUSIVE and routes to REVIEW; perceptual hash is a coarse fallback and never decides; aged photos use one step threshold and can never auto-PASS; accuracy UNMEASURED (proxy only); liveness not integrated."
  - Merkle: per T2's result. SSRF allow-listing: only if `is_allowed_ml_url` exists and is tested; otherwise correct.
  - §21.1 supply chain: dated results with tool versions from JSON (or "UNVERIFIABLE: network blocked").
  - Rule naming: "Rule 12" becomes Invariant FS and Invariant AUTH, described separately.
  - Checklist (§31): `[x]` only for claims the ledger marks VERIFIED; otherwise `[ ]` with the reason; no "ACCEPTED" for a model whose gate failed.
  - New section **"Known limitations and NOT MEASURED"**: real Indian-card accuracy, real forgeries, real screen replays, field detection for PAN/voter/DL/Nagarikta/Bhutanese (rules + OCR), face-matching accuracy (proxy only), MIDV mock-document limits, legal admissibility (needs counsel; the system produces a certificate and a tamper-evident chain; it does not decide admissibility).
  - New section **"Resuming work and verifying this document"**: how `agent_ctl.py`, `QUEUE.json`, `AGENTS.md` work and how to regenerate the blueprint.
  - No adjectives for results; tables only; no legal-compliance claims ("designed with reference to …; legal review pending").
**K3 Claude handoff.** `scripts/render_handoff.py` writes `docs/CLAUDE_HANDOFF.md` (with `--check`). Contents: (1) the static narrative in Appendix F, copied verbatim; (2) a generated **facts block**: branch, last commit, queue counts, ledger counts, readiness table, env var names (never values), model manifest (names, bytes, SHA-256 prefixes), test count, the last 20 journal lines, open findings (S1/S2 first), OWNER_TODO headings; (3) **"Audit this repo in 10 commands"** (real commands, verified to run); (4) **"Upload these files to a fresh Claude chat"**: the blueprint, `docs/CLAUDE_HANDOFF.md`, `docs/QUEUE.json`, the newest `docs/AUDIT_V*.md`, the newest claims report, `docs/SWITCH_READINESS.md`; the zip of the repo only if asked.
**K4** Run `python scripts/render_blueprint.py --check` and `python scripts/render_handoff.py --check`; docs hygiene tests green.

---

## 7. PHASE G — VERDICT AND CLOSE-OUT

G1 `python scripts/release_verdict.py --write docs/FINAL_REPORT_DRAFT.md` (overwrites the earlier "READY FOR RELEASE" draft; never hand-edit the verdict).
G2 Commit, push `ml/patch-v8` only, `agent_ctl.py checkpoint "v8 complete"`.
G3 Final message to the owner: the verdict and reasons, what is BLOCKED for the owner (exact commands from OWNER_TODO), the three most important residual risks, and Appendix G questions, in one message.

---

## 8. QUEUE (machine-read by `agent_ctl.py init`; do not edit the format)

```queue
R1 | R | Install agent_ctl.py, AGENTS.md, GEMINI.md and init the queue | python scripts/agent_ctl.py selftest
R2 | R | Resume-system tests | python -m pytest tests/test_v8_resume.py -q
R3 | R | Windows PID check recorded | -
P1 | P | Single face-threshold policy | python -m pytest tests/test_v8_face_policy.py -q -k policy
P2 | P | Relaxed match never auto-PASS | python -m pytest tests/test_v8_face_policy.py -q -k cap
P3 | P | Fallback never decides | python -m pytest tests/test_v8_face_policy.py -q -k fallback
P4 | P | Face-model provisioning hardened | python -m pytest tests/test_v8_face_policy.py -q -k provisioning
P5 | P | Face metadata and health fields | python -m pytest tests/test_v8_face_policy.py -q -k health
P6 | P | Liveness not routed | python -m pytest tests/test_v8_face_policy.py -q -k liveness
P7 | P | Readiness table from evidence only | python -m pytest tests/test_v8_docs_hygiene.py -q -k readiness
P8 | P | Honest CSP | python -m pytest tests/test_v8_csp.py -q
P9 | P | No credential prefixes in docs | python -m pytest tests/test_v8_docs_hygiene.py -q -k secrets
P10 | P | Unmistakably fake test secrets | python -m pytest tests/test_v8_docs_hygiene.py -q -k fake
P11 | P | Single source for test counts | python scripts/count_tests.py
P12 | P | Coverage ratchet and CI step | python -m pytest tests/test_v8_docs_hygiene.py -q -k coverage_ci
P13 | P | Owner isolation script | python -m pytest tests/test_v8_docs_hygiene.py -q -k owner_script
A1 | A | Face proxy evaluation script | python -m eval.eval_face_proxy --selftest
A2 | A | Release verdict script | python -m pytest tests/test_v8_release_verdict.py -q
A3 | A | Three-run stability script | python scripts/run_suite_n.py 1
A4 | A | Skills updated | python -m pytest tests/test_v8_docs_hygiene.py -q -k skills
T1 | T | Invariant FS with face states | python -m pytest tests/test_v8_invariants.py -q
T2 | T | Merkle root independent check | python -m pytest tests/test_v8_merkle.py -q
T3 | T | Docs hygiene tests | python -m pytest tests/test_v8_docs_hygiene.py -q
T4 | T | Full suite three times | python scripts/run_suite_n.py 3
T5 | T | Static checks | python -m compileall -q app ml_service api scripts
K1 | K | Claims ledger has no FALSE claim | python scripts/verify_blueprint_claims.py
K2 | K | Blueprint template and renderer | python scripts/render_blueprint.py --check
K3 | K | Claude handoff document | python scripts/render_handoff.py --check
K4 | K | Docs hygiene final | python -m pytest tests/test_v8_docs_hygiene.py -q
G1 | G | Release verdict written by code | python scripts/release_verdict.py --write docs/FINAL_REPORT_DRAFT.md
G2 | G | Commit and push the branch | -
G3 | G | Final message to the owner | -
```

---

## APPENDICES

### Appendix A — Evidence block (append to `docs/TRAINING_PROGRESS.md`; nothing else)
```
TASK <id> | <UTC time>
SKILLS USED: <router output or NONE>
TEST-FIRST: <test command and its FAIL output on old code, or n/a>
COMMAND: <exact command>
OUTPUT: <first 15 + last 15 lines>
RESULT: PASS | FAIL | BLOCKED (<reason>)
DIFF: <git diff --stat>
ADVERSARY: <3 ways it could be wrong + what you tested>
NEXT: <next task id>
```

### Appendix B — Resume protocol for odd situations
- **Stopped mid-edit** (`resume` shows uncommitted paths and a DOING task): run `git diff --stat`; do NOT discard; commit as `wip(<ID>)`; run `agent_ctl.py done <ID>`: pass → finished; fail → continue the work.
- **Stopped mid-training/long job** (`resume` lists a job): `RUNNING` → one `Wait-Process`, then read `DONE.json`/`FAILED.txt`. `FINISHED` → continue with its outputs. `DIED without DONE/FAILED` → read `job.err` tail; relaunch **once**; resume from the last checkpoint only if the library's resume argument is verified from installed source, otherwise restart; if it dies twice → `block`.
- **State lost or corrupt** (`QUEUE.json` missing/invalid): `agent_ctl.py init` then `agent_ctl.py reconcile` (runs each task's verify command; passing tasks become DONE). `docs/JOURNAL.jsonl` and git history (`git log --oneline`, commits start with `[<ID>]`) show what happened.
- **QUEUE and work order disagree:** `agent_ctl.py init` merges by task id and keeps statuses.
- **A DONE task looks wrong:** `agent_ctl.py recheck --phase <P>` re-runs verify commands and reopens regressions.
- **Two sessions at once:** not supported; if `resume` shows a RUNNING job you did not start, wait for it.

### Appendix C — `scripts/agent_ctl.py` (create byte for byte)

````python
#!/usr/bin/env python
"""Task/state controller so work survives a stopped session.

  python scripts/agent_ctl.py init            # build docs/QUEUE.json from the ```queue block in docs/WORK_ORDER_V8.md (keeps existing statuses)
  python scripts/agent_ctl.py resume          # what to do next after a stop ("get back to work")
  python scripts/agent_ctl.py status|next
  python scripts/agent_ctl.py start ID
  python scripts/agent_ctl.py done ID [--evidence TEXT] [--no-verify] [--timeout SEC]
  python scripts/agent_ctl.py block ID --reason TEXT | fail ID --evidence TEXT
  python scripts/agent_ctl.py checkpoint "note"
  python scripts/agent_ctl.py recheck [--phase P]   # re-run verify commands of DONE tasks
  python scripts/agent_ctl.py reconcile [--phase P] # if state was lost: run verify of TODO tasks, mark the passing ones DONE
  python scripts/agent_ctl.py section NAME    # print one "## ..." section of the work order
  python scripts/agent_ctl.py selftest
`done` only succeeds when the task's verify command exits 0 (receipt enforced by code).
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
QUEUE = DOCS / "QUEUE.json"
STATE = DOCS / "AGENT_STATE.json"
JOURNAL = DOCS / "JOURNAL.jsonl"
WORK = DOCS / "WORK_ORDER_V8.md"


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def journal(event, **kw):
    DOCS.mkdir(parents=True, exist_ok=True)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": now(), "event": event, **kw}, ensure_ascii=False) + "\n")


def parse_queue_block(text):
    m = re.search(r"```queue\n(.*?)\n```", text, re.S)
    tasks = []
    if not m:
        return tasks
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", 3)]
        if len(parts) < 4:
            continue
        tid, phase, title, verify = parts
        tasks.append({"id": tid, "phase": phase, "title": title, "verify": verify,
                      "status": "TODO", "attempts": 0, "evidence": "", "updated": now()})
    return tasks


def get_queue():
    q = load(QUEUE, None)
    if isinstance(q, dict) and q.get("version") == 8:
        return q
    return {"version": 8, "tasks": []}


def save_queue(q):
    atomic_write(QUEUE, q)


def find(q, tid):
    for t in q["tasks"]:
        if t["id"] == tid:
            return t
    print(f"unknown task id: {tid}")
    sys.exit(2)


def run_shell(cmd, timeout):
    try:
        p = subprocess.run(cmd, shell=True, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, "\n".join(out.strip().splitlines()[-15:])
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"


def git(*args):
    try:
        p = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def pid_alive(pid):
    if os.name == "nt":  # never os.kill on Windows: it terminates the process
        try:
            p = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=20)
            return str(pid) in p.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def counts(q):
    c = {}
    for t in q["tasks"]:
        c[t["status"]] = c.get(t["status"], 0) + 1
    return c


def cmd_init(a):
    if not WORK.exists():
        print(f"missing {WORK}; save the work order there first")
        return 2
    old = load(QUEUE, None)
    if old is not None and not (isinstance(old, dict) and old.get("version") == 8):
        bak = DOCS / "QUEUE_v7.json"
        if not bak.exists():
            atomic_write(bak, old)
    q = get_queue()
    have = {t["id"]: t for t in q["tasks"]}
    new = parse_queue_block(WORK.read_text(encoding="utf-8"))
    if not new:
        print("no ```queue block found in work order")
        return 2
    merged = []
    for t in new:
        if t["id"] in have and not a.force:
            keep = have[t["id"]]
            keep.update({"phase": t["phase"], "title": t["title"], "verify": t["verify"]})
            merged.append(keep)
        else:
            merged.append(t)
    q["tasks"] = merged
    save_queue(q)
    journal("init", tasks=len(merged))
    print(f"queue ready: {len(merged)} tasks", counts(q))
    return 0


def next_task(q):
    for t in q["tasks"]:
        if t["status"] == "DOING":
            return t
    for t in q["tasks"]:
        if t["status"] == "TODO":
            return t
    return None


def cmd_status(a):
    q = get_queue()
    print(counts(q))
    for t in q["tasks"]:
        if t["status"] in ("DOING", "BLOCKED", "FAILED"):
            print(f'  {t["status"]:8} {t["id"]}  {t["title"][:70]}  {t["evidence"][:60]}')
    return 0


def cmd_next(a):
    t = next_task(get_queue())
    print("NONE (queue finished: run release verdict)" if not t else f'{t["id"]} [{t["phase"]}] {t["title"]} | verify: {t["verify"]}')
    return 0


def cmd_start(a):
    q = get_queue()
    t = find(q, a.id)
    t["status"] = "DOING"
    t["attempts"] += 1
    t["updated"] = now()
    save_queue(q)
    st = load(STATE, {})
    st.update({"current_task": a.id, "updated": now()})
    atomic_write(STATE, st)
    journal("start", id=a.id, attempt=t["attempts"])
    print(f'started {a.id} (attempt {t["attempts"]}); verify: {t["verify"]}')
    return 0


def cmd_done(a):
    q = get_queue()
    t = find(q, a.id)
    ev = a.evidence or ""
    if t["verify"] not in ("-", "") and not a.no_verify:
        rc, tail = run_shell(t["verify"], a.timeout)
        if rc != 0:
            t["status"] = "DOING"
            t["evidence"] = f"verify FAILED rc={rc}: {tail[-300:]}"
            t["updated"] = now()
            save_queue(q)
            journal("verify_failed", id=a.id, rc=rc)
            print(f"NOT DONE: verify command failed (rc={rc})\n{tail}")
            return 1
        ev = (ev + " | " if ev else "") + "verify OK: " + t["verify"]
    elif t["verify"] in ("-", "") and not a.evidence:
        print("manual task: --evidence is required")
        return 1
    elif a.no_verify and not a.evidence:
        print("--no-verify requires --evidence")
        return 1
    t["status"] = "DONE"
    t["evidence"] = ev[:500]
    t["updated"] = now()
    save_queue(q)
    journal("done", id=a.id, evidence=ev[:200])
    print(f"DONE {a.id}")
    return 0


def cmd_block(a):
    q = get_queue()
    t = find(q, a.id)
    t["status"], t["evidence"], t["updated"] = "BLOCKED", a.reason[:300], now()
    save_queue(q)
    journal("block", id=a.id, reason=a.reason[:200])
    print(f"BLOCKED {a.id}")
    return 0


def cmd_fail(a):
    q = get_queue()
    t = find(q, a.id)
    t["status"], t["evidence"], t["updated"] = "FAILED", a.evidence[:300], now()
    save_queue(q)
    journal("fail", id=a.id, evidence=a.evidence[:200])
    print(f"FAILED {a.id}")
    return 0


def cmd_checkpoint(a):
    st = load(STATE, {})
    st.update({"last_checkpoint": a.note[:500], "checkpoint_at": now(),
               "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "last_commit": git("rev-parse", "--short", "HEAD")})
    atomic_write(STATE, st)
    journal("checkpoint", note=a.note[:200])
    print("checkpoint saved")
    return 0


def jobs_report():
    out = []
    for pat in ("eval/runs/*/pid.txt", "training/runs/*/pid.txt", "runs/*/pid.txt"):
        for p in ROOT.glob(pat):
            d = p.parent
            try:
                pid = int(p.read_text().strip())
            except Exception:
                continue
            finished = (d / "DONE.json").exists() or (d / "FAILED.txt").exists()
            state = "FINISHED (DONE.json)" if (d / "DONE.json").exists() else (
                "FINISHED (FAILED.txt)" if (d / "FAILED.txt").exists() else
                ("RUNNING" if pid_alive(pid) else "DIED without DONE/FAILED (inspect job.log tail, relaunch once)"))
            if not finished or True:
                out.append(f"  {d.relative_to(ROOT).as_posix()}: pid {pid} {state}")
    return out[-8:]


def cmd_resume(a):
    q = get_queue()
    st = load(STATE, {})
    st["session"] = int(st.get("session", 0)) + 1
    st["resumed_at"] = now()
    atomic_write(STATE, st)
    journal("resume", session=st["session"])
    porcelain = git("status", "--porcelain").splitlines()
    print(f'RESUME session #{st["session"]} @ {now()}')
    print(f'branch: {git("rev-parse", "--abbrev-ref", "HEAD") or "?"} | last commit: {git("log", "-1", "--format=%h %s") or "?"}')
    print(f"uncommitted paths: {len(porcelain)}" + ("  -> " + "; ".join(l.strip() for l in porcelain[:8]) if porcelain else ""))
    print(f'last checkpoint: {st.get("last_checkpoint", "(none)")}')
    print("queue:", counts(q) if q["tasks"] else "EMPTY -> run: python scripts/agent_ctl.py init")
    jr = jobs_report()
    if jr:
        print("jobs:")
        print("\n".join(jr))
    t = next_task(q)
    if not q["tasks"]:
        print("NEXT ACTION: python scripts/agent_ctl.py init")
    elif t is None:
        print("NEXT ACTION: queue finished. Run the release verdict step; do not claim completion without it.")
    elif t["status"] == "DOING":
        print(f'NEXT ACTION: task {t["id"]} was interrupted (attempt {t["attempts"]}). 1) git diff --stat  2) python scripts/agent_ctl.py done {t["id"]}  '
              f'(if verify passes it is finished) 3) otherwise continue its work. Never discard uncommitted work; commit it as "wip({t["id"]})" first.')
    else:
        print(f'NEXT ACTION: python scripts/agent_ctl.py start {t["id"]}   ({t["title"]}) ; then python scripts/skill_router.py "<task>"')
    print("RULES: read only docs/AGENT_STATE.json, this output and `agent_ctl.py section <current phase>`. Do not re-read the whole work order.")
    return 0


def cmd_recheck(a):
    q = get_queue()
    bad = 0
    for t in q["tasks"]:
        if t["status"] == "DONE" and t["verify"] not in ("-", "") and (not a.phase or t["phase"] == a.phase):
            rc, tail = run_shell(t["verify"], a.timeout)
            if rc != 0:
                bad += 1
                t["status"] = "TODO"
                t["evidence"] = f"REGRESSION on recheck rc={rc}: {tail[-200:]}"
                t["updated"] = now()
                print(f'REGRESSION {t["id"]}')
    save_queue(q)
    journal("recheck", regressions=bad)
    print(f"recheck done, regressions: {bad}")
    return 1 if bad else 0


def cmd_reconcile(a):
    q = get_queue()
    fixed = 0
    for t in q["tasks"]:
        if t["status"] in ("TODO", "DOING") and t["verify"] not in ("-", "") and (not a.phase or t["phase"] == a.phase):
            rc, _ = run_shell(t["verify"], a.timeout)
            if rc == 0:
                t["status"], t["evidence"], t["updated"] = "DONE", "reconciled: verify passes", now()
                fixed += 1
                print(f'reconciled DONE {t["id"]}')
    save_queue(q)
    journal("reconcile", fixed=fixed)
    print(f"reconcile finished, newly DONE: {fixed}")
    return 0


def cmd_section(a):
    if not WORK.exists():
        print("missing work order copy")
        return 2
    lines = WORK.read_text(encoding="utf-8").splitlines()
    key = a.name.lower()
    start = None
    for i, l in enumerate(lines):
        if l.startswith("## ") and key in l.lower():
            start = i
            break
    if start is None:
        print("no such section; headings:")
        print("\n".join(l for l in lines if l.startswith("## ")))
        return 2
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    print("\n".join(lines[start:min(end, start + 400)]))
    return 0


def cmd_selftest(a):
    assert parse_queue_block("x\n```queue\nA1 | P | title one | python -c \"print(1)\"\nA2 | P | manual | -\n```")[1]["verify"] == "-"
    t = pathlib.Path(tempfile.mkdtemp()) / "x.json"
    atomic_write(t, {"a": 1})
    assert load(t, None) == {"a": 1}
    assert pid_alive(os.getpid())
    print("selftest OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--force", action="store_true"); p.set_defaults(f=cmd_init)
    for n, f in (("status", cmd_status), ("next", cmd_next), ("resume", cmd_resume), ("selftest", cmd_selftest)):
        sub.add_parser(n).set_defaults(f=f)
    p = sub.add_parser("start"); p.add_argument("id"); p.set_defaults(f=cmd_start)
    p = sub.add_parser("done"); p.add_argument("id"); p.add_argument("--evidence", default=""); p.add_argument("--no-verify", action="store_true"); p.add_argument("--timeout", type=int, default=1800); p.set_defaults(f=cmd_done)
    p = sub.add_parser("block"); p.add_argument("id"); p.add_argument("--reason", required=True); p.set_defaults(f=cmd_block)
    p = sub.add_parser("fail"); p.add_argument("id"); p.add_argument("--evidence", required=True); p.set_defaults(f=cmd_fail)
    p = sub.add_parser("checkpoint"); p.add_argument("note"); p.set_defaults(f=cmd_checkpoint)
    p = sub.add_parser("recheck"); p.add_argument("--phase", default=""); p.add_argument("--timeout", type=int, default=1800); p.set_defaults(f=cmd_recheck)
    p = sub.add_parser("reconcile"); p.add_argument("--phase", default=""); p.add_argument("--timeout", type=int, default=1800); p.set_defaults(f=cmd_reconcile)
    p = sub.add_parser("section"); p.add_argument("name"); p.set_defaults(f=cmd_section)
    a = ap.parse_args()
    sys.exit(a.f(a))


if __name__ == "__main__":
    main()
````

### Appendix D — `AGENTS.md` and `GEMINI.md` (create both byte for byte, same content)

Content (same for both files):

````markdown
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
````

### Appendix E — Skill changes (create/replace byte for byte; the router reads only the first six lines of each file)

#### File: `docs/agent_skills/agent-ctl.md`

````
name: agent-ctl
triggers: agent_ctl, resume, queue, checkpoint, state file, get back to work, stopped, continue, journal, reconcile
- `python scripts/agent_ctl.py resume` first in every session; do its NEXT ACTION.
- start -> work -> `done <ID>` (verify command must pass) -> commit `[<ID>] ...` -> `checkpoint "<note>"`.
- Edit QUEUE.json / AGENT_STATE.json / JOURNAL.jsonl only through the script (atomic writes).
- Lost state: `init` then `reconcile`. Doubt about an old task: `recheck --phase <P>`.
- Interrupted task with uncommitted changes: `git diff --stat`, commit as `wip(<ID>)`, then `done <ID>`.
- Windows: never use os.kill to test a process (it terminates it); the script uses tasklist.
````

#### File: `docs/agent_skills/csp-hardening.md`

````
name: csp-hardening
triggers: csp, content-security-policy, script-src, unsafe-inline, nonce, report-only, inline script, security headers
- Enforced header = baseline that works today; a stricter policy goes in Report-Only until someone checks the UI in a browser.
- Strict policy: no `unsafe-inline` in `script-src`; allow inline scripts by `'sha256-<base64>'` of the exact script text (UTF-8, between the tags, whitespace included); no `unsafe-eval`.
- Inline event handlers (`onclick=`) and `javascript:` URLs cannot be allowed by hashes: list them in docs/CSP_NOTES.md.
- Recompute hashes when the served HTML changes (mtime). Test: header hashes equal the real inline scripts.
- Never send the identical policy as both enforced and Report-Only. Say exactly which one is enforced in the blueprint.
````

#### File: `docs/agent_skills/face-embedding.md`

````
name: face-embedding
triggers: arcface, face, embedding, cosine, landmark, alignment, face_match, face_embed_model, biometric, selfie, w600k
- Face matching must really run a verified embedding model, or say plainly that it did not (mode `unavailable` -> INCONCLUSIVE -> REVIEW).
- Model files come only from the private HF repo through `ml_service/model_fetch.py`, pinned by SHA-256 in `ml_service/models/MODEL_MANIFEST.json`. Empty or missing SHA = refuse. Auto-download is off by default.
- Read the model contract from the file itself with onnxruntime (input name/shape/dtype, embedding size); preprocessing text must come from the code actually used and stay `preprocessing_verified: false` until the proxy evaluation shows which variant separates genuine from impostor pairs best.
- Always L2-normalise; cosine = dot product. Tests: norm 1 +/- 1e-3, self-similarity >= 0.999, deterministic.
- Thresholds: see skill face-policy. Accuracy figures only from labelled pairs; `pics` gives PROXY numbers only.
- Licence heads-up for OWNER_TODO (not a blocker): some popular face-model weight families are limited to non-commercial research; record the licence text path in the manifest.
````

#### File: `docs/agent_skills/face-policy.md`

````
name: face-policy
triggers: threshold, aged photo, age relax, face verdict, match decision, inconclusive, face_policy, similarity, face threshold
- One policy file (`face_policy.py`) in app/ and ml_service/, byte-identical copies, one step function `effective_threshold(photo_age_years)`.
- Defaults BASE_SAME 0.60, AGED_SAME 0.52 after 5 years, DIFF 0.40; env overrides only inside 0.30 <= AGED <= BASE <= 0.90.
- PASS needs mode arcface AND decision MATCH AND similarity >= BASE_SAME. A match that exists only because of the aged threshold is REVIEW.
- Any mode other than arcface: decision INCONCLUSIVE, verdict REVIEW, legacy `match` None, no age relaxation.
- No sliding formulas without an impostor-pair measurement; report possible same-person pairs separately.
````

### Appendix F — Static narrative for `docs/CLAUDE_HANDOFF.md` (copy verbatim into that file's first section)

````markdown
## Context from previous Claude sessions (written 2026-10-12 by Claude; narrative, so re-verify facts against the generated block below)

### Who and what
- Owner: Dikhyant Satapathy. Project: NO-CAP (SIH26188), AI-assisted screening of identity documents (Aadhaar, PAN, voter ID, driving licence, passports/MRZ, Nepali Nagarikta, Bhutanese CID) for border officers. Decision support only; a human officer decides.
- Repo: github.com/dikhyantsatpathy-ui/Vibe-Check-point. `main` deploys to Vercel production; a separate test project (`vibe-check-point-test`) exists. Database: Neon Postgres. Models live in a private Hugging Face repo (`koropanda/no-cap-detectors`) and an ML service runs as a Hugging Face Space. All of this was reported by the coding agent or the owner; Claude could not check any live system.
- Owner machine: Windows, PowerShell, RTX 4060 Laptop 8 GB. The coding agent is Gemini in Antigravity.

### How the owner works (adapt to it)
- Casual, direct, often away. Wants a finished prompt or answer, not a discussion. Pays per token, so no long polling or narration by the agent.
- Delegates all coding to the Gemini agent through long markdown work orders; Claude's job is to write, audit and correct those prompts and to review the agent's output from uploaded zips and reports.
- The owner has pasted secrets into chat more than once (a Hugging Face token, a Roboflow key, an SFTP password from an email). Never echo, store or reuse them. Treat the Hugging Face token as compromised.
- Owner decisions: YOLOv8 stays the default backend until the owner says otherwise; licensing is not a blocker unless a model cannot work; the demo pass is an intentional jury feature (opt-in via DEMO_PASS_ENABLED); `data/AADHAR` (possibly real people's scans) is internal only.

### History
- v3 to v8 work orders. Earlier agent runs: hand-typed metrics, "PASS (honest)" on failed gates, comparing different test sets, a test site cloned with production secrets, a final report saying "ready for release" while its own ledger listed false claims. The v6 to v8 designs answer this with a claims ledger, receipts, queue-based state and code-generated verdicts.
- Datasets: MIDV-2020 (owner accepted the form; the shared SFTP login came by email and must not be stored), MIDV-500, FantasyID (not confirmed downloaded), small Roboflow Indian sets, a private `pics/` folder of unlabeled images (never committed). Licences of several sets are unread.

### Claude's own corrections (do not repeat these mistakes)
- Claude first called the demo login a forgotten bypass; it is documented and intentional. The risk is only deploying that build to a real checkpoint.
- Claude could not run the project's tests in its sandbox (project dependencies absent); its reviews were static reading of zips. Say so each time.
- Claude cannot access the owner's machine, Vercel, Neon or Hugging Face.

### Known weak spots (as of this handoff; check the generated block for current state)
- Face matching: no model shipped; earlier code auto-downloaded a third-party copy; three inconsistent age-relaxation rules; accuracy numbers 98.4 % / 99.1 % had no source. v8 patches P1 to P7.
- CSP baseline allows inline scripts. Isolation of the test site from production secrets was never verified (needs the owner's Vercel login). Real Indian-card accuracy, real forgery and replay detection are NOT MEASURED. Court-admissibility wording needs a lawyer.
- About 95 MB of ONNX weights are tracked in git on `main` (owner decision pending).

### What a fresh Claude should do first
1. Read this file, the blueprint, `docs/QUEUE.json`, the newest `docs/AUDIT_V*.md`, the newest claims report.
2. Ask the owner only what the files cannot answer; offer a finished artifact rather than options.
3. Review claims against code before trusting any report; compare numbers only on identical test sets; never accept a document that states a result without a JSON behind it.
4. Never place secrets, personal data or the owner's real ID values in any file or reply.
````

### Appendix G — Questions for the owner (once, at the very end)
1. Did you revoke the exposed Hugging Face token and create read-only tokens for the Space/Vercel? Confirm only.
2. Please upload `w600k_r50.onnx` (or the face model you choose) to the private HF repo and confirm the licence is acceptable for your use (exact commands are in OWNER_TODO).
3. Run `scripts/owner_check_isolation.ps1` and paste the SAME/DIFFERENT lines (no values exist in its output).
4. Open the site with DevTools open, report any CSP violation lines, then decide on `CSP_STRICT_ENFORCE=1`.
5. Can you provide ~50 consented same-person photo pairs for a real face-matching accuracy figure?
6. Specimen photos of printed Indian-layout cards: where and how many?
7. Do you want a PR from `ml/patch-v8` to `main` when the verdict says GO?
8. Any entry in DECISIONS.md or any ACCEPTED-RISK finding you disagree with.

**START: `python scripts/agent_ctl.py resume` (if the script does not exist yet: task R1). Do not narrate. Do not stop while the queue has TODO/DOING tasks.**
