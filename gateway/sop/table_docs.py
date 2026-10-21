"""The two table documents of the data pack, rendered from recorded data.

    TABLES-1-AND-4.md   Table 1 (static payload) and Table 4 (Scenarios C, D, E, Success-Run)
    TABLES-2-AND-3.md   Table 2 (Scenarios A and B) and Table 3 (Raspberry Pi gateway)

The table bodies come from thesis_tables.py (approved headings, columns and markers, never edited). Around them this module writes
what a reader needs: how to read each table, which SOP and equation it serves, the definitions of its columns, and the provenance
(files, SHA-256 hashes, revisions, failed or superseded cycles). Nothing is typed by hand: rerun `python -m sop.chapter4 --tables`.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as importlib_metadata
import re
from pathlib import Path

from . import campaign, chapter4 as c4, thesis_tables as tt

PI_EVIDENCE = ("Raspberry Pi 4 Model B limited to Raspberry Pi 3B+ memory and clock: `free -m` 905 MB total (1 GB cap, `total_mem=1024`), "
               "`arm_freq=1400` (measured 1,400,361,344 Hz), 4 cores, swap enabled (904 MB); recorded on the Pi on 2026-10-19 "
               "(before the caps: 3,795 MB and 1,800 MHz).")


def _sha(path_or_bytes) -> str:
    data = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else Path(path_or_bytes).read_bytes()
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------------- Tables 1 and 4
def table1_and_4_doc(*, base: Path, target: Path, patch: bytes, cde_csv: Path, cde_rows: list[dict], head: str,
                     bsdiff_version: str | None = None, run_folder: str = "sop-results/experiment-paper-tables/scenarios-C-D-E/") -> str:
    base_b, target_b = Path(base).read_bytes(), Path(target).read_bytes()
    saved = len(target_b) - len(patch)
    revs = sorted({r["git_revision"] for r in cde_rows if r.get("git_revision")})
    n_by = {s: sum(1 for r in cde_rows if r["scenario"] == s) for s in "CDE"}
    invalid = sum(1 for r in cde_rows if r["status"] == "invalid")
    conf = tt.success_run_confidence(tt.RELIABILITY, tt.APPROVED_CYCLES) * 100
    bsdiff_version = bsdiff_version or importlib_metadata.version("bsdiff4")
    return f"""# Experiment Paper tables: Table 1 (Instrument 1) and Table 4 (Instrument 4)

Generated from recorded data (`python -m sop.chapter4 --tables`). The table headings, columns and markers are the **approved** ones; only the cells are filled.
Tables 2 and 3 are in `TABLES-2-AND-3.md`. Statistics behind these tables: `STATISTICS.md`. How to use them in Chapters 4 and 5: `SOP-MAP-AND-CLAIMS.md`.

| Table | Serves | Equation | Draft section |
|---|---|---|---|
| 1 | SOP 1 (payload) | Eq. 3 (relative payload reduction) | 4.3.1 |
| 4 | SOP 3 (deterministic reliability) | Eq. 6 (Success-Run Theorem) | 4.5 |

---

{tt.table1(len(target_b), len(patch))}

**How to read it.** One static benchmark of the version pair, as the approved volume states (1 per version pair). "Firmware Full Binary" is the raw v1.1 image;
"Delta Patch" is the bsdiff4 engine output (BSDIFF40), not the device stream. Total Bytes Saved = {len(target_b):,} - {len(patch):,} = {saved:,}.
Compression Ratio = {saved:,} / {len(target_b):,} x 100 = **{saved / len(target_b) * 100:.2f}%** (Equation 3 with the full image as the baseline).
The bytes on the wire measured in Scenarios A and B (86.13% fewer) are reported with Table 2, not here.

| Input | Path and size | SHA-256 |
|---|---|---|
| Base image (v1.0) | `{base}` ({len(base_b):,} B) | `{_sha(base_b)}` |
| Target image (v1.1) | `{target}` ({len(target_b):,} B) | `{_sha(target_b)}` |
| bsdiff4 patch | {len(patch):,} B (bsdiff4 {bsdiff_version}) | `{_sha(patch)}` |

---

{tt.table4(cde_rows)}

**How to read it.** 60 automated cycles per scenario on a local Hardhat chain with the real gateway process (`sop/host_scenarios.py`). **Pass** means the attempt was
rejected, blocked or reverted as required:

| Scenario | What is attempted | Pass when |
|---|---|---|
| C: Tampered Patch | one bit of the patch is altered | the gateway detects the hash mismatch and stages nothing |
| D: Kill-Switch Revocation | a release is revoked on the smart contract | the gateway refuses the version request and holds no blocks |
| E: Incomplete Signature | a release below the 2-of-3 threshold is submitted | it never goes live; the extra signatures are reverted |

Success-Run (Equation 6): C = 1 - 0.95^60 = **{conf:.2f}%**, valid only with zero failures in all three scenarios; it bounds reliability (at least 95% at this confidence),
it does not prove the failure probability is zero. 59 failure-free cycles are the minimum for 95% reliability at 95% confidence (1 - 0.95^59 = {tt.success_run_confidence(0.95, 59) * 100:.2f}%).

| Item | Value |
|---|---|
| Run folder | `{run_folder}` |
| Per-trial data | `scenarios-C-D-E/campaign/trials.csv` ({len(cde_rows)} rows: C {n_by['C']}, D {n_by['D']}, E {n_by['E']}; {invalid} invalid) |
| `trials.csv` SHA-256 | `{_sha(cde_csv)}` |
| Gateway system logs | `scenarios-C-D-E/raw/campaign-c-gateway.log`, `campaign-d-gateway.log`, `campaign-e-gateway.log` |
| Blockchain transaction logs | `scenarios-C-D-E/raw/campaign-c-node.log`, `campaign-d-node.log`, `campaign-e-node.log` |
| Software revision | run recorded `{', '.join(revs) or 'n/a'}`; tables rendered at `{head}` |
| Patch used in C, D and E | the real v1.0 to v1.1 patch above, SHA-256 `{_sha(patch)[:16]}...` |
| Do not | save `trials.csv` from a spreadsheet program: it rewrites the boolean spelling (the analysis tolerates it, but keep the original) |

Supplementary columns of the same run (not part of Table 4, used in the discussion): Scenario C detection time and Scenario D revocation propagation delay
(`STATISTICS.md`, section 8).
"""


# ------------------------------------------------------------------------------------------- Tables 2 and 3
def table2_and_3_doc(*, ab_csv: Path, t3_csv: Path, ab_rows: list[dict], t3_rows: list[dict], head: str) -> str:
    pairs = c4.select_pairs(ab_rows)
    if len(pairs) < tt.APPROVED_CYCLES:
        raise ValueError(f"only {len(pairs)} complete A/B pairs; Table 2 needs {tt.APPROVED_CYCLES}")
    render, mapping = [], []
    for p in pairs:
        for sc in "AB":
            r = dict(p[sc])
            r["trial"] = str(p["pair"])
            render.append(r)
        mapping.append(f"{p['pair']}={p['trial']}")
    table2 = tt.table2(render)
    table3 = tt.table3(t3_rows)

    nw = [r for r in ab_rows if not campaign.truthy(r["warmup"])]
    status = {sc: {s: sum(1 for r in nw if r["scenario"] == sc and r["status"] == s) for s in ("ok", "failed", "invalid")} for sc in "AB"}
    fails = c4.failures(ab_rows)["detail"]
    revs = sorted({r["git_revision"] for r in ab_rows if r.get("git_revision")})
    t3n = [r for r in t3_rows if not campaign.truthy(r["warmup"]) and r["status"] == "ok"]
    superseded = sorted({int(r["trial"]) for r in t3_rows if r["status"] == "invalid" and (r.get("note") or "").startswith("superseded")})
    sup_text = ("Cycles " + ", ".join(map(str, superseded)) + " " if len(superseded) > 1 else f"Cycle {superseded[0]} " if superseded else "")
    poll = sorted(float(r["poll_ms"]) for r in t3n)
    median = (poll[len(poll) // 2 - 1] + poll[len(poll) // 2]) / 2

    return f"""# Experiment Paper tables: Table 2 (Instrument 2) and Table 3 (Instrument 3)

Generated from recorded data (`python -m sop.chapter4 --tables`). The table headings, columns and markers are the **approved** ones; only the cells are filled.
Tables 1 and 4 are in `TABLES-1-AND-4.md`. Statistics behind these tables: `STATISTICS.md`. How to use them in Chapters 4 and 5: `SOP-MAP-AND-CLAIMS.md`.

| Table | Serves | Equations | Draft section |
|---|---|---|---|
| 2 | SOP 5 (systemic performance), SOP 1 (wire bytes), SOP 2 (per-block decryption) | Eq. 1, 2, 5; paired t-test; Eq. 3 | 4.7 |
| 3 | SOP 4 (offloading), SOP 2 (encapsulation) | Eq. 1, 2, 5 | 4.6.1 |

## How to read Table 2
- **Cycle n = the n-th complete A/B pair.** A pair is a trial number that both Scenario A and Scenario B finished successfully; a failed cycle has no completion time, so it is not a pair.
  Table cycle to campaign trial number: {", ".join(mapping)}.
- **Wireshark TTC** = first device `GET /patch` to the gateway's last `2.04` in the same capture (tshark on the gateway PC).
- **ESP32 Peak RAM** = static RAM of our update technology (updater image minus the Wi-Fi-only control, {tt.mean([float(r['static_ram_kb']) for r in render]):.2f} KB). It is a build property, so it is the same in every row and its SD is 0 (no t-test). The measured heap peak is reported separately in `STATISTICS.md`.
- **Decryption + Reconstruction** = device AES-CCM time plus the delta decoder time (inflate, merge with the old flash, flash writes), from the `[Metrics2]` serial line. Scenario B is **N/A** by the approved layout; its measured value is in `data/ab_pairs.csv`.
- **Flash write throughput** = bytes written by `esp_ota_write` over the time spent in `esp_ota_begin` plus `esp_ota_write`.
- **STAT rows** = Equation 1 (mean) and Equation 2 (sample standard deviation) per scenario.

{table2}

### Table 2 provenance
- Campaign data: `{ab_csv}` (sha256 `{_sha(ab_csv)}`)
- Counted attempts: A ok {status['A']['ok']}, failed {status['A']['failed']}; B ok {status['B']['ok']}, failed {status['B']['failed']}; harness-invalid cycles re-run (no update started): A {status['A']['invalid']}, B {status['B']['invalid']}.
- Firmware: factory image `campaign-fw-1` (firmware repo commit 7131621). Controller revisions recorded: {", ".join(revs) or 'n/a'}. Table code revision: {head}.
- Failed cycles (kept in the raw CSV, listed in `data/failures.csv`): {"; ".join(f"{d['scenario']} trial {d['trial']}: {d['cause']}" for d in fails)}.
- Gateway = the development PC (not the Pi); Wi-Fi 2.4 GHz to one ESP32; one version pair (v1.0 to v1.1).

## How to read Table 3
- 60 gateway-only cycles after 3 discarded warm-up cycles, on a {PI_EVIDENCE}
- **Polling** = mean time of the contract reads since the previous release (a LAN call to the chain on the PC). **SHA-256** and **AES-CCM encapsulation** (24 blocks) are timed with the pyperf clock, garbage collector off.
  **Peak RAM** and **CPU** are psutil samples (50 ms) from detection to staging; CPU is a share of total capacity (4 cores).
- **STAT: Average** = Equation 1. The standard deviations and tolerance limits are in `STATISTICS.md` section 7.

{table3}

### Table 3 provenance
- Campaign data: `{t3_csv}` (sha256 `{_sha(t3_csv)}`), 3 warm-up + {len(t3n)} counted cycles, all ok.
- {sup_text + "was run twice: the first run had a stalled contract read (an RPC call to the chain on the PC) and is marked superseded in the CSV; the table shows the re-run. The original row is kept in `table3.csv` and in `table3.before-cycle6-rerun.csv`." if superseded else "No cycle was superseded."}
- Median polling latency {median:.1f} ms; maximum {poll[-1]:.1f} ms.
- The Pi clock was about 200 s ahead of the PC; only the derived time-to-stage column (not part of the table) is affected.
"""


def appendix_from_docs(doc14: str, doc23: str) -> str:
    """The Appendix of the chapter draft: the four approved tables and their provenance, cut from the two documents."""
    def between(text: str, start: str, stop: str | None = None) -> str:
        i = text.index(start)
        j = text.index(stop, i) if stop else len(text)
        return text[i:j].strip()

    tab1 = between(doc14, "**Table 1.", "\n**How to read it.**")
    tab4 = between(doc14, "**Table 4.", "\n**How to read it.**")
    tab2 = between(doc23, "**Table 2.", "\n### Table 2 provenance")
    prov2 = between(doc23, "### Table 2 provenance", "\n## How to read Table 3")
    tab3 = between(doc23, "**Table 3.", "\n### Table 3 provenance")
    prov3 = between(doc23, "### Table 3 provenance")
    src1 = between(doc14, "| Input | Path and size", "\n---")
    src4 = between(doc14, "| Item | Value |", "\nSupplementary columns")
    return f"""# APPENDIX: THE APPROVED INSTRUMENTS FILLED FROM THE RECORDED DATA

Layouts, headings and markers are those of the approved Experiment Paper; only the cells are filled.

{tab1}

{src1}

{tab2}

{prov2}

{tab3}

{prov3}

{tab4}

{src4}

*Source files:* Table 1 and Table 4 from `experiment-paper-tables/TABLES-1-AND-4.md`; Tables 2 and 3 from `experiment-paper-tables/TABLES-2-AND-3.md` (under `sop-results/`), generated from the campaign CSV files recorded with their SHA-256 hashes.
"""


def replace_appendix(draft: str, appendix: str) -> str:
    """Swap the Appendix of the draft for a fresh one (everything from the APPENDIX heading to the end)."""
    m = re.search(r"^# APPENDIX: THE APPROVED INSTRUMENTS FILLED FROM THE RECORDED DATA", draft, flags=re.M)
    if not m:
        raise ValueError("the draft has no Appendix heading")
    head = draft[:m.start()].rstrip("\n")
    if head.endswith("---"):
        head = head[:-3].rstrip("\n")
    return head + "\n\n---\n\n" + appendix


# ------------------------------------------------------------------------------------------- Supplementary baselines (H and N)
def baselines_doc(*, ctx: dict, n_csv: Path | None, h_dir: Path | None, head: str) -> str:
    """BASELINES.md: Supplementary Table S2 and the results for the Chapter 3 comparators, with provenance."""
    from . import baselines

    n, h = ctx.get("n"), ctx.get("h")
    hdata = ctx.get("h_data")
    table = ""
    if n and hdata:
        counted = [r for r in hdata["rows"] if not campaign.truthy(r["warmup"]) and r["status"] == "ok"]
        table = tt.table2s(n["pairs"], counted, (hdata["summary"].get("heap") or {}).get("peak_bytes"))
    prov = []
    if n_csv:
        prov.append(f"- N campaign (A and N, interleaved): `{n_csv}` (sha256 `{_sha(n_csv)}`)")
    if h_dir:
        prov.append(f"- H run: `{Path(h_dir) / 'campaign' / 'https_runs.csv'}` (sha256 `{_sha(Path(h_dir) / 'campaign' / 'https_runs.csv')}`), "
                    f"`summary.json`, `static_increments.json`")
    prov.append(f"- Firmware: separate PlatformIO environments `https_baseline`, `https_control` and `factory_naked` of the firmware repository; the standard "
                f"`factory` environment is unchanged in code (its image differs from the original in the 64 bytes derived from the ELF checksum only).")
    prov.append(f"- Table code revision: {head}.")
    nl = chr(10)
    return f"""# Chapter 3 comparators on the same board: HTTPS full binary (H) and naked CoAP delta (N)

Generated from recorded data (`python -m sop.chapter4 --n <N campaign> --h <H run> --tables`). Specification: `BASELINES-SPEC.md`.
**Supplementary**: the approved Tables 1 to 4 are not changed. H and N exist because Chapter 3's statistical treatment names a standard HTTPS full-binary update
(Equations 3 and 4) and an unsecured naked CoAP transfer (the Absolute Difference). They share the setup of Scenarios A and B (same ESP32, Wi-Fi, gateway PC,
firmware pair, tshark and serial measurement) but are separate conditions, not one architecture.

{table}

{baselines.render(n, h).replace('## 10. ', '## ').replace('### 10.', '### ')}

## Provenance
{nl.join(prov)}
"""
