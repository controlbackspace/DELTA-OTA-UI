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
