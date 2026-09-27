"""Root ASGI entrypoint for Vercel's native FastAPI detection.

Vercel auto-detects a FastAPI app exported as `app` from a root-level
`main.py` and forwards every request's ORIGINAL path into it (no rewrites
needed), which is why /api/* and / keep working. Re-export from app/main.py.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from app.main import (  # noqa: E402,F401
        app as app,
        ScreeningReport,
        ScreeningSession,
        now_utc,
        Base,
        engine,
        SessionLocal,
        get_db,
    )
except Exception as _import_err:
    import traceback
    _tb = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    app = FastAPI()
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
    def _catchall(path: str):
        return JSONResponse(status_code=500, content={"error": "IMPORT_FAILED", "detail": str(_import_err), "traceback": _tb})