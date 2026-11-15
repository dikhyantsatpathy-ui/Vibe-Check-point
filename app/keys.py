"""
Cryptographic key management for the SSB Border Screening desk (SIH26188).

Centralises every secret the app signs with, and makes the two things that
went wrong in the original implementation impossible to reintroduce:

  1. No built-in default key. `MASTER_VAULT_KEY` must be supplied by the
     environment and must be at least 32 bytes. There is no padding and no
     truncation -- a short or missing key is a hard startup error, because a
     known fallback key means anyone who can read the source can mint a valid
     session cookie for any address, including a super admin.

  2. Key separation. The session-signing key and the evidence-seal key are
     derived from the master via HMAC-SHA256 under distinct domain-separation
     labels, so a signature produced in one context can never be replayed in
     the other.

Rotation
--------
Deploy a new `MASTER_VAULT_KEY`. Tokens and seals signed with the outgoing key
stop being *produced*, but the old key is still *accepted for verification*
while you roll forward if you also set:

    MASTER_VAULT_KEY_PREV=<the outgoing key>

Seals and dossier documents produced under the old key therefore keep
verifying, while anything newly minted uses the new key only. Drop
`MASTER_VAULT_KEY_PREV` once the old key's lifetime (session TTL, 24h) has
fully elapsed.
"""

import hashlib
import hmac
import os

__all__ = [
    "VaultKeyError",
    "load_master_key",
    "MASTER_VAULT_KEY",
    "SESSION_KEY",
    "SEAL_KEY",
    "session_key",
    "seal_key",
    "session_keys_to_try",
    "seal_keys_to_try",
    "sign",
    "verify",
    "rotate_note",
]

MIN_KEY_BYTES = 32

# Domain-separation labels. Changing either of these invalidates every
# existing token/seal signed under the old label, so treat them as frozen.
_SESSION_LABEL = b"SSB-SIH26188/session-token/v1"
_SEAL_LABEL = b"SSB-SIH26188/evidence-seal/v1"

_TESTING = os.getenv("TESTING") == "1"


class VaultKeyError(RuntimeError):
    """Raised at startup when MASTER_VAULT_KEY is missing or too weak."""


def _validate(raw: bytes, env_name: str) -> bytes:
    if not raw:
        raise VaultKeyError(
            f"{env_name} is not set. This application refuses to start without it: "
            "a built-in fallback key would let anyone who reads the source mint a "
            "valid session cookie for any address. Generate one with:\n"
            "    python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    if len(raw) < MIN_KEY_BYTES:
        # Deliberately NOT padded and NOT truncated. Silently stretching a short
        # key is how a 5-character "master key" ends up protecting a live
        # deployment of identity records.
        raise VaultKeyError(
            f"{env_name} is {len(raw)} bytes; at least {MIN_KEY_BYTES} are required. "
            "Refusing to pad or truncate a weak key."
        )
    return raw


def load_master_key() -> bytes:
    """Return the validated master key from the environment.

    Under TESTING=1 an ephemeral random key is generated per process, so a test
    run can never accidentally sign with (or assert against) a developer's real
    key, and no test fixture has to hardcode a secret.
    """
    if _TESTING:
        return hashlib.sha256(os.urandom(32)).digest()
    return _validate(os.getenv("MASTER_VAULT_KEY", "").encode("utf-8"), "MASTER_VAULT_KEY")


def _load_prev_key() -> bytes | None:
    """The outgoing key, accepted for verification only. Never signs."""
    if _TESTING:
        return None
    prev = os.getenv("MASTER_VAULT_KEY_PREV", "").encode("utf-8")
    return prev if prev else None


#: Raw master key. Retained under this name because it is part of the module's
#: public surface and because callers that need the raw bytes (rather than a
#: derived sub-key) still reference it.
MASTER_VAULT_KEY = load_master_key()


def _derive(master: bytes, label: bytes) -> bytes:
    """HMAC-SHA256 KDF with a fixed domain-separation label."""
    return hmac.new(master, label, hashlib.sha256).digest()


SESSION_KEY = _derive(MASTER_VAULT_KEY, _SESSION_LABEL)
SEAL_KEY = _derive(MASTER_VAULT_KEY, _SEAL_LABEL)

# Verification-only key rings: [current, previous-if-configured].
_SESSION_KEYS = [SESSION_KEY]
_SEAL_KEYS = [SEAL_KEY]
_prev = _load_prev_key()
if _prev is not None:
    _SESSION_KEYS.append(_derive(_prev, _SESSION_LABEL))
    _SEAL_KEYS.append(_derive(_prev, _SEAL_LABEL))


def session_key() -> bytes:
    """Active session-token signing key."""
    return SESSION_KEY


def seal_key() -> bytes:
    """Active evidence-seal signing key (dossier, BSA certificate, handover,
    ledger anchor)."""
    return SEAL_KEY


def session_keys_to_try() -> list[bytes]:
    """[current, previous] -- for verifying a token of unknown vintage."""
    return list(_SESSION_KEYS)


def seal_keys_to_try() -> list[bytes]:
    """[current, previous] -- for verifying a seal of unknown vintage."""
    return list(_SEAL_KEYS)


def sign(key: bytes, message: str | bytes) -> str:
    """Hex HMAC-SHA256 over `message` under `key`."""
    payload = message.encode("utf-8") if isinstance(message, str) else message
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify(key: bytes, message: str | bytes, signature: str) -> bool:
    """Constant-time signature check."""
    return hmac.compare_digest(sign(key, message), signature or "")


def rotate_note() -> str:
    """Operator-facing summary of the currently active key material. Safe to
    log: contains no key material."""
    if _prev is None:
        return "MASTER_VAULT_KEY active; MASTER_VAULT_KEY_PREV not set (no rotation window)."
    return (
        "MASTER_VAULT_KEY active; MASTER_VAULT_KEY_PREV also accepted for "
        "verification. Remove MASTER_VAULT_KEY_PREV once the previous key's "
        "tokens have expired."
    )
