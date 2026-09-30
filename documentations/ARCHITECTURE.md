# Delta-OTA Deployment Architecture

Monorepo, independently deployable units. Units share **nothing but the
network**: no shared disk, no shared imports across unit boundaries. The only
exceptions are explicit bench/test seams, labeled as such in code.

## Deploy units (directory → machine → runtime)

| Unit | Directory | Runs on | Runtime |
|---|---|---|---|
| Developer console UI | `ui/secureota-ui/` (bundled into `desktop/dist/`) | Developer workstation | Electron + renderer |
| Release builder | `gateway/make_release.py`, `gateway/secureota/release_builder/`, `gateway/serve_artifacts.py` | Developer workstation (spawned by the app; standalone via CLI) | Python venv (`gateway/requirements.txt`) |
| Artifact hosting | `gateway/serve_artifacts.py` | Workstation or infra | Plain HTTP `:8000`, patch files only |
| Ledger | `blockchain/` (DeltaOTA.sol, Hardhat) | Any node (laptop, Pi, third machine) | Hardhat / EVM RPC `:8545` |
| Edge gateway | `gateway/secureota/gateway_runtime/` | Pi (field) or laptop (bench) | Python venv + systemd unit |
| Device firmware | PlatformIO `Thesis` project (outside this repo) | ESP32 fleet | Bare metal (Arduino) |
| Test/sim harness | `gateway/secureota/gateway_runtime/simulation/`, `testing-deliverables/` | Developer workstation | Python venv, evidence logs |

## Interface contracts (the only legal crossings)

1. **Console → world**: patch bytes at a URL + `(version, goldenHash, patchUrl)`
   anchored on-chain via wallet-signed `proposeRelease` / `approveRelease` /
   `revokeRelease`. The contract field is named `ipfsUrl` but carries any URL
   string opaquely (legacy name; content is an HTTP(S) URL in current use).
2. **World → gateway**: ledger state via Web3 polls + patch bytes via HTTP(S)
   download of the on-chain URL. The gateway hashes the *downloaded bytes*
   against the golden hash before anything touches disk.
3. **Gateway → device**: CoAP/UDP `:5683` — whole-frame `/firmware` plus
   MID-indexed `/patch` blocks (`2.05` data / `2.04` final-with-tail /
   `4.01` kill-parity / `4.04` range), each an independent
   `nonce(13)‖cipher‖tag(16)` AES-CCM frame under the pre-shared key.

## Hard rules

- **Gateway code must never import builder code.** The builder lives with the
  console because it *is* console tooling that happens to sit in `gateway/`.
  (A post-defense move to top-level `console/` is scoped but intentionally
  deferred: packaging paths, sim imports, and evidence all key off current
  locations.)
- **`DELTA_PAYLOAD` is bench/test only.** Production resolves payloads
  exclusively through download-then-hash. Any log line saying "local payload
  override" marks a non-production run.
- **`artifacts/` is per-machine runtime state**, never a transport: state
  files, encrypted frames, and block slices are generated where they are
  served. Copying `artifacts/` between machines (notably `gateway_state.json`)
  produces phantom-version bugs.
- **URL schemes the gateway accepts: `http(s)` + `file` (tests).** Bare
  `ipfs://` is refused loudly — native IPFS needs a gateway in front, which
  is P3 future work, not a silent gap.

## Supported topologies (all observed working)

- **Bench**: everything on one laptop (node `127.0.0.1`, gateway LAN IP).
- **Split**: node on laptop A (`--hostname 0.0.0.0` + firewall), gateway on
  Pi (env `DELTA_RPC_URL` + shared `DELTA_CONTRACT_ADDRESS`).
- **All-on-Pi**: full `setup.sh` stack; UI points RPC at the Pi (requires the
  UI RPC-endpoint fix — open item, not yet built).
- **Venue**: Pi-hosted hotspot (`192.168.50.1`, see `NETWORK.md`) + direct
  Ethernet laptop↔Pi (`10.10.10.x`); no venue infrastructure participates.
