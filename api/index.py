import sys
import os

# Ensure the project root is on the path so `from app.main import app` resolves
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.main import app  # noqa: F401 — Vercel ASGI entrypoint