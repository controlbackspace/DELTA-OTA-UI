@echo off
REM SecureOTA gateway runner (laptop bench / rehearsal).
REM Persistent terminal: configure mode below, start, leave running. Ctrl+C stops.
REM Requires gateway/.venv (see setup-gateway.bat for first-time setup).
cd /d "%~dp0secureota\gateway_runtime"

REM --- Mode: simulated ledger (no blockchain processes needed) ---
set SIM_LEDGER=1

REM --- Live-ledger mode instead: REM out the SIM_LEDGER line above and set: ---
REM set DELTA_RPC_URL=http://127.0.0.1:8545
REM set DELTA_CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3

REM --- Optional overrides (leave commented for defaults) ---
REM set DELTA_BIND_ADDR=192.168.100.94
REM set DELTA_PAYLOAD=C:\path\to\payload.bin  (bench/test seam only, never production)

..\..\.venv\Scripts\python.exe -u main_gateway.py
