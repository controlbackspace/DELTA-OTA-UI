@echo off
REM SecureOTA gateway setup (Python 3.12 venv + release-builder dependencies).
REM Run this once per machine, from the gateway/ folder (repo) or the
REM resources\gateway folder of an installed SecureOTA app.
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python launcher 'py' not found.
  echo         Install Python 3.12 from https://www.python.org/downloads/
  echo         and check "py launcher" during installation.
  exit /b 1
)

echo [1/2] Creating Python 3.12 venv (.venv)...
py -3.12 -m venv .venv
if errorlevel 1 (
  echo [ERROR] Could not create venv with py -3.12.
  echo         Make sure Python 3.12 is installed and selectable via `py -3.12`.
  exit /b 1
)

echo [2/2] Installing dependencies (bsdiff4==1.2.6)...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed. See message above.
  exit /b 1
)

echo.
echo [OK] Gateway ready. You can now start the SecureOTA app.
