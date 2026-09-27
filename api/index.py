import sys
import os

# Ensure project root is importable (api/ -> parent)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# Ensure app/ itself is importable for `from screening import ...` etc.
_APP = os.path.join(_ROOT, "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from app.main import app  # noqa: F401 — Vercel ASGI entrypoint