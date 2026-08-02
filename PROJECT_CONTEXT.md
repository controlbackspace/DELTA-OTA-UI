# Securing Delta-OTA for Constrained IoT via OSCORE and Ledger-Anchored Release Governance

## Project Overview
- **Goal:** Secure delta OTA updates for constrained IoT devices.
- **Target hardware:** ESP32 acting as a Class 2 constrained node.
- **Constraint:** Strict time limits due to concurrent industry OJT — prioritize backend mechanics over front-end scope creep; work in compartmentalized, efficient batches.

## Current Progress — What Has Been Built & Decided

### Phase 3 & 4: Edge Gateway and Constrained Client (Ready for Testing)
- **Python Gateway:** Async scripts drafted: `coap_server.py`, `gateway.py`, `blockchain_poller.py`, `security_engine.py`.
- **Capabilities:**
  - Mocks blockchain polling.
  - Verifies downloaded binary patches against a simulated SHA-256 `goldenHash`.
  - Wraps payload in OSCORE AES-CCM encryption (13-byte Nonce, 128-bit pre-shared key).
  - Serves payload via async CoAP server on port **5683**.
- **C++ ESP32 Client:** Maps to: CoAP GET request → extract OSCORE frame → hardware-accelerated AES-CCM decryption via mbedTLS → process patch with strict **1 KB sliding window buffer** (prevents heap overflow).

### Phase 1: Ledger-Anchored Governance (Drafted & Ready for Deployment)
- **Smart Contract `DeltaOTA.sol`:** Strict, immutable ACL + registry.
- **Capabilities:**
  - Hardcoded **M-of-N threshold: 2-of-3 signatures** required to promote a firmware hash to `Live` state.
  - `FirmwareRelease` struct mapping; duplicate-vote prevention.
  - Single-actor `revokeRelease` emergency kill switch.

### Phase 2: Orchestrator Interface (UI Built)
- **Web Frontend:** React/Node app running locally. Dark-mode dashboard for staging binaries, generating deltas, viewing on-chain firmware ledger.
- **Architecture shift:** UI uses static JSON presets for hardware constraints (e.g., ESP32 Target Node) instead of dynamic network discovery — prevents scope creep, avoids browser sandbox networking restrictions.

## Architectural Strategy: The Hybrid Handoff
Bridge between browser security restrictions and heavy binary manipulation:

| Layer | Responsibility |
|---|---|
| **Python Backend** | All raw binary manipulation (BSDIFF4) and cryptographic hashing |
| **Web App Frontend** | Receives hash from Python; handles Web3 wallet connection (MetaMask); signs and broadcasts transactions to Ethereum |

## Execution Roadmap (Backend → Blockchain → Frontend Integration)

### Phase B: Python Backend Engine (Priority 1)
- **B.1 (BSDIFF4 Integration):** Script ingests base firmware (`v1.0.bin`) + target (`v1.1.bin`), runs bsdiff4, outputs physical `patch.bin`.
- **B.2 (Cryptographic Hashing):** `hashlib` computes exact SHA-256 Golden Hash of generated `patch.bin`.
- **B.3 (Local Hosting):** Lightweight Python HTTP server or mock IPFS script to host `patch.bin` and produce a static download URL for the Phase 3 Gateway.

### Phase A: Blockchain Infrastructure Initialization (Priority 2)
- **A.1 (Local Deployment):** Compile and deploy `DeltaOTA.sol` on a local test network (Hardhat or Ganache). Initialize constructor with the 3 authorized developer wallet addresses.
- **A.2 (Extraction):** Extract deployed Contract Address + JSON ABI for frontend integration.

### Phase C: Web3 Frontend Integration (Priority 3)
- **C.1 (Wallet Integration):** `ethers.js` or `web3.js` in the existing frontend to trigger MetaMask connection.
- **C.2 (Transaction Execution):** Ingest Golden Hash + URL from Phase B → package into `proposeRelease` payload → prompt user to sign via MetaMask.
- **C.3 (Governance Execution):** Wire UI buttons for remaining threshold developers to call `approveRelease` and `revokeRelease` on the live contract.
