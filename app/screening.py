"""
MHA identity-document screening pipeline — SIH 2026 PS SIH26188.

"AI-Based Fake Identity and Document Screening System" (Ministry of Home
Affairs). The flow is the statement's own: Upload -> Extract -> Analyze ->
Verify -> Assess Risk. Every conclusion is *explainable*: each risk point
carries a human-readable reason, the same file is cross-referenced against
the watchlist AND the AI detectors, and the system keeps an audit trail
while storing ZERO raw document bytes or text (only SHA-256 hashes,
masked identifiers, and explainable signals — same zero-storage philosophy
as the rest of nocap).

Identifier validation is deliberately deterministic and transparent (checksum
+ format rules) so screening works offline, explains itself to a human
reviewer, and stays open to every downstream model later swapped in.
"""

import hashlib
import json
import re
import time
import unicodedata
import uuid

# AI-detection + document-awareness live inside app/main.py (single-file
# backend). They are imported lazily inside run_screening() at call time, so
# main.py -> screening.py -> main.py circular import is avoided.

# --------------------------------------------------------------------------- #
# Identifier normalization & masks
# --------------------------------------------------------------------------- #

_PUNCT = str.maketrans("", "", " -/\\._:()")


def norm(value):
    """Collapse spaces/punctuation and uppercase — 'ka-01/2020/1234567' vs
    'KA 012020 1234567' must match as the same identifier."""
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return ""
    return unicodedata.normalize("NFKC", value).translate(_PUNCT).strip().upper()


def mask(value: str, keep: int = 4) -> str:
    """Display-safe mask: keep only the last `keep` characters."""
    v = norm(value)
    return ("*" * (len(v) - keep)) + v[-keep:] if len(v) > keep else v


def sha256(value: str) -> str:
    return hashlib.sha256(norm(value).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """SHA-256 digest of raw bytes — used for file-hash fingerprinting."""
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Checksum utilities (deterministic, explainable)
# --------------------------------------------------------------------------- #

def mrz_checkdigit(field: str) -> int:
    """ICAO 9303 check digit over an MRZ field (weights 7,3,1 repeating)."""
    weights = (7, 3, 1)
    total = 0
    for i, ch in enumerate(field):
        if ch == "<":
            v = 0
        elif ch.isdigit():
            v = ord(ch) - 48
        else:
            v = ord(ch) - 55  # A=10 .. Z=35
        total += v * weights[i % 3]
    return total % 10


# --------------------------------------------------------------------------- #
# Field extraction (regex + checksums over pdf text and declared fields)
# --------------------------------------------------------------------------- #

_PAN_RE = re.compile(r"\b[A-Za-z]{5}\s*[0-9]{4}\s*[A-Za-z]\b")
_PAN_CATEGORY = set("ABCDFGHLJPT")
_DL_RE = re.compile(r"\b[A-Za-z]{2}[- ]*\d{2}[- ]*\d{4}[- ]*\d{7}\b|\b[A-Za-z]{2}[- ]*\d{13,14}\b")
_AADHAAR_RE = re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")
# Passport numbers on Indian/ICAO documents come in two shapes: the classic
# 9-char "1 letter + 6 digits + 1 letter" (e.g. L898902C — the ICAO Doc 9303
# specimen) and the shorter 8-char "1 letter + 7 digits" (e.g. P9876543).
# Only the 8-char form matched before, silently failing to extract the
# standard 9-char format from declared values and OCR text.
_PASSPORT_LITE_RE = re.compile(r"\b[A-Z][0-9]{6,7}[A-Z]?\b")
_EPIC_RE = re.compile(r"\b[A-Z]{3}\s*\d{7}\b")
_PHONE_RE = re.compile(r"\b[6-9]\d{9}(?![0-9])")
_DOB_RE = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b|\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_EXP_RE = re.compile(r"(?i)(?:VALID\s*(?:TILL|UPTO|THRU|TO)|EXPIRY(?:\s*DATE)?|EXP)[:\s]+(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})")
_PIN_RE = re.compile(r"\b([1-9][0-9]{5})\b")
_ADDR_RE = re.compile(r"(?i)(?:Address|पता|Res|Residence)[:\s\n]+([A-Za-z0-9, \-/\n]{10,120})")
_MRZ_LINE2_RE = re.compile(r"([A-Z0-9<]{9})(\d)([A-Z<]{3})(\d{6})(\d)([A-Z<]{1})(\d{6})(\d)[A-Z0-9<]*")


def _days_in_month(m: int, y: int) -> int:
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
    return 29 if leap else 28


def _valid_date(y: int, m: int, d: int) -> bool:
    if not (1900 <= y <= 9999) or not (1 <= m <= 12) or d < 1:
        return False
    return d <= _days_in_month(m, y)


def _first_date(text: str) -> str | None:
    """Best DOB candidate as YYYY-MM-DD.

    A printed identity document carries several dates — issue, expiry, DOB.
    The DOB is the OLDEST and must lie in the past, so pick the oldest
    plausible date instead of the first one; otherwise an expiry printed
    before the DOB ("VALID TILL: 31-12-2031 / DOB: 15-08-1990") is mistaken
    for a future date of birth and adds a false +30 risk. When nothing is in
    the past (a pure future-date scan), fall back to the first date so the
    future-DOB signal can still fire."""
    picks = []
    # 1. Standard separated dates: 15/08/1990, 15-08-1990, 15.08.1990, 15 08 1990
    for m in re.finditer(r"\b([0-3]?[0-9])[\s\-_./]+([0-1]?[0-9])[\s\-_./]+((?:19|20)\d{2})\b", text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(y, mo, d):
            picks.append((y, mo, d))
    # 2. ISO format: 1990-08-15
    for m in re.finditer(r"\b((?:19|20)\d{2})[\s\-_./]+([0-1]?[0-9])[\s\-_./]+([0-3]?[0-9])\b", text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(y, mo, d):
            picks.append((y, mo, d))
    # 3. OCR glued format: 1508/1990 or 15/081990
    for m in re.finditer(r"\b([0-3][0-9])([0-1][0-9])[\s\-_./]+((?:19|20)\d{2})\b", text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(y, mo, d):
            picks.append((y, mo, d))
    if not picks:
        return None
    y, mo, d = min(picks)
    if (y, mo, d) <= tuple(int(x) for x in _today().split("-")):
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return f"{picks[0][0]:04d}-{picks[0][1]:02d}-{picks[0][2]:02d}"


def extract_mrz(text: str) -> dict:
    """Parse an ICAO TD3 MRZ (passport). Validates passport/DOB/expiry
    check digits — a tampered or photoshopped zone fails these."""
    out = {}
    for m in _MRZ_LINE2_RE.finditer(text):
        pno, ck_p, _nat, dob, ck_d, _sex, exp, ck_e = m.groups()
        if not pno.rstrip("<"):
            continue  # a number field that is all '<' filler is not a passport
        pno_ok = mrz_checkdigit(pno) == int(ck_p)
        dob_ok = mrz_checkdigit(dob) == int(ck_d)
        exp_ok = mrz_checkdigit(exp) == int(ck_e)
        out = {
            "passport": pno.rstrip("<"),   # drop ICAO '<' filler before masking/hashing
            "mrz_dob": dob,
            "mrz_passport_ck": pno_ok,
            "mrz_dob_ck": dob_ok,
            "mrz_expiry_ck": exp_ok,
            "mrz_valid": pno_ok and dob_ok and exp_ok,
        }
        if out.get("mrz_valid"):
            break  # first structurally valid MRZ wins
    return out


def _find_pan_robust(source: str) -> str | None:
    """Extract 10-char PAN with OCR confusion error-correction (e.g. 0/O, 1/I, 5/S, R/P).
    Validates that the 4th character is a legitimate ITD entity category (ABCDFGHLJPT)."""
    # 1. Direct standard regex (ignoring whitespace/hyphens)
    m = _PAN_RE.search(source)
    if m:
        clean = re.sub(r"\s+", "", m.group(0)).upper()
        if len(clean) == 10:
            if clean[3] in _PAN_CATEGORY:
                return clean
            if clean[3] == "R":
                return f"{clean[:3]}P{clean[4:]}"
    # 2. Match PAN with spaces/hyphens between segments (e.g. ABCDE 1234 F or ABCDE-1234-F)
    m_seg = re.search(r"\b([A-Za-z]{5})[\s\-_.:]*([0-9]{4})[\s\-_.:]*([A-Za-z])\b", source)
    if m_seg:
        cand = f"{m_seg.group(1).upper()}{m_seg.group(2)}{m_seg.group(3).upper()}"
        if len(cand) == 10:
            if cand[3] in _PAN_CATEGORY:
                return cand
            if cand[3] == "R":
                return f"{cand[:3]}P{cand[4:]}"
    # 3. Token scan for 10-char sequences with OCR character confusions
    tokens = re.findall(r"\b[A-Za-z0-9]{5}[\s\-_.:]*[A-Za-z0-9]{4}[\s\-_.:]*[A-Za-z0-9]\b", source)
    digit_map = {"O": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "A": "4", "T": "7", "b": "6", "q": "9", "g": "9"}
    letter_map = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G", "4": "A", "7": "T"}
    for t in tokens:
        cand = re.sub(r"[\s\-_.:]+", "", t).upper()
        if len(cand) == 10:
            f5 = "".join(letter_map.get(c, c) if not c.isalpha() else c for c in cand[:5])
            m4 = "".join(digit_map.get(c, c) if not c.isdigit() else c for c in cand[5:9])
            l1 = letter_map.get(cand[9], cand[9]) if not cand[9].isalpha() else cand[9]
            if f5[3] == "R":
                f5 = f5[:3] + "P" + f5[4:]
            bad_pan_prefixes = {"BIRTH", "INDIA", "VALID", "STATE", "UNION", "ISSUE", "TOTAL", "ORDER", "MONTH", "FIRST", "NORTH", "SOUTH", "UNDER"}
            if f5 in bad_pan_prefixes:
                continue
            if f5.isalpha() and m4.isdigit() and l1.isalpha():
                if f5[3] in _PAN_CATEGORY:
                    return f"{f5}{m4}{l1}"
    return None


def _find_aadhaar_robust(source: str) -> str | None:
    """Extract 12-digit Aadhaar UIDAI number, standard or spaced/dashed."""
    m = re.search(r"\b([2-9]\d{3})[ -]?(\d{4})[ -]?(\d{4})\b", source)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    # Handle OCR substitution in 4-digit groups (e.g. S instead of 5, O instead of 0)
    for cand in re.finditer(r"\b([A-Za-z0-9]{4})[ -]([A-Za-z0-9]{4})[ -]([A-Za-z0-9]{4})\b", source):
        raw = cand.group(1) + cand.group(2) + cand.group(3)
        digit_map = {"O": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}
        digits = "".join(digit_map.get(c.upper(), c) for c in raw)
        if len(digits) == 12 and digits.isdigit() and digits[0] not in ("0", "1"):
            return digits
    return None


def _find_dl_robust(source: str) -> str | None:
    """Extract Indian Driving Licence number across all state RTO formats."""
    # Standard format: State(2) + RTO(2) + Year(4 opt) + Serial(7)
    m = re.search(r"\b([A-Za-z]{2})[- /]*(\d{2})[- /]*((?:19|20)\d{2})?[- /]*(\d{7})\b", source)
    if m:
        st, rto, yr, num = m.groups()
        if yr:
            return f"{st.upper()}{rto}{yr}{num}"
        return f"{st.upper()}{rto}{num}"
    # Generic DL match: 2 letters + 13-14 digits
    m2 = re.search(r"\b([A-Za-z]{2})[- /]*(\d{13,14})\b", source)
    if m2:
        return f"{m2.group(1).upper()}{m2.group(2)}"
    return None


def _find_passport_robust(source: str) -> str | None:
    """Extract passport number: from MRZ blocks, labeled passport numbers, or standard series."""
    try:
        from app.mrz import parse_mrz
    except ImportError:
        try:
            from mrz import parse_mrz
        except ImportError:
            parse_mrz = None
    if parse_mrz is not None:
        try:
            mrz_res = parse_mrz(source)
            if mrz_res and mrz_res.get("passport_number"):
                pno = mrz_res["passport_number"].strip("<").strip()
                if len(pno) >= 6:
                    return pno
        except Exception:
            pass

    m_label = re.search(r"(?:PASSPORT\s*(?:NO|NUMBER|#)?|DOC\s*(?:NO|NUMBER))\s*[:\.\s\-]*([A-Z0-9]{7,9})\b", source, re.IGNORECASE)
    if m_label:
        cand = m_label.group(1).upper()
        if not cand.isdigit() and any(c.isdigit() for c in cand):
            return cand

    m_ind = re.search(r"\b([A-PR-WYa-pr-wy][0-9]{7}|[A-PR-WYa-pr-wy][0-9]{6}[A-Za-z])\b", source)
    if m_ind:
        return m_ind.group(1).upper()

    for cand in set(_PASSPORT_LITE_RE.findall(source)):
        return cand.upper()
    return None


def _match_identifiers(source: str) -> dict:
    """Run the identifier regexes over one text variant; first valid wins."""
    hits = {}
    pan = _find_pan_robust(source)
    if pan:
        hits["pan"] = pan
    dl = _find_dl_robust(source)
    if dl:
        hits["driving_licence"] = dl
    p_no = _find_passport_robust(source)
    if p_no:
        hits["passport"] = p_no
    for cand in set(_EPIC_RE.findall(source)):
        hits["voter_id"] = re.sub(r"\s+", "", cand).upper()  # EPIC: 3 letters + 7 digits
        break
    for cand in set(_PHONE_RE.findall(source)):
        hits["phone"] = cand
        break
    aadh = _find_aadhaar_robust(source)
    if aadh:
        hits["aadhaar"] = aadh
    return hits


_COMMON_SURNAMES = (
    "SATAPATHY", "SATPATHY", "SHARMA", "KUMAR", "SINGH", "PATEL", "GUPTA", "VERMA", "JOSHI",
    "REDDY", "RAO", "NAIR", "DAS", "MISHRA", "MOHAPATRA", "PANDA", "PRADHAN", "ROUT", "SAHOO",
    "BEHERA", "NAYAK", "KHAN", "ALI", "CHOUDHURY", "CHOWDHURY", "ROY", "SEN", "BANERJEE",
    "MUKHERJEE", "CHATTERJEE", "DUTTA", "BOSE", "GHOSE", "GHOSH", "AGRAWAL", "AGARWAL",
    "JAIN", "MEHTA", "SHAH", "YADAV", "TIWARI", "PANDEY", "DUBEY", "TRIPATHI", "CHAUHAN",
    "THAKUR", "SHUKLA", "BHAT", "BHATT", "DESHMUKH", "PATIL", "KULKARNI", "PAWAR", "SHINDE"
)

def _format_glued_name(raw: str) -> str:
    s = raw.strip()
    if " " in s:
        return s
    up = s.upper()
    for sur in _COMMON_SURNAMES:
        if up.endswith(sur) and len(up) > len(sur):
            first = up[:-len(sur)].strip()
            if len(first) >= 2:
                if s.isupper():
                    return f"{first} {sur}"
                return f"{first.title()} {sur.title()}"
    return s


def extract_fields(text: str, doc_type: str = "") -> dict:
    """Deterministic extraction of Indian identity identifiers from text.
    Returns only validated/masked-able raw values plus explainable flags."""
    text = unicodedata.normalize("NFKC", text or "")
    clean = norm(text)
    spaced = re.sub(r"(?i)(?<=[a-z])(?=\d)", " ", clean)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    found = {"pan": None, "driving_licence": None,
             "passport": None, "voter_id": None, "phone": None,
             "dob": None, "aadhaar": None, "name": None, "gender": None,
             "expiry": None, "pincode": None, "address": None, "state": None}
    for src in (text, clean, spaced):
        for key, val in _match_identifiers(src).items():
            if val and not found.get(key):
                found[key] = val

    dob = _first_date(text)
    if dob:
        found["dob"] = dob

    # Extract expiry date if present
    exp_m = _EXP_RE.search(text)
    if exp_m:
        raw_e = exp_m.group(1)
        parsed_e = _parse_date(raw_e)
        if parsed_e:
            found["expiry"] = f"{parsed_e[0]:04d}-{parsed_e[1]:02d}-{parsed_e[2]:02d}"

    # Extract pincode if present
    pin_m = _PIN_RE.search(text)
    if pin_m:
        found["pincode"] = pin_m.group(1)

    # Extract address snippet if present (filter out informational/policy text)
    addr_policy_noise = ("UPDATED IN", "SUPPORT IDENTITY", "PROOF OF IDENTITY", "AVAIL OF", "DATE OF ENROLMENT", "DOWNLOAD MAADHAAR")
    for addr_cand in _ADDR_RE.finditer(text):
        cand_str = re.sub(r"\s+", " ", addr_cand.group(1)).strip()
        cand_str = re.sub(r"(?i)\s*(?:Aadhaar|Aadhar)\s+is\s+proof.*", "", cand_str).strip()
        if not any(noise in cand_str.upper() for noise in addr_policy_noise) and len(cand_str) >= 8:
            found["address"] = cand_str[:140]
            break

    # Look for address lines starting with Plot/House/Street/Sahid Nagar/etc. if _ADDR_RE didn't match
    if not found.get("address"):
        addr_cands = []
        for ln in lines:
            up = ln.upper()
            if any(k in up for k in ("PLOT", "HOUSE", "STREET", "ROAD", "SAHID NAGAR", "NAGAR", "VTC:", "DISTRICT:", "DIST:")) and not any(noise in up for noise in addr_policy_noise):
                cleaned_ln = re.sub(r"(?i)\s*(?:Aadhaar|Aadhar)\s+is\s+proof.*", "", ln).strip()
                if cleaned_ln:
                    addr_cands.append(cleaned_ln)
        if addr_cands:
            found["address"] = ", ".join(addr_cands[:3])[:140]

    # Suppress cross-document barcode noise (e.g. UIDAI letter tracking codes matching EPIC voter_id regex)
    doc_norm = (doc_type or "").lower().strip()
    if doc_norm in ("aadhaar", "aadhaar_card", "aadhar", "pan", "passport", "visa") and found.get("voter_id"):
        if doc_norm in ("aadhaar", "aadhaar_card", "aadhar") and not any(v in text.upper() for v in ("ELECTION", "VOTER", "EPIC")):
            found["voter_id"] = None
        elif doc_norm == "pan" and not any(v in text.upper() for v in ("ELECTION", "VOTER", "EPIC")):
            found["voter_id"] = None
    if doc_norm in ("driving_licence", "driving_license", "dl", "rc") and found.get("pan"):
        if not any(k in text.upper() for k in ("PERMANENT ACCOUNT", "PAN NO", "PAN NUMBER", "PAN:")):
            found["pan"] = None

    # Extract state if present in text
    indian_states = ["Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh"]
    for st in indian_states:
        if re.search(rf"\b{re.escape(st)}\b", text, re.IGNORECASE):
            found["state"] = st
            break

    # Extract holder name from text patterns (e.g. "Name: ...", "नाम: ...", "To ...", lines before S/O)
    bad_roots = [
        "INCOME", "TAX", "GOVT", "INDIA", "INDA", "INDAA", "INDIRA", "DEPART", "DEPARTMENT",
        "PERMANENT", "ACCOUNT", "CARD", "SIGN", "DATE", "BIRTH", "BLRTH", "BLTH", "DOB",
        "MALE", "FEMALE", "NUMBER", "AYAKAR", "BHARAT", "GOVERN", "SIGNED", "PHYSIC",
        "APPLIC", "VALID", "UNLESS", "DIGIT", "REPUBLIC", "MINISTRY", "AUTHORITY", "NATIONAL",
        "FATHER", "MOTHER", "HUSBAND", "NAME", "HOLDER", "APLI", "PUD", "HALL", "TION", "DIGI",
        "UIDAI", "ENROLMENT", "ENROLLMENT", "INFORMATION", "AADHAAR", "AADHAR", "UNIQUE",
        "IDENTIFICATION", "VID", "HELP", "WWW", "PLOT", "SAHID", "NAGAR", "DISTRICT", "STATE"
    ]
    vowels = set("AEIOUYaeiouy")

    # Pre-identify lines explicitly adjacent to holder name markers (Name / नाम / Holder)
    name_indices = [idx for idx, l in enumerate(lines) if re.search(r"(?i)\b(?:Name|नाम|Holder)\b", l) and not any(k in l.upper() for k in ("FATHER", "पिता", "PERMANENT", "ACCOUNT", "INCOME", "TAX", "CARD"))]
    holder_cands = set()
    for ni in name_indices:
        for off in (1, -1, 2):
            if 0 <= ni + off < len(lines):
                c_up = re.sub(r"[^A-Za-z ]", " ", lines[ni + off]).strip().upper()
                c_up = re.sub(r"\s+", " ", c_up)
                if c_up and not any(bad in c_up for bad in ("INCOME", "TAX", "PERMANENT", "ACCOUNT", "CARD")):
                    holder_cands.add(c_up)

    # Find father's name / guardian name if explicitly labeled
    father_cands = set()
    for i, ln in enumerate(lines):
        up = ln.upper()
        if any(k in up for k in ("FATHER", "पिता", "S/O", "D/O", "W/O", "C/O")) and not any(k in up for k in ("INCOME", "TAX", "CARD", "PERMANENT")):
            for offset in (0, 1, 2, -1):
                idx = i + offset
                if 0 <= idx < len(lines):
                    cand_ln = lines[idx]
                    if offset == 0:
                        m_f = re.search(r"(?i)(?:Father(?:'s)?\s*Name|पिता(?: का)?\s*नाम|(?:S|D|W|C)/O)[:\s.\-_/]+([A-Za-z ]{3,50})", cand_ln)
                        if m_f:
                            cand_ln = m_f.group(1)
                    raw_c = re.sub(r"[^A-Za-z ]", " ", cand_ln).strip()
                    raw_c = re.sub(r"\s+", " ", raw_c)
                    if len(raw_c) >= 3 and not any(b in raw_c.upper() for b in ("FATHER", "NAME", "पिता", "SIGN", "VALID", "GOVT", "INCOME", "TAX")):
                        fmt_f = _format_glued_name(raw_c)
                        if fmt_f.upper() not in holder_cands and raw_c.upper() not in holder_cands:
                            father_cands.add(fmt_f.upper())

    # 1. Line immediately preceding S/O or D/O or W/O or C/O (e.g. Asutosh Nayak \n S/O ...)
    for i, ln in enumerate(lines):
        up = ln.upper()
        if any(k in up for k in ("S/O", "D/O", "W/O", "C/O")) and not any(k in up for k in ("INCOME", "TAX", "CARD")):
            for prev_offset in (1, 2):
                if i - prev_offset >= 0:
                    prev_ln = lines[i - prev_offset].strip()
                    raw_c = re.sub(r"[^A-Za-z ]", " ", prev_ln).strip()
                    raw_c = re.sub(r"\s+", " ", raw_c)
                    up_prev = raw_c.upper()
                    if raw_c and len(raw_c) >= 3 and not any(bad in up_prev for bad in bad_roots):
                        fmt = _format_glued_name(raw_c)
                        words = [w for w in fmt.split() if w.isalpha() and 2 <= len(w) <= 20]
                        if 1 <= len(words) <= 4 and all(any(c in vowels for c in w) for w in words):
                            found["name"] = fmt[:80]
                            break
            if found.get("name"):
                break

    # 2. Aadhaar Letter "To <Name>" pattern
    if not found.get("name"):
        for i, ln in enumerate(lines):
            if ln.strip().upper() == "TO" or ln.strip().upper().startswith("TO "):
                for offset in (1, 2, 3):
                    if i + offset < len(lines):
                        cand_ln = lines[i + offset].strip()
                        raw_c = re.sub(r"[^A-Za-z ]", " ", cand_ln).strip()
                        raw_c = re.sub(r"\s+", " ", raw_c)
                        up = raw_c.upper()
                        if raw_c and len(raw_c) >= 3 and not any(bad in up for bad in bad_roots):
                            fmt = _format_glued_name(raw_c)
                            words = [w for w in fmt.split() if w.isalpha() and 2 <= len(w) <= 20]
                            if 1 <= len(words) <= 4 and all(any(c in vowels for c in w) for w in words) and fmt.upper() not in father_cands:
                                found["name"] = fmt[:80]
                                break
                if found.get("name"):
                    break

    # 3. Label on same line or immediate next/previous line around Name / नाम (with strict word boundaries)
    if not found.get("name"):
        for i, ln in enumerate(lines):
            up = ln.upper()
            # Same-line match: Name: ...
            m_same = re.search(r"(?i)\b(?:Name|नाम|Holder(?:'s)?\s*Name|Applicant|कार्डधारक)\b[:\s.\-_/]+([A-Za-z ]{3,50})", ln)
            if m_same and not any(k in up for k in ("FATHER", "पिता", "PERMANENT", "ACCOUNT", "INCOME", "TAX", "CARD")):
                cand = re.sub(r"\s+", " ", m_same.group(1)).strip()
                cand_up = cand.upper()
                if not any(bad in cand_up for bad in bad_roots):
                    fmt = _format_glued_name(cand)
                    words = [w for w in fmt.split() if w.isalpha() and 2 <= len(w) <= 20]
                    if 1 <= len(words) <= 4 and all(any(c in vowels for c in w) for w in words) and fmt.upper() not in father_cands:
                        found["name"] = fmt[:80]
                        break

            # Line check around Name / नाम (forward offset 1, 2 or previous line -1 for bottom-labeled/inverted layouts)
            if re.search(r"(?i)\b(?:NAME|नाम|HOLDER)\b", ln) and not any(k in up for k in ("FATHER", "पिता", "PERMANENT", "ACCOUNT", "INCOME", "TAX", "CARD")):
                for offset in (1, 2, -1):
                    if 0 <= i + offset < len(lines):
                        next_ln = lines[i + offset].strip()
                        next_up = next_ln.upper()
                        if not any(bad in next_up for bad in bad_roots) and len(next_ln) >= 3:
                            cand = re.sub(r"[^A-Za-z ]", " ", next_ln).strip()
                            cand = re.sub(r"\s+", " ", cand)
                            if cand and not any(bad in cand.upper() for bad in bad_roots):
                                fmt = _format_glued_name(cand)
                                words = [w for w in fmt.split() if w.isalpha() and 2 <= len(w) <= 20]
                                if 1 <= len(words) <= 4 and all(any(c in vowels for c in w) for w in words) and fmt.upper() not in father_cands:
                                    found["name"] = fmt[:80]
                                    break
                if found.get("name"):
                    break

    # 4. PAN Card Specific Layout Scan (below PAN or below Permanent Account Number)
    if not found.get("name") and (doc_norm == "pan" or any("INCOME" in ln.upper() or "PERMANENT" in ln.upper() for ln in lines)):
        for i, ln in enumerate(lines):
            up = ln.upper()
            if any(k in up for k in ("PERMANENT", "ACCOUNT", "INCOME", "TFPPS", "PAN")) or re.search(r"\b[A-Za-z]{5}\s*[0-9]{4}\s*[A-Za-z]\b", ln):
                for offset in (1, 2, 3):
                    if i + offset < len(lines):
                        cand_ln = lines[i + offset].strip()
                        cand_up = cand_ln.upper()
                        if len(cand_ln) >= 4 and not any(bad in cand_up for bad in bad_roots):
                            cand = re.sub(r"[^A-Za-z ]", " ", cand_ln).strip()
                            cand = re.sub(r"\s+", " ", cand)
                            if cand and len(cand) >= 4 and not any(bad in cand.upper() for bad in bad_roots):
                                fmt = _format_glued_name(cand)
                                words = [w for w in fmt.split() if w.isalpha() and 2 <= len(w) <= 20]
                                if 1 <= len(words) <= 4 and any(fmt.upper().endswith(sur) or sur in fmt.upper() for sur in _COMMON_SURNAMES):
                                    found["name"] = fmt[:80]
                                    break
                if found.get("name"):
                    break

    # 5. Scored candidate extraction for PAN and ID cards across all lines
    if not found.get("name") or any(found.get("name", "").upper().endswith(sur) for sur in _COMMON_SURNAMES) is False:
        scored_cands = []
        for ln in lines:
            raw_clean = re.sub(r"[^A-Za-z ]", " ", ln).strip()
            raw_clean = re.sub(r"\s+", " ", raw_clean)
            if len(raw_clean) < 3:
                continue
            up = raw_clean.upper()
            if any(bad in up for bad in bad_roots):
                continue
            fmt = _format_glued_name(raw_clean)
            words = [w for w in fmt.split() if w.isalpha() and 2 <= len(w) <= 20]
            if not (1 <= len(words) <= 4) or any(len(w) > 18 or len(w) < 2 for w in words):
                continue
            if not all(any(c in vowels for c in w) for w in words):
                continue

            score = 0
            if any(fmt.upper().endswith(sur) or sur in fmt.upper() for sur in _COMMON_SURNAMES):
                score += 60
            if len(words) in (2, 3):
                score += 30
            if all(len(w) >= 3 for w in words):
                score += 15
            # All caps on official document
            if raw_clean.isupper():
                score += 10
            # Bonus for candidate lines adjacent to Name markers
            if fmt.upper() in holder_cands or raw_clean.upper() in holder_cands:
                score += 50
            # Non-father preferred
            if fmt.upper() in father_cands or raw_clean.upper() in father_cands:
                score -= 60
            scored_cands.append((score, fmt))

        scored_cands.sort(key=lambda x: x[0], reverse=True)
        if scored_cands and scored_cands[0][0] >= 30:
            found["name"] = scored_cands[0][1][:80]

    # Aadhaar Address block extraction
    if not found.get("address"):
        addr_lines = []
        in_addr = False
        for ln in lines:
            up = ln.upper()
            if "ADDRESS" in up or "पता" in up:
                in_addr = True
                cleaned_ln = re.sub(r"(?i)^(?:Address|पता)[:\s.\-_]+", "", ln).strip()
                if cleaned_ln:
                    addr_lines.append(cleaned_ln)
                continue
            if in_addr:
                if any(k in up for k in ("AADHAAR", "UIDAI", "VID", "1947", "HELP@UIDAI", "WWW.UIDAI", "SIGNATURE", "DIGITALLY SIGNED")):
                    break
                if re.search(r"\b\d{4}\s*\d{4}\s*\d{4}\b", ln):
                    break
                addr_lines.append(ln)
                if re.search(r"\b\d{6}\b", ln) or len(addr_lines) >= 4:
                    break
        if addr_lines:
            found["address"] = re.sub(r"\s+", " ", ", ".join(addr_lines)).strip()[:140]

    # Extract gender if present
    g = re.search(r"\b(MALE|FEMALE|पुरुष|महिला)\b", text, re.IGNORECASE)
    if g:
        found["gender"] = "M" if g.group(1).upper() in ("MALE", "पुरुष") else "F"

    mrz = extract_mrz(text)
    if mrz:
        found["passport"] = mrz.pop("passport", found["passport"])
        found.update(mrz)
        if mrz.get("mrz_valid") and mrz.get("mrz_dob") and not found.get("dob"):
            yymmdd = mrz["mrz_dob"]
            century = "19" if int(yymmdd[:2]) > int(time.strftime("%y")) else "20"
            found["dob"] = f"{century}{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    return found


# --------------------------------------------------------------------------- #
# Risk assessment
# --------------------------------------------------------------------------- #

def _today():
    return time.strftime("%Y-%m-%d")


def _travel_validity(mrz_expiry_yymmdd: str | None,
                     dob: str | None,
                     doc_type: str) -> dict:
    """Return a travel-clearance status block.

    expiry_yymmdd: 6-char ICAO MRZ field (YYMMDD) from the parsed MRZ, or None.
    dob:           ISO date string YYYY-MM-DD, or None.
    Returns a dict with days_to_expiry, six_month_rule, age_at_crossing,
    status ('VALID' | 'EXPIRING_SOON' | 'EXPIRED' | 'UNKNOWN')."""
    from datetime import date
    today = date.today()
    result: dict = {
        "days_to_expiry": None,
        "six_month_rule": None,
        "age_at_crossing": None,
        "status": "UNKNOWN",
        "detail": "Expiry date not available from MRZ.",
    }
    if mrz_expiry_yymmdd and len(mrz_expiry_yymmdd) == 6:
        try:
            yy = int(mrz_expiry_yymmdd[:2])
            mm = int(mrz_expiry_yymmdd[2:4])
            dd = int(mrz_expiry_yymmdd[4:6])
            # ICAO convention: YY >= 30 → 1900s, YY < 30 → 2000s
            year = (2000 + yy) if yy < 30 else (1900 + yy)
            exp_date = date(year, mm, dd)
            days = (exp_date - today).days
            result["days_to_expiry"] = days
            result["six_month_rule"] = days >= 180  # most countries require 6-month buffer
            if days < 0:
                result["status"] = "EXPIRED"
                result["detail"] = (f"Document EXPIRED {abs(days)} day(s) ago "
                                    f"(expiry {exp_date.isoformat()}).")
            elif days < 180:
                result["status"] = "EXPIRING_SOON"
                result["detail"] = (f"Only {days} day(s) until expiry "
                                    f"({exp_date.isoformat()}) — "
                                    "fails the 6-month validity rule for most destinations.")
            else:
                result["status"] = "VALID"
                result["detail"] = (f"Document valid for {days} more day(s) "
                                    f"(expiry {exp_date.isoformat()}).")
        except (ValueError, OverflowError):
            result["detail"] = "Expiry date could not be parsed from MRZ field."

    if dob:
        try:
            dob_date = date.fromisoformat(dob[:10])
            result["age_at_crossing"] = (today - dob_date).days // 365
        except (ValueError, OverflowError):
            pass
    return result


def _parse_date(s: str):
    """Parse an officer-typed date (YYYY-MM-DD or DD-MM-YYYY, separators - / .)
    into a (y, m, d) tuple. Returns None when unparseable — callers SKIP rather
    than mis-verdict on a typo (a lexical string compare would call e.g.
    "31-12-2031" expired because "3" > "2")."""
    if not isinstance(s, str):
        return None
    raw = s.strip()
    if len(raw) == 6 and raw.isdigit():
        yy = int(raw[:2])
        mm = int(raw[2:4])
        dd = int(raw[4:6])
        yyyy = 1900 + yy if yy > 50 else 2000 + yy
        if _valid_date(yyyy, mm, dd):
            return (yyyy, mm, dd)
    parts = re.split(r"[-/.]", raw)
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    a, b, c = (int(p) for p in parts)
    y, m, d = (a, b, c) if len(parts[0]) == 4 else (c, b, a)
    if not _valid_date(y, m, d):
        return None
    return (y, m, d)


def _grade(score: int, hard_flag: bool = False, can_clear: bool = True) -> str:
    if hard_flag or score > 55:
        return "FLAGGED"
    if not can_clear or score > 25:
        return "REVIEW"
    return "CLEAR"


def run_screening(data: bytes, filename: str, doc_type: str | None,
                  checkpoint: str | None, declared: dict | None,
                  screener: str | None = None,
                  live_frame: bytes | None = None,
                  session_id: str | None = None,
                  nationality: str | None = None,
                  purpose: str | None = None,
                  data_back: bytes | None = None,
                  filename_back: str | None = None) -> dict:
    """Full Upload->Extract->Analyze->Verify->AssessRisk pass. Returns a
    report dict AND persists an immutable ScreeningReport row.

    Supports both single-sided and two-sided (front bio page + back address/QR page)
    document verification for Passports, Aadhaar, Voter ID, and Driving Licences.

    The problem statement's four modules run as thin, self-contained passes:
      M1 extraction -> app/extraction.py (OCR/MRZ field extraction)
      M2 validation -> app/validation.py (checksums, format rules, watchlist)
      M3 tampering -> app/tampering.py (ELA, QA, liveness, AI-generation cues)
      M4 face      -> app/face.py (document portrait vs live frame capture)
    Each contributes an explainable `modules` section to the report, alongside
    the existing risk-scoring explained in `reasons`."""
    try:
        from app.main import WatchlistEntry, ScreeningReport
    except ImportError:  # bare-module invocation (tests / direct run)
        from main import WatchlistEntry, ScreeningReport
    from extraction import extract_document
    from validation import validate_document
    from tampering import tamper_analysis
    from face import face_verification

    file_hash = hashlib.sha256(data).hexdigest()
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    started = time.monotonic()

    # ---- Module 1: Extract (OCR/MRZ + declared merge) --------------------------
    extract_res = extract_document(data, filename, doc_type or "", declared)
    fields = extract_res["fields"]

    # If back side is provided (e.g. Passport address page, Aadhaar back, DL back)
    if data_back and len(data_back) > 0:
        extract_back = extract_document(data_back, filename_back or "back.jpg", doc_type or "", declared)
        fields_back = extract_back.get("fields", {})
        for k, v in fields_back.items():
            if k not in fields or not fields[k]:
                fields[k] = v
            elif k in ("address", "pincode", "guardian", "father_name") and not fields.get(k):
                fields[k] = v
        extract_res["two_sided"] = True
        extract_res["has_back_side"] = True
        if extract_back.get("qr_data") and not extract_res.get("qr_data"):
            extract_res["qr_data"] = extract_back["qr_data"]

    # AI-detection + document-awareness live inside app/main.py (single-file
    # backend). They are imported lazily here the same way, so main.py ->
    # screening.py -> main.py circular import is avoided.
    ai_det, document_aware = {"ran": False, "ai_suspected": False, "ai_score": 0,
                              "model": None, "provider": None, "explanation": "No image.",
                              "latency_ms": 0, "document_aware": None}, None
    is_image = ext in ("jpg", "jpeg", "png", "webp", "bmp") or data.startswith((b"\x89PNG", b"\xff\xd8", b"RIFF"))
    is_pdf = ext == "pdf" or data.startswith(b"%PDF")
    if is_image or is_pdf:
        # Lazy import to avoid circular dependency (screening <- main <- screening).
        try:
            from app.main import detect_image, looks_like_scanned_document
        except ImportError:
            from main import detect_image, looks_like_scanned_document  # type: ignore[no-redef]
        try:
            ai_det = detect_image(data, filename)
        except Exception:
            ai_det = {**ai_det, "explanation": "AI detector unavailable."}
        try:
            document_aware = looks_like_scanned_document(data) if is_image else None
        except Exception:
            document_aware = None

    # ---- Module 2: Validate (deterministic checks + watchlist) -------------
    # Watchlist query (hash-based, privacy-preserving) runs here — the whole
    # table is never pulled into Python, only the ≤7 identifier hashes we need.
    needed = {}
    for key in ("pan", "driving_licence", "passport", "voter_id", "phone", "dob"):
        val = fields.get(key)
        if val:
            needed[sha256(val)] = (key, val)
    watched = set()
    if needed:
        try:
            try:
                from app.main import WatchlistEntry, _get_db_for_session
            except ImportError:
                from main import WatchlistEntry, _get_db_for_session
            with _get_db_for_session(session_id) as temp_db:
                watched = {h for (h,) in temp_db.query(WatchlistEntry.identifier_hash)
                           .filter(WatchlistEntry.identifier_hash.in_(list(needed))).all()}
        except Exception:
            pass
    hits = [{"field": key, "mask": mask(val)} for key, val in
            (needed[h] for h in needed if h in watched)]

    val_res = validate_document(
        doc_type or "", fields, declared or {},
        "", watchlist_hits=hits,
    )

    # ---- Module 3: Tampering (visual forensics on images) ------------------
    timeout_hit = False
    if time.monotonic() - started > 40.0:
        timeout_hit = True
        tamper_res = {"ran": False, "verdict": "SKIP", "ela": {"status": "skipped", "quality": 0}, "checks": [{"label": "timeout", "ok": False, "detail": "Timeout exceeded before tampering check."}]}
    elif is_image:
        tamper_res = tamper_analysis(data, {**ai_det, "document_aware": document_aware},
                                     document_aware, doc_type or "")
    else:
        tamper_res = tamper_analysis(None, ai_det, document_aware, doc_type or "")

    # Back side tamper check if back image is present
    if not timeout_hit and data_back and len(data_back) > 0 and (data_back.startswith((b"\x89PNG", b"\xff\xd8", b"RIFF")) or "jpg" in (filename_back or "").lower() or "png" in (filename_back or "").lower()):
        try:
            tamper_back = tamper_analysis(data_back, ai_det, document_aware, doc_type or "")
            if tamper_back.get("verdict") == "FAIL":
                tamper_res["checks"].append({
                    "label": "back-page-forensics",
                    "ok": False,
                    "detail": "Back page of document raised visual tampering or ELA anomalies.",
                })
        except Exception:
            pass

    # ---- Module 4: Face (document portrait vs live capture) ----------------
    # Aadhaar ships its holder photo as a purpose-cropped b64 (domestic-ID
    # route); other document types keep the whole-document face ROI crop that
    # face_verification computes internally. dob/issue_date feed the age-aware
    # threshold logic ('Age Drift Compensation Active').
    if time.monotonic() - started > 40.0 or timeout_hit:
        timeout_hit = True
        face_res = {"ran": False, "verdict": "SKIP", "match": None, "score": 0.0, "method": "timeout", "signals": ["Face verification skipped due to timeout."]}
    else:
        face_res = face_verification(
            document_bytes=data if is_image else None,
            live_frame=live_frame,
            doc_type=doc_type or "",
            document_photo_b64=extract_res.get("aadhaar_photo"),
            dob=fields.get("dob"),
            issue_date=(
                (declared or {}).get("issue_date") or
                (
                    f"{_parse_date(fields.get('expiry') or (declared or {}).get('expiry_date'))[0] - (5 if 'visa' in (doc_type or '').lower() else 10):04d}-{_parse_date(fields.get('expiry') or (declared or {}).get('expiry_date'))[1]:02d}-{_parse_date(fields.get('expiry') or (declared or {}).get('expiry_date'))[2]:02d}"
                    if _parse_date(fields.get('expiry') or (declared or {}).get('expiry_date')) and (doc_type or "").lower() in ("passport", "visa")
                    else None
                )
            ),
        )

    # ---- Analyze: signals, each one explainable ----------------------------
    reasons = []
    if timeout_hit:
        reasons.append("Report degraded due to processing timeout.")
    
    # Face-verification signals (e.g. 'Age Drift Compensation Active') surface
    # any threshold adjustment here, so the desk and the saved report both see
    # why the ArcFace threshold moved for an aged document photo.
    for sig in (face_res.get("signals") or []):
        reasons.append(sig)
    risk = 20  # neutral starting point; stays low when evidence is clean
    hard_flag = False
    can_clear = True

    pan = fields.get("pan")
    dl = fields.get("driving_licence")
    aadhaar_no = fields.get("aadhaar")
    voter = fields.get("voter_id")
    passport = fields.get("passport")
    mrz_valid = fields.get("mrz_valid")

    # Document identification check: Must have at least one valid, machine-verifiable ID
    identified = bool(
        pan or dl or aadhaar_no or voter or (passport and mrz_valid is not False)
    )

    if not identified:
        can_clear = False
        reasons.append("CRITICAL: Unrecognized document format — No machine-verifiable identity number (Aadhaar, PAN, Passport, Driving Licence, or Voter ID) was validated on the document.")
        risk = max(risk, 80)
        hard_flag = True

    # Document type structure validation
    doc_type_clean = (doc_type or "").strip().lower()
    if pan:
        reasons.append(f"PAN validates as a 10-character identity code ({mask(pan)}).")
        risk -= 3
    elif "pan" in doc_type_clean and not pan:
        reasons.append("DECLARED DOCUMENT MISMATCH: PAN card declared, but machine-reading could not extract a valid PAN code from image — verify printed card by eye.")
        risk = max(risk, 30)
        can_clear = False

    if dl:
        reasons.append(f"Driving-licence number format validates ({mask(dl)}).")
        risk -= 3
    elif "driving" in doc_type_clean and not dl:
        reasons.append("Driving licence declared, but machine-reading could not extract state-code licence number — inspect printed card by eye.")
        risk = max(risk, 30)
        can_clear = False

    if aadhaar_no:
        try:
            from app.identity import validate_verhoeff
        except ImportError:
            from identity import validate_verhoeff
        if not validate_verhoeff(aadhaar_no):
            reasons.append(f"CRITICAL FORGERY SIGNAL: Aadhaar number {mask(aadhaar_no)} FAILS UIDAI Verhoeff Checksum — mathematical proof of a fabricated or counterfeit Aadhaar number.")
            risk = max(risk + 65, 90)
            hard_flag = True
            can_clear = False
        else:
            reasons.append(f"Aadhaar verified as a 12-digit UIDAI-format number with valid Verhoeff checksum ({mask(aadhaar_no)}).")
            risk -= 3
    elif "aadhaar" in doc_type_clean and not aadhaar_no:
        reasons.append("Aadhaar declared but the 12-digit number zone could not be "
                       "machine-read (OCR/webcam quality) — verify the printed number by eye.")
        risk = max(risk, 30)
        can_clear = False

    # Check for explicit synthetic/fake/meme watermarks or markers on document text
    text_raw = f"{extract_res.get('text') or ''} {fields.get('name') or ''} {filename or ''}"
    fake_match = re.search(r"\b(fake|sample|specimen|dummy|chatgpt|dall-?e|midjourney|photoshop|counterfeit|meme|parody|not a real id|not a valid id|not for official use|stay alert)\b", text_raw, re.IGNORECASE)
    if fake_match:
        reasons.append(f"CRITICAL FORGERY / SYNTHETIC WATERMARK: Document text explicitly contains '{fake_match.group(1).upper()}' marker — counterfeit or AI-generated identity document.")
        risk = max(risk + 70, 95)
        hard_flag = True
        can_clear = False

    # Check for known public celebrity / athlete names used in fake IDs
    name_upper = (fields.get("name") or "").upper()
    if any(celeb in name_upper for celeb in ("CRISTIANO RONALDO", "LIONEL MESSI", "DONALD TRUMP", "BARACK OBAMA", "ELON MUSK")):
        reasons.append(f"CRITICAL IMPOSTER / FICTITIOUS IDENTITY: Document name '{fields.get('name')}' is a known public celebrity — fraudulent identity spoofing.")
        risk = max(risk + 70, 95)
        hard_flag = True
        can_clear = False

    if voter:
        reasons.append(f"Voter-ID (EPIC) number validates as 3 letters + 7 digits ({mask(voter)}).")
        risk -= 3
    elif "voter" in doc_type_clean and not voter:
        reasons.append("Voter ID declared, but no valid EPIC (3 letters + 7 digits) was read — inspect card by eye.")
        risk = max(risk, 30)
        can_clear = False

    if passport:
        is_visa = "visa" in doc_type_clean
        lbl = "Visa" if is_visa else "Passport"
        if mrz_valid is True:
            reasons.append(f"{lbl} {mask(passport)} passes every MRZ check digit — the "
                           "machine-readable zone is internally consistent.")
            risk -= 6
        elif mrz_valid is False:
            reasons.append(f"CRITICAL FORGERY SIGNAL: {lbl} {mask(passport)} has an MRZ whose check digits FAIL — "
                           "mathematical proof of an altered or counterfeit document.")
            risk = max(risk + 45, 75)
            hard_flag = True
            can_clear = False
        else:
            reasons.append(f"{lbl} number found ({mask(passport)}) but no valid MRZ was "
                           "read to cross-check it — inspect the zone by eye.")
            risk += 10
            can_clear = False
    elif ("passport" in doc_type_clean or "visa" in doc_type_clean) and not passport:
        reasons.append("Passport/Visa declared, but identifier could not be machine-read — inspect document by eye.")
        risk = max(risk, 35)
        can_clear = False

    # Cryptographic QR Code Verification Reward
    qr_info = extract_res.get("qr_data") or {}
    if qr_info.get("qr_verified") or qr_info.get("signature_present"):
        reasons.append(f"CRYPTOGRAPHIC QR VERIFIED: {qr_info.get('details', 'Official signed QR code verified (UIDAI / NSDL / Parivahan).')}")
        risk = max(0, risk - 15)

    dob = fields.get("dob")
    if dob:
        if dob > _today():
            reasons.append(f"CRITICAL DATE ANOMALY: Date of birth {dob} is in the FUTURE on this document.")
            risk = max(risk + 40, 70)
            hard_flag = True
            can_clear = False
        elif dob.startswith("20") and passport:
            reasons.append("Child DOB on a passport — require guardian linkage.")
            risk += 6

    # Expiry Check (both extracted and declared)
    expiry = fields.get("expiry") or ((declared or {}).get("expiry_date") or "").strip()
    _exp = _parse_date(expiry)
    if _exp:
        from datetime import date as _date
        try:
            exp_date_obj = _date(int(_exp[0]), int(_exp[1]), int(_exp[2]))
            if exp_date_obj < _date.today():
                reasons.append(f"CRITICAL EXPIRED DOCUMENT: Document expired on {exp_date_obj.isoformat()} (in the PAST) — document is invalid for travel or entry.")
                risk = max(risk + 45, 80)
                hard_flag = True
                can_clear = False
        except (ValueError, OverflowError):
            pass

    # Travel validity timeline
    travel_val = _travel_validity(None, dob, doc_type or "")
    if _exp:
        from datetime import date as _date
        try:
            exp_obj = _date(int(_exp[0]), int(_exp[1]), int(_exp[2]))
            days = (exp_obj - _date.today()).days
            travel_val["days_to_expiry"] = days
            travel_val["six_month_rule"] = days >= 180
            if days < 0:
                travel_val["status"] = "EXPIRED"
                travel_val["detail"] = f"Document EXPIRED {abs(days)} day(s) ago."
            elif days < 180:
                travel_val["status"] = "EXPIRING_SOON"
                travel_val["detail"] = (f"Only {days} day(s) to expiry — "
                                        "fails 6-month rule for most destinations.")
                reasons.append(travel_val["detail"])
                risk += 6
            else:
                travel_val["status"] = "VALID"
                travel_val["detail"] = f"Document valid for {days} more day(s)."
        except (ValueError, OverflowError):
            pass

    # Cross-Border Nationality & Document Appropriateness Checks
    if nationality:
        nat_raw = str(nationality).strip().upper()
        # Normalization map to standard ISO codes and human labels
        nat_map = {
            "IN": ("IND", "Indian"), "IND": ("IND", "Indian"), "INDIA": ("IND", "Indian"),
            "NP": ("NPL", "Nepali"), "NPL": ("NPL", "Nepali"), "NEPAL": ("NPL", "Nepali"),
            "BT": ("BTN", "Bhutanese"), "BTN": ("BTN", "Bhutanese"), "BHUTAN": ("BTN", "Bhutanese"),
            "BD": ("BGD", "Bangladeshi"), "BGD": ("BGD", "Bangladeshi"), "BANGLADESH": ("BGD", "Bangladeshi"),
            "PK": ("PAK", "Pakistani"), "PAK": ("PAK", "Pakistani"), "PAKISTAN": ("PAK", "Pakistani"),
            "CN": ("CHN", "Chinese"), "CHN": ("CHN", "Chinese"), "CHINA": ("CHN", "Chinese"),
            "US": ("USA", "United States"), "USA": ("USA", "United States"),
            "GB": ("GBR", "British"), "UK": ("GBR", "British"), "GBR": ("GBR", "British"),
        }
        iso3, nat_label = nat_map.get(nat_raw, (nat_raw[:3], nat_raw))
        text_upper = (extract_res.get("text") or "").upper()
        mrz_data = extract_res.get("mrz") or {}
        mrz_issuing = (mrz_data.get("issuing_country") or "").upper()
        mrz_nat = (mrz_data.get("nationality") or "").upper()

        # 1. Indian Domestic Documents presented by Foreign Nationals
        if doc_type_clean in ("aadhaar", "pan", "voter_id", "driving_licence"):
            if iso3 not in ("IND", "UNKNOWN", ""):
                reasons.append(
                    f"CRITICAL NATIONALITY / DOCUMENT MISMATCH: Traveller declared {nat_label} nationality ({iso3}), "
                    f"but presented an Indian domestic identity document ({doc_type_clean.upper().replace('_', ' ')}). "
                    f"Indian domestic IDs are restricted to Indian citizens/residents and cannot serve as proof of identity for {nat_label} nationals."
                )
                risk = max(risk + 55, 85)
                hard_flag = True
                can_clear = False

        # 2. Nepali Citizenship presented by Non-Nepali Nationals
        elif doc_type_clean == "nepal_citizenship":
            if iso3 not in ("NPL", "UNKNOWN", ""):
                reasons.append(
                    f"CRITICAL CITIZENSHIP MISMATCH: Traveller declared {nat_label} nationality ({iso3}), "
                    f"but presented a Nepali Citizenship Certificate. Citizenship certificates are strictly issued to Nepali nationals."
                )
                risk = max(risk + 55, 85)
                hard_flag = True
                can_clear = False

        # 3. Bhutanese Citizenship presented by Non-Bhutanese Nationals
        elif doc_type_clean == "bhutan_citizenship":
            if iso3 not in ("BTN", "UNKNOWN", ""):
                reasons.append(
                    f"CRITICAL CITIZENSHIP MISMATCH: Traveller declared {nat_label} nationality ({iso3}), "
                    f"but presented a Bhutanese Citizenship Identity. Valid only for Bhutanese nationals."
                )
                risk = max(risk + 55, 85)
                hard_flag = True
                can_clear = False

        # 4. Third-Country Nationals Crossing Land Border (Non-Treaty Nationals)
        elif iso3 not in ("IND", "NPL", "BTN", "UNKNOWN", ""):
            # Third-country nationals MUST present a valid passport + visa
            if doc_type_clean not in ("passport", "visa"):
                reasons.append(
                    f"CRITICAL BORDER COMPLIANCE VIOLATION: Third-country nationals ({nat_label}) crossing international land borders "
                    f"require a valid International Passport with a verified Indian Visa / e-Visa. Domestic ID cards ({doc_type_clean}) are strictly invalid."
                )
                risk = max(risk + 60, 88)
                hard_flag = True
                can_clear = False

        # 5. Passport MRZ Nationality vs Declared Nationality Conflict
        if doc_type_clean == "passport" and (mrz_issuing or mrz_nat):
            doc_country = mrz_nat or mrz_issuing
            if iso3 not in ("UNKNOWN", "") and doc_country and doc_country != iso3:
                reasons.append(
                    f"CRITICAL MRZ NATIONALITY CONFLICT: Machine Readable Zone (MRZ) encodes nationality as {doc_country}, "
                    f"which contradicts the declared traveller nationality ({iso3} - {nat_label})."
                )
                risk = max(risk + 55, 85)
                hard_flag = True
                can_clear = False

        # 6. Foreign Visa / Transit Mismatch for Nepali/Bhutanese citizens
        if iso3 in ("NPL", "BTN") and any(foreign in text_upper for foreign in ("UNITED KINGDOM", "GREAT BRITAIN", "UK VISA", "SCHENGEN", "UNITED STATES")):
            reasons.append("CRITICAL NATIONALITY / VISA MISMATCH: Traveller declared Nepali/Bhutanese nationality but travel document/visa indicates third-country issuance without transit authorization.")
            risk = max(risk + 50, 85)
            hard_flag = True
            can_clear = False

    # AI Detection Evaluation
    # AI Detection Evaluation
    # Calibrated (SIH26188 real-desk fix): a *physical* desk/webcam photo of a
    # glossy laminated card can trip the spectral band detector at 50-64%
    # purely from glare + JPEG/webcam compression, WITHOUT the card being
    # synthetic.
    ai_raw_kind = (ai_det.get("raw") or {}).get("kind")
    _ai_score = ai_det.get("ai_score", 0) or 0
    has_valid_id = bool(pan or aadhaar_no or passport or fields.get("driving_licence") or fields.get("voter_id"))
    val_passed = (val_res.get("verdict") == "PASS")
    is_physical_camera = (document_aware is False) or (has_valid_id and val_passed)
    tamper_passed = (tamper_res.get("verdict") == "PASS")
    ela_status = (tamper_res.get("ela") or {}).get("status")
    is_cloud_or_model = ai_det.get("provider") in ("self-hosted", "sightengine", "hive", "vit", "clip", "test")

    if ai_raw_kind == "pdf_utility":
        tool_name = (ai_det.get("raw") or {}).get("match_tool") or "PDF utility"
        reasons.append(f"Document processed with PDF utility ({tool_name}) — standard document handling.")
    elif ai_raw_kind == "ai":
        score_val = max(_ai_score, 85)
        tool_name = (ai_det.get("raw") or {}).get("match_tool") or "AI generator"
        reasons.append(f"CRITICAL AI-ALERT: Visual/metadata scan confirms AI-GENERATED image via {tool_name} ({score_val}% confidence) — synthetic documents are a known forgery vector.")
        risk = max(risk + 55, 82)
        hard_flag = True
        can_clear = False
    elif ai_raw_kind == "edited":
        tool_name = (ai_det.get("raw") or {}).get("match_tool") or "editor"
        if has_valid_id and val_passed and ela_status != "HIGH":
            reasons.append(f"Document software signature noted ({tool_name}) — legal identifier verified valid with low tampering risk.")
            risk += 5
        else:
            score_val = max(_ai_score, 80)
            reasons.append(f"CRITICAL TAMPER-ALERT: Metadata confirms image manipulation / editing tool signature via {tool_name} ({score_val}% confidence).")
            risk = max(risk + 50, 80)
            hard_flag = True
            can_clear = False
    elif ai_det.get("ai_suspected") or _ai_score >= 65:
        if (has_valid_id or (document_aware is False and _ai_score < 80)) and ela_status != "HIGH":
            reasons.append(f"Physical photo capture advisory: Surface background texture / optical glare noted ({_ai_score}% model variation).")
            risk += 5
        else:
            score_val = max(_ai_score, 80)
            reasons.append(f"CRITICAL AI-ALERT: Visual/spectral scan flags the document as AI-GENERATED or edited ({score_val}% confidence) — synthetic documents are a known forgery vector.")
            risk = max(risk + 55, 82)
            hard_flag = True
            can_clear = False
    elif _ai_score >= 55 and document_aware is not True:
        if not (is_physical_camera or val_passed or has_valid_id):
            score_val = _ai_score
            reasons.append(f"Borderline synthetic artifacts detected ({score_val}% confidence).")
            risk = max(risk + 12, 48)
            can_clear = False

    if document_aware is True:
        reasons.append("File reads as a scanned paper document — orientation/medium looks right.")
    elif document_aware is False and doc_type_clean not in ("other", ""):
        reasons.append("Physical card camera capture (desk/handheld photo, not flatbed scan).")

    if extract_res.get("pdf_no_text"):
        reasons.append("PDF contains no extractable text layer (scanned or image-only pages) — "
                       "identifier checksums could not run, so treat the number on the paper as "
                       "unverified until a human or OCR reads it.")
        risk += 8
        can_clear = False

    # Module verdicts fold into the risk score — use each module's own
    # weighted verdict rather than re-deriving a separate any(ok is False)
    # check (which double-counted noisy signals and was inconsistent with
    # the has_real_tamper logic immediately below it).
    for mod_key, mod_res in (("validation", val_res), ("tampering", tamper_res),
                             ("face", face_res)):
        mod_verdict = mod_res.get("verdict", "")
        if mod_key == "validation" and mod_verdict == "FAIL":
            reasons.append("CRITICAL VALIDATION FAILURE: Module 2 (validation) failed deterministic check — see modules.")
            risk = max(risk + 35, 70)
            hard_flag = True
            can_clear = False
        elif mod_key == "tampering" and mod_verdict == "FAIL":
            # Only trigger CRITICAL FORENSIC ALERT when there is actual tampering detected
            ela_status = (tamper_res.get("ela") or {}).get("status")
            has_real_tamper = (
                ela_status == "HIGH"
                or ai_raw_kind in ("ai", "edited")
                or any(c.get("label") == "ai-generated-or-edited" and c.get("ok") is False for c in tamper_res.get("checks", []))
                or any(c.get("label", "").startswith("liveness-") and c.get("ok") is False for c in tamper_res.get("checks", []))
            )
            if has_real_tamper:
                reasons.append("CRITICAL FORENSIC ALERT: Module 3 (tampering) raised visual forgery anomalies (high ELA paste, AI generation, or liveness failure) — see modules.")
                risk = max(risk + 55, 82)
                hard_flag = True
                can_clear = False
            else:
                reasons.append("Forensic check advisory: Soft image focus or physical capture note — see tampering module.")
                risk = max(risk, 25)
        elif mod_key == "tampering" and mod_verdict == "REVIEW":
            reasons.append("Forensic check advisory: Module 3 (tampering) returned REVIEW — see tampering module.")
            risk = max(risk, 25)
        elif mod_key == "face" and mod_res.get("match") is False:
            reasons.append("CRITICAL BIOMETRIC ALERT: Module 4 reports the document portrait does NOT match the "
                           "captured holder — a very strong fraud signal.")
            risk = max(risk + 55, 82)
            hard_flag = True
            can_clear = False

    # Watchlist contributed by Module 2 (hash query above the Analyze pass).
    if hits:
        joined = "; ".join(f"{h['field']} {h['mask']}" for h in hits)
        reasons.append(f"WATCHLIST HIT — {joined}. Reroute to a supervisory officer.")
        risk = max(risk + 60, 90)
        hard_flag = True
        can_clear = False

    # Evidence coverage: how much of this decision is grounded vs by-eye?
    evidence = sum(bool(v) for v in fields.values() if v) + bool(declared) + len(hits)
    coverage = min(evidence, 8) / 8.0
    confidence = round(min(0.98, 0.45 + coverage * 0.5), 2)
    if not identified:
        can_clear = False
        risk = max(risk, 40)
    elif evidence < 1:
        can_clear = False
        risk = max(risk, 35)

    # Removed: blanket "any check with ok is False disables CLEAR" loop.
    # This was the root cause of mass false-positives — it vetoed can_clear
    # even when the weighted verdict said PASS/REVIEW. Each module's own
    # weighted verdict (above) now governs whether can_clear is disabled.

    # ---- Feature 5: Devanagari ↔ Latin name divergence check ---------------
    mrz_name = fields.get("mrz_name") or fields.get("holder_name") or ""
    declared_name = (declared or {}).get("name") or (declared or {}).get("holder_name") or ""
    if mrz_name and declared_name:
        try:
            from transliterate import names_match
            nm, ns, nd = names_match(mrz_name, declared_name)
            if nm is False:
                reasons.append(f"NAME DIVERGENCE — {nd}")
                risk += 18
                can_clear = False
            elif nm is None and ns < 0.60:
                reasons.append(f"Name check inconclusive — {nd}")
                risk += 6
        except Exception:
            pass

    # ---- Syndicate & Recidivism Graph Analytics (SIH26188) ----------------
    syndicate_alerts = []
    try:
        from syndicate import analyze_syndicate_patterns
        try:
            from app.main import ScreeningReport, _get_db_for_session
        except ImportError:
            from main import ScreeningReport, _get_db_for_session
            
        recent_history = []
        try:
            with _get_db_for_session(session_id) as temp_db:
                rows = temp_db.query(ScreeningReport).order_by(ScreeningReport.created_at.desc()).limit(50).all()
                for r in rows:
                    ef = {}
                    try:
                        ef = json.loads(r.extracted_fields or "{}")
                    except Exception:
                        pass
                    recent_history.append({
                        "file_hash": r.file_hash,
                        "checkpoint": r.checkpoint,
                        "doc_number": ef.get("passport") or ef.get("pan") or ef.get("driving_licence") or ef.get("voter_id"),
                        "name": ef.get("mrz_name") or ef.get("holder_name") or ef.get("name"),
                        "verdict": r.verdict,
                        "created_at": r.created_at,
                    })
        except Exception:
            pass

        doc_no = fields.get("passport") or fields.get("pan") or fields.get("driving_licence") or fields.get("voter_id")
        holder = fields.get("mrz_name") or fields.get("holder_name") or (declared or {}).get("name")
        cur_meta = {
            "file_hash": file_hash,
            "checkpoint": checkpoint or "",
            "doc_number": doc_no,
            "name": holder,
            "dob": fields.get("dob"),
            "verdict": _grade(risk, hard_flag=hard_flag, can_clear=can_clear),
            "risk_score": risk,
        }
        syn_res = analyze_syndicate_patterns(cur_meta, recent_history)
        if syn_res.get("has_alerts"):
            syndicate_alerts = syn_res["alerts"]
            for alert in syndicate_alerts:
                reasons.append(f"SYNDICATE ALERT [{alert['type']}]: {alert['detail']}")
            risk += syn_res.get("syndicate_risk_bump", 0)
            # Only individual recidivism / identity clash alerts block CLEAR;
            # an ambient sector burst alert alone (general checkpoint volume alert)
            # does not block an otherwise genuine document from clearing.
            if any(a.get("type") in ("IDENTITY_CLASH", "CROSS_CHECKPOINT_REPRESENTATION", "PREVIOUSLY_FLAGGED_IDENTIFIER") for a in syndicate_alerts):
                can_clear = False
    except Exception:
        pass

    risk = max(0, min(100, risk))
    verdict = _grade(risk, hard_flag=hard_flag, can_clear=can_clear)

    # Cross-document fingerprints (session flow, SIH26188): per-field sha256 of
    # the normalized value, so a later session close can compare this document
    # against the others in the same session WITHOUT storing raw values.
    try:
        from session import field_hashes as _field_hashes
        _fh = _field_hashes(fields)
    except Exception:
        _fh = {}

    report = {
        "id": uuid.uuid4().hex[:16],
        "file_hash": file_hash,
        "filename": filename or "upload",
        "doc_type": doc_type or "UNKNOWN",
        "checkpoint": checkpoint or "",
        "verdict": verdict,
        "travel_validity": travel_val,
        "syndicate_alerts": syndicate_alerts,
        "risk_score": risk,
        "confidence": confidence,
        "degraded": timeout_hit,
        "masked_fields": {k: (mask(v) if isinstance(v, str) else v)
                          for k, v in fields.items()},
        "raw_fields": extract_res.get("fields", {}),
        "field_hashes": _fh,
        "session_id": session_id,
        "watchlist_hits": hits,
        "nationality": nationality,
        "purpose": purpose,
        "reasons": reasons,
        "ai_detection": {k: ai_det.get(k) for k in
                         ("ran", "ai_suspected", "ai_score", "model", "provider",
                          "explanation", "latency_ms")},
        "modules": {
            "extraction": {
                "ran": True,
                "verdict": "PASS" if len([v for v in fields.values() if v]) > 0 else "FAIL",
                "medium": extract_res["medium"],
                "mrz": extract_res.get("mrz"),
                "ocr": extract_res.get("ocr", {"ran": True}),
                "document_aware": document_aware,
            },
            "validation": {
                "verdict": val_res["verdict"],
                "checks": val_res["checks"],
            },
            "tampering": {
                "verdict": tamper_res["verdict"],
                "checks": tamper_res["checks"],
                "ela": {k: (tamper_res.get("ela") or {}).get(k) for k in
                        ("status", "damage_ratio", "mean_diff", "latency_ms")},
                "heatmap_b64": (tamper_res.get("ela") or {}).get("heatmap_b64"),
                "overlay_grid": (tamper_res.get("ela") or {}).get("overlay_grid"),
                "roi": tamper_res.get("roi", []),
            },
            "face": {
                "verdict": face_res["verdict"],
                "match": face_res.get("match"),
                "score": face_res.get("score"),
                "method": face_res.get("method"),
                "detail": face_res.get("detail"),
                "checks": face_res.get("checks", []),
            },
        },
        "latency_ms": int((time.monotonic() - started) * 1000),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "created_at_ist": None,  # filled by the API layer (IST display)
    }

    # Hash-chain linkage: compute block hash linking to the previous report
    prev_hash = "GENESIS"
    
    # Module snapshot persisted for the desk/review surfaces. Compact leaf shape
    # (no raw bytes, no heatmaps): M1 medium/MRZ/OCR, M2 verdict, M3 verdict +
    # ELA status, M4 verdict/match/score/method.
    def _mod_leaf(mod: str, path: str):
        node = report.get("modules", {}).get(mod) or {}
        for part in path.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                return None
        return node

    if isinstance(report.get("modules"), dict):
        modules_snapshot = json.dumps({
            "extraction": {"medium": _mod_leaf("extraction", "medium"),
                           "mrz": {"valid": _mod_leaf("extraction", "mrz.valid")},
                           "ocr": {"ran": _mod_leaf("extraction", "ocr.ran")},
                           "document_aware": _mod_leaf("extraction", "document_aware")},
            "validation": {"verdict": _mod_leaf("validation", "verdict")},
            "tampering": {"verdict": _mod_leaf("tampering", "verdict"),
                          "ela": {"status": _mod_leaf("tampering", "ela.status")}},
            "face": {"verdict": _mod_leaf("face", "verdict"),
                     "match": _mod_leaf("face", "match"),
                     "score": _mod_leaf("face", "score"),
                     "method": _mod_leaf("face", "method")},
        })
    else:
        modules_snapshot = None
    _wl_hits = report.get("watchlist_hits") or []

    # We must compute hash block AFTER the payload values are ready, but we
    # do it inside the DB context so we can pull the previous row's hash.
    try:
        from app.main import ScreeningReport, _get_db_for_session
    except ImportError:
        from main import ScreeningReport, _get_db_for_session

    try:
        with _get_db_for_session(session_id) as temp_db:
            try:
                prev_row = temp_db.query(ScreeningReport).order_by(ScreeningReport.created_at.desc(), ScreeningReport.id.desc()).first()
                prev_hash = prev_row.ledger_hash if (prev_row and getattr(prev_row, "ledger_hash", None)) else "GENESIS"
            except Exception:
                prev_hash = "GENESIS"
                
            block_payload = f"{prev_hash}:{file_hash}:{verdict}:{risk}:{report['created_at']}:{screener or 'unknown'}"
            ledger_hash = hashlib.sha256(block_payload.encode("utf-8")).hexdigest()
            report["block_hash"] = ledger_hash
            report["prev_hash"] = prev_hash
            
            temp_db.add(ScreeningReport(
                id=report["id"], file_hash=file_hash, filename=report["filename"],
                doc_type=report["doc_type"], checkpoint=report["checkpoint"],
                verdict=verdict, risk_score=risk, confidence=confidence,
                extracted_fields=json.dumps(report["masked_fields"]),
                signals=json.dumps(reasons),
                ai_detection=json.dumps(report["ai_detection"]),
                modules=modules_snapshot,
                watchlist_hits=json.dumps(_wl_hits) if _wl_hits else None,
                previous_hash=prev_hash,
                ledger_hash=ledger_hash,
                screener=screener,
                latency_ms=report.get("latency_ms"),
                created_at=report["created_at"],
                session_id=session_id or report.get("session_id"),
                field_hashes=json.dumps(_fh) if _fh else None,
                ephemeral_raw_fields=json.dumps(extract_res.get("fields", {})) if extract_res.get("fields") else None,
                nationality=nationality,
                purpose=purpose,
            ))
            temp_db.commit()
    except Exception:
        pass

    return report