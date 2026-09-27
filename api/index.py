import sys
import os
import traceback

# Ensure project root is importable
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# Ensure app/ directory itself is importable (for `from screening import ...`)
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

try:
    from app.main import app  # noqa: F401
except Exception as _exc:
    # Surface the real startup traceback as a minimal ASGI app
    _tb = traceback.format_exc()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            body = f"STARTUP ERROR:\n{_tb}".encode()
            await send({"type": "http.response.start", "status": 500,
                        "headers": [[b"content-type", b"text/plain"],
                                    [b"content-length", str(len(body)).encode()]]})
            await send({"type": "http.response.body", "body": body})