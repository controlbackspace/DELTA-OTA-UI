# Scope, test bed and method notes

*Hand-written source (not generated). Numbers are from `01_statistical-analysis.md`; update both together.*

## Scope (from Chapter 1, as it applies to the data)

The study evaluates the feasibility and performance of a multi-layered firmware deployment framework on Class 2 constrained devices: payload optimisation by binary differencing, OSCORE-style per-block encryption over CoAP, ledger-anchored release governance (2-of-3 approvals, kill switch) and an Edge Gateway that offloads Web3 work. Physical-layer attacks, hardware key storage and network-layer denial of service are excluded; validation is limited to a small cluster of nodes (here one ESP32) and one firmware pair (v1.0 to v1.1); fleet-scale orchestration and gas-fee optimisation are left to future work.

## Test bed

| Part | What was used |
|---|---|
| Target device | one ESP32 (Wi-Fi 2.4 GHz), factory updater + two OTA partitions; all device figures from its serial log |
| Gateway, Scenarios A, B, N and the confirmation run | the development PC (Windows 11), Python gateway, local Hardhat chain, tshark capture |
| Gateway, Table 3 | Raspberry Pi 4 Model B limited to Pi 3B+ memory and clock (905 MB visible, `arm_freq=1400`, 4 cores, swap present) |
| Firmware | `campaign-fw-1` (updater with the `[Metrics2]` line); `baselines-fw-1` adds the separate `https_baseline`, `https_control` and `factory_naked` builds |
| Statistics | `gateway/sop/inference.py` (Equations 1 to 6 and the supporting tests); K = 2.8071 for n = 60 (99% coverage, 95% confidence); alpha = 0.05, Bonferroni 0.01 for the five primary tests |

## What each column means

### Table 2 (Scenarios A and B)
- **Cycle n = the n-th complete A/B pair.** A pair is a trial number that both Scenario A and Scenario B finished successfully; a failed cycle has no completion time, so it is not a pair.
  Table cycle to campaign trial number: 1=1, 2=2, 3=3, 4=4, 5=5, 6=6, 7=8, 8=9, 9=10, 10=12, 11=13, 12=14, 13=16, 14=17, 15=18, 16=19, 17=20, 18=22, 19=23, 20=24, 21=25, 22=26, 23=27, 24=28, 25=29, 26=30, 27=31, 28=32, 29=33, 30=35, 31=36, 32=37, 33=38, 34=39, 35=40, 36=41, 37=42, 38=44, 39=45, 40=46, 41=47, 42=48, 43=49, 44=50, 45=51, 46=53, 47=54, 48=55, 49=56, 50=57, 51=58, 52=59, 53=60, 54=61, 55=63, 56=64, 57=65, 58=67, 59=68, 60=69.
- **Wireshark TTC** = first device `GET /patch` to the gateway's last `2.04` in the same capture (tshark on the gateway PC).
- **ESP32 Peak RAM** = static RAM of our update technology (updater image minus the Wi-Fi-only control, 28.73 KB). It is a build property, so it is the same in every row and its SD is 0 (no t-test). The measured heap peak is reported separately in `03-writing/01_statistical-analysis.md`.
- **Decryption + Reconstruction** = device AES-CCM time plus the delta decoder time (inflate, merge with the old flash, flash writes), from the `[Metrics2]` serial line. Scenario B is **N/A** by the approved layout; its measured value is in `01-raw-data/tidy-csv/table2_ab-pairs.csv`.
- **Flash write throughput** = bytes written by `esp_ota_write` over the time spent in `esp_ota_begin` plus `esp_ota_write`.
- **STAT rows** = Equation 1 (mean) and Equation 2 (sample standard deviation) per scenario.

### Table 3 (gateway profile)
- 60 gateway-only cycles after 3 discarded warm-up cycles, on a Raspberry Pi 4 Model B limited to Raspberry Pi 3B+ memory and clock: `free -m` 905 MB total (1 GB cap, `total_mem=1024`), `arm_freq=1400` (measured 1,400,361,344 Hz), 4 cores, swap enabled (904 MB); recorded on the Pi on 2026-10-19 (before the caps: 3,795 MB and 1,800 MHz).
- **Polling** = mean time of the contract reads since the previous release (a LAN call to the chain on the PC). **SHA-256** and **AES-CCM encapsulation** (24 blocks) are timed with the pyperf clock, garbage collector off.
  **Peak RAM** and **CPU** are psutil samples (50 ms) from detection to staging; CPU is a share of total capacity (4 cores).
- **STAT: Average** = Equation 1. The standard deviations and tolerance limits are in `03-writing/01_statistical-analysis.md` section 7.

## Chapter 3 is fixed: how each difference is presented (Chapter 3 is not edited)

Chapter 3 and the approved Experiment Paper stay as they are. Chapter 4 explains how the plan was carried out, in its own section (draft Section 4.1.3, "How the plan was carried out"), and the limitations list what was not done.
Rule of thumb: **where Chapter 3 contradicts itself, follow the part the approved Experiment Paper follows, and say so.**

### B1. Not deviations: Chapter 3 itself says the same (cite it)
| Topic | Where Chapter 3 / the approved paper says it | What to write in Chapter 4 |
|---|---|---|
| The comparison is delta against full binary through the same pipeline | Chapter 3, *Test Scenarios*: "Scenario B ... acting as the internal control benchmark ... the same v1.0 to v1.1 update without the delta patching algorithm"; *Research Design* and *Data Analysis* compare against "Full-OTA"; Experiment Paper, Instrument 2: "isolates the architectural efficiency against the Internal Control" | "Scenario B, the internal control defined in Chapter 3, is the comparison." The Equation 3 and 4 passage that names a standard-HTTPS "Baseline A" and a naked-CoAP "Baseline B" refers to scenarios that are not among the five scenarios of Chapter 3; the five scenarios and the approved Experiment Paper govern. |
| Wireshark | Experiment Paper: "Wireshark (Time-to-Completion)" | The capture used tshark, Wireshark's command-line tool, on the gateway PC |
| Gateway RAM and CPU tool | Experiment Paper, Table 3: Python psutil (Chapter 3 text names `memory_profiler`) | psutil, as in the approved Table 3 |

### B2. Operational choices: disclose in Section 4.1.3 with a reason and the effect
| # | Plan | What was done | Reason and effect |
|---|---|---|---|
| 1 | ESP32 peak RAM by `uxTaskGetStackHighWaterMark()` | **Static RAM** of the technology (updater image minus the Wi-Fi-only control) in Table 2, and the heap high-water mark from the device's `[MEM]` markers | A stack mark measures only the stack. Static RAM is the part that transfers to a Class 2 device, and heap covers dynamic use. Effect: the Table 2 RAM column is a build property (SD 0). |
| 2 | Pretest-posttest on the same hardware | A and B **interleaved** per round in random order (seeded), 3 warm-up rounds, paired by trial | Slow drift of the Wi-Fi channel hits both alike. |
| 3 | 60 trials per scenario | **60 complete pairs** analysed; 69 attempts per scenario | 9 counted cycles failed and a failed cycle has no completion time; trials were added (same seed) until 60 pairs were complete. The failed cycles are reported. |
| 4 | Gateway on a Raspberry Pi | Scenarios A and B: the **development PC** as gateway; Table 3: a Raspberry Pi 4 **capped to Pi 3B+ specifications** | The device-side and wire-side metrics do not depend on the gateway computer; the gateway cost (Table 3) was measured on the capped Pi. |
| 5 | OSCORE (RFC 8613) | **OSCORE-style** AEAD framing (pre-shared key, AES-CCM per block) | State the differences (no key derivation, no sequence numbers or replay window, no binding of release and block position into the authenticated data). |
| 6 | "Reconstruction throughput" first byte to reboot | Flash write throughput (bytes over time in `esp_ota_begin` + `esp_ota_write`); decryption + reconstruction = AES-CCM time + decoder time, from `[Metrics2]` | State the definitions (they are under Table 2 in `02-interpretation/tables/table-2_*.md`, `table-3_*.md`). |
| 7 | Update integrity rate | Success of updates: 93.5% (129 of 138 attempts); all 9 failures were detected by the device and none installed an image | Report with its interval (Wilson 88.1% to 96.5%). |

### B3. Not done: limitations and future work (do not hide, do not apologise)
| Plan | Status | How to handle |
|---|---|---|
| Naked CoAP and standard HTTPS baselines | **Measured** (supplementary, `03-writing/07_baselines-results.md`) | H (HTTPS full binary) for Eq. 3 and 4 and N (naked CoAP delta) for the Absolute Difference, on the same board; the approved tables are unchanged. See `03-writing/06_baselines-spec.md`. Caveats: H is a lower bound (no certificate validation) and unpaired with A; the TLS/DTLS handshake on the device is still host-measured. |
| Energy in mA | Not measured | Limitation; say less radio-on time is expected from 86% fewer bytes, but give no energy figure |
| TLS/DTLS comparison on the device | Host and specification values only | Label it modelled/literature |

If a panel member insists on a naked-CoAP number, a supplementary run is possible (about 60 cycles, roughly 2.5 hours) and would go to the supplementary data, not into the approved tables. Keep it as a contingency.

