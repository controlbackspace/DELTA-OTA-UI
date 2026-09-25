# Delta-OTA Test Status (8-day run: Sept 23 → Oct 1 panel)

Status legend: **SIM** = demonstrated headless (Python sim/harness, re-runnable
today) · **CODE** = reviewed, compile-verified, hardware-untested (no boards
in hand) · **HW** = proven over the air on Pi + ESP32 (needs arrival day).

| Date | Deliverable | Evidence today | Needs HW day |
|---|---|---|---|
| Sept 23 | D1 Baseline (happy path) | SIM: `run_simulation.py` phase 4 (`[OK] b'test'`); `block_client.py` pass 1 (2.04-final, reassembly exact) | Flash+reboot on ESP32; 1 KB window flush to backup slot on-device |
| Sept 24 (ran Sept 23) | D2 Kill switch | SIM phases 1–2 green + LIVE: revoke→HALT (exit 0, no artifact, device [TIMEOUT]); mismatch→destroyed (device [BLOCKED] 4.01). Evidence: `testing-deliverables/day-02-2026-09-23/` (04/05 revoke, 08/09 mismatch transcripts) | 4.01 handling on-device (`main.cpp` ignores unknown codes — CODE) |
| Sept 25 (ran Sept 24) | D3 Tag corruption + rollback | SIM: threshold proven — Seq A (2 faults + healthy → no abort, counter reset to 0); Seq B (3 consecutive → ABORT at exactly 3, transfer never reassembles). Evidence: `testing-deliverables/day-03-2026-09-24/` (03/04 threshold logs). No node: fault sits downstream of the ledger, bypass-Live output is behaviorally identical | Rollback *execution* (`esp_ota_mark_app_invalid_rollback_and_reboot`) stays CODE (`main.cpp:140-144`), needs HW day |
| Sept 26 (ran Sept 25) | D4 bsdiff stress | SIM: 6-case metrics (identical 140B/0.3ms; noise-64KB 66285B/ratio −0.0114 honest worst case; fw-bump-1.25MB 209B/99.98%/255.4ms) + 128-block sequential fetch, exact reassembly (O(1)-per-chunk proxy). Evidence: `testing-deliverables/day-04-2026-09-25/` | Multi-chunk flash streaming + stack-overflow watch stay CODE (BSS design, 14.7% RAM) |
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
