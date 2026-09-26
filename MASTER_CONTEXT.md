# SIH26188: MASTER CONTEXT & ARCHITECTURAL BLUEPRINT
**Target Agent:** Anti-Gravity / OpenCode / Any Autonomous Coding Agent
**Project:** AI-Based Fake Identity & Document Screening System
**Organization:** Ministry of Home Affairs — Sashastra Seema Bal (SSB), Police II Division
**Category:** Software | **Theme:** Blockchain & Cybersecurity
**Deadline Context:** Idea submission window closes 30 September 2026; SIH 2026
**Source of Truth:** Full-codebase architecture audit (verified against actual source paths, signatures, and metrics)

---

## 🛑 AGENT INSTRUCTION PROMPT 🛑

**Read this carefully before executing any tasks.**

You are operating as a Senior AI/Cybersecurity Architect assisting with Smart India Hackathon 2026 (Problem Statement SIH26188).

1. Your goal is to construct a "God-Tier", production-ready system that strictly adheres to the architecture outlined in this document and the verified codebase reality.
2. **ACTIVE RESEARCH MANDATE:** If you encounter a missing library, an unfamiliar algorithm (ELA, ArcFace, PRNU, ICAO 9303 MRZ check digits, YOLOv8 ONNX export, FastAPI dependency injection, React single-file Vite build, etc.), or need the latest documentation for FastAPI, React, YOLOv8, ONNX Runtime, Pillow, NumPy, SQLAlchemy, Google OAuth, Gemini, or any other component, **you MUST autonomously use your internet search tools to look up the most up-to-date information before writing or modifying code.** Do not guess API signatures, model input shapes, or threshold values.
3. Prioritize:
   - Offline-first capabilities (border posts have low-to-zero connectivity)
   - Zero-storage privacy (no raw image bytes, no plaintext identifiers ever persist)
   - Immutable / tamper-evident audit logs (hash-chain or HMAC seals)
   - Explainable risk scoring (officers need evidence, not black-box "Fake/Real")
   - Graceful degradation (ONNX models optional; heuristic + Pillow paths always work)
4. The previously open items (age-aware thresholds, hash-chain ledger, Aadhaar fields route, challenge-response liveness) have been implemented. When extending further, keep the existing 4-module pipeline, masking, session model, and zero-raw-storage invariants intact.
5. All code changes must remain compatible with the current Vercel deployment topology and the local SQLite / Neon Postgres dual path.

---

## 1. PROBLEM STATEMENT DATA (SIH26188) — COMPLETE

### 1.1 Official Metadata
- **S.No.:** 188
- **PS Number:** SIH26188
- **Title:** AI-Based Fake Identity & Document Screening System
- **Organization:** Ministry of Home Affairs
- **Department:** Sashastra Seema Bal (SSB), Police II Division
- **Category:** Software
- **Theme:** Blockchain & Cybersecurity
- **Deadline for Idea Submission:** 30 September 2026
- **Dataset Link:** N/A
- **Contact Info:** N/A

### 1.2 Background & Operational Reality
Common challenges faced at border checkpoints (SSB primarily guards the Indo-Nepal and Indo-Bhutan land borders):
- Fake passports and visas
- Altered photographs / photo replacement
- Modified dates of birth
- Tampered visa stamps
- Identity impersonation
- Multiple identities used by the same person
- Expired or blacklisted travel documents
- High passenger volume causing delays

Current verification methods rely heavily on human inspection and basic database lookups. Checkpoints are often remote, dusty, with intermittent or zero internet connectivity. Officers process thousands of identity documents daily (passports, visas, national identity cards, permits, travel authorizations). Manual verification is time-consuming, error-prone, and weak against sophisticated digital/physical forgeries.

Real-world incidents (public reporting) confirm ongoing threats: fake exit stamps, forged Aadhaar used by foreign nationals, Chinese/Bangladeshi/Myanmar nationals intercepted with counterfeit Indian IDs at Panitanki, Raxaul, and other Indo-Nepal posts.

### 1.3 Detailed Description (Official)
Border checkpoints process thousands of identity documents every day, including passports, visas, national identity cards, permits, and travel authorizations. Manual verification is time-consuming, prone to human error, and often unable to detect sophisticated forgeries, tampering, or identity fraud. Develop an AI-powered document screening platform that automatically analyzes identity and travel documents, detects signs of tampering or forgery, validates information against rules and databases, and generates a risk score to assist border security personnel in making faster and more accurate decisions.

### 1.4 Expected Solution — Four Mandatory Modules
**Module 1: OCR Extraction**  
Objective: Automatically extract all relevant information from identity documents.  
Inputs: Passport image, Visa image, National ID image, Driving license, Permit documents.  
Extracted Fields (examples):  
- Passport: Name, Passport Number, Nationality, Date of birth, Date of expiry, Gender  
- Visa: Visa Number, Visa Type, Entry Validation, etc.  
- National ID / DL / Voter ID / Aadhaar-style: Name, DOB, Gender, ID Number, Photo region, etc.

**Module 2: Document Validation**  
Checksums, format rules, MRZ logic (ICAO 9303), expiry checks, serial plausibility, watchlist hits, travel-validity rules (e.g., six-month rule).

**Module 3: Tampering Detection**  
Physical and digital manipulation: JPEG re-compression anomalies (ELA), spectral/FFT artifacts, noise/PRNU inconsistency, AI-generation signatures, ROI-level analysis.

**Module 4: Face Detection / Verification**  
Match the portrait on the document to a live webcam still of the person presenting it. Support age-aware thresholds where possible.

### 1.5 Who Will Use It & Where
- **Primary users:** SSB border-screening officers / desk personnel at land checkpoints on Indo-Nepal and Indo-Bhutan borders.
- **Secondary users:** Supervisors / super-admins for adjudication, watchlist management, syndicate pattern alerts, shift-log export, and court-ready dossiers.
- **Environment constraints:** Low/zero internet, high volume, dusty, need for offline operation, privacy (no raw PII or images stored), human-in-the-loop adjudication, explainable outputs for legal defensibility.
- **Deployment target:** Edge/local worker or lightweight serverless (Vercel-compatible) with optional Neon Postgres; heavy ONNX models run only where `onnxruntime` is present.

### 1.6 Core Non-Functional Requirements (Inferred + Implemented)
- Privacy-by-design: SHA-256 of file + masked identifiers only; no raw bytes or plaintext IDs in DB.
- Auditability: Immutable ScreeningReport rows + HMAC-sealed dossiers + optional hash-chain.
- Explainability: Granular 0–100 risk score with per-check reasons, interactive ELA heatmaps, spectral PAPR, PRNU ratios, YOLO ROI chips.
- Graceful degradation: Heuristic + Pillow paths always available; ONNX (YOLO, ArcFace, ViT) optional.
- Rate-limited, role-gated API with Google SSO + domain/email allow-lists + super-admin bypass.

---

## 2. COMPETITIVE ANALYSIS (30+ TEAM AGGREGATION)

**Note on intelligence quality:** Public pitch videos, demo reels, and early repositories for SIH26188 are sparse at the time of this blueprint (idea window still open). The analysis below synthesizes:
- Patterns observed across similar document-fraud / ID-verification hackathon and commercial solutions,
- Typical student-team architectural choices for OCR + biometrics + "blockchain" themed problems,
- The strategic weaknesses that a production-grade offline-first system can exploit,
- and the explicit differentiators already present in our verified codebase.

This is strategic competitive intelligence for winning, not a claim of having watched 30 specific SIH videos.

### 2A. The Top Direct Threat Archetypes (Deep Dives)

**1. Cloud-Heavy OCR + Basic ELA Teams (majority pattern, ~60–70%)**  
*Typical stack:* Tesseract / PaddleOCR / EasyOCR + AWS Rekognition / Google Vision / Azure Form Recognizer + simple ELA or CNN copy-move + FaceNet/ArcFace cloud or lightweight. React dashboard with Low/Medium/High risk.  
*Output:* Binary or coarse risk + basic dashboard.  
*Fatal flaw at SSB posts:* Requires reliable internet; cloud APIs are unreachable or latency-intolerable. Privacy risk of sending images to third parties.  
*How we beat them:* 100% local ONNX + Pillow/NumPy forensics; zero raw image persistence; granular explainable score + interactive heatmaps.

**2. Age-Aware / Threshold-Adaptive Face Teams**  
*Typical novelty:* Recognise that a 9-year-old passport photo will fail strict cosine thresholds; dynamically lower match threshold based on document age.  
*How we beat / absorb them:* Implement the same age-aware logic inside our local `face_match.py` / `face.py` ONNX path (ArcFace cosine + dHash fallback) while keeping the entire pipeline offline-first and privacy-preserving.

**3. Passport-Only / MRZ-Centric Teams (~80% tendency)**  
*Typical focus:* Heavy investment in ICAO 9303 MRZ parsing for international passports; weak or missing support for domestic Indian IDs (Aadhaar-style, Voter ID, DL).  
*Fatal flaw:* Indo-Nepal / Indo-Bhutan traffic is dominated by domestic documents.  
*How we beat them:* Custom YOLOv8s `card.onnx` (mAP50 0.986) + `aadhaar_fields.onnx` (mAP50 0.995, 5 classes: Name/DOB/Gender/Aadhaar_No/Photo) already trained and verified; full PAN/DL/EPIC/Passport/Visa validators with real checksums.

**4. "Offline-First" Claim Teams**  
*Typical claim:* Bundle models for edge.  
*How we beat them:* Our entire stack (FastAPI + single-file React SPA + optional ONNX) already runs with graceful degradation; Vercel-safe heuristics always available; models gitignored and path-configurable.

**5. HITL / Explainability-Focused Teams**  
*Typical strength:* Officers can see *why*.  
*How we beat them:* Interactive ModuleScorecard with toggled ELA heatmap, 2D-FFT spectral, PRNU noise consistency, YOLO ROI overlay chips, per-check reason list, and HMAC-sealed court dossier.

**6–30. Aggregate Patterns of the Remaining Field**
- **Cloud Trap (~70%):** AWS/GCP/Azure wrappers → unusable offline.
- **Passport Trap (~80%):** MRZ-only → fails domestic ID volume.
- **Blockchain Ignorance (~85%):** Theme is "Blockchain & Cybersecurity" yet most use plain Postgres with no cryptographic linkage → silent deletion possible. Our response: HMAC dossier seals + SHA-256-tailed shift CSV + designed (but currently de-scoped) append-only hash-chain; `ledger_status` column retained as inert "LOCAL".
- **Black-Box Trap (~60%):** "Fake/Real" binary → legally insufficient for border officers. Our response: 0–100 explainable risk starting at 20, adjusted by deterministic deltas + AI signals.
- **No Privacy Hygiene:** Many store raw images or plaintext IDs. Ours: only file SHA-256, masked fields (`****1234`), never raw bytes.
- **No Adjudication / Syndicate / Shift Export:** Missing human-in-the-loop, cross-checkpoint pattern detection, and chain-of-custody CSV.
- **Aadhaar Avoidance or Naïve OCR:** Either ignore national ID or treat it as generic text. We have a trained 5-class field detector ready for wiring.

**Winning strategy summary:** Offline-first + domestic-ID YOLO + explainable forensics + privacy-by-hash + HITL adjudication + optional cryptographic seal. Most competitors will lose on at least two of these axes.

---

## 3. THE "GOD-TIER" TARGET ARCHITECTURE (VERIFIED AGAINST CODE)

This section is the authoritative blueprint. Paths, signatures, metrics, and behaviour are taken from the live codebase audit.

### 3.1 Repository Layout & Deployment Topology
```
D:\mos\crypto\  (or equivalent)
├── main.py                  # Root ASGI shim → re-exports app.main.app (Vercel native FastAPI)
├── api/index.py             # Vercel serverless entry (Preset=Other) → same re-export
├── app/                     # Python backend package
│   ├── main.py              # ~2167 lines — FastAPI app, DB models, auth, inlined AI detectors
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
│   ├── transliterate.py     # Devanagari → Latin + fuzzy name matching
│   ├── yolo_roi.py          # YOLOv8 ONNX locator (card.onnx / aadhaar_fields.onnx) + CV heuristics
│   ├── codebase.py          # repo index injected into Gemini /api/chat context
│   ├── static/index.html    # 294 KB single-file React build (Vite singlefile) served at /
│   └── models/              # gitignored ONNX weights (auto-loaded defaults)
├── frontend/src/            # React 18 + TS + Vite source
│   ├── App.tsx · main.tsx · api.ts · knowledge.ts
│   ├── views/AuthorityView.tsx (1415 lines) · gsi.ts
│   ├── components/ui.tsx · ProjectChatbot.tsx
│   └── app/state.tsx · explain.tsx · motion.tsx · theme.ts · specimens.ts · util.ts
├── scripts/                 # training corpus builders + train_yolo.py (local GPU)
├── tests/                   # pytest — 95 passed, 1 skipped
├── requirements.txt         # serverless-safe (onnxruntime deliberately commented out)
├── vercel.json              # rewrite all → api/index.py, maxDuration 60
├── .vercelignore            # strips scripts/tests/data/*.md — keep <128 MB
└── .gitignore               # data/, runs/, weights/, *.pt, *.onnx, .env, models/
```

**Deployment:** Vercel hosts everything. Heavy ONNX runs only on machines that have `onnxruntime`; Vercel path uses heuristics + Pillow. React is compiled by `vite-plugin-singlefile` into one self-contained `app/static/index.html`.

### 3.2 ML Pipeline (Python)

#### 3a. YOLOv8 Document Locator — `app/yolo_roi.py`
Trained with `scripts/train_yolo.py` (YOLOv8s, 129 layers, ~11.1 M params, 28.6–28.7 GFLOPs, 640 px).

| Weight | Classes | Shape | Val Metrics |
|--------|---------|-------|-------------|
| `app/models/card.onnx` | 1 (`Card`) | [1,3,640,640] → [1,5,8400] | mAP50 **0.986** · mAP50-95 **0.928** |
| `app/models/aadhaar_fields.onnx` | 5 (`Name, DOB, Gender, Aadhaar_No, Photo`) | [1,3,640,640] → [1,9,8400] | mAP50 **0.995** · mAP50-95 **0.836** |

Key symbols:
- `_get_onnx_session()` → lazy `onnxruntime.InferenceSession` (CPUExecutionProvider) or None
- `extract_roi_boxes(image_bytes)` → ONNX if available else heuristic stack (face/MRZ/QR/card)
- `extract_aadhaar_fields(image_bytes)` → 5-class model (currently **no endpoint/UI consumer**)

**Wired:** ROI chips + overlay in M3 Tamper panel.  
**Missing:** Aadhaar field route + UI (deliberately excluded from `SCREEN_DOC_TYPES` for now).

#### 3b. ArcFace Identity Matching — `app/face_match.py` + `app/face.py`
- `compare_faces(document_photo, selfie) -> dict` — cosine (ArcFace/FaceNet ONNX) or dHash fallback.
  - Thresholds: `_EMB_SAME=0.60`, `_EMB_DIFF=0.40`; dHash `_DHASH_SAME=8`, `_DHASH_DIFF=20`.
- `face_verification(document_bytes, live_frame, doc_type)` — returns verdict (`PASS/CLEAR/REVIEW/FAIL/UNVERIFIED`), match, score, method, detail, checks.
- Called from `run_screening` with uploaded document + live webcam still (`getUserMedia` → canvas JPEG 0.85).

**Age-aware adaptive thresholding (IMPLEMENTED):** `compare_faces()` now accepts `doc_age_years`. When document age > 4.0 years the ArcFace cosine threshold is dynamically relaxed (down to 0.48) and dHash distance tolerance raised (up to 12). Document issue/holder age is inferred and piped from `face.py` / `screening.py`. Fully unit-tested.

#### 3c. AI-Generation Detectors (inlined in `app/main.py`)
Three backends resolved by `AI_DETECTOR_PROVIDER`:
1. `heuristic` (default) — metadata signatures, pixel scan, document-aware gate.
2. `sightengine` — cloud (needs key).
3. `self-hosted` — ViT-Base Real-vs-AI ONNX (~340 MB, needs onnxruntime).

Public: `detect_image(image_bytes, filename) -> dict` persisted in `ai_detection` column.

### 3.3 Backend API (FastAPI) — 20 Routes (updated)
All in `app/main.py`. Rate-limited via `slowapi`. Auth via HMAC session cookie `nischay_session` (1-day) + Google `id_token` verification.

| Method / Path | Auth | Rate | Purpose |
|---------------|------|------|---------|
| GET / | any | 120/min | Serve single-file React |
| POST /api/admin/login | — | 20/min | Google SSO → session cookie |
| POST /api/admin/logout | any | 20/min | Clear cookie |
| GET /api/admin/me | session | 120/min | Current officer status |
| POST /api/admin/assign_role | super | 20/min | Grant post + institution |
| GET /api/admin/signers | super | 60/min | Officer directory |
| POST /api/screen | officer/evaluator | 60/min | **Main pipeline** (multipart ≤8 MB) |
| GET /api/screen/queue | officer | 120/min | Pending + recent reports |
| GET /api/screen/reports/{id} | owner/super | 120/min | Full masked detail |
| POST /api/screen/reports/{id}/adjudicate | super | 60/min | CLEARED / CONFIRMED_FRAUD / INCONCLUSIVE |
| GET /api/screen/watchlist | super | 120/min | Last 300 hash-only entries |
| GET /api/screen/shift-export | super | 30/min | CSV + `# SHA-256:` trailer |
| GET /api/screen/syndicate-alerts | super | 60/min | Recidivism / multi-checkpoint / burst |
| GET /api/screen/dossier/{id} | super | 60/min | HMAC-sealed printable HTML (+ ledger block hashes) |
| POST /api/screen/watchlist/add | super | 60/min | Hash-only insert |
| POST /api/screen/watchlist/remove | super | 60/min | Delete by id |
| GET /api/screen/ledger/verify | super | 30/min | **NEW** Walk entire chain, verify prev_hash linkage + recompute block hashes |
| POST /api/screen/aadhaar-fields | officer | 60/min | **NEW** Run 5-class YOLO (`aadhaar_fields.onnx`) → Name/DOB/Gender/Aadhaar_No/Photo boxes |
| POST /api/screen/liveness | officer | 60/min | **NEW** Challenge-response multi-frame liveness (blink/nod + motion/variance) |
| POST /api/chat | any | 30/min | Gemini + codebase context (offline KB fallback) |
Delete by id |
| POST /api/chat | any | 30/min | Gemini + codebase context (offline KB fallback) |

**Auth model:** Self-contained HMAC `email::exp::sig`. Super-admins (env or hardcoded demo list) always bypass. Startup hard-fails if `MASTER_VAULT_KEY` or `GOOGLE_CLIENT_ID` missing.

**DB:** Neon Postgres (pooled, keepalive) or SQLite fallback. Models: `SignerIdentity`, `ScreeningReport` (immutable, masked, no raw bytes), `WatchlistEntry` (hash-only).

### 3.4 Screening Pipeline (`app/screening.py:run_screening`)
```
file_hash = sha256(data)
M1 → extraction.extract_document(...)          # PDF/image → OCR + MRZ + translit + declared merge
AI → detect_image(...) + document-aware gate
M2 → validation.validate_document(...)         # format/checksum/MRZ/expiry/watchlist (hash-only query)
M3 → tampering.tamper_analysis(...)            # ELA + spectral + PRNU + QA + YOLO ROI + liveness helpers
M4 → face.face_verification(...)               # ArcFace or dHash
Analyze → explainable reasons[]; risk starts at 20, ±deltas
verdict → CLEAR | REVIEW | FLAGGED
Persist → one immutable ScreeningReport (masked fields only)
```

### 3.5 Image Forensics & Security (`app/forensics.py` + hashing helpers)
- ELA (re-save JPEG diff → heatmap base64)
- Spectral (2D-FFT → PAPR + high-freq ratio)
- Noise consistency / PRNU-style (portrait vs substrate)
- Image QA (megapixels, blur Laplacian variance, exposure)
- ROI boxes via YOLO or heuristics
- Liveness signal helpers (present, not yet in main pipeline)
- **Security skeleton:** sha256 / mask / norm at every boundary. Nothing raw persists. Dossier sealed with `HMAC-SHA256(MASTER_VAULT_KEY, id:file_hash:verdict:risk:created:admin)` **plus ledger block hashes**. Shift CSV ends with `# SHA-256: <digest>`. **Append-only cryptographic hash-chain now live** (`previous_hash` → `ledger_hash` per ScreeningReport; verified by `GET /api/screen/ledger/verify`).

### 3.6 Frontend (React 18 + TypeScript + Vite)
Single officer-console view (`AuthorityView.tsx`). Single-file build.  
Flow: pick file / specimen + doc_type + checkpoint + optional live still → `POST /api/screen` → ModuleScorecard (M1–M4) + risk meter + ELA/spectral/ROI panels → queue / adjudicate / dossier / syndicate / shift export.  
Explain Mode, theme, specimen presets, offline chatbot KB (`knowledge.ts`) with Gemini fallback.

### 3.7 Configurations
- `requirements.txt`: fastapi, uvicorn, sqlalchemy, psycopg2-binary, pypdf, requests, python-multipart, slowapi, google-auth, python-dotenv, numpy, Pillow. **onnxruntime commented out** (local only).
- Key env vars: `DATABASE_URL`, `MASTER_VAULT_KEY`, `GOOGLE_CLIENT_ID`, `ALLOWED_DOMAINS`, `ALLOWED_EMAILS`, `SUPER_ADMINS`, `FACE_EMBED_MODEL`, `AI_DETECTOR_*`, `YOLO_ROI_ONNX_PATH`, `AADHAAR_FIELDS_ONNX_PATH`, `GEMINI_*`.
- `vercel.json`: rewrite all → `/api/index.py`, maxDuration 60.

### 3.8 Build-Status Triage (Updated — Post Implementation Pass)

**Fully built (as of latest agent pass):**
- End-to-end 4-module pipeline + explainable risk + CLEAR/REVIEW/FLAGGED
- Google SSO + role gates + HMAC sessions
- Hash-only watchlist
- Adjudication, HMAC dossiers, SHA-256 shift CSV
- ICAO 9303 MRZ + real validators (PAN/DL/EPIC/Passport/Visa)
- ELA, spectral, PRNU, QA, YOLO ROI (card.onnx wired)
- Face M4 (ArcFace path + dHash always) **+ Age-Aware Adaptive Thresholding**
- **Append-only cryptographic hash-chain ledger** (`GET /api/screen/ledger/verify` + block hashes on dossiers + UI “Verify Chain” button)
- **Aadhaar 5-class YOLO field extraction route + UI chips** (`POST /api/screen/aadhaar-fields`)
- **Interactive challenge-response webcam liveness** (`POST /api/screen/liveness` + LiveCapture wiring)
- Gemini chat + offline KB + Explain Mode + specimens
- Frontend production build clean (`npm run build` → `app/static/index.html`)
- **102 pytest passed, 1 skipped, 0 failures**

**Still environment-dependent / partial:**
- ArcFace quality depends on presence of `FACE_EMBED_MODEL` + `onnxruntime` (dHash always available)
- Self-hosted ViT / Sightengine remain env-gated
- Neon Postgres (code ready; tests use SQLite)
- `onnxruntime` deliberately absent from Vercel requirements (by design)
- Weight files remain gitignored (by design)

**Intentionally de-scoped / residual:**
- Full interactive multi-round liveness challenge UI polish (core endpoint + basic wiring present)
- Re-evaluation of unsigned `evaluator@ssb.gov.in` fallback scope (still deliberate for demos)
- Commit hygiene / clean history (working tree changes exist; stage when ready)

---

## 4. OPEN ITEMS / PENDING DECISIONS (UPDATED)

**Completed in latest pass:**
1. ~~Wire `extract_aadhaar_fields` into endpoint + UI~~ → **DONE** (`POST /api/screen/aadhaar-fields` + 5-Class ID Zones chips)
2. ~~Implement age-aware threshold adjustment~~ → **DONE** (dynamic ArcFace/dHash relaxation for docs > 4 years)
3. ~~Append-only SHA-256 checksum chain~~ → **DONE** (ledger verify endpoint + dossier seals + UI banner)
4. ~~Interactive challenge-response liveness~~ → **DONE** (endpoint + LiveCapture integration)

**Still open / owner decisions:**
1. Confirm Aadhaar class-name semantics with a real prediction strip on diverse samples (provisional labels still in use).
2. Re-evaluate unsigned `evaluator@ssb.gov.in` fallback scope for queue/report visibility in production deployments.
3. Commit hygiene: stage the de-blockchain + ArcFace + YOLO + ledger + liveness changes into clean, reviewable commits.
4. Optional future hardening: stronger multi-round liveness UI, continuous chain monitoring alerts, or external notarization of the ledger root.
5. Any new feature must continue to preserve zero-raw-storage, offline heuristics, and the existing risk-explainability model.

---

## 5. FINAL AGENT REMINDER
- Always research before coding unfamiliar APIs or model shapes.
- Prefer local/offline paths.
- Never store raw images or plaintext identifiers.
- Keep risk scores explainable and officer-actionable.
- Match or exceed the competitive differentiators listed above.
- When in doubt, read the actual source files (`app/main.py`, `app/screening.py`, `app/yolo_roi.py`, `app/face_match.py`, `app/forensics.py`, `frontend/src/api.ts`, `frontend/src/views/AuthorityView.tsx`) — they are the ground truth.

This document is the single source of architectural truth for SIH26188. Use it to keep every generation, refactor, and extension aligned with a production-ready, privacy-first, offline-capable, explainable border-screening system.
