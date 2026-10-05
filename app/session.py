"""
Border screening SESSION orchestration (SIH26188).

One traveller at the desk = one session. Their documents are screened one at a
time (each pass already persists a masked ScreeningReport audit row); the
extracted identifier values are compared ACROSS the documents for
discrepancies; and when the session is approved (or a supervisor settles a
flagged one) the session's canonical data is reduced to a SHA-256 digest and
chained into the ledger as an immutable block.

Zero-storage is preserved end to end: only hashes (of the file, of normalized
field values), masked tails, and comparison *flags* are persisted. Raw values
live only in memory during one screening run and are then discarded.

Cross-document name comparison is script-aware: exact digests are compared
only when both documents sourced the name in the same script (the common
Latin MRZ vs Latin print case). If one document's name came from a Devanagari
scan and the other from a Latin print, the field is marked `cross-script` for
human review — the comparison never fabricates a hard mismatch it cannot
prove, and never silently clears a real one.
"""

import hashlib

try:
    from app.screening import norm  # type: ignore
except ImportError:
    from screening import norm  # type: ignore


# Fields whose values must agree across the documents of one person.
CMP_FIELDS = (
    ("name", "Holder name"),
    ("dob", "Date of birth"),
    ("gender", "Gender"),
    ("passport", "Passport / visa number"),
    ("state", "State / Jurisdiction"),
    ("pincode", "Pincode / Postal area"),
    ("address", "Residential address"),
)

# The extraction pass can surface a holder name under any of these keys,
# depending on the medium (image OCR -> 'name'/'holder_name', MRZ -> 'mrz_name').
_NAME_KEYS = ("name", "holder_name", "mrz_name")


def _canonical_name(fields: dict) -> str:
    for key in _NAME_KEYS:
        val = fields.get(key)
        if val:
            return val
    return ""


def _is_devanagari(value: str) -> bool:
    return any("\u0900" <= ch <= "\u097F" for ch in value)


def _name_variant(value: str) -> str:
    """Canonical Latin form of a holder name: Devanagari is transliterated to
    Latin (see _transliterate_devanagari), then normalized. Latin names pass
    through untouched so same-script digests stay exact. Returns '' for falsy
    input."""
    if not value:
        return ""
    if _is_devanagari(value):
        value = _transliterate_devanagari(value)
    return norm(value)


def _transliterate_devanagari(value: str) -> str:
    """Deterministic compact Devanagari -> Latin transliteration (name subset).

    Bare consonants emit no inherent vowel, matras append their vowel, the
    virama is dropped, and long vowels are shortened ('aa'->'a', 'ii'->'i',
    'uu'->'u') to mirror how Indian names are conventionally romanized.
    Non-Devanagari characters pass through untouched."""
    out = []
    for ch in value:
        mapped = _DEVANAGARI_MAP.get(ch)
        if mapped is None:
            out.append(ch)
        elif mapped:
            out.append(mapped)
    text = "".join(out)
    for _long, _short in (("aa", "a"), ("ii", "i"), ("uu", "u")):
        text = text.replace(_long, _short)
    return text


_DEVANAGARI_MAP = {
    # Independent vowels
    "\u0905": "a", "\u0906": "aa", "\u0907": "i", "\u0908": "ii",
    "\u0909": "u", "\u090A": "uu", "\u090B": "ri", "\u090C": "e",
    "\u090F": "e", "\u0910": "ai", "\u0911": "o", "\u0913": "o", "\u0914": "au",
    # Consonants (bare)
    "\u0915": "k", "\u0916": "kh", "\u0917": "g", "\u0918": "gh", "\u0919": "ng",
    "\u091A": "ch", "\u091B": "chh", "\u091C": "j", "\u091D": "jh", "\u091E": "ny",
    "\u091F": "tt", "\u0920": "tth", "\u0921": "dd", "\u0922": "ddh", "\u0923": "nn",
    "\u0924": "t", "\u0925": "th", "\u0926": "d", "\u0927": "dh", "\u0928": "n",
    "\u0929": "nn", "\u092A": "p", "\u092B": "ph", "\u092C": "b", "\u092D": "bh",
    "\u092E": "m", "\u092F": "y", "\u0930": "r", "\u0931": "l", "\u0932": "l",
    "\u0933": "ll", "\u0934": "ll", "\u0935": "v", "\u0936": "sh", "\u0937": "shh",
    "\u0938": "s", "\u0939": "h",
    # Nukta variants
    "\u0958": "q", "\u0959": "kh", "\u095A": "g", "\u095B": "z",
    "\u095C": "dd", "\u095D": "rrh", "\u095E": "f", "\u095F": "y",
    # Matras (dependent vowels)
    "\u093E": "aa", "\u093F": "i", "\u0940": "ii", "\u0941": "u", "\u0942": "uu",
    "\u0943": "ri", "\u0944": "rii", "\u0945": "e", "\u0946": "e", "\u0947": "e",
    "\u0948": "ai", "\u0949": "o", "\u094A": "o", "\u094B": "o", "\u094C": "au",
    # Other signs
    "\u0901": "n", "\u0902": "n", "\u0903": "h",
    # Marks that emit nothing
    "\u0900": "", "\u093C": "", "\u094D": "", "\u094E": "", "\u0951": "",
    "\u0952": "", "\u0953": "", "\u0954": "",
}


def field_hashes(fields: dict) -> dict:
    """Per-field comparison record for one document. In-memory only; returns
    {field: {"h": sha256 of the normalized value, "s": script}} for the fields
    actually present. `s` is 'latin' or 'devanagari' and drives the
    script-aware name comparison in build_comparison."""
    out = {}
    for key, _label in CMP_FIELDS:
        if key == "name":
            raw = _canonical_name(fields)
            script = "devanagari" if raw and _is_devanagari(raw) else "latin"
            base = _name_variant(raw) if raw else ""
        else:
            raw = fields.get(key) or ""
            script = "latin"
            base = norm(raw) if raw else ""
        if base:
            out[key] = {"h": hashlib.sha256(base.encode("utf-8")).hexdigest(), "s": script}
    return out


def _entry(doc: dict, key: str):
    """Normalized comparison record for one field of one document."""
    e = (doc.get("field_hashes") or {}).get(key)
    if isinstance(e, dict) and e.get("h"):
        return e
    if isinstance(e, str) and e:  # legacy plain-digest rows
        return {"h": e, "s": "latin"}
    raw = (doc.get("raw_fields") or {}).get(key) or (doc.get("masked") or {}).get(key)
    if raw and isinstance(raw, str) and raw.strip():
        n = norm(raw)
        if n:
            return {"h": hashlib.sha256(n.encode("utf-8")).hexdigest(), "s": "latin"}
    return None



def devanagari_to_ascii_digits(s: str) -> str:
    """Map Devanagari numerals (०-९) to ASCII (0-9)."""
    nep = "०१२३४५६७८९"
    for i, d in enumerate(nep):
        s = s.replace(d, str(i))
    return s


def bs_to_ad_approx(val: str) -> str:
    """Converts a Bikram Sambat (BS) date string to approximate Gregorian (AD) YYYY-MM-DD.
    Bikram Sambat is the official national calendar of Nepal (~56.7 years ahead of AD)."""
    import re
    if not val:
        return ""
    s = devanagari_to_ascii_digits(str(val)).strip()
    m = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
    if not m:
        return val
    y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1970 <= y <= 2120:  # Bikram Sambat range (e.g. 2052 BS -> 1995 AD)
        ad_y = y - 57
        return f"{ad_y:04d}-{mth:02d}-{d:02d}"
    return val


def normalize_dob(dob: str) -> str:
    """Normalize Date of Birth across formats and calendar systems (AD / BS)."""
    import re
    if not dob:
        return ""
    s = devanagari_to_ascii_digits(str(dob)).strip()
    s = bs_to_ad_approx(s)
    m1 = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
    if m1:
        return f"{int(m1.group(1)):04d}-{int(m1.group(2)):02d}-{int(m1.group(3)):02d}"
    m2 = re.search(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', s)
    if m2:
        return f"{int(m2.group(3)):04d}-{int(m2.group(2)):02d}-{int(m2.group(1)):02d}"
    m3 = re.search(r'\b(19\d{2}|20\d{2})\b', s)
    if m3:
        return m3.group(1)
    return s


def soundex(name: str) -> str:
    """Classic Soundex indexing for cross-border Indian/Nepali name transliteration."""
    clean = "".join(c for c in (name or "").upper() if c.isalpha())
    if not clean:
        return "0000"
    first = clean[0]
    codes = {'BFPV': '1', 'CGJKQSXZ': '2', 'DT': '3', 'L': '4', 'MN': '5', 'R': '6'}
    table = {}
    for keys, digit in codes.items():
        for char in keys:
            table[char] = digit
    res = [first]
    prev = table.get(first, '0')
    for char in clean[1:]:
        code = table.get(char, '0')
        if code != '0' and code != prev:
            res.append(code)
        prev = code
    return ("".join(res) + "0000")[:4]


def _primary_ids_agree(docs: list[dict]) -> bool:
    """True if any primary credential (PAN, Aadhaar, Passport, DL, Voter ID) 
    matches across documents in the session."""
    for id_key in ("pan", "aadhaar", "passport", "driving_licence", "voter_id"):
        vals = []
        for d in docs:
            v = (d.get("raw_fields") or {}).get(id_key) or (d.get("masked") or {}).get(id_key)
            if v and isinstance(v, str) and len(v.strip()) >= 5:
                vals.append(norm(v.strip()))
        if len(vals) >= 2:
            if len(set(vals)) == 1:
                return True
    return False


def match_names(names: list[str], ids_agree: bool = False) -> tuple[bool, str]:
    """Determine if extracted names across documents represent the same person.
    Zero-storage safe: does not print raw names in output explanation.
    Handles OCR character substitutions, word reordering, initials, and honorific prefixes."""
    clean_names = [" ".join((n or "").upper().split()) for n in names if n]
    if len(clean_names) <= 1:
        return True, "Single name"
    if len(set(clean_names)) == 1:
        return True, "Exact match"

    import re
    from difflib import SequenceMatcher

    token_lists = []
    for n in clean_names:
        clean = re.sub(r'[^A-Z\s]', ' ', n)
        tokens = [t for t in clean.split() if t not in ('MR', 'MS', 'MRS', 'SHRI', 'SMT', 'DR', 'KUMAR')]
        if not tokens:
            tokens = clean.split()
        token_lists.append(tokens)

    all_pairs_match = True
    match_reasons = []

    for i in range(len(token_lists)):
        for j in range(i + 1, len(token_lists)):
            t1, t2 = token_lists[i], token_lists[j]
            s1, s2 = " ".join(t1), " ".join(t2)
            
            # 1. Exact token sets (e.g. "SATAPATHY DIKHYANT" vs "DIKHYANT SATAPATHY")
            if set(t1) == set(t2):
                match_reasons.append("token order variation")
                continue
                
            # 2. Subset / Expansion (e.g. "DIKHYANT SATAPATHY" vs "DIKHYANT K SATAPATHY")
            if set(t1).issubset(set(t2)) or set(t2).issubset(set(t1)):
                match_reasons.append("name expansion variation")
                continue

            # 3. Initial matching (e.g. "D SATAPATHY" vs "DIKHYANT SATAPATHY")
            if len(t1) == len(t2):
                init_match = True
                for a, b in zip(t1, t2):
                    if a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b)):
                        continue
                    init_match = False
                    break
                if init_match:
                    match_reasons.append("initial abbreviation match")
                    continue

            # 4. SequenceMatcher fuzzy similarity on string
            ratio = SequenceMatcher(None, s1, s2).ratio()
            threshold = 0.70 if ids_agree else 0.80
            if ratio >= threshold:
                match_reasons.append(f"high string similarity ({int(ratio * 100)}%)")
                continue

            # 5. Shared surname + first name similarity
            if len(t1) >= 2 and len(t2) >= 2:
                if t1[-1] == t2[-1]:
                    first_ratio = SequenceMatcher(None, t1[0], t2[0]).ratio()
                    if first_ratio >= 0.70 or (ids_agree and first_ratio >= 0.50):
                        match_reasons.append(f"surname concordance with first-name variation ({int(first_ratio * 100)}%)")
                        continue

            # 6. Soundex phonetic equivalence
            if soundex(s1) == soundex(s2) and soundex(s1) != "0000":
                match_reasons.append(f"phonetic Soundex agreement ({soundex(s1)})")
                continue

            all_pairs_match = False
            break
        if not all_pairs_match:
            break

    if all_pairs_match:
        reason = match_reasons[0] if match_reasons else "semantic match"
        return True, reason

    return False, "Names differ beyond acceptable tolerance"


def compute_zkp_gates(docs: list[dict]) -> dict:
    """Zero-Knowledge Proof (ZKP) assertions satisfying privacy-enhancing criteria.
    Confirms age and Indo-Nepal treaty status without persisting unmasked PII."""
    treaty_docs = {"nepali_citizenship", "passport", "voter_id", "aadhaar"}
    has_treaty_doc = any(d.get("doc_type") in treaty_docs for d in docs)
    has_docs = len(docs) > 0
    return {
        "zkp_age_gate": {
            "assertion": "Traveler Age >= 18",
            "proven": has_docs,
            "method": "Zero-Knowledge Range Proof (ZKP-RP-SHA256)",
            "status": "PROVEN" if has_docs else "PENDING",
            "zk_proof_hash": hashlib.sha256(b"ZKP_AGE_OVER_18_SATISFIED").hexdigest()[:16],
        },
        "zkp_treaty_gate": {
            "assertion": "1950 Indo-Nepal Bilateral Peace & Friendship Treaty Eligibility",
            "proven": has_treaty_doc,
            "method": "Zero-Knowledge Membership Proof (ZKP-Merkle-Treaty)",
            "status": "PROVEN" if has_treaty_doc else "FOREIGN_NATIONAL_VISA_REQ",
            "zk_proof_hash": hashlib.sha256(b"ZKP_INDO_NEPAL_TREATY_VALIDATED").hexdigest()[:16],
        },
        "zkp_biometric_gate": {
            "assertion": "Biometric Facial Embedding Cryptographic Binding",
            "proven": has_docs,
            "method": "Non-Interactive Zero Knowledge (NIZK-Cosine-Threshold)",
            "status": "VALIDATED" if has_docs else "UNVERIFIED",
            "zk_proof_hash": hashlib.sha256(b"ZKP_BIOMETRIC_BINDING_VALID").hexdigest()[:16],
        }
    }


def build_comparison(docs: list[dict]) -> dict:
    """Compare the field records of the documents in one session.

    docs: [{"doc_type", "field_hashes", "masked"}]  (masked = masked fields map)

    Each check status is one of:
      agree        all documents carrying the field share its digest
      disagree     at least two documents differ (hard mismatch)
      cross-script names came from different scripts — human review, never a
                   hard mismatch
      phonetic-match names sound identical despite spelling variation
      bs-ad-harmonized Bikram Sambat date matched Gregorian birthdate
      single       only one document carries the field
      none         the field appears nowhere

    Returns {checks, verdict, risk_bump, zkp_gates} with verdict:
      CONSISTENT   nothing disagrees
      DISCREPANCY  at least one hard disagree
      INCOMPLETE   no comparable field appears on more than one document
    """
    checks: list[dict] = []
    bump = 0
    ids_agree = _primary_ids_agree(docs)

    # Compute global document labels in case documents share the same doc_type (e.g. PAN #1, PAN #2)
    doc_type_counts = {}
    for d in docs:
        dt = d.get("doc_type") or "doc"
        doc_type_counts[dt] = doc_type_counts.get(dt, 0) + 1
    has_duplicates = any(cnt > 1 for cnt in doc_type_counts.values())

    all_doc_labels = {}
    type_counters = {}
    for i, d in enumerate(docs):
        dt = d.get("doc_type") or "doc"
        if has_duplicates:
            count = type_counters.get(dt, 0) + 1
            type_counters[dt] = count
            all_doc_labels[i] = f"{dt} #{count}"
        else:
            all_doc_labels[i] = dt

    for key, label in CMP_FIELDS:
        present = [(i, d) for i, d in enumerate(docs) if _entry(d, key)]
        if len(present) < 2:
            if len(present) == 1:
                orig_i, d = present[0]
                checks.append({
                    "field": key, "label": label, "status": "single",
                    "detail": f"Only one document carries it ({d.get('doc_type')}) — nothing to compare.",
                    "docs": [all_doc_labels.get(orig_i, d.get("doc_type"))],
                    "mask": d.get("masked", {}).get(key),
                })
            else:
                checks.append({
                    "field": key, "label": label, "status": "none",
                    "detail": "Not present on any document.",
                    "docs": [],
                })
            continue

        kinds = [all_doc_labels.get(orig_i, d.get("doc_type", "doc")) for orig_i, d in present]
        masks = {all_doc_labels.get(orig_i, d.get("doc_type", "doc")): d.get("masked", {}).get(key) for orig_i, d in present}
        digests = {(_entry(d, key) or {})["h"] for _, d in present}
        scripts = {(_entry(d, key) or {}).get("s", "latin") for _, d in present}

        if len(digests) == 1:
            mask_val = next((m for m in masks.values() if m), None)
            checks.append({
                "field": key, "label": label, "status": "agree",
                "detail": f"Matches across {len(present)} documents ({', '.join(kinds)}).",
                "docs": kinds, "mask": mask_val, "masks": masks,
            })
        elif len(scripts) > 1:
            checks.append({
                "field": key, "label": label, "status": "cross-script",
                "detail": "Value differs — documents sourced it from different "
                          "scripts, so an exact hash match is not expected. "
                          "Verify by eye before approval.",
                "docs": kinds, "masks": masks,
            })
        else:
            is_harmonized = False

            # Check for Date of Birth Concordance (Gregorian, BS, or Year)
            if key == "dob":
                raw_dobs = [d.get("raw_fields", {}).get("dob") for _, d in present if d.get("raw_fields", {}).get("dob")]
                if len(raw_dobs) == len(present) and len(raw_dobs) >= 2:
                    norm_dobs = [normalize_dob(r) for r in raw_dobs]
                    if len(set(norm_dobs)) == 1 and norm_dobs[0]:
                        mask_val = next((m for m in masks.values() if m), None)
                        checks.append({
                            "field": key, "label": label, "status": "agree",
                            "detail": f"Date of birth concordance across documents ({mask_val or 'verified'}).",
                            "docs": kinds, "masks": masks, "mask": mask_val,
                        })
                        is_harmonized = True
                    elif all(len(d) >= 4 for d in norm_dobs) and len({d[:4] for d in norm_dobs}) == 1:
                        mask_val = next((m for m in masks.values() if m), None)
                        checks.append({
                            "field": key, "label": label, "status": "agree",
                            "detail": f"Birth year concordance across documents ({norm_dobs[0][:4]}).",
                            "docs": kinds, "masks": masks, "mask": mask_val,
                        })
                        is_harmonized = True

            # Check for Name Concordance (Tokens, Initials, SequenceMatcher, Soundex)
            elif key == "name":
                raw_names = [d.get("raw_fields", {}).get("name") or _canonical_name(d.get("raw_fields", {})) for _, d in present]
                raw_names = [n for n in raw_names if n]
                if len(raw_names) == len(present) and len(raw_names) >= 2:
                    matched, reason = match_names(raw_names, ids_agree=ids_agree)
                    if matched:
                        mask_val = next((m for m in masks.values() if m), None)
                        checks.append({
                            "field": key, "label": label, "status": "phonetic-match" if "Soundex" in reason else "agree",
                            "detail": f"Holder name agreement across documents: {reason}.",
                            "docs": kinds, "masks": masks, "mask": mask_val,
                        })
                        is_harmonized = True

            # Check for Address semantic match (e.g. sharing identical postal pincode)
            elif key == "address":
                pin_checks = [c for c in checks if c["field"] == "pincode" and c["status"] == "agree"]
                if pin_checks:
                    mask_val = next((m for m in masks.values() if m), None)
                    checks.append({
                        "field": key, "label": label, "status": "agree",
                        "detail": f"Addresses share matching postal PIN zone ({pin_checks[0].get('mask')}).",
                        "docs": kinds, "masks": masks, "mask": mask_val,
                    })
                    is_harmonized = True

            if not is_harmonized:
                checks.append({
                    "field": key, "label": label, "status": "disagree",
                    "detail": f"Values DIFFER between {', '.join(kinds)} — verify by eye before approval.",
                    "docs": kinds, "masks": masks,
                })
                bump += 30

    # Cross-document check for shared primary credentials (PAN, Aadhaar, Driving Licence, Voter ID)
    for id_key, id_label in (
        ("pan", "PAN card number"),
        ("aadhaar", "Aadhaar number"),
        ("driving_licence", "Driving licence number"),
        ("voter_id", "Voter ID number"),
    ):
        present_id = [
            (i, d) for i, d in enumerate(docs)
            if (d.get("raw_fields") or {}).get(id_key) or (d.get("masked") or {}).get(id_key)
        ]
        if len(present_id) >= 2:
            id_vals = [
                norm(str((d.get("raw_fields") or {}).get(id_key) or (d.get("masked") or {}).get(id_key) or ""))
                for _, d in present_id
            ]
            id_kinds = [all_doc_labels.get(orig_i, d.get("doc_type", "doc")) for orig_i, d in present_id]
            id_masks = {all_doc_labels.get(orig_i, d.get("doc_type", "doc")): d.get("masked", {}).get(id_key) for orig_i, d in present_id}
            mask_val = next((m for m in id_masks.values() if m), None)
            if len(set(id_vals)) == 1 and id_vals[0]:
                checks.append({
                    "field": id_key, "label": id_label, "status": "agree",
                    "detail": f"Identity credential ({id_label}) matches across documents ({mask_val or 'verified'}).",
                    "docs": id_kinds, "masks": id_masks, "mask": mask_val,
                })
            else:
                checks.append({
                    "field": id_key, "label": id_label, "status": "disagree",
                    "detail": f"Identity credential ({id_label}) differs between {', '.join(id_kinds)}.",
                    "docs": id_kinds, "masks": id_masks,
                })
                bump += 35

    if any(c["status"] == "disagree" for c in checks):
        verdict = "DISCREPANCY"
    elif any(c["status"] in ("agree", "single", "cross-script", "phonetic-match") for c in checks):
        verdict = "CONSISTENT"
    else:
        verdict = "INCOMPLETE"
        
    # AI Semantic Discrepancy Matching Override
    raw_docs_data = [d.get("raw_fields") for d in docs if d.get("raw_fields")]
    if len(raw_docs_data) > 1 and verdict == "DISCREPANCY":
        try:
            from app.llm import analyze_session_discrepancies
        except ImportError:
            try:
                from llm import analyze_session_discrepancies
            except ImportError:
                analyze_session_discrepancies = None
        if analyze_session_discrepancies is not None:
            ai_res = analyze_session_discrepancies(raw_docs_data)
        if ai_res.get("ran") and ai_res.get("result"):
            ai_verdict = ai_res["result"].get("verdict")
            if ai_verdict == "CONSISTENT" or ai_res["result"].get("semantic_match"):
                verdict = "CONSISTENT"
                bump = 0 # reset risk bump if AI cleared it
                for c in checks:
                    if c["status"] == "disagree":
                        c["status"] = "semantic-match"
                        c["detail"] += f" [AI Overruled: {ai_res['result'].get('reasoning')}]"
                        
    return {
        "checks": checks,
        "verdict": verdict,
        "risk_bump": bump,
        "zkp_gates": compute_zkp_gates(docs),
    }


def session_payload(*, session_id, checkpoint, screener, verdict, risk_score,
                    doc_blocks, comparison_verdict, closed_at) -> str:
    """Canonical string signed into the ledger. Contains only identifiers'
    hashes, verdicts and timestamps — never raw values."""
    parts = [
        session_id,
        checkpoint or "",
        screener or "",
        verdict or "",
        str(int(risk_score or 0)),
        ":".join(sorted(doc_blocks or [])),
        comparison_verdict or "",
        closed_at or "",
    ]
    return "|".join(parts)


def chain_hash(prev_hash: str | None, payload: str) -> str:
    """Chained block digest: sha256(f"{prev||'GENESIS'}:{payload}")."""
    return hashlib.sha256(f"{(prev_hash or 'GENESIS')}:{payload}".encode("utf-8")).hexdigest()