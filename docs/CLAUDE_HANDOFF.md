# NO-CAP (SIH26188) — Claude Handoff Dossier

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
- Face matching: no model shipped; earlier code auto-downloaded a third-party copy; three inconsistent age-relaxation rules; accuracy numbers (unverified ~98% / ~99% figures) had no source. v8 patches P1 to P7.
- CSP baseline allows inline scripts. Isolation of the test site from production secrets was never verified (needs the owner's Vercel login). Real Indian-card accuracy, real forgery and replay detection are NOT MEASURED. Court-admissibility wording needs a lawyer.
- About 95 MB of ONNX weights are tracked in git on `main` (owner decision pending).

### What a fresh Claude should do first
1. Read this file, the blueprint, `docs/QUEUE.json`, the newest `docs/AUDIT_V*.md`, the newest claims report.
2. Ask the owner only what the files cannot answer; offer a finished artifact rather than options.
3. Review claims against code before trusting any report; compare numbers only on identical test sets; never accept a document that states a result without a JSON behind it.
4. Never place secrets, personal data or the owner's real ID values in any file or reply.

---

## Dynamic Repository Facts Block (Auto-Generated)

- **Branch:** `ml/patch-v8`
- **Last Commit:** `4c21f3e [K3] Claude handoff generator with static narrative and dynamic facts block`
- **Queue Task Statuses:** {"DONE": 28, "DOING": 1, "TODO": 3}
- **Claims Ledger Verdicts:** {"UNKNOWN": 78}
- **Test Suite Status:** **467 total tests** collected across **54 suites** (100% passing)

### Model Manifest (Pinned Artifacts)
| Model Name | Size (Bytes) | Size (MB) | SHA-256 (Prefix) | Origin Hint |
| :--- | :--- | :--- | :--- | :--- |
| `doctype_v2.onnx` | 6,113,857 | 5.83 MB | `548faa0fd6cf98ca...` | MobileNetV3 document classifier |
| `rfdetr_card_int8.onnx` | 38,963,695 | 37.16 MB | `ccab01630e533893...` | Fine-tuned card detector |
| `rfdetr_id_fields_int8.onnx` | 39,072,565 | 37.26 MB | `85c342e33f2b116d...` | Fine-tuned ID fields detector |
| `rfdetr_mrz_int8.onnx` | 39,034,095 | 37.23 MB | `a208402229d99023...` | Fine-tuned MRZ detector |
| `w600k_r50.onnx` | 174,383,860 | 166.31 MB | `4c06341c33c2a6f3...` | https://huggingface.co/maze/faceX/resolve/main/w60 |

### Environment Configuration Variables (.env.example names only)
`CARD_DETECTOR_BACKEND`, `DATABASE_URL`, `DEBUG`, `DETECTOR_BACKEND`, `DOCTYPE_BACKEND`, `ENABLE_GEMINI_FALLBACK`, `FIELD_DETECTOR_BACKEND`, `GEMINI_API_KEY`, `HF_MODEL_REPO`, `HF_MODEL_REVISION`, `HF_TOKEN`, `HOST`, `MASTER_VAULT_KEY`, `ML_SECRET_KEY`, `ML_SERVICE_SECRET`, `ML_SERVICE_URL`, `MODEL_CACHE_DIR`, `MRZ_DETECTOR_BACKEND`, `NODE_ENV`, `PORT`, `SESSION_SECRET`, `TAMPER_MODEL_BACKEND`

### Switch Readiness Matrix (Evidence-Backed)
| Stage | Evaluated Backend | REAL-Data Metric | SYNTHETIC Metric | Latency (2 vCPU Throttled) | File SHA-256 | Verdict |
|---|---|---|---|---|---|:---:|
| **Card Boundary** | `yolov8` (default) | **Recall: 1.0000, Prec: 1.0000**<br>(Clean MIDV-500 test) | Scale-stress 2x: 3.3%<br>3x: 16.7% | **32.4 ms** (CPU) | `ba5b3a91e3d80df74a6b31d1da695306d6a6bc767f27d2a9422de1ed66c98428` | **SHIP (Default)** |
| **Card Boundary** | `rf_detr` (candidate) | **Recall: 1.0000, Prec: 0.9912**<br>(Clean MIDV-500 test) | Scale-stress 2x: 46.7%<br>3x: 30.0% | **26.1 ms** (CPU INT8) | `ccab01630e53389387738a5af0c9456fb1aa6f3d68e3a0f1128ebe78b7f6b179` | **SHIP-WITH-REVIEW** (Kept YOLO baseline per C1) |
| **Doc-Type Cls** | `v1` (MobileNetV3) | **Aadhaar F1: 1.00, Passport F1: 0.95** | Overall Macro-F1: 0.952 | **8.2 ms** (CPU) | `71072468d2f50fc17b392b41cfa8f3179e634a3a00ce21ad2a43f5482ab26dd3` | **SHIP** |
| **Doc-Type Cls** | `v2` (Calibrated T=1.35) | **Aadhaar F1: 1.00, Passport F1: 0.95** | Macro-F1: 0.997 (8-class)<br>T=1.35, Review < 0.75 | **7.8 ms** (CPU) | `548faa0fd6cf98ca0ca520c9e7848b37e11cee2b7de9ed7bc13c6b9d1a5552a6` | **SHIP (Recommended)** |
| **Aadhaar Fields** | `yolov8` (default) | **mAP50-95: 0.8380** | mAP50-95: 0.8380 | **35.0 ms** (CPU) | `20754291b3e773dddc8be3155b5e3d15e3475f636b79ca30ae3d3e93cfc29c55` | **SHIP (Default)** |
| **Aadhaar Fields** | `rf_detr` (candidate) | mAP50-95: 0.7678 (Regression) | mAP50-95: 0.7678 | **185.2 ms** (CPU INT8) | `bc0af8e5483b9e503988537bf39666e680124f4a34ff496b3af4c55bbee59698` | **DO-NOT-SHIP** (Regression vs YOLO) |
| **ID Fields (PAN/DL)** | `rf_detr` | **UNVALIDATED** (Specimens pending) | Synthetic Recall: 0.5583 | **190.5 ms** (CPU INT8) | `85c342e33f2b116dcf9c616687ab4f62e132771da32800e22a7fc11a59a7c85d` | **DO-NOT-SHIP** (Not routed to prod) |
| **MRZ Extraction** | `bottom20` + Enhancer | **Valid Rate: 74.0%** (74/100 real MIDV)<br>(Gate: $\ge 60\%$) | **Valid Rate: 94.0%** (94/100 synth)<br>(Gate: $\ge 90\%$) | **45.2 ms** (CPU) | Rule-based (`app/mrz_enhancer.py` + `app/mrz.py`) | **SHIP (PASS)** |
| **Forensics ELA** | Heuristic Suite | **UNVALIDATED** (Real forgeries pending) | Synthetic AUC: 0.963 | **12.5 ms** (CPU) | In-process heuristic (`app/tampering.py`) | **SHIP-WITH-REVIEW** (Labeled SYNTHETIC-ONLY) |
| **Screen Replay** | 2D-FFT PAPR + Moiré | **UNVALIDATED** (Physical screens pending) | Synthetic Recapture **AUC: 0.9284**<br>TPR@0.63: 0.86, FPR: 0.06 | **15.1 ms** (CPU) | In-process heuristic (`app/replay_detector.py`) | **SHIP-WITH-REVIEW** (Labeled SYNTHETIC-ONLY) |
| **Face Biometrics** | `w600k_r50` (ArcFace) | **UNMEASURED** | **UNMEASURED** | Pending benchmark | `ml_service/models/w600k_r50.onnx` | **UNMEASURED** |
| **Indian Specimens** | Physical Specimen Test | **NOT MEASURED** | Synthetic Proxy Recall: 1.0000 | **32.0 ms** (CPU) | [`eval/eval_indian_specimens.py`](../eval/eval_indian_specimens.py) | **NOT MEASURED** (Awaiting photos) |

### Open Findings & Priority Actions (S1 / S2 First)
1. **S1 / Secret Hygiene & Credential Sealing:**
   - Exposed HF token flagged in prior session; write tokens must remain private.
   - Zero plaintext secrets in git tree verified by `scripts/audit_secrets_s1.py`.
2. **S2 / Deployment Isolation:**
   - Production (`vibe-check-point.vercel.app`) vs Staging (`vibe-check-point-test.vercel.app`) isolation verification pending owner Vercel CLI session. Script provided: `scripts/owner_check_isolation.ps1`.
3. **Face Model Provisioning:**
   - Private HF model fetch hardened with SHA-256 verification and size caps in `ml_service/model_fetch.py`. Model weights upload pending owner action in Item 10.
4. **CSP Strict Enforcement:**
   - Dynamic sha256 hash injection implemented for inline scripts. Strict enforcement behind `CSP_STRICT_ENFORCE=1` switch; officer UI manual verification pending.

### Active OWNER_TODO Headings
- # NO-CAP (SIH26188) — OWNER ACTION & TODO LIST
- ## 0. JURY EVALUATION PASS CONFIGURATION (F-01)
- # On jury demo instance (Vercel or local):
- ## 1. PENDING CREDENTIALS & ACCESS
- ### Item 1: Roboflow API Key
- ### Item 2: Hugging Face Write Token & Repository
- ## 2. PHYSICAL SPECIMEN CAPTURE (PHASE 9)
- ## 3. DATASET LICENSING & GOVERNANCE
- ### Item 3: MIDV-2020 Licence Text
- ### Item 4: `data/AADHAR` Dataset Disposition
- ### Item 5: Mendeley Synthetic Aadhaar Download
- ## 4. VERCEL DEPLOYMENT & ISOLATION ACTIONS (F-13 / F-14)
- ### Item 6: Staging vs Production Environment Isolation (F-13)
- ### Item 7: Token Hygiene in Deployed Vercel Projects (F-14)
- ### Item 8: Historical Neon PostgreSQL Password Rotation (Phase V1 / S1)
- ### Item 9: AGPL Tooling License Assessment for ONNX Checkpoints (Phase V2 / Legal)
- ## 5. PRIVATE MODEL REPOSITORY PROVISIONING (PHASE P4)
- ### Item 10: Upload ArcFace Model to Private Hugging Face Repository
- ## 6. CSP ENFORCEMENT VERIFICATION (PHASE P8)
- ### Item 11: CSP Strict Enforce Verification

### Last 20 Agent Journal Entries
- `{"t": "2026-10-12T22:00:29Z", "event": "checkpoint", "note": "T4 complete; next T5 compileall and ruff check"}`
- `{"t": "2026-10-12T22:00:34Z", "event": "resume", "session": 34}`
- `{"t": "2026-10-12T22:00:41Z", "event": "start", "id": "T5", "attempt": 1}`
- `{"t": "2026-10-12T22:02:48Z", "event": "done", "id": "T5", "evidence": "verify OK: python -m compileall -q app ml_service api scripts"}`
- `{"t": "2026-10-12T22:03:10Z", "event": "checkpoint", "note": "T5 complete (Phase T finished); next Phase K"}`
- `{"t": "2026-10-12T22:03:16Z", "event": "resume", "session": 35}`
- `{"t": "2026-10-12T22:03:28Z", "event": "start", "id": "K1", "attempt": 1}`
- `{"t": "2026-10-12T22:04:03Z", "event": "resume", "session": 36}`
- `{"t": "2026-10-12T22:05:10Z", "event": "done", "id": "K1", "evidence": "verify OK: python scripts/verify_blueprint_claims.py"}`
- `{"t": "2026-10-12T22:05:50Z", "event": "checkpoint", "note": "K1 complete; next K2 blueprint template and renderer"}`
- `{"t": "2026-10-12T22:05:54Z", "event": "resume", "session": 37}`
- `{"t": "2026-10-12T22:05:59Z", "event": "start", "id": "K2", "attempt": 1}`
- `{"t": "2026-10-12T22:14:33Z", "event": "done", "id": "K2", "evidence": "verify OK: python scripts/render_blueprint.py --check"}`
- `{"t": "2026-10-12T22:15:00Z", "event": "checkpoint", "note": "K2 complete; next K3 Claude handoff generator"}`
- `{"t": "2026-10-12T22:15:08Z", "event": "resume", "session": 38}`
- `{"t": "2026-10-12T22:15:14Z", "event": "start", "id": "K3", "attempt": 1}`
- `{"t": "2026-10-12T22:17:45Z", "event": "done", "id": "K3", "evidence": "verify OK: python scripts/render_handoff.py --check"}`
- `{"t": "2026-10-12T22:18:32Z", "event": "checkpoint", "note": "K3 complete; next K4 blueprint and handoff check"}`
- `{"t": "2026-10-12T22:18:37Z", "event": "resume", "session": 39}`
- `{"t": "2026-10-12T22:18:43Z", "event": "start", "id": "K4", "attempt": 1}`

---

## Audit this repo in 10 commands

Run these 10 commands in order from PowerShell or terminal to independently verify system status:

```bash
# 1. Inspect queue progression and agent control state
python scripts/agent_ctl.py status

# 2. Evaluate overall release readiness verdict
python scripts/release_verdict.py

# 3. Verify all 78 engineering blueprint claims against reality
python scripts/verify_blueprint_claims.py

# 4. Confirm blueprint template matches disk with zero unresolved placeholders
python scripts/render_blueprint.py --check

# 5. Confirm Claude handoff document integrity
python scripts/render_handoff.py --check

# 6. Verify switch readiness matrix rendered from verified JSON evidence
python scripts/render_switch_readiness.py

# 7. Execute automated secret hygiene audit across working tree and commit history
python scripts/audit_secrets_s1.py

# 8. Check test coverage gate against 85% threshold
python scripts/check_coverage.py

# 9. Run documentation hygiene, queue parity, and Invariant FS test suites
python -m pytest tests/test_v8_docs_hygiene.py tests/test_v8_invariants.py -q

# 10. Verify clean working tree on authorized branch
git status
```

---

## Upload these files to a fresh Claude chat

When opening a new Claude audit or development session, upload exactly these files:

1. `SIH26188_ENGINEERING_BLUEPRINT.md` (System specifications and mathematical models)
2. `docs/CLAUDE_HANDOFF.md` (This handoff file with narrative and dynamic facts)
3. `docs/QUEUE.json` (Machine-readable task status queue)
4. `docs/AUDIT_V7.md` (Most recent comprehensive architecture and security audit)
5. `eval/runs/20261012_221411_claims/report.json` (Latest claims verification run report)
6. `docs/SWITCH_READINESS.md` (Evidence-backed model and pipeline readiness matrix)

*(Note: Provide repository zip only if specifically requested by the owner or auditor.)*

