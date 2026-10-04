# Vibe Check Point — AI-Based Fake Identity & Document Screening

**Team:** crypto_knights  ·  **SIH26188** — AI-Based Fake Identity & Document Screening

> One-liner: *At a border inspection desk (a Vibe Check Point), an officer uploads an identity document
> (passport / visa / driving licence / PAN / voter ID) plus an optional live face capture.
> A four-module forensic pipeline — extract, validate, tamper-detect, face-match — returns a
> risk score and a CLEAR / REVIEW / FLAGGED verdict with one explainable reason per risk
> point, and produces a court-admissible dossier.*

---

## Table of Contents

1. [The Problem](#1-the-problem)
2. [The Solution](#2-the-solution)
3. [How Screening Works — The Four Modules](#3-how-screening-works--the-four-modules)
4. [Architecture](#4-architecture)
5. [Code Map](#5-code-map)
6. [Security & Privacy Model](#6-security--privacy-model)
7. [API Reference](#7-api-reference)
8. [Setup & Run](#8-setup--run)
9. [Deploying to Vercel](#9-deploying-to-vercel)
10. [Judge Q&A](#10-judge-qa)

---

## 1. The Problem

Border checkpoints handle hundreds of identity documents per shift. Forged passports,
tampered visas, cloned driving licences and PAN cards travelling under different names are
the currency of cross-border crime — yet the frontline decision is usually a tired officer
holding a document up to the light. Static rules miss:

- **Forged documents** — re-printed, re-saved, or digitally edited before printing.
- **Tampered genuine documents** — an authentic passport whose data page or portrait has been
  altered or digitally spliced.
- **Impostors** — a person carrying someone else's genuine document.

Misjudged identities don't just slip through once; the same numbers resurface at other
checkpoints, which is exactly how illegal cross-border networks operate.

## 2. The Solution

A screening console where every officer decision is supported by hard forensics instead of
eyeballing:

1. **Any document in, numbers out.** Upload a photo or PDF; the document's text, MRZ and
   declared fields are extracted automatically — nothing is stored on disk.
2. **Rule-based validation.** Check digits (ICAO 9303 MRZ), document-number formats (PAN,
   DL, Voter ID checksum rules), expiry, the six-month travel rule, and a hash-only watchlist.
3. **Digital tamper forensics.** ELA, 2D-FFT spectral analysis, and PRNU noise show *where*
   the document was re-saved or spliced — visible heatmaps, not just a number.
4. **Face match.** A live webcam capture of the person is compared against the document
   portrait to catch impostors.
5. **Human-in-the-loop.** AI produces a verdict — CLEAR / REVIEW / FLAGGED — with one
   explainable reason per risk point; a supervisor adjudicates. Every run is attributed to
   the screening officer and recorded in an audit trail.
6. **Court-admissible dossier.** Each report has a printable, HMAC-sealed dossier for legal
   proceedings.

## 3. How Screening Works — The Four Modules

| Module | What it does | Key signals |
|---|---|---|
| **M1 Extract** | Reads all text from the document — printed fields, the MRZ at the bottom of passports, and any declared numbers, from photos (Pillow) or PDFs (PyPDF). | OCR, MRZ lines, document-aware capture |
| **M2 Validate** | Checks the data, not just the pixels: MRZ check digits, document-number format, expiry dates, the six-month travel rule, travel validity, and a hash-only watchlist hit. | ICAO 9303 check digits, P&L/Voter-ID checksum rules, `travel_validity` |
| **M3 Tamper** | Three digital forensics on the image: Error Level Analysis (re-saved JPEG regions), 2D-FFT spectral (unnatural pixel patterns), and PRNU noise (digitally spliced portrait), with a YOLO ROI pre-check. | ELA heatmap Δ, PAPR, noise ratio, ROI labels |
| **M4 Face** | Compares the document portrait with a live camera capture of the person standing at the desk. | face-embedding cosine similarity (or perceptual dHash fallback) |

Output: `risk_score` (0–100) + verdict `CLEAR | REVIEW | FLAGGED` + per-reason `reasons[]`,
plus a four-module scorecard. Supervisors escalate non-clear results via `adjudicate`
(`CLEARED | CONFIRMED_FRAUD | INCONCLUSIVE`).

A **Cross-Border Syndicate Monitor** additionally analyses all recent screenings across
checkpoints for organised-fraud patterns: the same identity used at multiple posts, a cluster
of suspicious documents from one origin, or an individual flagged repeatedly.

## 4. Architecture

```
 [ Officer console (React + Vite, single-file build) ]
    ├─ Google single sign-in → session cookie (HttpOnly, HMAC-signed)
    ├─ Screening desk: doc + doc-type + checkpoint + declared number + live frame
    └─ Super-admin: adjudication queue, watchlist, role approvals, shift export

 [ Backend (FastAPI + SQLAlchemy / PostgreSQL) ]
    /api/screen            4-module pipeline → ScreenReport
    /api/screen/queue      pending/recent screening queue
    /api/screen/adjudicate supervisor verdict (human-in-the-loop)
    /api/screen/dossier    HMAC-sealed printable court dossier
    /api/screen/syndicate  cross-checkpoint pattern alerts
    /api/screen/watchlist  hash-only watchlist (add/remove/list)
    /api/screen/shift-export signed CSV shift log
    /api/chat              rule-based officer assistant (offline knowledge base)
    /api/admin/*           login, logout, me, assign_role, signers

 [ Screening engine (app/) ]
    screening.py  syndicate.py  forensics.py  identity.py  face.py
    mrz.py        validation.py tampering.py  transliterate.py
    extraction.py yolo_roi.py   face_match.py codebase.py
```

**Zero-storage discipline:** document bytes and live captures are processed in memory and
never written to disk; the audit trail and watchlist store only hashes and *masked*
identifiers (e.g. `PAN: ABCT…23`, never the naked number).

## 5. Code Map

| File | Role |
|---|---|
| `app/main.py` | FastAPI app: admin auth (Google SSO / HMAC session), screening routes, adjudication, dossier, chat. |
| `app/screening.py` | The 4-module pipeline orchestrator and risk scoring. |
| `app/syndicate.py` | Cross-checkpoint syndicate / recidivism alert engine. |
| `app/forensics.py`, `app/tampering.py` | ELA / spectral / PRNU / YOLO ROI tamper detection. |
| `app/face.py`, `app/face_match.py` | Face comparison (embedding model or dHash fallback). |
| `app/mrz.py`, `app/validation.py` | ICAO 9303 MRZ parsing/check digits + document-number rules. |
| `app/identity.py`, `app/extraction.py` | PAN/DL/Voter-ID detection and text extraction (Pillow/pypdf). |
| `app/session.py` | Session orchestration, cross-document comparison, ledger block chaining. |
| `app/keys.py` | Key loading, sub-key derivation, rotation window. No defaults. |
| `app/qr_decoder.py` | Barcode/QR decode and Aadhaar Secure-QR parsing. |
| `app/yolo_roi.py`, `app/doctype_cls.py`, `app/doc_forgery.py` | ONNX ROI detection, doc-type classification, dual-stream forgery. |
| `app/codebase.py` | Architecture index and source retrieval for the officer assistant. |
| `app/config.py`, `app/guide.py`, `app/stats.py` | Checkpoint/document catalogs, guided protocol, aggregates. |
| `frontend/src/views/DeskView.tsx` | Officer console: intake, capture, the 4-module scorecard, decision bar. |
| `frontend/src/views/ReviewQueueView.tsx` · `LedgerView.tsx` | Supervisory adjudication; hash-chain block explorer. |
| `frontend/src/views/StaffView.tsx` · `WatchlistView.tsx` | Officer directory / role grants; hash-only watchlist. |
| `frontend/src/views/GoogleSignIn.tsx` · `ChatModal.tsx` | Google Identity sign-in gate; officer assistant. |
| `frontend/src/api.ts` | Typed API client. |
| `app/static/index.html` | Built frontend (Vite single-file), served by the backend. |

## 6. Security & Privacy Model

- **Google SSO + hard gate.** Officers authenticate via Google Identity Services; the
  `id_token` is verified server-side against `GOOGLE_CLIENT_ID`. Access is decided by
  configuration only: `ALLOWED_DOMAINS` / `ALLOWED_EMAILS` gate sign-in, and `SUPER_ADMINS`
  holds the addresses with root clearance. **All three default to empty, which means nobody
  can sign in** — a misconfigured deployment is inaccessible, not open. There is no
  hardcoded fallback list, and no substring or pattern matching: only an exact address match
  grants admin rights.
- **Screening duty is granted, never self-claimed.** A first sign-in has no role and is
  blocked from screening until a super-admin assigns post & institution via
  `/api/admin/assign_role` (the officer directory in the UI).
- **No baked-in secrets.** `DATABASE_URL` and `MASTER_VAULT_KEY` are required; the app
  refuses to start without them, and refuses a key shorter than 32 bytes rather than
  padding or truncating a weak one. Session tokens and evidence seals are signed with two
  *separately derived* sub-keys, so a signature from one context cannot be replayed in the
  other. Roll the key forward by setting `MASTER_VAULT_KEY_PREV` to the outgoing key, which
  is then accepted for verification only.
- **Stateless, constant-time sessions.** Login cookies are `email::expiry::HMAC(...)`,
  verified with `hmac.compare_digest`, `HttpOnly`, `SameSite=Lax` (`Secure` in production).
  The identity row is re-read on every request, so revocation, role changes and account
  removal take effect immediately — a deleted account's cookie stops working at once.
- **Every route is authenticated.** There is one auth gate (`get_current_admin`) and no
  anonymous fallback. The liveness probe and the signed public notice feed are the only
  unauthenticated surfaces, and the probe returns nothing operational without a session.
  `tests/test_authz.py` asserts this for the whole registered route table, and fails if a
  newly added route is not explicitly classified as public or protected.
- **Zero PII at rest.** Screenings store masked fields only; the watchlist stores SHA-256
  hashed identifiers; no document bytes or images are persisted. Unmasked fields are held
  *only while a session is open*, so the desk can cross-compare documents, and are wiped on
  close, flag, adjudication and document-removal — plus a TTL sweep
  (`RAW_FIELD_TTL_MINUTES`) for sessions abandoned mid-shift. They are withheld from API
  responses unless a supervisor asks for them.
- **Rate limiting** via slowapi on auth and screening routes; WAF-grade response headers
  (`nosniff`, `DENY` framing, HSTS). CORS is an exact-origin allow-list (`CORS_ORIGINS`);
  the default same-origin deployment needs none. Note that the limiter is per-process
  unless you set `REDIS_URL`, since each serverless instance keeps its own counters.
- **The officer assistant is a cloud LLM.** `/api/chat` sends the question plus a retrieved
  slice of this repository's source to Google Gemini. It requires a signed-in officer, and
  the security-critical files (`app/main.py`, `app/keys.py`, `app/session.py`,
  `api/index.py`, `scripts/anchor_ledger.py`) and any `.env` are excluded from that
  retrieval. Unset `GEMINI_API_KEY` and a static offline guide is used instead.

## 7. API Reference

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/admin/login` | — | Google OAuth ID token → `SignerIdentity` + HttpOnly session |
| `POST /api/admin/logout` | cookie | Clear session |
| `GET /api/admin/me` | cookie | Officer profile: name, role, `pending_approval`, `is_super_admin` |
| `POST /api/admin/assign_role` | **super-admin** | Assign/approve an officer's post & institution |
| `GET /api/admin/signers` | **super-admin** | Officer directory for role approvals |
| `POST /api/screen` | cookie (approved role) | Run the 4-module screening on a document (+ optional live frame) |
| `GET /api/screen/queue` | cookie | Pending (supervisor) + recent screenings |
| `GET /api/screen/reports/{id}` | cookie | Queue-shaped summary for one report |
| `POST /api/screen/reports/{id}/adjudicate` | **super-admin** | CLEARED / CONFIRMED_FRAUD / INCONCLUSIVE |
| `GET /api/screen/watchlist` | **super-admin** | Hash-only watchlist entries |
| `POST /api/screen/watchlist/add` | **super-admin** | Hash an identifier + reason onto the watchlist |
| `POST /api/screen/watchlist/remove` | **super-admin** | Remove a watchlist entry |
| `GET /api/screen/syndicate-alerts` | cookie | Cross-checkpoint pattern alerts (optional checkpoint filter) |
| `GET /api/screen/shift-export` | **super-admin** | Signed CSV shift log |
| `GET /api/screen/dossier/{id}` | cookie (owner or super) | Printable HMAC-sealed court dossier (HTML) |
| `POST /api/chat` | cookie | Officer assistant — **cloud LLM** (Gemini), with retrieved source context |

### Border sessions (one traveller = one session)

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/sessions` | cookie (approved role) | Open a traveller session |
| `GET /api/sessions` | cookie | Session list (scoped; supervisors see all) |
| `GET /api/sessions/{id}` | owner or **super-admin** | Session + documents + cross-document comparison |
| `POST /api/sessions/{id}/close` | owner or **super-admin** | `approve` / `flag` / `close`; approve signs the ledger |
| `POST /api/sessions/{id}/adjudicate` | **super-admin** | CLEARED / CONFIRMED_FRAUD / INCONCLUSIVE on a flagged session |
| `POST /api/sessions/{id}/documents/{rid}/remove` \| `/restore` | owner or **super-admin** | Soft-remove / restore a document (audit row + chain preserved) |
| `POST /api/sessions/close-unused` | cookie | Close open sessions with zero documents |
| `POST /api/sessions/sweep-raw-fields` | **super-admin** | Wipe raw fields from sessions idle past `RAW_FIELD_TTL_MINUTES` |

### Ledger, evidence & threat picture

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /api/screen/ledger/verify` | cookie | Replay and verify the whole hash chain |
| `POST /api/screen/ledger/anchor` | cookie | Publish an external notarisation anchor |
| `GET /api/screen/ledger/anchor` | cookie | Latest anchor + drift vs the current head |
| `GET /api/sessions/ledger/blocks` \| `/verify` | cookie | Session-level ledger blocks and chain check |
| `GET /api/screen/bsa65b/{session_id}` | owner or **super-admin** | BSA 2023 §63/§65B electronic-evidence certificate (HTML) |
| `GET /api/screen/handover/{session_id}` | owner or **super-admin** | Signed shift-handover token (2D-QR packet) |
| `GET /api/border/threat_matrix` | cookie | Cross-checkpoint threat posture |

### Extraction, verification & reference data

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/extract` | cookie | Live-field extraction from a captured frame (no ledger write) |
| `POST /api/screen/aadhaar-fields` | cookie | 5-class Aadhaar zone detection |
| `POST /api/screen/liveness` | cookie | Challenge-response webcam liveness |
| `POST /api/verify` | cookie | Digest lookup for a previously screened document |
| `POST /api/verify/dl` | cookie | Driving-licence structure + registry credential check |
| `POST /api/verify/aadhaar-qr` | cookie | Decode an Aadhaar QR/barcode |
| `GET /api/checkpoints` \| `/api/guide` | cookie | Checkpoint clusters, document catalog, guided protocol |
| `GET /api/stats/overview` \| `/api/analytics` \| `/api/analytics/summary` | cookie | Operational dashboards |
| `GET /api/admin/revoke_officer` \| `/unrevoke_officer` \| `/remove_officer` | **super-admin** | Revoke, restore or delete an officer account |
| `GET`/`POST` `/api/broadcasts*` | read: public · write: **super-admin** | Signed public notice board |
| `GET /api/ml/status`, `POST /api/ml/keepalive/ping` | cookie | Remote ML microservice health / wake-up |
| `GET /api/health` | public | Liveness only; full detail requires a session |

## 8. Setup & Run

```bash
git clone <repo-url> && cd Vibe-Check-point
python -m venv .venv
.venv\Scripts\activate                 # Windows (Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                # then fill in DATABASE_URL, MASTER_VAULT_KEY,
                                      # GOOGLE_CLIENT_ID and SUPER_ADMINS
python -m uvicorn app.main:app --port 8000
```

Running the test suite (`tests/conftest.py` pins a throwaway SQLite database and an
ephemeral key, so a test run can never touch a real deployment). That SQLite is
**test-only** — it lets the suite run without a Postgres server, and the app
refuses to start on it in any deployment:

```bash
python -m pytest tests/ -q
```

Or double-click **START.bat** (Windows), which installs Python + npm deps, rebuilds the
single-file frontend, and starts the server on http://127.0.0.1:8000.

**Environment variables** (`.env`, gitignored — see `.env.example` for the annotated set):

> The app **refuses to start** without `DATABASE_URL`, `MASTER_VAULT_KEY` (minimum 32 bytes,
> never padded or truncated) and `GOOGLE_CLIENT_ID`. With all three authorisation lists empty
> nobody can sign in — set `SUPER_ADMINS` before first run or you will lock yourself out.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | **yes** | SQLAlchemy URL (PostgreSQL / Neon recommended). No default DSN exists. |
| `MASTER_VAULT_KEY` | **yes** | 32+ byte master key. Session tokens and evidence seals use separately derived sub-keys. |
| `MASTER_VAULT_KEY_PREV` | no | Outgoing key during rotation — accepted for **verification only**. |
| `GOOGLE_CLIENT_ID` | **yes** | Google OAuth 2.0 client (GSI + backend ID-token verification). No fallback. |
| `SUPER_ADMINS` | no | Comma-separated exact addresses with root clearance. **Defaults to empty.** No substring matching. |
| `ALLOWED_DOMAINS` / `ALLOWED_EMAILS` | no | Sign-in allow-list driven by Google Cloud. |
| `CORS_ORIGINS` / `ALLOW_DEV_CORS` | no | Exact browser origins allowed to call the API. Same-origin deployments need neither. |
| `REDIS_URL` / `KV_URL` | no | Shared rate-limit store. Without it the limiter is per-process (each serverless instance has its own). |
| `RAW_FIELD_TTL_MINUTES` | no | Idle time before a supervisor sweep wipes raw fields from an abandoned session (default 240). |
| `KEEPALIVE_INTERVAL` | no | Neon wake-up pinger interval in seconds (default 45; `0` disables). Auto-disabled on Vercel. |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | no | Officer assistant. **This is a cloud LLM** — see §6. Unset → static offline guide. |
| `GITHUB_TOKEN` / `LEDGER_GIST_ID` | no | Publishes the ledger anchor to a **public** Gist. The manifest includes the anchoring officer's email. |
| `AI_DETECTOR_PROVIDER`, `AI_DETECTOR_KEY`, `AI_DETECTOR_ENDPOINT` | no | Optional cloud tamper-detector backends (blank → local heuristic) |
| `ML_SERVICE_URL` | no | Remote ML microservice. **Leave blank unless deployed** — a placeholder value is treated as configured. |
| `FACE_EMBED_MODEL` | no | ArcFace/FaceNet-style `.onnx` for production face matching (e.g. `data/models/w600k_r50.onnx`) |
| `YOLO_ROI_ONNX_PATH` | no | Local ID-card ROI detector (worker only; auto-loads `app/models/card.onnx`) |
| `AADHAAR_FIELDS_ONNX_PATH` | no | 5-class Aadhaar field detector (`app/models/aadhaar_fields.onnx`) via `yolo_roi.extract_aadhaar_fields` |

## 9. Deploying to Vercel

The repo ships `api/index.py` (serverless entrypoint) and `vercel.json`. The Vite frontend
builds to the tracked `app/static/index.html`, served with `Cache-Control: no-store`.

1. Push to GitHub (or use the `vercel` CLI from this folder).
2. Set the same env vars in the Vercel project dashboard as your local `.env`
   (`DATABASE_URL`, `MASTER_VAULT_KEY`, `GOOGLE_CLIENT_ID` at minimum).
3. `VERCEL=1` is injected automatically: the session cookie gets the `Secure` flag, the Neon
   keepalive thread is disabled, and the AI/tamper forensics gracefully degrade to on-device
   heuristics when cloud providers aren't configured.
4. Cold starts: Neon + dependency import can take a few seconds on the first hit — the engine
   retries DNS/connect and treats table bootstrap as best-effort.

### Edge / Border Deployments (PostgreSQL only)

An edge desk with no internet still needs a database, and it must be a real PostgreSQL
server - a local one, or a managed instance reachable over the link. **SQLite is not a
supported target.** It serialises every write behind a single writer lock (officers queue
against each other during a shift burst), it has no concurrent-reader story for the review
queue, and a local file is exactly the ephemeral-/tmp failure mode a serverless deploy
hits on every cold start. The app refuses to start on a SQLite `DATABASE_URL` rather than
pretend it can hold an append-only audit chain.

If `DATABASE_URL` is unset, startup fails loudly. There is no default DSN and no fallback -
a missing variable must not silently send the audit trail somewhere nobody chose.

## 10. Judge Q&A

**Q: How does this beat a forged document that already fooled an officer?**
A: Validation is algorithmic: ICAO 9303 MRZ check digits and PAN/DL/Voter-ID checksum rules
reject documents with internally inconsistent numbers, and the forensics module marks
re-saved/spread-region edits and spliced portraits visibly. A document that is *valid* but
*fake* still fails one of the four modules — which is why the verdict is per-module and
explainable.

**Q: What makes the screening trustworthy rather than just a black-box AI?**
A: Three properties: the verdict is **rule-first** (checksums, formats, expiry), the tamper
module outputs **heatmaps and metrics** (ELA Δ, PAPR, noise ratio) a supervisor can read, and
every FLAGGED result goes through **human adjudication** — the AI suggests, the officer
decides.

**Q: What about privacy?**
A: Zero-storage discipline — document bytes and live captures exist only in memory, and the
database keeps masked identifiers and hashes. The one place unmasked values exist is inside an
*open* session, where they are needed to cross-check the traveller's documents against each
other; they are wiped the moment the session closes, is flagged, is adjudicated or has a
document removed, and a supervisor can sweep any session left idle past
`RAW_FIELD_TTL_MINUTES`. The watchlist stores SHA-256 hashes, never raw numbers.

**Q: How do you stop an impostor using a genuine document?**
A: Module 4 compares the live face capture with the document portrait (embedding-model cosine
similarity, with a perceptual dHash fallback that runs on Vercel today). Combined with the
syndicate monitor, an impostor's identity also trips cross-checkpoint alerts.

**Q: How is the role system real?**
A: Screening requires an approved post & institution set only by `/api/admin/assign_role`.
A sign-in without an approved role is blocked server-side; officers cannot claim their own
title. Which addresses hold administrative rights comes solely from `SUPER_ADMINS` in the
environment — there is no list in the code, and no pattern matching, so an address that
merely *looks* like an admin's is not one.

**Q: What if Google or the cloud AI provider is down?**
A: Screening still runs: heuristic AI detection and the OCR/forensics pipeline are on-device,
OAuth verify failure simply denies login. The demo never depends on external availability.
The officer assistant is the one exception — it is a cloud LLM, and with no `GEMINI_API_KEY`
it degrades to a static offline guide rather than failing.

---

*Vibe Check Point — SIH26188: AI-Based Fake Identity & Document Screening.*
© 2026 · Team crypto_knights.