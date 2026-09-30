@echo off
REM DeltaOTA demo teardown: closes the five demo-up.bat windows.
REM WARNING: killing DeltaOTA-Node wipes the in-memory chain. The contract
REM address from that run is dead afterwards — redeploy on next demo-up.
setlocal
taskkill /FI "WINDOWTITLE eq DeltaOTA-Node*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-Deploy*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-Artifacts*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-Tunnel*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-App*" >nul 2>nul
echo Demo windows closed (node, deploy, artifacts, tunnel, app). Chain state is wiped; redeploy next run.
endlocal
