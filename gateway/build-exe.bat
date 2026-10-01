@echo off
REM Build the packaged gateway console: dist\DeltaOTA-Gateway\DeltaOTA-Gateway.exe
REM
REM One-folder build on purpose: the console launches the gateway as a child
REM process of the SAME exe (--run-gateway). A one-file build would put a
REM bootloader process in between, and "Stop" could leave the gateway holding
REM UDP 5683. Ship/copy the whole dist\DeltaOTA-Gateway folder.
REM
REM Needs the gateway venv (setup-gateway.bat). PyInstaller is installed on demand.
setlocal
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (echo [FAIL] .venv missing - run setup-gateway.bat first. & exit /b 1)
"%PY%" -m pip install -q -r requirements-build.txt || exit /b 1
"%PY%" -m PyInstaller --noconfirm --clean --onedir --console ^
  --name DeltaOTA-Gateway ^
  --paths secureota\gateway_runtime --paths . ^
  --collect-all aiocoap --collect-all web3 --collect-all eth_account ^
  --collect-submodules cryptography ^
  gateway_console.py || exit /b 1
echo.
echo [Build] dist\DeltaOTA-Gateway\DeltaOTA-Gateway.exe
echo [Build] Config + key stay in %%APPDATA%%\DeltaOTA\gateway.json; artifacts go to dist\DeltaOTA-Gateway\artifacts.
