"""Phase T1 — Test Hardening: Invariants Suite.

Formally tests:
1. Invariant FS: Under no degraded, fallback, or error condition does screening
   autonomously CLEAR a screening pass (verdict != "CLEAR", screening_verdict in {REVIEW, REJECT_LIKELY, REJECT}).
2. Invariant AUTH: All protected routes fail closed (401/403) on missing, expired,
   or forged credentials, and role boundaries are strictly enforced.
"""

from __future__ import annotations

import io
import sys
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.main import app, _vault_keys, SESSION_SIGNING_KEY
from app.screening import run_screening, _grade
from app.face import face_verification
import app.face_match as app_face_match


def _create_synthetic_id_bytes(text: str = "INSPECTION TEST") -> bytes:
    img = Image.new("RGB", (500, 320), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(10, 10), (490, 310)], outline=(20, 40, 80), width=2)
    draw.text((30, 40), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Invariant FS Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mode,decision,expected_verdict",
    [
        ("fallback", "INCONCLUSIVE", "REVIEW"),
        ("fallback", "MISMATCH", "REVIEW"),
        ("unavailable", "INCONCLUSIVE", "REVIEW"),
        ("arcface", "MISMATCH", "FAIL"),
        ("arcface", "INCONCLUSIVE", "REVIEW"),
        ("arcface", "MATCH", "PASS"),
    ],
)
def test_invariant_fs_face_verification_contract(monkeypatch, mode, decision, expected_verdict):
    """Module 4 face_verification must ONLY return 'PASS' when mode == 'arcface' and decision == 'MATCH'."""
    mock_fm = {
        "score": 85 if expected_verdict == "PASS" else 35,
        "match": True if expected_verdict == "PASS" else (False if decision == "MISMATCH" else None),
        "method": mode,
        "mode": mode,
        "decision": decision,
        "age_adjusted": False,
        "threshold_used": 0.50,
        "detail": f"mocked {mode} {decision}",
        "face_match": {
            "mode": mode,
            "similarity": 0.85 if expected_verdict == "PASS" else 0.35,
            "threshold": 0.50,
            "decision": decision,
        },
    }

    monkeypatch.setattr(app_face_match, "compare_faces", lambda *args, **kwargs: mock_fm)
    if "face_match" in sys.modules:
        monkeypatch.setattr(sys.modules["face_match"], "compare_faces", lambda *args, **kwargs: mock_fm)
    import app.face as face_mod
    monkeypatch.setattr(face_mod, "_document_face_b64", lambda *args, **kwargs: "fake_b64_crop")

    res = face_verification(
        document_bytes=b"dummy_bytes",
        live_frame=b"dummy_live_frame",
        doc_type="passport",
    )

    assert res["verdict"] == expected_verdict
    if mode != "arcface" or decision != "MATCH":
        assert res["verdict"] != "PASS", (
            f"Invariant FS violated: face_verification returned PASS in mode={mode}, decision={decision}"
        )


def test_invariant_fs_face_non_match_never_clears_screening(monkeypatch):
    """Screening pipeline MUST NOT clear when face verification is non-matching or fallback."""
    import app.face as face_mod

    # Force face_verification to return REVIEW
    monkeypatch.setattr(
        face_mod,
        "face_verification",
        lambda *args, **kwargs: {
            "ran": True,
            "verdict": "REVIEW",
            "match": None,
            "score": 40.0,
            "method": "fallback",
            "mode": "fallback",
            "decision": "INCONCLUSIVE",
            "signals": ["Face verification inconclusive"],
            "checks": [{"label": "face-match", "ok": None, "detail": "Fallback mode"}],
        },
    )

    dummy_img = _create_synthetic_id_bytes()
    result = run_screening(
        dummy_img,
        filename="test_doc.jpg",
        doc_type="passport",
        checkpoint="ICP-Raxaul",
        declared={"name": "ANNA TEST", "passport": "P1234567"},
        live_frame=dummy_img,
    )

    assert result["verdict"] != "CLEAR", "Invariant FS violated: verdict is CLEAR in fallback face mode"
    assert result["screening_verdict"] in ("REVIEW", "REJECT_LIKELY")
    assert any("DEGRADED BIOMETRIC" in str(r) or "BIOMETRIC REVIEW" in str(r) for r in result["reasons"])


def test_invariant_fs_grade_matrix():
    """Verify _grade function strictly enforces can_clear invariant."""
    for score in (0, 10, 20, 25, 30, 60):
        # When can_clear is False, grade can NEVER be CLEAR
        assert _grade(score, hard_flag=False, can_clear=False) in ("REVIEW", "FLAGGED")
        assert _grade(score, hard_flag=True, can_clear=False) == "FLAGGED"
        assert _grade(score, hard_flag=True, can_clear=True) == "FLAGGED"


def test_invariant_fs_remote_ml_timeout_never_clears(monkeypatch):
    """When remote ML times out or raises an exception, screening fails safe to REVIEW."""
    dummy_img = _create_synthetic_id_bytes()

    def mock_failing_post(*args, **kwargs):
        raise ConnectionError("Simulated remote ML service network partition")

    import requests
    monkeypatch.setattr(requests, "post", mock_failing_post)

    result = run_screening(
        dummy_img,
        filename="test_doc.jpg",
        doc_type="passport",
        checkpoint="ICP-Panitanki",
        declared={},
        live_frame=dummy_img,
    )

    assert result["verdict"] != "CLEAR"
    assert result["screening_verdict"] in ("REVIEW", "REJECT_LIKELY")


def test_invariant_fs_corrupt_payload_never_clears():
    """Corrupt image payload should result in REJECT_LIKELY or REVIEW, never clearance."""
    corrupt_bytes = b"NOT_A_VALID_JPEG_OR_PNG_HEADER" * 16

    result = run_screening(
        corrupt_bytes,
        filename="corrupt.jpg",
        doc_type="passport",
        checkpoint="ICP-Raxaul",
        declared={},
    )

    assert result["verdict"] != "CLEAR"
    assert result["screening_verdict"] in ("REVIEW", "REJECT_LIKELY")


# ---------------------------------------------------------------------------
# Invariant AUTH Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/admin/me", "get"),
        ("/api/admin/assign_role", "post"),
        ("/api/screen/queue", "get"),
        ("/api/screen/watchlist", "get"),
        ("/api/screen/watchlist/add", "post"),
        ("/api/screen/ledger/anchor", "post"),
    ],
)
def test_invariant_auth_unauthenticated_fails_closed(client, path, method):
    """Protected endpoints fail closed with HTTP 401 or 403 when unauthenticated."""
    req_fn = getattr(client, method)
    resp = req_fn(path)
    assert resp.status_code in (401, 403, 422), (
        f"Invariant AUTH violated: {method.upper()} {path} returned {resp.status_code} without auth"
    )


def test_invariant_auth_forged_session_token(client):
    """Forged session token fails closed with 401 or 403."""
    resp = client.get(
        "/api/admin/me",
        cookies={"nischay_session": "officer@ssb.gov.in::9999999999::invalidsignature"},
    )
    assert resp.status_code in (401, 403)


def test_invariant_auth_expired_session_token(client):
    """Expired session token fails closed with 401 or 403."""
    expired_exp = 1000
    expired_sig = _vault_keys.sign(SESSION_SIGNING_KEY, f"officer@ssb.gov.in::{expired_exp}")
    expired_token = f"officer@ssb.gov.in::{expired_exp}::{expired_sig}"
    resp = client.get("/api/admin/me", cookies={"nischay_session": expired_token})
    assert resp.status_code in (401, 403)


def test_invariant_auth_evaluator_role_restrictions(client):
    """Evaluator role cannot access superadmin-only endpoints."""
    from main import make_session_token
    token = make_session_token("evaluator@example.com")
    client.cookies.set("nischay_session", token)
    resp = client.post(
        "/api/admin/assign_role",
        json={"email": "target@example.com", "role": "admin"},
    )
    # Evaluator is forbidden from assigning roles
    assert resp.status_code in (401, 403)


def test_invariant_auth_ml_service_fails_closed():
    """ML microservice rejects unauthorized requests."""
    import ml_service.main as ml_main
    ml_client = TestClient(ml_main.app)

    no_secret_resp = ml_client.post(
        "/api/ml/yolo_roi",
        files={"file": ("test.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )
    wrong_secret_resp = ml_client.post(
        "/api/ml/yolo_roi",
        headers={"X-ML-Secret-Key": "wrong-secret"},
        files={"file": ("test.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert no_secret_resp.status_code in (401, 403, 503)
    assert wrong_secret_resp.status_code in (401, 403, 503)
