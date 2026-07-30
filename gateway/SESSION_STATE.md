# Session State — Ledger-Anchored Delta-OTA Framework

## Last Updated
2026-07-30

## Bounded Contexts Identified

| # | Context | Runtime | Role |
|---|---------|---------|------|
| 1 | **Developer GUI** | React/TS (Vite) | Stateless presentation; delta generation, upload, wallet signing |
| 2 | **ManifestRegistry** | Solidity (EVM) | Governance: multi-sig, state machine, kill-switch |
| 3 | **Edge Gateway** | Python AsyncIO | Poll ledger, fetch/verify payload, OSCORE encrypt, CoAP serve |
| 4 | **Target Node** | C/C++ (FreeRTOS) | ESP32 CoAP client, O(1) flash reconstruction |

## Ubiquitous Language Glossary

| Term | Definition |
|------|------------|
| **Golden Hash** | SHA-256 digest of the delta patch; content-addressed identity anchor |
| **Delta Patch** | Binary diff (bsdiff4) between baseline and target firmware |
| **Quorum** | M-of-N multi-signature threshold required to activate a release |
| **Target Node** | ESP32 microcontroller with OTA partition |
| **ReleaseManifest** | Aggregate root on-chain; struct with version, goldenHash, ipfsUrl, signatures |
| **FirmwareRelease** | (Alternative name) mapping(string => FirmwareRelease) keyed by version string |
| **StagedPatch** | Edge Gateway entity managing local binary lifecycle (5 states) |
| **JanpatchHeader** | Binary wire header: magic, source_size, target_size, patch_size, compression_type |

## Aggregate: ReleaseManifest (ManifestRegistry)

**Identity:** version string (e.g. "v1.1") as `mapping(string => FirmwareRelease)`

**Struct fields:**
- `version` (string) — primary key
- `goldenHash` (bytes32) — immutable payload digest
- `ipfsUrl` (string) — raw patch location
- `minNodeRevision` (uint32)
- `signatures` (address[])

**State machine:**
```
Proposed → Active → Deprecated (soft terminal)
                    → Revoked (hard terminal, sets isLive=false, isRevoked=true)
```

**Invariants enforced:**
1. `proposeRelease` must assert `releases[version].goldenHash == bytes32(0)` — no collision
2. Kill-switch must explicitly set `isLive = false` alongside `isRevoked = true`
3. No re-proposal on existing version without explicit reclaim step
4. Developers cannot double-vote (mapping `hasSigned`)

**Events:**
- `ReleaseProposed(string version, bytes32 goldenHash, string ipfsUrl, address proposer)`
- `ReleaseActivated(string version, bytes32 goldenHash)`
- `ReleaseRevoked(string version, bytes32 goldenHash, address revoker)`

## Aggregate: StagedPatch (Edge Gateway)

**Identity:** bound to one `ReleaseManifest` via `manifest.golden_hash`

**State machine:**
```
DISCOVERED → FETCHING → VERIFYING → SERVING
                                    → REVOKED → PURGED
              FETCHING → REVOKED → PURGED
              VERIFYING → REVOKED → PURGED
```
All transitions validated by `transition()` method; illegal raises `ValueError`.

## Aggregate: JanpatchHeader (Wire Format)

**Binary layout:** `<4sIIIB` (17 bytes total)
- magic (4B) — e.g. `b"JNP2"`
- source_size (uint32 LE)
- target_size (uint32 LE)
- patch_size (uint32 LE)
- compression_type (uint8: 0=RAW, 1=HEATSHRINK, 2=BZ2)

## Architectural Decisions (ADRs)

### ADR-1: No Gateway nesting in UI tree
**Status:** Accepted
**Context:** Gateway (Python) and UI (React/TS) are separate runtimes with different lifecycles.
**Decision:** Root layout mirrors Bounded Contexts: `gateway/` and `ui/` as siblings under `Projects/thesis/`.

### ADR-2: UI ↔ Gateway sync via Option B (local REST API)
**Status:** Accepted
**Context:** UI needs to show gateway staging state; gateway must not leak internal lifecycle.
**Decision:** Gateway exposes lightweight control API (FastAPI/aiohttp):
- `GET /api/v1/staged-patches`
- `GET /api/v1/staged-patches/{version}`
- `POST /api/v1/staged-patches/{version}/purge`
- `GET /api/v1/health`
UI never writes through to ledger — only reads gateway cache state.

### ADR-3: Version string as primary key
**Status:** Accepted
**Context:** Version strings are human-readable and simplify off-chain polling.
**Constraint:** `proposeRelease` must guard against key collision via `releases[version].goldenHash == bytes32(0)`.

### ADR-4: Kill-switch mutates isLive
**Status:** Accepted
**Context:** Boolean ambiguity between `isLive` and `isRevoked`.
**Decision:** Contract explicitly sets `isLive = false` when `isRevoked = true`. Off-chain compound logic (`isLive && !isRevoked`) is insufficient for zero-trust.

## Implementation Status

### Built (this session)
- [x] Python domain model package at `gateway/secureota/gateway/domain/`
  - `_enums.py` — `StagedPatchState`, `CompressionType`
  - `_models.py` — `ReleaseManifest`, `StagedPatch`, `JanpatchHeader`
- [x] Smoke test at `gateway/quick_test.py` (12 checks, all passing)
- [x] This session state file

### Pending (Target Node context — next session)
- [ ] ESP32 domain entity / process name
- [ ] CoAP discovery mechanism (push vs poll)
- [ ] Block streaming unit name
- [ ] In-flash reconstruction concept (delta + baseline → target)

## Running Tests
```bash
cd /home/archxnx/Projects/thesis/gateway
python quick_test.py
```
