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
| 3 | ledger reliability, attack matrix, revoke-to-halt latency | phase P1 |
| 4 | Web3 offloading footprint (static + heap) | phase P2 |
| 2 | OSCORE vs standard handshake | phase P3 |
| 5 | 60-cycle campaign | deferred until the tool is approved |

SOP 1 inputs: `release-images/app-v1.0.bin` and `app-v1.1.bin` of the firmware
project (found via `--firmware-dir`, `DELTA_FIRMWARE_DIR`, or
`~/Documents/PlatformIO/Projects/Thesis`), the 100 KB test pair in `fixtures/`,
and the frozen synthetic cases of `simulation/measure_patch.py`.
