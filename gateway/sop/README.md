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
| 4 | Web3 offloading footprint (static + heap) | phase P2 |
| 2 | OSCORE vs standard handshake | phase P3 |
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
