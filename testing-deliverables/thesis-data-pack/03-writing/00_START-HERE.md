# Start here: writing Chapters 4 and 5 from this data pack

Everything here comes from recorded data. The four tables are the approved Experiment Paper tables (layout, headings and markers unchanged; only the cells are filled). Chapter 3 is not edited.

## 1. The three folders

| Folder | What it holds | Open first |
|---|---|---|
| `01-raw-data/` | `RUNS-INDEX.csv` (what every run is, which table it feeds, which harness and firmware), `tidy-csv/` (the CSVs behind every table), the original run folders (`runs/`, `pilots/`, `discarded/`) with serial logs and packet captures (local only) | `tidy-csv/` |
| `02-interpretation/` | `tables/`: one markdown file per table (`table-1` to `table-4`, `table-s2`, `sop4-static-footprint`); `02-interpretation/figures/`: seven PNG figures | `tables/table-2_hardware-network.md` |
| `03-writing/` | The files you write the chapters from (below) | this file |

The chapter draft `CHAPTERS-4-AND-5-DRAFT.md` is in the root of `sop-results/` (local, not pushed); the other group members' drafts can use it as a worked example.

## Reading order for `03-writing/`

| File | Use it for |
|---|---|
| `00_START-HERE.md` | this page: map, headline results, pitfalls |
| `01_statistical-analysis.md` | every test with its formula and inputs (generated): paired t-tests, tolerance limits, root cause, failures, sensitivity, SOP 4, baselines, confirmation run |
| `02_claims.md` | what can and cannot be claimed, per SOP, and a checklist |
| `03_limitations.md` | limitations and threats to validity, and what is still open |
| `04_scope-and-method.md` | scope, test bed, column definitions, and how each difference from Chapter 3 is presented |
| `05_sop-evidence-map.md` | SOP by SOP: instrument, formula, result, where it sits in the draft |
| `06_baselines-spec.md`, `07_baselines-results.md` | the HTTPS (H) and naked-CoAP (N) comparators: specification and results (results generated) |
| `08_failures-and-harness-race.md` | why cycles failed, and the harness race |
| `09_defense-qa.md` | likely panel questions with honest answers |
| `10_reproducibility.md` | how to regenerate everything, how to add a run, naming rules |
| `11_sop4-supporting-data.md` | the on-device Web3 client and the static footprint (SOP 4) |

## 2. The headline results

| Result | Value | Source |
|---|---|---|
| Table 1: delta patch against full image | 22,497 B against 288,880 B: **92.21%** smaller | `02-interpretation/tables/table-1_*.md`, `table-4_*.md` |
| Time to completion, delta (A) against full binary (B), 60 matched pairs | 5,571.1 ms against 37,051.8 ms: **84.96%** shorter; paired t = -29.49, p = 5.2e-37; A faster in 60 of 60 pairs | `03-writing/01_statistical-analysis.md` section 3 |
| Bytes on the wire | 27,499 against 198,211: **86.13%** fewer | section 3 |
| 99%/95% worst case (Eq. 5, K = 2.8071) | 9.0 s (A) against 60.5 s (B) | section 3 |
| Decryption + reconstruction | 1,753.9 ms (A); B is "N/A" in the approved Table 2 (raw: 1,845.1 ms) | Table 2 |
| Flash write throughput | 184.3 KB/s (A) and 195.9 KB/s (B): A is **5.9% lower** (significant, unfavourable) | section 3 |
| Static RAM of the technology | 28.73 KB, constant in every cycle (SD 0), 57.4% of 50 KiB | Table 2 |
| Table 3 (Raspberry Pi, 3B+ limits) | polling 54.13 ms, SHA-256 0.230 ms, AES-CCM 6.13 ms, 80.9 MB, 30.4% CPU | `02-interpretation/tables/table-2_*.md`, `table-3_*.md` |
| Table 4 | 60 of 60 in each of C, D, E; Success-Run C = 1 - 0.95^60 = **95.39%** | `02-interpretation/tables/table-1_*.md`, `table-4_*.md` |
| Update failures (counted A/B attempts) | 9 of 138 (6.5%): **6 were interrupted by a race in the old harness**, 3 (B) unexplained; **0 of 182 cleanly started delta cycles failed**; confirmation run: 0 failures in 40 | `03-writing/01_statistical-analysis.md` section 5 |
| SOP 4, on the board | one on-device ledger check 1,414 ms, 52,000 B heap; offloading cuts peak RAM by 58% and flash by 78.5% | `11_sop4-supporting-data.md` |
| Against the HTTPS full binary (H) | 91.05% fewer bytes (Eq. 3); peak RAM 71,668 B = 140% of 50 KiB for H against 35,534 B (69%) to 46,072 B (90%) for A: **50.4% to 35.7% less** (Eq. 4); flash 72.3% less; **but HTTPS is faster: 3,733 ms against 5,571 ms** | `03-writing/07_baselines-results.md` |
| Security tax against naked CoAP (N) | +42.7 ms of decryption + reconstruction (0.8% of the time); time to completion +179 ms, not significant (p = 0.20); +1.07 KB static RAM | `03-writing/07_baselines-results.md` |
| Confirmation run (fixed harness, 20 pairs) | time -84.65%, bytes -86.39%, decrypt+recon -5.44%, flash -5.19%; peak heap -10.6% (p = 0.12) | `03-writing/01_statistical-analysis.md` section 11 |


## 3. How the instruments map to the tables and scenarios

| Table | Instrument | Scenarios | Tools (as approved) | Volume |
|---|---|---|---|---|
| 1 | Volumetric payload (static) | none (one benchmark of the version pair) | bsdiff4 output, file sizes | 1 |
| 2 | Hardware and network telemetry | A (delta) and B (full binary, the internal control) | Wireshark/tshark (TTC), ESP32 serial metrics | 60 matched pairs |
| 3 | Edge gateway overhead and security tax | gateway-only cycles on the Raspberry Pi | pyperf timer, psutil | 60 cycles (+3 warm-up) |
| 4 | Deterministic security validation | C (tampered patch), D (kill switch), E (incomplete signatures) | gateway logs, chain transaction logs | 60 per scenario |


## 4. Things that are easy to get wrong

1. **Cycle n of Table 2 is the n-th complete A/B pair, not trial n.** A trial counts as a pair only when both A and B finished it. Nine counted cycles failed, so trials 61 to 69 were added until 60 pairs existed. `03-writing/01_statistical-analysis.md` section 2 lists the pair-to-trial mapping.
2. **B's "Decryption + Reconstruction Time" is N/A in Table 2** (approved layout). The measured B value (1,845.1 ms) is in `01-raw-data/tidy-csv/table2_ab-pairs.csv` and is used only to explain the A/B comparison.
3. **ESP32 Peak RAM in Table 2 is the static RAM of our technology** (updater image minus the Wi-Fi-only control), a build property: the same in every row, SD = 0, no t-test. The measured heap peak is separate (`03-writing/01_statistical-analysis.md` section 3, "Peak heap used during the update"; 58 pairs, because one A and one B cycle lack the marker).
4. **Scenarios A and B used the development PC as the gateway; Table 3 used a Raspberry Pi 4 limited to Raspberry Pi 3B+ specifications** (905 MB visible, 1.4 GHz, 4 cores, swap present). Do not use PC gateway numbers as Table 3 values.
5. **Table 3 cycle 6 was measured twice.** The first run had a stalled contract read; the original row is kept in the raw CSV (`table3.before-cycle6-rerun.csv`) and the table shows the re-run (provenance note under Table 3).
6. **Delta is not better on every metric.** Flash write throughput is 5.9% lower, and the decoder spends 136 ms more per update (it reads the old image). Report both (see `03-writing/05_sop-evidence-map.md` and `02_claims.md`).
7. **The "OSCORE" framing is OSCORE-style** (pre-shared key, AES-CCM per 1 KiB block, 13 B nonce, 16 B tag), not RFC 8613. Replayed and reordered authentic blocks pass the per-block check and are caught only by the final image digest.
8. **Do not open the CSV files in Excel and save them.** Excel rewrites True/False as TRUE/FALSE and can reformat numbers. Open read-only or copy first; `01-raw-data/tidy-csv/MANIFEST.sha256` lets you check nothing changed.
9. **Never edit generated files by hand** (`03-writing/01_statistical-analysis.md`, `01-raw-data/tidy-csv/`, `02-interpretation/figures/`): rerun the command.
10. **Success-Run (Eq. 6) bounds reliability, it does not prove security.** 60 of 60 gives at least 95% reliability at 95.39% confidence.
11. **The old A/B failures are a harness artifact.** The harness reset the board while it had already begun updating by itself, interrupting the backup copy. Do not quote 6.5% as the architecture's failure rate; use the clean-start table (`03-writing/01_statistical-analysis.md` section 5) and the confirmation run.
12. **H and N are supplementary.** They are not in the approved Tables 1 to 4. H is a lower bound (no certificate validation) and is compared with A unpaired; N is paired with a fresh A in the same rounds. Say "fits / exceeds the Class 2 budget", never "runs / does not run".
13. **The peak-heap difference between A and B is not robust** (p = 0.158 on 58 pairs, 0.040 on 45, 0.122 in the confirmation run): report it as possible, not demonstrated.


## 5. File naming

| Kind | Pattern | Example |
|---|---|---|
| Run folder | `R<nn>_<topic>_<scenarios>_<yyyy-mm-dd>` (R = run, P = pilot, D = discarded) | `R03_table2_A-vs-B-main_2026-10-19` |
| Tidy CSV | `<table-or-topic>_<what>.csv` | `table2_ab-pairs.csv` |
| Table document | `table-<n>_<slug>.md` | `table-2_hardware-network.md` |
| Figure | `fig-<nn>_<slug>.png` | `fig-02_time-to-completion.png` |
| Writing file | `<nn>_<slug>.md` (reading order) | `02_claims.md` |

Dates appear only in run folder names. Old run names are listed in `01-raw-data/RENAMES.csv`.
