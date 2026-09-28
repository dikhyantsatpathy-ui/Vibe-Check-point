@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title SSB Border Screening (SIH26188) launcher

echo.
echo   [SSB] Border screening console launcher
echo   ---------------------------------------
echo.

set "PY=python"
where python >nul 2>nul || set "PY=py -3"

echo  [1/4] Installing Python dependencies...
"%PY%" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :err

echo  [2/4] Installing frontend dependencies...
pushd frontend
if not exist node_modules (
    call npm install --no-audit --no-fund >nul 2>nul || call npm install
)
if errorlevel 1 ( popd & goto :err )

echo  [3/4] Building the single-file web bundle...
call npm run build
if errorlevel 1 ( popd & goto :err )
popd

echo  [4/4] Starting server on http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000"
rem Run from the repo root: the app package needs both the root and app/ on the
rem path, and the built frontend lives at app/static/index.html.
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof

:err
echo.
echo  Setup failed - check the message above.
pause