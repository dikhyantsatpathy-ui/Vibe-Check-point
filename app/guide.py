"""
Guided border-screening flow (SIH26188) — the "works at every checkpoint in
India" layer.

Every screening action is presented as a step-by-step protocol:
  * the OFFICER sees exactly what to do next (capture -> validate -> biometric
    -> compare -> decide);
  * the TRAVELLER sees the same protocol in plain, human language ("Please
    place your passport flat on the scanner..."), so the desk can run the
    traveller through capture even when no officer has done this checkpoint
    before.

The flow is nationality- and document-aware: a Nepali citizen crossing the
Indo-Nepal border gets the treaty-style expectation set (passport OR Nepali
citizenship certificate), a foreign national gets visa+passport expectations,
and an Indian citizen gets the domestic-ID expectations. Everything degrades
gracefully — unknown nationality/doc-type combos return a sensible default.

Zero-storage discipline is untouched: this module only builds *instructions*
and *expectations*; it never stores traveller data.
"""

from config import (
    CHECKPOINT_CLUSTERS,
    DOCUMENT_CATALOG,
    SUPPORTED_CHECKPOINTS,
    guided_steps,
)

# --------------------------------------------------------------------------- #
# Nationality-aware document expectations (Indo-Nepal / Indo-Bhutan / SAARC /
# foreign national — the actual traffic mix at SSB posts).
# --------------------------------------------------------------------------- #

# ISO 3166-1 alpha-2 nationality -> human label + expected document set.
NATIONALITIES = {
    "IN": ("India", "passport", "aadhaar", "driving_licence", "voter_id", "pan"),
    "NP": ("Nepal", "passport", "nepali_citizenship"),
    "BT": ("Bhutan", "passport", "bhutan_citizenship"),
    "BD": ("Bangladesh", "passport", "visa"),
    "MM": ("Myanmar", "passport", "visa"),
    "CN": ("China", "passport", "visa"),
    "PK": ("Pakistan", "passport", "visa"),
    "LK": ("Sri Lanka", "passport", "visa"),
    "AF": ("Afghanistan", "passport", "visa"),
    "US": ("United States", "passport", "visa"),
    "GB": ("United Kingdom", "passport", "visa"),
    "UA": ("Ukraine", "passport", "visa"),
    "RU": ("Russia", "passport", "visa"),
    "UNKNOWN": ("Other / unlisted", "passport", "visa"),
}

# Visa-exempt / treaty flows that change the document expectation.
DOMESTIC_TREATY_NATIONALS = {"IN", "NP", "BT"}  # Indo-Nepal & Indo-Bhutan treaty
SAARC_EXEMPT = {"NP", "BT", "MV", "LK", "BD"}   # SAARC visa-liberalised subset


def nationality_label(code: str) -> str:
    code = (code or "UNKNOWN").strip().upper()[:2]
    return NATIONALITIES.get(code, NATIONALITIES["UNKNOWN"])[0]


def expected_documents(nationality: str, doc_types: list[str] | None = None,
                       mode: str = "land") -> list[str]:
    """Documents this traveller is expected to present, in capture order.

    `doc_types` (what the traveller declared, or what they have on them) wins
    when provided; otherwise the nationality defaults apply. For treaty
    nationals at a land checkpoint, a domestic ID satisfies the entry document
    requirement instead of a passport — mirroring real SSB desk practice.
    """
    nat = (nationality or "UNKNOWN").strip().upper()[:2]
    _, *defaults = NATIONALITIES.get(nat, NATIONALITIES["UNKNOWN"])
    merged = list(doc_types) if doc_types else list(defaults)
    if not merged:
        merged = list(defaults)
    # Treaty nationals may travel land borders with domestic identity docs.
    if nat in DOMESTIC_TREATY_NATIONALS and mode == "land":
        if "passport" in merged and not any(d in merged for d in
                                            ("nepali_citizenship", "aadhaar", "voter_id", "driving_licence")):
            pass  # passport alone is always acceptable
    seen: list[str] = []
    for d in merged:
        if d not in seen:
            seen.append(d)
    return seen


def traveller_brief(nationality: str, doc_types: list[str] | None = None,
                    mode: str = "land") -> dict:
    """Short plain-language protocol for the traveller display / the desk's
    first contact with the person, in the traveller's own terms."""
    docs = expected_documents(nationality, doc_types, mode)
    labels = [DOCUMENT_CATALOG.get(d, {}).get("label", d) for d in docs]
    nat_label = nationality_label(nationality)
    treaty = nationality in DOMESTIC_TREATY_NATIONALS and mode == "land"
    lines = [
        f"Welcome. Please present your {' / '.join(labels)} for screening.",
    ]
    if treaty:
        lines.append("As a treaty national you may travel with a national ID "
                     "in addition to (or instead of) a passport.")
    lines.append("Please step to the scanner and place your document flat, "
                 "face up, in full view.")
    return {
        "nationality": nat_label,
        "treaty_national": treaty,
        "expected_documents": docs,
        "steps": [{"order": i + 1, "text": t} for i, t in enumerate(lines)],
    }


def flow_for(*, checkpoint: str = "", doc_type: str = "other",
             nationality: str = "UNKNOWN") -> dict:
    """Full guided protocol for one screening action at one checkpoint.

    Returns officer steps, traveller steps, document expectations, and the
    checkpoint context — everything the desk UI needs to guide both sides.
    """
    cluster = "LAND_NEPAL"
    mode = "land"
    for key, cfg in CHECKPOINT_CLUSTERS.items():
        if checkpoint in cfg["icps"]:
            cluster = key
            mode = cfg["mode"]
            break
    steps = guided_steps(mode, doc_type, nationality)
    brief = traveller_brief(nationality, [doc_type] if doc_type != "other" else None, mode)
    return {
        "checkpoint": checkpoint or "",
        "cluster": cluster,
        "cluster_label": CHECKPOINT_CLUSTERS[cluster]["label"],
        "mode": mode,
        "doc_type": doc_type,
        "doc_label": DOCUMENT_CATALOG.get(doc_type, DOCUMENT_CATALOG["other"])["label"],
        "nationality": nationality,
        "nationality_label": brief["nationality"],
        "expected_documents": brief["expected_documents"],
        "officer_steps": steps,
        "traveller_steps": brief["steps"],
        "capture_hint": DOCUMENT_CATALOG.get(doc_type, DOCUMENT_CATALOG["other"])["hint"],
    }


def checkpoint_catalog() -> dict:
    """Public checkpoint catalog for the desk / gate UI."""
    return {
        "clusters": [
            {
                "key": key,
                "label": cfg["label"],
                "mode": cfg["mode"],
                "checkpoints": cfg["icps"],
            }
            for key, cfg in CHECKPOINT_CLUSTERS.items()
        ],
        "all": SUPPORTED_CHECKPOINTS,
        "modes": {"land": "Land border (SSB)", "air": "International airport",
                  "sea": "Sea port", "rail": "Rail checkpoint"},
    }


def document_catalog() -> dict:
    """Public identity/travel document catalog (domestic + international)."""
    return {
        key: {"label": cfg["label"], "field": cfg["field"], "hint": cfg["hint"]}
        for key, cfg in DOCUMENT_CATALOG.items()
    }


def nationality_catalog() -> list[dict]:
    return [{"code": k, "label": v[0]} for k, v in NATIONALITIES.items()]