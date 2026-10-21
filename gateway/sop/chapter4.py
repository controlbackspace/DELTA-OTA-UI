"""Chapter 4 statistics from the recorded campaign files (no new data, only analysis).

    python -m sop.chapter4 --ab <campaign-AB-full-...> --t3 <campaign-T3-full-...> \
        --cde <R02 campaign/trials.csv> --web3 <R05 run folder> --out <folder> [--sop4 <folder>]
    (the data pack's single entry point is `python -m sop.pack build`, which finds the runs through 01-raw-data/RUNS-INDEX.csv)

Writes STATISTICS.md, data/*.csv and MANIFEST.sha256 into --out (and web3_checks.csv / updater_heap_peak.csv into --sop4).
Rules fixed here so every number can be regenerated:

* Table 2 cycle n = the n-th complete A/B pair: a trial number for which both Scenario A and Scenario B finished `ok`,
  taken in ascending trial order, the first 60 pairs. Failed cycles stay in the raw CSV and are listed in failures.csv.
* Warm-up cycles are never analysed.
* Statistics are those of Chapter 3 (inference.py): Eq. 1 and 2, the paired t-test, Eq. 3 to 6, with a few supporting tests
  (sign test, Pearson r, Fisher exact, Wilson interval, Welch t) that the discussion uses.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import re
from pathlib import Path

from . import campaign, inference as inf
from .serial_parse import parse_log, peak_heap

PAIRS_WANTED = 60
AB_METRICS = [                      # (column, label, decimals)
    ("ttc_ms", "Wireshark TTC (ms)", 1),
    ("wire_bytes", "Bytes on the wire", 0),
    ("blocks", "1 KiB blocks transferred", 0),
    ("requests", "Block requests (with repeats)", 2),
    ("retransmissions", "Repeated block requests", 2),
    ("decrypt_recon_ms", "Decryption + reconstruction (ms)", 1),
    ("flash_kbps", "Flash write throughput (KB/s)", 1),
    ("decrypt_avg_us", "AES-CCM decryption per block (us)", 1),
    ("decrypt_max_us", "Slowest block decryption (us)", 0),
    ("reconstruct_us", "Decoder time: inflate, merge, flash (us)", 0),
    ("total_us", "Device stream time (us)", 0),
    ("heap_peak_used", "Peak heap used during the update (B)", 0),
    ("heap_min_free", "Minimum free heap (B)", 0),
    ("static_ram_kb", "Static RAM of the technology (KB)", 2),
    ("payload_bytes", "Payload size (B)", 0),
]
# Static figures of the SOP 4 evidence report (Tables 10 and 11, ESP32 + Arduino builds, increments over the Wi-Fi-only control).
UPDATER_FLASH_B, UPDATER_STATIC_B = 43_040, 29_400
WEB3_FLASH_B, WEB3_STATIC_B = 156_872, 3_244
CLASS2_FLASH_B, CLASS2_RAM_B = 250 * 1024, 50 * 1024


# ----------------------------------------------------------------------------------------------- loading
def load_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def short_path(p) -> str:
    """A path as shown in the documents: relative to the sop-results root when it is under one (so it means something on any machine)."""
    s = str(p)
    i = s.lower().find("sop-results")
    return s[i + len("sop-results") + 1:].replace(chr(92), "/") if i >= 0 else s


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def select_pairs(rows: list[dict], wanted: int = PAIRS_WANTED, scenarios: tuple[str, str] = ("A", "B")) -> list[dict]:
    """The first `wanted` complete pairs of two scenarios (non-warm-up, both `ok`), as {pair, trial, <first>, <second>} in trial order.
    Default A/B (Table 2); ("A", "N") pairs the proposed architecture with the naked-CoAP baseline."""
    first, second = scenarios
    counted = [r for r in rows if not campaign.truthy(r["warmup"])]
    ok = {sc: {int(r["trial"]): r for r in counted if r["scenario"] == sc and r["status"] == "ok"} for sc in scenarios}
    trials = sorted(set(ok[first]) & set(ok[second]))[:wanted]
    return [{"pair": i, "trial": t, first: ok[first][t], second: ok[second][t]} for i, t in enumerate(trials, 1)]


def column(pairs: list[dict], scenario: str, metric: str) -> list[float]:
    return [v for v in (_num(p[scenario].get(metric)) for p in pairs) if v is not None]


# ----------------------------------------------------------------------------------------------- analyses
def paired_table(pairs: list[dict], first: str = "A", second: str = "B") -> list[dict]:
    """Per metric: both scenarios' mean/SD/tolerance limit, the reduction (second - first) / second, and the paired test of
    first - second. Keys are suffixed with the scenario letters (mean_A, mean_B; for the naked baseline mean_A, mean_N)."""
    out = []
    for col, label, digits in AB_METRICS:
        # only pairs where both cycles have the value, so the two scenarios stay matched (a few cycles lack a heap marker)
        both = [(_num(p[first].get(col)), _num(p[second].get(col))) for p in pairs]
        both = [(x, y) for x, y in both if x is not None and y is not None]
        a, b = [x for x, _ in both], [y for _, y in both]
        if len(a) < 2:
            continue
        row = {"metric": col, "label": label, "digits": digits, "n": len(a),
               f"mean_{first}": inf.mean(a), f"sd_{first}": inf.sample_sd(a), f"mean_{second}": inf.mean(b), f"sd_{second}": inf.sample_sd(b),
               "reduction_pct": inf.relative_reduction_pct(inf.mean(b), inf.mean(a)) if inf.mean(b) else None,
               f"utl_{first}": inf.upper_tolerance_limit(a)["upper_limit"], f"utl_{second}": inf.upper_tolerance_limit(b)["upper_limit"]}
        t = inf.paired_t_test(a, b)
        row.update({"mean_diff": t["mean_difference"], "sd_diff": t["sd_of_differences"], "degenerate": t["degenerate"],
                    "t": t["t"], "p": t["p_two_sided"]})
        if not t["degenerate"]:
            ci = inf.paired_ci95(a, b)
            row.update({"ci_low": ci["low"], "ci_high": ci["high"], "dz": inf.effect_size_dz(a, b)})
            s = inf.sign_test_p(a, b)
            row.update({"a_lower": s["first_lower"], "n_sign": s["n"], "sign_p": s["p_two_sided"]})
        out.append(row)
    return out


def root_cause(pairs: list[dict]) -> dict:
    """Why the time to completion varies: correlation with repeated block requests, and the cycles with none."""
    out = {}
    for sc in "AB":
        ttc, rt = column(pairs, sc, "ttc_ms"), column(pairs, sc, "retransmissions")
        dr = column(pairs, sc, "decrypt_recon_ms")
        none = [t for t, r in zip(ttc, rt) if r == 0]
        some = [t for t, r in zip(ttc, rt) if r > 0]
        out[sc] = {"n": len(ttc), "r": inf.pearson_r(ttc, rt), "slope_ms_per_retransmission": inf.linear_slope(rt, ttc),
                   "cv_ttc": inf.sample_sd(ttc) / inf.mean(ttc), "cv_decrypt_recon": inf.sample_sd(dr) / inf.mean(dr),
                   "n_clean": len(none), "mean_clean": inf.mean(none) if none else None,
                   "sd_clean": inf.sample_sd(none) if len(none) > 1 else None,
                   "n_repeat": len(some), "mean_repeat": inf.mean(some) if some else None}
    return out


def classify_failure(note: str, serial_text: str) -> str:
    """A short cause for a failed cycle, from the device's own words."""
    m = re.search(r"\[Delta\] FAILED: ([^\r\n]+)", serial_text or "")
    if m:
        return m.group(1).strip()
    if "stall" in (note or "").lower() or "stall" in (serial_text or "").lower():
        return "transfer stalled"
    return (note or "unknown").split(":")[-1].strip()[:60] or "unknown"


START_MARKERS = ("Update available", "Backing up")
RESET_MARKER = "POWERON_RESET"


def update_interrupted(log_text: str) -> bool:
    """True when the device had already started its update (it printed `Update available` or began the ota_0 -> ota_1 backup) and a
    power-on-reset line follows. With the harness of Scenarios A and B that reset is the harness's own EN pulse, so the update was
    interrupted mid-backup (the delta then has no base and fails with `delta decode error`). A device that started on its own and was
    left alone (the fixed harness) has no reset line, and a clean start has its marker only after the reset."""
    lines = log_text.splitlines()
    start = next((i for i, l in enumerate(lines) if any(m in l for m in START_MARKERS)), None)
    return start is not None and any(RESET_MARKER in l for l in lines[start + 1:])


def cycle_log(raw_dir: Path | None, scenario: str, trial, warmup: bool = False) -> str:
    if not raw_dir:
        return ""
    tag = "w" if warmup else "c"
    logs = sorted(glob.glob(str(Path(raw_dir) / f"cycle-{scenario}-{tag}{int(trial):03d}-*.serial.log")))
    return Path(logs[-1]).read_text(encoding="utf-8", errors="replace") if logs else ""


def interrupted_map(rows: list[dict], raw_dir: Path | None) -> dict:
    """(scenario, trial) -> True/False for every counted ok or failed cycle that has a serial log; missing logs are left out."""
    out = {}
    for r in rows:
        if campaign.truthy(r["warmup"]) or r["status"] not in campaign.DONE_STATUSES:
            continue
        text = cycle_log(raw_dir, r["scenario"], r["trial"])
        if text:
            out[(r["scenario"], int(r["trial"]))] = update_interrupted(text)
    return out


def outcomes_by_start(rows: list[dict], flags: dict, scenarios: str = "AB") -> dict:
    """ok / failed counts of the counted cycles, split by whether the harness interrupted the update."""
    out = {}
    for sc in scenarios:
        cell = {"interrupted": {"ok": 0, "failed": 0}, "clean": {"ok": 0, "failed": 0}}
        for r in rows:
            if r["scenario"] != sc or campaign.truthy(r["warmup"]) or r["status"] not in campaign.DONE_STATUSES:
                continue
            f = flags.get((sc, int(r["trial"])))
            if f is not None:
                cell["interrupted" if f else "clean"][r["status"]] += 1
        out[sc] = cell
    return out


def interruption_sensitivity(pairs: list[dict], flags: dict, metrics=("ttc_ms", "wire_bytes", "decrypt_recon_ms", "flash_kbps", "heap_peak_used"),
                             first: str = "A", second: str = "B") -> dict:
    """The main comparisons on all pairs and on the pairs in which neither cycle was interrupted."""
    clean = [p for p in pairs if not flags.get((first, p["trial"])) and not flags.get((second, p["trial"]))]
    full = {r["metric"]: r for r in paired_table(pairs, first, second)}
    sub = {r["metric"]: r for r in paired_table(clean, first, second)} if len(clean) >= 3 else {}
    rows = [{"metric": m, "label": full[m]["label"], "all": full[m], "clean": sub.get(m)} for m in metrics if m in full]
    return {"n_all": len(pairs), "n_clean": len(clean), "rows": rows}


def failures(rows: list[dict], raw_dir: Path | None = None) -> dict:
    counted = [r for r in rows if not campaign.truthy(r["warmup"])]
    detail, by_scenario = [], {}
    for sc in "AB":
        c = {s: sum(1 for r in counted if r["scenario"] == sc and r["status"] == s) for s in ("ok", "failed", "invalid")}
        n = c["ok"] + c["failed"]
        lo, hi = inf.wilson_interval(c["ok"], n)
        by_scenario[sc] = {**c, "attempts": n, "rate": c["ok"] / n, "wilson_low": lo, "wilson_high": hi}
    for r in counted:
        if r["status"] != "failed" or r["scenario"] not in "AB":
            continue
        text = ""
        if raw_dir:
            logs = sorted(glob.glob(str(Path(raw_dir) / f"cycle-{r['scenario']}-c{int(r['trial']):03d}-*.serial.log")))
            if logs:
                text = Path(logs[-1]).read_text(encoding="utf-8", errors="replace")
        detail.append({"scenario": r["scenario"], "trial": int(r["trial"]), "cause": classify_failure(r["note"], text),
                       "reconstructed": bool(re.search(r"reconstructed|RECONSTRUCTED", text)),
                       "interrupted": update_interrupted(text) if text else "", "note": r["note"]})
    a, b = by_scenario["A"], by_scenario["B"]
    both_n, both_ok = a["attempts"] + b["attempts"], a["ok"] + b["ok"]
    lo, hi = inf.wilson_interval(both_ok, both_n)
    flash = sum(1 for d in detail if d["scenario"] == "A" and "flash write" in d["cause"])
    return {"by_scenario": by_scenario, "detail": detail, "both": {"ok": both_ok, "attempts": both_n, "rate": both_ok / both_n,
            "low": lo, "high": hi}, "fisher_p": inf.fisher_exact_two_sided(a["failed"], a["attempts"], b["failed"], b["attempts"]),
            "fisher_flash_write_p": inf.fisher_exact_two_sided(flash, a["attempts"], 0, b["attempts"]), "flash_write_in_A": flash}


def after_failure_effect(rows: list[dict]) -> dict:
    """Cycles that ran straight after a failed or invalid cycle (and so after a device reset) against the others."""
    flags, prev = [], None
    for r in rows:
        flags.append(prev is not None and prev["status"] in ("failed", "invalid"))
        prev = r
    out = {}
    for sc in "AB":
        rec = [(f, float(r["ttc_ms"])) for r, f in zip(rows, flags)
               if r["scenario"] == sc and not campaign.truthy(r["warmup"]) and r["status"] == "ok" and _num(r.get("ttc_ms")) is not None]
        after, rest = [v for f, v in rec if f], [v for f, v in rec if not f]
        row = {"n_after": len(after), "mean_after": inf.mean(after) if after else None, "n_rest": len(rest), "mean_rest": inf.mean(rest)}
        if len(after) > 1:
            row.update(inf.welch_t(after, rest))
        out[sc] = row
    return out


def sensitivity(rows: list[dict], pairs: list[dict]) -> list[dict]:
    """The time-to-completion reduction under other ways of choosing the data."""
    counted = [r for r in rows if not campaign.truthy(r["warmup"])]
    flags, prev = {}, None
    for r in rows:
        flags[id(r)] = prev is not None and prev["status"] in ("failed", "invalid")
        prev = r
    out = []

    def add(label, a, b, paired):
        red = inf.relative_reduction_pct(inf.mean(b), inf.mean(a))
        p = inf.paired_t_test(a, b)["p_two_sided"] if paired else inf.welch_t(a, b)["p_two_sided"]
        out.append({"label": label, "n": f"{len(a)} pairs" if paired else f"{len(a)} A, {len(b)} B", "reduction_pct": red, "p": p})

    a, b = column(pairs, "A", "ttc_ms"), column(pairs, "B", "ttc_ms")
    add("The 60 matched pairs (Table 2)", a, b, True)
    clean = [p for p in pairs if not flags[id(p["A"])] and not flags[id(p["B"])]]
    add("Pairs where neither cycle followed a failure", column(clean, "A", "ttc_ms"), column(clean, "B", "ttc_ms"), True)
    okA = [float(r["ttc_ms"]) for r in counted if r["scenario"] == "A" and r["status"] == "ok"]
    okB = [float(r["ttc_ms"]) for r in counted if r["scenario"] == "B" and r["status"] == "ok"]
    add("All successful counted cycles, unpaired (Welch)", okA, okB, False)
    return out


def table3_stats(rows: list[dict]) -> list[dict]:
    counted = [r for r in rows if not campaign.truthy(r["warmup"]) and r["status"] == "ok"]
    out = []
    for col, label, digits in [("poll_ms", "Web3 smart-contract polling (ms)", 2), ("sha_ms", "Local SHA-256 (ms)", 3),
                               ("encap_ms", "AES-CCM encapsulation (ms)", 2), ("gw_ram_mb", "Peak gateway RAM (MB)", 2),
                               ("gw_cpu_pct", "Peak gateway CPU (%)", 2), ("diff_ms", "Delta generation (ms), raw column", 2),
                               ("to_dota_ms", "Device-stream packaging (ms), raw column", 2)]:
        v = sorted(float(r[col]) for r in counted if _num(r.get(col)) is not None)
        u = inf.upper_tolerance_limit(v)
        out.append({"label": label, "digits": digits, "n": len(v), "mean": u["mean"], "sd": u["sd"], "median": (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2,
                    "min": v[0], "max": v[-1], "utl": u["upper_limit"]})
    return out


def scenario_stats(rows: list[dict]) -> dict:
    out = {}
    for sc in "CDE":
        used = [r for r in rows if r["scenario"] == sc and not campaign.truthy(r["warmup"])]
        done = [r for r in used if r["status"] in campaign.DONE_STATUSES]
        rejected = sum(1 for r in done if campaign.truthy(r.get("rejected")))
        row = {"trials": len(done), "rejected": rejected, "failures": len(done) - rejected,
               "confidence": inf.success_run_confidence(0.95, len(done)) if len(done) == rejected else None}
        for col in ("delay_ms", "detect_ms"):
            v = [float(r[col]) for r in done if _num(r.get(col)) is not None]
            if len(v) > 1:
                row[col] = {"mean": inf.mean(v), "sd": inf.sample_sd(v), "min": min(v), "max": max(v)}
        out[sc] = row
    return out


def web3_stats(log_text: str) -> dict:
    """The 60 on-device ledger checks: timings, per-check heap and the highest heap use."""
    p = parse_log(log_text)
    runs = [w for w in p["web3"] if w["ok"]]
    out = {"n_ok": len(runs), "n_all": len(p["web3"]), "metrics": {}}
    for key, label in (("tls_connect_ms", "TLS connect and handshake (ms)"), ("request_ms", "Request and response (ms)"),
                       ("keccak_us", "Keccak-256 of the call data (us)"), ("decode_us", "ABI decode (us)")):
        v = [float(w[key]) for w in runs]
        u = inf.upper_tolerance_limit(v)
        out["metrics"][key] = {"label": label, "mean": u["mean"], "sd": u["sd"], "max": max(v), "utl": u["upper_limit"]}
    total = [w["tls_connect_ms"] + w["request_ms"] + (w["keccak_us"] + w["decode_us"]) / 1000.0 for w in runs]
    u = inf.upper_tolerance_limit(total)
    out["total_ms"] = {"mean": u["mean"], "sd": u["sd"], "max": max(total), "utl": u["upper_limit"]}
    out["tls_share"] = out["metrics"]["tls_connect_ms"]["mean"] / u["mean"]
    out["heap"] = peak_heap(p["mem"], "web3-start", "web3-end")
    out["runs"] = runs
    out["mem_runs"] = [m for m in p["mem"] if m["phase"] == "web3-run"]
    return out


def sop4_comparison(heap_mean_A: float, heap_utl_A: float, web3_heap_peak: float) -> dict:
    """Like-for-like: the offloaded design (updater only) against the same device doing the Web3 work itself."""
    off_flash, non_flash = UPDATER_FLASH_B, UPDATER_FLASH_B + WEB3_FLASH_B
    off_static, non_static = UPDATER_STATIC_B, UPDATER_STATIC_B + WEB3_STATIC_B
    off_peak, off_peak_utl = off_static + heap_mean_A, off_static + heap_utl_A
    non_peak = non_static + web3_heap_peak
    return {
        "flash": {"offloaded": off_flash, "not_offloaded": non_flash, "reduction_pct": inf.relative_reduction_pct(non_flash, off_flash),
                  "offloaded_pct_budget": off_flash / CLASS2_FLASH_B * 100, "not_offloaded_pct_budget": non_flash / CLASS2_FLASH_B * 100},
        "static_ram": {"offloaded": off_static, "not_offloaded": non_static, "reduction_pct": inf.relative_reduction_pct(non_static, off_static),
                       "offloaded_pct_budget": off_static / CLASS2_RAM_B * 100, "not_offloaded_pct_budget": non_static / CLASS2_RAM_B * 100},
        "peak_ram": {"offloaded": off_peak, "offloaded_at_utl": off_peak_utl, "not_offloaded": non_peak,
                     "reduction_pct": inf.relative_reduction_pct(non_peak, off_peak),
                     "reduction_pct_at_utl": inf.relative_reduction_pct(non_peak, off_peak_utl),
                     "offloaded_pct_budget": off_peak / CLASS2_RAM_B * 100, "offloaded_utl_pct_budget": off_peak_utl / CLASS2_RAM_B * 100,
                     "not_offloaded_pct_budget": non_peak / CLASS2_RAM_B * 100},
        "web3_alone_peak": WEB3_STATIC_B + web3_heap_peak, "web3_alone_pct_budget": (WEB3_STATIC_B + web3_heap_peak) / CLASS2_RAM_B * 100,
        "heap_ratio_vs_updater_mean": web3_heap_peak / heap_mean_A, "heap_ratio_vs_updater_utl": web3_heap_peak / heap_utl_A,
    }


# ----------------------------------------------------------------------------------------------- output
def _f(v, d=2):
    return "-" if v is None else f"{v:,.{d}f}"


def _p(v):
    if v is None:
        return "-"
    return f"{v:.1e}" if v < 1e-3 else f"{v:.3f}"


def render(ctx: dict) -> str:
    L: list[str] = []
    w = L.append
    w("# Chapter 4 statistics (generated)\n")
    w("Generated by `python -m sop.pack build` (module `sop.chapter4`) from the recorded runs in `01-raw-data/runs/`. Do not edit by hand; rerun the command. "
      "Formulas are those of Chapter 3 (`gateway/sop/inference.py`).\n")
    w("## 1. Inputs\n")
    w("| Input | File | SHA-256 |\n|---|---|---|")
    for name, path in ctx["inputs"]:
        w(f"| {name} | `{short_path(path)}` | `{sha256(path)}` |")
    w("")
    w("## 2. Which cycles are analysed\n")
    pairs = ctx["pairs"]
    w(f"- Table 2 cycle n is the n-th **complete A/B pair** (both Scenario A and B `ok` for the same trial number), in ascending trial order, the first {PAIRS_WANTED}. "
      f"{len(pairs)} pairs were available and used (trials {pairs[0]['trial']} to {pairs[-1]['trial']}).")
    w("- Warm-up cycles are never analysed. Failed and harness-invalid cycles stay in the raw CSV (see section 7).")
    w("- Significance level: two-sided alpha = 0.05; for the five primary comparisons a Bonferroni level of 0.01 is also checked.")
    w(f"- Tolerance factor (Eq. 5): K = {inf.tolerance_factor(len(pairs))[0]} (exact one-sided factor, 99% coverage, 95% confidence, n = {len(pairs)}).\n")
    w("Pair numbers to trial numbers: " + ", ".join(f"{p['pair']}={p['trial']}" for p in pairs) + "\n")

    w("## 3. Table 2 metrics: Scenario A against B (Eq. 1, Eq. 2, Eq. 3, paired t-test, Eq. 5)\n")
    w("Reduction = (B - A) / B x 100 (Eq. 3 form; negative means A is larger). `diff` = mean(A - B). UTL = mean + K x SD.\n")
    w("| Metric | A mean (SD) | B mean (SD) | Reduction % | Mean diff (95% CI) | t | p | dz | A lower in | UTL A | UTL B |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for r in ctx["paired"]:
        d = r["digits"]
        if r["degenerate"]:
            w(f"| {r['label']} | {_f(r['mean_A'], d)} ({_f(r['sd_A'], d)}) | {_f(r['mean_B'], d)} ({_f(r['sd_B'], d)}) | {_f(r['reduction_pct'])} | "
              f"{_f(r['mean_diff'], d)} (no variance) | - | - | - | - | {_f(r['utl_A'], d)} | {_f(r['utl_B'], d)} |")
        else:
            w(f"| {r['label']} | {_f(r['mean_A'], d)} ({_f(r['sd_A'], d)}) | {_f(r['mean_B'], d)} ({_f(r['sd_B'], d)}) | {_f(r['reduction_pct'])} | "
              f"{_f(r['mean_diff'], d)} ({_f(r['ci_low'], d)} to {_f(r['ci_high'], d)}) | {_f(r['t'])} | {_p(r['p'])} | {_f(r['dz'])} | "
              f"{r['a_lower']} of {r['n_sign']} untied (sign p {_p(r['sign_p'])}) | {_f(r['utl_A'], d)} | {_f(r['utl_B'], d)} |")
    short = [f"{r['label']}: {r['n']} pairs" for r in ctx["paired"] if r["n"] != len(pairs)]
    if short:
        w("\nPairs used per metric when fewer than all (a cycle without a value is dropped together with its partner, so A and B stay matched; "
          "the tolerance factor is then the Natrella approximation, not the exact table value): " + "; ".join(short) + ".")
    w("\nStatic RAM is a build property: identical in every cycle, so its differences are all zero (no t-test).\n")

    w("## 4. Why the completion time varies (root-cause analysis required by Chapter 3)\n")
    w("| | A (delta) | B (full binary) |\n|---|---|---|")
    rc = ctx["root"]
    w(f"| Pearson r, TTC against repeated block requests | {_f(rc['A']['r'], 3)} | {_f(rc['B']['r'], 3)} |")
    w(f"| Slope (ms per repeated request) | {_f(rc['A']['slope_ms_per_retransmission'], 0)} | {_f(rc['B']['slope_ms_per_retransmission'], 0)} |")
    w(f"| Coefficient of variation, TTC | {rc['A']['cv_ttc']:.1%} | {rc['B']['cv_ttc']:.1%} |")
    w(f"| Coefficient of variation, decryption + reconstruction | {rc['A']['cv_decrypt_recon']:.2%} | {rc['B']['cv_decrypt_recon']:.2%} |")
    w(f"| Cycles with no repeated request | {rc['A']['n_clean']} of {rc['A']['n']} | {rc['B']['n_clean']} of {rc['B']['n']} |")
    w(f"| TTC of those cycles, mean (SD) ms | {_f(rc['A']['mean_clean'], 0)} ({_f(rc['A']['sd_clean'], 0)}) | {_f(rc['B']['mean_clean'], 0)} ({_f(rc['B']['sd_clean'], 0)}) |")
    w(f"| TTC of cycles with repeats, mean ms | {_f(rc['A']['mean_repeat'], 0)} | {_f(rc['B']['mean_repeat'], 0)} |\n")

    w("## 5. Failures and the update integrity rate\n")
    fl = ctx["fail"]
    w("| | Successful | Failed | Rate (Wilson 95%) | Harness faults re-run |\n|---|---|---|---|---|")
    for sc, name in (("A", "A: delta"), ("B", "B: full binary")):
        b = fl["by_scenario"][sc]
        w(f"| {name} | {b['ok']} | {b['failed']} | {b['rate']:.1%} ({b['wilson_low']:.1%} to {b['wilson_high']:.1%}) | {b['invalid']} |")
    b = fl["both"]
    w(f"| Both | {b['ok']} | {b['attempts'] - b['ok']} | {b['rate']:.1%} ({b['low']:.1%} to {b['high']:.1%}) | |")
    w(f"\nFailure rate A against B: Fisher exact p = {_p(fl['fisher_p'])}. Flash-write errors in A ({fl['flash_write_in_A']} of {fl['by_scenario']['A']['attempts']}) "
      f"against none in B: Fisher p = {_p(fl['fisher_flash_write_p'])}.\n")
    w("| Scenario | Trial | Cause (device's own words) | Image reconstructed? |\n|---|---|---|---|")
    for d in fl["detail"]:
        w(f"| {d['scenario']} | {d['trial']} | {d['cause']} | {'yes' if d['reconstructed'] else 'no'} |")
    w("")
    w("Cycles that ran straight after a failed or invalid cycle (after a device reset), time to completion:\n")
    w("| | n after | mean after (ms) | n others | mean others (ms) | Welch t | p |\n|---|---|---|---|---|---|---|")
    for sc in "AB":
        r = ctx["after"][sc]
        w(f"| {sc} | {r['n_after']} | {_f(r['mean_after'], 0)} | {r['n_rest']} | {_f(r['mean_rest'], 0)} | {_f(r.get('t'))} | {_p(r.get('p_two_sided'))} |")
    w("")

    w("### Why cycles failed: the harness reset race\n")
    w("The updater starts an update on its own once the release is staged. The harness of Scenarios A and B then pulses the board's reset pin; if the update "
      "has already begun, the reset lands in the middle of the ota_0 -> ota_1 backup copy, the delta has no base and fails (`delta decode error`). "
      "`interrupted` = the serial log shows the update started and a reset line after it (function `update_interrupted`).\n")
    w("| Scenario | Harness interrupted the update: ok / failed | Clean start: ok / failed |\n|---|---|---|")
    for sc, name in (("A", "A: delta"), ("B", "B: full binary")):
        c = ctx["by_start"][sc]
        w(f"| {name} | {c['interrupted']['ok']} / {c['interrupted']['failed']} | {c['clean']['ok']} / {c['clean']['failed']} |")
    sens = ctx["interrupt_sens"]
    w(f"\nMain comparisons on all {sens['n_all']} pairs and on the {sens['n_clean']} pairs in which neither cycle was interrupted:\n")
    w("| Metric | Reduction % (all pairs) | t | p | Reduction % (clean pairs) | t | p |\n|---|---|---|---|---|---|---|")
    for r in sens["rows"]:
        a, c = r["all"], r["clean"]
        cs = "- | - | -" if not c or c.get("t") is None else f"{_f(c['reduction_pct'])} | {_f(c['t'])} | {_p(c['p'])}"
        w(f"| {r['label']} | {_f(a['reduction_pct'])} | {_f(a['t'])} | {_p(a['p'])} | {cs} |")
    w("")
    w("## 6. Sensitivity of the time-to-completion result\n")
    w("| Analysis | Data | Reduction % | p |\n|---|---|---|---|")
    for r in ctx["sens"]:
        w(f"| {r['label']} | {r['n']} | {_f(r['reduction_pct'])} | {_p(r['p'])} |")
    w("")

    w("## 7. Table 3: Edge gateway on the capped Raspberry Pi (60 counted cycles)\n")
    w("| Column | n | Mean (Eq. 1) | SD (Eq. 2) | Median | Min | Max | UTL (Eq. 5) |\n|---|---|---|---|---|---|---|---|")
    for r in ctx["t3"]:
        d = r["digits"]
        w(f"| {r['label']} | {r['n']} | {_f(r['mean'], d)} | {_f(r['sd'], d)} | {_f(r['median'], d)} | {_f(r['min'], d)} | {_f(r['max'], d)} | {_f(r['utl'], d)} |")
    w("")

    w("## 8. Table 4: Scenarios C, D, E and the Success-Run Theorem (Eq. 6)\n")
    w("| Scenario | Cycles | Rejected / blocked / reverted | Failures | C = 1 - 0.95^n |\n|---|---|---|---|---|")
    for sc, name in (("C", "C: tampered patch"), ("D", "D: kill switch"), ("E", "E: incomplete signature")):
        r = ctx["cde"][sc]
        conf = "-" if r["confidence"] is None else f"{r['confidence']:.2%}"
        w(f"| {name} | {r['trials']} | {r['rejected']} | {r['failures']} | {conf} |")
    w(f"\nCycles needed for 95% reliability at 95% confidence: {inf.success_run_trials(0.95, 0.95)} (1 - 0.95^59 = {inf.success_run_confidence(0.95, 59):.2%}).\n")
    w("| Delay measure | Mean (ms) | SD | Min | Max |\n|---|---|---|---|---|")
    for sc, col, name in (("C", "delay_ms", "C: release on-chain to rejection"), ("D", "delay_ms", "D: revocation sent to refusal"), ("D", "detect_ms", "D: block mined to refusal")):
        m = ctx["cde"][sc].get(col)
        if m:
            w(f"| {name} | {_f(m['mean'], 0)} | {_f(m['sd'], 1)} | {_f(m['min'], 0)} | {_f(m['max'], 0)} |")
    w("")

    if ctx.get("web3"):
        wb, cmp_ = ctx["web3"], ctx["compare"]
        w("## 9. SOP 4: the on-device Web3 client (60 ledger checks on the ESP32)\n")
        w(f"{wb['n_ok']} of {wb['n_all']} checks returned the correct release state.\n")
        w("| Measurement | Mean | SD | Largest | UTL (Eq. 5) |\n|---|---|---|---|---|")
        for m in wb["metrics"].values():
            w(f"| {m['label']} | {_f(m['mean'], 1)} | {_f(m['sd'], 1)} | {_f(m['max'], 0)} | {_f(m['utl'], 1)} |")
        t = wb["total_ms"]
        w(f"| **One complete ledger check (ms)** | {_f(t['mean'], 1)} | {_f(t['sd'], 1)} | {_f(t['max'], 1)} | {_f(t['utl'], 1)} |")
        h = wb["heap"]
        w(f"\nTLS share of one check: {wb['tls_share']:.1%}. Peak heap used (start free - lowest free over the 60 checks, exact={h['exact']}): "
          f"**{h['peak_bytes']:,} B** ({h['peak_bytes'] / 1024:.1f} KiB); start-to-lowest minimum: {h['class2_peak']:,} B.\n")
        w("### Like-for-like: offloaded design against the same device doing the Web3 work itself (Eq. 4 form)\n")
        w("| Resource | Offloaded (updater only) | Not offloaded (updater + on-device Web3) | Reduction % |\n|---|---|---|---|")
        for key, name in (("flash", "Flash (B)"), ("static_ram", "Static RAM (B)")):
            c = cmp_[key]
            w(f"| {name} | {c['offloaded']:,} ({c['offloaded_pct_budget']:.1f}% of Class 2) | {c['not_offloaded']:,} ({c['not_offloaded_pct_budget']:.1f}%) | {c['reduction_pct']:.2f} |")
        c = cmp_["peak_ram"]
        w(f"| Peak RAM, static + heap (B), offloaded at the mean heap | {c['offloaded']:,.0f} ({c['offloaded_pct_budget']:.1f}%) | {c['not_offloaded']:,.0f} ({c['not_offloaded_pct_budget']:.1f}%) | {c['reduction_pct']:.2f} |")
        w(f"| Peak RAM, offloaded at the upper tolerance limit of the heap (B) | {c['offloaded_at_utl']:,.0f} ({c['offloaded_utl_pct_budget']:.1f}%) | {c['not_offloaded']:,.0f} | {c['reduction_pct_at_utl']:.2f} |")
        w(f"\nThe on-device Web3 client alone: {cmp_['web3_alone_peak']:,} B = {cmp_['web3_alone_pct_budget']:.0f}% of the 50 KiB Class 2 RAM budget. "
          f"Its heap peak is {cmp_['heap_ratio_vs_updater_mean']:.1f}x the updater's mean heap peak and {cmp_['heap_ratio_vs_updater_utl']:.1f}x its upper limit.\n")
        w("Static figures (flash, static RAM) are from the SOP 4 evidence report (builds minus the Wi-Fi-only control). The peak-RAM rows take the larger heap, "
          "not the sum of the two heaps, i.e. they assume the two peaks do not coincide, which understates the not-offloaded total.\n")
    if ctx.get("n") or ctx.get("h"):
        from . import baselines
        L.append(baselines.render(ctx.get("n"), ctx.get("h")).rstrip(chr(10)))
    if ctx.get("confirm"):
        from . import baselines
        L.append(chr(10) + baselines.render_confirmation(ctx["confirm"]).rstrip(chr(10)))
    return "\n".join(L) + "\n"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def export(ctx: dict, out: Path, sop4: Path | None) -> list[Path]:
    """The tidy CSV files groupmates can open directly."""
    data = out / "data"
    written = []
    pairs = ctx["pairs"]
    cols = [c for c, _, _ in AB_METRICS]
    rows = []
    for p in pairs:
        row = {"pair": p["pair"], "trial": p["trial"]}
        for sc in "AB":
            for c in cols:
                row[f"{sc}_{c}"] = p[sc].get(c, "")
        rows.append(row)
    for row, p in zip(rows, pairs):
        for sc in "AB":
            row[f"{sc}_interrupted"] = ctx["interrupted"].get((sc, p["trial"]), "")
    write_csv(data / "ab_pairs.csv", ["pair", "trial"] + [f"{sc}_{c}" for sc in "AB" for c in cols] + ["A_interrupted", "B_interrupted"], rows)
    write_csv(data / "failures.csv", ["scenario", "trial", "cause", "reconstructed", "interrupted", "note"], ctx["fail"]["detail"])
    t3 = [r for r in ctx["t3_rows"] if not campaign.truthy(r["warmup"]) and r["status"] == "ok"]
    t3f = ["trial", "poll_ms", "sha_ms", "encap_ms", "gw_ram_mb", "gw_cpu_pct", "diff_ms", "to_dota_ms", "download_ms", "blocks"]
    write_csv(data / "table3_cycles.csv", t3f, [{k: r.get(k, "") for k in t3f} for r in t3])
    cde = [r for r in ctx["cde_rows"] if not campaign.truthy(r["warmup"])]
    cf = ["scenario", "trial", "status", "rejected", "delay_ms", "detect_ms", "note"]
    write_csv(data / "scenarios_cde_trials.csv", cf, [{k: r.get(k, "") for k in cf} for r in cde])
    written += [data / n for n in ("ab_pairs.csv", "failures.csv", "table3_cycles.csv", "scenarios_cde_trials.csv")]
    if ctx.get("n"):
        npairs = ctx["n"]["pairs"]
        ncols = [c for c, _, _ in AB_METRICS]
        nrows = []
        for p in npairs:
            row = {"pair": p["pair"], "trial": p["trial"]}
            for sc in "AN":
                for c in ncols:
                    row[f"{sc}_{c}"] = p[sc].get(c, "")
            nrows.append(row)
        write_csv(data / "baseline_n_pairs.csv", ["pair", "trial"] + [f"{sc}_{c}" for sc in "AN" for c in ncols], nrows)
        written.append(data / "baseline_n_pairs.csv")
    if ctx.get("h_data"):
        hrows = ctx["h_data"]["rows"]
        write_csv(data / "baseline_h_runs.csv", list(hrows[0].keys()), hrows)
        written.append(data / "baseline_h_runs.csv")
    if sop4 and ctx.get("web3"):
        wb = ctx["web3"]
        mem = wb["mem_runs"]
        rows = []
        for i, w in enumerate(wb["runs"]):
            m = mem[i] if i < len(mem) else {}
            rows.append({"run": w["run"], "tls_connect_ms": w["tls_connect_ms"], "request_ms": w["request_ms"], "keccak_us": w["keccak_us"],
                         "decode_us": w["decode_us"], "total_ms": round(w["tls_connect_ms"] + w["request_ms"] + (w["keccak_us"] + w["decode_us"]) / 1000, 3),
                         "free_heap_after": m.get("free", ""), "lowest_free_heap_so_far": m.get("min", "")})
        write_csv(sop4 / "web3_checks.csv", ["run", "tls_connect_ms", "request_ms", "keccak_us", "decode_us", "total_ms",
                                              "free_heap_after", "lowest_free_heap_so_far"], rows)
        hp = [{"pair": p["pair"], "trial": p["trial"], "A_heap_peak_used": p["A"].get("heap_peak_used", ""), "A_heap_min_free": p["A"].get("heap_min_free", ""),
               "B_heap_peak_used": p["B"].get("heap_peak_used", ""), "B_heap_min_free": p["B"].get("heap_min_free", "")} for p in pairs]
        write_csv(sop4 / "updater_heap_peak.csv", list(hp[0].keys()), hp)
        written += [sop4 / "web3_checks.csv", sop4 / "updater_heap_peak.csv"]
    return written


def write_manifest(out: Path, extra: list[Path]) -> Path:
    files = sorted({p for p in (list((out / "data").glob("*.csv")) + list((out / "figures").glob("*.png")) + [out / "STATISTICS.md"] + extra) if p.exists()})
    lines = [f"{sha256(p)}  {p.relative_to(out.parent) if out.parent in p.parents else p.name}".replace("\\", "/") for p in files]
    path = out / "data" / "MANIFEST.sha256"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def analyse(ab_run: Path, t3_run: Path, cde_csv: Path, web3_run: Path | None = None, n_run: Path | None = None,
            h_run: Path | None = None, confirm_run: Path | None = None) -> dict:
    ab_csv, t3_csv = Path(ab_run) / "campaign" / "trials.csv", Path(t3_run) / "campaign" / "table3.csv"
    rows, t3_rows, cde_rows = load_rows(ab_csv), load_rows(t3_csv), load_rows(Path(cde_csv))
    pairs = select_pairs(rows)
    ctx = {"inputs": [("Scenarios A and B (Table 2)", ab_csv), ("Table 3 run", t3_csv), ("Scenarios C, D, E (Table 4)", Path(cde_csv))],
           "rows": rows, "t3_rows": t3_rows, "cde_rows": cde_rows, "pairs": pairs, "paired": paired_table(pairs),
           "root": root_cause(pairs), "fail": failures(rows, Path(ab_run) / "raw"), "after": after_failure_effect(rows),
           "sens": sensitivity(rows, pairs), "t3": table3_stats(t3_rows), "cde": scenario_stats(cde_rows)}
    if n_run or h_run:
        from . import baselines
        if n_run:
            n_csv = Path(n_run) / "campaign" / "trials.csv"
            ctx["inputs"].append(("Scenario N, naked CoAP delta (supplementary)", n_csv))
            ctx["n_rows"] = load_rows(n_csv)
            ctx["n"] = baselines.n_analysis(ctx["n_rows"], Path(n_run) / "raw")
        if h_run:
            ctx["inputs"].append(("Scenario H, HTTPS full binary (supplementary)", Path(h_run) / "campaign" / "https_runs.csv"))
            ctx["h_data"] = baselines.load_h(Path(h_run))
            ctx["h"] = baselines.h_analysis(ctx["h_data"], pairs)
    if confirm_run:
        from . import baselines
        c_csv = Path(confirm_run) / "campaign" / "trials.csv"
        ctx["inputs"].append(("Confirmation run, A and B on the fixed harness", c_csv))
        ctx["confirm"] = baselines.confirmation(load_rows(c_csv), Path(confirm_run) / "raw", pairs)
    flags = interrupted_map(rows, Path(ab_run) / "raw")
    ctx["interrupted"] = flags
    ctx["by_start"] = outcomes_by_start(rows, flags)
    ctx["interrupt_sens"] = interruption_sensitivity(pairs, flags)
    if web3_run:
        log = Path(web3_run) / "raw" / "serial-web3_baseline.log"
        ctx["inputs"].append(("On-device Web3 client (SOP 4)", log))
        ctx["web3"] = web3_stats(log.read_text(encoding="utf-8", errors="replace"))
        heap = next(r for r in ctx["paired"] if r["metric"] == "heap_peak_used")
        ctx["compare"] = sop4_comparison(heap["mean_A"], heap["utl_A"], ctx["web3"]["heap"]["peak_bytes"])
    return ctx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ab", required=True)
    ap.add_argument("--t3", required=True)
    ap.add_argument("--cde", required=True)
    ap.add_argument("--web3")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sop4")
    ap.add_argument("--n", help="the A/N campaign folder (naked-CoAP baseline, supplementary)")
    ap.add_argument("--h", help="the HTTPS baseline run folder (supplementary)")
    ap.add_argument("--confirm", help="the A/B confirmation run folder (fixed harness)")
    ap.add_argument("--tables", action="store_true", help="also write TABLES-1-AND-4.md and TABLES-2-AND-3.md (the approved tables, filled)")
    ap.add_argument("--base", help="v1.0 image for Table 1 (default: found like SOP 1 does)")
    ap.add_argument("--target", help="v1.1 image for Table 1")
    ap.add_argument("--draft", help="refresh the Appendix of this chapter draft from the table documents (needs --tables)")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    ctx = analyse(Path(a.ab).resolve(), Path(a.t3).resolve(), Path(a.cde).resolve(), Path(a.web3).resolve() if a.web3 else None,
                  Path(a.n).resolve() if a.n else None, Path(a.h).resolve() if a.h else None,
                  Path(a.confirm).resolve() if a.confirm else None)
    (out).mkdir(parents=True, exist_ok=True)
    (out / "STATISTICS.md").write_text(render(ctx), encoding="utf-8")
    extra = export(ctx, out, Path(a.sop4).resolve() if a.sop4 else None)
    man = write_manifest(out, [e for e in extra if out not in e.parents])
    print(f"wrote {out / 'STATISTICS.md'}, {len(extra)} CSV files and {man.name}")
    if a.tables:
        write_table_documents(ctx, out, a.base, a.target, Path(a.draft).resolve() if a.draft else None)
        write_manifest(out, [e for e in extra if out not in e.parents])
    return 0


def table_documents(ctx: dict, base: str | None = None, target: str | None = None) -> tuple[str, str, str]:
    """The two combined table documents (Tables 1 and 4, Tables 2 and 3) and the code revision they were rendered at."""
    import subprocess

    import bsdiff4

    from . import sop1, table_docs

    pair = sop1.find_real_pair(None, base, target)
    if pair is None:
        raise SystemExit("the v1.0 and v1.1 firmware images were not found: pass --base and --target")
    patch = bsdiff4.diff(pair[0].read_bytes(), pair[1].read_bytes())
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).resolve().parent).stdout.strip() or "unknown"
    ab_csv, t3_csv, cde_csv = (Path(p) for _, p in ctx["inputs"][:3])
    doc14 = table_docs.table1_and_4_doc(base=pair[0], target=pair[1], patch=patch, cde_csv=cde_csv, cde_rows=ctx["cde_rows"], head=head)
    doc23 = table_docs.table2_and_3_doc(ab_csv=ab_csv, t3_csv=t3_csv, ab_rows=ctx["rows"], t3_rows=ctx["t3_rows"], head=head)
    return doc14, doc23, head


def refresh_draft_appendix(draft: Path, doc14: str, doc23: str) -> None:
    """Replace the Appendix of the chapter draft with one cut from the table documents (line endings are kept)."""
    from . import table_docs

    raw = draft.read_bytes().decode("utf-8")
    crlf, lf = chr(13) + chr(10), chr(10)
    had_crlf = crlf in raw
    new = table_docs.replace_appendix(raw.replace(crlf, lf), table_docs.appendix_from_docs(doc14, doc23))
    draft.write_bytes((new.replace(lf, crlf) if had_crlf else new).encode("utf-8"))


def write_table_documents(ctx: dict, out: Path, base: str | None, target: str | None, draft: Path | None) -> None:
    """TABLES-1-AND-4.md and TABLES-2-AND-3.md (and, with `draft`, a refreshed Appendix in the chapter draft)."""
    from . import table_docs

    doc14, doc23, head = table_documents(ctx, base, target)
    (out / "TABLES-1-AND-4.md").write_text(doc14, encoding="utf-8")
    (out / "TABLES-2-AND-3.md").write_text(doc23, encoding="utf-8")
    print(f"wrote {out / 'TABLES-1-AND-4.md'} and {out / 'TABLES-2-AND-3.md'}")
    if ctx.get("n") and ctx.get("h"):
        n_csv = next(Path(p) for name, p in ctx["inputs"] if name.startswith("Scenario N"))
        h_csv = next(Path(p) for name, p in ctx["inputs"] if name.startswith("Scenario H"))
        (out / "BASELINES.md").write_text(table_docs.baselines_doc(ctx=ctx, n_csv=n_csv, h_dir=h_csv.parents[1], head=head), encoding="utf-8")
        print(f"wrote {out / 'BASELINES.md'}")
    if draft:
        refresh_draft_appendix(draft, doc14, doc23)
        print(f"refreshed the Appendix of {draft}")


if __name__ == "__main__":
    raise SystemExit(main())
