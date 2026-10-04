#!/usr/bin/env bash
# start.sh — SSB Border Screening console launcher (Linux/macOS).
# Windows: use START.bat.
set -euo pipefail
cd "$(dirname "$0")"

echo
echo "  [SSB] Border screening console launcher"
echo "  ---------------------------------------"
echo

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

echo "  [1/4] Installing Python dependencies..."
"$PY" -m pip install -q --disable-pip-version-check -r requirements.txt

echo "  [2/4] Installing frontend dependencies..."
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi

echo "  [3/4] Building the single-file web bundle..."
(cd frontend && npm run build)

# The app refuses to start without these. Fail here with a clear message
# rather than letting uvicorn exit with a stack trace.
for var in DATABASE_URL MASTER_VAULT_KEY GOOGLE_CLIENT_ID; do
  if [ -z "${!var:-}" ] && ! grep -qE "^${var}=..+" .env 2>/dev/null; then
    echo
    echo "  ERROR: ${var} is not set."
    echo "         Copy .env.example to .env and fill in at least:"
    echo "           DATABASE_URL, MASTER_VAULT_KEY (32+ bytes), GOOGLE_CLIENT_ID"
    echo "         Set SUPER_ADMINS too, or no account can sign in."
    echo
    exit 1
  fi
done

echo "  [4/4] Starting server on http://127.0.0.1:8000 ..."
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
