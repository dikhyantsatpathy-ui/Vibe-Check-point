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

def _get_app():
    try:
        from app.main import app as real_app
        return real_app
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        
        async def error_app(scope, receive, send):
            if scope["type"] == "http":
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"text/plain")],
                })
                await send({
                    "type": "http.response.body",
                    "body": err_msg.encode("utf-8"),
                })
        
        return error_app

app = _get_app()