"""Tests for Phase P: Single face-threshold policy (Task P1).

Asserts:
- app/face_policy.py and ml_service/face_policy.py exist and are byte-identical.
- Constants BASE_SAME (0.60), AGED_PHOTO_YEARS (5.0), AGED_SAME (0.52), DIFF (0.40).
- effective_threshold returns AGED_SAME when photo_age_years >= 5.0, BASE_SAME otherwise.
- effective_threshold returns BASE_SAME when photo_age_years is None or invalid.
- Env override bounds checking: 0.30 <= AGED_SAME <= BASE_SAME <= 0.90.
- Out of bound env overrides fallback to default values with logged warning.
- Sliding formulas and get_age_aware_threshold removed from ml_service/face_match.py.
"""

from __future__ import annotations

import importlib
import logging
import os
import pathlib
import sys
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_face_policy_files_byte_identical():
    app_policy_path = REPO_ROOT / "app" / "face_policy.py"
    ml_policy_path = REPO_ROOT / "ml_service" / "face_policy.py"

    assert app_policy_path.exists(), "app/face_policy.py must exist"
    assert ml_policy_path.exists(), "ml_service/face_policy.py must exist"

    app_bytes = app_policy_path.read_bytes()
    ml_bytes = ml_policy_path.read_bytes()

    assert app_bytes == ml_bytes, "app/face_policy.py and ml_service/face_policy.py must be byte-identical"


def test_face_policy_constants_and_effective_threshold(monkeypatch):
    from app import face_policy

    assert face_policy.BASE_SAME == 0.60
    assert face_policy.AGED_PHOTO_YEARS == 5.0
    assert face_policy.AGED_SAME == 0.52
    assert face_policy.DIFF == 0.40

    # effective_threshold
    assert face_policy.effective_threshold(0.0) == face_policy.BASE_SAME
    assert face_policy.effective_threshold(2.5) == face_policy.BASE_SAME
    assert face_policy.effective_threshold(4.99) == face_policy.BASE_SAME
    assert face_policy.effective_threshold(5.0) == face_policy.AGED_SAME
    assert face_policy.effective_threshold(10.0) == face_policy.AGED_SAME
    assert face_policy.effective_threshold(None) == face_policy.BASE_SAME
    assert face_policy.effective_threshold(-1.0) == face_policy.BASE_SAME


def test_face_policy_env_overrides(monkeypatch):
    import app.face_policy as fp

    # Valid override
    monkeypatch.setenv("FACE_EMBED_SAME", "0.65")
    monkeypatch.setenv("FACE_EMBED_SAME_AGED", "0.55")
    base, aged = fp.resolve_policy_thresholds()
    assert base == 0.65
    assert aged == 0.55

    # Invalid override (AGED > BASE)
    monkeypatch.setenv("FACE_EMBED_SAME", "0.50")
    monkeypatch.setenv("FACE_EMBED_SAME_AGED", "0.60")
    base, aged = fp.resolve_policy_thresholds()
    assert base == 0.60
    assert aged == 0.52

    # Invalid override (out of 0.30 - 0.90 range)
    monkeypatch.setenv("FACE_EMBED_SAME", "0.95")
    monkeypatch.setenv("FACE_EMBED_SAME_AGED", "0.25")
    base, aged = fp.resolve_policy_thresholds()
    assert base == 0.60
    assert aged == 0.52


def test_policy_no_sliding_formulas_in_code():
    ml_fm_path = REPO_ROOT / "ml_service" / "face_match.py"
    content = ml_fm_path.read_text(encoding="utf-8")

    assert "get_age_aware_threshold" not in content, "get_age_aware_threshold must be removed"
    assert "0.015" not in content, "0.015/year sliding formula must be removed"


def test_cap_relaxed_threshold_never_auto_pass(monkeypatch):
    """P2: similarity 0.55 with an old photo -> REVIEW; 0.61 -> PASS; 0.55 with a young photo -> REVIEW."""
    import app.face as face_mod
    import app.face_match as app_fm

    monkeypatch.setattr(face_mod, "_document_face_b64", lambda *args, **kwargs: "dummy_doc_b64")

    # 1. Similarity 0.55 with old photo (e.g. issued 8 years ago)
    def mock_fm_old(*args, **kwargs):
        return {
            "score": 75,
            "match": True,
            "method": "onnx-embedding",
            "mode": "arcface",
            "decision": "MATCH",
            "age_adjusted": True,
            "threshold_used": 0.52,
            "detail": "Face-embedding cosine 0.55: same person.",
            "face_match": {
                "mode": "arcface",
                "similarity": 0.55,
                "threshold": 0.52,
                "decision": "MATCH",
            },
        }

    def _patch_fm(fn):
        monkeypatch.setattr(app_fm, "compare_faces", fn)
        if "face_match" in sys.modules:
            monkeypatch.setattr(sys.modules["face_match"], "compare_faces", fn)

    _patch_fm(mock_fm_old)
    res_old = face_mod.face_verification(
        document_bytes=b"dummy",
        live_frame=b"dummy_live",
        issue_date="2016-01-01",
    )
    assert res_old["verdict"] == "REVIEW"
    assert any("Aged-photo match at relaxed threshold — officer to confirm" in s for s in res_old.get("signals", []))

    # 2. Similarity 0.61 with any photo -> PASS
    def mock_fm_pass(*args, **kwargs):
        return {
            "score": 85,
            "match": True,
            "method": "onnx-embedding",
            "mode": "arcface",
            "decision": "MATCH",
            "age_adjusted": False,
            "threshold_used": 0.60,
            "detail": "Face-embedding cosine 0.61: same person.",
            "face_match": {
                "mode": "arcface",
                "similarity": 0.61,
                "threshold": 0.60,
                "decision": "MATCH",
            },
        }

    _patch_fm(mock_fm_pass)
    res_pass = face_mod.face_verification(
        document_bytes=b"dummy",
        live_frame=b"dummy_live",
        issue_date="2024-01-01",
    )
    assert res_pass["verdict"] == "PASS"

    # 3. Similarity 0.55 with young photo -> INCONCLUSIVE/REVIEW (never PASS)
    def mock_fm_young(*args, **kwargs):
        return {
            "score": 75,
            "match": None,
            "method": "onnx-embedding",
            "mode": "arcface",
            "decision": "INCONCLUSIVE",
            "age_adjusted": False,
            "threshold_used": 0.60,
            "detail": "Face-embedding cosine 0.55: inconclusive.",
            "face_match": {
                "mode": "arcface",
                "similarity": 0.55,
                "threshold": 0.60,
                "decision": "INCONCLUSIVE",
            },
        }

    _patch_fm(mock_fm_young)
    res_young = face_mod.face_verification(
        document_bytes=b"dummy",
        live_frame=b"dummy_live",
        issue_date="2024-01-01",
    )
    assert res_young["verdict"] == "REVIEW"

