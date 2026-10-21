# Reproducibility: regenerate everything, add a run

*Hand-written source (not generated). Numbers are from `01_statistical-analysis.md`; update both together.*

All commands run from the `gateway/` folder of the repository. Python tests: `python -m unittest discover -s sop/tests -t .`.

## Regenerate the generated files

```
python -m sop.pack build --root ../sop-results --draft ../sop-results/CHAPTERS-4-AND-5-DRAFT.md
python -m sop.pack publish --root ../sop-results --dest ../testing-deliverables/thesis-data-pack
```

`build` reads `01-raw-data/RUNS-INDEX.csv`, finds the runs by ID (R02 Table 4, R03 Table 2, R04 Table 3, R05 SOP 4 Web3, R06 baseline H, R07 baseline N, R08 confirmation) and rewrites `01-raw-data/tidy-csv/`, `02-interpretation/` and the generated files of `03-writing/` (`01_statistical-analysis.md`, `07_baselines-results.md`); with `--draft` it also refreshes the Appendix of the chapter draft. The seven figures need matplotlib (the gateway virtual environment has none; `build` uses the Python on PATH that has it, or pass `--no-figures`). `publish` copies the light parts (no run folders, no draft) to the tracked folder for the group.

## How each run was produced

| Run | Command | Code |
|---|---|---|
| R02 Scenarios C, D, E | `python -m sop.host_scenarios --trials 60 --run <folder>` | `gateway/sop/host_scenarios.py` |
| R03 / R08 Scenarios A and B | `python -m sop.device_cycle --serial COM3 --lan-ip <PC> --iface <n> --scenarios A,B --trials 60 --warmup 3 --static-ram-bytes 29416` (R08: `--trials 20`) | `gateway/sop/device_cycle.py` |
| R04 Table 3 (Raspberry Pi) | `python -m sop.device_cycle --table3 --gateway-url http://<pi>:8000 --lan-ip <PC> --trials 60 --warmup 3` | `gateway/sop/device_cycle.py` |
| R05 on-device Web3 | `python -m sop.web3_hw --serial COM3 --lan-ip <PC> --runs 60 --allow-flash` | `gateway/sop/web3_hw.py` |
| R06 baseline H (HTTPS) | `python -m sop.https_hw --serial COM3 --lan-ip <PC> --iface <n> --runs 63 --allow-flash` | `gateway/sop/https_hw.py` |
| R07 baseline N (naked CoAP) | `python -m sop.device_cycle ... --scenarios A,N --trials 60 --warmup 3 --static-ram-bytes 29416 --static-ram-naked-bytes 28328` | `gateway/sop/device_cycle.py` |

A new run is created in `sop-results/<timestamp>/`; move it into `01-raw-data/runs/` under the next ID (`R09_<topic>_<scenarios>_<date>`), add a row to `RUNS-INDEX.csv` (kind, what it feeds, harness version, firmware, git revision) and rerun `build`. Firmware: the firmware repository, tags `campaign-fw-1` and `baselines-fw-1`.

## Integrity

`01-raw-data/tidy-csv/MANIFEST.sha256` holds the SHA-256 of every tidy CSV; the table documents record the hash of every source CSV. Do not open the CSV files in a spreadsheet and save them (booleans and numbers are rewritten); open read-only or copy first.
