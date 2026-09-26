# SSB Border Screening — Architecture Walkthrough

**Project:** Fake Identity & Document Screening (SIH26188) — Ministry of Home Affairs / SSB screening desk.
**Scope of this document:** read-only full-codebase audit of the architecture as it stands. Everything below was verified against the actual source; paths are exact, function signatures are copied from code.

---

## Table of contents

1. [Objective of this audit](#1-objective)
2. [Repository layout & deployment topology](#2-repository-layout--deployment-topology)
3. [ML pipeline (Python)](#3-ml-pipeline-python)
   - 3a. YOLOv8 document locator (`app/yolo_roi.py`)
   - 3b. ArcFace identity matching (`app/face_match.py`, `app/face.py`)
   - 3c. AI-generation detectors (inlined in `app/main.py`)
   - 3d. Training context (recent work) — datasets, runs, metrics
4. [Backend API (FastAPI)](#4-backend-api-fastapi)
   - Endpoints table
   - Auth & session model
   - Database models & startup behaviour
5. [Screening pipeline](#5-screening-pipeline)
6. [Image forensics & security](#6-image-forensics--security)
7. [Frontend (React)](#7-frontend-react)
8. [Configurations](#8-configurations)
9. [Build-status triage](#9-build-status-triage)
10. [Thinking notes & deltas discovered during the audit](#10-thinking-notes--deltas)
11. [Open items / pending decisions](#11-open-items--pending-decisions)

---

## 1. Objective

Produce a comprehensive architecture walkthrough of the SIH26188 screening system, covering:

- the ML pipeline (how the YOLOv8 `.onnx` document locator and the ArcFace identity matcher are loaded, initialised, and executed — paths + signatures),
- the FastAPI backend (all active endpoints, request/response shapes, and how endpoints call the AI models),
- image forensics & security (ELA/tamper detection, SHA-256 hashing, audit logging of verification records),
- the React frontend (components, how images reach the backend and how the risk score is displayed),
- configurations (`requirements.txt`, `package.json`, env vars), and
- a per-area classification: **fully built / partially scaffolded / missing**.

---

## 2. Repository layout & deployment topology

```
D:\mos\crypto\
├── main.py                  # Root ASGI shim → re-exports `app.main.app` (Vercel native FastAPI detection)
├── api/index.py             # Vercel serverless entry (Preset = Other) → same re-export
├── app\                     # Python backend package (no __init__.py — path-shim imports)
│   ├── main.py              # 2,167 lines — FastAPI app, DB models, auth, inlined AI detectors
│   ├── screening.py         # run_screening() 4-module pipeline + hash/mask helpers
│   ├── extraction.py        # M1 field extraction (PDF/image/OCR/MRZ/declared merge)
│   ├── validation.py        # M2 deterministic validation + watchlist
│   ├── tampering.py         # M3 tamper orchestration
│   ├── face.py              # M4 face-verify orchestration
│   ├── face_match.py        # ArcFace/FaceNet ONNX embeddings + dHash fallback
│   ├── forensics.py         # ELA / spectral / PRNU / image_qa / ROI overlay / liveness
│   ├── identity.py          # PAN/DL/Voter/Passport/Visa verify + OCR dispatch
│   ├── mrz.py               # ICAO 9303 TD1/TD2/TD3 parse + check digits
│   ├── syndicate.py         # cross-checkpoint recidivism/clash/burst alerts
│   ├── transliterate.py     # Devanagari → Latin transliteration + fuzzy name matching
│   ├── yolo_roi.py          # YOLOv8 ONNX locator (card.onnx / aadhaar_fields.onnx) + CV heuristics
│   ├── codebase.py          # repo index injected into Gemini /api/chat context
│   ├── static\index.html    # 294 KB single-file React build (Vite inline) served at "/"
│   └── models\              # gitignored ONNX weights (auto-loaded defaults)
├── frontend\src\            # React 18 + TS + Vite source (build → app/static/index.html)
│   ├── App.tsx · main.tsx · api.ts · knowledge.ts
│   ├── views\  AuthorityView.tsx (1,415 lines) · gsi.ts
│   ├── components\  ui.tsx · ProjectChatbot.tsx
│   └── app\  state.tsx · explain.tsx · motion.tsx · theme.ts · specimens.ts · util.ts
├── scripts\                 # training corpus builders + train_yolo.py (local GPU only)
├── tests\                   # pytest — 95 passed, 1 skipped
├── requirements.txt         # serverless-safe deps (onnxruntime deliberately omitted)
├── vercel.json              # rewrite all → api/index.py, maxDuration 60
├── .vercelignore            # excludes scripts/tests/data/*.md — Vercel bundle stays < 128 MB
├── .gitignore               # ignores data/, runs/, weights/, *.pt, *.onnx, .env, models
├── README.md                # project guide + env table
├── MHA_SCREENING.md         # screening-desk design doc
├── AI_MODELS.md             # model inventory + training instructions
├── TRAINING.md              # YOLO/ONNX training notes
├── TRAINING.md / START.bat / LICENSE / opencode.json
```

**Deployment topology:**

- **Vercel** hosts everything. `vercel.json` rewrites every path to `api/index.py` (`{ "source": "/(.*)", "destination": "/api/index.py" }`, `maxDuration: 60`). A second root-level `main.py` exists for Vercel's *native FastAPI detection*; both shims re-export the real app from `app/main.py`.
- `.vercelignore` strips `scripts/`, `tests/`, `data/`, `*/*.md` (docs), `.env*` — keeping the lambda bundle under Vercel's 128 MB ceiling.
- The React app is compiled by `vite-plugin-singlefile` into one self-contained `app/static/index.html` (all JS + CSS inlined), served by FastAPI at `/`. Dev mode uses the Vite proxy (`VITE_PROXY_TARGET`, default `http://localhost:8000`) so the browser stays same-origin.
- Heavy AI runtimes (`onnxruntime`) are **not** on Vercel by design — heuristic/Pillow paths run there; the ONNX models (YOLO, ArcFace, self-hosted ViT) run on laptops/workers.

---

## 3. ML pipeline (Python)

The screening engine fuses **rule-based forensics + deterministic validation + optional ONNX deep models**, all loaded lazily so cold starts never pay for missing native deps.

### 3a. YOLOv8 document locator — `app/yolo_roi.py`

Trained locally with `scripts/train_yolo.py` (YOLOv8s; 129 layers, 11.1 M params, 28.6–28.7 GFLOPs, input 640 px). Two deployed ONNX weights live in `app/models/` (gitignored, ~42.7 MB each):

| Weight | Classes | Export shape | Val metrics |
|---|---|---|---|
| `app/models/card.onnx` | 1 (`Card`) | `[1,3,640,640] → [1,5,8400]` | mAP50 **0.986** · mAP50-95 **0.928** |
| `app/models/aadhaar_fields.onnx` | 5 (`Name, DOB, Gender, Aadhaar_No, Photo`) | `[1,3,640,640] → [1,9,8400]` | mAP50 **0.995** · mAP50-95 **0.836** (val 185 imgs / 731 instances) |

Symbols (all in `app/yolo_roi.py`):

| Symbol | Signature | Role |
|---|---|---|
| `_default_model_path()` | `-> str` | env `YOLO_ROI_ONNX_PATH` → `app/models/card.onnx` → `app/models/yolov8n.onnx` |
| `_get_onnx_session()` | `-> Session \| None` | lazy `onnxruntime.InferenceSession`, CPUExecutionProvider; `None` if `onnxruntime` absent |
| `_open_rgb(data)` | `-> np.ndarray \| None` | decode bytes → RGB float array |
| `_detect_face_heuristic(rgb)` | `-> dict \| None` | hand-rolled face-zone fallback |
| `_detect_mrz_zone(rgb)` | `-> dict \| None` | MRZ text-band fallback |
| `_detect_qr_zone(rgb)` | `-> dict \| None` | QR/2D-barcode zone fallback |
| `_detect_document_card(rgb)` | `-> dict` | card/quad detection fallback |
| `_run_yolo_onnx(rgb, session, max_boxes=4)` | `-> list[dict]` | preprocess → infer → `_nms` → JSON-safe dicts (`round(float(...),3)`, `label`, `box`, `confidence`, `class_id`) |
| `_nms(boxes, iou_thres=0.5)` | `-> list[dict]` | non-max suppression |
| `extract_roi_boxes(image_bytes)` | `-> list[dict]` | ONNX if session available else heuristic detector stack (graceful degradation) |
| `_get_aadhaar_session()` | `-> Session \| None` | env `AADHAAR_FIELDS_ONNX_PATH` → `app/models/aadhaar_fields.onnx`; CPUExecutionProvider, `intra_op_num_threads=2` |
| `extract_aadhaar_fields(image_bytes)` | `-> list[dict]` | runs the 5-class model, relabels via `_AADHAAR_CLASS_NAMES`, `max_boxes=8` |

**Wired usage — BUILT:** `app/forensics.py:398` `roi_boxes()` lazily imports `yolo_roi.extract_roi_boxes` and produces the YOLO ROI chips + overlay grid rendered in the M3 Tamper panel. Verified live: `card.onnx` on `data/card_synth/valid/images/scene_00000.jpg` returns a `document` box (0.614 / 0.124 / 0.081 / 0.067, conf 0.94); frames and JSON floats are clean.

**Wired usage — MISSING:** `extract_aadhaar_fields` currently has **no endpoint or UI consumer**. The trained 5-class Aadhaar model is the payload for a planned national-ID OCR route, but the desk's `SCREEN_DOC_TYPES` list deliberately excludes `aadhaar` ("intentionally absent: the backend no longer accepts it", `frontend/src/api.ts:276`), and class-name semantics (`Name/DOB/Gender/Aadhaar_No/Photo`) remain **provisional** pending a human eyeball of a prediction strip.

### 3b. ArcFace identity matching — `app/face_match.py`, `app/face.py`

- `compare_faces(document_photo, selfie) -> dict` (`app/face_match.py:139`) — M4 workhorse, returns `{score, match, method, detail, ...}`.
  - If `FACE_EMBED_MODEL` (`app/face_match.py` via `.env.example`, e.g. `data/models/w600k_r50.onnx` ArcFace 174 MB) points at an ArcFace/FaceNet-style `.onnx` **and** `onnxruntime` is installed: image → aligned face embedding → cosine distance; thresholds `_EMB_SAME = 0.60`, `_EMB_DIFF = 0.40`.
  - Else: **perceptual dHash** (Pillow) — `_DHASH_SAME = 8`, `_DHASH_DIFF = 20`. Coarse but works on Vercel today. `_embed_image(image)` lazily loads the ONNX; `dhash(image)`/`_hamming(a,b)` implement the fallback.
- `face_verification(document_bytes, live_frame, doc_type)` (`app/face.py:14`) — M4 body orchestrator; returns `verdict` (`PASS`/`CLEAR`/`REVIEW`/`FAIL`/`UNVERIFIED`), `match: bool | None`, `score`, `method`, `detail`, `checks`; `_document_face_b64` extracts the doc portrait for the comparison.
- Called from `run_screening` with the uploaded document bytes plus the live webcam still captured in-browser (`navigator.mediaDevices.getUserMedia` → canvas `toBlob('image/jpeg', 0.85)`).

### 3c. AI-generation detectors (inlined in `app/main.py`)

Section claim (line 52): "6 providers (free heuristic, Sightengine cloud, self-hosted ONNX) folded into one module" — in practice the live set is **3 backends in 1 resolver**:

| Provider | Trigger | What runs | Notes |
|---|---|---|---|
| `heuristic` (default) | provider unset | metadata/self-tag signatures (`_signatures` tables), `_pixel_scan`, `looks_like_scanned_document`, `heuristic_score(report)` | always-on; document-aware → a scan gets a `DOCUMENT` verdict, not an AI-art verdict |
| `sightengine` | `AI_DETECTOR_PROVIDER=sightengine` + `AI_DETECTOR_KEY` | `AI_DETECTOR_ENDPOINT` (default `https://api.sightengine.com`), model set `AI_DETECTOR_MODELS` (default `genai`) | cloud |
| `self-hosted` | `AI_DETECTOR_PROVIDER=self-hosted` | ViT-Base "Real vs AI" ONNX; `AI_DETECTOR_MODEL_URL` / `AI_DETECTOR_MODEL_DIR`; `onnx_score()` → softmax → `ai_score = P(Fake/AI)*100`, `ai_suspected = ai_score >= 50` | auto-downloads ~340 MB fp32 weights; needs `onnxruntime` (commented out of `requirements.txt`) |

Public entry: `detect_image(image_bytes, filename) -> dict` at `app/main.py:751`; resolver at line 711. Output snapshot `{ran, ai_suspected, ai_score, model, provider, explanation, latency_ms, document_aware}` is persisted in the `ai_detection` column per report.

### 3d. Training context (recent work)

| Run | Data | Metrics | Artifact |
|---|---|---|---|
| Card detector (yolov8s) | `data/card_synth` — synthetic 640×640 ID-card scenes; train 1314 / valid 243 (`nc=1` Card; first 225 scenes form `valid/images`; `data/IDcard` = 58 real cards normalized for synthetic augmentation) | final mAP50 0.986 · mAP50-95 0.928 | `runs/card/weights/best.onnx` → `app/models/card.onnx` |
| Aadhaar fields (yolov8s) | `data/AADHAR` — 3,165 imgs split train 2381 / val 185 / test 79, all pre-stretched 640×640, `nc=5` | final mAP50 0.995 · mAP50-95 0.836 (last-epoch 0.99496 / 0.82488) | `runs/aadhaar/weights/best.onnx` → `app/models/aadhaar_fields.onnx` |

- Training CLI used: `python scripts/train_yolo.py --task aadhaar --epochs 120` (logs in `data/logs/`).
- Live verification of `extract_aadhaar_fields` on the real sample `0521_adhar_jpg.rf.07ba8abd1b7df15479c52f38dcd1bfde.jpg` returned `Name` (0.86), `DOB` (0.85), `Aadhaar_No` (0.83), `Gender` (0.80) in the expected spatial positions; `Photo` (rare class, 87 val boxes) was absent on that run.

---

## 4. Backend API (FastAPI)

One `FastAPI` app in `app/main.py`. Infrastructure: `slowapi` rate limiter keyed by `get_remote_address`, CORS middleware, SQLAlchemy (`create_engine`, `declarative_base`, `sessionmaker`), lazy AI-model imports to avoid `main ↔ screening` circular imports and to keep cold starts fast.

### 4.1 Endpoint inventory (all routes — 17)

| Method / path | Auth gate | Rate | Purpose → AI/model hook |
|---|---|---|---|
| `GET /` | any | 120/min | `FileResponse(STATIC_DIR/index.html)` |
| `POST /api/admin/login` | — | 20/min | verifies Google `id_token` via `google.oauth2.id_token.verify_oauth2_token` (`GOOGLE_CLIENT_ID`, `clock_skew_seconds=300`); authorization gate from Google Cloud itself (`hd` claim / email-domain suffix in `ALLOWED_DOMAINS`, exact `ALLOWED_EMAILS`, super-admin bypass); `get_or_create_signer_identity`; sets HttpOnly cookie `nischay_session` (secure on Vercel) |
| `POST /api/admin/logout` | any | 20/min | deletes cookie |
| `GET /api/admin/me` | session | 120/min | returns `{status, admin, name, designation, institution, pending_approval, is_super_admin}` |
| `POST /api/admin/assign_role` | super | 20/min | grants post + institution (unblocks screening) |
| `GET /api/admin/signers` | super | 60/min | officer directory (no keys/ledger data) |
| `POST /api/screen` | officer/evaluator | 60/min | **the pipeline.** multipart: `file` (≤8 MB, `pdf|jpg|jpeg|png|webp|bmp`), `doc_type`, `checkpoint`, `declared` (JSON map), `live_frame` (optional Blob) → `run_screening(...)`; role-pending officers blocked |
| `GET /api/screen/queue` | officer | 120/min | pending (unadjudicated & not CLEAR) + recent (line officers see own, super/evaluator see all, limit 80) |
| `GET /api/screen/reports/{report_id}` | owner/super | 120/min | full masked detail + `signals`, `ai_detection`, `file_hash` |
| `POST /api/screen/reports/{report_id}/adjudicate` | super | 60/min | `CLEARED | CONFIRMED_FRAUD | INCONCLUSIVE` — human-in-the-loop |
| `GET /api/screen/watchlist` | super | 120/min | last 300 hash-only entries |
| `GET /api/screen/shift-export` | super | 30/min | CSV of the shift log; footer `# SHA-256: <digest>` (chain-of-custody receipt) |
| `GET /api/screen/syndicate-alerts` | super | 60/min | last 200 reports → `syndicate.analyze_syndicate_patterns` (recidivism / multi-checkpoint reuse / sector burst), optional `?checkpoint=` |
| `GET /api/screen/dossier/{report_id}` | super | 60/min | printable court dossier HTML; seal `HMAC-SHA256(MASTER_VAULT_KEY, f"{id}:{file_hash}:{verdict}:{risk}:{created}:{admin}")`; `?print=true` auto-prints |
| `POST /api/screen/watchlist/add` | super | 60/min | stores only `sha256(norm(value))` + `mask(value)`; unique `identifier_hash` + IntegrityError race guard |
| `POST /api/screen/watchlist/remove` | super | 60/min | delete by id |
| `POST /api/chat` | any | 30/min | Gemini (`GEMINI_MODEL`, model fallback chain `gemini-3.5-flash-lite → 3.6-flash → 2.5-flash…`), system prompt + `codebase.codebase_context(message)`; friendly `reason` on failure enough for the UI to fall back to the offline `knowledge.ts` |

### 4.2 Auth & session model

- Self-contained HMAC token: `f"{email}::{exp}::{sig}"`, `sig = HMAC-SHA256(MASTER_VAULT_KEY, f"{email}::{exp}")`, 1-day expiry (matches cookie `max_age`).
- Cookie `nischay_session`: `HttpOnly`, `SameSite=Lax`, `Secure` when `VERCEL=1`.
- Dependencies `get_current_admin(request)` (strict) and `get_current_admin_or_evaluator` (`/api/screen` — unsigned sandbox users screen as `evaluator@ssb.gov.in` for SIH26188 demos while logged-in officers keep attribution).
- `SUPER_ADMINS` environment variable (configured in `.env` or Vercel Secrets; comma-separated email list). Super-admins bypass the login gate and hold full supervisor administrative clearance (role assignments, officer directory).
- Startup is **hard-fail** if `MASTER_VAULT_KEY` or `GOOGLE_CLIENT_ID` is missing (`sys.exit`), to avoid running with an insecure demo config.

### 4.3 Database & startup behaviour

- **Neon Postgres** producer path: `_pg_creator` with 3-attempt retry; pooled `pool_size=3, max_overflow=5, pool_pre_ping=True, pool_recycle=290` (just under Neon's 300 s idle eviction), `pool_timeout=15`, `application_name="nocap"`.
- **SQLite** fallback: WAL + synchronous=NORMAL + busy_timeout=5000 + cache_size=-64000.
- `SessionLocal` + `Base`; `create_all` best-effort; idempotent `_MIGRATIONS` pass (adds `institution`/`designation`, screening indexes, unique watchlist hash, `modules` column) — never aborts startup on a transient Neon DNS blip.
- Neon keepalive daemon thread (non-Vercel): `SELECT 1` every `KEEPALIVE_INTERVAL` (default 45 s; `KEEPALIVE_INTERVAL=0` disables).

**Models (`app/main.py:899-945`):**
- `SignerIdentity` — `email` PK, `name`, `institution`, `designation`, `registered_at`.
- `ScreeningReport` — immutable audit row: `id`, `file_hash` (SHA-256, indexed), `filename`, `doc_type`, `checkpoint`, `verdict`, `risk_score`, `confidence`, `extracted_fields` (masked JSON), `signals` (reasons JSON), `ai_detection`, `modules` (M1–M4 JSON), `ledger_status` (always `LOCAL`), adjudication fields, `screener`, `created_at`. **Stores no raw bytes and no plaintext identifiers.**
- `WatchlistEntry` — `identifier_hash` (SHA-256, unique, indexed), `category`, `mask` (`****1234`), `reason`, `added_by`, `created_at`.

---

## 5. Screening pipeline

`app/screening.py:304` — `run_screening(db, data, filename, doc_type, checkpoint, declared, screener=None, live_frame=None) -> dict`:

```
file_hash = sha256(data); ledger_status = "LOCAL"
  M1 → extraction.extract_document(data, filename, doc_type, declared)
        [PDF (pypdf) → first image page; image → bytes; OCR (identity.ocr_extract →
         pytesseract, local-only) + MRZ (mrz.parse_mrz → ICAO 9303 TD1/TD2/TD3)
         + transliteration (transliterate) + officer-declared merge]
  AI → detect_image(data, filename) + looks_like_scanned_document(data)
        [lazy import from app.main; document-aware gate for scans]
  M2 → validation.validate_document(doc_type, fields, declared, "", watchlist_hits)
        [identity.verify_{pan,dl,rc,epic,passport,visa}: format + checksums +
         serial plausibility; MRZ check digits; expiry + 6-month travel rule]
        + watchlist: query ONLY the ≤7 identifier hashes we need, never the table
        [sha256(key) IN (identifier_hash)] → masked hit reports
  M3 → tampering.tamper_analysis(data, ai_det, document_aware, doc_type)
        [forensics: ela(), spectral_analysis(), noise_consistency(),
         image_qa(), roi_boxes(yolo), liveness_signals()]
  M4 → face.face_verification(document_bytes, live_frame, doc_type)
        [face_match.compare_faces: ArcFace/FaceNet cosine OR dHash]
  Analyze → explainable reasons[]; risk starts at 20, adjusted per check
        (e.g. valid PAN −3 … missing declared PAN +20, MRZ failure +30, watchlist +…);
  verdict → CLEAR | REVIEW | FLAGGED (map via _grade)
  Persist → one immutable ScreeningReport row (masked fields, zero raw bytes)
```

Relevant helper utilities (`app/screening.py`): `norm(value)` (normalize), `mask(value, keep=4)`, `sha256(value)`, `extract_fields(text)`, `_travel_validity(mrz_expiry, ...)` (six-month rule + age at crossing), `extract_mrz(text)`.

---

## 6. Image forensics & security

### Forensics (`app/forensics.py`, orchestrated by `app/tampering.py`)

Deliberately **numpy + Pillow only** (OpenCV optional accelerator) so everything runs on Vercel:

- `ela(data, quality=92, preview=128)` — re-save JPEG diff per block → damage-ratio heatmap → PNG base64.
- `spectral_analysis(data)` — 2D-FFT → PAPR + high-frequency ratio; flags unnatural pixel patterns.
- `noise_consistency(data, rois)` — PRNU-style sensor-noise variance (portrait vs substrate); splice detection.
- `image_qa(data)` — megapixels, blur estimate (variance of Laplacian), dark/bright fractions, over/under-exposure.
- `roi_boxes(data)` — calls `yolo_roi.extract_roi_boxes` (YOLO ONNX or heuristics).
- `liveness_signals(data)` + `verify_webcam_liveness(...)` — signal-based webcam-liveness checks (present; not part of `run_screening`).
- `forensics_report(data)` — kitchen-sink report.
- `_fire(row_norm)` — ELA scalar block fire; `_block_grid`, `_projected_bbox`, `_box_blur` internals.

### Hashing & audit trail (the security skeleton)

- `sha256()` / `mask()` / `norm()` at every identifier boundary. Nothing raw persists: **file bytes, live captures, OCR text and naked identifier numbers never touch disk or DB.**
- What **does** persist per screening: SHA-256 of the file bytes, masked identifier fields, explainable signals, the AI-detector snapshot, M1–M4 module verdicts, and the officer attribution. The `ScreeningReport` row is itself the tamper-evident verification record.
- Watchlist: only SHA-256 digests (`identifier_hash`) + a masked display label.
- Dossier: `HMAC-SHA256` custody seal over `{id}:{file_hash}:{verdict}:{risk}:{created}:{admin}`.
- Shift export: CSV end-trailer `# SHA-256: <hex>` for chain-of-custody verification.
- **Not present:** an external/immutable ledger. The earlier blockchain/signing layer (`HASHING_KEYS_AND_MODELS.md`, `VERIFICATION_PROVIDERS.md`, signing/ledger capability) was removed in the de-blockchain pass; `ledger_status` remains as an inert column always set to `LOCAL`. An optional non-blockchain audit-log checksum chain (append-only per-run hash chaining the four evidence hashes) was designed and offered but **not** implemented.

---

## 7. Frontend (React)

Stack: React 18 + TypeScript + Vite 6, built by `vite-plugin-singlefile` into `app/static/index.html` (single self-contained file — everything inline). No router; the whole app is one "authority console" view.

```
frontend/src/
├── main.tsx                       # StrictMode; ToastProvider > AuthProvider > ExplainProvider > App
├── App.tsx                        # ScrollProgress, TopBar (Google SSO chip, theme, Explain toggle), StatusBand, footer, <AuthorityView/> + ProjectChatbot
├── api.ts                         # typed fetch wrapper: ApiResult<T>; credentials:"include"; 429 → "Rate limit exceeded"; FormData builder; screenDocument/getScreenQueue/getScreenReport/adjudicateScreen/watchlist CRUD/syndicate/dossier
│                                  # SCREEN_DOC_TYPES (pan|passport|visa|driving_licence|voter_id|other — NO aadhaar)
│                                  # SCREEN_WATCHLIST_CATEGORIES (pan|passport|visa|driving_licence|voter_id|phone)
│                                  # Full ScreenReport / ScreenModules / ScreenModuleTampering type contracts
├── knowledge.ts                   # offline chatbot KB (14 curated Q/A entries), searchKnowledge() scorer, fallbackAnswer()
├── views/AuthorityView.tsx        # the console (1,415 lines)
│   ├── GoogleSignInButton         # GIS renderButton with VITE_GOOGLE_CLIENT_ID || FALLBACK_CLIENT_ID
│   ├── OfficerDirectory           # super-admin role approvals
│   ├── ScreeningDesk              # upload → run → module scorecard → judgment
│   ├── LiveCapture                # getUserMedia → canvas JPEG → live_frame Blob
│   ├── ModulePanel | ModuleScorecard | ScreenCheckRow | TravelValidityBadge
│   └── (queue, watchlist, syndicate panels, shift-log export, dossier links)
├── views/gsi.ts                   # FALLBACK_CLIENT_ID + downloadReceiptJson (legacy helper)
├── app/state.tsx                  # AuthProvider (booting/me/signedIn) + toast stack; signOut()
├── app/explain.tsx                # Explain Mode — plain-English "what & why" cards during demos
├── app/motion.tsx                 # scroll-reveal system
├── app/theme.ts                   # light/dark persisted to localStorage["nocap-theme"], applied pre-first-paint
├── app/specimens.ts               # SPECIMEN_PRESETS → generateSpecimenFile() (test documents for demos)
├── app/util.ts                    # initials, slugify, downloadBlob
└── components/
    ├── ui.tsx                     # Button, Card, Dropzone, Field, Modal, Pill, Kicker, EmptyNote, icons, useGsiReady
    └── ProjectChatbot.tsx         # floating "?" — posts to /api/chat (Gemini); auto-fallback to offline knowledge.ts
```

**How an image reaches the backend and comes back as a score:**

1. Officer picks a file (or a curated specimen preset) + doc type + checkpoint + optionally opens the camera for a live still.
2. `screenDocument(file, docType, checkpoint, declared, liveFrame)` builds multipart `FormData` (+ `live_frame` Blob named `holder_live.jpg`) → `POST /api/screen`.
3. The response `ScreenReport` drives `ModuleScorecard` pills (`M1 Extract / M2 Validate / M3 Tamper / M4 Face`) → panel detail (check rows, spectral PAPR, PRNU ratio, QA chips, YOLO ROI chips, toggled ELA heatmap) → **risk score `risk_score/100`** + verdict pill `CLEAR` (seal green) / `REVIEW` (amber) / `FLAGGED` (danger).
4. Report is appended to the queue; supervisors can adjudicate, open the HMAC-sealed ⚖️ dossier (new tab), export the shift log, and watch the syndicate monitor.

---

## 8. Configurations

### `requirements.txt` (serverless-safe)

```
fastapi · uvicorn · sqlalchemy · psycopg2-binary · pypdf · requests
python-multipart · slowapi · google-auth · python-dotenv
numpy==2.4.6 · Pillow==12.3.0
# onnxruntime  ← commented out: LOCAL-ONLY (self-hosted AI models)
```

### `frontend/package.json`

`react@^18.3.1` · `react-dom` · `jszip`; dev: `typescript ~5.6.3` · `vite ^6.1.0` · `vite-plugin-singlefile ^2.1.0` · `@vitejs/plugin-react`. Scripts: `dev` (vite, proxy → localhost:8000), `build` (`tsc --noEmit && vite build`), `preview`.

### Environment variables (`.env.example` / `.env.local`)

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Neon Postgres (or any SQLAlchemy URL; SQLite in dev/tests) |
| `MASTER_VAULT_KEY` | HMAC key for sessions + dossier seals (32+ bytes; changing resets sessions) |
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client (fatal if unset) |
| `ALLOWED_DOMAINS` | comma list; matches `hd` claim AND email suffix |
| `ALLOWED_EMAILS` | exact-email allowlist |
| `SUPER_ADMINS` | override list; fallback = hardcoded demo admins |
| `KEEPALIVE_INTERVAL` | Neon pinger seconds (0 = off) |
| `FACE_EMBED_MODEL` | path to ArcFace/FaceNet `.onnx` (else dHash) |
| `AI_DETECTOR_PROVIDER` | `sightengine` \| `self-hosted` \| blank ⇒ heuristic |
| `AI_DETECTOR_KEY / ENDPOINT / MODELS` | cloud detector config |
| `AI_DETECTOR_MODEL_URL / MODEL_DIR` | self-hosted ViT ONNX download |
| `YOLO_ROI_ONNX_PATH` | `app/models/card.onnx` (auto-if-present) |
| `AADHAAR_FIELDS_ONNX_PATH` | `app/models/aadhaar_fields.onnx` |
| `GEMINI_API_KEY / GEMINI_MODEL` | `/api/chat` Gemini (code) |

### Repo-level configs

- `vercel.json` — rewrite all → `api/index.py`; `maxDuration 60`.
- `.vercelignore` — strips `scripts/ tests/ data/ *_backup new .venv .env* .vercel .git *.md LICENSE` from the bundle.
- `.gitignore` — ignores `data/`, `runs/`, `weights/`, `*.pt`, `*.onnx`, `app/models/`, `.env*`, caches — weights stay out of Vercel's 128 MB ceiling and out of git.
- `.gitattributes` — LF line endings for source/text; binaries marked binary.
- `.python-version` = `3.12` (local environment ran 3.11.9 — minor mismatch worth noting).
- `START.bat` — one-shot local launcher (installs deps, rebuilds frontend, runs uvicorn on :8000, opens browser).
- Docs: `README.md` (project + env table), `MHA_SCREENING.md` (desk design), `AI_MODELS.md` (model inventory + "how to train your own"), `TRAINING.md` (YOLO/ONNX training notes).

---

## 9. Build-status triage

### ✅ Fully built

- End-to-end 4-module pipeline (extract → validate → tamper → face) with explainable risk scoring and `CLEAR / REVIEW / FLAGGED` verdicts, persisted as an immutable audit record.
- Google SSO + `ALLOWED_DOMAINS/EMAILS` + `SUPER_ADMINS` gate + super-admin role approvals + HMAC sessions.
- Hash-only watchlist with unique-hash dedup and accidental-plaintext immunity.
- Adjudication workflow; HMAC-sealed court dossiers; SHA-256-tailed shift-log CSV.
- ICAO 9303 MRZ (TD1/TD2/TD3) + check digits; PAN / Driving Licence / EPIC / Passport / Visa validators with real checksum logic.
- ELA, 2D-FFT spectral, PRNU noise-consistency, image QA, YOLO ROI overlay, and (present) webcam-liveness helpers.
- YOLOv8s `card.onnx` trained (mAP50 0.986) and **wired into M3** as ROI chips/overlay.
- Face module M4 (ArcFace-on-FaceMatch when model present; dHash always).
- Gemini `/api/chat` (codebase-grounded) with offline `knowledge.ts` fallback; Explain Mode; specimen presets; single-file React console.
- Full pytest suite green: **95 passed, 1 skipped**.

### 🟡 Partially scaffolded

- **Aadhaar field detector** — trained (mAP50 0.995, 5 classes) and exported to `app/models/aadhaar_fields.onnx`, and `extract_aadhaar_fields()` implemented + verified on a real Aadhaar sample, but **no endpoint or UI consumes it**; `aadhaar` is excluded from `SCREEN_DOC_TYPES`; class-name mapping is provisional pending a human eyeball.
- **ArcFace** — code path complete, but requires `FACE_EMBED_MODEL` + `onnxruntime` on a worker; live demos currently run the dHash fallback.
- **Self-hosted ViT detector / Sightengine** — fully coded, gated behind env; the default is the heuristic.
- **Neon Postgres** — pooling, retries, keepalive, idempotent migrations all present; the sandbox cannot reach the network, so SQLite is what runs in tests/dev.
- **Frontend** — single officer-console view; the broader public/analytics/charts/verify-panel/verdict-card views were removed earlier.

### ❌ Missing / intentionally de-scoped

- External/immutable audit ledger (blockchain or hash-chained checksum chain) — de-scoped in the de-blockchain pass; tamper-evidence today = HMAC dossier seal + signed shift CSV + the `ScreeningReport` row itself.
- National-ID (Aadhaar) OCR **route** — the trained model exists; the endpoint/UI doesn't.
- Interactive (challenge-response) liveness — only a single still is captured today.
- `onnxruntime` on Vercel — by design; the models run on local/worker machines.
- Committed weight files — by design (gitignored; auto-download or path via env).

---

## 10. Thinking notes & deltas discovered during the audit

- **The backend became a "two source files + support modules" architecture.** `app/main.py` is 2,167 lines and carries the DB layer, auth, the fast path, the AI-content-detector orchestration *and* all routes. `app/screening.py` (664 lines) carries the 4-module orchestrator and the risk model. The docstring literally says the headed "6 provider" AI layer is folded in so the backend is "exactly two source files".
- **The `/api/screen` evaluator back-door is intentional and visible:** `get_current_admin_or_evaluator` falls back to `evaluator@ssb.gov.in` so anonymized evaluators can screen in demos — but the same dependency also powers `queue` and `report detail`, so unsigned users see every report's `masked_fields` (masked, never raw). Worth re-verifying against the actual demo threat model: this is a deliberate trade-off, not a leak.
- **`ProjectChatbot.tsx`'s header comment claims a "scoped Gemini with full codebase ingestion",** which matches `_gemini_reply` + `codebase_context`, while `knowledge.ts` bills the chatbot as fully offline — both are true: Gemini when `GEMINI_API_KEY` is present, offline KB otherwise.
- **`ledger_status` is a ghost column.** All paths set `"LOCAL"`; the "ledger" system (and its docs `HASHING_KEYS_AND_MODELS.md`, `VERIFICATION_PROVIDERS.md`) was removed. `api.ts` still types `ledger_status: string` on `ScreenReport` and keeps `screenDocument` naming — harmless, but any future "ledger" feature must be re-architected.
- **Risk model is rule-weight based, not ML-produced.** Starting risk 20, ±deltas per deterministic check; the AI detectors contribute signals + a `document_aware` gate but do not set the score directly. This is a deliberate explainability choice.
- **`app/main.py` still carries architectural commentary about a codebase-restructure goal** (columns, inlined detector sections, `docs` references) while the *actual* refactor has already happened — some inline claims (e.g. "the backend is exactly two source files") only hold at the module level, and `validation.py`/`identity.py`/`mrz.py` are separate files feeding M2. Minor doc drift.
- **`.python-version` (3.12) vs the local interpreter (3.11.9)** — deployment pins differ from the training/run env; not currently breaking anything.
- **Two `main.py` shims** (`api/index.py`, root `main.py`) both re-export `app.main.app`; `api/index.py`'s own docstring says Preset = Other while `main.py` says native detection. They coexist fine; keep both in sync if you ever rename the app factory.

---

## 11. Open items / pending decisions

1. **Commit + push** — the working tree holds 33 changed/deleted files from the de-blockchain + ArcFace + YOLO passes (no commits yet). Remotes: `origin` (Veri_source) and `crypto-knights`. Awaiting your go-ahead to stage deliberately and split into clean commits.
2. **National-ID (Aadhaar) OCR route** — wire `extract_aadhaar_fields` into an endpoint + UI (probably env-gated or behind a new `doc_type`), and eyeball one prediction strip to confirm the class-name semantics before shipping.
3. **Audit-log checksum chain** — build the append-only per-run SHA-256 checksum chain (file → fields → signals → previous chain) if you want stronger tamper-evidence than the current dossier seal.
4. **`aadhaar` doc-type reintroduction** — currently deliberately absent from the desk; re-add only if the national-ID route lands.
5. **Verify the evaluator scope** — confirm the unsigned `evaluator@ssb.gov.in` fallback is acceptable for queue/report-detail exposure in real deployments, or tighten it to screening-only.