"""Vercel ASGI entrypoint for the NO-CAP screening API.

A startup failure here (missing environment variable, absent dependency,
unavailable timezone data) otherwise surfaces only as an opaque
``FUNCTION_INVOCATION_FAILED`` with no way to tell the cause without dashboard
log access. We import the app inside a guard and, if it fails, serve a minimal
JSON diagnostic containing ONLY an exception class name and a fixed,
secret-free hint. The full traceback still goes to the Vercel function log.
"""

import json
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)


def _safe_hint(exc: BaseException) -> str:
    """Map a startup exception to an actionable message that leaks no secrets.

    Never returns the raw exception text: a database error can embed the
    connection string, and configuration values must not be echoed publicly.
    """
    name = type(exc).__name__
    message = str(exc)
    if name == "VaultKeyError":
        raw = os.getenv("MASTER_VAULT_KEY", "")
        if not raw:
            return "MASTER_VAULT_KEY is not set in the deployment environment."
        return f"MASTER_VAULT_KEY is {len(raw)} bytes; at least 32 are required."
    if name == "ZoneInfoNotFoundError":
        return "IANA timezone database unavailable; tzdata must be installed."
    if name == "ModuleNotFoundError":
        missing = getattr(exc, "name", "") or "unknown"
        return f"Python dependency missing at startup: {missing}"
    if name == "RuntimeError" and message.startswith("DATABASE_URL is not set"):
        return "DATABASE_URL is not set in the deployment environment."
    if name == "RuntimeError" and message.startswith("Unsupported database scheme"):
        return "DATABASE_URL uses an unsupported scheme; Neon Postgres is required."
    return f"Startup failed with {name}. See the function log for details."


try:
    from app.main import app  # noqa: F401
except BaseException as _exc:  # noqa: BLE001 - a startup crash must not be masked
    traceback.print_exc()
    _ERROR_CLASS = type(_exc).__name__
    _HINT = _safe_hint(_exc)

    async def app(scope, receive, send):  # noqa: F811
        if scope["type"] != "http":
            return
        body = json.dumps(
            {"status": "startup_failed", "error_class": _ERROR_CLASS, "hint": _HINT}
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
