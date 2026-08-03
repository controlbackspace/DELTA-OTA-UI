<#
SecureOTA - one-command developer setup.
Installs every prerequisite to build and run the desktop app:

  1. Toolchain check  : Python 3.12 (py launcher) + Node.js (>= 20) + npm
  2. Gateway (Python) : creates .venv, installs release-builder deps, smoke test
  3. UI (React)       : npm install
  4. Desktop (Electron): npm install + builds the bundled renderer (tsc + vite)

Usage:
  .\setup.ps1                      detect + install project deps
  .\setup.ps1 -InstallTools        also winget-install missing Python 3.12 / Node LTS
  .\setup.ps1 -EdgeGateway         also install CoAP runtime deps (web3, cryptography, aiocoap)

Idempotent: safe to re-run any time. Detailed log: setup.log (repo root).
#>
[CmdletBinding()]
param(
    [switch]$InstallTools,
    [switch]$EdgeGateway
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$LogFile = Join-Path $Root "setup.log"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Update-PathFromRegistry {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Invoke-Npm {
    param([string]$Folder, [string[]]$Arguments, [string]$Label)
    Push-Location (Join-Path $Root $Folder)
    try {
        & npm.cmd @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Label failed (exit code $LASTEXITCODE)"
        }
    }
    finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
Set-Content -LiteralPath $LogFile -Value "SecureOTA setup - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding UTF8
Write-Log "== SecureOTA setup =="

# ---------------------------------------------------------------------------
Write-Log "== 1. Toolchain (Python 3.12 / Node.js / npm) =="

$pyVersion = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pyVersion = (& py -3.12 --version 2>&1 | Out-String).Trim()
}
$pythonOk = ($pyVersion -and ($pyVersion -match "Python 3\.12"))

if (-not $pythonOk) {
    if ($InstallTools) {
        Write-Log "Python 3.12 not found - installing via winget..."
        winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Log "FAILED: winget could not install Python 3.12"
            exit 1
        }
        Update-PathFromRegistry
        $pyVersion = (& py -3.12 --version 2>&1 | Out-String).Trim()
        $pythonOk = ($pyVersion -match "Python 3\.12")
    }
    if (-not $pythonOk) {
        Write-Log "FAILED: Python 3.12 is required (bsdiff4 ships wheels only up to cp313)."
        Write-Log "        Re-run with -InstallTools to install automatically, or install it from"
        Write-Log "        https://www.python.org/downloads/ (make sure 'py launcher' is enabled)."
        exit 1
    }
}
Write-Log "  python : $pyVersion"

$nodeOk = $false
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = (& node --version 2>&1 | Out-String).Trim()
    if ($nodeVer -match "v(\d+)") {
        $nodeOk = ([int]$Matches[1] -ge 20)
    }
}
if (-not $nodeOk) {
    if ($InstallTools) {
        Write-Log "Node.js not found - installing LTS via winget..."
        winget install --id OpenJS.NodeJS.LTS -e --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Log "FAILED: winget could not install Node.js LTS"
            exit 1
        }
        Update-PathFromRegistry
        $nodeVer = (& node --version 2>&1 | Out-String).Trim()
        if ($nodeVer -match "v(\d+)") {
            $nodeOk = ([int]$Matches[1] -ge 20)
        }
    }
    if (-not $nodeOk) {
        Write-Log "FAILED: Node.js >= 20 is required (Vite 8 / Electron)."
        Write-Log "        Re-run with -InstallTools to install automatically, or install from https://nodejs.org/"
        exit 1
    }
}
Write-Log "  node   : $nodeVer"

$npmOk = [bool](Get-Command npm.cmd -ErrorAction SilentlyContinue)
if (-not $npmOk) {
    Write-Log "FAILED: npm not found (it ships with Node.js; re-run with -InstallTools if needed)."
    exit 1
}
$npmVer = (& npm.cmd --version 2>&1 | Out-String).Trim()
Write-Log "  npm    : $npmVer"

# ---------------------------------------------------------------------------
Write-Log "== 2. Gateway (Python venv + release-builder deps) =="
$venvPython = Join-Path $Root "gateway\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Log "  venv already exists - reusing gateway\.venv"
}
else {
    Write-Log "  creating venv (py -3.12 -m venv gateway\.venv)..."
    Push-Location (Join-Path $Root "gateway")
    try {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            throw "venv creation failed (exit code $LASTEXITCODE)"
        }
    }
    finally {
        Pop-Location
    }
}
Write-Log "  pip install -r gateway\requirements.txt ..."
& $venvPython -m pip install --disable-pip-version-check -q -r (Join-Path $Root "gateway\requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Log "FAILED: pip install"
    exit 1
}
Write-Log "  quick_test.py smoke test..."
$env:PYTHONIOENCODING = "utf-8"
& $venvPython (Join-Path $Root "gateway\quick_test.py")
if ($LASTEXITCODE -ne 0) {
    Write-Log "FAILED: gateway smoke test (quick_test.py)"
    exit 1
}
Write-Log "  gateway : OK"

# ---------------------------------------------------------------------------
Write-Log "== 3. UI (React) - npm install =="
if (Test-Path (Join-Path $Root "ui\secureota-ui\node_modules")) {
    Write-Log "  node_modules already exists - skipping"
}
else {
    Invoke-Npm -Folder "ui\secureota-ui" -Arguments @("install") -Label "ui npm install"
}
Write-Log "  ui : OK"

# ---------------------------------------------------------------------------
Write-Log "== 4. Desktop (Electron) - npm install + renderer bundle =="
if (Test-Path (Join-Path $Root "desktop\node_modules")) {
    Write-Log "  node_modules already exists - skipping"
}
else {
    Invoke-Npm -Folder "desktop" -Arguments @("install") -Label "desktop npm install"
}
Invoke-Npm -Folder "desktop" -Arguments @("run", "build:app") -Label "desktop build:app"
Write-Log "  desktop : OK"

# ---------------------------------------------------------------------------
if ($EdgeGateway) {
    Write-Log "== 5. Edge Gateway runtime deps (web3, cryptography, aiocoap) =="
    & $venvPython -m pip install --disable-pip-version-check -q web3 cryptography aiocoap
    if ($LASTEXITCODE -ne 0) {
        Write-Log "FAILED: edge gateway deps install"
        exit 1
    }
    Write-Log "  edge gateway : OK"
}

# ---------------------------------------------------------------------------
Write-Log "== Setup complete =="
Write-Log ""
Write-Log "Next steps:"
Write-Log "  cd desktop"
Write-Log "  npm start          -> launch the SecureOTA desktop app (offline)"
Write-Log ""
Write-Log "Other modes (see documentations\README.md):"
Write-Log "  ui/secureota-ui: npm run dev   -> browser simulation on http://localhost:5173"
Write-Log "  gateway: python make_release.py fixtures\v1.0.bin fixtures\v1.1.bin v1.1 --json"
Write-Log "  desktop: npm run dist          -> build the SecureOTA installer (.exe)"
