# Blueprint vs. Reality — Claims Verification Report
**Generated UTC:** 20261011_182816 | **Branch:** `ml/blueprint-sync-v7`

## Summary
- **VERIFIED:** 62
- **FALSE:** 15
- **UNVERIFIABLE:** 1

## Detailed Claims Ledger
| ID | Section | Claim | Check Kind | Verdict | Detail |
|---|---|---|---|---|---|
| C-01 | 21.1 | Strict pinning in all requirements manifests | file | **FALSE** | Root requirements unpinned: False, ML service pinned: True |
| C-02 | 9 / 27 | Strict Content-Security-Policy headers enforced | cmd | **FALSE** | No Content-Security-Policy header returned on / |
| C-03 | 20 / 22 / A08 | Merkle tree audit trail for ledger blocks | cmd | **FALSE** | No Merkle tree computation found |
| C-04 | 27 / A10 | Outbound-URL destination domain allow-listing against SSRF | file | **FALSE** | Outbound ML URL read directly from ML_SERVICE_URL env var without destination domain allowlisting |
| C-05 | 15.4 / 21 | ArcFace 512-dimensional facial biometric embedding matching | cmd | **FALSE** | ArcFace 512-D claimed but falls back to 64-bit dHash perceptual hash when model unmounted |
| C-06 | 17 / 26 | Test suite total count equals 305 tests | cmd | **VERIFIED** | 305 tests collected across suite |
| C-07 | 14.1 / 15.1 | Zero-raw-storage: motion photo temp video file handling | file | **VERIFIED** | Temp .mp4 written for motion photo extraction and reliably unlinked in finally |
| C-08 | 15.1 / 31 | Card Detector v2 (RF-DETR Small INT8) accepted with 0.63% Neg FP Rate | file | **FALSE** | Blueprint §31 marks Card INT8 ACCEPTED, but production default is YOLOv8 and bakeoff records {'models': {'yolov8': {'license': 'AGPL-3.0 (Copyleft restrictions for proprietary deployments)', 'nms_required': True, 'card_mAP50': 0.0, 'aadhaar_mAP50': 0.992, 'card_p50_ms': 152.16, 'aadhaar_p50_ms': 152.98}, 'rf_detr': {'license': 'Apache 2.0 (Permissive, unrestricted commercial & gov deployments)', 'nms_required': False, 'card_mAP50': 0.0, 'aadhaar_mAP50': 0.0, 'card_p50_ms': None, 'aadhaar_p50_ms': None}}, 'recommendation': "Deploy RF-DETR (Apache 2.0) for production checkpoint deployments to eliminate AGPL copyleft liability, while maintaining YOLOv8 operational side-by-side via DETECTOR_BACKEND='yolov8' for backward compatibility."} |
| C-09 | 15.1 / 31 | MRZ Phase C2 check-digit recovery achieves 74% on held-out crops | file | **VERIFIED** | MRZ metrics accurately attributed |
| C-10 | 27.1 / 29 | Multi-Environment Isolation: production vs staging Neon branches | cmd | **UNVERIFIABLE** | Requires Vercel CLI credentials to query live production and staging project env vars |
| C-11 | 27.1 / 31 | Rule 12 Fail-Safe Invariant definition | file | **FALSE** | Blueprint conflates fail-closed auth with fail-safe screening (Rule 12 vs Invariant FS/AUTH) |
| C-12 | 27 / A10 | MAX_IMAGE_PIXELS decompression bomb protection | cmd | **VERIFIED** | Custom MAX_IMAGE_PIXELS=None enforced |
| C-13 | 27 / A10 | 15MB request payload boundary enforced | file | **FALSE** | No explicit 15MB upload stream limit in app/main.py |
| C-14 | 9 / 15 / 31 | End-to-end and detector pipeline latency budgets | file | **VERIFIED** | Consistent latency budget |
| C-15 | 28 / 31 | Statutory compliance and legal admissibility claims | file | **FALSE** | Blueprint claims definitive legal compliance without qualification; legal review pending counsel |
| C-16 | 15.4 | Face matching accuracy figures (98.4% / 99.1%) | file | **VERIFIED** | No unproven face accuracy metrics in blueprint |
| EP-POST-/api/admin/login | 22 | Endpoint POST /api/admin/login implemented | cmd | **VERIFIED** | Route registered: POST /api/admin/login |
| EP-POST-/api/admin/demo_login | 22 | Endpoint POST /api/admin/demo_login implemented | cmd | **VERIFIED** | Route registered: POST /api/admin/demo_login |
| EP-GET-/api/admin/me | 22 | Endpoint GET /api/admin/me implemented | cmd | **VERIFIED** | Route registered: GET /api/admin/me |
| EP-POST-/api/admin/logout | 22 | Endpoint POST /api/admin/logout implemented | cmd | **VERIFIED** | Route registered: POST /api/admin/logout |
| EP-GET-/api/sessions/open | 22 | Endpoint GET /api/sessions/open implemented | cmd | **FALSE** | Route GET /api/sessions/open not registered in FastAPI app |
| EP-POST-/api/sessions | 22 | Endpoint POST /api/sessions implemented | cmd | **VERIFIED** | Route registered: POST /api/sessions |
| EP-POST-/api/screen | 22 | Endpoint POST /api/screen implemented | cmd | **VERIFIED** | Route registered: POST /api/screen |
| EP-GET-/api/reports/{id} | 22 | Endpoint GET /api/reports/{id} implemented | cmd | **FALSE** | Route GET /api/reports/{id} not registered in FastAPI app |
| EP-GET-/api/ledger/blocks | 22 | Endpoint GET /api/ledger/blocks implemented | cmd | **FALSE** | Route GET /api/ledger/blocks not registered in FastAPI app |
| EP-GET-/api/ledger/verify | 22 | Endpoint GET /api/ledger/verify implemented | cmd | **FALSE** | Route GET /api/ledger/verify not registered in FastAPI app |
| EP-GET-/api/ledger/cert/65b/{id} | 22 | Endpoint GET /api/ledger/cert/65b/{id} implemented | cmd | **FALSE** | Route GET /api/ledger/cert/65b/{id} not registered in FastAPI app |
| EP-POST-/api/ledger/anchor | 22 | Endpoint POST /api/ledger/anchor implemented | cmd | **FALSE** | Route POST /api/ledger/anchor not registered in FastAPI app |
| FILE-api_index.py | 25 | Repository file api/index.py exists on disk | file | **VERIFIED** | File exists (287 bytes) |
| FILE-app_main.py | 25 | Repository file app/main.py exists on disk | file | **VERIFIED** | File exists (227545 bytes) |
| FILE-app_keys.py | 25 | Repository file app/keys.py exists on disk | file | **VERIFIED** | File exists (5845 bytes) |
| FILE-app_screening.py | 25 | Repository file app/screening.py exists on disk | file | **VERIFIED** | File exists (86195 bytes) |
| FILE-app_extraction.py | 25 | Repository file app/extraction.py exists on disk | file | **VERIFIED** | File exists (21002 bytes) |
| FILE-app_validation.py | 25 | Repository file app/validation.py exists on disk | file | **VERIFIED** | File exists (7986 bytes) |
| FILE-app_mrz.py | 25 | Repository file app/mrz.py exists on disk | file | **VERIFIED** | File exists (21893 bytes) |
| FILE-app_mrz_enhancer.py | 25 | Repository file app/mrz_enhancer.py exists on disk | file | **VERIFIED** | File exists (5944 bytes) |
| FILE-app_forensics.py | 25 | Repository file app/forensics.py exists on disk | file | **VERIFIED** | File exists (38342 bytes) |
| FILE-app_tampering.py | 25 | Repository file app/tampering.py exists on disk | file | **VERIFIED** | File exists (19113 bytes) |
| FILE-app_doc_forgery.py | 25 | Repository file app/doc_forgery.py exists on disk | file | **VERIFIED** | File exists (12004 bytes) |
| FILE-app_face_match.py | 25 | Repository file app/face_match.py exists on disk | file | **VERIFIED** | File exists (11821 bytes) |
| FILE-app_face.py | 25 | Repository file app/face.py exists on disk | file | **VERIFIED** | File exists (6507 bytes) |
| FILE-app_identity.py | 25 | Repository file app/identity.py exists on disk | file | **VERIFIED** | File exists (28166 bytes) |
| FILE-app_rectification.py | 25 | Repository file app/rectification.py exists on disk | file | **VERIFIED** | File exists (5684 bytes) |
| FILE-app_remote_ml.py | 25 | Repository file app/remote_ml.py exists on disk | file | **VERIFIED** | File exists (3677 bytes) |
| FILE-app_syndicate.py | 25 | Repository file app/syndicate.py exists on disk | file | **VERIFIED** | File exists (6320 bytes) |
| FILE-app_session.py | 25 | Repository file app/session.py exists on disk | file | **VERIFIED** | File exists (25263 bytes) |
| FILE-app_stats.py | 25 | Repository file app/stats.py exists on disk | file | **VERIFIED** | File exists (8489 bytes) |
| FILE-app_doctype_cls.py | 25 | Repository file app/doctype_cls.py exists on disk | file | **VERIFIED** | File exists (8483 bytes) |
| FILE-app_qr_decoder.py | 25 | Repository file app/qr_decoder.py exists on disk | file | **VERIFIED** | File exists (15539 bytes) |
| FILE-app_transliterate.py | 25 | Repository file app/transliterate.py exists on disk | file | **VERIFIED** | File exists (3403 bytes) |
| FILE-app_heif_support.py | 25 | Repository file app/heif_support.py exists on disk | file | **VERIFIED** | File exists (862 bytes) |
| FILE-app_llm.py | 25 | Repository file app/llm.py exists on disk | file | **VERIFIED** | File exists (9659 bytes) |
| FILE-app_yolo_roi.py | 25 | Repository file app/yolo_roi.py exists on disk | file | **VERIFIED** | File exists (49706 bytes) |
| FILE-app_codebase.py | 25 | Repository file app/codebase.py exists on disk | file | **VERIFIED** | File exists (16908 bytes) |
| FILE-app_config.py | 25 | Repository file app/config.py exists on disk | file | **VERIFIED** | File exists (11907 bytes) |
| FILE-app_guide.py | 25 | Repository file app/guide.py exists on disk | file | **VERIFIED** | File exists (7213 bytes) |
| FILE-app_static_index.html | 25 | Repository file app/static/index.html exists on disk | file | **VERIFIED** | File exists (396648 bytes) |
| FILE-docs_AUDIT_V4.md | 25 | Repository file docs/AUDIT_V4.md exists on disk | file | **VERIFIED** | File exists (6393 bytes) |
| FILE-docs_AUDIT_V5.md | 25 | Repository file docs/AUDIT_V5.md exists on disk | file | **VERIFIED** | File exists (1131 bytes) |
| FILE-docs_DATASET_CREDITS.md | 25 | Repository file docs/DATASET_CREDITS.md exists on disk | file | **VERIFIED** | File exists (3525 bytes) |
| FILE-docs_DEPENDENCY_LICENCES.md | 25 | Repository file docs/DEPENDENCY_LICENCES.md exists on disk | file | **VERIFIED** | File exists (1857 bytes) |
| FILE-docs_DEPLOYMENT_ISOLATION.md | 25 | Repository file docs/DEPLOYMENT_ISOLATION.md exists on disk | file | **VERIFIED** | File exists (1512 bytes) |
| FILE-docs_LIMITATIONS.md | 25 | Repository file docs/LIMITATIONS.md exists on disk | file | **VERIFIED** | File exists (3032 bytes) |
| FILE-docs_ML_PIPELINE.md | 25 | Repository file docs/ML_PIPELINE.md exists on disk | file | **VERIFIED** | File exists (5742 bytes) |
| FILE-docs_ML_PIPELINE_CHANGES.md | 25 | Repository file docs/ML_PIPELINE_CHANGES.md exists on disk | file | **VERIFIED** | File exists (28328 bytes) |
| FILE-docs_MODEL_CARD.md | 25 | Repository file docs/MODEL_CARD.md exists on disk | file | **VERIFIED** | File exists (3250 bytes) |
| FILE-docs_OPERATIONS.md | 25 | Repository file docs/OPERATIONS.md exists on disk | file | **VERIFIED** | File exists (3346 bytes) |
| FILE-docs_OWNER_TODO.md | 25 | Repository file docs/OWNER_TODO.md exists on disk | file | **VERIFIED** | File exists (3283 bytes) |
| FILE-docs_RESUME_AFTER_SPECIMENS.md | 25 | Repository file docs/RESUME_AFTER_SPECIMENS.md exists on disk | file | **VERIFIED** | File exists (4114 bytes) |
| FILE-docs_SWITCH_READINESS.md | 25 | Repository file docs/SWITCH_READINESS.md exists on disk | file | **VERIFIED** | File exists (5189 bytes) |
| FILE-docs_TRAINING_PROGRESS.md | 25 | Repository file docs/TRAINING_PROGRESS.md exists on disk | file | **VERIFIED** | File exists (75525 bytes) |
| FILE-ml_service_Dockerfile | 25 | Repository file ml_service/Dockerfile exists on disk | file | **VERIFIED** | File exists (655 bytes) |
| FILE-ml_service_main.py | 25 | Repository file ml_service/main.py exists on disk | file | **VERIFIED** | File exists (16092 bytes) |
| FILE-ml_service_media_processor.py | 25 | Repository file ml_service/media_processor.py exists on disk | file | **VERIFIED** | File exists (16044 bytes) |
| FILE-ml_service_requirements.txt | 25 | Repository file ml_service/requirements.txt exists on disk | file | **VERIFIED** | File exists (240 bytes) |
| FILE-ml_service_yolo_roi.py | 25 | Repository file ml_service/yolo_roi.py exists on disk | file | **VERIFIED** | File exists (39859 bytes) |
| FILE-scripts_anchor_ledger.py | 25 | Repository file scripts/anchor_ledger.py exists on disk | file | **VERIFIED** | File exists (6691 bytes) |
| FILE-scripts_audit_secrets_s1.py | 25 | Repository file scripts/audit_secrets_s1.py exists on disk | file | **VERIFIED** | File exists (6670 bytes) |
