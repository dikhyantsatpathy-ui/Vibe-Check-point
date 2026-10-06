"""
Central configuration for the SSB Border Screening console (SIH26188).

One source of truth for:
  * timezone handling (UTC storage -> IST display, per the desk's requirement)
  * checkpoint catalog — every Indian border cluster SSB screens at
  * identity/travel document catalog (domestic + international)
  * guided-screening flow definitions (officer steps + traveller steps)
  * operational limits (uploads, body sizes, timeouts, page sizes)

Keeps magic numbers out of routes/screening logic and makes the "works at
every checkpoint in India" behaviour data-driven.

Storage stays UTC (chronological sort + hash-chain integrity depend on a
stable, lexicographically sortable timestamp); every API response also
carries `*_ist` fields and the frontend renders IST.
"""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# --------------------------------------------------------------------------- #
# Time helpers (UTC store -> IST display)
# --------------------------------------------------------------------------- #

_UTC_FMT = "%Y-%m-%d %H:%M:%S UTC"
_IST_FMT = "%Y-%m-%d %H:%M:%S IST"


def now_utc() -> str:
    """Canonical store timestamp: 'YYYY-MM-DD HH:MM:SS UTC' (sortable)."""
    return datetime.now(timezone.utc).strftime(_UTC_FMT)


def to_ist(utc_str: str | None) -> str | None:
    """'YYYY-MM-DD HH:MM:SS UTC' -> 'YYYY-MM-DD HH:MM:SS IST'.

    Accepts ISO 8601 with 'Z'/'+00:00' as well. Returns None for unparseable
    input so callers can degrade instead of exploding on legacy rows."""
    if not utc_str:
        return None
    s = str(utc_str).strip()
    try:
        if s.endswith("UTC") or " " in s:
            naive = datetime.strptime(s, _UTC_FMT).replace(tzinfo=timezone.utc)
        else:
            naive = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if naive.tzinfo is None:
                naive = naive.replace(tzinfo=timezone.utc)
        return naive.astimezone(IST).strftime(_IST_FMT)
    except Exception:
        return utc_str


def utc_to_epoch(utc_str: str | None) -> int | None:
    """Parse a stored UTC string (or ISO) into a Unix epoch (seconds)."""
    if not utc_str:
        return None
    s = str(utc_str).strip()
    try:
        if s.endswith("UTC") or " " in s:
            naive = datetime.strptime(s, _UTC_FMT).replace(tzinfo=timezone.utc)
        else:
            naive = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if naive.tzinfo is None:
                naive = naive.replace(tzinfo=timezone.utc)
        return int(naive.timestamp())
    except Exception:
        return None


def ist_hour_of_day(utc_str: str | None) -> int | None:
    """0-23 hour of the day the event happened IN IST (for shift analytics)."""
    ts = utc_to_epoch(utc_str)
    if ts is None:
        return None
    return int(datetime.fromtimestamp(ts, IST).strftime("%H"))


# --------------------------------------------------------------------------- #
# Checkpoint catalog — every border cluster SSB screens at
# --------------------------------------------------------------------------- #

# Specimen real ICPs (Indo-Nepal + Indo-Bhutan land borders), plus air/sea/rail.
CHECKPOINT_CLUSTERS = {
    "LAND_NEPAL": {
        "label": "Integrated Check Post (Land Border)",
        "mode": "land",
        "icps": [
            "Sunauli", "Raxaul", "Jogbani", "Rupaidiha", "Banbasa", "Barhni",
            "Gauriphanta", "Panitanki", "Galgalia", "Raniganj", "Bhitthamore",
            "Nautanwa", "Katauna", "Rajganj", "Bhimnagar", "Thakurganj",
            "Sanauli", "Laukaha", "Bathnaha", "Sursand",
        ],
    },
    "LAND_BHUTAN": {
        "label": "Indo-Bhutan Land (SSB)",
        "mode": "land",
        "icps": [
            "Jaigaon", "Uttarkanya", "Samdrup Jongkhar (Darranga)", "Gelephu",
            "Sarbhang", "Rangla", "Chakung", "Kakarbhitta (Panitanki)",
        ],
    },
    "AIR": {
        "label": "International Airports (SSB/CISF)",
        "mode": "air",
        "icps": [
            "IGI Delhi", "Kolkata Netaji", "Patna Jay Prakash", "Varanasi",
            "Guwahati", "Bagdogra", "Gaya", "Lucknow", "Mumbai T2", "Hyderabad",
        ],
    },
    "SEA": {
        "label": "Sea Ports (SSB/CISF)",
        "mode": "sea",
        "icps": ["Kolkata Port", "Haldia", "Paradip"],
    },
    "RAIL": {
        "label": "Rail checkpoints (SSB)",
        "mode": "rail",
        "icps": ["Raxaul Rail", "Jogbani Rail", "Nautanwa Rail", "Bathnaha Rail"],
    },
}

SUPPORTED_CHECKPOINTS = sorted(
    {icp for cluster in CHECKPOINT_CLUSTERS.values() for icp in cluster["icps"]}
)

CHECKPOINT_MODE = {
    icp: cluster["mode"]
    for cluster in CHECKPOINT_CLUSTERS.values()
    for icp in cluster["icps"]
}

# --------------------------------------------------------------------------- #
# Document catalog — domestic + international
# --------------------------------------------------------------------------- #

# doc_type key -> display label, expected identifier field, capture hint.
DOCUMENT_CATALOG = {
    "passport": {
        "label": "Passport (any nationality)",
        "field": "passport",
        "hint": "Open the data page face-up; MRZ at the bottom must be fully visible.",
    },
    "visa": {
        "label": "Visa / permit sticker",
        "field": "passport",
        "hint": "Place the visa page flat; keep the sticker and MRZ band in frame.",
    },
    "aadhaar": {
        "label": "Aadhaar (UIDAI)",
        "field": "aadhaar",
        "hint": "Front of card, no cover/sleeve reflections.",
    },
    "pan": {
        "label": "PAN card",
        "field": "pan",
        "hint": "Front of card; the 10-char PAN must be legible.",
    },
    "driving_licence": {
        "label": "Driving Licence (India)",
        "field": "driving_licence",
        "hint": "Licence side with photo + number visible.",
    },
    "voter_id": {
        "label": "Voter ID (EPIC)",
        "field": "voter_id",
        "hint": "Front of card with 10-char EPIC number.",
    },
    "nepali_citizenship": {
        "label": "Nepali Citizenship Certificate",
        "field": "citizenship_number",
        "hint": "Inner pages with photograph and personal details.",
    },
    "bhutan_citizenship": {
        "label": "Bhutanese Citizenship Identity Card",
        "field": "citizenship_number",
        "hint": "Front side of card with 11-digit CID and photo.",
    },
    "rc": {
        "label": "Passport (RC) or travel document",
        "field": "passport",
        "hint": "Data page with MRZ.",
    },
    "other": {
        "label": "Other / unidentified",
        "field": None,
        "hint": "Scan the document; the system will attempt type identification.",
    },
}

SCREEN_DOC_TYPES = list(DOCUMENT_CATALOG.keys())

# Identity classes recognised by the trained doc-type classifier (ONNX).
DOC_TYPE_CLASSES = [
    "passport", "aadhaar", "pan", "driving_licence",
    "voter_id", "nepali_citizenship", "bhutan_citizenship", "other",
]

# --------------------------------------------------------------------------- #
# Guided flow definitions (per mode + doc type)
# --------------------------------------------------------------------------- #

def guided_steps(mode: str = "land", doc_type: str = "passport",
                 nationality: str = "IN") -> list[dict]:
    """The screening protocol for one (mode, doc_type, nationality) combo.

    Returns officer steps and traveller-facing instructions so the desk can
    walk the traveller through capture and the officer through verification
    in lock-step. Data-driven; extend here to add flows.
    """
    doc = DOCUMENT_CATALOG.get(doc_type, DOCUMENT_CATALOG["other"])
    face_required = doc_type in ("passport", "visa", "rc", "nepali_citizenship") \
        or mode != "land"
    steps = [
        {
            "order": 1,
            "phase": "intake",
            "title": "Open traveller session",
            "officer": "Open a session, record nationality, purpose of travel and the documents the traveller declares.",
            "traveller": "Please state your name, nationality and purpose of travel.",
        },
        {
            "order": 2,
            "phase": "capture",
            "title": f"Capture {doc['label']}",
            "officer": f"Scan the document clean and in focus. {doc['hint']}",
            "traveller": "Please place your document on the scanner / hold it steady facing the camera.",
        },
        {
            "order": 3,
            "phase": "verify",
            "title": "Validate & analyse",
            "officer": "Auto run: extract fields -> validate checksums/MRZ -> tamper forensics -> AI/edit screening.",
            "traveller": "Please wait while the system checks the document.",
        },
    ]
    if face_required:
        steps.append({
            "order": 4,
            "phase": "biometric",
            "title": "Live face capture",
            "officer": "Capture a live webcam still of the holder and confirm the portrait match.",
            "traveller": "Please look into the camera without glasses/headgear covering your face.",
        })
    steps.append({
        "order": len(steps) + 1,
        "phase": "decide",
        "title": "Compare & decide",
        "officer": "Review cross-document agreement, then Approve (signs the ledger) or Flag for a supervisor.",
        "traveller": "Please wait for the officer's decision.",
    })
    return steps


# --------------------------------------------------------------------------- #
# Operational limits
# --------------------------------------------------------------------------- #

MAX_UPLOAD_BYTES = 8 * 1024 * 1024          # multipart hard cap (matches route)
MAX_PAGE_SIZE = 200                          # list endpoints
REMOTE_ML_TIMEOUT = float(os.getenv("ML_TIMEOUT", "6.0"))   # s; fail fast offline
REMOTE_ML_CONNECT = float(os.getenv("ML_CONNECT_TIMEOUT", "2.0"))
SCREEN_DEFAULT_DOC_TYPE = "other"

# --------------------------------------------------------------------------- #
# Modules / detector gates
# --------------------------------------------------------------------------- #

# Screen the runtime the same way the tests do: prefer the local ONNX engines
# when present, else degrade to remote (short timeout) then heuristics.
MODEL_DIRS = {
    "app_models": os.getenv("APP_MODELS_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "models"),
    "data_models": os.getenv("DATA_MODELS_DIR") or os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "models")),
    "ml_models": os.getenv("ML_MODELS_DIR") or os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "ml_service", "models")),
}

# Authorized officer post/designation role titles used by the guided flow UI.
OFFICER_ROLES = {
    "desk": "Desk Screening Officer",
    "supervisor": "Supervisory Officer",
    "admin": "Border Station Admin",
}

# --------------------------------------------------------------------------- #
# Calibrated Decision Layer Thresholds (derived from validation splits)
# --------------------------------------------------------------------------- #
SCREENING_THRESHOLDS = {
    # Doc-type classification confidence below which document requires human review
    "DOCTYPE_CONFIDENCE_REVIEW": float(os.getenv("DOCTYPE_CONFIDENCE_REVIEW", "0.75")),
    # Risk score bands for overall decision
    "RISK_MAX_GENUINE": int(os.getenv("SCREENING_RISK_MAX_GENUINE", "25")),
    "RISK_MIN_REJECT": int(os.getenv("SCREENING_RISK_MIN_REJECT", "55")),
    # Forensics / tampering risk threshold
    "TAMPER_RISK_FLAG": float(os.getenv("TAMPER_RISK_FLAG", "50.0")),
    # Face match similarity threshold for biometric verification
    "FACE_SIMILARITY_MIN": float(os.getenv("FACE_SIMILARITY_MIN", "0.60")),
}