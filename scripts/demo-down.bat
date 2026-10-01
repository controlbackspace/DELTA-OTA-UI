@echo off
REM DeltaOTA demo teardown: closes the demo-up.bat windows and unpublishes
REM the phone RPC. With Tailscale the URL stays the same (it is this machine's
REM name); Funnel is only switched off so nothing is reachable between demos.
REM WARNING: killing DeltaOTA-Node wipes the in-memory chain. The contract
REM address from that run is dead afterwards — redeploy on next demo-up.
setlocal
taskkill /FI "WINDOWTITLE eq DeltaOTA-Node*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-Deploy*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-Artifacts*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-RpcGuard*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-Tunnel*" >nul 2>nul
taskkill /FI "WINDOWTITLE eq DeltaOTA-App*" >nul 2>nul
where tailscale >nul 2>nul
if not errorlevel 1 tailscale funnel reset >nul 2>nul
echo Demo windows closed (node, deploy, artifacts, RPC guard, tunnel, app); Funnel off.
echo Chain state is wiped; redeploy next run.
endlocal
