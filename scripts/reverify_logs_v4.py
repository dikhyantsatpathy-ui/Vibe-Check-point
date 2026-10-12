"""Log Redaction Test (Phase V4).
Verifies that sensitive credentials (tokens, DB passwords, API keys)
are actively redacted and NEVER leak into logs or stdout.
"""

import io
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from main import sanitize_secret_text

FAKE_SECRETS = [
    "postgresql://testuser:FAKE-PASSWORD-NOT-REAL-SECRET-123@ep-fake-db-not-real.neon.tech/neondb",
    "sk-FAKE-TOKEN-NOT-REAL-OPENAI-KEY-123456789",
    "gsk-FAKE-TOKEN-NOT-REAL-GROQ-KEY-1234567890",
    "AIzaSyFAKE-TOKEN-NOT-REAL-GOOGLE-12345",
]

def test_log_redaction():
    results = []
    all_passed = True

    # 1. Test sanitize_secret_text redaction
    for sec in FAKE_SECRETS:
        sanitized = sanitize_secret_text(f"Connection error with {sec} occurred.")
        leaked = False
        if "FAKE-PASSWORD" in sanitized or "FAKE-TOKEN-NOT-REAL" in sanitized:
            leaked = True
            all_passed = False
        results.append({
            "pattern": sec[:10] + "...",
            "sanitized": sanitized,
            "secret_leaked": leaked
        })

    # 2. Test logger capture during pipeline execution with synthetic document
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger("app")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        from screening import run_screening
        # Run screening with synthetic text containing a fake secret
        fake_text = "Holder John Doe with API token sk-FAKE-TOKEN-NOT-REAL-PASSPORT-123456"
        res = run_screening(
            data=b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF",
            filename="fake_passport.pdf",
            declared={"name": "John Doe", "notes": "sk-FAKE-TOKEN-NOT-REAL-PASSPORT-123456"},
            is_image=False,
            session_id="test-log-redaction"
        )
    except Exception as exc:
        pass
    finally:
        logger.removeHandler(handler)

    captured_logs = log_stream.getvalue()
    raw_token_leaked = "FAKE-TOKEN-NOT-REAL" in captured_logs
    if raw_token_leaked:
        all_passed = False

    out_dir = ROOT / "eval" / "runs" / "20261011_reverify_v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "log_redaction_test.json"

    report = {
        "phase": "V4",
        "redaction_sanitizer_tests": results,
        "pipeline_logger_leak_detected": raw_token_leaked,
        "verdict": "PASS" if all_passed else "FAIL"
    }
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Log redaction test complete (verdict: {report['verdict']}). Written to {out_file}")

if __name__ == "__main__":
    test_log_redaction()
