#!/usr/bin/env python3
"""
scripts/anchor_ledger.py — External Blockchain Ledger Notarization CLI (SIH26188).

Theme: Blockchain & Cybersecurity
Purpose:
  Externally notarizes the local append-only SHA-256 hash-chain ledger to
  provide immutable, decentralized non-repudiation. Even if a local database
  is compromised or destroyed, the cryptographic root is publicly verifiable.

Usage:
  python scripts/anchor_ledger.py                       # Anchors against the local DB
  python scripts/anchor_ledger.py --verify              # Verifies the local chain
  python scripts/anchor_ledger.py --remote <URL> --cookie <SESSION>
      Anchors against a running deployment. The endpoint is authenticated, so
      pass the officer's session cookie (or set ANCHOR_SESSION_COOKIE).

Note: the manifest records the anchoring officer's email address, and
_publish_anchor_gist publishes to a PUBLIC gist. Treat that as public data.
"""

import argparse
import hashlib
import json
import os
import sys

# Add project root to sys.path so app modules import cleanly
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)


def _banner():
    print("=" * 72)
    print("  SSB BORDER SCREENING DESK — BLOCKCHAIN LEDGER NOTARY (SIH26188)")
    print("  Theme: Blockchain & Cybersecurity | Non-Repudiation Engine")
    print("=" * 72)


def anchor_via_api(api_url: str, verify_only: bool = False, session_cookie: str = ""):
    """Anchor or verify against a running deployment.

    The anchor endpoints require a signed-in officer, so a session cookie must
    be supplied. Mint one by signing in through the UI and copying the
    `nischay_session` value from the browser's cookies, or run this against a
    local instance with anchor_local_db() instead.
    """
    import urllib.error
    import urllib.request

    endpoint = f"{api_url.rstrip('/')}/api/screen/ledger/anchor"
    method = "GET" if verify_only else "POST"
    if not session_cookie:
        print(
            "[-] A session cookie is required: the ledger anchor endpoint is "
            "authenticated.\n"
            "    Sign in to the console, copy the `nischay_session` cookie, then:\n"
            "    python scripts/anchor_ledger.py --remote <url> --cookie '<value>'\n"
            "    Or anchor directly against the database with --local."
        )
        return 2

    print(f"[*] Calling {method} {endpoint} ...")
    req = urllib.request.Request(
        endpoint,
        data=b"{}" if method == "POST" else None,
        headers={
            "Content-Type": "application/json",
            "Cookie": f"nischay_session={session_cookie}",
            "User-Agent": "ssb-ledger-anchor-cli/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print("\n[+] SUCCESS: Response from Notary Gateway:")
            print(json.dumps(data, indent=2))
            return 0
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print(f"\n[-] AUTH ({e.code}): the session cookie is missing, invalid or expired.")
        else:
            print(f"\n[-] HTTP {e.code} calling API: {e}")
        return 1
    except Exception as e:
        print(f"\n[-] ERROR calling API: {e}")
        return 1


def anchor_local_db(verify_only: bool = False):
    from app.main import (
        get_db, ScreeningReport, _publish_anchor_gist, _compute_anchor_manifest,
    )

    with get_db() as db:
        rows = db.query(ScreeningReport).order_by(ScreeningReport.created_at.asc(), ScreeningReport.id.asc()).all()

    if not rows:
        print("[!] Cannot anchor empty ledger: no screening reports found in database.")
        return 0

    total_blocks = len(rows)
    latest = rows[-1]
    head_hash = latest.ledger_hash or "GENESIS"
    checkpoint = latest.checkpoint or "Border Checkpoint"
    screener = latest.screener or "officer@ssb.gov.in"

    print("[*] Database Ledger Summary:")
    print(f"    - Total Blocks:    {total_blocks}")
    print("    - Genesis Anchor:  GENESIS")
    print(f"    - Head Block Hash: {head_hash}")
    print(f"    - Latest Post:     {checkpoint}")
    print(f"    - Officer / Sign:  {screener}")

    # Verify chain integrity
    expected_prev = "GENESIS"
    for idx, r in enumerate(rows):
        if r.previous_hash and idx > 0 and r.previous_hash != expected_prev:
            print(f"[-] CHAIN BROKEN at block {r.id}: expected {expected_prev}, got {r.previous_hash}")
            return 1
        block_payload = f"{r.previous_hash or 'GENESIS'}:{r.file_hash}:{r.verdict}:{r.risk_score}:{r.created_at}:{r.screener or 'unknown'}"
        computed_hash = hashlib.sha256(block_payload.encode("utf-8")).hexdigest()
        if r.ledger_hash and r.ledger_hash != computed_hash:
            print(f"[-] TAMPERED BLOCK at {r.id}: hash mismatch!")
            return 1
        if r.ledger_hash:
            expected_prev = r.ledger_hash

    print("[+] Cryptographic Chain Integrity: VALID (Unbroken SHA-256 Sequence)")

    if verify_only:
        return 0

    # Compute anchor manifest
    manifest = _compute_anchor_manifest(head_hash, total_blocks, screener, checkpoint)
    anchor_type, public_url = _publish_anchor_gist(manifest)
    manifest["anchor_type"] = anchor_type
    manifest["public_url"] = public_url

    print("\n[+] IMMUTABLE ANCHOR MANIFEST GENERATED:")
    print("-" * 72)
    print(json.dumps(manifest, indent=2))
    print("-" * 72)
    print(f"[+] External Anchor Type: {anchor_type}")
    print(f"[+] Public Proof Location: {public_url}")
    print("[+] Non-Repudiation Status: ACTIVATED")
    return 0


def main():
    _banner()
    parser = argparse.ArgumentParser(description="SSB Border Screening Blockchain Notary")
    parser.add_argument(
        "--remote", type=str, default="",
        help="Remote API base URL, e.g. https://your-deployment.example.com",
    )
    parser.add_argument(
        "--cookie", type=str, default=os.environ.get("ANCHOR_SESSION_COOKIE", ""),
        help="Session cookie for --remote (or set ANCHOR_SESSION_COOKIE). The "
             "anchor endpoint is authenticated.",
    )
    parser.add_argument("--verify", action="store_true", help="Verify ledger integrity without publishing a new anchor")
    args = parser.parse_args()

    if args.remote:
        sys.exit(anchor_via_api(args.remote, args.verify, args.cookie))
    else:
        sys.exit(anchor_local_db(args.verify))


if __name__ == "__main__":
    main()
