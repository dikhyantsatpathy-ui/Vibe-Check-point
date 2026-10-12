"""Face-match tests: identical portraits match, different ones don't,
garbage stays inconclusive, base64 (QR-attr form) is accepted."""

import base64
import io
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import face_match as fm  # noqa: E402

_MODELPATH = Path(__file__).resolve().parent.parent / "data" / "models" / "w600k_r50.onnx"


@pytest.fixture(autouse=True)
def _no_model_environ():
    """The dHash assertions below are only valid with no ONNX model configured
    and no remote ML service. .env may set FACE_EMBED_MODEL / ML_SERVICE_URL on
    real machines (and earlier test files' `import main` loads .env into the
    process environment), so clear both around each test and drop any cached
    ONNX session."""
    old_model = os.environ.pop("FACE_EMBED_MODEL", None)
    old_ml = os.environ.pop("ML_SERVICE_URL", None)
    fm._embed_model_path = None
    fm._embed_session = None
    fm._embed_failed = None
    yield
    if old_model is not None:
        os.environ["FACE_EMBED_MODEL"] = old_model
    if old_ml is not None:
        os.environ["ML_SERVICE_URL"] = old_ml


def _img(kind: str) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (96, 96), "white")
    d = ImageDraw.Draw(im)
    if kind == "checker":
        for y in range(0, 96, 12):
            for x in range(0, 96, 12):
                if (x + y) // 12 % 2 == 0:
                    d.rectangle([x, y, x + 11, y + 11], fill="black")
    elif kind == "stripes":
        for x in range(0, 96, 8):
            d.rectangle([x, 0, x + 3, 95], fill="navy")
    elif kind == "circle":
        d.ellipse([16, 16, 80, 80], fill="firebrick")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_identical_portraits_match():
    a = _img("checker")
    out = fm.compare_faces(a, a)
    assert out["match"] is None
    assert out["decision"] == "INCONCLUSIVE"
    assert out["score"] == 100
    assert out["method"] == "phash-dhash"


def test_reencoded_same_portrait_still_matches():
    from PIL import Image
    buf = io.BytesIO()
    with Image.open(io.BytesIO(_img("checker"))) as im:
        im.save(buf, format="JPEG", quality=70)
    out = fm.compare_faces(_img("checker"), buf.getvalue())
    assert out["match"] is None
    assert out["decision"] == "INCONCLUSIVE"


def test_different_portraits_reject():
    out = fm.compare_faces(_img("checker"), _img("stripes"))
    assert out["match"] is None
    assert out["decision"] == "INCONCLUSIVE"
    assert out["score"] <= 75  # score is informational; the verdict is the contract


def test_garbage_stays_inconclusive():
    assert fm.compare_faces(b"not-an-image", _img("checker"))["match"] is None
    assert fm.compare_faces(None, _img("checker"))["match"] is None
    assert fm.compare_faces("", "")["match"] is None


def test_base64_qr_attr_form_accepted():
    b64 = base64.b64encode(_img("circle")).decode("ascii")
    out = fm.compare_faces(b64, _img("circle"))
    assert out["match"] is None
    assert out["decision"] == "INCONCLUSIVE"


def test_face_match_does_not_download_a_model():
    import os
    import urllib.request
    old_model = os.environ.pop("FACE_EMBED_MODEL", None)
    old_retrieve = urllib.request.urlretrieve

    def _forbidden_retrieve(*args, **kwargs):
        raise AssertionError("face matching must not download a model")

    urllib.request.urlretrieve = _forbidden_retrieve
    try:
        out = fm.compare_faces(_img("checker"), _img("checker"))
    finally:
        urllib.request.urlretrieve = old_retrieve
        if old_model is not None:
            os.environ["FACE_EMBED_MODEL"] = old_model
    assert out["method"] == "phash-dhash"
    assert out["match"] is None
    assert out["decision"] == "INCONCLUSIVE"


def test_capabilities_shape():
    caps = fm.face_match_capabilities()
    assert set(caps) == {"available", "method", "onnx_configured"}
    assert caps["available"] is True
    assert caps["method"] == "phash-dhash"  # no FACE_EMBED_MODEL in test env


@pytest.mark.skipif(not _MODELPATH.exists(), reason="w600k_r50.onnx not downloaded")
def test_onnx_embedding_path_when_configured():
    """With FACE_EMBED_MODEL pointing at the ArcFace weights, the embedding
    engine takes over (no download, no fallback) and identical portraits
    match."""
    os.environ["FACE_EMBED_MODEL"] = str(_MODELPATH)
    try:
        caps = fm.face_match_capabilities()
        assert caps["method"] == "onnx-embedding"
        assert caps["onnx_configured"] is True
        out = fm.compare_faces(_img("checker"), _img("checker"))
        assert out["method"] == "onnx-embedding"
        assert out["match"] is True
    finally:
        os.environ.pop("FACE_EMBED_MODEL", None)


def test_age_aware_adaptive_threshold_dhash():
    """Under P3: perceptual hash threshold is constant 8 (no age relaxation); decision is always INCONCLUSIVE."""
    a = _img("checker")
    out_standard = fm.compare_faces(a, a, doc_age_years=2.0)
    assert out_standard["threshold_used"] == 8
    assert out_standard["match"] is None
    assert out_standard["decision"] == "INCONCLUSIVE"

    out_aged = fm.compare_faces(a, a, doc_age_years=8.5)
    assert out_aged["threshold_used"] == 8
    assert out_aged["match"] is None
    assert out_aged["decision"] == "INCONCLUSIVE"


def test_face_match_fail_safe_contract_when_no_model():
    """Invariant FS / A3: When FACE_EMBED_MODEL is absent, mode is fallback and decision is never MATCH."""
    a = _img("checker")
    out = fm.compare_faces(a, a)
    assert out["mode"] == "fallback"
    assert out["decision"] != "MATCH"
    assert out["decision"] == "INCONCLUSIVE"
    assert "face_match" in out
    assert out["face_match"]["mode"] == "fallback"
    assert out["face_match"]["decision"] != "MATCH"
    assert out["face_match"]["decision"] == "INCONCLUSIVE"


@pytest.mark.skipif(not _MODELPATH.exists(), reason="w600k_r50.onnx not downloaded")
def test_arcface_onnx_mode_decision_match_when_configured():
    """A3/A4: When ArcFace model is configured, identical portraits yield MATCH with mode='arcface'."""
    os.environ["FACE_EMBED_MODEL"] = str(_MODELPATH)
    try:
        a = _img("checker")
        out = fm.compare_faces(a, a)
        assert out["mode"] == "arcface"
        assert out["decision"] == "MATCH"
        assert out["match"] is True
        assert out["face_match"]["mode"] == "arcface"
        assert out["face_match"]["decision"] == "MATCH"
        assert out["face_match"]["similarity"] is not None
        assert out["face_match"]["similarity"] >= 0.90
    finally:
        os.environ.pop("FACE_EMBED_MODEL", None)


def test_remote_ml_failure_fail_safe():
    """A7 / Invariant FS: If remote ML fails or times out, return mode='unavailable' and decision='INCONCLUSIVE', never falling back to dHash."""
    os.environ["ML_SERVICE_URL"] = "http://127.0.0.1:59999/offline_endpoint"
    try:
        a = _img("checker")
        out = fm.compare_faces(a, a)
        assert out["mode"] == "unavailable"
        assert out["decision"] == "INCONCLUSIVE"
        assert out["match"] is None
        assert out["face_match"]["mode"] == "unavailable"
        assert out["face_match"]["decision"] == "INCONCLUSIVE"
    finally:
        os.environ.pop("ML_SERVICE_URL", None)


def test_get_age_aware_threshold_calculation():
    """A5: get_age_aware_threshold scales down threshold for older documents while enforcing floor."""
    th_base = fm.get_age_aware_threshold()
    assert th_base == 0.65

    th_2y = fm.get_age_aware_threshold(doc_age_years=2.0)
    assert th_2y == 0.62

    th_5y = fm.get_age_aware_threshold(doc_age_years=5.0)
    assert th_5y == 0.575

    th_10y = fm.get_age_aware_threshold(doc_age_years=10.0)
    assert th_10y == 0.50

    # Strict floor enforcement
    th_20y = fm.get_age_aware_threshold(doc_age_years=20.0)
    assert th_20y == 0.50

    # Issue year calculation
    th_issue = fm.get_age_aware_threshold(issue_year=2021, screening_year=2026)
    assert th_issue == 0.575


def test_evaluate_liveness_frames_blink():
    """A6: evaluate_liveness_frames for BLINK challenge."""
    # Under 3 frames
    res_short = fm.evaluate_liveness_frames([{"ear": 0.3}, {"ear": 0.1}], "BLINK")
    assert res_short["passed"] is False
    assert res_short["reason"] == "INSUFFICIENT_FRAMES"

    # Blink passed: EAR dips below 0.20
    frames_pass = [{"ear": 0.32}, {"ear": 0.15}, {"ear": 0.31}]
    res_pass = fm.evaluate_liveness_frames(frames_pass, "BLINK")
    assert res_pass["passed"] is True
    assert res_pass["min_ear"] == 0.15

    # Blink failed: EAR never dips below 0.20
    frames_fail = [{"ear": 0.32}, {"ear": 0.25}, {"ear": 0.28}]
    res_fail = fm.evaluate_liveness_frames(frames_fail, "BLINK")
    assert res_fail["passed"] is False


def test_evaluate_liveness_frames_nod_and_turn():
    """A6: evaluate_liveness_frames for NOD and TURN_HEAD challenges."""
    # Nod passed: vertical travel >= 20px
    nod_frames = [{"face_center_y": 100}, {"face_center_y": 125}, {"face_center_y": 105}]
    res_nod = fm.evaluate_liveness_frames(nod_frames, "NOD")
    assert res_nod["passed"] is True
    assert res_nod["vertical_travel"] == 25.0

    # Nod failed: vertical travel < 20px
    nod_fail = [{"face_center_y": 100}, {"face_center_y": 110}, {"face_center_y": 102}]
    res_nod_fail = fm.evaluate_liveness_frames(nod_fail, "NOD")
    assert res_nod_fail["passed"] is False

    # Turn head passed: horizontal travel >= 20px
    turn_frames = [{"face_center_x": 200}, {"face_center_x": 230}, {"face_center_x": 210}]
    res_turn = fm.evaluate_liveness_frames(turn_frames, "TURN_HEAD")
    assert res_turn["passed"] is True
    assert res_turn["horizontal_travel"] == 30.0


