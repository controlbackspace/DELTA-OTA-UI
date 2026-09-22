# Delta-OTA Test Status (8-day run: Sept 23 → Oct 1 panel)

Status legend: **SIM** = demonstrated headless (Python sim/harness, re-runnable
today) · **CODE** = reviewed, compile-verified, hardware-untested (no boards
in hand) · **HW** = proven over the air on Pi + ESP32 (needs arrival day).

| Date | Deliverable | Evidence today | Needs HW day |
|---|---|---|---|
| Sept 23 | D1 Baseline (happy path) | SIM: `run_simulation.py` phase 4 (`[OK] b'test'`); `block_client.py` pass 1 (2.04-final, reassembly exact) | Flash+reboot on ESP32; 1 KB window flush to backup slot on-device |
| Sept 24 | D2 Kill switch | SIM: phase 1 (`[BLOCKED]` 4.01), phase 2 (`[TIMEOUT]` halt) | 4.01 handling on-device (`main.cpp` ignores unknown codes — CODE) |
| Sept 25 | D3 Tag corruption + rollback | SIM: phase 3 (`[FAIL]` tag mismatch); harness: per-block auth | `AUTH_FAIL_THRESHOLD=3` → abort → boot old image (CODE, `main.cpp:250-268`) |
| Sept 26 | D4 bsdiff stress | SIM + harness pass 2 (3-block 3000 B image, exact reassembly); gateway bsdiff real | Multi-chunk flash streaming on-device; stack-overflow watch (BSS design — CODE) |
| Sept 27 | D5 Interruption / power loss | CODE: `_abortOta`, `_rollbackToBackup`, anti-brick self-test (`main.cpp:67-144`) | Real power-cut + A/B isolation proof |
| Sept 28 | D6 Hardware migration | CODE: `setup.sh`, `setup-network.sh` (bash -n), `NETWORK.md` runbook | Full runbook execution on arrival (conditional on boards) |
| Sept 29 | D7 Metrics | Gateway-side timings measurable now (bsdiff, poll, encrypt) | ESP32 `mbedtls_ccm_auth_decrypt` ms + CoAP latency on-device |
| Sept 30 | D8 Rehearsal | Sim dry run green today | Re-run on FINAL network profile (hotspot default) |

## Rerun commands (all green 2026-09-22)

- `python simulation/run_simulation.py` — 4 phases PASS
- `python simulation/block_client.py` — both passes PASS
- `python test_gateway_flow.py` — TEST 1 + TEST 2 PASS
- `pio run` (Thesis) — `[SUCCESS]`, RAM 14.7%, Flash 57.2%

## Panel narrative rule

Never present CODE items as measured. Sim/harness numbers are real measurements
of the Python stack; ESP32-side numbers are code-level until the HW column fills.
