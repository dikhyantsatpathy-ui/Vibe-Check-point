import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

step = "start"
try:
    step = "fastapi"
    from fastapi import FastAPI
    step = "psycopg2"
    import psycopg2
    step = "cryptography"
    import cryptography
    step = "pypdf"
    import pypdf
    step = "PIL"
    from PIL import Image
    step = "screening"
    import screening
    step = "app.main"
    import app.main
    app = app.main.app
except Exception as e:
    import traceback
    tb = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    app = FastAPI()
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"])
    def err(path: str):
        return JSONResponse(
            status_code=500,
            content={"error": "IMPORT_FAILED_AT_STEP", "step": step, "exception": str(e), "traceback": tb}
        )