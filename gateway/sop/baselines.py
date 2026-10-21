"""Analysis of the two Chapter 3 comparators measured on the same board (see 03-writing/06_baselines-spec.md in the data pack).

  H  the full v1.1 image over HTTPS (Chapter 3 Baseline A): Equation 3 (payload) and Equation 4 (RAM) against the proposed architecture
  N  the same delta over naked CoAP, no AES-CCM (Chapter 3 Baseline B): the Absolute Difference ("security tax"), A minus N, paired

Inputs are the recorded runs: `https_hw` writes campaign/https_runs.csv, summary.json and static_increments.json; the N campaign is a normal
`device_cycle --scenarios A,N` run (campaign/trials.csv). Nothing is typed by hand; the supplementary table and the report text are rendered
from these functions. The approved Tables 1 to 4 are not touched.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import campaign, chapter4 as c4, inference as inf

H_COLUMNS = ("ttc_ms", "wire_bytes", "connect_ms", "download_ms", "device_ms", "flash_kbps")
N_METRICS = ("ttc_ms", "wire_bytes", "decrypt_recon_ms", "decrypt_avg_us", "reconstruct_us", "flash_kbps", "heap_peak_used", "static_ram_kb")
CLASS2_RAM_B, CLASS2_FLASH_B = 50 * 1024, 250 * 1024


def _col(rows: list[dict], key: str) -> list[float]:
    out = []
    for r in rows:
        try:
            out.append(float(r[key]))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def stats(values: list[float]) -> dict:
    u = inf.upper_tolerance_limit(values)
    return {"n": len(values), "mean": u["mean"], "sd": u["sd"], "utl": u["upper_limit"], "min": min(values), "max": max(values)}


# ------------------------------------------------------------------------------------------------ N: naked CoAP delta
def n_analysis(n_rows: list[dict], raw_dir: Path | None = None, wanted: int = 60) -> dict:
    """A against N, matched by trial: every Table 2 column, the paired test of A - N, and the effect of interrupted cycles."""
    pairs = c4.select_pairs(n_rows, wanted, ("A", "N"))
    if len(pairs) < 3:
        raise ValueError(f"only {len(pairs)} complete A/N pairs")
    flags = c4.interrupted_map(n_rows, raw_dir) if raw_dir else {}
    table = [r for r in c4.paired_table(pairs, "A", "N") if r["metric"] in N_METRICS]
    counted = [r for r in n_rows if not campaign.truthy(r["warmup"])]
    count = {sc: {s: sum(1 for r in counted if r["scenario"] == sc and r["status"] == s) for s in ("ok", "failed", "invalid")} for sc in "AN"}
    out = {"pairs": pairs, "table": table, "counts": count, "n_pairs": len(pairs), "complete": len(pairs) >= wanted,
           "by_start": c4.outcomes_by_start(n_rows, flags, "AN") if flags else None,
           "interrupt_sens": c4.interruption_sensitivity(pairs, flags, metrics=("ttc_ms", "wire_bytes", "decrypt_recon_ms"), first="A", second="N") if flags else None}
    # the wire-byte difference against the framing arithmetic: 29 bytes (13 nonce + 16 tag) per block
    blocks = [float(p["A"]["blocks"]) for p in pairs if p["A"].get("blocks") not in ("", None)]
    out["expected_wire_diff"] = 29.0 * inf.mean(blocks) if blocks else None
    return out


# ------------------------------------------------------------------------------------------------ H: HTTPS full binary
def load_h(h_run: Path) -> dict:
    h_run = Path(h_run)
    with open(h_run / "campaign" / "https_runs.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {"rows": rows, "summary": json.loads((h_run / "summary.json").read_text(encoding="utf-8")),
            "sizes": json.loads((h_run / "static_increments.json").read_text(encoding="utf-8"))}


def h_analysis(h: dict, a_pairs: list[dict]) -> dict:
    """H series statistics, and H against A (the Table 2 pairs of Scenario A): Equations 3 and 4, flash, and an unpaired test."""
    counted = [r for r in h["rows"] if not campaign.truthy(r["warmup"]) and r["status"] == "ok"]
    failed = [r for r in h["rows"] if not campaign.truthy(r["warmup"]) and r["status"] != "ok"]
    out = {"n_ok": len(counted), "n_failed": len(failed), "columns": {k: stats(_col(counted, k)) for k in H_COLUMNS if _col(counted, k)}}
    a = lambda m: c4.column(a_pairs, "A", m)
    a_wire, a_ttc = a("wire_bytes"), a("ttc_ms")
    h_wire, h_ttc = _col(counted, "wire_bytes"), _col(counted, "ttc_ms")
    out["eq3"] = {"h_mean": inf.mean(h_wire), "a_mean": inf.mean(a_wire), "reduction_pct": inf.relative_reduction_pct(inf.mean(h_wire), inf.mean(a_wire)),
                  "static_full": 288_880, "static_patch": 22_497,
                  "static_reduction_pct": inf.relative_reduction_pct(288_880, 22_497),
                  "welch": inf.welch_t(a_wire, h_wire)}
    out["ttc"] = {"h": stats(h_ttc), "a": stats(a_ttc), "reduction_pct_a_vs_h": inf.relative_reduction_pct(inf.mean(h_ttc), inf.mean(a_ttc)),
                  "welch": inf.welch_t(a_ttc, h_ttc)}
    sizes, heap = h["sizes"], h["summary"].get("heap") or {}
    a_heap = a("heap_peak_used")
    h_static, a_static = sizes["https_baseline"]["static_ram_increment_b"], sizes["factory"]["static_ram_increment_b"]
    h_heap = heap.get("peak_bytes")
    eq4 = {"h_static": h_static, "a_static": a_static, "h_heap_max": h_heap, "a_heap_mean": inf.mean(a_heap) if a_heap else None,
           "a_heap_max": max(a_heap) if a_heap else None, "a_heap_utl": inf.upper_tolerance_limit(a_heap)["upper_limit"] if len(a_heap) > 2 else None}
    if h_heap is not None and a_heap:
        h_total = h_static + h_heap
        for tag, a_h in (("mean", eq4["a_heap_mean"]), ("max", eq4["a_heap_max"])):
            a_total = a_static + a_h
            eq4[f"a_total_{tag}"] = a_total
            eq4[f"reduction_pct_{tag}"] = inf.relative_reduction_pct(h_total, a_total)
            eq4[f"a_budget_pct_{tag}"] = a_total / CLASS2_RAM_B * 100
        eq4.update({"h_total": h_total, "h_budget_pct": h_total / CLASS2_RAM_B * 100})
    out["eq4"] = eq4
    out["flash"] = {"h": sizes["https_baseline"]["flash_increment_b"], "a": sizes["factory"]["flash_increment_b"],
                    "n": sizes["factory_naked"]["flash_increment_b"],
                    "reduction_pct_a_vs_h": inf.relative_reduction_pct(sizes["https_baseline"]["flash_increment_b"], sizes["factory"]["flash_increment_b"])}
    out["static"] = {"h": h_static, "a": a_static, "n": sizes["factory_naked"]["static_ram_increment_b"]}
    out["capture_vs_device_ms"] = stats(_col(counted, "capture_minus_device_ms")) if _col(counted, "capture_minus_device_ms") else None
    return out


# ------------------------------------------------------------------------------------------------ rendering
def _f(v, d=2):
    return "-" if v is None else f"{v:,.{d}f}"


def render(n: dict | None, h: dict | None) -> str:
    L: list[str] = []
    w = L.append
    w("## 10. Chapter 3 comparators on the same board: HTTPS full binary (H) and naked CoAP delta (N)\n")
    w("Specification: `BASELINES-SPEC.md`. Both are supplementary: they are not part of the approved Tables 1 to 4.\n")
    if n:
        w("### 10.1 N: the security tax (Absolute Difference, A minus N, paired)\n")
        c = n["counts"]
        w(f"{n['n_pairs']} complete A/N pairs. Counted attempts: A ok {c['A']['ok']}, failed {c['A']['failed']}; N ok {c['N']['ok']}, failed {c['N']['failed']}; "
          f"harness faults re-run: A {c['A']['invalid']}, N {c['N']['invalid']}.\n")
        w("| Metric | A (secured) mean (SD) | N (naked) mean (SD) | A - N (95% CI) | t | p | dz |\n|---|---|---|---|---|---|---|")
        for r in n["table"]:
            d = r["digits"]
            if r["degenerate"]:
                w(f"| {r['label']} | {_f(r['mean_A'], d)} ({_f(r['sd_A'], d)}) | {_f(r['mean_N'], d)} ({_f(r['sd_N'], d)}) | {_f(r['mean_diff'], d)} (no variance) | - | - | - |")
            else:
                w(f"| {r['label']} | {_f(r['mean_A'], d)} ({_f(r['sd_A'], d)}) | {_f(r['mean_N'], d)} ({_f(r['sd_N'], d)}) | "
                  f"{_f(r['mean_diff'], d)} ({_f(r['ci_low'], d)} to {_f(r['ci_high'], d)}) | {_f(r['t'])} | {c4._p(r['p'])} | {_f(r['dz'])} |")
        if n.get("expected_wire_diff") is not None:
            w(f"\nFraming arithmetic: 29 B (13 B nonce + 16 B tag) x {n['expected_wire_diff'] / 29:.0f} blocks = {n['expected_wire_diff']:,.0f} B expected per update; "
              "the measured difference also contains the effect of repeated block requests.\n")
        if n.get("by_start"):
            w("| Scenario | Harness interrupted the update: ok / failed | Clean start: ok / failed |\n|---|---|---|")
            for sc in ("A", "N"):
                s = n["by_start"][sc]
                w(f"| {sc} | {s['interrupted']['ok']} / {s['interrupted']['failed']} | {s['clean']['ok']} / {s['clean']['failed']} |")
            w("")
        sens = n.get("interrupt_sens")
        if sens:
            w(f"Security tax on all {sens['n_all']} pairs and on the {sens['n_clean']} pairs in which neither cycle was interrupted by the old harness:" + chr(10))
            w("| Metric | A - N, all pairs (95% CI), p | A - N, clean pairs (95% CI), p |" + chr(10) + "|---|---|---|")
            for r in sens["rows"]:
                a_, c_ = r["all"], r["clean"]
                fa = f"{_f(a_['mean_diff'], 1)} ({_f(a_['ci_low'], 1)} to {_f(a_['ci_high'], 1)}), p = {c4._p(a_['p'])}" if a_.get("t") is not None else "-"
                fc = f"{_f(c_['mean_diff'], 1)} ({_f(c_['ci_low'], 1)} to {_f(c_['ci_high'], 1)}), p = {c4._p(c_['p'])}" if c_ and c_.get("t") is not None else "-"
                w(f"| {r['label']} | {fa} | {fc} |")
            w("")
    if h:
        w("### 10.2 H: HTTPS full binary (Equations 3 and 4)\n")
        w(f"{h['n_ok']} counted downloads ok, {h['n_failed']} failed (one boot, 3 warm-up discarded). H against A is **unpaired** (H is a single-boot series).\n")
        w("| H column | Mean | SD | UTL (Eq. 5) | Min | Max |\n|---|---|---|---|---|---|")
        labels = {"ttc_ms": "Time to completion (ms)", "wire_bytes": "Bytes on the wire", "connect_ms": "TCP + TLS connect (ms)",
                  "download_ms": "Download incl. flash (ms)", "device_ms": "Device total (ms)", "flash_kbps": "Flash write throughput (KB/s)"}
        for k, v in h["columns"].items():
            d = 0 if k == "wire_bytes" else 1
            w(f"| {labels[k]} | {_f(v['mean'], d)} | {_f(v['sd'], d)} | {_f(v['utl'], d)} | {_f(v['min'], d)} | {_f(v['max'], d)} |")
        e3, t = h["eq3"], h["ttc"]
        w(f"\n**Equation 3 (payload).** Static: ({e3['static_full']:,} - {e3['static_patch']:,}) / {e3['static_full']:,} = **{e3['static_reduction_pct']:.2f}%** (Table 1). "
          f"On the wire: H {e3['h_mean']:,.0f} B against A {e3['a_mean']:,.0f} B = **{e3['reduction_pct']:.2f}% fewer bytes** "
          f"(Welch t = {e3['welch']['t']:.1f}, p = {c4._p(e3['welch']['p_two_sided'])}).")
        w(f"\n**Time to completion.** H {t['h']['mean']:,.0f} ms (SD {t['h']['sd']:,.0f}) against A {t['a']['mean']:,.0f} ms (SD {t['a']['sd']:,.0f}): A is "
          f"{-t['reduction_pct_a_vs_h']:.1f}% {'longer' if t['reduction_pct_a_vs_h'] < 0 else 'shorter'} than H (Welch t = {t['welch']['t']:.1f}, p = {c4._p(t['welch']['p_two_sided'])}).")
        q, fl, st = h["eq4"], h["flash"], h["static"]
        w("\n**Equation 4 (RAM) and flash.**\n")
        w("| | H (HTTPS) | A (proposed) | Reduction % (Eq. 4) |\n|---|---|---|---|")
        w(f"| Static RAM added (B) | {st['h']:,} | {st['a']:,} | {inf.relative_reduction_pct(st['h'], st['a']):.1f} (A is higher: it carries the delta decoder) |")
        if q.get("h_heap_max") is not None:
            w(f"| Peak heap (B): H series maximum, A at its mean / maximum | {q['h_heap_max']:,} | {q['a_heap_mean']:,.0f} / {q['a_heap_max']:,.0f} | "
              f"{inf.relative_reduction_pct(q['h_heap_max'], q['a_heap_mean']):.1f} / {inf.relative_reduction_pct(q['h_heap_max'], q['a_heap_max']):.1f} |")
            w(f"| **Peak RAM, static + heap (B)** | {q['h_total']:,} ({q['h_budget_pct']:.0f}% of 50 KiB) | {q['a_total_mean']:,.0f} ({q['a_budget_pct_mean']:.0f}%) mean; "
              f"{q['a_total_max']:,.0f} ({q['a_budget_pct_max']:.0f}%) max | **{q['reduction_pct_mean']:.1f}** (A mean) / **{q['reduction_pct_max']:.1f}** (A max) |")
        w(f"| Flash added (B) | {fl['h']:,} ({fl['h'] / CLASS2_FLASH_B * 100:.1f}% of 250 KiB) | {fl['a']:,} ({fl['a'] / CLASS2_FLASH_B * 100:.1f}%) | {fl['reduction_pct_a_vs_h']:.1f} |")
        w("\nH is a lower bound: no certificate validation and the framework's default TLS buffers. The 50 KiB and 250 KiB figures are an accounting budget on a 520 KB ESP32, "
          "not a hardware limit: read the result as 'fits' or 'exceeds' the Class 2 budget.\n")
        if h.get("capture_vs_device_ms"):
            c = h["capture_vs_device_ms"]
            w(f"Cross-check: the capture's time to completion minus the device's own time is {c['mean']:.0f} ms on average (SD {c['sd']:.0f}), "
              "the device total including the final image verification.\n")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------------------------------ confirmation run
CONFIRM_METRICS = ("ttc_ms", "wire_bytes", "decrypt_recon_ms", "flash_kbps", "heap_peak_used", "decrypt_avg_us")


def confirmation(conf_rows: list[dict], conf_raw: Path | None, main_pairs: list[dict], wanted: int = 20) -> dict:
    """A/B repeated on the fixed harness (no reset of a device that began on its own): does it agree with the main campaign?"""
    pairs = c4.select_pairs(conf_rows, wanted)
    if len(pairs) < 3:
        raise ValueError(f"only {len(pairs)} complete A/B pairs in the confirmation run")
    flags = c4.interrupted_map(conf_rows, conf_raw) if conf_raw else {}
    counted = [r for r in conf_rows if not campaign.truthy(r["warmup"])]
    counts = {sc: {s: sum(1 for r in counted if r["scenario"] == sc and r["status"] == s) for s in ("ok", "failed", "invalid")} for sc in "AB"}
    conf_t = {r["metric"]: r for r in c4.paired_table(pairs)}
    main_t = {r["metric"]: r for r in c4.paired_table(main_pairs)}
    rows = [{"metric": m, "label": conf_t[m]["label"], "conf": conf_t[m], "main": main_t[m]} for m in CONFIRM_METRICS if m in conf_t and m in main_t]
    a_vs_a = []
    for m in ("ttc_ms", "wire_bytes", "decrypt_recon_ms", "flash_kbps", "heap_peak_used"):
        x, y = c4.column(pairs, "A", m), c4.column(main_pairs, "A", m)
        if len(x) > 2 and len(y) > 2:
            a_vs_a.append({"metric": m, "label": conf_t[m]["label"], "conf_mean": inf.mean(x), "main_mean": inf.mean(y),
                           "diff_pct": (inf.mean(x) - inf.mean(y)) / inf.mean(y) * 100.0, "p": inf.welch_t(x, y)["p_two_sided"]})
    return {"n_pairs": len(pairs), "counts": counts, "interrupted": sum(flags.values()), "logs": len(flags), "rows": rows, "a_vs_a": a_vs_a}


def render_confirmation(c: dict) -> str:
    L: list[str] = []
    w = L.append
    w("## 11. Confirmation run: A and B repeated on the fixed harness\n")
    k = c["counts"]
    w(f"{c['n_pairs']} complete A/B pairs. Counted attempts: A ok {k['A']['ok']}, failed {k['A']['failed']}; B ok {k['B']['ok']}, failed {k['B']['failed']}; "
      f"harness faults re-run: A {k['A']['invalid']}, B {k['B']['invalid']}. Cycles in which the harness interrupted an update: {c['interrupted']} of {c['logs']}.\n")
    w("| Metric | Reduction % (confirmation) | p | n | Reduction % (main campaign) | p | n |\n|---|---|---|---|---|---|---|")
    for r in c["rows"]:
        a, b = r["conf"], r["main"]
        w(f"| {r['label']} | {_f(a['reduction_pct'])} | {c4._p(a['p'])} | {a['n']} | {_f(b['reduction_pct'])} | {c4._p(b['p'])} | {b['n']} |")
    w("\nScenario A in the confirmation run against Scenario A in the main campaign (unpaired Welch; different days):\n")
    w("| Metric | Confirmation mean | Main mean | Difference % | p |\n|---|---|---|---|---|")
    for r in c["a_vs_a"]:
        w(f"| {r['label']} | {_f(r['conf_mean'])} | {_f(r['main_mean'])} | {_f(r['diff_pct'])} | {c4._p(r['p'])} |")
    w("")
    return chr(10).join(L)
