"""
Module 1 — OCR Extraction (SIH26188 "AI-Based Fake Identity & Document
Screening"). One uploaded document -> machine-readable fields:

  pdf   -> pypdf text layer -> extract_fields (identifier regexes + MRZ)
  image -> tesseract OCR (best-effort) + MRZ parse

Everything else joins here too: the officer's typed `declared` map merged over
the scan (declared never overrides machine-read values; it back-fills gaps so
officer typos cannot silently shadow verified fields).

Output is the same zero-storage shape as the rest of the desk: raw text and
photos are read, used, and discarded — only masked identifiers and checksums
move on to Module 2.
"""

import re

# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

# Declared keys are keyed by purpose, not by free text. Generic keys always
# belong to the selected document type; unrelated typed keys (for example, an
# EPIC key supplied during passport screening) are ignored so one form cannot
# populate another document's identifier field.
_TARGET_FIELD_FOR = {
    "passport": "passport",
    "visa": "passport",
    "pan": "pan",
    "driving_licence": "driving_licence",
    "voter_id": "voter_id",
    "rc": "driving_licence",
    "nepali_citizenship": "citizenship_number",
    "bhutan_citizenship": "citizenship_number",
}
_GENERIC_DECL_KEYS = {"document_number", "doc_number", "number", "id", "declared"}


def extract_document(data: bytes, filename: str = "", doc_type: str = "",
                     declared: dict = None) -> dict:
    """Run the extraction pass over one document.

    Returns a dict the screening desk merges into its report:
      medium     "pdf" | "image" | "unknown"
      fields     normalized identifier fields {pan, dl, passport, ...}
      mrz        parsed MRZ block (passport / visa) or None
      ocr        {ran, engine, reason} metadata
      pdf_no_text made this pass for image-only PDFs
      ai_detection / document_aware: filled by run_screening when the caller
                 already computed them (they live in app/main.py); not rerun here.
    """
    declared = {k: v for k, v in (declared or {}).items()
                if isinstance(v, str) and v.strip()}
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if not ext or ext not in ("pdf", "jpg", "jpeg", "png", "webp", "bmp", "tiff", "heic"):
        if data and data.startswith(b"%PDF"):
            ext = "pdf"
        else:
            ext = "jpg"

    try:
        from app.screening import extract_fields
    except ImportError:
        from screening import extract_fields

    result = {
        "medium": "unknown",
        "fields": {},
        "mrz": None,
        "ocr": {"ran": False, "reason": "no image"},
        "pdf_no_text": False,
        "ai_detection": {"ran": False, "explanation": "No image."},
        "document_aware": None,
    }

    if ext == "pdf":
        result["medium"] = "pdf"
        text, img_bytes = _pdf_text_or_image(data)
        if text:
            result["text"] = text
            result["fields"] = extract_fields(text, doc_type=doc_type)
            result["ocr"] = {"ran": True, "engine": "pdf-text-layer", "reason": "Digital PDF text stream"}
        elif img_bytes:
            img_res = _extract_image(img_bytes, doc_type=doc_type)
            result["fields"] = img_res.get("fields", {})
            result["mrz"] = img_res.get("mrz")
            result["text"] = img_res.get("text", "")
            result["ocr"] = img_res.get("ocr", {"ran": True, "engine": "pdf-embedded-ocr"})
            result["pdf_no_text"] = False
        else:
            result["pdf_no_text"] = True
            result["ocr"] = {"ran": False,
                             "reason": "PDF has no extractable text layer (scan)."}
    else:
        result["medium"] = "image"
        if _is_aadhaar(doc_type):
            # Aadhaar gets a purpose-built pass: the 5-class YOLO zone detector
            # isolates Name/DOB/Aadhaar_No/Gender/Photo; each text zone is
            # cropped and OCR'd in isolation, and the Photo crop rides along
            # for Module 4. Model missing? Falls back to the generic image OCR
            # so screening never hard-fails (Vercel-safe degradation).
            result.update(_extract_aadhaar_image(data))
        else:
            result.update(_extract_image(data, doc_type=doc_type))

    # Merge declared values only into gaps (machine-read values win).
    # Scope parsing to the selected document type: only generic identifier
    # keys or keys naming this document are considered. Unknown/unspecified
    # types retain the legacy behavior of scanning all declared values.
    doc_key = (doc_type or "").lower().strip()
    target = _TARGET_FIELD_FOR.get(doc_key)
    selected = []
    for k, v in declared.items():
        key = (k or "").lower().strip()
        if not doc_key or target is None:
            selected.append(v)
        elif (key in _GENERIC_DECL_KEYS or doc_key in key or
                (target and target in key)):
            selected.append(v)
    decl_text = " ".join(v for v in selected if isinstance(v, str))
    if not decl_text:
        decl_text = " ".join(v for v in declared.values()
                             if isinstance(v, str))
    decl_fields = extract_fields(decl_text)
    for k, v in decl_fields.items():
        if v and not result["fields"].get(k):
            result["fields"][k] = v

    # Free-text identity values (name / gender) back-fill exactly like
    # identifiers: when there is no OCR engine (Vercel/offline workers) the
    # scanner reads no holder fields, and officers legitimately type them at
    # the desk. Without this the cross-document comparison could never see a
    # name and every session would compare INCOMPLETE. Machine-read values
    # still win (same gap-only rule); a sanitized Latin form keeps digests
    # comparable across documents.
    for decl_key, field_key in (("name", "name"), ("holder_name", "name"),
                                ("gender", "gender")):
        typed = (declared.get(decl_key) or "").strip()
        if not typed or result["fields"].get(field_key):
            continue
        if field_key == "name":
            cleaned = re.sub(r"\s+", " ",
                             re.sub(r"[^A-Za-z .\-]", " ", typed)).strip()[:100]
            if cleaned:
                result["fields"]["name"] = cleaned
        else:
            g = re.search(r"\b(M|F|MALE|FEMALE)\b", typed.upper())
            if g:
                result["fields"]["gender"] = g.group(1)[0].upper()
    return result


# --------------------------------------------------------------------------- #
# Medium-specific passes
# --------------------------------------------------------------------------- #

def _pdf_text_or_image(data: bytes) -> tuple[str, bytes | None]:
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = ""
        for pg in reader.pages:
            t = ""
            try:
                t = pg.extract_text(extraction_mode="layout") or ""
            except Exception:
                t = ""
            if not t or len(t.strip()) < 10:
                t = pg.extract_text() or ""
            text += t + "\n"
        if text.strip():
            return text, None
        if reader.pages:
            for p in reader.pages:
                if getattr(p, "images", None) and len(p.images) > 0:
                    first_img = p.images[0]
                    img_d = getattr(first_img, "data", None)
                    if img_d:
                        return "", img_d
    except Exception:
        pass
    try:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        if text.strip():
            return text, None
        if len(doc) > 0:
            pix = doc[0].get_pixmap()
            return "", pix.tobytes("png")
    except Exception:
        pass
    return "", None


def _extract_image(data: bytes, doc_type: str = "") -> dict:
    """OCR + MRZ + Barcodes/QR over one image. Each subsystem is isolated: a failure in
    one never loses the rest, and unreadable input degrades to honest 'ran:
    False' rather than a hard error."""
    try:
        from app.screening import extract_fields
        from app.identity import ocr_extract
        from app.mrz import parse_mrz
        from app.llm import extract_document_data
    except ImportError:
        from screening import extract_fields
        from identity import ocr_extract
        from mrz import parse_mrz
        from llm import extract_document_data

    out = {"fields": {}, "mrz": None,
           "ocr": {"ran": False, "reason": "not run"}, "pdf_no_text": False,
           "llm_extraction": {"ran": False, "reason": "not run"},
           "qr_data": None, "text": ""}

    # 1. Barcode & QR extraction (100% exact cryptographic fields if present)
    try:
        try:
            from app.qr_decoder import extract_from_barcodes
        except ImportError:
            from qr_decoder import extract_from_barcodes
        qr_res = extract_from_barcodes(data, doc_type=doc_type)
        if qr_res.get("ran") and qr_res.get("fields"):
            for k, v in qr_res["fields"].items():
                if v:
                    out["fields"][k] = v
            out["qr_data"] = qr_res
    except Exception:
        pass

    text, ocr_meta = ocr_extract(data)
    out["ocr"] = ocr_meta
    out["text"] = text or ""
    if text:
        extracted = extract_fields(text, doc_type=doc_type)
        for k, v in extracted.items():
            if v and not out["fields"].get(k):
                out["fields"][k] = v
        try:
            mrz_res = parse_mrz(text)
            if mrz_res.get("valid"):
                out["mrz"] = _mrz_public(mrz_res)
                # Enrich fields with verified MRZ data
                if mrz_res.get("passport_number") and not out["fields"].get("passport"):
                    out["fields"]["passport"] = mrz_res["passport_number"]
                if mrz_res.get("dob") and not out["fields"].get("dob"):
                    out["fields"]["dob"] = mrz_res["dob"]
                if mrz_res.get("expiry") and not out["fields"].get("expiry"):
                    out["fields"]["expiry"] = mrz_res["expiry"]
                mrz_full_name = f"{mrz_res.get('surname', '')} {mrz_res.get('given_names', '')}".strip()
                if mrz_full_name and not out["fields"].get("mrz_name"):
                    out["fields"]["mrz_name"] = mrz_full_name
                out["fields"]["mrz_valid"] = True
        except Exception:
            out["mrz"] = None

    # Dedicated MRZ zone detector pass if whole-page OCR did not yield a valid MRZ
    if not out.get("mrz"):
        try:
            try:
                from app.yolo_roi import extract_mrz_zone, get_mrz_detector_backend
                from app.mrz_enhancer import extract_and_parse_mrz_enhanced
                from app.identity import _get_rapid_ocr
            except ImportError:
                from yolo_roi import extract_mrz_zone, get_mrz_detector_backend
                from mrz_enhancer import extract_and_parse_mrz_enhanced
                from identity import _get_rapid_ocr

            mrz_box = extract_mrz_zone(data)
            rapid_ocr = _get_rapid_ocr()
            if rapid_ocr is not None:
                import io
                import numpy as np
                from PIL import Image
                with Image.open(io.BytesIO(data)) as im:
                    rgb_mat = np.asarray(im.convert("RGB"), dtype=np.uint8)
                m_res = extract_and_parse_mrz_enhanced(rgb_mat, rapid_ocr, mrz_box=mrz_box)
                if m_res.get("valid"):
                    out["mrz"] = _mrz_public(m_res)
                    out["mrz"]["effective_backend"] = (mrz_box or {}).get("mrz_backend", get_mrz_detector_backend())
                    if m_res.get("passport_number") and not out["fields"].get("passport"):
                        out["fields"]["passport"] = m_res["passport_number"]
                    if m_res.get("dob") and not out["fields"].get("dob"):
                        out["fields"]["dob"] = m_res["dob"]
                    if m_res.get("expiry") and not out["fields"].get("expiry"):
                        out["fields"]["expiry"] = m_res["expiry"]
                    mrz_full_name = f"{m_res.get('surname', '')} {m_res.get('given_names', '')}".strip()
                    if mrz_full_name and not out["fields"].get("mrz_name"):
                        out["fields"]["mrz_name"] = mrz_full_name
                    out["fields"]["mrz_valid"] = True
        except Exception:
            pass

    # Multi-crop enhancement pass: If key identity numbers are missing, crop the center card area
    # to significantly boost OCR resolution and eliminate glare around outer borders
    if not (out["fields"].get("pan") or out["fields"].get("aadhaar") or out["fields"].get("passport") or out["fields"].get("driving_licence") or out["fields"].get("voter_id")):
        try:
            import io
            from PIL import Image, ImageOps
            img = Image.open(io.BytesIO(data))
            img = ImageOps.exif_transpose(img)
            w_img, h_img = img.size
            if w_img >= 200 and h_img >= 200:
                crop_box = (int(w_img * 0.18), int(h_img * 0.18), int(w_img * 0.82), int(h_img * 0.82))
                crop_im = img.crop(crop_box)
                c_buf = io.BytesIO()
                crop_im.save(c_buf, format="JPEG", quality=95)
                c_bytes = c_buf.getvalue()
                text_crop, _ = ocr_extract(c_bytes)
                if text_crop:
                    out["text"] = f"{out['text']}\n{text_crop}"
                    extracted_crop = extract_fields(text_crop, doc_type=doc_type)
                    for k, v in extracted_crop.items():
                        if v and not out["fields"].get(k):
                            out["fields"][k] = v
        except Exception:
            pass

    # LLM Structured Extraction pass
    llm_res = extract_document_data(data)
    out["llm_extraction"] = {"ran": llm_res.get("ran", False), "reason": llm_res.get("reason", "unknown")}
    if llm_res.get("ran") and llm_res.get("fields"):
        # Merge LLM extracted fields into out["fields"] where gaps exist
        for k, v in llm_res["fields"].items():
            if v and not out["fields"].get(k):
                out["fields"][k] = v

    return out


def _mrz_public(res: dict) -> dict:
    """Slim MRZ result for the report: format + check-digit outcome + masked
    identifiers. Never the raw MRZ lines (zero-storage rule)."""
    try:
        from app.screening import mask
    except ImportError:
        from screening import mask
    checks = res.get("checks") or {}
    pub = {
        "format": res.get("format"),
        "valid": bool(res.get("valid")),
        "document_ck": _check_ok(checks.get("document_number")),
        "dob_ck": _check_ok(checks.get("dob")),
        "expiry_ck": _check_ok(checks.get("expiry")),
        "composite_ck": _check_ok(checks.get("composite")),
    }
    pno = res.get("passport_number")
    if pno:
        pub["passport"] = mask(pno)
    return pub


def _check_ok(ck):
    return ck.get("ok") if isinstance(ck, dict) else None


# --------------------------------------------------------------------------- #
# Aadhaar domestic-ID pass (Module 1 national-ID route)
# --------------------------------------------------------------------------- #

# 12-digit UIDAI number — spaces or none between the 4/4/4 groups.
_AADHAAR_NO_RE = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")


def _is_aadhaar(doc_type: str) -> bool:
    return (doc_type or "").strip().lower() in ("aadhaar", "aadhaar_card", "aadhar")


def _extract_aadhaar_image(data: bytes) -> dict:
    """Aadhaar-optimised extraction for image scans.

    The 5-class ONNX detector locates the field zones on the card; each text
    zone (Name / DOB / Aadhaar_No / Gender) is cropped and OCR'd in isolation
    — far more robust than whole-card OCR on dense UV-stamped text — and the
    Photo zone crop is handed to Module 4 for face verification. Fields and
    photos are USED and DISCARDED: nothing persists (zero-storage rule).
    """
    import base64
    try:
        from app.yolo_roi import crop_region_to_bytes, extract_aadhaar_fields
    except ImportError:
        from yolo_roi import crop_region_to_bytes, extract_aadhaar_fields

    out = {"fields": {}, "mrz": None,
           "ocr": {"ran": False, "reason": "aadhaar zone OCR not run"},
           "pdf_no_text": False,
           "aadhaar_photo": None,      # b64 PNG crop -> Module 4 (memory only)
           "aadhaar_zones": [],        # zone metadata (label + confidence; no PII)
           "qr_data": None}

    photo_b64 = None

    # 0. Barcode & QR extraction (UIDAI Secure QR or Code128 barcode)
    try:
        try:
            from app.qr_decoder import extract_from_barcodes
        except ImportError:
            from qr_decoder import extract_from_barcodes
        qr_res = extract_from_barcodes(data, "aadhaar")
        if qr_res.get("ran") and qr_res.get("fields"):
            for k, v in qr_res["fields"].items():
                if v:
                    out["fields"][k] = v
            out["qr_data"] = qr_res
            if qr_res.get("photo_b64"):
                photo_b64 = qr_res["photo_b64"]
    except Exception:
        pass

    boxes = extract_aadhaar_fields(data)
    if not boxes:
        # Model absent (e.g. Vercel) or no zones found: degrade to the generic
        # image pass so Aadhaar still screens with whole-card OCR + LLM heuristics.
        whole = _extract_image(data, doc_type="aadhaar")
        for k, v in whole.get("fields", {}).items():
            if v and not out["fields"].get(k):
                out["fields"][k] = v
        out["ocr"] = whole.get("ocr", out["ocr"])
        if whole.get("qr_data") and not out.get("qr_data"):
            out["qr_data"] = whole["qr_data"]
        return out

    for b in boxes:
        label = str(b.get("label") or "").strip()
        out["aadhaar_zones"].append(
            {"label": label, "confidence": round(float(b.get("confidence") or 0), 3)})
        crop = crop_region_to_bytes(data, b, padding=0.08)
        if not crop:
            continue
        key = label.lower().replace(" ", "_")
        if key == "photo":
            photo_b64 = base64.b64encode(crop).decode("ascii")
            continue
        text = _zone_ocr(crop)
        if text:
            out["ocr"] = {"ran": True, "engine": "aadhaar-zone-ocr",
                          "reason": f"zone OCR on {label}"}
            _consume_aadhaar_zone(out["fields"], key, text)
    out["aadhaar_photo"] = photo_b64

    # Backfill with whole-image OCR if key fields are missing
    if not out["fields"].get("aadhaar") or not out["fields"].get("name"):
        whole = _extract_image(data, doc_type="aadhaar")
        for k, v in whole.get("fields", {}).items():
            if v and not out["fields"].get(k):
                out["fields"][k] = v
        if whole.get("ocr", {}).get("ran"):
            out["ocr"] = whole["ocr"]

    return out


def _zone_ocr(crop_bytes: bytes) -> str:
    """OCR over ONE cropped field zone using RapidOCR or local fallback."""
    try:
        from app.identity import ocr_extract
    except ImportError:
        from identity import ocr_extract
    text, _ = ocr_extract(crop_bytes)
    return text or ""


def _consume_aadhaar_zone(fields: dict, key: str, text: str) -> None:
    """Fold one OCR'd zone into the normalized field map. Garbage yields a gap,
    never a wrong value — downstream validators skip absent fields."""
    try:
        from app.screening import _first_date
    except ImportError:
        from screening import _first_date
    if not text:
        return
    if "aadhaar" in key or "no" in key or "uid" in key:
        digits = re.sub(r"\D", "", text)
        if len(digits) == 12 and digits[0] not in ("0", "1"):
            fields["aadhaar"] = digits
        else:
            m = _AADHAAR_NO_RE.search(text)
            if m:
                clean = re.sub(r"[ -]", "", m.group(0))
                if len(clean) == 12 and clean[0] not in ("0", "1"):
                    fields["aadhaar"] = clean
    elif "dob" in key or "birth" in key:
        d = _first_date(text)
        if d:
            fields["dob"] = d
    elif "name" in key:
        name = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z .\-]", " ", text)).strip()
        if name and len(name) >= 3:
            fields["name"] = name[:100]
    elif key == "gender":
        g = re.search(r"\b(M|F|MALE|FEMALE)\b", text, re.IGNORECASE)
        if g:
            fields["gender"] = g.group(0).upper()[0]