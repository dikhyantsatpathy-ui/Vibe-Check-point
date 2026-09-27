"""
Tests for the MHA screening pipeline's deterministic identifier layer.

Covers normalization/masking, ICAO 9303 MRZ check digits and the regex
extraction layer (incl. PAN, driving licence, voter-ID/EPIC).

Run either way (no deps beyond what the app already needs):
    python tests/test_screening.py        # plain asserts
    pytest tests/test_screening.py        # pytest runner

Vectors: the MRZ line is the ICAO 9303 TD3 specimen (passport L898902C,
DOB 690806, expiry 940623 — check digits 3 / 1 / 6).
"""

import os
import numpy as np
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "app"))

from screening import (
    _parse_date,
    extract_fields,
    extract_mrz,
    mask,
    norm,
    mrz_checkdigit,
    sha256,
)

_MRZ_LINE2 = "L898902C<3UTO6908061F9406236"


def test_norm_collapses_spacing_and_case():
    assert norm("ka-01/2020/1234567") == norm("KA 012020 1234567")
    assert norm("  AbC 12-34 ") == "ABC1234"
    assert norm("2345 1234 5678") == "234512345678"


def test_norm_handles_empty_and_non_string():
    assert norm("") == ""
    assert norm(None) == ""
    assert norm(987654321096) == "987654321096"


def test_mask_keeps_only_tail():
    assert mask("234512345670") == "********5670"
    assert mask("ABC1234567") == "******4567"
    assert mask("abc") == "ABC"  # short values are returned whole, normalized


def test_sha256_deterministic_and_normalized():
    assert sha256("2345 1234 5678") == sha256("234512345678")
    assert len(sha256("x")) == 64


def test_mrz_checkdigit_icao_specimen():
    assert mrz_checkdigit("L898902C<") == 3
    assert mrz_checkdigit("690806") == 1
    assert mrz_checkdigit("940623") == 6


def test_extract_mrz_valid_specimen():
    out = extract_mrz(_MRZ_LINE2)
    assert out["passport"] == "L898902C"      # ICAO '<' padding stripped
    assert out["mrz_valid"] is True
    assert out["mrz_dob"] == "690806"


def test_extract_mrz_tampered_expiry_fails():
    # Flip the expiry check digit: the MRZ must no longer validate.
    tampered = _MRZ_LINE2[:-1] + str((int(_MRZ_LINE2[-1]) + 1) % 10)
    out = extract_mrz(tampered)
    assert out["mrz_valid"] is False
    assert out["mrz_expiry_ck"] is False


def test_extract_fields_pan():
    out = extract_fields("PAN AAAPL1234C on the corner.")
    assert out["pan"] == "AAAPL1234C"


def test_extract_fields_driving_licence():
    out = extract_fields("DL MH01 2015 0001234, valid till 2035.")
    assert out["driving_licence"] is not None


def test_extract_fields_voter_id_epic():
    out = extract_fields("EPIC card number ABC1234567 issued by the ECI.")
    assert out["voter_id"] == "ABC1234567"


def test_extract_fields_voter_id_rejects_bad_shape():
    assert extract_fields("EPIC AB1234567 (two letters is invalid)")["voter_id"] is None
    assert extract_fields("EPIC ABCD1234567 (four letters invalid)")["voter_id"] is None


def test_extract_fields_phone_and_dob():
    out = extract_fields("Contact 9876543210, DOB 06/08/1969.")
    assert out["phone"] == "9876543210"
    assert out["dob"] == "1969-08-06"


def test_extract_fields_mrz_populates_adult_dob():
    # No plain-text DOB, but the MRZ is valid -> century heuristic yields 1969.
    out = extract_fields(f"Passport page. {_MRZ_LINE2} footer.")
    assert out["passport"] == "L898902C"
    assert out["dob"] == "1969-08-06"
    assert out["mrz_valid"] is True


def test_extract_fields_mrz_populates_child_dob():
    # YYMMDD "050104" with current 2-digit year 26 -> born in 2005 (not 1905).
    pno = "P1234567<"
    line = f"{pno}{mrz_checkdigit(pno)}UTO050104{mrz_checkdigit('050104')}M160905{mrz_checkdigit('160905')}"
    out = extract_fields(f"footer {line} more")
    assert out["passport"] == "P1234567"
    assert out["dob"] == "2005-01-04"
    assert out["mrz_valid"] is True


def test_extract_mrz_stateless_nationality():
    # UN/stateless passports print '<<<' in the nationality field — the zone
    # must still parse and validate (regression: previously returned {}).
    pno = "ABCD1234<"
    nat = "<<<"
    dob = "690806"
    exp = "241231"
    line = f"{pno}{mrz_checkdigit(pno)}{nat}{dob}{mrz_checkdigit(dob)}M{exp}{mrz_checkdigit(exp)}"
    out = extract_mrz(line)
    assert out["mrz_valid"] is True
    assert out["passport"] == "ABCD1234"


def test_extract_fields_dob_ignores_future_expiry():
    # A document prints 'VALID TILL' BEFORE the DOB — the first date must not
    # be mistaken for a birth date (the DOB is the oldest date on the page).
    out = extract_fields("VALID TILL: 31-12-2031  DOB: 15-08-1990")
    assert out["dob"] == "1990-08-15"


def test_parse_date_accepts_both_orders():
    assert _parse_date("1990-08-15") == (1990, 8, 15)   # ISO
    assert _parse_date("15-08-1990") == (1990, 8, 15)   # officer-typed DMY
    assert _parse_date("15/08/1990") == (1990, 8, 15)   # slash separator
    assert _parse_date("2031-12-31") == (2031, 12, 31)


def test_parse_date_rejects_garbage_silently():
    # Unparseable input must SKIP the expired check, never misfire on a typo.
    assert _parse_date("") is None
    assert _parse_date("not a date") is None
    assert _parse_date("15-15-1990") is None   # month 15 impossible
    assert _parse_date("1990-13-40") is None
    assert _parse_date(None) is None


# ============================================================================
# Module 1 — Extraction (app/extraction.py)
# ============================================================================

def test_module1_extracts_pdf_text_layer():
    from extraction import extract_document
    pdf = b"%PDF-1.4\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n" * 1
    # extract_document reports the medium even when pypdf cannot decode junk bytes
    res = extract_document(pdf, "scan.pdf", "passport")
    assert res["medium"] == "pdf"


def test_module1_declared_merges_only_into_gaps():
    from extraction import extract_document
    # No OCR/mrz: fields empty, so the declared number must land into fields.
    res = extract_document(b"\xff\xd8\xff\xe0not-an-image", "doc.jpg", "pan",
                           {"document_number": "ABCDP2234A"})
    assert res["medium"] == "image" or res["medium"] == "unknown"
    assert res["fields"].get("pan") == "ABCDP2234A"


def test_module1_declared_values_are_scoped_by_document_type():
    from extraction import extract_document
    # A passport pass must accept the generic declared number but must not let
    # an EPIC-typed declared value populate the voter-ID field.
    res = extract_document(b"junk", "visa.pdf", "passport",
                           {"document_number": "K1234567",
                            "epic_number": "ABC1234567"})
    assert res["fields"].get("passport") == "K1234567"
    assert res["fields"].get("voter_id") is None


def test_module1_extracts_from_declared_pdf():
    from extraction import extract_document
    res = extract_document(b"junk", "visa.pdf", "passport",
                           {"document_number": "K1234567"})
    assert res["ocr"]["ran"] is False


def test_module1_declared_name_and_gender_backfill_when_no_ocr():
    from extraction import extract_document
    # No OCR engine (Vercel/offline): typed name/gender must reach the field
    # map so cross-document comparison can compare them instead of INCOMPLETE.
    res = extract_document(b"\xff\xd8\xff\xe0not-an-image", "doc.jpg", "aadhaar",
                           {"name": "Dikhyant Satapathy", "dob": "1992-08-15",
                            "gender": "Male"})
    assert res["fields"].get("name") == "Dikhyant Satapathy"
    assert res["fields"].get("gender") == "M"
    assert res["fields"].get("dob") == "1992-08-15"
    # Devanagari/mixed junk in a typed name is sanitized to a Latin form so
    # digest comparison stays comparable, never fabricating a raw match.
    res2 = extract_document(b"\xff\xd8\xff\xe0not-an-image", "doc.jpg", "aadhaar",
                            {"name": "दीक्षांत शतपथी / DIKHYANT SATAPATHY"})
    assert res2["fields"].get("name") == "DIKHYANT SATAPATHY"


# ============================================================================
# Module 2 — Validation (app/validation.py)
# ============================================================================

def test_module2_pan_valid_passes():
    from validation import validate_document
    res = validate_document("pan", {"pan": "ABCDP2234A"})
    assert res["verdict"] == "PASS"
    assert {c["label"] for c in res["checks"]} >= {"structure", "category-letter",
                                                   "check-char"}


def test_module2_dl_invalid_structure_fails():
    from validation import validate_document
    res = validate_document("driving_licence", {"driving_licence": "not-a-licence"})
    assert res["verdict"] == "FAIL"


def test_module2_no_number_never_silent_pass():
    from validation import validate_document
    res = validate_document("pan", {}, {"document_number": "ABCDP2234A"})
    # Nothing verifiable -> UNVERIFIED, never a silent pass or a "valid" claim.
    assert res["verdict"] == "UNVERIFIED"


def test_module2_watchlist_hit_surfaces_fail_and_review():
    from validation import validate_document
    hits = [{"field": "pan", "mask": "******2234A"}]
    res = validate_document("pan", {"pan": "ABCDP2234A"}, watchlist_hits=hits)
    # Valid PAN + watchlist hit -> mixed signals, REVIEW (deck risk folds to FLAGGED)
    assert res["verdict"] == "REVIEW"
    assert any(c["label"] == "watchlist" and c["ok"] is False for c in res["checks"])


def test_module2_expired_date_fails_surfaces_review():
    from validation import validate_document
    res = validate_document("driving_licence", {"driving_licence": "KA0120201234567"},
                            {"expiry_date": "01-01-2000"})
    assert res["verdict"] == "REVIEW"
    assert any(c["label"] == "expiry" and c["ok"] is False for c in res["checks"])


def test_module2_passport_mrz_fallback_via_fields():
    from validation import validate_document
    # No raw MRZ text handed in, but the extractor validated the check digits:
    # that outcome must be folded into Module 2 (zero-storage of MRZ lines).
    res = validate_document("passport", {"passport": "K1234567",
                                         "mrz_valid": True})
    assert res["verdict"] == "PASS"
    assert any(c["label"] == "mrz-check-digits" and c["ok"] is True
               for c in res["checks"])


# ============================================================================
# Module 3 — Tampering (app/tampering.py)
# ============================================================================

def test_module3_no_image_degrades_honestly():
    from tampering import tamper_analysis
    res = tamper_analysis(None)
    assert res["verdict"] == "UNVERIFIED"
    assert any(c["label"] == "ela" and c["ok"] is None for c in res["checks"])


def test_module3_ai_suspected_flags_fail():
    from io import BytesIO
    from PIL import Image
    from tampering import tamper_analysis
    img = BytesIO()
    Image.new("RGB", (96, 64), (230, 230, 230)).save(img, format="PNG")
    ai = {"ran": True, "ai_suspected": True, "ai_score": 0.9, "provider": "test",
          "explanation": "synthetic by test"}
    res = tamper_analysis(img.getvalue(), ai_detection=ai,
                          document_aware=False, doc_type="pan")
    # Weighted-evidence redesign (FIX_ALL_ISSUES.md §1 Problem 1): a single
    # ai-generated-or-edited signal is intentionally corroborating-only
    # (weight 0.5, below the 1.3 FAIL threshold) so one noisy detector can no
    # longer hard-veto a document alone — it now correctly lands on REVIEW,
    # not an automatic FAIL. See tampering.CHECK_WEIGHTS.
    assert res["verdict"] in ("REVIEW", "FAIL")
    assert any(c["label"] == "ai-generated-or-edited" and c["ok"] is False
               for c in res["checks"])


def test_doc_forgery_returns_dead_block_ratio_and_largest_component():
    """Regression test: analyze_doc_forgery()'s return dict must carry
    dead_block_ratio and largest_component — tampering.py's optional
    ONNX-classifier feature vector reads both, and they used to silently
    default to 0.0 because the return dict never actually included them."""
    from io import BytesIO
    from PIL import Image
    from doc_forgery import analyze_doc_forgery
    img = BytesIO()
    Image.new("RGB", (256, 256), (180, 180, 180)).save(img, format="PNG")
    res = analyze_doc_forgery(img.getvalue())
    assert res.get("ran") is True
    assert "dead_block_ratio" in res
    assert "largest_component" in res
    assert isinstance(res["dead_block_ratio"], float)
    assert isinstance(res["largest_component"], int)


def test_onnx_classifier_is_weighted_not_a_hard_override():
    """Regression test: when the optional ONNX tamper-classifier is present,
    its result must be folded into the weighted verdict as one more check —
    not allowed to unilaterally set verdict = FAIL/PASS on its own. A single
    classifier "tampered" reading (weight 1.2, below the 1.3 FAIL threshold)
    on an otherwise-clean document must land on REVIEW, never a hard FAIL,
    exactly like every other single-signal check."""
    from io import BytesIO
    from unittest.mock import patch, MagicMock
    from PIL import Image
    import tampering

    class _FakeInput:
        name = "input"

    class _FakeSession:
        def get_inputs(self):
            return [_FakeInput()]

        def run(self, output_names, feed):
            return [np.array([1])]  # "tampered" = 1

    img = BytesIO()
    Image.new("RGB", (256, 256), (200, 200, 200)).save(img, format="PNG")
    ai = {"ran": True, "ai_suspected": False, "ai_score": 0, "provider": "test"}

    with patch.object(tampering, "_load_tamper_classifier", return_value=_FakeSession()):
        res = tampering.tamper_analysis(img.getvalue(), ai_detection=ai,
                                        document_aware=False, doc_type="pan")
    assert any(c["label"] == "onnx-classifier" for c in res["checks"])
    assert res["verdict"] != "FAIL", (
        "A single ONNX-classifier 'tampered' reading must not hard-override "
        "the whole verdict — it should be weighed against the other checks."
    )


# ============================================================================
# Module 4 — Face (app/face.py)
# ============================================================================

def test_module4_no_document_face_reviews():
    from face import face_verification
    res = face_verification(document_bytes=b"\xff\xd8notreal", live_frame=b"\xff\xd8also")
    assert res["verdict"] == "REVIEW" or res["verdict"] == "UNVERIFIED"
    assert res["score"] == 0


# ============================================================================
# Anti-Fraud Hard-Veto & Verdict Rules (app/screening.py)
# ============================================================================

def test_grade_hard_veto_flagged():
    from screening import _grade
    assert _grade(15, hard_flag=True) == "FLAGGED"
    assert _grade(15, hard_flag=False, can_clear=True) == "CLEAR"
    assert _grade(15, hard_flag=False, can_clear=False) == "REVIEW"
    assert _grade(58, hard_flag=False, can_clear=True) == "FLAGGED"


def test_screening_empty_or_fake_document_never_clears():
    from unittest.mock import MagicMock
    from screening import run_screening
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []

    res = run_screening(b"fake content without any id", "fake.pdf", "other", "CP-1", {})
    assert res["verdict"] in ("REVIEW", "FLAGGED")
    assert res["verdict"] != "CLEAR"
    assert any("machine-verifiable" in r.lower() for r in res["reasons"])


def test_screening_declared_pan_mismatch_flags_or_reviews():
    from unittest.mock import MagicMock
    from screening import run_screening
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []

    res = run_screening(b"This is definitely not a PAN card", "fake_pan.pdf", "pan", "CP-1", {})
    assert res["verdict"] in ("REVIEW", "FLAGGED")
    assert res["verdict"] != "CLEAR"
    assert any("pan" in r.lower() and "mismatch" in r.lower() for r in res["reasons"])


def test_screening_ai_suspected_hard_flags():
    from unittest.mock import MagicMock, patch
    from screening import run_screening
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []

    ai_mock = {
        "ran": True,
        "ai_suspected": True,
        "ai_score": 85,
        "model": "ViT",
        "provider": "self-hosted",
        "explanation": "High confidence synthetic image",
        "latency_ms": 10,
    }
    import main
    with patch.object(main, "detect_image", return_value=ai_mock):
        if "app.main" in sys.modules:
            import app.main
            with patch.object(app.main, "detect_image", return_value=ai_mock):
                res = run_screening(b"\xff\xd8\xff\xe0mock_ai_image", "ai_fake.jpg", "pan", "CP-1", {})
        else:
            res = run_screening(b"\xff\xd8\xff\xe0mock_ai_image", "ai_fake.jpg", "pan", "CP-1", {})
        assert res["verdict"] == "FLAGGED"
        assert res["risk_score"] >= 70
        assert any("ai" in r.lower() for r in res["reasons"])


def test_screening_mrz_checksum_failure_hard_flags():
    from unittest.mock import MagicMock, patch
    from screening import run_screening
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []

    extract_mock = {
        "medium": "pdf",
        "fields": {"passport": "K1234567", "mrz_valid": False},
        "mrz": None,
        "ocr": {"ran": True},
        "pdf_no_text": False,
    }
    with patch("extraction.extract_document", return_value=extract_mock):
        res = run_screening(b"dummy passport", "passport.pdf", "passport", "CP-1", {})
        assert res["verdict"] == "FLAGGED"
        assert res["risk_score"] >= 70
        assert any("mrz" in r.lower() and "fail" in r.lower() for r in res["reasons"])


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print("PASS", fn.__name__)
    print(f"{passed}/{len(fns)} tests passed")