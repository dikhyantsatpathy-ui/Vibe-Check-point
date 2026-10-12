name: face-policy
triggers: threshold, aged photo, age relax, face verdict, match decision, inconclusive, face_policy, similarity, face threshold
- One policy file (`face_policy.py`) in app/ and ml_service/, byte-identical copies, one step function `effective_threshold(photo_age_years)`.
- Defaults BASE_SAME 0.60, AGED_SAME 0.52 after 5 years, DIFF 0.40; env overrides only inside 0.30 <= AGED <= BASE <= 0.90.
- PASS needs mode arcface AND decision MATCH AND similarity >= BASE_SAME. A match that exists only because of the aged threshold is REVIEW.
- Any mode other than arcface: decision INCONCLUSIVE, verdict REVIEW, legacy `match` None, no age relaxation.
- No sliding formulas without an impostor-pair measurement; report possible same-person pairs separately.
