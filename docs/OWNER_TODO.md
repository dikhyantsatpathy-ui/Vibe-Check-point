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
- **Detail**: The provided key (`pcsk_6P9BVB_...`) returned `401 Unauthorized` (`"This API key does not exist (or has been revoked)"`).
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

