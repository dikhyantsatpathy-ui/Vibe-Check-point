"""Regression tests for the Nov 16 audit fixes."""
from app.qr_decoder import parse_aadhaar_qr


def _rec(text):
    return {"format": "QRCode", "text": text}


def test_qr_xml_with_entities_is_rejected_not_parsed():
    bomb = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>'
            '<PrintLetterBarcodeData uid="123456789012" name="&a;"/>')
    out = parse_aadhaar_qr(_rec(bomb))
    assert not out["valid"]
    assert not out["fields"].get("aadhaar")


def test_qr_doctype_case_and_spacing_variants_rejected():
    sneaky = '<?xml version="1.0"?><! doctype x><PrintLetterBarcodeData uid="123456789012"/>'
    assert not parse_aadhaar_qr(_rec(sneaky))["fields"].get("aadhaar")


def test_qr_plain_xml_still_parses():
    ok = '<?xml version="1.0"?><PrintLetterBarcodeData uid="123456789012" name="A B"/>'
    out = parse_aadhaar_qr(_rec(ok))
    assert out["fields"].get("aadhaar") == "123456789012"


def test_requirements_pin_patched_versions():
    reqs = open("requirements.txt", encoding="utf-8").read()
    assert "Pillow==13.0.0" in reqs
    assert "pypdf==6.21.4" in reqs
