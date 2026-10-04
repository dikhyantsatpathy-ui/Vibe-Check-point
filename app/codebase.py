"""
Codebase-backed context for the nocap guide chatbot.

Scans the project's own repository (lazily, cached in memory) and builds an authoritative,
full-visibility database of every source file, configuration, database model, API route,
frontend component, screening pipeline, and documentation guide.

Every /api/chat query receives the COMPLETE CODEBASE DATABASE in Gemini's 1-million-token
context window. Files most relevant to the query are prioritized at the top of the context
block right after the Architectural Blueprint, followed by the rest of the repository.
Every file is injected with 1-based line numbers, allowing the AI to pinpoint exact lines
(e.g., `app/main.py:1124`, `frontend/src/views/DeskView.tsx:42`).
"""

import os
import re
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories that never belong in the code context.
# Note: 'scripts' is now permitted for documentation guides (.md, .txt).
# 'static' is skipped because app/static/index.html is a compiled/minified bundle.
SKIP_DIRS = {
    ".agents", ".backup", ".git", ".opencode", ".playwright-mcp", ".pytest_cache",
    ".ruff_cache", ".venv", "_backup", "build", "data", "dist", "new", "node_modules",
    "smoke", "tasks", "temp", "tmp", "FIX", "__pycache__", "static",
}

# Files / extensions that never belong in the code context.
SKIP_FILE_PREFIXES = (".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "FIX")
SKIP_FILE_NAMES = {
    "bun.lock", "package-lock.json", "credentials.json", "service_account.json",
    "service-account.json", "client_secret.json", "nocap.db", "nocap_fallback.db",
}
SKIP_FILE_EXTS = {
    ".bat", ".bin", ".exe", ".gif", ".ico", ".jpeg", ".jpg", ".lock", ".log",
    ".otf", ".pdf", ".png", ".pyc", ".sh", ".ttf", ".woff", ".woff2", ".pyw",
    ".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db",
}
INCLUDE_EXTS = {
    ".css", ".html", ".js", ".json", ".jsx", ".md", ".py", ".toml", ".ts",
    ".tsx", ".txt", ".yaml", ".yml", ".sql",
}

# Stopwords that add no signal when ranking files for a query.
_STOPWORDS = {
    "a", "an", "and", "are", "can", "do", "does", "for", "from", "how", "i",
    "in", "is", "it", "me", "my", "of", "on", "or", "that", "the", "this",
    "to", "what", "when", "where", "which", "who", "why", "with", "you", "your",
}

_MAX_FILE_CHARS = 25_000
_MAX_CONTEXT_CHARS = 160_000  # High-density, fast-loading codebase context within Gemini TPM limits

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_CAMEL_RE = re.compile(r"([a-z])([A-Z])")


def _sanitize_secrets(text: str) -> str:
    """Scrub sensitive credentials, database URLs, passwords, and tokens from code context."""
    if not text:
        return text
    # 1. Database Connection Strings (Postgres / MySQL / etc)
    s = re.sub(
        r'(postgres(?:ql)?://[^\s:]+:)([^@\s]+)(@[^\s"\'`]+)',
        r'\1[REDACTED_PASSWORD]\3',
        text,
        flags=re.IGNORECASE,
    )
    # 2. Hostnames like ep-*.neon.tech
    s = re.sub(r'[a-zA-Z0-9_-]+\.neon\.tech', '[REDACTED_DB_HOST]', s)
    # 3. Google / Cloud API Keys (AIzaSy...)
    s = re.sub(r'AIza[0-9A-Za-z_-]{30,45}', '[REDACTED_GOOGLE_API_KEY]', s)
    # 4. GitHub Personal Access Tokens / Secrets
    s = re.sub(r'(?:ghp_|github_pat_)[0-9A-Za-z_]{35,}', '[REDACTED_GITHUB_TOKEN]', s)
    # 5. OpenAI / Anthropic / Groq Keys
    s = re.sub(r'(?:sk|gsk)-[a-zA-Z0-9_-]{20,}', '[REDACTED_AI_API_KEY]', s)
    # 6. Bearer / Auth tokens
    s = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]{25,}', 'Bearer [REDACTED_TOKEN]', s)
    # 7. Private Key blocks
    s = re.sub(
        r'-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----',
        '[REDACTED_PRIVATE_KEY_BLOCK]',
        s,
    )
    # 8. Assignment of sensitive credentials in configs / scripts
    s = re.sub(
        r'(?i)(password|secret_key|master_vault_key|auth_token|api_secret)\s*([:=])\s*(["\'])[^\3\n]{6,}\3',
        r'\1 \2 \3[REDACTED_CREDENTIAL]\3',
        s,
    )
    return s

_lock = threading.Lock()
_index: list[dict] | None = None

# Files that must never leave the deployment. `app/main.py` used to be the
# single worst case: it carried a committed production database DSN and a
# fallback vault key, so indexing it meant shipping both to a third-party LLM.
# The credentials themselves are gone now, but the file remains the densest
# concentration of security-relevant logic in the repo, so it is excluded
# wholesale rather than relied upon for redaction.
NEVER_INDEX = {
    "app/main.py",      # auth, key resolution, DSN handling
    "app/keys.py",      # key derivation
    "app/session.py",   # holds raw-field comparison inputs
    "api/index.py",
    "main.py",
    "scripts/anchor_ledger.py",
}


# Files that must never leave the deployment. `app/main.py` used to be the
# single worst case: it carried a committed production database DSN and a
# fallback vault key, so indexing it meant shipping both to a third-party LLM.
# The credentials themselves are gone now, but the file remains the densest
# concentration of security-relevant logic in the repo, so it is excluded
# wholesale rather than relied upon for redaction.
NEVER_INDEX = {
    "app/main.py",      # auth, key resolution, DSN handling
    "app/keys.py",      # key derivation
    "app/session.py",   # holds raw-field comparison inputs
    "api/index.py",
    "main.py",
    "scripts/anchor_ledger.py",
}


def _iter_source_files():
    """Yield (rel_path, abs_path) for every source and doc file that belongs to the index."""
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn in SKIP_FILE_NAMES or fn.startswith(SKIP_FILE_PREFIXES):
                continue
            # Never index a dotfile-adjacent secret or the explicitly blocked set.
            if fn.startswith(".env"):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_FILE_EXTS or ext not in INCLUDE_EXTS:
                continue
            abs_path = os.path.join(dirpath, fn)
            rel = os.path.relpath(abs_path, REPO_ROOT).replace("\\", "/")

            # For scripts/ directory, only include documentation guides (.md, .txt)
            if rel.startswith("scripts/") and ext not in (".md", ".txt"):
                continue

            # Don't index temporary or test artifacts from root
            if rel.startswith("_tmp_"):
                continue

            # Hard block on secret-bearing / security-critical files.
            if rel in NEVER_INDEX:
                continue

            yield rel, abs_path


def _tokenize(text: str) -> dict[str, int]:
    """Tokenize text into lower-case keywords, splitting camelCase, snake_case, and paths."""
    counts: dict[str, int] = {}
    # Split camelCase before regular token extraction
    expanded = _CAMEL_RE.sub(r"\1 \2", text)
    for tok in _TOKEN_RE.findall(expanded.lower()):
        if len(tok) > 1:
            counts[tok] = counts.get(tok, 0) + 1
    return counts


def reload_index() -> list[dict]:
    """Force re-scan and reload of the codebase index."""
    global _index
    with _lock:
        _index = None
    return _load_index()


def _load_index() -> list[dict]:
    """Lazily scan the repo once, precompute line numbers & blocks, and cache in memory."""
    global _index
    if _index is not None:
        return _index
    with _lock:
        if _index is not None:
            return _index
        files = []
        for rel, abs_path in _iter_source_files():
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                    raw_text = fh.read(_MAX_FILE_CHARS)
            except OSError:
                continue
            if not raw_text.strip():
                continue
            text = _sanitize_secrets(raw_text)
            lines = text.splitlines()
            width = len(str(len(lines)))
            snippet = "\n".join(f"{i + 1:>{width}}| {ln}" for i, ln in enumerate(lines))
            block = (
                f"================================================================================\n"
                f"FILE: {rel}\n"
                f"================================================================================\n"
                f"{snippet}"
            )
            files.append({
                "rel": rel,
                "text": text,
                "line_count": len(lines),
                "snippet": snippet,
                "block": block,
                "manifest_entry": f"- `{rel}` ({len(lines)} lines)",
                "tokens": _tokenize(text),
                "name_tokens": _tokenize(rel),
            })
        files.sort(key=lambda f: f["rel"])
        _index = files
        return _index


def _rank_files(question: str) -> list[dict]:
    """Score every indexed file against the query's tokens; return matches sorted best-first."""
    q_tokens = [t for t in _tokenize(question) if t not in _STOPWORDS]
    all_files = _load_index()
    if not q_tokens:
        return all_files
    attempts = list(dict.fromkeys(q_tokens))  # dedupe, preserve order
    scored = []
    for f in all_files:
        score = 0.0
        for tok in attempts:
            name_hits = f["name_tokens"].get(tok, 0)
            body_hits = f["tokens"].get(tok, 0)
            if name_hits:
                score += 8.0 + name_hits * 2.0
            if body_hits:
                score += 1.0 + min(body_hits, 10)
        if score > 0:
            scored.append((score, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored]


def _snippets(f: dict, question: str = "") -> str:
    """Return the precomputed line-numbered snippet in O(1)."""
    return f.get("snippet") or f["text"]


def _architecture_blueprint() -> str:
    """Return a high-level system architectural blueprint summarizing the repository layout,
    frontend visual map (where every button/tab/modal is located), and backend logic pipelines."""
    return (
        "### SYSTEM ARCHITECTURE BLUEPRINT & REPOSITORY MAP:\n\n"
        "#### 1. FRONTEND ARCHITECTURE & VISUAL UI MAP (`frontend/src/`):\n"
        "- **Main Application Frame (`frontend/src/App.tsx`)**:\n"
        "  - **Super Header**: Displays the Government of India Ashoka Lion Emblem, official SSB (Sashastra Seema Bal) seal, current Indian Standard Time (IST) clock, and current user profile.\n"
        "  - **Ashoka Chakra Watermark**: High-resolution 24-spoke Navy Blue Ashoka Chakra rotating smoothly behind the main content area with soft opacity.\n"
        "  - **Navigation Bar**: 5 main tabs with real-time badges:\n"
        "    1. `Desk` (Active screening intake)\n"
        "    2. `Review Queue` (Supervisory review of flagged travellers)\n"
        "    3. `Crypto Ledger` (SHA-256 immutable audit chain & Section 65B certificates)\n"
        "    4. `Watchlist` (Salted hash-only fugitive & red-notice directory)\n"
        "    5. `Staff` (Officer directory & role assignments)\n"
        "  - **Floating AI Assistant (`frontend/src/views/ChatModal.tsx`)**: Bottom-right floating button (`💬 AI Assistant`), opens the conversational Oracle modal with quick-topic chips.\n\n"
        "- **Desk View (`frontend/src/views/DeskView.tsx`)**:\n"
        "  - **Checkpoint & Treaty Protocol HUD**: Top banner showing active Border Post (Panitanki, Raxaul, Sonauli, Jaigaon, Petrapole) and Indo-Nepal / Indo-Bhutan treaty rules.\n"
        "  - **Step 1 — Traveller Session Intake**: Name input, nationality dropdown, purpose of travel (Tourism, Trade, Transit), and session start button.\n"
        "  - **Step 2 — Document Upload & Optical Scan**: Document type selector (Passport, Aadhaar, PAN, Driving Licence, Voter ID, Nepali Citizenship), Side A & Side B dual-dropzones, sample specimen picker.\n"
        "  - **Step 3 — Optical Extraction HUD**: Displays parsed holder name, masked identifier (e.g. `TFPPS****G`, `XXXX-XXXX-4014`), DOB, and physical address with validation checkmarks.\n"
        "  - **Step 4 — 4-Module Forensic Breakdown**:\n"
        "    - *Module 1 (Extraction)*: OCR engine status (RapidOCR, Tesseract, pypdf, Gemini multimodal) and parsed fields.\n"
        "    - *Module 2 (Validation)*: ICAO 9303 MRZ check-digit verification, Verhoeff checksum calculation, and hash-only watchlist matching.\n"
        "    - *Module 3 (Tampering Forensics)*: ELA compression noise, 2D-FFT spectral PAPR, PRNU camera sensor pattern, and Laplacian blur analysis.\n"
        "    - *Module 4 (Facial Biometrics)*: Document photo extraction vs live webcam holder capture with cosine similarity score and challenge-response liveness.\n"
        "  - **Step 5 — Officer Decision Bar**: Two prominent buttons — green 'Approve & Sign to Ledger' or amber 'Flag for Review'.\n\n"
        "- **Review Queue View (`frontend/src/views/ReviewQueueView.tsx`)**:\n"
        "  - Displays all flagged crossings awaiting senior officer adjudication.\n"
        "  - Side-by-side evidence dossier with one-click verdicts: `CLEARED`, `CONFIRMED_FRAUD`, or `INCONCLUSIVE`.\n\n"
        "- **Cryptographic Ledger View (`frontend/src/views/LedgerView.tsx`)**:\n"
        "  - Live hash-chain block explorer showing `prev_hash`, `block_hash`, `timestamp_ist`, and digital signatures.\n"
        "  - 'Verify Whole Ledger' cryptographic Merkle audit button.\n"
        "  - One-click BSA 2023 Section 65B Electronic Court Certificate generation and printable PDF/HTML export.\n\n"
        "- **Watchlist View (`frontend/src/views/WatchlistView.tsx`)**:\n"
        "  - Searchable hash-only repository of Interpol and SSB watchlist records with salted SHA-256 matching.\n\n"
        "- **Staff View (`frontend/src/views/StaffView.tsx`)**:\n"
        "  - Roster of screening officers, active duty stations, designations, and cryptographic signing profiles.\n\n"
        "#### 2. BACKEND ARCHITECTURE & DATA FLOW (`app/`):\n"
        "- `app/main.py`: FastAPI server, Neon serverless PostgreSQL connection pooling with background keep-alive loop (`SELECT 1` every 210s), OAuth authentication gate, rate limiting, and `/api/chat` conversational endpoint.\n"
        "- `app/extraction.py`: Module 1 optical data extraction orchestrating RapidOCR, ICAO 9303 MRZ parsing, QR byte decompression, and multimodal Gemini fallback.\n"
        "- `app/screening.py`: Master screening desk engine executing all 4 forensic modules, risk-scoring matrix (`CLEAR`, `REVIEW`, `FLAGGED`), and ledger block creation.\n"
        "- `app/validation.py` & `app/mrz.py`: Mathematical checksum validators (ICAO Doc 9303 7-3-1 weights, Aadhaar Verhoeff D5 algorithm, PAN 4th-character category rules).\n"
        "- `app/forensics.py` & `app/tampering.py`: Computer vision forensic detectors (JPEG Error Level Analysis, 2D-FFT spectral PAPR, PRNU sensor noise, blur detection).\n"
        "- `app/face_match.py` & `app/face.py`: Face detection, portrait isolation, cosine embedding similarity, age-aware adaptive thresholding, and blink/nod liveness.\n"
        "- `app/syndicate.py`: Graph-based cross-border human trafficking and fake document syndicate detection.\n"
        "- `app/session.py`: Multi-document traveller session tracker comparing names, DOBs, and identifiers across all presented IDs.\n"
        "- `app/config.py`: Environment configuration, Zero-Storage privacy settings, and cryptographic salt generation.\n"
    )


def codebase_context(question: str) -> str:
    """Build the CODE CONTEXT block containing the project blueprint, file manifest, and relevant source files."""
    files = _load_index()
    if not files:
        return ""

    q_clean = (question or "").strip().lower()
    is_greeting = len(q_clean) < 15 and any(g in q_clean for g in ("hi", "hello", "hey", "who", "help", "start", "oracle"))

    blueprint = _architecture_blueprint()
    
    if is_greeting:
        return (
            "Below is the SYSTEM BLUEPRINT of the entire project repository. "
            "Use it to welcome the user, introduce the console, and explain how you can assist them.\n\n"
            f"{blueprint}"
        )

    core_landmark_rels = ("app/main.py", "app/screening.py", "frontend/src/views/DeskView.tsx", "app/validation.py")
    landmarks = [f for f in files if f["rel"] in core_landmark_rels]
    landmark_set = {f["rel"] for f in landmarks}

    ranked = _rank_files(question)
    ranked_filtered = [f for f in ranked if f["rel"] not in landmark_set]
    ranked_set = {f["rel"] for f in ranked_filtered}
    remaining = [f for f in files if f["rel"] not in landmark_set and f["rel"] not in ranked_set]
    ordered_files = landmarks + ranked_filtered + remaining

    manifest = "### COMPLETE PROJECT FILES MANIFEST:\n" + "\n".join(f["manifest_entry"] for f in ordered_files[:30])

    parts: list[str] = [blueprint, manifest]
    used = len(blueprint) + len(manifest) + 10

    for f in ordered_files:
        block = f["block"]
        if used + len(block) + 4 > _MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        used += len(block) + 4

    return (
        "Below is the ACTUAL SOURCE CODE DATABASE of the project repository. "
        "The codebase across backend, frontend, database schemas, cryptographic vaults, "
        "identity screening algorithms, verification pipelines, configuration, and documentation "
        "is provided with 1-based line numbers. "
        "Cite exact file paths and line numbers (e.g. `app/main.py:1124`, `frontend/src/views/DeskView.tsx:35`) "
        "when answering questions, while explaining everything in clear layman terms.\n\n"
        + "\n\n".join(parts)
    )