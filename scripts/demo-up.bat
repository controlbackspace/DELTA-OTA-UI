@echo off
REM DeltaOTA one-click demo bring-up (chain + artifacts + tunnel).
REM Cold laptop to summary card in one double-click. Leaves three windows open:
REM   DeltaOTA-Node, DeltaOTA-Artifacts, DeltaOTA-Tunnel.
REM Fresh chain every run: killing the node wipes state, so redeploy happens here.
REM Companion: demo-down.bat closes all three windows.
REM Usage: demo-up.bat
REM Always starts the cloudflared tunnel: WalletConnect phone signing needs a
REM public RPC for the node, so a tunnel-less bring-up is phone-incompatible.
setlocal EnableDelayedExpansion
cd /d "%~dp0.."
set ROOT=%CD%
set ENVDIR=%TEMP%\delta-ota-demo
mkdir "%ENVDIR%" 2>nul
del /q "%ENVDIR%\contract-address.txt" "%ENVDIR%\tunnel-url.txt" "%ENVDIR%\deploy.log" "%ENVDIR%\tunnel.log" 2>nul

echo [Preflight] Checking required tools...
where node >nul 2>nul
if errorlevel 1 (echo [FAIL] node not found on PATH. Install Node.js LTS first. & exit /b 1)
where python >nul 2>nul
if errorlevel 1 (echo [FAIL] python not found on PATH. Install Python 3.12+ first. & exit /b 1)
where cloudflared >nul 2>nul
if errorlevel 1 (echo [FAIL] cloudflared not found on PATH. Install cloudflared and retry. & exit /b 1)
if not exist "%ROOT%\blockchain\package.json" (echo [FAIL] blockchain\package.json missing. Run from a full repo clone. & exit /b 1)
if not exist "%ROOT%\gateway\artifacts" mkdir "%ROOT%\gateway\artifacts"
echo [Preflight] OK.

echo [1/4] Starting Hardhat node (window: DeltaOTA-Node)...
start "DeltaOTA-Node" cmd /k "cd /d %ROOT%\blockchain && npx hardhat node --hostname 0.0.0.0"
echo [1/4] Waiting for RPC on 127.0.0.1:8545 (60s)...
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(60); while ((Get-Date) -lt $d) { try { Invoke-WebRequest -Uri http://127.0.0.1:8545 -Method POST -Body '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"web3_clientVersion\",\"params\":[]}' -ContentType 'application/json' -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"
if errorlevel 1 (echo [FAIL] Hardhat node did not answer within 60s. Read the DeltaOTA-Node window. & exit /b 1)
echo [1/4] Node is up.

echo [2/4] Deploying DeltaOTA contract...
cd /d "%ROOT%\blockchain"
call npx hardhat run scripts/deploy.js --network localhost > "%ENVDIR%\deploy.log" 2>&1
if errorlevel 1 (type "%ENVDIR%\deploy.log" & echo [FAIL] Deploy failed. & exit /b 1)
powershell -NoProfile -Command "$t=Get-Content '%ENVDIR%\deploy.log' -Raw; if ($t -match 'CONTRACT ADDRESS:\s*(0x[0-9a-fA-F]{40})') { $Matches[1] | Out-File -LiteralPath '%ENVDIR%\contract-address.txt' -NoNewline -Encoding ascii; exit 0 } else { exit 1 }"
if errorlevel 1 (type "%ENVDIR%\deploy.log" & echo [FAIL] No contract address in deploy output. & exit /b 1)
set /p CONTRACT=<"%ENVDIR%\contract-address.txt"
echo [2/4] Contract: %CONTRACT%

echo [3/4] Starting artifact server :8000 (window: DeltaOTA-Artifacts)...
start "DeltaOTA-Artifacts" cmd /k "cd /d %ROOT%\gateway && python serve_artifacts.py --port 8000"
echo [3/4] Waiting for :8000 to serve (30s; 404 also proves serving)...
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(30); while ((Get-Date) -lt $d) { try { Invoke-WebRequest -Uri http://127.0.0.1:8000/ -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { if ($_.Exception.Response -and $_.Exception.Response.StatusCode.value__ -eq 404) { exit 0 }; Start-Sleep -Seconds 2 } }; exit 1"
if errorlevel 1 (echo [FAIL] Artifact server did not answer within 30s. Read the DeltaOTA-Artifacts window. & exit /b 1)
echo [3/4] Artifact server is up.

echo [4/4] Starting cloudflared tunnel for :8545 (window: DeltaOTA-Tunnel)...
start "DeltaOTA-Tunnel" cmd /k "cd /d %ROOT% && cloudflared tunnel --url http://127.0.0.1:8545 --logfile %ENVDIR%\tunnel.log"
echo [4/4] Waiting for tunnel URL (90s)...
powershell -NoProfile -Command "$d=(Get-Date).AddSeconds(90); while ((Get-Date) -lt $d) { if (Test-Path '%ENVDIR%\tunnel.log') { $t=Get-Content '%ENVDIR%\tunnel.log' -Raw; if ($t -match 'https://[a-zA-Z0-9-]+\.trycloudflare\.com') { $Matches[0] | Out-File -LiteralPath '%ENVDIR%\tunnel-url.txt' -NoNewline -Encoding ascii; exit 0 } }; Start-Sleep -Seconds 2 }; exit 1"
if errorlevel 1 (echo [FAIL] No tunnel URL within 90s. Read the DeltaOTA-Tunnel window. & exit /b 1)
set /p TUNNEL=<"%ENVDIR%\tunnel-url.txt"

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
echo  Artifacts: http://%LANIP%:8000/patch_v1.2.bin
echo  Tunnel   : %TUNNEL%  (phone MetaMask custom network RPC, chain 31337)
echo ---------------------------------------------------------------
echo  Next (judgment steps, NOT automated):
echo   1. App Config tab: contract = %CONTRACT%, RPC = local or tunnel
echo   2. Phone MetaMask: custom network RPC = %TUNNEL%, chain 31337, switch to it
echo   3. Propose with GOLDEN_HASH=(sha256 of patch) IPFS_URL=http://%LANIP%:8000/patch_v1.2.bin
echo   4. demo-down.bat wipes the chain when done (fresh node next run)
echo ===============================================================
endlocal
