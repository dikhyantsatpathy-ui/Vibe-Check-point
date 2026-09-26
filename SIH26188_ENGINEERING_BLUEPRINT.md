# SIH26188 Engineering Blueprint — AI-Based Fake Identity & Document Screening System (NO-CAP)

**SMART INDIA HACKATHON 2026**  
**Problem Statement ID:** SIH26188 (S.No. 188)  
**Title:** AI-Based Fake Identity & Document Screening System  
**Organization:** Ministry of Home Affairs (MHA)  
**Department / Agency:** Sashastra Seema Bal (SSB), Police II Division  
**Category:** Software | **Theme:** Blockchain & Cybersecurity  
**Document Type:** Software Solution | Engineering & Product Blueprint  
**System Name:** NO-CAP (Next-Gen Online Checkpoint & Admissibility Platform)  
**Version:** 1.0 | **Date:** September 2026  

---

## Document Purpose

This document serves as the team's single source of truth for product scope, system architecture, forensic & AI methodology, legal admissibility under the Bharatiya Sakshya Adhiniyam 2023 (BSA), zero-storage privacy under the Digital Personal Data Protection Act 2023 (DPDP), technology stack, API contracts, deployment topology, and live demonstration workflow. It is intentionally written as an exhaustive engineering blueprint rather than an academic overview.

---

## Table of Contents

1. Executive Summary
2. Problem Definition & Operational Context
3. Objectives & Key Results (OKRs)
4. Users and Stakeholders
5. Scope and Boundaries (In Scope, Out of Scope, Future Scope)
6. Proposed Solution & End-to-End Pipeline
7. Core Use Cases (UC-01 to UC-06)
8. Functional Requirements
9. Non-Functional Requirements
10. Product and System Workflow
11. System Architecture
12. Data Architecture & Zero-Raw-Storage Invariant
13. Forensic Analytics & AI/ML Methodology
14. Risk Scoring & Explainability Engine
15. Application Modules (M1 to M9)
16. Officer Desk and Inspection Experience
17. Alert, Escalation & Shift Handover System
18. Technology Stack
19. API and Integration Contract
20. Development and Collaboration Workflow
21. Repository and Code Organization
22. Team Responsibilities & Ownership Matrix
23. Testing and Evaluation Strategy
24. Security, Privacy & Legal Governance (DPDP 2023 & BSA 65B)
25. MLOps, False-Positive Tuning & Model Governance
26. Deployment Architecture (Hybrid Cloud & Edge Fallback)
27. MVP and Future Scope
28. Risks, Assumptions and Mitigations
29. Golden Path Live Demo Workflow
30. Deliverables and Presentation Plan
31. Definition of Done (DoD)
32. Reference Standards and Legal Frameworks

---

## 1. Executive Summary

The **NO-CAP** (Next-Gen Online Checkpoint & Admissibility Platform) is an offline-capable, AI-powered document forensics, biometrics, and zero-knowledge verification platform designed specifically for **Sashastra Seema Bal (SSB)** checkpoint officers guarding India's open and semi-regulated land borders (predominantly the Indo-Nepal and Indo-Bhutan borders, including major Integrated Check Posts such as Raxaul, Panitanki, Sonauli, and Jaigaon).

Border check posts encounter hundreds of thousands of travellers possessing diverse identity documents (Indian Passports, Aadhaar Cards, Voter IDs, PAN Cards, Driving Licences, Nepali Citizenship Certificates / Nagarikta, and Bhutanese Travel Permits). Fraud syndicates exploit the open border regime via photo-substitution, forged visa/exit stamps, fraudulent Aadhaar cards generated for third-country illegal immigrants, and repeated document recycling across different checkpoint sectors.

NO-CAP acts as an **auditable decision-support console**. It does not autonomously seize documents or deny entry; instead, within **under 1.5 seconds**, it:
1. Validates mathematical checksums (ICAO 9303 MRZ 731 weights, Verhoeff algorithm for Aadhaar, PAN format rules).
2. Performs multi-spectral pixel forensics (Error Level Analysis, 2D-FFT high-frequency spectral PAPR, PRNU sensor noise variance, and copy-move splice detection).
3. Verifies traveller identity using 1:1 facial biometrics (ArcFace / InsightFace) with anti-spoofing challenge-response liveness.
4. Enforces **Zero-Raw-Storage**: zero unencrypted passenger images or PII ever touch disk.
5. Emits an immutable, cryptographic SHA-256 hash-chain ledger block accompanied by an automated, court-admissible electronic record certificate under **Section 65B of the Bharatiya Sakshya Adhiniyam, 2023 (BSA)**.

---

## 2. Problem Definition & Operational Context

### 2.1 The Operational Challenge
The Indo-Nepal Treaty of Peace and Friendship (1950) and bilateral Indo-Bhutan arrangements permit visa-free movement of citizens across designated land borders. Consequently:
- **High Volume & Severe Time Constraints:** Officers must process a pedestrian or vehicular traveller in under 10–20 seconds to prevent massive border chokepoints.
- **Remote & Adverse Physical Environments:** Land border posts (such as Panitanki in West Bengal or Raxaul in Bihar) suffer from dusty physical conditions, varying lighting, and frequent electrical or broadband outages.
- **Sophisticated Transnational Forgery:** Transnational human-trafficking and smuggling syndicates utilize high-quality commercial dye-sublimation printers, laser scoring, and fake holograms to forge Indian Aadhaar cards and Nepali Nagarikta documents for third-country nationals (e.g., Bangladeshi, Pakistani, and Chinese nationals).
- **Physical Document Wear vs. Malicious Tampering:** In rural border populations, laminated IDs frequently suffer from air bubbles, peeling plastic, scratches, and water damage that cause naive AI algorithms to trigger false-positive alarms.

### 2.2 Primary Engineering Question
*Can a lightweight, edge-deployable software system automatically inspect multi-modal identity documents in real time, distinguish genuine physical wear from deliberate forgery, verify traveller biometrics, detect syndicate link patterns, and generate legally bulletproof evidence certificates—without ever storing sensitive citizen PII?*

---

## 3. Objectives & Key Results (OKRs)

- **Objective 1: Sub-Second Multimodal Forensic Triage**
  - *KR 1.1:* Complete full document OCR, MRZ parsing, and 4-tier forensic analysis in `< 1,200 ms` on standard checkpoint hardware.
  - *KR 1.2:* Zero dependencies on external commercial cloud APIs for the primary triage loop.
- **Objective 2: Zero False-Alarm Disruption**
  - *KR 2.1:* Keep the false-positive rate on physically worn or laminated documents below `3.5%` via adaptive sensor noise thresholding and texture-aware ELA.
  - *KR 2.2:* Achieve `100%` detection rate on altered ICAO 9303 MRZ digits and invalid Verhoeff Aadhaar checksums.
- **Objective 3: Absolute Privacy & DPDP Act 2023 Compliance**
  - *KR 3.1:* Enforce Zero-Raw-Storage invariant: discard 100% of raw image buffers immediately from volatile RAM post-extraction.
  - *KR 3.2:* Store only salted SHA-256 one-way cryptographic hashes and masked PII (e.g., `XXXX-XXXX-5446`).
- **Objective 4: BSA 2023 Section 65B Legal Admissibility**
  - *KR 4.1:* Automatically hash every screening report into a tamper-evident SHA-256 Merkle chain.
  - *KR 4.2:* Generate instant, digitally verifiable PDF/A certificates compliant with Section 65B(4) of the Bharatiya Sakshya Adhiniyam, ready for court submission.

---

## 4. Users and Stakeholders

| User / Stakeholder | Primary Need | Key System Capabilities |
| :--- | :--- | :--- |
| **Border Checkpoint Screening Officer (SSB Constable/Head Constable)** | Rapid, effortless document screening; clear, non-cryptic pass/flag decisions. | Dual-dropzone upload, webcam capture, 1-click test presets, keyboard shortcut `[Ctrl + Enter]`, clear color-coded verdict banner. |
| **Shift Supervisor / Inspector (Adjudicator)** | Review flagged/suspicious cases, adjudicate borderline travellers, seal shift handovers. | Review Queue with side-by-side forensic diff, biometric threshold override, digital signature handover tokens. |
| **Central Intelligence / Forensics Unit** | Detect cross-checkpoint syndicate patterns, document recycling, and imposter rings. | Syndicate cluster graph, travel frequency anomaly analysis, passport reuse tracking across checkpoints. |
| **Court of Law / Legal Prosecutors** | Tamper-proof evidence that proves document forgery beyond a reasonable doubt. | Cryptographically signed BSA Section 65B Certificate, Merkle inclusion proof, immutable hash chain. |
| **System Administrator** | Roster management, audit logging, system health, Hugging Face ML node monitoring. | Officer access control (approve/revoke), rate-limit monitoring, Neon PostgreSQL sync, health HUD. |

---

## 5. Scope and Boundaries

### 5.1 In Scope for MVP
- Dual-sided document intake (Passports, Aadhaar, Driving Licence, PAN, Voter ID, Nepali Nagarikta).
- Automated mathematical validation (ICAO Doc 9303 TD1/TD2/TD3 check digits, Verhoeff algorithm, PAN structure).
- Multimodal image forensics: Error Level Analysis (ELA), 2D-FFT spectral Peak-to-Average Power Ratio (PAPR), Photo-Response Non-Uniformity (PRNU) noise variance.
- Face matching (ArcFace cosine similarity) and webcam challenge-response liveness.
- Zero-Knowledge Selective Disclosure Gates (e.g., proving Age ≥ 18 without disclosing Date of Birth).
- Immutable SHA-256 hash-chain ledger with live Merkle tree root computation.
- One-click Section 65B BSA 2023 Electronic Evidence Certificate generation.
- Responsive, decluttered officer desk console with high-contrast Sovereign Navy palette and offline fallback.

### 5.2 Out of Scope for MVP
- Direct automated physical gate barrier opening or turnstile hardware actuation.
- Direct live production integration with confidential CCTNS / NCRP / Interpol databases (simulated via sanitized intelligence lists).
- Autonomous passenger detention decisions (system is strictly human-in-the-loop decision support).

### 5.3 Future Scope
- Direct integration with Land Ports Authority of India (LPAI) automated biometric e-Gates.
- Hardware passport optical RFID chip readers (BAC/EAC/PACE cryptographic chip reading).
- Drone/surveillance feed integration along unfenced riverine border segments.

---

## 6. Proposed Solution & End-to-End Pipeline

```
       [ Traveller ID Document: Front + Back ] + [ Optional Live Webcam Frame ]
                                  │
                                  ▼
        ┌───────────────────────────────────────────────────────────────┐
        │   FastAPI In-Memory Stream Intake (Zero-Raw-Storage Layer)     │
        │   - Volatile RAM buffer only; Never persisted to disk         │
        └───────────────────────────────┬───────────────────────────────┘
                                        │
                                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                         PARALLEL SCREENING PIPELINE                         │
 │                                                                             │
 │  [Module 1: Document Classification, OCR & Checksum Verification]           │
 │  - ICAO Doc 9303 MRZ Check Digit Parser (Weights 7, 3, 1)                   │
 │  - Verhoeff Checksum Matrix Validator (Aadhaar 12-digit)                    │
 │  - PAN / Driving Licence / Nepali Nagarikta Rule Matcher                    │
 │                                                                             │
 │  [Module 2: Multimodal Image Tampering Forensics]                           │
 │  - Error Level Analysis (ELA) Compression Artifact Discrepancy             │
 │  - 2D-FFT High-Frequency Spectral Analysis (PAPR synthetic grain detection) │
 │  - PRNU Sensor Noise & Laplacian Blur Variance                              │
 │  - Spatial SRM High-Pass Filter Bank Splice Detection                       │
 │                                                                             │
 │  [Module 3: Face Biometrics & Anti-Spoofing Liveness]                       │
 │  - YOLOv8-Face Detection + MTCNN 5-point facial landmark alignment          │
 │  - ArcFace Deep Embedding Extraction & Cosine Similarity Match              │
 │  - Multi-frame Eye-blink / Head-pose Challenge-Response Liveness            │
 │                                                                             │
 │  [Module 4: Border Syndicate & Intelligence Link Analysis]                  │
 │  - Cross-checkpoint SHA-256 document recycling detection                   │
 │  - Imposter alias clustering & rapid border re-crossing alerts              │
 └──────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
        ┌───────────────────────────────────────────────────────────────┐
        │             EXPLAINABLE RISK AGGREGATION ENGINE               │
        │   Score: 0.35(Tamper) + 0.30(Face) + 0.20(Rule) + 0.15(Synd)  │
        │   Verdicts: CLEAR (0-27) | REVIEW (28-59) | FLAGGED (60-100)  │
        └───────────────────────────────┬───────────────────────────────┘
                                        │
                                        ▼
        ┌───────────────────────────────────────────────────────────────┐
        │         LEGAL LEDGER & COURT ADMISSIBILITY (BSA 2023)         │
        │   - SHA-256 Salted Field Digests (No Raw PII)                 │
        │   - Chained Merkle Ledger Block: H(n) = SHA256(H(n-1) + Data) │
        │   - Automated Section 65B Electronic Evidence Certificate     │
        └───────────────────────────────────────────────────────────────┘
```

---

## 7. Core Use Cases

| Use Case ID | Scenario | Trigger & Primary Action | Operational Outcome |
| :--- | :--- | :--- | :--- |
| **UC-01** | **Land Border Primary Passport/Visa Inspection** | Traveller presents passport at Raxaul ICP. Officer scans front bio page and back page. | In 850ms, MRZ checksums verified, photo-substitution ELA checked. Verdict: **CLEAR**. Traveller cleared. |
| **UC-02** | **Altered MRZ / Counterfeit Passport** | Smuggler alters birth year or passport number in printed visual zone, but fails to recompute check digits in MRZ. | MRZ validator flags check digit mismatch; ELA reveals localized re-compression around DOB. Verdict: **FLAGGED** (Risk: 88). |
| **UC-03** | **Fabricated Aadhaar with Verhoeff Failure** | Third-country national presents fake plastic Aadhaar card with randomly generated 12-digit number. | Verhoeff d8 check table calculates invalid checksum. Verdict: **FLAGGED** (Risk: 92, "Invalid Aadhaar Checksum"). |
| **UC-04** | **Cross-Border Imposter Ring (Syndicate)** | An Indian passport is presented at Panitanki that was presented 3 hours earlier at Raxaul by a different individual. | Intelligence graph matches salted document hash across checkpoints; ArcFace detects facial divergence. Verdict: **FLAGGED** (Risk: 96, "Syndicate Imposter"). |
| **UC-05** | **Genuine Physical Wear Disambiguation** | Villager presents laminated Nepali Nagarikta with surface scratches and moisture bubbles. | Multi-tier forensic engine analyzes background PRNU noise and texture; confirms non-malicious wear. Verdict: **CLEAR / LOW REVIEW**. No false arrest. |
| **UC-06** | **Court Prosecution Evidence Export** | Legal prosecutor requires evidence for Section 420/468 IPC / BNS trial of intercepted smuggler. | Officer clicks "Generate BSA 65B Certificate". System produces signed PDF with SHA-256 chain and device telemetry. |

---

## 8. Functional Requirements

### 8.1 Authentication & Role-Based Access Control (RBAC)
- Support secure Google OAuth and local emergency evaluator credentials.
- Roles: `Screening Officer`, `Shift Supervisor / Adjudicator`, `Super Admin`.
- Session tokens secured via `HttpOnly`, `SameSite=Lax`, `Secure` cookies.

### 8.2 Document Intake & Client-Side Pre-Flight
- Dual-dropzone support (Front Side mandatory, Back Side optional/recommended).
- Integrated live webcam capture for both document scanning and traveller portraiture.
- Automatic client-side canvas downscaling (2048px bounding box, 0.89 JPEG quality) to prevent HTTP 413 payloads on low-bandwidth satellite links.

### 8.3 Forensics & Biometric Inspection
- **MRZ Verification:** Strict implementation of ICAO Doc 9303 check digit algorithms with 7-3-1 weight multipliers.
- **Aadhaar Verification:** Full Verhoeff dihedral group $D_5$ multiplication table validation.
- **Image Forensics:** ELA discrepancy calculation, 2D-FFT spectral PAPR calculation, PRNU noise variance ratio between portrait and substrate.
- **Biometric Matching:** 1:1 face embedding cosine distance with age-invariant threshold relaxation.

### 8.4 Legal Ledger & Audit
- Continuous hash-chain block creation where $Block_n = \text{SHA256}(Block_{n-1} \parallel \text{Timestamp} \parallel \text{ReportHash})$.
- Automated generation of Section 65B Bharatiya Sakshya Adhiniyam electronic record certificates containing machine identifier, time in IST, officer credentials, and cryptographic digest.

---

## 9. Non-Functional Requirements

| Metric / Dimension | Specification | Verification Method |
| :--- | :--- | :--- |
| **Processing Latency** | $\le 1,500\text{ ms}$ total end-to-end screening latency. | Automated latency timer logged on every screening audit row. |
| **False Positive Rate** | $< 3.5\%$ false-positive rate on physically worn or laminated documents. | Evaluated against benchmark test set of 250 weathered IDs. |
| **Availability & Uptime** | $99.9\%$ operational uptime with dual SQLite/PostgreSQL automatic failover. | Graceful in-memory fallback if Neon cloud PostgreSQL is unreachable. |
| **Zero Raw Storage** | $0\text{ bytes}$ of raw image or cleartext PII stored on disk. | Automated filesystem audit in CI pipeline verifying no media writes. |
| **Security Standards** | OWASP Top 10 compliance; NIST SP 800-218 SSDF alignment. | Automated static application security testing (SAST) with Ruff/Bandit. |

---

## 10. Product and System Workflow

### 10.1 Operational Checkpoint Workflow
1. **Officer Opens Session:** Checkpoint location (e.g., Raxaul) and traveller nationality (e.g., India/Nepal) selected.
2. **Document Intake:** Officer uploads or snaps front and back images.
3. **Automated Analysis:** System executes OCR, mathematical check digits, image forensics, and biometric liveness in parallel.
4. **Instant Triage Banner:**
   - **CLEAR (Green):** Low risk score ($<28$). Officer clears passenger in one click.
   - **REVIEW (Amber):** Borderline risk score ($28–59$). Guidance cue displays specific fields for physical manual verification.
   - **FLAGGED (Red):** High risk score ($\ge 60$). Critical alerts highlight exact tampering indicators (e.g., "MRZ Check Digit Failed", "ELA Splicing Detected").
5. **Ledger Sealing:** Audit block appended to SHA-256 chain; BSA 65B evidence certificate generated on demand.

### 10.2 Team Development & Collaboration Workflow
- GitHub Trunk-Based Workflow with feature branches (`feat/`, `fix/`).
- Enforced automated pre-commit testing (`pytest tests/`) and bundle compilation (`npm run build`).

---

## 11. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLIENT TIER (Vite / React)                       │
│  - DeskView (Officer Screening Console, Dual Dropzone, Presets, Keyboard)   │
│  - ReviewQueueView (Supervisor Adjudication & Soft-Delete Review)           │
│  - StaffView (Officer Roster Management & Revocation)                       │
│  - Ledgerview (Immutable Hash Chain & BSA 65B Electronic Certificate Export)│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTPS / REST (JSON + Multipart)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          APPLICATION TIER (FastAPI)                         │
│  - Security & RBAC Middleware (Session Cookies, Google OAuth, Rate Limiting)│
│  - Zero-Storage In-Memory Stream Ingestion                                  │
│  - Core Verification Engine (ICAO 9303, Verhoeff, PAN, Nagarikta Rules)     │
│  - Forensic Pipeline (ELA, 2D-FFT PAPR, PRNU Noise Variance, SRM Splice)    │
│  - Legal Ledger Engine (SHA-256 Hash Chain & BSA 2023 Sec 65B Generator)   │
│  - AI Oracle & Fallback Knowledge Engine (Gemini 2.5 Flash / 1.5 Pro)       │
└───────────────────────┬───────────────────────────────┬─────────────────────┘
                        │                               │
                        ▼                               ▼
┌────────────────────────────────────────┐ ┌──────────────────────────────────┐
│   ML MICROSERVICE (Hugging Face Spaces)│ │      PERSISTENCE TIER (DB)       │
│  - ArcFace Deep Facial Embeddings      │ │  - Primary: Cloud Neon PostgreSQL│
│  - YOLOv8-Face Alignment               │ │  - Edge Fallback: Local SQLite   │
│  - Challenge-Response Liveness         │ │  - Stores: Salted SHA-256 Hashes,│
│  - Heuristic CPU Fallback in FastAPI   │ │    Masked PII, Ledger Chain      │
└────────────────────────────────────────┘ └──────────────────────────────────┘
```

---

## 12. Data Architecture & Zero-Raw-Storage Invariant

### 12.1 Data Domains & Masking Policies

| Domain | Representative Schema Fields | Storage & Masking Policy |
| :--- | :--- | :--- |
| **Screening Sessions** | `id`, `checkpoint`, `officer_email`, `status`, `opened_at`, `closed_at` | Plaintext metadata; no PII. |
| **Document Screening Reports** | `id`, `session_id`, `doc_type`, `risk_score`, `verdict`, `doc_number_masked` | `doc_number_masked` stored as `XXXX-XXXX-1234` or `K****567`. |
| **Cryptographic Digests** | `doc_number_hash`, `name_hash`, `dob_hash`, `report_hash` | Salted SHA-256 hex string (`HMAC-SHA256(field, SYSTEM_SALT)`). |
| **Image Buffers** | `file_bytes`, `live_frame_bytes` | **STRICT ZERO STORAGE:** Processed exclusively in volatile RAM; discarded immediately upon report generation. |
| **Immutable Ledger** | `block_height`, `prev_hash`, `curr_hash`, `merkle_root`, `timestamp` | Tamper-proof hash chain; permanently retained. |

---

## 13. Forensic Analytics & AI/ML Methodology

### 13.1 Mathematical Document Validation
- **ICAO Doc 9303 MRZ Engine:** Computes composite check digits over Document Number, Date of Birth, and Expiration Date using repeating weight sequence $[7, 3, 1] \pmod{10}$.
- **Verhoeff Dihedral $D_5$ Matrix:** Validates 12-digit Aadhaar identifiers against permutation and multiplication tables $d(i, j)$ and $p(i, j)$, detecting $100\%$ of single-digit transcription errors and $95.3\%$ of twin transpositions.

### 13.2 Multimodal Image Tampering Analysis
- **Error Level Analysis (ELA):** Resaves document at $90\%$ JPEG quality; computes difference matrix $|I_{orig} - I_{resave}|$. Splices and digital text modifications exhibit significantly elevated error variance compared to original substrate.
- **2D-FFT Spectral Peak-to-Average Power Ratio (PAPR):** Analyzes high-frequency Fourier spectrum to detect synthetic AI-generated artifacts, screen re-capture moiré patterns, and halftone printing discrepancies.
- **PRNU & Laplacian Blur Variance:** Compares sensor noise residuals across portrait and card background to flag photo-replacement splices while ignoring natural lens softness.

### 13.3 Face Biometrics & Liveness
- **ArcFace Embedding Cosine Similarity:** Computes normalized 512-dimensional facial embeddings. Match score $S = \cos(\theta) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\| \|\mathbf{v}\|}$.
- **Anti-Spoofing Challenge-Response:** Tracks multi-frame eye-aspect ratio (EAR) and head yaw/pitch angles to prevent 2D photo printout or smartphone video playback attacks.

---

## 14. Risk Scoring & Explainability Engine

### 14.1 Composite Risk Formula
$$\text{Risk Score} = 0.35 \cdot R_{\text{tamper}} + 0.30 \cdot R_{\text{face}} + 0.20 \cdot R_{\text{rule}} + 0.15 \cdot R_{\text{syndicate}}$$

### 14.2 Decision Thresholds & Operational Verdicts
- **CLEAR ($0 \le \text{Score} < 28$):** All checksums valid, no localized compression anomalies, biometric match confident. Traveller cleared.
- **REVIEW ($28 \le \text{Score} < 60$):** Borderline anomalies (e.g., surface wear, mild name abbreviation discrepancy). Manual officer inspection guidance displayed.
- **FLAGGED ($60 \le \text{Score} \le 100$):** Critical failure (e.g., MRZ checksum mismatch, photo splice detected, syndicate duplicate). Shift supervisor alerted.

---

## 15. Application Modules (M1 to M9)

- **M1: Officer Authentication & RBAC:** Session management, Google OAuth integration, secure supervisor credential validation.
- **M2: Desk Intake & Camera Capture:** Dual-dropzone file ingestion, live browser webcam capture, client-side auto-downscaling.
- **M3: Mathematical Checksum Engine:** ICAO 9303 MRZ parser, Verhoeff Aadhaar matrix, PAN and Nagarikta structural rules.
- **M4: Deep Image Forensics Engine:** In-memory ELA, 2D-FFT spectral PAPR, PRNU noise variance, and SRM splice detector.
- **M5: Facial Biometrics & Liveness:** ArcFace face embedding comparator and challenge-response liveness validator.
- **M6: Zero-Knowledge Selective Disclosure:** Zero-raw-storage field digest calculator and age/citizenship selective disclosure gates.
- **M7: Immutable Blockchain Ledger & BSA 65B:** SHA-256 Merkle chain logger and automated court-admissible PDF certificate generator.
- **M8: Cross-Checkpoint Syndicate Intelligence:** Graph analysis detecting recycled identity documents and cross-border imposter rings.
- **M9: AI Oracle Assistant:** Gemini 2.5 Flash / 1.5 Pro border assistant with complete knowledge of SSB operational border protocols.

---

## 16. Officer Desk and Inspection Experience

The Officer Desk console is engineered according to strict human-factors principles to avoid cognitive fatigue during multi-hour border shifts:
- **Unified Sovereign Navy Console:** High-contrast authoritative command palette (`#061528` background with `#d97706` amber border-top) ensuring crisp readability in high-glare border environments.
- **Dual-Sided Dropzone Architecture:** Front side (primary bio page) and back side (address/guardians) dropzones side-by-side with instantaneous live image thumbnails.
- **1-Click Test Presets:** High-visibility pastel specimen chips for instant demonstration: Clean Passport, Tampered MRZ, Syndicate Imposter, Driving Licence, PAN Card, Clean Aadhaar, Tampered Aadhaar, and Nepali Nagarikta.
- **Keyboard-Driven Execution:** Complete screening cycle triggerable via `[Ctrl + Enter]`.

---

## 17. Alert, Escalation & Shift Handover System

- **Tiered Operational Alerts:** 
  - *Level 1 (Info):* Document screened CLEAR, logged to session.
  - *Level 2 (Warning):* Physical wear detected, officer guided to verify lamination.
  - *Level 3 (Critical Alert):* Forgery confirmed, supervisor escalation modal triggered.
- **Cryptographic Shift Handover Token:** Generates a sealed digital handover packet summarizing total passengers cleared, flagged imposters, and Merkle chain root hash signed by the outgoing shift inspector.

---

## 18. Technology Stack

| Layer | Selected Technology | Technical Justification |
| :--- | :--- | :--- |
| **Frontend Framework** | React 18 + Vite + TypeScript | Type-safe, high-speed single-page application with sub-second page transitions. |
| **UI Styling** | Vanilla Modern CSS (Sovereign Design System) | Zero CSS runtime overhead; complete design control without brittle framework churn. |
| **Backend Framework** | FastAPI (Python 3.12) | Asynchronous, high-throughput, native OpenAPI documentation, standard in Python AI/ML ecosystem. |
| **Database & ORM** | PostgreSQL (Neon DB) + SQLAlchemy 2.0 | Production-grade relational storage with automated local SQLite offline fallback. |
| **Forensic & Computer Vision** | OpenCV, Pillow, NumPy, SciPy | In-memory image processing for ELA, FFT spectral analysis, and PRNU noise extraction. |
| **Deep Learning & Biometrics**| PyTorch, ONNX Runtime, ArcFace, YOLOv8 | High-accuracy facial feature extraction with optimized CPU/GPU execution. |
| **Cryptography** | Python `hashlib`, `hmac`, WebCrypto API | SHA-256 Merkle trees, HMAC salt hashing, and Ed25519 digital signature support. |
| **Hosting & Deployment** | Vercel (Edge API) + Hugging Face Spaces (ML Node) | Serverless scalability with zero infrastructure maintenance overhead. |

---

## 19. API and Integration Contract

### 19.1 Core Endpoints Table

| Method | Endpoint | Description | Request Type | Response Type |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/admin/login` | Authenticate officer credentials | Form (`credential`) | `{ ok: true, admin: string }` |
| `GET` | `/api/sessions/open` | Fetch current active screening session | Query (`checkpoint`) | `ScreeningSession` |
| `POST` | `/api/sessions` | Initialize new screening session | JSON (`checkpoint`, `nationality`) | `ScreeningSession` |
| `POST` | `/api/screen` | Execute multimodal document triage | Multipart (`file`, `file_back`, `doc_type`) | `ScreenReport` |
| `GET` | `/api/ledger/blocks` | Retrieve immutable hash-chain ledger | None | `LedgerBlock[]` |
| `GET` | `/api/ledger/cert/65b/{id}` | Export BSA 2023 Section 65B Certificate | Path (`report_id`) | PDF Stream / JSON Audit |

### 19.2 Sample Screening Response (`/api/screen`)
```json
{
  "report_id": "rep_94a2b8e5",
  "verdict": "FLAGGED",
  "risk_score": 84,
  "doc_type": "PASSPORT",
  "doc_number_masked": "K****567",
  "checks": {
    "mrz_checksum": { "status": "FAIL", "detail": "MRZ Check Digit 2 mismatch on birth date." },
    "ela_tampering": { "status": "FAIL", "damage_ratio": 0.42, "detail": "Localized splice detected in photo zone." },
    "face_biometrics": { "status": "PASS", "similarity": 0.91, "method": "ArcFace" },
    "syndicate_match": { "status": "WARN", "detail": "Same passport hash presented at Raxaul 2h ago." }
  },
  "ledger_block": {
    "height": 412,
    "block_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "timestamp_ist": "2026-09-26 00:30:15 IST"
  }
}
```

---

## 20. Development and Collaboration Workflow

- **Work Management:** Features and bug fixes tracked via structured milestone issues with explicit acceptance criteria.
- **Git Branching Policy:** Protected `main` branch. All work completed in topical branches (`feat/`, `fix/`).
- **CI Quality Gates:** Every pull request requires:
  1. `ruff check .` (Python linting & formatting).
  2. `pytest tests/` (Unit and integration regression tests passing 100%).
  3. `npm run build` (TypeScript compilation and Vite single-file bundling).

---

## 21. Repository and Code Organization

```
NO-CAP---SIH/
├── app/
│   ├── main.py               # Core FastAPI monolith & route definitions
│   ├── config.py             # Pydantic environment configuration & secrets
│   ├── db.py                 # SQLAlchemy database engine & session factory
│   ├── models.py             # Database ORM models (Sessions, Reports, Ledger)
│   ├── forensics.py          # Multimodal image forensics (ELA, FFT, PRNU, SRM)
│   ├── biometrics.py         # ArcFace & YOLOv8-Face feature extractors
│   ├── mrz.py                # ICAO Doc 9303 MRZ & Verhoeff checksum validators
│   ├── bsa_cert.py           # Bharatiya Sakshya Adhiniyam 2023 Sec 65B generator
│   └── static/
│       └── index.html        # Compiled, inlined single-file production bundle
├── frontend/
│   ├── src/
│   │   ├── api.ts            # Typed backend API client & error handlers
│   │   ├── styles.css        # Sovereign Navy design system tokens & classes
│   │   ├── views/
│   │   │   ├── DeskView.tsx  # Border screening console & dual dropzone
│   │   │   ├── ReviewQueueView.tsx # Supervisor adjudication workspace
│   │   │   ├── StaffView.tsx # Officer roster & permission management
│   │   │   └── LedgerView.tsx# Hash-chain blocks & BSA certificate viewer
│   │   └── app/
│   │       ├── util.ts       # Client-side image optimizer & formatters
│   │       └── specimens.ts  # 1-click test specimen generators
│   └── package.json          # Vite / React build configuration
├── ml_service/               # Hugging Face Spaces standalone ML container
│   ├── app.py                # Dedicated inference server for deep models
│   └── requirements.txt
├── tests/                    # Pytest test suite (MRZ, Verhoeff, Forensics, API)
├── requirements.txt          # Python dependencies
└── vercel.json               # Serverless deployment configuration
```

---

## 22. Team Responsibilities & Ownership Matrix

| Member / Role | Primary Ownership | Secondary Responsibility |
| :--- | :--- | :--- |
| **Product & Architecture Lead** | System architecture, BSA 65B compliance, end-to-end integration | Code reviews, demo rehearsal |
| **Computer Vision / ML Engineer** | ELA, 2D-FFT spectral analysis, PRNU sensor noise, ArcFace embeddings | Model calibration & false-positive tuning |
| **Backend & Security Engineer** | FastAPI endpoints, RBAC, Zero-Storage memory streams, rate limiting | Database migrations & SQLite fallback |
| **Frontend / UX Engineer** | React DeskView console, dropzones, keyboard shortcuts, accessibility | Visual hierarchy & high-contrast styling |
| **Cryptography & Ledger Engineer**| SHA-256 Merkle chain, Verhoeff/ICAO algorithms, Section 65B PDF export | Zero-Knowledge proof protocols |
| **DevOps & QA Engineer** | CI/CD automation, Vercel/HuggingFace deployment, pytest test suite | Load testing & offline resilience checks |

---

## 23. Testing and Evaluation Strategy

```
               /  End-to-End Golden Path Demo Test   \
              /---------------------------------------\
             /     API & Integration Route Tests       \
            /-------------------------------------------\
           /   Unit Tests: MRZ, Verhoeff, ELA, Hashes    \
          /-----------------------------------------------\
          lint (Ruff) | typecheck (tsc) | security (Bandit)
```

- **Golden Path Acceptance Test:** Full execution flow verifying document upload $\to$ parallel forensic pass $\to$ risk score computation $\to$ ledger insertion $\to$ BSA 65B PDF generation in $< 1,500\text{ ms}$.
- **Edge-Case Checksum Test:** 50 test vectors verifying detection of swapped MRZ characters, modified DOBs, and invalid Verhoeff digits.
- **Memory Leak & Storage Verification:** Test suite actively asserts that no temporary `.jpg` or `.pdf` files remain in filesystem after request termination.

---

## 24. Security, Privacy & Legal Governance (DPDP 2023 & BSA 65B)

1. **Digital Personal Data Protection Act (DPDP), 2023:**
   - Enforces the **Zero-Raw-Storage** architectural pattern.
   - PII is masked on the UI and never persisted in database tables.
   - Cross-matching relies exclusively on one-way salted HMAC-SHA256 digests.
2. **Bharatiya Sakshya Adhiniyam (BSA), 2023 — Section 65B:**
   - In accordance with Section 65B(4) governing electronic records in Indian courts, every generated screening report produces an automated cryptographic certificate identifying:
     - The electronic device hash and operational checkpoint.
     - Hash of the input document and screening output.
     - Exact timestamp in Indian Standard Time (IST).
     - Merkle root proof guaranteeing absence of post-hoc record alteration.

---

## 25. MLOps, False-Positive Tuning & Model Governance

- **Adaptive False-Positive Mitigation:** Worn, laminated documents produce natural optical noise. NO-CAP utilizes a dual-threshold texture analyzer that weights PRNU sensor noise against local blur variance, ensuring weathered physical IDs are not incorrectly flagged as synthetic forgeries.
- **Graceful Heuristic Fallback:** If the high-intensity neural network service on Hugging Face is unreachable, the system automatically falls back to native CPU heuristics (Pillow ELA, mathematical check digits, OpenCV feature matching) without service disruption.

---

## 26. Deployment Architecture (Hybrid Cloud & Edge Fallback)

- **Production Cloud Deployment:**
  - Frontend & API: Vercel Serverless Edge runtime.
  - Relational Database: Neon Serverless PostgreSQL with connection pooling.
  - Deep Inference Node: Hugging Face Spaces (Dockerized PyTorch/ArcFace container).
- **Edge / Checkpoint Local Fallback:**
  - Docker Compose running FastAPI + SQLite + pre-bundled static frontend locally on checkpoint laptop, ensuring $100\%$ operational continuity during border internet outages.

---

## 27. MVP and Future Scope

### 27.1 MVP Capabilities (Current Production)
- Full support for Indian Passport, Aadhaar, PAN, DL, and Nepali Nagarikta.
- Parallel ELA, FFT spectral analysis, and Verhoeff validation.
- ArcFace facial biometrics with challenge-response liveness.
- Instant SHA-256 hash-chain ledger & Section 65B BSA certificate export.
- Real-time Neon PostgreSQL synchronization with live WebSocket/polling updates.

### 27.2 Post-Hackathon Roadmap
- **Phase 2 (e-Passport NFC):** Integrate physical contactless smartcard readers for ICAO Doc 9303 RFID passport chips.
- **Phase 3 (LPAI e-Gates):** Deploy REST webhooks to Land Ports Authority of India automated entry barriers.
- **Phase 4 (Offline Mesh Sync):** Enable peer-to-peer Wi-Fi mesh synchronization across remote SSB border outposts.

---

## 28. Risks, Assumptions and Mitigations

| Risk / Assumption | Severity | Mitigation Strategy |
| :--- | :--- | :--- |
| **Low-Quality Checkpoint Cameras** | High | Client-side canvas auto-enhancement and contrast normalization prior to inference. |
| **Complete Border Internet Outage** | Critical | Dual-path SQLite engine and local browser caching enabling 100% offline screening. |
| **Physical Card Creases & Scratches** | Medium | Texture-aware forensic filters that distinguish physical creasing from digital pixel splices. |
| **High Passenger Arrival Spikes** | High | Sub-second execution pipeline and client-side background pre-fetching. |

---

## 29. Golden Path Live Demo Workflow

The Smart India Hackathon jury demonstration follows a deterministic, 12-step operational narrative:

1. **Officer Login:** Officer logs into Raxaul Integrated Check Post console.
2. **Session Initialization:** System displays active session with bilateral Indo-Nepal screening protocol.
3. **Clean Passport Screening:** Officer clicks `[Clean Indian Passport]` preset; hits `[Ctrl + Enter]`. System returns **CLEAR** in 780ms.
4. **Tampered MRZ Interception:** Officer clicks `[Tampered Passport (Altered MRZ)]`. System flags check digit failure in red; displays exact mismatched digit.
5. **Aadhaar Forgery Check:** Officer clicks `[Tampered Aadhaar Card]`. System triggers mathematical failure: **"Invalid Verhoeff Dihedral Checksum"**.
6. **Syndicate Imposter Detection:** Officer clicks `[Syndicate Imposter Passport]`. Intelligence engine surfaces duplicate document alert across checkpoints.
7. **Nepali Nagarikta Verification:** Officer screens genuine Nepali citizenship certificate; verified under Indo-Nepal 1950 Treaty rules.
8. **Live Camera Capture:** Officer activates webcam; live document photo captured and auto-optimized in memory.
9. **Supervisor Adjudication:** Officer opens Review Queue; supervisor inspects side-by-side forensic ELA heatmap.
10. **Zero-Knowledge Proof Demo:** Officer demonstrates Age $\ge 18$ selective disclosure gate without exposing passenger birth date.
11. **Immutable Ledger Audit:** Officer opens Ledger view; verifies Merkle tree height and SHA-256 block hash.
12. **BSA Section 65B Export:** Officer clicks "Export 65B Certificate"; downloads tamper-evident electronic evidence certificate ready for court.

---

## 30. Deliverables and Presentation Plan

1. **Master Engineering Blueprint:** This document (`SIH26188_ENGINEERING_BLUEPRINT.md`).
2. **Live Production Web Portal:** Deployed and accessible at `https://no-cap-sih.vercel.app`.
3. **Deep Forensic Inference Service:** Deployed on Hugging Face Spaces.
4. **Complete Git Source Code:** Full repository with clean history, modular architecture, and zero hardcoded secrets.
5. **Interactive Juror Slide Deck:** 10-slide high-impact presentation covering problem context, live demo, forensic math, and legal admissibility.

---

## 31. Definition of Done (DoD)

- [x] Code strictly adheres to Python 3.12, FastAPI, and React 18 single-file standards.
- [x] Zero-Raw-Storage invariant verified: no unencrypted PII or passenger images written to disk.
- [x] Full automated test coverage for ICAO 9303 MRZ and Verhoeff Aadhaar checksums.
- [x] Production build passes `tsc --noEmit` and Vite bundling with zero errors.
- [x] Live cloud deployment operational on Vercel with Neon PostgreSQL resilience.
- [x] Court-admissible Section 65B certificate generation verified against Bharatiya Sakshya Adhiniyam standards.

---

## 32. Reference Standards and Legal Frameworks

- **ICAO Doc 9303:** *Machine Readable Travel Documents (Part 1–12)*, International Civil Aviation Organization.
- **Bharatiya Sakshya Adhiniyam (BSA), 2023:** *Section 65B — Admissibility of Electronic Records*, Ministry of Law and Justice, Government of India.
- **Digital Personal Data Protection Act (DPDP), 2023:** *Principles of Storage Limitation & Purpose Limitation*, Government of India.
- **Verhoeff, J. (1969):** *Error Detecting Decimal Codes*, Mathematical Centre Tract 29, Amsterdam.
- **ISO/IEC 19794-5:** *Information technology — Biometric data interchange formats — Part 5: Face image data*.
- **NIST SP 800-218:** *Secure Software Development Framework (SSDF) Version 1.1*, National Institute of Standards and Technology.
