# Delta-OTA Session Record — 2026-09-22 → 2026-09-30
## Progress-check prep → hardware OTA → wallet signing → Pi bring-up staging

**Branch:** `feat-desktop-app`.
**Standing rules honored throughout:** no commit/push without explicit word; test tooling additive-only; evidence one-day-one-folder; fresh Hardhat chain per live run.

---

## 1. Gateway reorg + simulation split (Sept 22)

- `gateway_runtime/` split: production (`main_gateway.py`, `coap_server.py`, `security_engine.py`, `blockchain_poller.py` restored to real web3 class) vs `simulation/` (`run_simulation.py`, `simulated_device.py`, `simulated_ledger.py`, later `block_client.py`, `ledger_live_run.py`, `measure_patch.py`).
- 4-phase sim verified (mismatch→`[BLOCKED]`, revoked→`[TIMEOUT]`, tamper→`[FAIL]`, valid→`[OK]`); `test_gateway_flow.py` green; `main_gateway` import-safe. Pushed.

## 2. Desktop app fixes (pushed)

- `patch:generate` IPC signature mismatch (UI positional args vs object request) fixed in `preload.ts`, plus upload-flag defaults and empty-path guard.
- Wallet branch (`feat-wallet-integration`) reviewed and fast-forward merged; follow-up fixes: UI↔gateway contract-address alignment, 2-of-3 narrative, `ALLOW_OFFLINE_PROGRESSION` gate.
- Workflow gating (all 5 steps on true prerequisites), `.bin/.elf/.hex` 3-layer file filtering, step-1 redirect (fake staging removed).
- Error handling: 120 s spawn timeout, honest wallet-connected state, wallet `statusMessage` surfaced in QR modal.

## 3. Testing campaign Days 1–5 (all green, all pushed, one day ahead each)

| Day | Deliverable | Proof |
|---|---|---|
| D1 | Baseline happy path | Bypass 4/4 + live-ledger driver (`BASELINE GREEN`) + propose script + D7 metrics harness |
| D2 | Kill switch | Live revoke→HALT + mismatch→destroyed, both asserted (gateway transcript + device verdicts) |
| D3 | Tag corruption + threshold | `DeviceSession` counter model; 2-faults-reset vs 3-faults-abort sequences |
| D4 | bsdiff stress | 6-case metrics (incl. honest negative-ratio noise case) + 128-block sequential fetch |
| D5 | Interruption | Mid-transfer drop (no-2.04-no-commit), read-only serving proof, WinError-10054 fix, harness exit-code fix |

- Status sheet `TEST-STATUS.md` tracks every claim as SIM / CODE / HW (panel-honesty rule: never present CODE as measured).
- Evidence convention: `testing-deliverables/day-XX/`, untracked-until-pushed, frozen after filing.

## 4. Network plan (docs, committed)

- `setup-network.sh` (hotspot `192.168.50.1` primary / LAN-static `192.168.100.50` fallback, writes `DELTA_BIND_ADDR`), `NETWORK.md` runbook + pre-flight checklist, `setup.sh` preserves bind addr. Pi OS: Bookworm 64-bit (NetworkManager assumption).

## 5. Hardware: ESP32 bring-up → full OTA on silicon (Sept 28–29)

**Bring-up saga (all resolved):** CP2102 driver triangle → COM3 → partition/app offset mismatch (`0x10000` vs `0x20000` boot loop, fixed `partitions.csv`) → brownout reset loop (marginal USB power; isolated with no-RF diagnostic, fixed by cable/port swap) → weak auto-reset circuit (manual BOOT every flash on this unit) → Wi-Fi join on home `2.4GHZ`, gateway = laptop `.100.94`.

**Four hardware-found firmware bugs** (sim could catch none — Python client strips framing, never dupes, never drops finals):
1. Dead request path (`loop()` never called `requestChunk`) → MID-deduped 200 ms pull driver.
2. CoAP option/0xFF marker parsed as payload (1025 > 1024 fail) → RFC 7252 option walker.
3. Duplicate responses double-buffered → size mismatch reject → dedupe gate (buffer only on MID match).
4. Final block treated as pure marker (tail dropped → `0x1503`) → finalize-through-data-path.

**Proven on silicon:** 739-block authenticated transfers, `esp_ota_end` passes, boot into `ota_0` + rotation (`ota_0`→`ota_1`→`ota_0`, zero rollbacks on good images), rollback executed on faulty images (dummy + pre-fix staged), factory always rebootable (no brick), NVS self-test pin on both slots (after proving IDF never yields PENDING — stale-mark theory killed by erase-confirmed rerun), AES-CCM `n=743 avg≈3.07 ms` on-device, kill-switch halt + 4.01 refusal recognized (`Refused 0x81`, after empty-response guard fix).

**Also:** golden v1.0 archived (`golden-v1.0/` + revert procedure); v1.1 version marker; `DELTA_PAYLOAD` + `GOLDEN_HASH` overrides; CCM 64 KB single-frame ceiling documented (blocks-only serving for firmware images).

## 6. Wallet signing (Sept 29–30, pushed through `4400de7`)

- Real-signer priority (`getSigner()`: phone → injected → labeled dev fallback) + chain-31337 guard + session sync + per-tx origin labels.
- **Fake-QR root cause:** overlay rendered hardcoded `wc:7f9a…` with no session ever started → deleted; QR renders only from live URI, else error + retry; AppKit errors surfaced.
- **Relay rejection:** `Failed to publish payload` traced to `@walletconnect/core` (unregistered project ID) → real ID wired, bundle-verified.
- **Terminal tail-f bug:** prepend-vs-autoscroll mismatch → append restored.
- **Tunnel saga:** MetaMask-mobile HTTPS requirement → cloudflared (quick tunnel adopted; persistent retired; service-uninstall friction noted) → custom-hostname DNS (CNAME to `<tunnel-id>.cfargotunnel.com`, DNS-only, CAA trap noted) → `WALLET-NETWORK.md` procedure doc.
- Verified live: QR pairing, per-payload phone prompts, terminal receipt flow.

## 7. Security backlog P0–P3 (groupmate-owned, awaiting branch changes)

- **P0:** offline-progression removal, chain-as-truth refresh, contract-address validation, dev-signer gating, proposer≠approver guard, key-distribution assumption doc, wallet E2E evidence.
- **P1:** placeholder write-path blocks, supply-chain triage, D7 poll-RTT mining, Sept 30 lock-down rehearsal (incl. v1.0-fast doors-open image), Pi bring-up, `main.cpp` backup.
- **P2:** CSP, auto-update story, gateway env perms, PSK rotation note, log injection.
- **P3 (post-defense):** device version check, bare-metal/Class-2 path, on-device delta apply, offline wallet story, multi-operator UI.
- Key honest findings preserved: no human-auth in wallet UX (possession = identity); offline removal is hygiene, not the Sybil fix; test bench holds all keys on one phone (labeled, not mistaken for posture).

## 8. Open items / next actions

1. **Pi bring-up** (reader arrived): image Bookworm 64-bit → SSH → clone → `setup-network.sh hotspot` → `setup.sh` → pre-flight → optional Pi→ESP32 OTA.
2. **Wallet E2E close-out:** stable-hostname swap → per-payload prompts + unimported-account negative → evidence pack.
3. **D7 remainder:** poll-RTT mining from node logs + CoAP-latency statement (~30 min desk work).
4. **Sept 30 lock-down:** golden revert, v1.0-fast image, `dist/` rebuild, `defense-oct1` tag, 25-min rehearsal.
5. **Thesis `main.cpp`** (8 iterations, unversioned — P1-6 backup pending): partition fix, profiles, TX cap, request driver, option parser, dedupe, refusal handling, NVS pin + timing + marker.

## 9. Invariants that held all session

- Production/sim split; env-gated overrides; no core-logic edits for tests.
- Fresh chain per live run; nodes killed after; ports verified free.
- Evidence frozen once filed; SIM/CODE/HW labeling honest throughout.
- Nothing pushed without the word (all pushes logged above).
