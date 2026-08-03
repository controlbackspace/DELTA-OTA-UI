@echo off
REM SecureOTA one-command developer setup. Wraps setup.ps1 (double-click friendly).
REM Pass-through flags: -InstallTools -EdgeGateway
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
exit /b %errorlevel%
