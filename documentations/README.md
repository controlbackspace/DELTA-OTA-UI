# SecureOTA — Delta OTA for Constrained IoT

Securing delta firmware updates for constrained IoT (ESP32, Class 2 node) via OSCORE encryption and ledger-anchored release governance.

- **Release Builder (Python)** — bsdiff4 delta generation + SHA-256 golden hashing
- **Desktop App (Electron)** — the React dashboard running locally, no web server
- **Dashboard (React/Vite)** — dark-mode firmware console (also runs in a plain browser in simulation mode)
- **Edge Gateway (Python, CoAP)** — mocks blockchain polling, verifies golden hash, wraps payload in OSCORE (AES-CCM), serves via CoAP on 5683
- **Smart Contract** — `DeltaOTA.sol`: 2-of-3 multi-sig release governance

---

## Quick start (Windows, one command)

```powershell
git clone <repo-url>
cd DELTA-OTA-UI
.\setup.ps1          # or double-click setup.bat
```

Installs everything: Python 3.12 venv + release-builder deps (bsdiff4),
all npm packages (UI + desktop), and builds the bundled renderer.
Safe to re-run anytime; details in `setup.log`.

| Flag | Effect |
|---|---|
| `-InstallTools` | winget-installs missing **Python 3.12** / **Node.js LTS** automatically |
| `-EdgeGateway` | also installs `web3`, `cryptography`, `aiocoap` (CoAP runtime) |

Then launch the app:

```powershell
cd desktop
npm.cmd start
```

## Repository layout

```
DELTA-OTA-UI/
├── setup.ps1 / setup.bat        one-command developer setup (see Quick start)
├── contracts/DeltaOTA.sol          Solidity governance contract (Phase A: deploy pending)
├── gateway/                        Python backend
│   ├── make_release.py             CLI: build delta patch + golden hash (--json supported)
│   ├── setup-gateway.bat           one-shot venv + deps setup (dev AND installed app)
│   ├── quick_test.py               domain model smoke test
│   ├── requirements.txt            bsdiff4==1.2.6
│   ├── fixtures/                   sample v1.0.bin / v1.1.bin (gitignored, local only)
│   ├── artifacts/                  generated patches + gateway runtime state (gitignored)
│   └── secureota/
│       ├── domain/                 ReleaseManifest, StagedPatch, JanpatchHeader
│       ├── release_builder/        core.py — bsdiff4 diff + SHA-256 golden hash
│       └── gateway_runtime/        CoAP server/client, blockchain poller, security engine
├── desktop/                        Electron app (main/preload/ipc/services + packaging)
│   ├── scripts/bundle-renderer.cjs bundles the built UI into dist/renderer/
│   ├── scripts/preload-smoke.cjs   bridge regression check
│   ├── scripts/package-smoke.cjs   packaged-layout end-to-end check
│   └── build/icon.png              app icon (electron-builder converts to .ico)
├── ui/secureota-ui/                React + Vite + Tailwind dashboard (Atomic design)
└── documentations/                 all docs: README.md (this file), changes.txt,
                                    PROJECT_CONTEXT.md
```

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | **3.12** (not 3.14) | `bsdiff4` ships prebuilt wheels only up to cp313; 3.14 forces a source build that needs MSVC |
| Node.js | 20.19+ / 22.12+ (tested on 26.x) | Vite 8 + Electron + electron-builder |
| npm | 10+ | package management |

> Windows note: PowerShell blocks `npm.ps1` by default. Use `npm.cmd` instead of `npm` (e.g. `npm.cmd run dev`).

---

## Setup

### 1. Gateway (Python)

```powershell
cd gateway
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

…or simply double-click / run `gateway\setup-gateway.bat` (does both steps).

> **pip cache quirk:** a corrupt cache entry can serve a wrong-version `bsdiff4` wheel
> (`core.cp314-win_amd64.pyd` in a 3.12 venv) or a broken `pydantic_core` for the
> edge-gateway deps. If an import fails with `ModuleNotFoundError` on a compiled
> package, reinstall with
> `--no-cache-dir --force-reinstall --only-binary=:all: <package>`.

Sanity check:

```powershell
$env:PYTHONIOENCODING = "utf-8"   # needed once — see "Known quirks"
.\.venv\Scripts\python.exe quick_test.py
```

### 2. Desktop app (Electron + bundled UI)

```powershell
cd desktop
npm.cmd install
npm.cmd run build:app     # tsc + vite build + bundle renderer into dist/renderer/
```

`npm start` then launches the app **offline** — it loads the bundled UI from
disk (`file://`), with no server and no second terminal.

### 3. Dashboard (React) — only for UI work

```powershell
cd ui/secureota-ui
npm.cmd install
npm.cmd run dev            # Vite dev server on http://localhost:5173
```

To point Electron at the dev server (hot reload while editing UI):

```powershell
cd desktop
$env:VITE_DEV_SERVER_URL = "http://localhost:5173"
npm.cmd start
```

---

## Running

### Option A — Desktop app (recommended)

```powershell
cd desktop
npm.cmd run build:app      # once per source change
npm.cmd start
```

**In the window:** drag `base.bin` + `target.bin` into the sidebar DropZones →
**Generate Delta** → Python runs locally (hidden), the real golden hash + delta
metrics appear. **Configure URL** logs the mock IPFS CID + download URL.
Wallet/Approval steps are simulation-only until Phase A (contract deployment).

### Option B — Plain browser (simulation mode)

```powershell
cd ui/secureota-ui
npm.cmd run dev            # open http://localhost:5173
```

Same UI, hardcoded simulation, no Python execution, no IPC.

### Option C — Release builder CLI (no UI)

```powershell
cd gateway
.\.venv\Scripts\python.exe make_release.py fixtures\v1.0.bin fixtures\v1.1.bin v1.1
.\.venv\Scripts\python.exe make_release.py fixtures\v1.0.bin fixtures\v1.1.bin v1.1 --json
```

JSON shape consumed by the desktop app:

```json
{
  "version_tag": "v1.1",
  "golden_hash": "8b24adce...",
  "patch_size": 164,
  "compression_ratio": 0.9983,
  "patch_url": "http://localhost:8000/files/patch.bin",
  "patch_path": "C:\\...\\gateway\\artifacts\\patch_v1.1.bin"
}
```

> `patch_url` above is the CLI's stale Phase B URL; the desktop adapter rewrites
> it to `http://local-test-server/patch_<tag>.bin`, consistent with the Edge Gateway poller.

### Option D — Installed app (distribution)

```powershell
cd desktop
npm.cmd run dist           # -> desktop\release\SecureOTA Setup 0.1.0.exe
```

1. Run the installer (per-user install; choose any folder).
2. On the target machine: open the install folder, run
   `resources\gateway\setup-gateway.bat` once (creates the Python venv there).
   The machine needs Python 3.12 installed.
3. Launch **SecureOTA** from the Start Menu. No Node.js required.

> Runtime lookup order for the gateway (dev + installed):
> `SECUREOTA_GATEWAY_DIR` env var → `SECUREOTA_PYTHON` env var →
> venv `gateway\.venv\Scripts\python.exe` (dev) / `resources\gateway\.venv` (installed) →
> system `python`.

### Edge Gateway (Phase 3 runtime — optional, separate deps)

```powershell
cd gateway
.\.venv\Scripts\python.exe -m pip install web3 cryptography aiocoap
.\.venv\Scripts\python.exe secureota\gateway_runtime\main_gateway.py
```

Reads/writes `artifacts/`, serves the firmware over CoAP at `127.0.0.1:5683`.

---

## Verification / quality gates

```powershell
# Python domain models
cd gateway; $env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe quick_test.py

# Desktop shell + renderer
cd desktop; npm.cmd run build:app            # tsc + vite build + bundle
npx electron scripts\preload-smoke.cjs       # sandboxed bridge exposes desktopAPI?

# Renderer alone
cd ui/secureota-ui; npm.cmd run lint; npm.cmd run build
```

---

## Architecture notes

- **Hybrid handoff:** Python owns raw binary manipulation (bsdiff4 + hashing);
  the renderer never sees bytes, only the `ReleaseResult` JSON via IPC.
- **IPC contract** (authoritative: `desktop/src/contracts/`):
  - `patch:generate` `{basePath, targetPath, versionTag}` → `ReleaseResult`
  - `dialog:pick-bin` → `string | null` (native file dialog)
  - `getPathForFile(file)` (preload, `webUtils`)
- **Security posture:** `contextIsolation: true`, `sandbox: true`,
  `nodeIntegration: false`; sandboxed preload inlines channel names (local
  `require` is unavailable there — keep the constants in sync with
  `contracts/ipc.ts`); Python spawned with `shell: false` + sanitized
  `version_tag` (no command injection / path traversal).
- **PythonLocator** resolves the gateway for both dev and installed layouts
  (strategy list above); `ReleaseResult` stays snake_case across IPC to mirror
  the CLI JSON 1:1.
- **UI constraint:** the dashboard is a stateless presentation layer; the
  Atomic Architecture is untouched. Browser mode = simulation; Electron mode =
  real local execution, selected at runtime by the presence of `window.desktopAPI`.
- **Phase 4 (WalletConnect) is deferred** until the contract is deployed.
  Correct payload shape (`contracts/DeltaOTA.sol:79`):
  `proposeRelease(string version, bytes32 goldenHash, string ipfsUrl)` —
  `version` is a **string** ("v1.1"), `goldenHash` must be **0x-prefixed** hex.
  Wallet signing requires internet at runtime (relay + Sepolia RPC) — this is
  independent of the app being installed locally.

---

## Known quirks

1. **`quick_test.py` prints unicode arrows** — crashes on the cp1252 Windows
   console with `UnicodeEncodeError`. Run with `$env:PYTHONIOENCODING="utf-8"`
   first (or replace the `→` characters).
2. **bsdiff4 pip cache** — see setup section above.
3. **Python 3.14** — the default `python` may be 3.14; always create the venv
   with `py -3.12`.
4. **Google Fonts CSS import** — the Tailwind theme imports JetBrains Mono from
   fonts.googleapis.com; offline, the app falls back to the system monospace.
   The Vite CSS-order warning is cosmetic.
5. **Electron dev-mode CSP warning** — shown only while running unpackaged; the
   packaged app does not show it. A stricter CSP for the bundle is future work.
6. **Gitignored by design:** `gateway/artifacts/`, `gateway/fixtures/*.bin`,
   `gateway/.venv/`, `desktop/node_modules`, `desktop/dist`, `desktop/release/`,
   `ui/node_modules`, `ui/dist/` — fresh clones need `fixtures/*.bin`
   regenerated by hand.
