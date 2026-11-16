# NO-CAP (SIH26188) — DEPLOYMENT ISOLATION ARCHITECTURE

## 1. Overview
The staging/test site (`vibe-check-point-test.vercel.app`) must maintain strict cryptographic, database, and credential isolation from the production deployment (`vibe-check-point.vercel.app`).

## 2. Resource Isolation Matrix

| Credential / Resource | Production (`vibe-check-point`) | Test (`vibe-check-point-test`) | Isolation Status |
|---|---|---|---|
| **Database** | Neon Production Primary Branch | Neon Dedicated `test-staging` Branch | **ISOLATED** (Separate DB) |
| **Master Vault Key** | `MASTER_VAULT_KEY_PROD` | `MASTER_VAULT_KEY_TEST` (distinct random 32-byte key) | **ISOLATED** (Derives `SESSION_KEY` and `SEAL_KEY` via `app/keys.py`) |
| **Session Secret** | `SESSION_SECRET` (unread legacy on Vercel) | `SESSION_SECRET` (unread legacy on Vercel) | **NOT USED IN CODE** (`MASTER_VAULT_KEY` is the canonical signer) |
| **OAuth Client** | Google Client ID / Secret (prod redirect) | Dedicated Test OAuth Client (or test redirect URIs) | **ISOLATED** |
| **ML Microservice Secret** | `ML_SERVICE_SECRET_PROD` | `ML_SERVICE_SECRET_TEST` | **ISOLATED** |
| **Hugging Face Token** | Not needed on Vercel | Not needed on Vercel (Remove) | **REMOVED FROM VERCEL** |

## 3. Findings & Owner Action
- **F-003 (S2)**: `HF_TOKEN` is not read by `app/` or `frontend/` (only by `ml_service/model_fetch.py`). It should be removed from both Vercel projects to minimize attack surface.
- **F-004 (S1)**: Verify and enforce that test Vercel project does not share `DATABASE_URL` or `MASTER_VAULT_KEY` with production. Commands documented in `docs/OWNER_TODO.md`.

## 4. Branch & Deploy Workflow
- `main` deploys **only** to production (`vibe-check-point`). Treat it as release-only.
- `staging` deploys **only** to the test project (`vibe-check-point-test`, isolated DB and keys per section 2).
- Flow: commit to `staging` → confirm `https://<test-deployment>/api/health` returns 200 → merge `staging` into `main`.
- Each Vercel project uses an *Ignored Build Step* so branches do not cross-deploy:
  - production: `[ "$VERCEL_GIT_COMMIT_REF" != "main" ]`
  - test: `[ "$VERCEL_GIT_COMMIT_REF" != "staging" ]`
  (exit 0 = skip the build). This also stops experimental previews from ever running against the production database.
- `vercel.json` must stay `{}`; a catch-all rewrite to `/api/index` 404s every route (the entrypoint is `app/main.py`).

