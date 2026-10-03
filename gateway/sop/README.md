# SOP evidence runner

One command that runs the experiments behind the thesis SOPs, stores the raw
data, and writes `SOP-REPORT.md`.

```
gateway\sop-run.bat                    # double-click: preflight + every implemented step + report
.venv\Scripts\python -m sop sop1       # one step (from gateway\)
.venv\Scripts\python -m sop sop1 --n 10 --firmware-dir C:\path\to\Thesis
.venv\Scripts\python -m sop report     # rebuild the report of the latest run
.venv\Scripts\python -m unittest discover -s sop/tests -t .    # unit tests
```

Results go to `sop-results/<UTC stamp>/` (git-ignored): `SOP-REPORT.md`,
`results.json`, `meta.json` (commit, versions, SHA-256 of the input images),
and `sopN/*.csv|json`. `--run DIR` adds a step to an existing run.

## What each number means
Every table is tagged **measured** (taken here), **modelled** (computed from
stated assumptions, e.g. link rates) or **cited** (from the literature). A step
that cannot run is reported as skipped / not implemented; nothing is invented.

## Status
| SOP | Step | State |
|---|---|---|
| 1 | delta footprint and network load (real v1.0 -> v1.1 pair + stress cases) | **done** (offline) |
| 3 | contract suite, attack matrix, live-chain refusals, revoke-to-halt latency + gas | **done** (offline; live part needs Node and a free UDP 5683) |
| 4 | Web3 offloading: static footprint (offline) + heap/timing (hardware, guarded flash) | **done** (static); hardware part untested on a board |
| 2 | OSCORE-style framing vs a standard handshake (not RFC 8613 OSCORE) | **done** (gateway host); device numbers via `--factory-log` and the SOP 4 hardware run |
| 5 | 60-cycle campaign | deferred until the tool is approved |

SOP 1 inputs: `release-images/app-v1.0.bin` and `app-v1.1.bin` of the firmware
project (found via `--firmware-dir`, `DELTA_FIRMWARE_DIR`, or
`~/Documents/PlatformIO/Projects/Thesis`), the 100 KB test pair in `fixtures/`,
and the frozen synthetic cases of `simulation/measure_patch.py`.

## SOP 3 details
`python -m sop sop3 [--trials 30] [--n-latency 10] [--live-trials 3] [--no-chain] [--hardhat-port 18545]`

- **A.** `npx hardhat test` with a JSON report (`SOP_MOCHA_JSON`, inert unless set).
- **B.** Nine injected faults x N seeded trials against the production checks
  (gateway hash/ledger check, per-block AES-CCM tag, end-of-transfer image digest),
  with the stopping layer and a Wilson 95% bound per attack.
- **C.** A fresh Hardhat node on its own port plus the real `main_gateway.py`
  subprocess (never your chain on 8545). Measures outsider calls, wrong-hash
  releases, and revoke-to-halt latency (revokes sent at a seeded random point of
  the gateway's poll cycle) and gas per call. Needs UDP 5683 free: stop a running
  gateway first. If Node or the port is unavailable, part C is reported as skipped.

## SOP 4 details
`python -m sop sop4 [--serial COM3 --allow-flash] [--web3-host H --web3-contract 0x... --web3-port 443 --web3-version v1.1] [--factory-log FILE] [--hw-dry-run] [--capture-seconds 90]`

Builds three PlatformIO environments of the firmware project and compares them on the same ESP32 + Wi-Fi base:
`web3_control` (Wi-Fi only), `factory` (the Delta-OTA updater) and `web3_baseline` (control + HTTPS + Keccak-256 +
`eth_call` + ABI decode: a read-only **lower bound** of an on-device Web3 client). Output: whole-image sizes, the
increment of each design over the control against the Class 2 budget (250 KiB flash / 50 KiB RAM), link-map groups
for the extra flash, and the largest static-RAM symbols.

- **Static part** needs only the PlatformIO toolchain (`pio` on PATH or in `~/.platformio`).
- **Hardware part** (heap and timing of TLS, which live on the heap, not in static RAM): with `--serial` AND
  `--allow-flash` it flashes `web3_baseline`, captures `[MEM]`/`[Web3]` lines, and **always restores the factory
  updater** with `toolslash_device.bat factory COMx`. Flashing replaces the updater, which is why it needs the
  explicit flag; `--hw-dry-run` prints the plan. The device needs the Wi-Fi in `include/secrets.h` and an HTTPS
  JSON-RPC endpoint (your Funnel URL: `--web3-host`).
- `--factory-log` takes an existing serial capture of an update and reports the stream's peak heap.
- Firmware sources: `src/baseline/` in the firmware project; `tools/host_test_baseline.cpp` tests the Keccak and ABI
  decoder on the host (`gateway/sop/tests/test_baseline_firmware.py` compares them with web3 when g++ exists).

## SOP 2 details
`python -m sop sop2 [--ops 2000] [--handshakes 50] [--factory-log FILE]`

Scope is stated in the report: the framing is **OSCORE-style AEAD framing** (pre-shared key, AES-CCM, 13-byte nonce,
16-byte tag, no handshake), not RFC 8613 OSCORE. Measured on the gateway host: AES-CCM seal/open per 1 KiB block,
key schedule, sealing the real update stream, and a complete in-memory TLS 1.2 handshake (CPU time and exact
bytes/flights). Literature overheads (RFC 8613, TLS 1.2, DTLS 1.2) are labelled **cited**; handshake airtime is
**modelled**. Device numbers come from a supplied serial capture of an update (`--factory-log`, the `[Metrics]` line)
and from the SOP 4 hardware run in the same `--run` directory (TLS connect time and peak heap); without them the
device side is reported as skipped. `python -m sop all` runs sop2 last for that reason.
