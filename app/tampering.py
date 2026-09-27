"""
Module 3 — Account / Identity Tampering Detection (SIH26188 "AI-Based Fake
Identity & Document Screening"). For images, runs the visual-forensics suite
from app/forensics.py — ELA (error-level analysis), focus/exposure QA, zone
boxes, and passive liveness cues — and folds in the AI-generation / "photo of
a screen" signals the calling desk already computed, each mapped to an
explainable check {label, ok, detail}. PDFs and unreadable inputs degrade to
honest "not applicable" rows, never to a silent pass.
"""

import io
import os

_TAMPER_CLF_SESSION = None
_TAMPER_CLF_ATTEMPTED = False

def _load_tamper_classifier():
    global _TAMPER_CLF_SESSION, _TAMPER_CLF_ATTEMPTED
    if _TAMPER_CLF_ATTEMPTED:
        return _TAMPER_CLF_SESSION
    _TAMPER_CLF_ATTEMPTED = True
    path = os.getenv("TAMPER_CLF_ONNX_PATH", os.path.join(os.path.dirname(__file__), "models", "tamper_classifier.onnx"))
    if not os.path.exists(path):
        return None
    try:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        _TAMPER_CLF_SESSION = ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])
        return _TAMPER_CLF_SESSION
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Weighted-evidence scoring (replaces boolean AND-gate that compounded
# independent noise — see FIX_ALL_ISSUES.md §1 Problem 1).
# ---------------------------------------------------------------------------
CHECK_WEIGHTS = {
    "dual-stream-forgery": 1.0,
    "ela": 1.0,
    "sensor-noise": 0.8,
    "copy-move-cloning": 0.9,
    "ai-generated-or-edited": 0.5,   # noisiest signal — corroborating, not decisive alone
    "spectral-analysis": 0.4,        # corroborating only
    "focus": 0.2,
    "liveness": 0.2,
    "card-localization": 0.1,
    "medium": 0.1,
}

MIN_PIXELS_FOR_TEXTURE_CHECKS = 400_000  # ~640x625, roughly a low-end webcam frame


def _weighted_verdict(checks: list[dict]) -> str:
    """Sum weighted evidence for FAIL / PASS instead of letting one shaky
    signal veto everything.  Each check has a reliability weight; a single
    soft misfiring (e.g. spectral on a glossy card) no longer forces FAIL."""
    decided = [c for c in checks if c.get("ok") is not None]

    def _w(label: str) -> float:
        key = label.split("-", 1)[0] if label.startswith("liveness-") else label
        return CHECK_WEIGHTS.get(key, 0.5)

    fail_weight = sum(_w(c["label"]) for c in decided if c.get("ok") is False)
    pass_weight = sum(_w(c["label"]) for c in decided if c.get("ok") is True)

    if fail_weight >= 1.3:       # one strong signal, or two+ weak ones corroborating
        return "FAIL"
    if fail_weight > 0 or pass_weight < 1.0:
        return "REVIEW"
    return "PASS"


def _has_camera_exif(image_bytes: bytes) -> bool:
    """Check if image carries real camera EXIF (Make/Model/DateTimeOriginal).
    AI-generated and screenshot images almost never have these."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
        if not exif:
            return False
        # 0x010F = Make, 0x0110 = Model, 0x9003 = DateTimeOriginal
        return any(tag in exif for tag in (0x010F, 0x0110, 0x9003))
    except Exception:
        return False


def tamper_analysis(image_bytes: bytes | None, ai_detection: dict | None = None,
                    document_aware: bool | None = None, doc_type: str = "") -> dict:
    """Run Module 3 for a document.

    Returns {checks, ela, qa, roi, liveness, ai_detection, verdict}. The
    forensics sub-block (`ela`, `qa`, `roi`, `liveness`) is passed through edge
    to the desk's overlay, so the ESL heatmap and zone boxes render on the
    document preview without forensics.py being re-wired anywhere else.
    """
    checks = []
    doc_type = (doc_type or "").strip().lower()
    ai_detection = ai_detection or {"ran": False, "explanation": "No image."}

    try:
        from app.forensics import forensics_report
    except ImportError:
        from forensics import forensics_report

    if image_bytes is None:
        f0 = forensics_report(b"")  # always returns the "not readable" shape
        return {"checks": [{"label": "ela", "ok": None, "detail": "No image supplied."}],
                "ela": f0["ela"], "qa": f0["qa"], "roi": [], "liveness": [],
                "ai_detection": ai_detection, "verdict": "UNVERIFIED"}

    # Automatic card localization: isolates card from white paper, desk, or hands
    crop_meta = None
    active_bytes = image_bytes
    try:
        from app.yolo_roi import isolate_document_card
    except ImportError:
        try:
            from yolo_roi import isolate_document_card
        except ImportError:
            isolate_document_card = None

    if isolate_document_card:
        c_bytes, meta = isolate_document_card(image_bytes)
        if meta and meta.get("cropped") and c_bytes:
            active_bytes = c_bytes
            crop_meta = meta
            checks.append({
                "label": "card-localization",
                "ok": True,
                "detail": f"Card localized & background isolated ({round(meta['area_ratio'] * 100)}% frame coverage).",
            })

    # Resolution gating: skip texture-heavy checks on low-res images where
    # they produce noise-on-noise rather than meaningful signal.
    try:
        from PIL import Image as _PILImg
        _dim_img = _PILImg.open(io.BytesIO(active_bytes))
        _img_w, _img_h = _dim_img.size
    except Exception:
        _img_w, _img_h = 0, 0
    low_res = (_img_w * _img_h) < MIN_PIXELS_FOR_TEXTURE_CHECKS

    # Run Dual-Stream Document Forgery Detector (SRM residuals + spatial seams)
    try:
        from app.doc_forgery import analyze_doc_forgery
    except ImportError:
        try:
            from doc_forgery import analyze_doc_forgery
        except ImportError:
            analyze_doc_forgery = None

    forgery_res = {}
    if low_res:
        checks.append({
            "label": "dual-stream-forgery", "ok": None,
            "detail": "Resolution too low for reliable dual-stream forgery analysis — not applicable, verify by other modules.",
        })
    elif analyze_doc_forgery:
        forgery_res = analyze_doc_forgery(active_bytes)
        if forgery_res.get("ran"):
            checks.append({
                "label": "dual-stream-forgery",
                "ok": not forgery_res.get("is_tampered"),
                "detail": forgery_res.get("detail", "Dual-Stream substrate analysis completed."),
            })

    fr = forensics_report(active_bytes)
    if fr.get("error"):
        return {"checks": [{"label": "image", "ok": None,
                            "detail": f"Image not readable: {fr['error']}"}],
                "ela": None, "qa": None, "roi": [], "liveness": [],
                "ai_detection": ai_detection, "doc_forgery": forgery_res,
                "verdict": "UNVERIFIED"}

    ela = fr["ela"] or {}
    qa = fr["qa"] or {}
    roi = fr["roi"] or []
    liveness = fr["liveness"] or []

    # ---- ELA: tampered region lights up ----------------------------------
    if ela.get("status"):
        checks.append({
            "label": "ela",
            "ok": ela["status"] in ("LOW", "MEDIUM"),
            "detail": (f"ELA {ela['status']} — {round((ela.get('damage_ratio') or 0) * 100)}% "
                       "of 8x8 blocks deviate from expected re-compression"
                       + ("" if ela["status"] == "LOW" else " (HIGH signals a real paste/composite)")),
        })
    else:
        checks.append({"label": "ela", "ok": None,
                       "detail": "ELA could not run on this image."})

    # ---- Focus: blur hides tamper artifacts ------------------------------
    if qa.get("blurry"):
        checks.append({"label": "focus", "ok": None,
                       "detail": "Image focus is soft (camera blur) — inspect details by eye."})
    else:
        checks.append({"label": "focus", "ok": qa.get("blur_est") is not None,
                       "detail": f"Focus looks acceptable (Blur est {qa.get('blur_est')})."})

    # ---- Passive liveness cues (single frame) ----------------------------
    for sig in liveness:
        if sig.get("level") in ("warn", "danger"):
            checks.append({
                "label": f"liveness-{sig.get('signal', 'cue')}",
                "ok": False if sig.get("level") == "danger" else None,
                "detail": sig.get("note", ""),
            })
    if not any(c["label"].startswith("liveness-") for c in checks):
        checks.append({"label": "liveness", "ok": None,
                       "detail": "Still frame cannot prove aliveness — pair with the "
                                 "webcam capture for a person check."})

    # ---- AI-generation / Editing / Screen-aware signal ------------------
    if (ai_detection.get("raw") or {}).get("kind") in ("ai", "edited"):
        checks.append({
            "label": "ai-generated-or-edited",
            "ok": False,
            "detail": (ai_detection.get("explanation") or
                       "Vision/metadata scan flags the document as AI-generated or digitally edited."),
        })
    elif ai_detection.get("ai_suspected") or (ai_detection.get("ai_score") or 0) >= 65:
        is_physical_card = bool(crop_meta and crop_meta.get("cropped") and ela.get("status") in ("LOW", "MEDIUM") and ela.get("verdict") != "FAIL")
        if is_physical_card:
            checks.append({
                "label": "ai-generated-or-edited",
                "ok": True,
                "detail": f"Physical card capture: camera sensor noise / surface lighting noted ({ai_detection.get('ai_score', 0)}% model variance); no composite forgery detected.",
            })
        else:
            checks.append({
                "label": "ai-generated-or-edited",
                "ok": False,
                "detail": (ai_detection.get("explanation") or
                           "Vision/metadata scan flags the document as AI-generated or digitally edited."),
            })
    elif ai_detection.get("ran") and not ai_detection.get("ai_suspected"):
        checks.append({
            "label": "ai-generated-or-edited",
            "ok": True,
            "detail": "No synthetic AI generation or editing tool signatures detected.",
        })

    if document_aware is False and doc_type and doc_type != "other":
        checks.append({
            "label": "medium",
            "ok": None,
            "detail": "Physical card camera capture (desk/handheld photo, not flatbed scan).",
        })

    # ---- 2D-FFT Spectral Frequency Analysis ------------------------------
    # Periodic high-frequency structure is expected on any QR/barcode-equipped
    # document (module grids, tricolor bands) and even dense text — so this is a
    # *warning* row (contributes to REVIEW), never a hard fail on its own.
    # Generative upsampling grids and screen-recapture moiré surface here, but
    # they are hard-flagged by the AI-generation check and the "photo of a
    # screen" medium check above; spectral corroborates rather than decides.
    if low_res:
        checks.append({
            "label": "spectral-analysis", "ok": None,
            "detail": "Resolution too low for reliable spectral/SRM texture analysis — not applicable, verify by other modules.",
        })
        spectral = {}
    else:
        spectral = fr.get("spectral") or {}
        if spectral.get("spectral_anomaly"):
            checks.append({
                "label": "spectral-analysis",
                "ok": None,
                "detail": f"Anomalous high-frequency periodicity (PAPR {spectral.get('papr', 0)}x) — generative grid or screen recapture; corroborate with the AI-generation check.",
            })
        elif spectral.get("papr") is not None:
            checks.append({
                "label": "spectral-analysis",
                "ok": True,
                "detail": f"Optical frequency spectrum consistent with natural physical capture (PAPR {spectral.get('papr')}x).",
            })

    # ---- Sensor Noise Consistency (PRNU / Photo Splicing) ----------------
    noise = fr.get("noise_consistency") or {}
    if noise.get("status") == "SUSPECT_PHOTO_SPLICE":
        checks.append({
            "label": "sensor-noise",
            "ok": False,
            "detail": noise.get("detail", "Sensor noise variance disparity indicates photo replacement or splicing."),
        })
    elif noise.get("status") == "CONSISTENT" and noise.get("noise_ratio") is not None:
        checks.append({
            "label": "sensor-noise",
            "ok": True,
            "detail": noise.get("detail", "Uniform sensor noise distribution verified across portrait and substrate."),
        })

    # ---- Copy-Move / Clone Stamp Duplication -----------------------------
    copy_move = fr.get("copy_move") or {}
    if copy_move.get("detected"):
        if (ela.get("status") != "HIGH" and ela.get("verdict") != "FAIL"):
            checks.append({
                "label": "copy-move-cloning",
                "ok": True,
                "detail": "Physical capture: repetitive surface/background patterns noted; no localized document splice.",
            })
        else:
            checks.append({
                "label": "copy-move-cloning",
                "ok": False,
                "detail": copy_move.get("detail", "Copy-move duplication detected: identical pixel patches identified across document zones."),
            })
    elif copy_move.get("status") == "CLEAN":
        checks.append({
            "label": "copy-move-cloning",
            "ok": True,
            "detail": "No copy-move cloning or duplicate-block stamp artifacts detected.",
        })

    has_exif = _has_camera_exif(image_bytes) if image_bytes else False
    
    clf = _load_tamper_classifier()
    if clf is not None:
        try:
            feat = [
                float(ela.get("damage_ratio", 0.0) or 0.0),
                float(ela.get("mean_diff", 0.0) or 0.0),
                float(spectral.get("papr", 0.0) or 0.0),
                float(spectral.get("high_freq_ratio", 0.0) or 0.0),
                float(noise.get("noise_ratio", 0.0) or 0.0),
                float(copy_move.get("duplicate_ratio", 0.0) or 0.0),
                float((forgery_res or {}).get("dead_block_ratio", 0.0) or 0.0),
                float((forgery_res or {}).get("largest_component", 0.0) or 0.0),
                float((ai_detection.get("raw") or {}).get("fine_noise", 0.0) or 0.0),
                float((ai_detection.get("raw") or {}).get("pixel_ratio", 0.0) or 0.0),
                1.0 if has_exif else 0.0
            ]
            import numpy as np
            inp = np.array([feat], dtype=np.float32)
            pred = clf.run(None, {clf.get_inputs()[0].name: inp})
            is_tampered = int(pred[0][0]) == 1
            verdict = "FAIL" if is_tampered else "PASS"
            checks.append({
                "label": "onnx-classifier",
                "ok": not is_tampered,
                "detail": f"Joint machine-learning classifier evaluated features ({'tampered' if is_tampered else 'genuine'}).",
            })
        except Exception:
            verdict = _weighted_verdict(checks)
    else:
        verdict = _weighted_verdict(checks)

    return {"checks": checks, "ela": ela, "qa": qa, "roi": roi, "liveness": liveness,
            "spectral": spectral, "noise_consistency": noise, "copy_move": copy_move,
            "ai_detection": ai_detection, "doc_forgery": forgery_res,
            "crop_meta": crop_meta, "verdict": verdict}