# Audit Findings Register (Work Order v7)

| ID | Severity | Area | Evidence Path | Status | Commit | Description |
|---|---|---|---|---|---|---|
| C-01 | S2 | claims/21.1 | requirements.txt, ml_service/requirements.txt, training/requirements-train.txt | RESOLVED | Phase F | Strict pinning with == across all manifests |
| C-02 | S2 | claims/9 / 27 | app/main.py, tests/test_csp_headers.py | RESOLVED | Phase F | Content-Security-Policy-Report-Only header enforced without unsafe-eval |
| C-03 | S2 | claims/20 / 22 / A08 | eval/runs/20261011_reverify_v1/code_health_c.json | RESOLVED | Phase C | Binary Merkle tree root computation implemented in app/session.py and exposed via /api/sessions/ledger/blocks and verify |
| C-04 | S2 | claims/27 / A10 | eval/runs/20261011_reverify_v1/code_health_c.json | RESOLVED | Phase C | Outbound ML URL destination domain allowlisting enforced in app/remote_ml.py via ALLOWED_ML_DOMAINS |
| C-05 | S2 | claims/15.4 / 21 | app/face_match.py, ml_service/face_match.py, tests/test_face_match.py | RESOLVED | 0fac786 | ArcFace 512-dimensional facial biometric embedding matching; fail-safe contract enforced (mode != arcface never matches) |
| S1-01 | S1 | git history | commit 3724e9e3, eval/runs/20261011_reverify_v1/secrets_scan.json | ACTION REQUIRED | 3724e9e3 | Hardcoded Neon connection string embedded in commit 3724e9e3; tree clean, owner rotation required in OWNER_TODO Item 8 |
| C-08 | S2 | claims/15.1 / 31 | eval/runs/20261011_reverify_v1/model_facts_m.json | RESOLVED | Phase M | Reconciled RF-DETR Card INT8 acceptance vs scale gate reality (recall 1.0, FP 0.63%, scale 2x/3x failed 44.3%/9.7%) on frozen manifest card_v7.json |
| C-11 | S2 | claims/27.1 / 31 | eval/runs/20261011_182816_claims/report.json | OPEN | | Rule 12 Fail-Safe Invariant definition -- Reality: Blueprint conflates fail-closed auth with fail-safe screening (Rule 12 vs Invariant FS/AUTH) |
| C-13 | S3 | claims/27 / A10 | app/main.py, ml_service/main.py, tests/test_upload_limits.py | RESOLVED | Phase F | Streaming hard cap enforced (8MB app, 15MB ML service), Content-Length check, 413 on overflow |
| C-15 | S3 | claims/28 / 31 | eval/runs/20261011_182816_claims/report.json | OPEN | | Statutory compliance and legal admissibility claims -- Reality: Blueprint claims definitive legal compliance without qualification; legal review pending counsel |
| EP-GET-/api/sessions/open | S3 | claims/22 | eval/runs/20261011_reverify_v1/code_health_c.json | RESOLVED | Phase C | Route GET /api/sessions/open registered in FastAPI app |
| EP-GET-/api/reports/{id} | S3 | claims/22 | eval/runs/20261011_reverify_v1/code_health_c.json | RESOLVED | Phase C | Route GET /api/reports/{id} registered in FastAPI app |
| EP-GET-/api/ledger/blocks | S3 | claims/22 | eval/runs/20261011_reverify_v1/code_health_c.json | RESOLVED | Phase C | Route GET /api/ledger/blocks registered in FastAPI app |
| EP-GET-/api/ledger/verify | S3 | claims/22 | eval/runs/20261011_reverify_v1/code_health_c.json | RESOLVED | Phase C | Route GET /api/ledger/verify registered in FastAPI app |
| EP-GET-/api/ledger/cert/65b/{id} | S3 | claims/22 | eval/runs/20261011_reverify_v1/code_health_c.json | RESOLVED | Phase C | Route GET /api/ledger/cert/65b/{id} registered in FastAPI app |
| EP-POST-/api/ledger/anchor | S3 | claims/22 | eval/runs/20261011_reverify_v1/code_health_c.json | RESOLVED | Phase C | Route POST /api/ledger/anchor registered in FastAPI app |
