"""Single face-threshold policy (Phase P1 / SIH26188 Feature 3).

Establishes a single, canonical policy for ArcFace cosine similarity thresholds:
- BASE_SAME = 0.60 (standard match threshold)
- AGED_PHOTO_YEARS = 5.0 (age drift cutoff)
- AGED_SAME = 0.52 (relaxed threshold for photos older than 5 years)
- DIFF = 0.40 (clear non-match boundary)

Environment overrides:
- FACE_EMBED_SAME
- FACE_EMBED_SAME_AGED
Overrides are accepted ONLY if 0.30 <= AGED_SAME <= BASE_SAME <= 0.90.
Otherwise defaults are used and a warning is logged.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("face_policy")

BASE_SAME: float = 0.60
AGED_PHOTO_YEARS: float = 5.0
AGED_SAME: float = 0.52
DIFF: float = 0.40


def resolve_policy_thresholds() -> tuple[float, float]:
    """Resolve base and aged thresholds considering bounded environment overrides."""
    base = BASE_SAME
    aged = AGED_SAME

    raw_base = os.getenv("FACE_EMBED_SAME", "").strip()
    raw_aged = os.getenv("FACE_EMBED_SAME_AGED", "").strip()

    cand_base = base
    cand_aged = aged

    if raw_base:
        try:
            cand_base = float(raw_base)
        except ValueError:
            logger.warning("[face_policy] Invalid FACE_EMBED_SAME value: %r", raw_base)
    if raw_aged:
        try:
            cand_aged = float(raw_aged)
        except ValueError:
            logger.warning("[face_policy] Invalid FACE_EMBED_SAME_AGED value: %r", raw_aged)

    if 0.30 <= cand_aged <= cand_base <= 0.90:
        return cand_base, cand_aged

    logger.warning(
        "[face_policy] Overrides rejected: require 0.30 <= AGED_SAME (%.3f) <= BASE_SAME (%.3f) <= 0.90; reverting to defaults (%.2f, %.2f)",
        cand_aged, cand_base, BASE_SAME, AGED_SAME
    )
    return BASE_SAME, AGED_SAME


def effective_threshold(photo_age_years: float | int | None = None) -> float:
    """Return the effective cosine similarity pass threshold for a document portrait.

    If photo_age_years >= 5.0, returns AGED_SAME (0.52).
    Otherwise (or if photo_age_years is None or negative), returns BASE_SAME (0.60).
    """
    base, aged = resolve_policy_thresholds()
    if photo_age_years is not None and isinstance(photo_age_years, (int, float)):
        if photo_age_years >= AGED_PHOTO_YEARS:
            return aged
    return base
