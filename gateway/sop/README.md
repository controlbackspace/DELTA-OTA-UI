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

`SOP-REPORT.md` is written as a formal evidence report for a review panel: purpose and scope,
experimental setup, one section per statement of the problem (research question, method, principal
result, findings, numbered tables, observations, limitations), a summary table, limitations and
reproducibility. Statement 5 is reserved for the implementation phase.

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

## Experiment Paper tables and the 60-cycle campaign
The approved Experiment Paper (Tables 1 to 4) is filled from recorded data only; the table layouts are never changed
(`thesis_tables.py` renders them). Statistics are the ones in Chapter 3 (`inference.py`).

| Table | Filled by | Command (from `gateway\`) |
|---|---|---|
| 1 Volumetric payload | one static benchmark | `thesis_tables.table1(...)` (done) |
| 2 Hardware and network | Scenarios A and B, ESP32 + this PC as gateway | `python -m sop.device_cycle --serial COM3 --lan-ip 192.168.100.94 --scenarios A,B --static-ram-bytes <SOP 4 figure>` |
| 3 Gateway profiling | gateway-only cycles on the Raspberry Pi | `python -m sop.device_cycle --table3 --gateway-url http://<pi>:8000 --lan-ip 192.168.100.94` |
| 4 Deterministic validation | Scenarios C, D, E, no device | `python -m sop.host_scenarios --trials 60` (done) |

Add `--dry-run` to print the plan. Runs are resumable (`--run <folder>` continues where it stopped). A cycle is `invalid`
(harness or network fault, re-run up to 3 times) or `failed` (the update itself failed; it counts).

**Before the device run** (not automated):
1. Firmware: the updater must print `[Metrics2] decrypt_us= feed_us= flash_us= flash_bytes= stream_us= blocks=` after an update
   (parsed by `serial_parse.py`; definitions in its comment). Rebuild, tag the git revision, reflash the factory image.
2. ESP32 `include/secrets.h`: gateway IP = this PC's LAN address; the key in `DELTA_OTA_KEY_HEX` is the one the gateway will use.
3. Windows Firewall (administrator): allow inbound UDP 5683 for the private profile; for Table 3 also TCP 8000 and 8545.
   `netsh advfirewall firewall add rule name="Delta-OTA CoAP" dir=in action=allow protocol=UDP localport=5683 profile=private`
4. Pi (Table 3): `pip install psutil pyperf`, gateway started with `DELTA_METRICS=1`, memory capped to 1 GB and CPU to 1.4 GHz
   (record `free -m` and `vcgencmd get_config arm_freq`), RPC and contract set from the controller's printed commands.
5. tshark: installed with Wireshark; capture works without administrator rights (`--iface` = adapter number, default 6 = Ethernet).

Gateway telemetry (`gateway_runtime/metrics.py`) is off unless `DELTA_METRICS=1`; the artifact server then also serves
`gateway_metrics.json`. Definitions: polling = mean contract-read time since the previous release; SHA-256 and AES-CCM are
timed with `pyperf`'s clock and the garbage collector off; peak RAM and CPU are `psutil` samples (50 ms) from detection to staging,
CPU as a share of total capacity.

## Chapter 4 data pack and SOP 4 hardware measurement
| Module | What it does | Command (from `gateway\`) |
|---|---|---|
| `chapter4.py` | Regenerates every Chapter 4 statistic from the recorded runs: the statistical analysis, tidy CSVs, SHA-256 manifest | `python -m sop.chapter4 --ab <campaign-AB> --t3 <campaign-T3> --cde <trials.csv> --web3 <on-device-web3> --out <experiment-paper-tables> --sop4 <sop4-supporting-data>` |
| `table_docs.py` | Writes `TABLES-1-AND-4.md` and `TABLES-2-AND-3.md` (approved tables from `thesis_tables.py` plus how-to-read notes and provenance) and refreshes the Appendix of the chapter draft | add `--tables` (and `--draft <CHAPTERS-4-AND-5-DRAFT.md>`) to the `chapter4` command |
| `figures.py` | Seven PNG figures from the same data (needs matplotlib; the gateway venv does not have it) | `python -m sop.figures --ab ... --t3 ... --cde ... --web3 ... --out <experiment-paper-tables>` |
| `web3_hw.py` | SOP 4 hardware part: 60 on-device Web3 ledger checks (local chain, TLS front, flash, capture, restore) | `python -m sop.web3_hw --serial COM3 --lan-ip <PC> --runs 60 --allow-flash` |

Table 2 cycle n is the n-th complete A/B pair (both scenarios `ok` for the same trial), the first 60 pairs. A metric missing in one cycle drops that pair
for that metric only. `inference.py` also holds the supporting tests used in the discussion (sign test, Pearson r, Fisher exact, Wilson interval, Welch t).
`sop4.hw_session` erases `otadata` after `pio run -t upload` (the upload also selects `ota_0`, so the baseline would never boot on a board holding an application).
Put the board back in demonstration state afterwards with `tools\flash_device.bat reset COMx` in the firmware repo.

## Chapter 3 comparators (H and N), the harness race and the confirmation run
| Module | What it does | Command (from `gateway\`) |
|---|---|---|
| `https_hw.py` | Baseline H: the full image over HTTPS (TLS 1.2), 63 downloads in one boot, tshark per TCP stream, writes `campaign/https_runs.csv` | `python -m sop.https_hw --serial COM3 --lan-ip <PC> --iface <n> --runs 63 --allow-flash` |
| `device_cycle.py` (scenario `N`) | Baseline N: the same delta over naked CoAP (plaintext blocks, no AES-CCM); interleaved with a fresh A; the rig flashes the secured or the naked updater on demand | `python -m sop.device_cycle --scenarios A,N --trials 60 --warmup 3 --static-ram-bytes 29416 --static-ram-naked-bytes 28328 ...` |
| `baselines.py` | Analysis of H and N (Equations 3 and 4, the security tax A minus N) and of the confirmation run | add `--n`, `--h`, `--confirm` to the `chapter4` command |
| `thesis_tables.table2s` | Supplementary Table S2 (not an approved table) | via `chapter4 ... --tables` (writes `BASELINES.md`) |

Harness race (found during the N campaign): the updater starts an update by itself once the release is staged; resetting the board then interrupts its ota_0 -> ota_1
backup copy and the delta fails (`delta decode error`). `LocalRig` now starts the capture before publishing and does **not** reset a device that has begun
(`update_interrupted()` in `chapter4.py` detects interrupted cycles in older logs). The firmware side (`https_baseline`, `https_control`, `factory_naked`) is in the firmware
repository, tag `baselines-fw-1`. The gateway's naked framing is switched by `DELTA_NAKED=1` or a flag file (`DELTA_NAKED_FILE`); it is never set in the product.

## Data pack layout and the `pack` command
`python -m sop.pack build --root ../sop-results [--draft <CHAPTERS-4-AND-5-DRAFT.md>]` rebuilds, from the runs listed in `01-raw-data/RUNS-INDEX.csv`, the tidy CSVs
(`01-raw-data/tidy-csv/`), one markdown file per table and the figures (`02-interpretation/`) and the generated writing files (`03-writing/01_statistical-analysis.md`,
`07_baselines-results.md`), and refreshes the Appendix of the draft. `python -m sop.pack publish --root ../sop-results --dest ../testing-deliverables/thesis-data-pack` copies the
light parts (no raw runs, no draft) to a tracked folder for the group. Runs are found by ID: R02 Table 4, R03 Table 2, R04 Table 3, R05 SOP 4 Web3, R06 baseline H, R07 baseline N,
R08 confirmation. Naming rules are in `sop-results/03-writing/00_START-HERE.md` (section 5).
