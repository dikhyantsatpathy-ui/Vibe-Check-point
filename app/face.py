"""
Module 4 — Face Verification (SIH26188 "AI-Based Fake Identity & Document
Screening"). Closes "valid document, wrong person": compare the face in the
document against the holder's live capture.

The document-side face is a face ROI cropped from the document image (Module
3's zone boxes). The live capture is a webcam frame uploaded at the desk.
Matches the face_match.compare_faces contract: {score, match (True|False|None),
method, detail}. `match=None` means "inconclusive — confirm by eye"; the desk
never treats a low-signal comparison as a pass.
"""


def face_verification(document_bytes: bytes | None = None,
                      live_frame: bytes | None = None,
                      doc_type: str = "",
                      document_photo_b64: str | None = None,
                      dob: str | None = None,
                      issue_date: str | None = None) -> dict:
    """Run Module 4.

    Returns {score, match, method, detail, checks, signals}. doc_type is
    advisory — when a document portrait is present, a face ROI is cropped from
    the document image (or `document_photo_b64` is used directly when the
    pipeline already isolated the portrait, as with Aadhaar's Photo zone).
    Missing live frame / missing document face degrade to an honest
    inconclusive row rather than a guessed verdict.

    Feature 3 (age-aware thresholding): when the document photo is older than
    5 years (issue date when present, else DOB age as a bound proxy), the
    ArcFace cosine pass threshold drops 0.60 -> 0.52 so a legitimate aged
    document is not rejected on pixel drift alone. The adjustment is surfaced
    through `signals` ('Age Drift Compensation Active') so the desk — and the
    explainable reasons array — can see exactly why the threshold moved.
    """
    try:
        from app.face_match import compare_faces
    except ImportError:
        from face_match import compare_faces
    result = {
        "score": 0,
        "match": None,
        "method": "unavailable",
        "detail": "No live capture supplied — face verification skipped.",
        "checks": [
            {"label": "face-match", "ok": None,
             "detail": "No live frame was captured at the desk."},
        ],
        "verdict": "UNVERIFIED",
        "signals": [],
    }

    if live_frame is None:
        return result

    # Age-drift compensation: react to an aged document photo BEFORE matching.
    try:
        from app.face_policy import effective_threshold, AGED_PHOTO_YEARS, BASE_SAME
    except ImportError:
        from face_policy import effective_threshold, AGED_PHOTO_YEARS, BASE_SAME

    photo_age = _photo_age_years(dob, issue_date)
    signals = []
    emb_same = effective_threshold(photo_age)
    if photo_age is not None and photo_age >= AGED_PHOTO_YEARS:
        signals.append("Age Drift Compensation Active")
    result["signals"] = signals

    doc_face_b64 = document_photo_b64 or _document_face_b64(document_bytes)
    if doc_face_b64 is None:
        result["detail"] = "No document-side face found (no face ROI)."
        result["checks"][0]["detail"] = result["detail"]
        return result

    try:
        fm = compare_faces(doc_face_b64, live_frame, doc_age_years=photo_age, emb_same=emb_same)
    except Exception as exc:
        result["detail"] = f"Face comparison failed to run: {exc}"
        result["checks"][0]["detail"] = result["detail"]
        return result

    for k in ("score", "match", "method", "detail", "mode", "decision", "face_match"):
        if k in fm:
            result[k] = fm[k]

    # Invariant FS / A3: verdict="PASS" ONLY when decision == "MATCH" and mode == "arcface" and similarity >= BASE_SAME.
    # A match at a relaxed threshold (AGED_SAME <= similarity < BASE_SAME) becomes verdict="REVIEW".
    f_match_struct = fm.get("face_match") or {}
    f_mode = fm.get("mode") or f_match_struct.get("mode") or "fallback"
    f_dec = fm.get("decision") or f_match_struct.get("decision") or (
        "MATCH" if fm.get("match") is True else ("MISMATCH" if fm.get("match") is False else "INCONCLUSIVE")
    )
    sim = f_match_struct.get("similarity")

    if f_mode != "arcface":
        verdict = "REVIEW"
        result["decision"] = "INCONCLUSIVE"
        result["match"] = None
    elif f_dec == "MISMATCH" or fm.get("match") is False:
        verdict = "FAIL"
    elif f_dec == "MATCH":
        if sim is not None and sim < BASE_SAME:
            verdict = "REVIEW"
            rel_sig = "Aged-photo match at relaxed threshold — officer to confirm"
            if rel_sig not in signals:
                signals.append(rel_sig)
        else:
            verdict = "PASS"
    else:
        verdict = "REVIEW"

    checks = [{
        "label": "face-match",
        "ok": True if verdict == "PASS" else (False if verdict == "FAIL" else None),
        "detail": (f"Document portrait vs live capture "
                   f"({fm.get('method')}, score {fm.get('score')}): {fm.get('detail')}"),
    }]
    if signals:
        checks.append({"label": "age-drift", "ok": True,
                       "detail": (f"{'; '.join(signals)} (photo ~{photo_age:.1f}y old; "
                                  f"arcface threshold {BASE_SAME:.2f} -> {emb_same:.2f}).")})
    result["checks"] = checks
    result["signals"] = signals
    result["verdict"] = verdict
    return result


def _photo_age_years(dob: str | None, issue_date: str | None):
    """Approximate age of the document photo in years, or None when unknowable.

    An issue date is exact when present (the portrait is captured at issue
    time). DOB is used deliberately as a PROXY per the SIH26188 design: a birth
    date N years ago bounds how long the photo can have existed — if that bound
    already exceeds 5 years the photo is treated as aged. Unparseable dates
    degrade to None (never a guessed verdict).
    """
    from datetime import datetime
    today = datetime.now().date()
    d = _parse_date_value(issue_date) or _parse_date_value(dob)
    if d is None:
        return None
    try:
        return max(0.0, (today - d).days / 365.25)
    except Exception:
        return None


def _parse_date_value(s):
    """Parse common date layouts into a date, or None. Lenient: ISO, dmy with
    - / . separators, and 6-digit YYMMDD/DDMMYY (MRZ-style) like the desk."""
    if not isinstance(s, str):
        return None
    from datetime import datetime
    raw = (s or "").strip()
    if not raw:
        return None
    if len(raw) == 6 and raw.isdigit():
        yy = int(raw[:2])
        mm = int(raw[2:4])
        dd = int(raw[4:6])
        yyyy = 1900 + yy if yy > 50 else 2000 + yy
        raw = f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _document_face_b64(document_bytes):
    """Document-side face: crop the face ROI (if any) out of the document
    image. Returns base64 PNG or None."""
    if document_bytes is None:
        return None
    try:
        from forensics import roi_boxes
        boxes = roi_boxes(document_bytes)
        face = next((b for b in boxes if b.get("label") == "face"), None)
        if not face:
            return None
        import base64
        import io
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(document_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
        w, h = img.size
        x0 = int(face["x"] * w)
        y0 = int(face["y"] * h)
        x1 = int((face["x"] + face["w"]) * w)
        y1 = int((face["y"] + face["h"]) * h)
        crop = img.crop((max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)))
        out = io.BytesIO()
        crop.save(out, format="PNG")
        return base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return None