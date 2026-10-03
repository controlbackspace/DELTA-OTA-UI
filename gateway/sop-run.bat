@echo off
REM Automated SOP evidence runner. Double-click for the full run, or pass a command:
REM   sop-run.bat                 preflight + every implemented SOP step + report
REM   sop-run.bat sop1 --n 10     one step with 10 timing repeats
REM   sop-run.bat report          rebuild SOP-REPORT.md for the latest run
REM Results: ..\sop-results\<UTC stamp>\SOP-REPORT.md  (raw data next to it).
setlocal
REM Double-clicked from Explorer (cmd /c): keep the window open at the end. NOPAUSE=1 disables.
set DBL=
if not defined NOPAUSE echo %cmdcmdline% | findstr /i /c:" /c " >nul && set DBL=1
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  echo [FAIL] .venv missing - run setup-gateway.bat first.
  if defined DBL pause
  exit /b 1
)
if "%~1"=="" (
  "%PY%" -m sop all
) else (
  "%PY%" -m sop %*
)
set RC=%ERRORLEVEL%
echo.
if %RC% neq 0 (echo [sop] finished with errors - see above.) else (echo [sop] done.)
if defined DBL pause
exit /b %RC%
