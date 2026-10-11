name: face-embedding
triggers: arcface, face, embedding, cosine, landmark, alignment, face_match, face_embed_model, biometric, selfie
- Goal: face matching must really run an embedding model, or say plainly that it did not.
- Inventory first: `Select-String -Path app,ml_service -Pattern "FACE_EMBED_MODEL|face_match|dhash"`, list every face `.onnx` on disk and on the HF model repo listing. Never invent a model name or URL.
- Read the model contract from the file itself: `onnxruntime.InferenceSession(...).get_inputs()/get_outputs()` (name, shape, dtype, embedding size). Read its README/model card for preprocessing. If unknown, determine the variant EMPIRICALLY (below) and record it in `face_embed.meta.json`.
- Empirical preprocessing check: for each candidate (RGB vs BGR, scale (x-127.5)/127.5 vs x/255, with/without 5-point alignment) compute genuine pairs (same pic + JPEG/blur/brightness/small rotation) vs impostor pairs (different pics). Pick the variant with the largest gap; log all variants.
- Always L2-normalise embeddings; cosine = dot product. Test: norm = 1 within 1e-3; self-similarity >= 0.999; deterministic across runs.
- Threshold from a target false-accept rate on impostor pairs; report n pairs; fewer than 1000 pairs = INDICATIVE ONLY. Same-person contamination of the impostor set must be reported, not hidden.
- Output contract (add fields only): `face_match: {mode: embedding|perceptual_hash|unavailable, similarity, threshold, decision: MATCH|MISMATCH|INCONCLUSIVE}`. Any mode other than `embedding` => INCONCLUSIVE, never MATCH, never lowers risk, routes to REVIEW (Invariant FS).
- Show the mode in `/ml/health` and in the screening response.
- Licence heads-up for OWNER_TODO (do not block): some popular face-model weight families are restricted to non-commercial research; read the licence on the model page you actually use and write the exact text path into the manifest.
