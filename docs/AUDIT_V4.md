# NO-CAP (SIH26188) — Evidence Audit Report v4

**Timestamp:** 20261006_204725  
**Auditor:** Automated Truth Engine (`eval/audit_v4.py`)  
**Standard:** Strict Truth Contract (Zero unproven assertions, clear REAL vs SYNTHETIC labeling)

---

## Executive Summary Matrix

| Section | Target Area | Claimed Performance | Audited Status | Verdict | Action Required |
|:---:|---|---|---|:---:|---|
| **B1** | Card Detector Split | 1.0000 Recall on clean split | Disjoint document types verified; min dHash = 15 | **VERIFIED (Narrow)** | Document that 300 test photos are all centered single cards |
| **B2** | Card Detector Gates | Pass all gates incl. scale & negs | Recall 1.0000, Neg FP 0.63%, but **Scale 2x: 44.3%, Scale 3x: 9.7%** | **WEAK** | **FAIL**: Scale stress gates failed. Fix in Phase C1 |
| **B3** | Visual Forensics | AUC 1.0000 across manipulations | Evaluated strictly on procedural PIL synthetic mockups | **SYNTHETIC-ONLY (WEAK)** | Re-evaluate on real IDNet-2025 & FantasyID (Phase C/D) |
| **B4** | MRZ Detector & OCR | 1.0000 Recall, beats baseline OCR | Valid check-digit OCR: 20.67% vs baseline 2.0% | **WEAK** | 20.67% beats baseline but misses >= 60% goal. Fix in Phase C2 |
| **B5** | Doc-Type Classifier | 99.69% accuracy across 8 classes | 3 classes validated on real cards; 5 classes are synthetic-only | **WEAK** | Flag 5 classes UNVALIDATED; add real samples & temperature scaling in Phase C3 |
| **B6** | 2-Thread Latency | <= 900 ms budget across all chains | Passport: 657.5 ms, Aadhaar: 503.3 ms, Generic: 321.8 ms | **VERIFIED** | Verified on 2-thread local CPU; verify in Docker/Space (Phase F) |
| **B7** | Indian Specimens | Real Indian specimen validation | Printable kit created; camera photos absent on disk | **NOT MEASURED** | Relabeled Phase 9 to NOT MEASURED; keep resume guide |

---

## Detailed Audit Findings

### B1. Card Detector Split Integrity
- **Train Document Types:** `['comp', 'esp', 'est', 'grc', 'idcard', 'lva', 'rus', 'synth']`
- **Validation Document Types:** `['aze', 'fin']`
- **Test Document Types:** `['alb', 'srb', 'svk']`
- **Disjoint Proof:** Zero document-type overlap between splits. Minimum dHash Hamming distance on test vs train is **15** (threshold <= 6 for duplicates).
- **Caveat:** All 300 photos feature a prominent, centered ID card on flat desks. Performance on small cards in wide shots was not evaluated.

### B2. Card Detector Gate Audit & Scale Stress Diagnostic
- **Clean Test Recall:** 1.0000 [Target >= 0.95: PASS]
- **Clean Test Precision:** 1.0000 [Target >= 0.90: PASS]
- **Negative FP Rate:** 0.63% (1/160; 0% on paper and receipts) [Target <= 5%: PASS]
- **Scale Stress Diagnostic:**
  - **2x Canvas Padding Recall:** **44.33%** (Target $\ge 90\%$) $ightarrow$ **FAILED**
  - **3x Canvas Padding Recall:** **9.67%** (Target $\ge 60\%$) $ightarrow$ **FAILED**
- **Root Cause:** Training composites lacked aggressive multi-scale training down to 8%–20% canvas coverage.
- **Remediation Plan:** Assigned to Phase C1 (multi-scale composite expansion, retrain, re-export INT8).

### B3. Visual Forensics Benchmark
- **Original Claim:** ROC AUC = 1.0000 on face-swap, text erasure, and clone patches.
- **Truth Audit:** Images were generated in-memory via PIL procedural synthesis.
- **Verdict:** **SYNTHETIC-ONLY**. Real-world generalisation on physical print-and-scan or compressed smartphone capture artifacts is unvalidated.
- **Remediation Plan:** Stream genuine vs manipulated cards from Hugging Face `cactuslab/IDNet-2025` and `34data/FantasyID-real` / `-fake` in Phase C/D.

### B4. MRZ Detector & OCR Quality
- **Detector Localization:** Recall = 1.0000 (300/300).
- **OCR Valid Check-Digit Rate:** **20.67%** (62/300) on raw smartphone crops without preprocessing vs **2.00%** (6/300) for fixed geometric bottom-20% heuristic.
- **Verdict:** **WEAK** against production usability standards (target $\ge 60\%$). Raw Tesseract OCR struggles on noisy smartphone crops without deskew, CLAHE, upscaling, and character correction.
- **Remediation Plan:** Assigned to Phase C2 (deskew, line splitting, CLAHE, OCR-B whitelist, and ICAO position-aware numeric correction).

### B5. Document-Type Classifier v2
- **Tested Classes Breakdown:**
  - `aadhaar`: 56 real test cards $ightarrow$ **VALIDATED**
  - `passport`: 15 real test cards $ightarrow$ **VALIDATED (Low sample size)**
  - `other`: 55 real desk/clutter crops $ightarrow$ **VALIDATED**
  - `pan`: 46 synthetic mockups $ightarrow$ **UNVALIDATED ON REAL CARDS**
  - `voter_id`: 34 synthetic mockups $ightarrow$ **UNVALIDATED ON REAL CARDS**
  - `driving_licence`: 46 synthetic mockups $ightarrow$ **UNVALIDATED ON REAL CARDS**
  - `nepali_citizenship`: 56 synthetic mockups $ightarrow$ **UNVALIDATED ON REAL CARDS**
  - `bhutan_cid`: 16 synthetic mockups $ightarrow$ **UNVALIDATED ON REAL CARDS**
- **Verdict:** **WEAK**. 5 of 8 classes are unvalidated on real documents.
- **Remediation Plan:** Assigned to Phase C3 (add real public images, photo-realism augments, and temperature calibration with a review threshold).

### B6. Latency Profile (2 vCPU Threads)
- **Affinity:** Constrained to 2 logical CPU cores via `psutil`.
- **Passport/MRZ Chain:** **657.53 ms** [Budget $\le 900$ ms: PASS]
- **Aadhaar Chain:** **503.25 ms** [Budget $\le 900$ ms: PASS]
- **Generic ID Chain:** **321.85 ms** [Budget $\le 900$ ms: PASS]
- **Runtime RAM:** **123.3 MB** peak memory.

### B7. Status Relabeling
- **Phase 9:** Explicitly relabeled to **NOT MEASURED**.
- **Documentation:** Promotional rhetoric removed and replaced with quantitative evidence tables.

---

## Action Tasks Derived from Audit
1. **[C1] Card Detector Fix:** Multi-scale data augmentation (8%–95%), hard negative mining round 2, retrain up to 40 epochs, re-export INT8, and pass 2x/3x scale stress.
2. **[C2] MRZ OCR Preprocessing Pipeline:** Deskew, CLAHE binarization, line splitting, OCR-B whitelist, position-aware character substitution to target $\ge 60\%$ valid check-digit rate.
3. **[C3] DocType v2 Real Data Augmentation & Calibration:** Add real public PAN/voter/DL data, photo-realism augments, and temperature-scaled confidence thresholds.
4. **[C4] Real Forensics Validation:** Stream real IDNet-2025 and FantasyID to establish an honest real-world operating point.
