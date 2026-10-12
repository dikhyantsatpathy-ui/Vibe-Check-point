name: face-embedding
triggers: arcface, face, embedding, cosine, landmark, alignment, face_match, face_embed_model, biometric, selfie, w600k
- Face matching must really run a verified embedding model, or say plainly that it did not (mode `unavailable` -> INCONCLUSIVE -> REVIEW).
- Model files come only from the private HF repo through `ml_service/model_fetch.py`, pinned by SHA-256 in `ml_service/models/MODEL_MANIFEST.json`. Empty or missing SHA = refuse. Auto-download is off by default.
- Read the model contract from the file itself with onnxruntime (input name/shape/dtype, embedding size); preprocessing text must come from the code actually used and stay `preprocessing_verified: false` until the proxy evaluation shows which variant separates genuine from impostor pairs best.
- Always L2-normalise; cosine = dot product. Tests: norm 1 +/- 1e-3, self-similarity >= 0.999, deterministic.
- Thresholds: see skill face-policy. Accuracy figures only from labelled pairs; `pics` gives PROXY numbers only.
- Licence heads-up for OWNER_TODO (not a blocker): some popular face-model weight families are limited to non-commercial research; record the licence text path in the manifest.
