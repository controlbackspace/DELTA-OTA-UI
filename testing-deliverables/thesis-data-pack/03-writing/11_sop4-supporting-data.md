# SOP 4 supporting data: what offloading Web3 logic to the gateway saves on the device

*SOP 4: What is the measurable efficiency of offloading Web3 logic to a dedicated Edge Gateway in terms of preserving the physical memory envelope (SRAM) and processing cycles of the target node?*

This folder is **supporting evidence**. It is not one of the four approved instruments (Tables 1 to 4), so none of it goes into those tables. It feeds the text of Section 4.6 of the draft.
All numbers below are generated from the recorded files by `python -m sop.pack build` (see `01_statistical-analysis.md`, section 9).

## 1. What was measured

| Part | How | Where |
|---|---|---|
| Static flash and RAM of three builds (Wi-Fi-only control, our updater, a read-only on-device Web3 client) | PlatformIO build output, evidence run of 2026-10-07 | `02-interpretation/tables/sop4-static-footprint.md` |
| Heap peak of our updater during an update | `[MEM]` markers in the serial log of each A and B cycle (60 pairs, 58 with a value in both cycles) | `sop4_updater-heap-peak.csv` |
| **Time and heap of the on-device Web3 client** | The `web3_baseline` firmware on the ESP32, 60 ledger checks in one boot (2026-10-19) | `01-raw-data/runs/R05_sop4_web3-client-on-device_2026-10-19/`, `sop4_web3-checks.csv` |

The on-device client does what a device would have to do without a gateway: open a TLS 1.2 connection (ECDHE-ECDSA), POST a JSON-RPC `eth_call` for release v1.1, hash the call data with Keccak-256, and decode the answer.
It is a **lower bound** of a real client: read-only, no signing, no certificate validation (`setInsecure`), default TLS buffer sizes of the ESP32 framework.

Set-up of the measurement: local Hardhat node, contract deployed, release v1.1 live (2 of 3 approvals); a TLS front on the gateway PC's LAN (self-signed ECDSA P-256, TLS 1.2, port 8545) in front of the node; the ESP32 on Wi-Fi 2.4 GHz.
All 60 checks returned the right state (approvals 2, live, not revoked).

## 2. Results

| One ledger check on the ESP32 (60 checks) | Mean | SD | Largest | 99%/95% limit (Eq. 5) |
|---|---|---|---|---|
| TLS connect and handshake (ms) | 1,364.0 | 27.7 | 1,447 | 1,441.9 |
| Request and response (ms) | 49.5 | 16.3 | 119 | 95.3 |
| Keccak-256 of the call data (µs) | 545.8 | 12.6 | 641 | 581.1 |
| ABI decode (µs) | 131.8 | 10.4 | 192 | 161.0 |
| **One complete check (ms)** | **1,414.1** | 38.8 | 1,537.7 | **1,523.0** |

- The TLS handshake is 96.5% of the time of a check.
- **Peak heap used by the client: 52,000 B (50.8 KiB)**, the highest over the 60 checks (start free heap minus the lowest free heap; exact).
- The gateway's contract poll on the capped Raspberry Pi (Table 3) is **54.13 ms** (SD 19.73): the device takes 26 times longer per check. The comparison is not exact: the gateway reads the local node over plain HTTP, the device over TLS (as a public endpoint would require).
- If a device polled the ledger at the gateway's 5 s interval, 28% of its time would go to ledger checks (1.414 s of every 5 s).

## 3. Like-for-like comparison (the Equation 4 form)

The offloaded design is the updater alone. The same device **not** offloading needs the updater **and** the Web3 client.

| Resource | Offloaded (updater only) | Not offloaded (updater + on-device Web3) | Reduction |
|---|---|---|---|
| Flash | 43,040 B (16.8% of 250 KiB) | 199,912 B (78.1%) | **78.47%** |
| Static RAM | 29,400 B (57.4% of 50 KiB) | 32,644 B (63.8%) | 9.94% |
| Peak RAM, static + heap (offloaded at the mean heap, 6,148 B) | 35,548 B (69.4%) | 84,644 B (165.3%) | **58.00%** |
| Peak RAM (offloaded at the upper tolerance limit of the heap, 11,057 B) | 40,457 B (79.0%) | 84,644 B | 52.20% |

- The Web3 client alone: 3,244 B static + 52,000 B heap = 55,244 B, **108% of the 50 KiB Class 2 RAM budget**, before any update logic.
- Its heap peak is **8.5 times** the updater's mean heap peak and 4.7 times the updater's upper limit.
- The peak-RAM rows add the static increment to the larger of the two heap peaks (assuming the two do not coincide), which **understates** the not-offloaded total.

## 4. What the data do **not** show (say this in the thesis)

1. A minimal read-only Web3 client taken **alone** has less static RAM than the whole updater (3,244 B against 29,400 B). The updater's RAM is mainly the delta decoder (`g_decoder`, 20,312 B), which belongs to differencing (SOP 1/5), not to offloading. Compare like with like (section 3).
2. The updater's heap peak did **not** differ significantly between delta and full binary (58 pairs: 6,148 B against 6,952 B, p = 0.158).
3. The client is a lower bound; a tuned TLS configuration (smaller record buffers) would reduce its heap, and a remote endpoint would add network time. The 60 checks are repeated measurements in one boot, not 60 independent sessions.
4. Two heap values (one A cycle, one B cycle) are missing in the campaign logs; those pairs are dropped for the heap comparison only.

## 5. Files

| File | Content |
|---|---|
| `01-raw-data/runs/R05_sop4_web3-client-on-device_2026-10-19/raw/serial-web3_baseline.log` | The full serial capture of the 60 checks (timestamps from the host) |
| `01-raw-data/runs/R05_sop4_web3-client-on-device_2026-10-19/parsed.json` | The parsed capture |
| `01-raw-data/runs/R05_sop4_web3-client-on-device_2026-10-19/raw/pio-upload-web3_baseline.log`, `erase-otadata-after-upload.log`, `restore-factory.log` | Flash, boot-selector erase and restore logs |
| `01-raw-data/runs/R05_sop4_web3-client-on-device_2026-10-19/raw/hardhat-node.log`, `front-cert.pem` | The test chain log and the throwaway TLS certificate (the private key was not kept) |
| `sop4_web3-checks.csv` | 60 rows: the four timings, the total, and the free heap after each check |
| `sop4_updater-heap-peak.csv` | Heap peak and minimum free heap of the updater for the 60 A and 60 B pairs |
| `02-interpretation/tables/sop4-static-footprint.md` | Tables 10 to 14 of the SOP 4 evidence (static sizes) |
| `01-raw-data/discarded/` | Two earlier tries that never ran the baseline (see its `README.md`) |

## 6. Reproduce

From `gateway/` (needs the ESP32 on a COM port, PlatformIO, and the firmware project; **it replaces the factory updater until restored**):

```
python -m sop.web3_hw --serial COM3 --lan-ip <this PC's LAN address> --runs 60 --allow-flash
python -m sop.pack build --root ../sop-results
```

Then put the board back in demonstration state with `tools\flash_device.bat reset COM3` (firmware repo): erase, factory updater, app v1.0.
Lesson recorded here: `pio run -t upload` also selects the `ota_0` slot, so `otadata` must be erased **after** the upload, or the board keeps running the old application (the first two attempts failed this way; fixed in `sop4.hw_session`).
