"""The approved experiment-paper tables (Tables 1 to 4), rendered from recorded data.

The column headings, row labels and cell markers below are copied from the approved
"EXPERIMENT PAPER" appendix of the thesis and must not be edited. Only the cells are filled,
and only from recorded data: nothing here is typed by hand.

  Table 1  Static Analysis of Volumetric Payload Optimization and Compression Ratio   (Instrument 1)
  Table 4  Deterministic Security Logic Validation and Success-Run Theorem Results     (Instrument 4)

  Table 2  Continuous Metrics for Hardware and Network Performance                     (Instrument 2)
  Table 3  Edge Gateway Computational Overhead and Security Tax Profiling              (Instrument 3)
"""
from __future__ import annotations

from . import campaign
from .campaign import truthy
from .inference import mean, sample_sd, success_run_confidence

RELIABILITY = 0.95
APPROVED_CYCLES = 60


def _md(columns: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


# ------------------------------------------------------------------ Table 1
TABLE1_TITLE = "Table 1. Static Analysis of Volumetric Payload Optimization and Compression Ratio"
TABLE1_COLUMNS = ["Metric ID", "Firmware Full Binary Version Pair Size (Bytes)", "Delta Patch Size (Bytes)",
                  "Total Bytes Saved", "Compression Ratio (%)"]


def table1(full_binary_bytes: int, delta_patch_bytes: int, pair: str = "v1.0 to v1.1") -> str:
    """One static benchmark per version pair: the raw new binary against the bsdiff4 patch."""
    if full_binary_bytes <= 0:
        raise ValueError("the full binary size must be positive")
    saved = full_binary_bytes - delta_patch_bytes
    ratio = saved / full_binary_bytes * 100.0
    row = ["VOL_01", f"{pair}: {full_binary_bytes:,}", f"{delta_patch_bytes:,}", f"{saved:,}", f"{ratio:.2f}"]
    return f"**{TABLE1_TITLE}**\n\n" + _md(TABLE1_COLUMNS, [row])


# ------------------------------------------------------------------ Table 4
TABLE4_TITLE = "Table 4. Deterministic Security Logic Validation and Success-Run Theorem Results"
TABLE4_COLUMNS = ["Cycle #", "Scenario C: Tampered Patch (Rejected: Y/N)", "Scenario D: Kill-Switch Revocation (Blocked: Y/N)",
                  "Scenario E: Incomplete Signature (Reverted: Y/N)", "Success-Run Status"]


def _outcomes(rows: list[dict], scenario: str) -> dict[int, str]:
    """cycle -> 'Pass' | 'Fail' from the analysed trials (a harness-invalid trial is not an outcome)."""
    out: dict[int, str] = {}
    for r in rows:
        if r["scenario"] == scenario and not truthy(r["warmup"]) and r["status"] in ("ok", "failed"):
            out[int(r["trial"])] = "Pass" if (r["status"] == "ok" and truthy(r.get("rejected"))) else "Fail"
    return out


def table4(rows: list[dict], cycles: int = APPROVED_CYCLES) -> str:
    """Pass/Fail per cycle for C, D and E, the failure totals, and the Success-Run result.

    The confidence statement is made only when every scenario has all `cycles` outcomes and zero
    failures; otherwise the table says what is missing instead.
    """
    outcomes = {s: _outcomes(rows, s) for s in "CDE"}
    body, failures_so_far = [], 0
    for c in range(1, cycles + 1):
        cells = [outcomes[s].get(c, "-") for s in "CDE"]
        failures_so_far += sum(1 for x in cells if x == "Fail")
        status = "Valid" if failures_so_far == 0 and all(x != "-" for x in cells) else ("Not valid" if failures_so_far else "Pending")
        body.append([str(c), *cells, status])
    totals = {s: sum(1 for v in outcomes[s].values() if v == "Fail") for s in "CDE"}
    complete = all(len(outcomes[s]) == cycles for s in "CDE")
    if complete and not any(totals.values()):
        verdict = f"{success_run_confidence(RELIABILITY, cycles) * 100:.1f}% Confidence Achieved"
    elif complete:
        verdict = "Confidence not achieved (failures recorded)"
    else:
        verdict = "Incomplete: " + ", ".join(f"{s} {len(outcomes[s])}/{cycles}" for s in "CDE")
    body.append(["RESULT", f"Total Failures {totals['C']}", f"Total Failures {totals['D']}", f"Total Failures {totals['E']}", verdict])
    return f"**{TABLE4_TITLE}**\n\n" + _md(TABLE4_COLUMNS, body)


# ------------------------------------------------------------------ Table 2
TABLE2_TITLE = "Table 2. Continuous Metrics for Hardware and Network Performance"
TABLE2_COLUMNS = ["Cycle #", "Scenario Type", "Wireshark TTC (ms)", "ESP32 Peak Ram Allocation (KB)",
                  "Decryption + Reconstruction Time (ms)", "Total Flash Write Throughput (KB/s)"]
TABLE2_SCENARIOS = (("A", "A (Delta-OTA)"), ("B", "B (Full-Binary)"))
NOTE_B_NA = ("Scenario B's Decryption + Reconstruction cells stay N/A as approved; in this testbed Scenario B also passes the same "
             "decrypt path, and its measured values are kept in the raw data.")


def _fmt(v, digits: int) -> str:
    return "-" if v is None else f"{v:.{digits}f}"


def _stats(vals: list[float], digits: int) -> tuple[str, str]:
    if not vals:
        return "-", "-"
    return f"{mean(vals):.{digits}f}", (f"{sample_sd(vals):.{digits}f}" if len(vals) > 1 else "-")


def table2(rows: list[dict], cycles: int = APPROVED_CYCLES) -> str:
    """Scenario A and B rows per cycle (device and capture cells), then Arithmetic Mean and Standard Deviation per scenario."""
    metrics = (("ttc_ms", 1), ("static_ram_kb", 2), ("decrypt_recon_ms", 1), ("flash_kbps", 1))
    vals = {sc: {m: campaign.values(rows, sc, m) for m, _ in metrics} for sc, _ in TABLE2_SCENARIOS}
    body = []
    for c in range(1, cycles + 1):
        for sc, label in TABLE2_SCENARIOS:
            cells = [_fmt(vals[sc]["ttc_ms"].get(c), 1), _fmt(vals[sc]["static_ram_kb"].get(c), 2),
                     "N/A" if sc == "B" else _fmt(vals[sc]["decrypt_recon_ms"].get(c), 1),
                     _fmt(vals[sc]["flash_kbps"].get(c), 1)]
            body.append([str(c), label, *cells])
    for stat, idx in (("Arithmetic Mean", 0), ("Standard Deviation", 1)):
        for sc, label in TABLE2_SCENARIOS:
            cells = []
            for m, d in metrics:
                if sc == "B" and m == "decrypt_recon_ms":
                    cells.append("N/A")
                else:
                    cells.append(_stats(list(vals[sc][m].values()), d)[idx])
            body.append(["STAT", f"{stat} ({label})", *cells])
    done = {sc: len(vals[sc]["ttc_ms"]) for sc, _ in TABLE2_SCENARIOS}
    note = "" if all(n == cycles for n in done.values()) else \
        "\n\n*Incomplete: " + ", ".join(f"{sc} {done[sc]}/{cycles} cycles" for sc, _ in TABLE2_SCENARIOS) + ".*"
    return f"**{TABLE2_TITLE}**\n\n" + _md(TABLE2_COLUMNS, body) + note + f"\n\n*{NOTE_B_NA}*"


# ------------------------------------------------------------------ Table 3
TABLE3_TITLE = "Table 3. Edge Gateway Computational Overhead and Security Tax Profiling"
TABLE3_COLUMNS = ["Cycle #", "Web3 Smart Contract Polling (ms)", "Local SHA-256 Hash Execution (ms)",
                  "OSCORE AES-CCM Encapsulation (ms)", "Peak Gateway RAM Utilized (MB)", "Peak Gateway CPU Load (%)"]


def table3(rows: list[dict], cycles: int = APPROVED_CYCLES) -> str:
    """One row per gateway profiling cycle, then the Average row."""
    metrics = (("poll_ms", 2), ("sha_ms", 3), ("encap_ms", 2), ("gw_ram_mb", 1), ("gw_cpu_pct", 1))
    vals = {m: campaign.values(rows, "T3", m) for m, _ in metrics}
    body = [[str(c), *[_fmt(vals[m].get(c), d) for m, d in metrics]] for c in range(1, cycles + 1)]
    body.append(["STAT: Average", *[_stats(list(vals[m].values()), d)[0] for m, d in metrics]])
    done = len(vals["poll_ms"])
    note = "" if done == cycles else f"\n\n*Incomplete: {done}/{cycles} cycles.*"
    return f"**{TABLE3_TITLE}**\n\n" + _md(TABLE3_COLUMNS, body) + note


# ------------------------------------------------------------------ Supplementary Table S2 (NOT one of the approved tables)
TABLE2S_TITLE = "Supplementary Table S2. Continuous Metrics for the Chapter 3 Comparators (not an approved instrument)"
TABLE2S_COLUMNS = ["Cycle #", "Scenario Type", "Wireshark TTC (ms)", "ESP32 Peak Ram Allocation (KB, static)",
                   "Decryption + Reconstruction Time (ms)", "Total Flash Write Throughput (KB/s)", "Bytes on the wire", "Peak heap (B)"]
TABLE2S_NOTE = ("Supplementary: the approved Tables 1 to 4 are unchanged. A is re-measured in the same rounds as N (paired); N is the naked-CoAP delta "
                "(Chapter 3 Baseline B); H is the full binary over HTTPS (Chapter 3 Baseline A), 60 downloads in one boot. For H the "
                "Decryption + Reconstruction cell is the receive-and-decrypt time (download time minus flash time), and the peak heap is one value for the series "
                "(the highest of the 60 downloads), shown in the footer row.")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def table2s(an_pairs: list[dict], h_rows: list[dict], h_heap_peak: int | None = None, cycles: int = APPROVED_CYCLES) -> str:
    """Rows A and N per matched pair, rows H per counted download, then the mean and SD of each, from recorded data only.

    `an_pairs` = [{"pair": i, "A": row, "N": row}, ...] (chapter4.select_pairs with scenarios ("A", "N")); `h_rows` = the counted ok rows of https_runs.csv.
    """
    def a_cells(r):
        return [r.get("ttc_ms"), r.get("static_ram_kb"), r.get("decrypt_recon_ms"), r.get("flash_kbps"), r.get("wire_bytes"), r.get("heap_peak_used")]

    def h_cells(r):
        recv = None
        if _num(r.get("download_ms")) is not None and _num(r.get("flash_us")) is not None:
            recv = _num(r["download_ms"]) - _num(r["flash_us"]) / 1000.0
        return [r.get("ttc_ms"), r.get("static_ram_kb"), recv, r.get("flash_kbps"), r.get("wire_bytes"), None]

    digits = (1, 2, 1, 1, 0, 0)
    fmt = lambda cells: [_fmt(_num(c), d) for c, d in zip(cells, digits)]
    groups = {"A": [a_cells(p["A"]) for p in an_pairs[:cycles]], "N": [a_cells(p["N"]) for p in an_pairs[:cycles]],
              "H": [h_cells(r) for r in h_rows[:cycles]]}
    labels = {"A": "A (Delta-OTA, paired with N)", "N": "N (Naked CoAP delta)", "H": "H (HTTPS full binary)"}
    body = []
    for i in range(cycles):
        for sc in ("A", "N"):
            body.append([str(i + 1), labels[sc], *(fmt(groups[sc][i]) if i < len(groups[sc]) else ["-"] * 6)])
    for i in range(cycles):
        body.append([str(i + 1), labels["H"], *(fmt(groups["H"][i]) if i < len(groups["H"]) else ["-"] * 6)])
    for stat, idx in (("Arithmetic Mean", 0), ("Standard Deviation", 1)):
        for sc in ("A", "N", "H"):
            cells = []
            for k, d in enumerate(digits):
                vals = [v for v in (_num(c[k]) for c in groups[sc]) if v is not None]
                cells.append(_stats(vals, d)[idx] if vals else "-")
            body.append(["STAT", f"{stat} ({labels[sc]})", *cells])
    if h_heap_peak is not None:
        body.append(["FOOTER", "H peak heap, highest of the downloads", "-", "-", "-", "-", "-", f"{h_heap_peak:,}"])
    done = {sc: len(groups[sc]) for sc in groups}
    nl = chr(10)
    note = "" if all(n == cycles for n in done.values()) else nl * 2 + "*Incomplete: " + ", ".join(f"{sc} {done[sc]}/{cycles}" for sc in groups) + ".*"
    return f"**{TABLE2S_TITLE}**" + nl * 2 + _md(TABLE2S_COLUMNS, body) + note + nl * 2 + f"*{TABLE2S_NOTE}*"
