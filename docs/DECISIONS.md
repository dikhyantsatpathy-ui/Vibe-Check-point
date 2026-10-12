# Decisions Log (Master Work Order v7)

| Date | Options | Choice | Reason |
|---|---|---|---|
| 2026-10-11 | Demo Pass / Watchlist Authz (F-01) | Require DEMO_PASS_ENABLED=1 and role evaluator 403 on restricted routes | Prevent demo backdoor in production; enforce least-privilege role auth |
| 2026-10-11 | ML Microservice Secret Precedence (F-02) | ML_SERVICE_SECRET preferred over ML_SECRET_KEY, hmac compare_digest | Consistent naming across microservices while preserving backwards compatibility |
| 2026-10-12 | ArcFace Model Path (A2/A4) | Load from `FACE_EMBED_MODEL` or `data/models/w600k_r50.onnx` | Model verified on disk (174MB), produces 512-d normalized embeddings without network download |
| 2026-10-12 | Fail-Safe Face Contract (A3/A7/A8) | If mode != 'arcface', decision is strictly never 'MATCH'; remote ML failure fails closed | Invariant FS: system must never autonomously CLEAR on unverified, fallback, or failed remote face matching |
| 2026-10-12 | ML Service Module Isolation | Explicit `ml_service.<mod>` imports in `ml_service/main.py` | Prevents test-runner namespace pollution where `app.<mod>` shadowed `ml_service.<mod>` and triggered remote HTTP network loops |
| 2026-10-12 | Single face-threshold policy (P1) | Single step policy = owner's original Feature 3; sliding relaxations removed because no impostor measurement supports them | Canonical BASE_SAME 0.60, AGED_SAME 0.52 (>=5y), DIFF 0.40; bounded overrides (0.30 <= AGED <= BASE <= 0.90) |
