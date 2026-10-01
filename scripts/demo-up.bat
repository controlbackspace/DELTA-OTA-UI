@echo off
REM DeltaOTA one-click demo bring-up (chain + artifacts + tunnel + app).
REM Cold laptop to running app in one double-click. Leaves five windows open:
REM   DeltaOTA-Node, DeltaOTA-Deploy, DeltaOTA-Artifacts, DeltaOTA-Tunnel, DeltaOTA-App.
REM Fresh chain every run: killing the node wipes state, so redeploy happens here.
REM Companion: demo-down.bat closes all five windows.
REM Usage: demo-up.bat [--skip-build]
REM   --skip-build  reuse the last desktop build (skip npm run build:app).
REM Always starts the cloudflared tunnel: WalletConnect phone signing needs a
REM public RPC for the node, so a tunnel-less bring-up is phone-incompatible.
setlocal EnableDelayedExpansion
cd /d "%~dp0.."
set ROOT=%CD%
set ENVDIR=%TEMP%\delta-ota-demo
mkdir "%ENVDIR%" 2>nul
del /q "%ENVDIR%\contract-address.txt" "%ENVDIR%\tunnel-url.txt" "%ENVDIR%\deploy.log" "%ENVDIR%\tunnel.log" 2>nul

set SKIP_BUILD=
if not "%~1"=="" (
  if /i "%~1"=="--skip-build" (
    set SKIP_BUILD=1
  ) else (
    echo [FAIL] Unknown flag "%~1". Usage: demo-up.bat [--skip-build]
    goto :fail
  )
)

echo [Preflight] Checking required tools...
where node >nul 2>nul
if errorlevel 1 (echo [FAIL] node not found on PATH. Install Node.js LTS first. & goto :fail)
where python >nul 2>nul
if errorlevel 1 (echo [FAIL] python not found on PATH. Install Python 3.12+ first. & goto :fail)
where cloudflared >nul 2>nul
if errorlevel 1 (echo [FAIL] cloudflared not found on PATH. Install cloudflared and retry. & goto :fail)
if not exist "%ROOT%\blockchain\package.json" (echo [FAIL] blockchain\package.json missing. Run from a full repo clone. & goto :fail)
if not exist "%ROOT%\desktop\package.json" (echo [FAIL] desktop\package.json missing. Run from a full repo clone. & goto :fail)
if not exist "%ROOT%\desktop\node_modules" (echo [FAIL] desktop\node_modules missing. Run setup.ps1 first. & goto :fail)
if not exist "%ROOT%\gateway\artifacts" mkdir "%ROOT%\gateway\artifacts"
echo [Preflight] OK.

echo [1/6] Starting Hardhat node (window: DeltaOTA-Node)...
start "DeltaOTA-Node" cmd /k "cd /d %ROOT%\blockchain && npx hardhat node --hostname 0.0.0.0"
echo [1/6] Waiting for RPC on 127.0.0.1:8545 (60s)...
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(60); while ((Get-Date) -lt $d) { try { Invoke-WebRequest -Uri http://127.0.0.1:8545 -Method POST -Body '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"web3_clientVersion\",\"params\":[]}' -ContentType 'application/json' -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"
if errorlevel 1 (echo [FAIL] Hardhat node did not answer within 60s. Read the DeltaOTA-Node window. & goto :fail)
echo [1/6] Node is up.

echo [2/6] Deploying DeltaOTA contract (window: DeltaOTA-Deploy)...
echo [2/6] Running: npx hardhat run scripts/deploy.js --network localhost
start "DeltaOTA-Deploy" cmd /k "cd /d %ROOT%\blockchain && npx hardhat run scripts/deploy.js --network localhost > %ENVDIR%\deploy.log 2>&1 & type %ENVDIR%\deploy.log"
echo [2/6] Waiting for contract address (120s)...
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(120); while ((Get-Date) -lt $d) { if (Test-Path '%ENVDIR%\deploy.log') { $t=Get-Content '%ENVDIR%\deploy.log' -Raw; if ($t -match 'CONTRACT ADDRESS:\s*(0x[0-9a-fA-F]{40})') { $Matches[1] | Out-File -LiteralPath '%ENVDIR%\contract-address.txt' -NoNewline -Encoding ascii; exit 0 }; if ($t -match '(?i)\berror\b|\bfailed\b|\brevert\b|\bexception\b') { exit 2 } }; Start-Sleep -Seconds 2 }; exit 1"
if errorlevel 2 (type "%ENVDIR%\deploy.log" & echo [FAIL] Deploy errored. See the DeltaOTA-Deploy window. & goto :fail)
if errorlevel 1 (echo [FAIL] No contract address within 120s. Read the DeltaOTA-Deploy window. & goto :fail)
set /p CONTRACT=<"%ENVDIR%\contract-address.txt"
echo [2/6] Contract: %CONTRACT%

echo [3/6] Starting artifact server :8000 (window: DeltaOTA-Artifacts)...
start "DeltaOTA-Artifacts" cmd /k "cd /d %ROOT%\gateway && python serve_artifacts.py --port 8000"
echo [3/6] Waiting for :8000 to serve (30s; 404 also proves serving)...
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(30); while ((Get-Date) -lt $d) { try { Invoke-WebRequest -Uri http://127.0.0.1:8000/ -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { if ($_.Exception.Response -and $_.Exception.Response.StatusCode.value__ -eq 404) { exit 0 }; Start-Sleep -Seconds 2 } }; exit 1"
if errorlevel 1 (echo [FAIL] Artifact server did not answer within 30s. Read the DeltaOTA-Artifacts window. & goto :fail)
echo [3/6] Artifact server is up.

echo [4/6] Starting cloudflared tunnel for :8545 (window: DeltaOTA-Tunnel)...
start "DeltaOTA-Tunnel" cmd /k "cd /d %ROOT% && cloudflared tunnel --url http://127.0.0.1:8545 --logfile %ENVDIR%\tunnel.log"
echo [4/6] Waiting for tunnel URL (90s)...
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(90); while ((Get-Date) -lt $d) { if (Test-Path '%ENVDIR%\tunnel.log') { $t=Get-Content '%ENVDIR%\tunnel.log' -Raw; if ($t -match 'https://[a-zA-Z0-9-]+\.trycloudflare\.com') { $Matches[0] | Out-File -LiteralPath '%ENVDIR%\tunnel-url.txt' -NoNewline -Encoding ascii; exit 0 } }; Start-Sleep -Seconds 2 }; exit 1"
if errorlevel 1 (echo [FAIL] No tunnel URL within 90s. Read the DeltaOTA-Tunnel window. & goto :fail)
set /p TUNNEL=<"%ENVDIR%\tunnel-url.txt"

echo [5/6] Building desktop app...
if defined SKIP_BUILD echo [5/6] Skipped -- --skip-build passed, reusing last build in desktop\dist.
if defined SKIP_BUILD goto :after_build
cd /d "%ROOT%\desktop"
call npm run build:app
if errorlevel 1 (echo [FAIL] Desktop build failed. See npm output above. & goto :fail)
echo [5/6] Desktop build OK.
:after_build

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
  for /f "tokens=1" %%b in ("%%a") do (
    if not defined LANIP (
      echo %%b | findstr /b "127\." >nul
      if errorlevel 1 (
        echo %%b | findstr /b "169\.254\." >nul
        if errorlevel 1 set LANIP=%%b
      )
    )
  )
)

echo.
echo ===============================================================
echo  DELTA-OTA DEMO IS UP
echo ===============================================================
echo  Contract : %CONTRACT%
echo  LAN IP   : %LANIP%
echo  Artifacts: http://%LANIP%:8000/  (serves gateway\artifacts)
echo  Tunnel   : %TUNNEL%  (phone MetaMask custom network RPC, chain 31337)
echo  App      : opening in the DeltaOTA-App window
echo ---------------------------------------------------------------
echo  Next (judgment steps, NOT automated):
echo   1. App Config tab: contract = %CONTRACT%, Node RPC = local (Phone RPC is pre-filled with the tunnel)
echo   2. Phone MetaMask: if chain 31337 already exists, set its RPC to %TUNNEL% (the app only adds it when missing)
echo   3. Console steps 1-5: the patch URL comes from step 3; the gateway serves whichever release goes live
echo   4. demo-down.bat wipes the chain and closes all windows when done (fresh node next run)
echo ===============================================================

echo [6/6] Starting SecureOTA desktop app (window: DeltaOTA-App)...
REM Inherited by the app window: the renderer reads it as the phone RPC.
set "DELTA_PHONE_RPC_URL=%TUNNEL%"
start "DeltaOTA-App" cmd /k "cd /d %ROOT%\desktop && npm start"
endlocal
exit /b 0

:fail
endlocal
echo.
echo Demo bring-up FAILED - see the [FAIL] line above for details.
echo Press any key to close this window...
pause >nul
exit /b 1
