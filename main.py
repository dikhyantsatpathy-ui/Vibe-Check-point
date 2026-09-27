import sys
import os
import traceback

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

try:
    from app.main import (  # noqa: F401
        app,
        ScreeningReport,
        ScreeningSession,
        now_utc,
        Base,
        engine,
        SessionLocal,
        get_db,
    )
except Exception:
    _tb = traceback.format_exc()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            body = f"STARTUP ERROR:\n{_tb}".encode()
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    [b"content-type", b"text/plain; charset=utf-8"],
                    [b"content-length", str(len(body)).encode()]
                ]
            })
            await send({"type": "http.response.body", "body": body})