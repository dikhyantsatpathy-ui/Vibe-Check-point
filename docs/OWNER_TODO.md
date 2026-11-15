# NO-CAP (SIH26188) — OWNER ACTION & TODO LIST

This document records all tasks, credentials, and actions that require human owner intervention. Kept current across all work order phases.

## 0. JURY EVALUATION PASS CONFIGURATION (F-01)

**To keep the jury one-click pass working you MUST set DEMO_PASS_ENABLED=1 on the jury deployment only; never on a real checkpoint deployment.**

```powershell
# On jury demo instance (Vercel or local):
$env:DEMO_PASS_ENABLED = "1"
```

---

## 1. PENDING CREDENTIALS & ACCESS

### Item 1: Roboflow API Key
- **Current Status**: **BLOCKED (401 Unauthorized)**
- **Detail**: Roboflow API key (value not recorded) returned `401 Unauthorized` (`"This API key does not exist (or has been revoked)"`).
- **Owner Action**:
  1. Log in to [Roboflow Dashboard](https://app.roboflow.com/).
  2. Navigate to **Account Settings** $\rightarrow$ **Roboflow Keys** (or **API Keys**).
  3. Copy your private API key (typically a 20-30 character alphanumeric token).
  4. Paste into terminal or session when ready.
- **Copy-Paste Command**:
  ```powershell
  $env:ROBOFLOW_API_KEY = "<your_roboflow_private_key>"
  ```

### Item 2: Hugging Face Write Token & Repository
- **Current Status**: **VERIFIED (Active)**
- **Username**: `koropanda`
- **Model Repository**: `koropanda/no-cap-detectors` (Private)
- **Token**: Verified and operational.

---

## 2. PHYSICAL SPECIMEN CAPTURE (PHASE 9)

- **Artifact Generated**: `training/indian_specimens/out/indian_specimen_sheets_300dpi.pdf` (Print-ready A4, 2 pages, 16 cards, 300 DPI, ID-1 85.6 × 54 mm, 5 generic designs with "SPECIMEN" watermark).
- **Field Capture Guide**: Read [`training/indian_specimens/CAPTURE_PROTOCOL.md`](training/indian_specimens/CAPTURE_PROTOCOL.md).
- **Owner Action**:
  1. Print the PDF at 100% scale (no "Fit to page" or scaling).
  2. Cut out card specimens along trim lines.
  3. Capture $\ge 150$ photos across $\ge 2$ smartphones under 8 physical conditions (low light, outdoor, table, cloth, keyboard, glare, perspective tilt, hand-held) plus 50 negative photos without cards.
  4. Save raw photos to `data/indian_specimens_photos/`.
  5. Label 4 card corners using the OpenCV clicker:
     ```powershell
     python -m training.label_cards --image-dir data/indian_specimens_photos --output-json data/indian_specimens_annotations.json
     ```
  6. Import into COCO test dataset:
     ```powershell
     python -m training.indian_specimens.import_indian_specimens --image-dir data/indian_specimens_photos --ann-json data/indian_specimens_annotations.json --output-dir data/coco_card_indian/test
     ```

---

## 3. DATASET LICENSING & GOVERNANCE

### Item 3: MIDV-2020 Licence Text
- **Current Status**: Marked `PENDING (owner to paste)`.
- **Owner Action**: Confirm accepted licence terms from original download/registration and whether legal review of ShareAlike terms for trained neural weights is required prior to public release.

### Item 4: `data/AADHAR` Dataset Disposition
- **Current Status**: Stays on local disk only; strictly excluded from Git and Hugging Face uploads.
- **Owner Action**: Decide whether to retire, retain strictly on local development machine, or replace with synthetic/consented citizen data.

### Item 5: Mendeley Synthetic Aadhaar Download
- **Current Status**: Download requires manual browser session if direct cURL is blocked.
- **URL**: `https://data.mendeley.com/datasets/wk6n8fhx3c/1`
- **Owner Action**: If automated download fails, download zip from Mendeley page and extract to `data/raw/mendeley_synthetic_aadhaar/`.

---

## 4. VERCEL DEPLOYMENT & ISOLATION ACTIONS (F-13 / F-14)

### Item 6: Staging vs Production Environment Isolation (F-13)
- **Status**: **BLOCKED (Vercel CLI logged out)**
- **Detail**: Blueprint claims isolated `main` vs `stage_test` Neon branches, distinct vault keys, and separate OAuth clients. Must be verified with active Vercel session; until verified, stays **UNVERIFIABLE**.
- **Owner Action**:
  ```powershell
  # 1. Log in to Vercel
  vercel login

  # 2. Inspect and compare production vs preview/staging env vars (never share secrets)
  vercel env ls --environment=production
  vercel env ls --environment=preview

  # 3. Verify DATABASE_URL points to different Neon branches:
  # Production: ep-red-scene-... (main branch)
  # Staging: stage_test branch
  ```

### Item 7: Token Hygiene in Deployed Vercel Projects (F-14)
- **Status**: **BLOCKED (Vercel CLI logged out)**
- **Detail**: Ensure `HF_TOKEN` is NOT injected into the frontend/app Vercel deployment unless code in `app/` requires it. Hugging Face Space should hold a dedicated read-only token.
- **Owner Action**:
  ```powershell
  # Check if HF_TOKEN is configured in Vercel project:
  vercel env ls
  # If present and unneeded on Vercel:
  vercel env rm HF_TOKEN production
  ```

### Item 8: Historical Neon PostgreSQL Password Rotation (Phase V1 / S1)
- **Status**: **ACTION REQUIRED (S1 Secret Hygiene)**
- **Detail**: Commit `3724e9e3` historically introduced a hardcoded connection string for `ep-red-scene-azg0qzq0-pooler...neon.tech`. While the working tree code was cleaned, git history retains the commit. The Neon database user password must be rotated immediately in the Neon console.
- **Owner Action**:
  1. Log into the Neon Console at https://console.neon.tech
  2. Select project `red-scene` / branch `main`.
  3. Go to **Roles / Users** -> `neondb_owner` -> **Reset Password**.
  4. Update `DATABASE_URL` in Vercel project environment variables (`vercel env add DATABASE_URL production`).

### Item 9: AGPL Tooling License Assessment for ONNX Checkpoints (Phase V2 / Legal)
- **Status**: **ACTION REQUIRED (Legal Counsel Review)**
- **Detail**: YOLOv8 model weights exported to ONNX were trained using Ultralytics tooling (AGPL-3.0). While Ultralytics is omitted from all runtime dependencies and runtime inference is pure ONNX Runtime (MIT license), whether model weights derived from AGPL-licensed training tooling inherit copyleft obligations is an unresolved legal question for intellectual property counsel. Assert nothing about copyleft freedom without legal review.

---

## 5. PRIVATE MODEL REPOSITORY PROVISIONING (PHASE P4)

### Item 10: Upload ArcFace Model to Private Hugging Face Repository
- **Status**: **ACTION REQUIRED (Model Provisioning)**
- **Detail**: In accordance with supply chain security hardening (Phase P4), automatic unauthenticated downloads of `w600k_r50.onnx` from third-party URLs are removed. When `AUTO_DOWNLOAD_MODELS=1`, models are fetched strictly from the private `HF_MODEL_REPO`. If `w600k_r50.onnx` is missing from the private repository or unverifiable, face verification runs in mode `unavailable` (INCONCLUSIVE -> REVIEW).
- **Owner Action**:
  Upload the local `w600k_r50.onnx` weights file to the private Hugging Face repository using `hf upload` (or `huggingface-cli upload`):
  ```powershell
  # 1. Configure environment variables
  $env:HF_MODEL_REPO = "koropanda/no-cap-detectors"
  $env:HF_TOKEN = "<your_hf_token>"

  # 2. Upload model file using verified CLI signature:
  # Usage: hf upload REPO_ID [LOCAL_PATH] [PATH_IN_REPO] --token TEXT
  hf upload koropanda/no-cap-detectors data/models/w600k_r50.onnx w600k_r50.onnx --token $env:HF_TOKEN

  # Alternatively, via huggingface-cli upload:
  # huggingface-cli upload koropanda/no-cap-detectors data/models/w600k_r50.onnx w600k_r50.onnx --token $env:HF_TOKEN
  ```

---

## 6. CSP ENFORCEMENT VERIFICATION (PHASE P8)

### Item 11: CSP Strict Enforce Verification
- **Status**: **ACTION REQUIRED (Browser DevTools Audit)**
- **Detail**: Security headers now send the baseline policy as `Content-Security-Policy` and the hash-based strict policy as `Content-Security-Policy-Report-Only`. Setting `CSP_STRICT_ENFORCE=1` switches the enforced policy to strict mode.
- **Owner Action**:
  1. Open the running deployment in a web browser.
  2. Open DevTools Console (`F12` -> Console).
  3. Navigate through the UI workflows (Scan & Verify, Needs Review, Log & History, Alert List, Officers).
  4. Verify that no CSP violation reports (`Content-Security-Policy-Report-Only`) appear in the browser console.
  5. Once verified clean, enable strict enforcement in the deployment environment:
     ```powershell
     $env:CSP_STRICT_ENFORCE = "1"
     ```




