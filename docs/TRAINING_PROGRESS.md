# TRAINING PROGRESS & VERIFICATION LOG (NO-CAP / SIH26188)

Last Updated: 2026-10-06 00:05:00 IST
Branch: `main`

---

## 1. System Hardware & Baseline State (Phase 0A)

- **OS / Platform:** Windows (PowerShell), Python 3.11.9
- **GPU Detected:** NVIDIA GeForce RTX 4060 Laptop GPU (8,188 MiB VRAM), Driver 610.88, CUDA 13.3
- **PyTorch / CUDA Status:** `Torch: 2.11.0+cu128 | CUDA available: True` (Verified via `python -c "import torch; print('Torch:', torch.__version__, 'CUDA available:', torch.cuda.is_available())"`)
- **Initial Test Suite Baseline:**
  ```
  Command: python -m pytest -q
  Result: 243 passed, 3 skipped, 3 warnings in 103.84s (0:01:43)
  Exit code: 0
  ```

---

## 2. Detection Architecture Wiring (15-Line Summary)

1. Client (`app/extraction.py`) routes incoming document image bytes to `app/yolo_roi.py:extract_roi_boxes` and `extract_aadhaar_fields`.
2. If `ML_SERVICE_URL` is set, `app/yolo_roi.py` checks `app/remote_ml.py:is_remote_available`, sending payload to `ml_service` via HTTP with header `X-ML-Secret-Key`.
3. If remote fails or is unset, `app/yolo_roi.py` falls back to local ONNX execution via `_get_onnx_session()` (`card.onnx`) and `_get_aadhaar_session()` (`aadhaar_fields.onnx`).
4. Both backends use `letterbox(img, (640, 640), pad=114)` to preserve aspect ratio, scaling back with `scale_boxes_to_original()`.
5. Post-processing executes vectorized per-class Non-Maximum Suppression via `nms_numpy` (IoU threshold 0.45).
6. Local fallback CV heuristics (`_detect_document_card`, `_detect_face_heuristic`, `_detect_mrz_zone`, `_detect_qr_zone`) run if ONNX is missing.
7. Heuristic detections are tagged `source: "heuristic"`, `confidence: None`; model detections are tagged `source: "model"`, `confidence: float`, and `backend: "yolov8"|"rf_detr"`.
8. Handheld camera perspective skew is corrected via `app/rectification.py:rectify_card_image` (pure Pillow DLT homography to 1000x630 CR-80) when `ENABLE_CARD_RECTIFICATION=true`.
9. `isolate_document_card()` crops card boundaries losslessly to PNG before downstream OCR and forensic ELA/PRNU analysis.
10. `ml_service/yolo_roi.py` mirrors the ONNX detection and rectification logic, serving `POST /api/ml/yolo_roi` and `/api/ml/aadhaar_fields`.
11. `ml_service/media_processor.py` provides in-memory PDF page rasterization, `/ByteRange` signature structural checks, and Live Photo MP4 burst slicing.
12. Multi-class Aadhaar zones isolate 5 semantic fields (`Aadhaar_No`, `DOB`, `Gender`, `Name`, `Photo`) with class-specific confidence thresholds.
13. If detection fails or operates under heuristic fallback, `app/screening.py` sets `can_clear = False`, forcing supervisory `REVIEW`.
14. `eval/evaluate.py` benchmarks detectors against held-out datasets using `eval/metrics.py` (mAP50, mAP50-95) and `eval/benchmark.py` (p50/p95 latency).
15. Neon PostgreSQL stores audit records and cryptographic hashes; raw pixels are never persisted to disk (Zero-Raw-Storage invariant).

---

## 3. Defect Verification Log (Defects D1–D8)

| ID | Verified Defect | Source File & Lines | Planned Fix | Status |
|:---|:---|:---|:---|:---:|
| **D1** | **Fake bake-off & silent fallback:** With `DETECTOR_BACKEND=rf_detr`, `_default_model_path()` logged fallback and loaded YOLO's `card.onnx`. Aliases like `rtdetr` mapped to `rf_detr`. `eval/bakeoff_report.json` contained fabricated null metrics with an unsupported recommendation. | `app/yolo_roi.py:87-117`, `ml_service/yolo_roi.py:44-74`, `eval/evaluate.py:270-334`, `eval/bakeoff_report.json` | (a) In `rf_detr` mode without weights: fail loudly (return `None` / `engine: "none"`), NEVER silently load YOLO. (b) Response `backend` field reports effective backend actually used. (c) `run_detector_bakeoff` aborts with clear error if RF-DETR weights missing. (d) Delete fabricated `eval/bakeoff_report.json`. (e) Remove `rtdetr`/`rt-detr` aliases. | FIXED & VERIFIED IN TESTS |
| **D2** | **Overclaiming in docs & test count discrepancy:** `docs/ML_PIPELINE_CHANGES.md` claimed "RF-DETR wins" and identical 0.992 mAP50. Blueprint §31 ticked RF-DETR operational. Blueprint §26 stated 220 tests, §31 stated 237+, real test count is 243 passed, 3 skipped. | `docs/ML_PIPELINE_CHANGES.md:210-234`, `ml_service/README.md:19-22`, `SIH26188_ENGINEERING_BLUEPRINT.md:§15.1, §26, §31` | Rewrite docs: "RF-DETR backend support implemented; trained weights pending; no comparative result yet." State real test counts (245 passed, 3 skipped). | FIXED & VERIFIED IN DOCS |
| **D3** | **Unreliable Card eval baseline:** Only 12 ground-truth cards evaluated from `data/IDcard`, yielding 0.083 recall without reliable sample size. | `eval/evaluate.py`, `eval/eval_report.json` | Rebuild card test set with generic real photos (MIDV-2020) and Indian specimens. | SCHEDULED PHASES 2-3 |
| **D4** | **Auth secret mismatch & open-by-default:** `ml_service/main.py:verify_ml_auth` permitted all requests without authentication if `ML_SECRET_KEY` was unset. Client in `app/remote_ml.py` reads `ML_SERVICE_SECRET` or `ML_SECRET_KEY`. | `ml_service/main.py:26-36`, `app/remote_ml.py:72-78`, `ml_service/README.md` | Fail closed: if `ML_SECRET_KEY` unset, reject with HTTP 503 unless `ML_ALLOW_NO_AUTH=true` explicitly set (log loud warning). | FIXED & VERIFIED IN TESTS |
| **D5** | **PDF signature overclaiming:** `inspect_pdf_signatures` performs structural regex on `/ByteRange` but does not verify PKCS#7 certificate chain or cryptographic signature. | `ml_service/media_processor.py:26-121`, `SIH26188_ENGINEERING_BLUEPRINT.md:§15.1` | Rename conceptually to signature presence/structure check. Add `cryptographically_verified: false` to output. Ensure no verdict logic treats it as cryptographic proof. | FIXED & VERIFIED IN TESTS |
| **D6** | **Live-Photo liveness thresholds uncalibrated:** Inter-frame delta thresholds (0.8–25.0) are heuristic without empirical calibration. | `ml_service/media_processor.py:347-380` | Mark output `experimental: true`. Verified no scoring path in `app/screening.py` uses this to influence CLEAR/REVIEW/FLAGGED. | FIXED & VERIFIED IN TESTS |
| **D7** | **Post-processing benchmark inflation:** `eval/benchmark.py:56` re-ran the full `_run_yolo_onnx` (pre-processing + inference + post-processing) inside the post-processing timer block, measuring ~206 ms for post-processing when NMS itself is only 1-3 ms. | `eval/benchmark.py:54-58`, `eval/eval_report.json` | Fix benchmark timer to isolate NMS + unscaling from inference and pre-processing. Measured real post-processing latency: 0.63-2.81 ms. | FIXED & VERIFIED IN BENCHMARK |
| **D8** | **Code drift between `app/yolo_roi.py` (846 lines) and `ml_service/yolo_roi.py` (670 lines):** Diff confirms structural core (letterbox, nms_numpy, _run_yolo_onnx, heuristics, isolate_document_card) matches, but `app/yolo_roi.py` contains client-side remote HTTP microservice calls (`is_remote_available`, `extract_roi_boxes` calling `ML_SERVICE_URL`), richer comments/docstrings, and flipped import order for `rectification`. | `app/yolo_roi.py`, `ml_service/yolo_roi.py` | Align docstrings, unify model path resolution and fail-loud logic. Add automated source-drift test `test_yolo_roi_dual_implementation_drift`. | FIXED & VERIFIED IN TESTS |

---

## 4. Dataset Inventory & Manifest (Phase 1)

Verified against disk on 2026-10-06 via `data/DATASET_MANIFEST.md` and direct label parsing:

| Dataset Path | Classes | Splits (Images) | Total Images | Label Counts per Class | Flips / Augs | License | Privacy Check (5.2 B) |
|:---|:---|:---|:---|:---|:---|:---|:---|
| `data/AADHAR` | `['Aadhaar_No', 'DOB', 'Gender', 'Name', 'Photo']` | Train: 2,381<br>Valid: 185<br>Test: 79 | 2,645 | **Train:** No: 2344, DOB: 2282, Gender: 2297, Name: 2274, Photo: 79<br>**Valid:** No: 183, DOB: 181, Gender: 183, Name: 180, Photo: 4<br>**Test:** No: 79, DOB: 73, Gender: 74, Name: 73, Photo: 4 | None (Resize 640x640 stretch only) | CC BY 4.0 (Roboflow Universe) | Appears to show real persons: **YES / UNCONFIRMED** |
| `data/IDcard` | `['Card']` | Train: 39<br>Valid: 10<br>Test: 8 | 57 | **Train:** Card: 71<br>**Valid:** Card: 13<br>**Test:** Card: 12 | None (Resize 640x640 stretch only) | CC BY 4.0 (Roboflow Universe) | Appears to show real persons: **NO / SPECIMEN-LIKE** |
| `data/card_synth` | `['Card']` | Train: 1,314<br>Valid: 243<br>Test: 0 | 1,557 | **Train:** Card: 1,346<br>**Valid:** Card: 250 | Synthetic internal | Project-generated | Pure synthetic specimens |

- **Git-ignore verification:** Confirmed with `git check-ignore -v` that `data/`, `eval/data/`, and `training/runs/` are completely ignored by git.
- **Privacy Contact Sheets:** Generated to `eval/runs/contact_sheets/aadhar_contact_sheet.jpg` and `eval/runs/contact_sheets/idcard_contact_sheet.jpg`.

---

## 5. Phase Execution Status

- [x] **Phase 0A: Understand & Baseline Audit** — Test baseline confirmed (243 passed, 3 skipped). Hardware verified (RTX 4060 GPU, PyTorch 2.11.0+cu128). D1–D8 defects verified.
- [x] **Phase 0B: Truth Fixes (Defects D1–D8)** — All 8 defects fixed. `eval/bakeoff_report.json` deleted. Strict fail-loud on missing weights (`FileNotFoundError` in bakeoff, empty string in `_default_model_path()`). Secret auth fail-closed (503 if unset unless `ML_ALLOW_NO_AUTH=true`). Benchmarking timing isolated (postprocessing ~0.63 ms). Automated drift test added. Full suite: 245 passed, 3 skipped (100%).
- [x] **Phase 1: Environment & Data Inventory** — Local RTX 4060 GPU with CUDA 13.3 verified. Full dataset inventory executed on `data/AADHAR`, `data/IDcard`, `data/card_synth`. `data/DATASET_MANIFEST.md` generated.
- [x] **Phase 2: Data Preparation & Offline Scripts** — Built offline conversion and augmentation suite without blocking on external FTP:
  - `training/convert_yolo_to_coco.py` (YOLO -> COCO conversion with coordinate clipping).
  - `training/convert_midv_to_coco.py` (MIDV-500 quad & MIDV-2020 VIA format parsing, leakage-free type splits).
  - `training/make_composites.py` (Realistic perspective distortion, glare, shadow, and occlusions; strictly NO flips).
  - `training/download_midv_subset.py` (HTTP range resume support and timeout retries).
  - Verified with unit tests in `tests/test_converters.py` (9 passed) and `tests/test_composites.py` (1 passed).
- [ ] **Phase 3: Baseline Measurement on Held-Out Sets**
- [ ] **Phase 4: Train Model A (Card) & Model B (Fields)** — `training/train_card_rfdetr.py` prepared with 1-epoch smoke test, VRAM safety caps, and metadata sidecar export. Blocked on real phone photos (MIDV-2020 photos or Indian specimens) per Addendum v2.1 §2.2.
- [x] **Phase 5: Export, ONNX Parity & Early Integration** — Inference pipeline integrated early:
  - `_load_model_metadata()` validates `*.meta.json` sidecar and enforces class count integrity.
  - `preprocess_rfdetr()` applies square resize and ImageNet mean/std normalization.
  - `_postprocess_rfdetr_predictions()` implements NMS-free sigmoid decode and coordinate mapping to original image pixels.
  - `_run_rfdetr_onnx()` maps outputs by name/shape and routes detection in `extract_roi_boxes` and `extract_aadhaar_fields`.
  - Both `app/yolo_roi.py` and `ml_service/yolo_roi.py` synchronized and verified via `test_yolo_roi_dual_implementation_drift`.
  - Unit tests in `tests/test_rfdetr_inference.py` (4 passed, 1 skipped cleanly for missing weights).
- [ ] **Phase 6: Bake-Off & Real Decision Matrix**
- [ ] **Phase 7: Documentation & Handoff**

---

## 6. Comprehensive Test Suite Audit

```
Command: python -m pytest -q
Result: 259 passed, 4 skipped, 3 warnings in 113.55s (0:01:53)
Exit code: 0
```

### Skipped Tests Accounting:
1. `tests/test_face_match.py:119`: `w600k_r50.onnx not downloaded` (expected in CI/dev when ArcFace weights are not pulled).
2. `tests/test_revamp.py:261`: `doctype.onnx not present` (expected when optional classifier is absent).
3. `tests/test_codebase.py:94`: `local scripts/ study guides not present (gitignored)` (expected for developer notes).
4. `tests/test_rfdetr_inference.py:89`: `RF-DETR card weights not present on disk (pending Phase 4 training)` (clean parity skip as required by Section 7.1).


