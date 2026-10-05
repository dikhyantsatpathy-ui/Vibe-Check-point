import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

from qr_decoder import parse_aadhaar_qr, parse_pan_qr
from dl_verify import verify_driving_licence
from screening import extract_fields


def test_pan_regex_robustness():
    # Spaced PAN from webcam OCR
    text = "INCOME TAX DEPARTMENT\nPermanent Account Number\nMQYPS 6545 L\nName: RAHUL SHARMA"
    f = extract_fields(text)
    assert f.get("pan") == "MQYPS6545L"
    assert f.get("name") == "RAHUL SHARMA"


def test_dl_regex_and_verification():
    dl_text = "DRIVING LICENCE\nDL NO: DL-04 2011 0012345\nVALID TILL: 31-12-2029"
    f = extract_fields(dl_text)
    assert f.get("driving_licence") == "DL0420110012345"
    assert f.get("expiry") == "2029-12-31"

    # DL validator
    res = verify_driving_licence("DL-04 2011 0012345")
    assert res["valid"] is True
    assert res["state_name"] == "Delhi"
    assert res["issue_year"] == 2011


def test_pincode_and_address_extraction():
    text = "Address: House No 42, Sector 15, Gandhinagar, Gujarat - 382015"
    f = extract_fields(text)
    assert f.get("pincode") == "382015"
    assert "House No 42" in (f.get("address") or "")


def test_xml_aadhaar_qr_parsing():
    xml_qr = '<?xml version="1.0" encoding="UTF-8"?><PrintLetterBarcodeData uid="812229740810" name="Amit Kumar" gender="M" dob="15-08-1992" house="Flat 12" dist="Patna" state="Bihar" pc="800001"/>'
    rec = {"format": "QRCode", "text": xml_qr}
    res = parse_aadhaar_qr(rec)
    assert res["valid"] is True
    assert res["fields"]["aadhaar"] == "812229740810"
    assert res["fields"]["name"] == "Amit Kumar"
    assert res["fields"]["dob"] == "1992-08-15"
    assert res["fields"]["pincode"] == "800001"
    assert res["fields"]["state"] == "Bihar"


def test_pan_qr_parsing():
    pan_qr = "MQYPS6545L|VIKRAM SINGH|RAMESH SINGH|10/04/1988"
    rec = {"format": "QRCode", "text": pan_qr}
    res = parse_pan_qr(rec)
    assert res["valid"] is True
    assert res["fields"]["pan"] == "MQYPS6545L"
    assert res["fields"]["name"] == "VIKRAM SINGH"
    assert res["fields"]["dob"] == "1988-04-10"
