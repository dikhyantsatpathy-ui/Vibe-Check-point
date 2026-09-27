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

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

_startup_error = None
_step = "init"

try:
    _step = "import_psycopg2"
    import psycopg2

    _step = "import_cryptography"
    import cryptography

    _step = "import_app_main"
    import app.main
    app = app.main.app
except BaseException as e:
    _startup_error = {
        "step": _step,
        "error": str(e),
        "type": type(e).__name__,
        "traceback": traceback.format_exc(),
    }

if _startup_error is not None:
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
    def error_handler(path: str):
        return JSONResponse(status_code=500, content={"status": "STARTUP_FAILED", **_startup_error})