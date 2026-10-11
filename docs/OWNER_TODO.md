# NO-CAP (SIH26188) — OWNER ACTION & TODO LIST

This document records all tasks, credentials, and actions that require human owner intervention. Kept current across all work order phases.

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
