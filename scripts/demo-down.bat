@echo off
REM DeltaOTA demo teardown: closes the three demo-up.bat windows.
REM WARNING: killing DeltaOTA-Node wipes the in-memory chain. The contract
REM address from that run is dead afterwards — redeploy on next demo-up.
setlocal
taskkill /FI "WINDOWTITLE eq DeltaOTA-Node*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-Artifacts*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-Tunnel*" >nul 2>nul
echo Demo windows closed (node, artifacts, tunnel). Chain state is wiped; redeploy next run.
endlocal
