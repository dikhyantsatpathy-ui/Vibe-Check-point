"""Vercel serverless entrypoint for the `no-cap` project (Framework Preset = Other).

This project does NOT auto-detect FastAPI from the root `main.py` the way the
`no-cap-tau` project does (that one uses Preset = FastAPI). With Preset = Other
Vercel only runs functions that are declared in vercel.json, so here we expose
the whole app as a single function and rewrite every path to it. The app's own
root level routes (/api/* and /) keep their original path inside FastAPI, so no
path information is lost.

The FastAPI instance lives in `app/main.py` (the refactored backend with the
Sightengine AI detector + quota endpoint). We re-export it here.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from main import app as app  # noqa: E402,F401
except Exception as e:
    import traceback
    tb = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    app = FastAPI()
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
    def _catchall(path: str):
        return JSONResponse(status_code=500, content={"error": "API_INDEX_IMPORT_FAILED", "detail": str(e), "traceback": tb})