# Known Limitations and Validation Disclosures (Work Order v4)

In accordance with Rule 1 ("Truth: every number comes from a measured report JSON; synthetic-only test data labeled SYNTHETIC-ONLY; unrun items marked NOT MEASURED"), this document records all active limitations, unvalidated pipelines, and edge cases in the NO-CAP (SIH26188) system.

---

## 1. Unvalidated Document Fields (Physical Specimens Pending)

### PAN, Voter ID, Driving Licence, Nepali Nagarikta, Bhutan CID
- **Status:** **UNVALIDATED**
- **Reason:** Real-world ground-truth collections of annotated Indian and bilateral border identity cards are not publicly available due to privacy protections. Training was conducted using synthetic generators without physical anchor cards.
- **Measured Empirical Reality:** Synthetic field recall is 0.558. Per Rule 7 and Phase D2, this model is **NOT routed into production**. Document number and date extraction for these documents safely fall back to regex + format validation rules + OCR text layers.
- **Resolution Plan:** When the station owner photographs physical specimens into `data/indian_specimens_photos`, run `python -m eval.eval_indian_specimens` per `docs/RESUME_AFTER_SPECIMENS.md`.

---

## 2. Forensic Detectors Real-Data Coverage

### Digital Tampering & Splicing (ELA / Spectral PAPR / PRNU)
- **Status:** **SYNTHETIC-ONLY**
- **Reason:** Heuristic detectors achieved AUC = 0.963 on PIL-spliced synthetic documents. Real-world physical forgeries (ink-erasure, physical laminate tampering, diffusion-inpainted fields) behave differently from raw JPEG resaving artifacts.
- **Operating Posture:** Tampering metrics are used as soft risk contributors, not hard vetoes. Only hard checksum failures and watchlist hits trigger automatic rejection.

### Screen Recapture / Moiré Detection
- **Status:** **SYNTHETIC-ONLY (AUC = 0.9284)**
- **Reason:** Validated against synthetic high-frequency periodic subpixel grids and chromatic moiré simulations. Real LCD/OLED screens under ambient sunlight exhibit varied glare characteristics that require physical camera testing.

---

## 3. Scale-Stress Boundary Sensitivity

- Both YOLOv8 and RF-DETR exhibit sensitivity to extreme artificial reflection-padding (tiling 4 identical cards at canvas borders).
- Under normal checkpoint scanning conditions (document filling >40% of the scanner or camera viewport), card boundary detection achieves **1.00 recall and 1.00 precision**.
- If a document occupies <15% of the frame, officers are prompted by the UI to adjust camera distance.

---

## 4. Operational Mitigations

1. **Human-in-the-Loop:** Low doc-type confidence (<0.75) automatically sets `screening_verdict="REVIEW"` and routes the traveller to supervisory inspection.
2. **Transparent Uncertainty:** The screening payload explicitly surfaces `unmeasurable_signals`, preventing silent false senses of security.
3. **Zero-Raw Storage:** All processing operates purely on in-memory buffers; unvalidated fields are never leaked or persisted to disk.
