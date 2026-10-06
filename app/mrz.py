"""
ICAO Doc 9303 Machine Readable Zone (MRZ) parser and validator.

Supports all standard ICAO Doc 9303 formats:
  - TD1 (3 lines of 30 characters, typically ID cards / residence cards)
  - TD2 (2 lines of 36 characters, visas / official travel cards)
  - TD3 (2 lines of 44 characters, international standard passports)

Implements the official ICAO 7-3-1 modulus-10 weighting algorithm for
calculating and verifying check digits:
  - Document Number check digit
  - Date of Birth (YYMMDD) check digit
  - Expiry Date (YYMMDD) check digit
  - Optional Data / Personal Number check digit
  - Overall Composite Check Digit

Zero-PII discipline: parsed holder names can be extracted or masked as requested.
"""

import re
from typing import Any

# Character value mapping per ICAO Doc 9303 Part 3
_CHAR_VALUES: dict[str, int] = {
    **{str(i): i for i in range(10)},
    **{chr(c): c - ord('A') + 10 for c in range(ord('A'), ord('Z') + 1)},
    '<': 0,
}

_WEIGHTS = (7, 3, 1)

# ICAO character correction mapping for OCR confusion in numeric slots
# O/0, I/1, B/8, S/5, Z/2, G/6 per Phase C2 specification
_ICAO_DIGIT_MAP: dict[str, str] = {
    'O': '0', 'D': '0', 'Q': '0', 'U': '0',
    'I': '1', 'L': '1', '|': '1',
    'Z': '2',
    'B': '8',
    'S': '5',
    'G': '6',
}

_ICAO_ALPHA_MAP: dict[str, str] = {
    '0': 'O',
    '1': 'I',
    '2': 'Z',
    '8': 'B',
    '5': 'S',
    '6': 'G',
}


def correct_td3_line2(line2: str) -> str:
    """Apply ICAO position-aware character correction (O/0, I/1, B/8, S/5, Z/2, G/6) to TD3 Line 2."""
    l2 = list(line2.ljust(44, '<')[:44])
    # pos 9: Document number check digit (ALWAYS digit)
    if l2[9] in _ICAO_DIGIT_MAP:
        l2[9] = _ICAO_DIGIT_MAP[l2[9]]
    # pos 10..12: Nationality (ALWAYS alpha)
    for i in range(10, 13):
        if l2[i] in _ICAO_ALPHA_MAP:
            l2[i] = _ICAO_ALPHA_MAP[l2[i]]
    # pos 13..18: Date of birth YYMMDD (ALWAYS digits)
    for i in range(13, 19):
        if l2[i] in _ICAO_DIGIT_MAP:
            l2[i] = _ICAO_DIGIT_MAP[l2[i]]
    # pos 19: DOB check digit (ALWAYS digit)
    if l2[19] in _ICAO_DIGIT_MAP:
        l2[19] = _ICAO_DIGIT_MAP[l2[19]]
    # pos 21..26: Expiry date YYMMDD (ALWAYS digits)
    for i in range(21, 27):
        if l2[i] in _ICAO_DIGIT_MAP:
            l2[i] = _ICAO_DIGIT_MAP[l2[i]]
    # pos 27: Expiry check digit (ALWAYS digit)
    if l2[27] in _ICAO_DIGIT_MAP:
        l2[27] = _ICAO_DIGIT_MAP[l2[27]]
    # pos 42: Optional data check digit
    if l2[42] in _ICAO_DIGIT_MAP:
        l2[42] = _ICAO_DIGIT_MAP[l2[42]]
    # pos 43: Overall composite check digit (ALWAYS digit)
    if l2[43] in _ICAO_DIGIT_MAP:
        l2[43] = _ICAO_DIGIT_MAP[l2[43]]
    return "".join(l2)


def correct_td1_lines(line1: str, line2: str) -> tuple[str, str]:
    """Apply ICAO position-aware character correction to TD1 Lines 1 and 2."""
    l1 = list(line1.ljust(30, '<')[:30])
    for i in range(0, 5):
        if l1[i] in _ICAO_ALPHA_MAP:
            l1[i] = _ICAO_ALPHA_MAP[l1[i]]
    if l1[14] in _ICAO_DIGIT_MAP:
        l1[14] = _ICAO_DIGIT_MAP[l1[14]]

    l2 = list(line2.ljust(30, '<')[:30])
    for i in range(0, 7):
        if l2[i] in _ICAO_DIGIT_MAP:
            l2[i] = _ICAO_DIGIT_MAP[l2[i]]
    for i in range(8, 15):
        if l2[i] in _ICAO_DIGIT_MAP:
            l2[i] = _ICAO_DIGIT_MAP[l2[i]]
    for i in range(15, 18):
        if l2[i] in _ICAO_ALPHA_MAP:
            l2[i] = _ICAO_ALPHA_MAP[l2[i]]
    if l2[29] in _ICAO_DIGIT_MAP:
        l2[29] = _ICAO_DIGIT_MAP[l2[29]]
    return "".join(l1), "".join(l2)


def correct_td2_line2(line2: str) -> str:
    """Apply ICAO position-aware character correction to TD2 Line 2."""
    l2 = list(line2.ljust(36, '<')[:36])
    if l2[9] in _ICAO_DIGIT_MAP:
        l2[9] = _ICAO_DIGIT_MAP[l2[9]]
    for i in range(10, 13):
        if l2[i] in _ICAO_ALPHA_MAP:
            l2[i] = _ICAO_ALPHA_MAP[l2[i]]
    for i in range(13, 20):
        if l2[i] in _ICAO_DIGIT_MAP:
            l2[i] = _ICAO_DIGIT_MAP[l2[i]]
    for i in range(21, 28):
        if l2[i] in _ICAO_DIGIT_MAP:
            l2[i] = _ICAO_DIGIT_MAP[l2[i]]
    if l2[35] in _ICAO_DIGIT_MAP:
        l2[35] = _ICAO_DIGIT_MAP[l2[35]]
    return "".join(l2)


def compute_mrz_check_digit(data: str) -> int:
    """Calculate the ICAO 9303 modulus-10 check digit for a string.
    
    Weights cycle in the sequence 7, 3, 1:
      total = sum(char_val(c) * weight) % 10
    """
    total = 0
    clean = (data or "").upper()
    for idx, ch in enumerate(clean):
        val = _CHAR_VALUES.get(ch, 0)
        weight = _WEIGHTS[idx % 3]
        total += val * weight
    return total % 10


def verify_check_digit(field: str, expected_digit: str | int) -> bool:
    """Verify if the computed check digit matches the expected check digit."""
    try:
        expected = int(str(expected_digit).strip())
    except (ValueError, TypeError):
        return False
    return compute_mrz_check_digit(field) == expected


def _clean_mrz_lines(raw_text: str) -> list[str]:
    """Extract and sanitize MRZ lines from raw OCR or pasted text.

    Filters for lines containing predominantly uppercase letters, digits, and '<'.
    Minimum 28 characters matches the ICAO TD1 format (shortest standardised MRZ:
    3 lines × 30 chars).
    Crucially, an authentic MRZ line per ICAO Doc 9303 Part 3 ALWAYS utilizes '<'
    filler characters (for blank positions and name separations). Any line with
    zero '<' characters is ordinary English/document text, not an MRZ line.
    """
    lines = []
    for line in (raw_text or "").splitlines():
        cleaned = re.sub(r"[^A-Z0-9<]", "", line.upper().strip())
        if len(cleaned) >= 28 and cleaned.count("<") >= 1:
            lines.append(cleaned)
    return lines


def parse_td3(line1: str, line2: str, allow_correction: bool = True) -> dict[str, Any]:
    """Parse and verify an ICAO TD3 passport MRZ (2 lines x 44 characters).
    
    Line 1 layout:
      0..1: Document code ('P<', 'P', 'PO', etc.)
      2..4: Issuing country / state code (3 chars)
      5..43: Name (Surname<<Given<Names)
    
    Line 2 layout:
      0..8: Document / Passport number (9 chars)
      9: Document number check digit (1 char)
      10..12: Nationality code (3 chars)
      13..18: Date of birth (YYMMDD, 6 chars)
      19: Date of birth check digit (1 char)
      20: Sex ('M', 'F', '<', 'X')
      21..26: Expiry date (YYMMDD, 6 chars)
      27: Expiry date check digit (1 char)
      28..41: Optional personal number (14 chars)
      42: Optional data check digit (or '<' if not used)
      43: Overall composite check digit (1 char)
    """
    l1 = line1.ljust(44, '<')[:44]
    l2 = line2.ljust(44, '<')[:44]

    doc_type = l1[0:2].rstrip('<')
    issuing_country = l1[2:5].rstrip('<')
    name_field = l1[5:44]
    name_parts = name_field.split('<<')
    surname = name_parts[0].replace('<', ' ').strip() if len(name_parts) > 0 else ""
    given_names = name_parts[1].replace('<', ' ').strip() if len(name_parts) > 1 else ""

    doc_number_field = l2[0:9]
    doc_number = doc_number_field.rstrip('<')
    doc_number_ck = l2[9]

    nationality = l2[10:13].rstrip('<')
    dob_field = l2[13:19]
    dob_ck = l2[19]
    sex = l2[20]
    expiry_field = l2[21:27]
    expiry_ck = l2[27]

    optional_field = l2[28:42]
    optional_ck = l2[42]
    composite_ck = l2[43]

    # Verify individual checksums
    doc_num_valid = verify_check_digit(doc_number_field, doc_number_ck)
    dob_valid = verify_check_digit(dob_field, dob_ck)
    expiry_valid = verify_check_digit(expiry_field, expiry_ck)

    optional_valid: bool | None = None
    if optional_ck.isdigit():
        optional_valid = verify_check_digit(optional_field, optional_ck)

    # Composite check digit calculation:
    # Over: doc_number(9) + doc_number_ck(1) + optional(14) + dob(6) + dob_ck(1) + expiry(6) + expiry_ck(1) + optional_ck(1)
    composite_payload = doc_number_field + doc_number_ck + dob_field + dob_ck + expiry_field + expiry_ck + optional_field + optional_ck
    
    if composite_ck.isdigit():
        composite_valid = verify_check_digit(composite_payload, composite_ck)
        is_valid = doc_num_valid and dob_valid and expiry_valid and composite_valid
    else:
        composite_valid = None
        # When composite digit is not present (e.g. truncated line or '<' filler), core fields decide validity
        is_valid = doc_num_valid and dob_valid and expiry_valid

    if not is_valid and allow_correction:
        corr_l2 = correct_td3_line2(l2)
        if corr_l2 != l2:
            corr_res = parse_td3(line1, corr_l2, allow_correction=False)
            if corr_res.get("valid"):
                corr_res["corrected"] = True
                return corr_res

    return {
        "format": "TD3",
        "valid": is_valid,
        "doc_type": doc_type,
        "issuing_country": issuing_country,
        "passport_number": doc_number,
        "surname": surname,
        "given_names": given_names,
        "nationality": nationality,
        "dob": dob_field,
        "sex": sex if sex in ('M', 'F', 'X') else "U",
        "expiry": expiry_field,
        "optional_data": optional_field.rstrip('<'),
        "checks": {
            "document_number": {
                "ok": doc_num_valid,
                "computed": compute_mrz_check_digit(doc_number_field),
                "expected": int(doc_number_ck) if doc_number_ck.isdigit() else doc_number_ck,
            },
            "dob": {
                "ok": dob_valid,
                "computed": compute_mrz_check_digit(dob_field),
                "expected": int(dob_ck) if dob_ck.isdigit() else dob_ck,
            },
            "expiry": {
                "ok": expiry_valid,
                "computed": compute_mrz_check_digit(expiry_field),
                "expected": int(expiry_ck) if expiry_ck.isdigit() else expiry_ck,
            },
            "optional_data": {
                "ok": optional_valid,
                "computed": compute_mrz_check_digit(optional_field) if optional_ck.isdigit() else None,
                "expected": int(optional_ck) if optional_ck.isdigit() else None,
            },
            "composite": {
                "ok": composite_valid,
                "computed": compute_mrz_check_digit(composite_payload),
                "expected": int(composite_ck) if composite_ck.isdigit() else composite_ck,
            },
        },
    }


def parse_td1(line1: str, line2: str, line3: str, allow_correction: bool = True) -> dict[str, Any]:
    """Parse and verify an ICAO TD1 ID card MRZ (3 lines x 30 characters)."""
    l1 = line1.ljust(30, '<')[:30]
    l2 = line2.ljust(30, '<')[:30]
    l3 = line3.ljust(30, '<')[:30]

    doc_type = l1[0:2].rstrip('<')
    issuing_country = l1[2:5].rstrip('<')
    doc_number_field = l1[5:14]
    doc_number = doc_number_field.rstrip('<')
    doc_number_ck = l1[14]
    optional1 = l1[15:30]

    dob_field = l2[0:6]
    dob_ck = l2[6]
    sex = l2[7]
    expiry_field = l2[8:14]
    expiry_ck = l2[14]
    nationality = l2[15:18].rstrip('<')
    optional2 = l2[18:29]
    composite_ck = l2[29]

    name_parts = l3.split('<<')
    surname = name_parts[0].replace('<', ' ').strip() if len(name_parts) > 0 else ""
    given_names = name_parts[1].replace('<', ' ').strip() if len(name_parts) > 1 else ""

    doc_num_valid = verify_check_digit(doc_number_field, doc_number_ck)
    dob_valid = verify_check_digit(dob_field, dob_ck)
    expiry_valid = verify_check_digit(expiry_field, expiry_ck)

    composite_payload = l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29]
    composite_valid = verify_check_digit(composite_payload, composite_ck)

    is_valid = doc_num_valid and dob_valid and expiry_valid and composite_valid

    if not is_valid and allow_correction:
        c1, c2 = correct_td1_lines(l1, l2)
        if (c1, c2) != (l1, l2):
            corr_res = parse_td1(c1, c2, l3, allow_correction=False)
            if corr_res.get("valid"):
                corr_res["corrected"] = True
                return corr_res

    return {
        "format": "TD1",
        "valid": is_valid,
        "doc_type": doc_type,
        "issuing_country": issuing_country,
        "passport_number": doc_number,
        "surname": surname,
        "given_names": given_names,
        "nationality": nationality,
        "dob": dob_field,
        "sex": sex if sex in ('M', 'F', 'X') else "U",
        "expiry": expiry_field,
        "optional_data": (optional1 + optional2).rstrip('<'),
        "checks": {
            "document_number": {
                "ok": doc_num_valid,
                "computed": compute_mrz_check_digit(doc_number_field),
                "expected": int(doc_number_ck) if doc_number_ck.isdigit() else doc_number_ck,
            },
            "dob": {
                "ok": dob_valid,
                "computed": compute_mrz_check_digit(dob_field),
                "expected": int(dob_ck) if dob_ck.isdigit() else dob_ck,
            },
            "expiry": {
                "ok": expiry_valid,
                "computed": compute_mrz_check_digit(expiry_field),
                "expected": int(expiry_ck) if expiry_ck.isdigit() else expiry_ck,
            },
            "composite": {
                "ok": composite_valid,
                "computed": compute_mrz_check_digit(composite_payload),
                "expected": int(composite_ck) if composite_ck.isdigit() else composite_ck,
            },
        },
    }


def parse_td2(line1: str, line2: str, allow_correction: bool = True) -> dict[str, Any]:
    """Parse and verify an ICAO TD2 MRZ (2 lines x 36 characters)."""
    l1 = line1.ljust(36, '<')[:36]
    l2 = line2.ljust(36, '<')[:36]

    doc_type = l1[0:2].rstrip('<')
    issuing_country = l1[2:5].rstrip('<')
    name_parts = l1[5:36].split('<<')
    surname = name_parts[0].replace('<', ' ').strip() if len(name_parts) > 0 else ""
    given_names = name_parts[1].replace('<', ' ').strip() if len(name_parts) > 1 else ""

    doc_number_field = l2[0:9]
    doc_number = doc_number_field.rstrip('<')
    doc_number_ck = l2[9]
    nationality = l2[10:13].rstrip('<')
    dob_field = l2[13:19]
    dob_ck = l2[19]
    sex = l2[20]
    expiry_field = l2[21:27]
    expiry_ck = l2[27]
    optional = l2[28:35]
    composite_ck = l2[35]

    doc_num_valid = verify_check_digit(doc_number_field, doc_number_ck)
    dob_valid = verify_check_digit(dob_field, dob_ck)
    expiry_valid = verify_check_digit(expiry_field, expiry_ck)

    composite_payload = doc_number_field + doc_number_ck + dob_field + dob_ck + expiry_field + expiry_ck + optional
    composite_valid = verify_check_digit(composite_payload, composite_ck)

    is_valid = doc_num_valid and dob_valid and expiry_valid and composite_valid

    if not is_valid and allow_correction:
        c2 = correct_td2_line2(l2)
        if c2 != l2:
            corr_res = parse_td2(l1, c2, allow_correction=False)
            if corr_res.get("valid"):
                corr_res["corrected"] = True
                return corr_res

    return {
        "format": "TD2",
        "valid": is_valid,
        "doc_type": doc_type,
        "issuing_country": issuing_country,
        "passport_number": doc_number,
        "surname": surname,
        "given_names": given_names,
        "nationality": nationality,
        "dob": dob_field,
        "sex": sex if sex in ('M', 'F', 'X') else "U",
        "expiry": expiry_field,
        "optional_data": optional.rstrip('<'),
        "checks": {
            "document_number": {
                "ok": doc_num_valid,
                "computed": compute_mrz_check_digit(doc_number_field),
                "expected": int(doc_number_ck) if doc_number_ck.isdigit() else doc_number_ck,
            },
            "dob": {
                "ok": dob_valid,
                "computed": compute_mrz_check_digit(dob_field),
                "expected": int(dob_ck) if dob_ck.isdigit() else dob_ck,
            },
            "expiry": {
                "ok": expiry_valid,
                "computed": compute_mrz_check_digit(expiry_field),
                "expected": int(expiry_ck) if expiry_ck.isdigit() else expiry_ck,
            },
            "composite": {
                "ok": composite_valid,
                "computed": compute_mrz_check_digit(composite_payload),
                "expected": int(composite_ck) if composite_ck.isdigit() else composite_ck,
            },
        },
    }


def parse_td3_line2(line2: str, allow_correction: bool = True) -> dict[str, Any]:
    """Parse and verify TD3 Line 2 alone (common when only check-digit line is provided)."""
    l2 = line2.ljust(44, '<')[:44]
    doc_number_field = l2[0:9]
    doc_number = doc_number_field.rstrip('<')
    doc_number_ck = l2[9]
    nationality = l2[10:13].rstrip('<')
    dob_field = l2[13:19]
    dob_ck = l2[19]
    sex = l2[20]
    expiry_field = l2[21:27]
    expiry_ck = l2[27]
    optional_field = l2[28:42]
    optional_ck = l2[42]
    composite_ck = l2[43]

    doc_num_valid = verify_check_digit(doc_number_field, doc_number_ck)
    dob_valid = verify_check_digit(dob_field, dob_ck)
    expiry_valid = verify_check_digit(expiry_field, expiry_ck)

    composite_valid = None
    if composite_ck.isdigit():
        composite_payload = doc_number_field + doc_number_ck + dob_field + dob_ck + expiry_field + expiry_ck + optional_field + optional_ck
        composite_valid = verify_check_digit(composite_payload, composite_ck)

    is_valid = doc_num_valid and dob_valid and expiry_valid and (composite_valid is not False)

    if not is_valid and allow_correction:
        c2 = correct_td3_line2(l2)
        if c2 != l2:
            corr_res = parse_td3_line2(c2, allow_correction=False)
            if corr_res.get("valid"):
                corr_res["corrected"] = True
                return corr_res

    return {
        "format": "TD3",
        "valid": is_valid,
        "doc_type": "P",
        "issuing_country": nationality or "IND",
        "passport_number": doc_number,
        "surname": "",
        "given_names": "",
        "nationality": nationality,
        "dob": dob_field,
        "sex": sex if sex in ('M', 'F', 'X') else "U",
        "expiry": expiry_field,
        "optional_data": optional_field.rstrip('<'),
        "checks": {
            "document_number": {
                "ok": doc_num_valid,
                "computed": compute_mrz_check_digit(doc_number_field),
                "expected": int(doc_number_ck) if doc_number_ck.isdigit() else doc_number_ck,
            },
            "dob": {
                "ok": dob_valid,
                "computed": compute_mrz_check_digit(dob_field),
                "expected": int(dob_ck) if dob_ck.isdigit() else dob_ck,
            },
            "expiry": {
                "ok": expiry_valid,
                "computed": compute_mrz_check_digit(expiry_field),
                "expected": int(expiry_ck) if expiry_ck.isdigit() else expiry_ck,
            },
            "composite": {
                "ok": composite_valid,
                "computed": compute_mrz_check_digit(doc_number_field + doc_number_ck + dob_field + dob_ck + expiry_field + expiry_ck + optional_field + optional_ck) if composite_ck.isdigit() else None,
                "expected": int(composite_ck) if composite_ck.isdigit() else None,
            },
        },
    }


def parse_mrz(raw_text: str) -> dict[str, Any]:
    """Auto-detect format (TD1, TD2, TD3) and parse MRZ lines."""
    lines = _clean_mrz_lines(raw_text)
    if not lines:
        return {"valid": False, "error": "No MRZ lines found in input text."}

    # TD1 detection: 3 lines each around 30 characters
    if len(lines) >= 3 and all(28 <= len(ln) <= 32 for ln in lines[-3:]):
        res = parse_td1(lines[-3], lines[-2], lines[-1])
        if res.get("valid"):
            return res

    # TD3 detection: 2 lines each around 44 characters
    if len(lines) >= 2 and any(42 <= len(line) <= 46 for line in lines):
        cand = [line for line in lines if len(line) >= 42]
        if len(cand) >= 2:
            res = parse_td3(cand[-2], cand[-1])
            if res.get("valid"):
                return res

    # TD2 detection: 2 lines each around 36 characters
    if len(lines) >= 2 and any(34 <= len(line) <= 38 for line in lines):
        cand = [line for line in lines if 34 <= len(line) <= 40]
        if len(cand) >= 2:
            res = parse_td2(cand[-2], cand[-1])
            if res.get("valid"):
                return res

    # Exhaustive pair search across candidate lines
    if len(lines) >= 2:
        for i in range(len(lines)):
            for j in range(len(lines)):
                if i == j:
                    continue
                # Try TD3 pair
                p_res = parse_td3(lines[i], lines[j])
                if p_res.get("valid"):
                    return p_res
                # Try TD2 pair
                p2_res = parse_td2(lines[i], lines[j])
                if p2_res.get("valid"):
                    return p2_res

    # Try last two lines fallback
    if len(lines) >= 2:
        res = parse_td3(lines[-2], lines[-1])
        if res.get("valid"):
            return res
        res2 = parse_td2(lines[-2], lines[-1])
        if res2.get("valid"):
            return res2
        if lines[-2].count("<") >= 2 and lines[-1].count("<") >= 2:
            return res

    # Single-line MRZ fallback (e.g. TD3 Line 2 alone)
    for l in lines:
        if len(l) >= 26:
            res = parse_td3_line2(l)
            if res.get("valid"):
                return res

    if len(lines) == 1 and len(lines[0]) >= 26:
        res = parse_td3_line2(lines[0])
        if res.get("valid") or lines[0].count("<") >= 3:
            return res
        return {"valid": False, "error": "Single line lacks valid check digits or MRZ filler"}

    return {"valid": False, "error": f"Incomplete MRZ lines ({len(lines)} line(s) found)."}
