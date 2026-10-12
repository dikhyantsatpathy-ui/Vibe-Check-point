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


def test_fallback_methods_never_decide(monkeypatch):
    """P3: For any mode other than arcface (phash-dhash, unavailable):
    - decision is INCONCLUSIVE always;
    - verdict is REVIEW always;
    - legacy field match is None always;
    - perceptual-hash threshold is constant (no age relaxation).
    """
    import app.face as face_mod
    import app.face_match as app_fm
    from PIL import Image
    import io

    monkeypatch.setattr(face_mod, "_document_face_b64", lambda *args, **kwargs: "dummy_doc_b64")

    # Create two images
    img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img2 = Image.new("RGB", (100, 100), color=(0, 255, 0))
    buf1 = io.BytesIO(); img1.save(buf1, format="PNG"); b1 = buf1.getvalue()
    buf2 = io.BytesIO(); img2.save(buf2, format="PNG"); b2 = buf2.getvalue()

    # Disable onnx embedding to force fallback
    monkeypatch.setattr(app_fm, "_embed_image", lambda img: None)

    out_diff = app_fm.compare_faces(b1, b2, doc_age_years=10.0)
    assert out_diff["mode"] == "fallback"
    assert out_diff["decision"] == "INCONCLUSIVE"
    assert out_diff["match"] is None
    assert out_diff["threshold_used"] == 8

    out_same = app_fm.compare_faces(b1, b1, doc_age_years=10.0)
    assert out_same["mode"] == "fallback"
    assert out_same["decision"] == "INCONCLUSIVE"
    assert out_same["match"] is None
    assert out_same["threshold_used"] == 8

    # Test face_verification verdict in fallback mode
    res = face_mod.face_verification(
        document_bytes=b"dummy",
        live_frame=b1,
        doc_type="passport",
    )
    assert res["verdict"] == "REVIEW"
    assert res["decision"] == "INCONCLUSIVE"
    assert res["match"] is None


def test_face_model_provisioning_manifest_structure():
    """P4: MODEL_MANIFEST.json contains per model: name, sha256, bytes, source_repo, revision, origin_hint.
    Face model sha256 matches DEFAULT_FACE_SHA256 constant, origin_hint has URL and licence heads-up.
    """
    import json
    import ml_service.face_match as ml_fm
    from ml_service.model_fetch import load_manifest, MANIFEST_PATH

    assert MANIFEST_PATH.exists(), f"Manifest file {MANIFEST_PATH} must exist"
    manifest = load_manifest()
    assert "w600k_r50.onnx" in manifest, "Manifest must contain w600k_r50.onnx"

    for name, entry in manifest.items():
        assert "name" in entry and entry["name"] == name
        assert "sha256" in entry and len(entry["sha256"]) == 64
        assert "bytes" in entry and isinstance(entry["bytes"], int) and entry["bytes"] > 0
        assert "source_repo" in entry and entry["source_repo"]
        assert "revision" in entry and entry["revision"]
        assert "origin_hint" in entry and isinstance(entry["origin_hint"], str)

    face_entry = manifest["w600k_r50.onnx"]
    assert face_entry["sha256"].lower() == ml_fm.DEFAULT_FACE_SHA256.lower()
    assert "maze/faceX" in face_entry["origin_hint"]
    assert "licence" in face_entry["origin_hint"].lower() or "license" in face_entry["origin_hint"].lower()


def test_face_model_provisioning_zero_calls_when_auto_download_off(monkeypatch, tmp_path):
    """P4: When AUTO_DOWNLOAD_MODELS is off, zero network calls may happen, and missing model yields mode unavailable."""
    import ml_service.face_match as ml_fm
    from PIL import Image
    import io

    # Ensure auto-download is off
    monkeypatch.delenv("AUTO_DOWNLOAD_MODELS", raising=False)
    monkeypatch.setenv("FACE_EMBED_MODEL", str(tmp_path / "nonexistent.onnx"))

    # Ensure local models dir in face_match doesn't find w600k_r50.onnx
    monkeypatch.setattr(
        ml_fm,
        "_resolve_face_model_path",
        lambda: None
    )

    network_called = []

    def fake_download(*args, **kwargs):
        network_called.append("hf_hub_download")
        raise RuntimeError("Network should not be called!")

    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)

    # Real call to _resolve_face_model_path with monkeypatched env
    monkeypatch.undo()  # restore real _resolve_face_model_path
    monkeypatch.setenv("AUTO_DOWNLOAD_MODELS", "false")
    monkeypatch.setenv("FACE_EMBED_MODEL", str(tmp_path / "nonexistent.onnx"))
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)

    resolved = ml_fm._resolve_face_model_path()
    assert resolved is None, "Should not resolve when local files absent and auto_download is false"
    assert len(network_called) == 0, f"Zero network calls expected when flag is off, got: {network_called}"

    # Missing face model in compare_faces yields unavailable
    img = Image.new("RGB", (64, 64), color="blue")
    buf = io.BytesIO(); img.save(buf, format="PNG"); b_img = buf.getvalue()
    res = ml_fm.compare_faces(b_img, b_img)
    assert res["mode"] == "unavailable"
    assert res["decision"] == "INCONCLUSIVE"
    assert res["match"] is None


def test_face_model_provisioning_mismatching_sha_refuses(monkeypatch, tmp_path):
    """P4: Mismatching SHA refuses to load face model."""
    import ml_service.face_match as ml_fm

    corrupt_model = tmp_path / "corrupt_model.onnx"
    corrupt_model.write_bytes(b"corrupt model data with invalid checksum")

    monkeypatch.setenv("FACE_EMBED_MODEL", str(corrupt_model))
    monkeypatch.setenv("FACE_MODEL_SHA256", ml_fm.DEFAULT_FACE_SHA256)
    monkeypatch.setenv("AUTO_DOWNLOAD_MODELS", "false")

    resolved = ml_fm._resolve_face_model_path()
    assert resolved is None, "Model with mismatching SHA must refuse to load"


def test_face_model_provisioning_empty_sha_refuses(monkeypatch, tmp_path):
    """P4: Empty or missing SHA refuses to load; empty override uses manifest value."""
    import hashlib
    import ml_service.face_match as ml_fm
    import ml_service.model_fetch as model_fetch

    fake_model = tmp_path / "fake_model.onnx"
    fake_bytes = b"real onnx bytes for testing empty sha logic"
    fake_model.write_bytes(fake_bytes)
    correct_sha = hashlib.sha256(fake_bytes).hexdigest()

    monkeypatch.setenv("FACE_EMBED_MODEL", str(fake_model))
    monkeypatch.setenv("AUTO_DOWNLOAD_MODELS", "false")

    # 1. Override is empty string -> uses manifest value.
    # When manifest has matching SHA, it loads!
    monkeypatch.setattr(
        model_fetch,
        "get_manifest_entry",
        lambda name: {"name": "w600k_r50.onnx", "sha256": correct_sha}
    )
    monkeypatch.setenv("FACE_MODEL_SHA256", "")
    assert ml_fm._resolve_face_model_path() == str(fake_model)

    # 2. Both env and manifest are empty -> refuses to load!
    monkeypatch.setattr(
        model_fetch,
        "get_manifest_entry",
        lambda name: {"name": "w600k_r50.onnx", "sha256": ""}
    )
    monkeypatch.setattr(ml_fm, "DEFAULT_FACE_SHA256", "")
    monkeypatch.setenv("FACE_MODEL_SHA256", "")
    assert ml_fm._resolve_face_model_path() is None, "Empty SHA must refuse to load"

    monkeypatch.setenv("FACE_MODEL_SHA256", "   ")
    assert ml_fm._resolve_face_model_path() is None, "Whitespace SHA must refuse to load"


def test_face_model_provisioning_oversize_refuses(monkeypatch, tmp_path):
    """P4: Size cap of 1.05 x manifest bytes enforced on any fetch; oversize unlinks and fails."""
    from ml_service.model_fetch import fetch_models_from_hf
    import ml_service.model_fetch as model_fetch

    # Manifest with 1000 bytes. Max allowed: 1050 bytes.
    manifest_stub = {
        "oversize_model.onnx": {
            "name": "oversize_model.onnx",
            "bytes": 1000,
            "sha256": "dummy_sha",
        }
    }
    monkeypatch.setattr(model_fetch, "load_manifest", lambda *args: manifest_stub)
    monkeypatch.setattr(model_fetch, "get_manifest_entry", lambda name, *args: manifest_stub.get(name))

    def fake_oversize_download(repo_id, filename, token, local_dir, **kwargs):
        out_file = Path(local_dir) / filename
        out_file.write_bytes(b"x" * 1200)  # 1200 bytes > 1050 bytes
        return str(out_file)

    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_oversize_download)

    res = fetch_models_from_hf(
        repo_id="test/repo",
        dest_dir=tmp_path,
        model_filenames=["oversize_model.onnx"],
        max_retries=1,
    )

    assert res.get("oversize_model.onnx") is False, "Oversize download must fail"
    assert not (tmp_path / "oversize_model.onnx").exists(), "Oversize file must be unlinked"


def test_face_health_metadata_sidecar():
    """P5: ml_service/models/face_embed.meta.json generated from real ONNX when present.
    Contains input name/shape, output size, SHA-256, bytes, preprocessing text, preprocessing_verified: false.
    """
    import json
    meta_path = REPO_ROOT / "ml_service" / "models" / "face_embed.meta.json"
    assert meta_path.exists(), "ml_service/models/face_embed.meta.json must exist"

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["model_name"] == "w600k_r50.onnx"
    assert "input_name" in meta and meta["input_name"] == "input.1"
    assert "input_shape" in meta and list(meta["input_shape"]) == [1, 3, 112, 112]
    assert "output_size" in meta and meta["output_size"] == 512
    assert "sha256" in meta and len(meta["sha256"]) == 64
    assert "bytes" in meta and meta["bytes"] == 174383860
    assert "preprocessing" in meta and "127.5" in meta["preprocessing"] and "128.0" in meta["preprocessing"]
    assert meta["preprocessing_verified"] is False


def test_ml_health_endpoint():
    """P5: /ml/health and /health show face_match.mode, loaded, model_sha256_prefix, auto_download."""
    from fastapi.testclient import TestClient
    from ml_service.main import app as ml_app

    client = TestClient(ml_app)
    for endpoint in ("/ml/health", "/health"):
        res = client.get(endpoint)
        assert res.status_code == 200
        body = res.json()
        assert body.get("status") in ("ok", "online", "degraded")
        fm = body.get("face_match")
        assert isinstance(fm, dict), f"face_match must be a dict in {endpoint}"
        assert "mode" in fm and fm["mode"] in ("arcface", "unavailable", "fallback")
        assert "loaded" in fm and isinstance(fm["loaded"], bool)
        assert "model_sha256_prefix" in fm
        if fm["loaded"]:
            assert isinstance(fm["model_sha256_prefix"], str)
            assert len(fm["model_sha256_prefix"]) == 12
        else:
            assert fm["model_sha256_prefix"] is None
        assert "auto_download" in fm and isinstance(fm["auto_download"], bool)


def test_screening_response_face_match_health_fields(monkeypatch):
    """P5: Screening response shows face_match.mode, loaded, model_sha256_prefix, auto_download."""
    import io
    from PIL import Image
    import screening

    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    # Run screening with image
    report = screening.run_screening(
        data=data,
        filename="test.png",
        doc_type="passport",
        checkpoint="Raxaul",
        declared={},
    )

    # Check top-level face_match
    assert "face_match" in report, "Screening report must contain top-level face_match"
    fm_top = report["face_match"]
    assert "mode" in fm_top
    assert "loaded" in fm_top and isinstance(fm_top["loaded"], bool)
    assert "model_sha256_prefix" in fm_top
    assert "auto_download" in fm_top and isinstance(fm_top["auto_download"], bool)

    # Check modules.face.face_match
    face_module = report.get("modules", {}).get("face", {})
    assert "face_match" in face_module, "Screening report modules.face must contain face_match"
    fm_mod = face_module["face_match"]
    assert "mode" in fm_mod
    assert "loaded" in fm_mod and isinstance(fm_mod["loaded"], bool)
    assert "model_sha256_prefix" in fm_mod
    assert "auto_download" in fm_mod and isinstance(fm_mod["auto_download"], bool)


def test_liveness_docstring_server_side_warning():
    """P6: evaluate_liveness_frames docstring warns that inputs must be server-side."""
    import app.face_match as app_fm
    import ml_service.face_match as ml_fm

    for mod, name in ((app_fm, "app.face_match"), (ml_fm, "ml_service.face_match")):
        doc = getattr(mod, "evaluate_liveness_frames").__doc__ or ""
        assert "server-side" in doc.lower(), f"{name}.evaluate_liveness_frames docstring must warn about server-side computation"
        assert "not integrated" in doc.lower(), f"{name}.evaluate_liveness_frames docstring must state not integrated"


def test_liveness_not_routed_in_apps():
    """P6: No route in app/main.py or ml_service/main.py references evaluate_liveness_frames."""
    app_main_path = REPO_ROOT / "app" / "main.py"
    ml_main_path = REPO_ROOT / "ml_service" / "main.py"

    assert app_main_path.exists()
    assert ml_main_path.exists()

    app_main_code = app_main_path.read_text(encoding="utf-8")
    ml_main_code = ml_main_path.read_text(encoding="utf-8")

    assert "evaluate_liveness_frames" not in app_main_code, "app/main.py must not reference evaluate_liveness_frames"
    assert "evaluate_liveness_frames" not in ml_main_code, "ml_service/main.py must not reference evaluate_liveness_frames"

    # Also inspect actual registered routes on the FastAPI app instances
    import app.main as main_mod
    from ml_service.main import app as ml_fastapi_app

    for route in main_mod.app.routes:
        endpoint = getattr(route, "endpoint", None)
        endpoint_name = getattr(endpoint, "__name__", "")
        assert endpoint_name != "evaluate_liveness_frames"
        assert getattr(endpoint, "__wrapped__", endpoint) != "evaluate_liveness_frames"

    for route in ml_fastapi_app.routes:
        endpoint = getattr(route, "endpoint", None)
        endpoint_name = getattr(endpoint, "__name__", "")
        assert endpoint_name != "evaluate_liveness_frames"
        assert getattr(endpoint, "__wrapped__", endpoint) != "evaluate_liveness_frames"


def test_liveness_blueprint_wording():
    """P6: Blueprint notes that evaluate_liveness_frames is not integrated."""
    blueprint_path = REPO_ROOT / "SIH26188_ENGINEERING_BLUEPRINT.md"
    assert blueprint_path.exists()
    content = blueprint_path.read_text(encoding="utf-8")
    assert "evaluate_liveness_frames" in content
    # Wording requires 'not integrated'
    assert "not integrated" in content





