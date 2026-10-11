# NO-CAP (SIH26188) — DEPLOYMENT ISOLATION ARCHITECTURE

## 1. Overview
The staging/test site (`vibe-check-point-test.vercel.app`) must maintain strict cryptographic, database, and credential isolation from the production deployment (`vibe-check-point.vercel.app`).

## 2. Resource Isolation Matrix

| Credential / Resource | Production (`vibe-check-point`) | Test (`vibe-check-point-test`) | Isolation Status |
|---|---|---|---|
| **Database** | Neon Production Primary Branch | Neon Dedicated `test-staging` Branch | **ISOLATED** (Separate DB) |
| **Master Vault Key** | `MASTER_VAULT_KEY_PROD` | `MASTER_VAULT_KEY_TEST` (distinct random 32-byte key) | **ISOLATED** (Independent encryption) |
| **Session Secret** | `SESSION_SECRET_PROD` | `SESSION_SECRET_TEST` | **ISOLATED** |
| **OAuth Client** | Google Client ID / Secret (prod redirect) | Dedicated Test OAuth Client (or test redirect URIs) | **ISOLATED** |
| **ML Microservice Secret** | `ML_SERVICE_SECRET_PROD` | `ML_SERVICE_SECRET_TEST` | **ISOLATED** |
| **Hugging Face Token** | Not needed on Vercel | Not needed on Vercel (Remove) | **REMOVED FROM VERCEL** |

## 3. Findings & Owner Action
- **F-003 (S2)**: `HF_TOKEN` is not read by `app/` or `frontend/` (only by `ml_service/model_fetch.py`). It should be removed from both Vercel projects to minimize attack surface.
- **F-004 (S1)**: Verify and enforce that test Vercel project does not share `DATABASE_URL` or `MASTER_VAULT_KEY` with production. Commands documented in `docs/OWNER_TODO.md`.
