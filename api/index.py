"""Vercel serverless entrypoint for the Vibe Check Point project.

Adapts Vercel's internal rewrite routing to FastAPI's route table by restoring
the original request path from Vercel's incoming forwarding headers.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)


class VercelASGIAdapter:
    def __init__(self, inner_app):
        self.inner_app = inner_app

    def __getattr__(self, name):
        return getattr(self.inner_app, name)

    async def __call__(self, scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            matched = (
                headers.get(b"x-matched-path")
                or headers.get(b"x-invoke-path")
                or headers.get(b"x-forwarded-uri")
            )
            if matched:
                orig_path = matched.decode("utf-8", errors="ignore").split("?")[0]
                scope["path"] = orig_path
                scope["raw_path"] = orig_path.encode("utf-8")
            elif scope.get("path") == "/api/index.py":
                scope["path"] = "/"
                scope["raw_path"] = b"/"
        await self.inner_app(scope, receive, send)


try:
    from app.main import app as _fastapi_app
    app = VercelASGIAdapter(_fastapi_app)
except Exception as _ex:
    import traceback
    _tb = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    app = FastAPI()
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
    def _catchall(path: str):
        return JSONResponse(status_code=500, content={"error": "IMPORT_FAILED", "detail": str(_ex), "traceback": _tb})