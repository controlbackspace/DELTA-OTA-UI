"""Figures for Chapter 4, drawn from the same recorded data as STATISTICS.md.

    python -m sop.figures --ab <campaign-AB> --t3 <campaign-T3> --cde <trials.csv> --web3 <on-device-web3> --out <experiment-paper-tables>

matplotlib is the only third-party package and is optional for the rest of the toolkit (the gateway virtual environment
does not have it); run this module with a Python that has it. Five PNG files are written to <out>/figures.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import chapter4 as c4, inference as inf

A_COLOR, B_COLOR, ACCENT, GREY = "#0072B2", "#D55E00", "#009E73", "#6b6b6b"      # colour-blind-safe palette


def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:                                    # pragma: no cover - depends on the environment
        raise SystemExit("matplotlib is required for the figures (pip install matplotlib): " + str(e))
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
                         "axes.titlesize": 11, "figure.dpi": 100, "savefig.bbox": "tight"})
    return plt


def _test_text(r: dict) -> str:
    """'t = -29.5, p = 5e-37', or a note when the differences have no variance (no test)."""
    return "no variance, no test" if r.get("t") is None else f"t = {r['t']:.1f}, p = {r['p']:.0e}"


def _row(ctx: dict, metric: str) -> dict:
    return next(r for r in ctx["paired"] if r["metric"] == metric)


def fig_payload(ctx: dict, path: Path) -> Path:
    plt = _plt()
    full, patch = 288_880, 22_497                       # Table 1: the static benchmark of the version pair
    wire = _row(ctx, "wire_bytes")
    fig, ax = plt.subplots(1, 2, figsize=(10, 4.2))
    ax[0].bar(["Full binary\n(v1.1 image)", "Delta patch\n(bsdiff4)"], [full / 1024, patch / 1024], color=[B_COLOR, A_COLOR], width=0.55)
    for x, v in enumerate((full, patch)):
        ax[0].text(x, v / 1024 + 5, f"{v:,} B", ha="center")
    ax[0].set_ylabel("Size (KiB)")
    ax[0].set_title(f"Table 1: patch is {inf.relative_reduction_pct(full, patch):.2f}% smaller")
    ax[1].bar(["Full binary\n(B)", "Delta-OTA\n(A)"], [wire["mean_B"] / 1024, wire["mean_A"] / 1024],
              yerr=[wire["sd_B"] / 1024, wire["sd_A"] / 1024], color=[B_COLOR, A_COLOR], width=0.55, capsize=6)
    for x, v in enumerate((wire["mean_B"], wire["mean_A"])):
        ax[1].text(x, v / 1024 + wire["sd_B"] / 1024 + 4, f"{v:,.0f} B", ha="center")
    ax[1].set_ylabel("Bytes on the wire per update (KiB, mean ± SD)")
    ax[1].set_title(f"On the wire: {wire['reduction_pct']:.2f}% fewer bytes ({_test_text(wire)})")
    fig.suptitle("SOP 1: delta differencing shrinks both the stored payload and the traffic", y=1.02, fontweight="bold")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def fig_ttc(ctx: dict, path: Path) -> Path:
    plt = _plt()
    r = _row(ctx, "ttc_ms")
    a, b = c4.column(ctx["pairs"], "A", "ttc_ms"), c4.column(ctx["pairs"], "B", "ttc_ms")
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4.6), gridspec_kw={"width_ratios": [1.5, 1]})
    for x, y in zip(a, b):
        ax[0].plot([0, 1], [x / 1000, y / 1000], color=GREY, alpha=0.35, lw=0.8)
    ax[0].scatter([0] * len(a), [v / 1000 for v in a], color=A_COLOR, s=18, zorder=3)
    ax[0].scatter([1] * len(b), [v / 1000 for v in b], color=B_COLOR, s=18, zorder=3)
    ax[0].set_xticks([0, 1], ["Delta-OTA (A)", "Full binary (B)"])
    ax[0].set_ylabel("Time to completion (s)")
    ax[0].set_title("Each line is one matched pair: A was faster in all 60")
    ax[1].bar(["A", "B"], [r["mean_A"] / 1000, r["mean_B"] / 1000], yerr=[r["sd_A"] / 1000, r["sd_B"] / 1000],
              color=[A_COLOR, B_COLOR], width=0.55, capsize=6)
    for x, (m, u) in enumerate(((r["mean_A"], r["utl_A"]), (r["mean_B"], r["utl_B"]))):
        ax[1].plot([x - 0.3, x + 0.3], [u / 1000] * 2, color="black", lw=1.6, ls="--")
        ax[1].text(x, u / 1000 + 1.2, f"mean {m / 1000:.2f} s" + chr(10) + f"99%/95% limit {u / 1000:.1f} s", ha="center", fontsize=9)
    ax[1].set_ylabel("Mean ± SD (s)")
    ax[1].set_title(f"{r['reduction_pct']:.2f}% shorter ({_test_text(r)})")
    ax[1].set_ylim(0, r["utl_B"] / 1000 * 1.25)
    fig.suptitle("SOP 5: time to completion, Delta-OTA against full binary (Wireshark TTC, 60 pairs)", y=1.02, fontweight="bold")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def fig_ttc_spread(ctx: dict, path: Path) -> Path:
    plt = _plt()
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4.2))
    for axis, sc, color, name in ((ax[0], "A", A_COLOR, "Delta-OTA (A)"), (ax[1], "B", B_COLOR, "Full binary (B)")):
        ttc, rt = c4.column(ctx["pairs"], sc, "ttc_ms"), c4.column(ctx["pairs"], sc, "retransmissions")
        clean = [t / 1000 for t, k in zip(ttc, rt) if k == 0]
        repeat = [t / 1000 for t, k in zip(ttc, rt) if k > 0]
        lo, hi = min(ttc) / 1000, max(ttc) / 1000
        bins = [lo + (hi - lo) * i / 20 for i in range(21)]
        axis.hist([clean, repeat], bins=bins, stacked=True, color=[color, GREY], label=[f"no repeated request ({len(clean)})", f"with repeats ({len(repeat)})"])
        axis.set_xlabel("Time to completion (s)")
        axis.set_ylabel("Cycles")
        axis.set_title(name)
        axis.legend(frameon=False)
    fig.suptitle("The spread comes from repeated requests: cycles with none are almost identical", y=1.02, fontweight="bold")
    rc = ctx["root"]
    fig.text(0.5, -0.04, f"Cycles without a repeated request: A {rc['A']['mean_clean']:,.0f} ms (SD {rc['A']['sd_clean']:.0f}), "
             f"B {rc['B']['mean_clean']:,.0f} ms (SD {rc['B']['sd_clean']:.0f}).", ha="center")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def fig_retransmissions(ctx: dict, path: Path) -> Path:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    for sc, color, name in (("A", A_COLOR, "Delta-OTA (A)"), ("B", B_COLOR, "Full binary (B)")):
        rt, ttc = c4.column(ctx["pairs"], sc, "retransmissions"), [v / 1000 for v in c4.column(ctx["pairs"], sc, "ttc_ms")]
        ax.scatter(rt, ttc, color=color, s=22, alpha=0.8, label=f"{name}: r = {ctx['root'][sc]['r']:.3f}")
        slope, mean_rt, mean_t = inf.linear_slope(rt, ttc), inf.mean(rt), inf.mean(ttc)
        xs = [0, max(rt)]
        ax.plot(xs, [mean_t + slope * (x - mean_rt) for x in xs], color=color, lw=1.2)
    ax.set_xlabel("Repeated block requests in the cycle")
    ax.set_ylabel("Time to completion (s)")
    ax.set_title(f"Each repeated request adds about {ctx['root']['A']['slope_ms_per_retransmission']:.0f} ms (the 200 ms re-request timer)")
    ax.legend(frameon=False)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def fig_sop4(ctx: dict, path: Path) -> Path:
    plt = _plt()
    wb, cmp_ = ctx["web3"], ctx["compare"]
    poll = next(r for r in ctx["t3"] if r["label"].startswith("Web3 smart-contract polling"))
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4.6))
    vals = [poll["mean"], wb["total_ms"]["mean"]]
    ax[0].bar(["Gateway poll\n(Raspberry Pi, HTTP)", "One ledger check\non the ESP32 (TLS)"], vals, color=[A_COLOR, B_COLOR], width=0.55)
    ax[0].set_yscale("log")
    for x, v in enumerate(vals):
        ax[0].text(x, v * 1.12, f"{v:,.1f} ms", ha="center")
    ax[0].set_ylabel("Time per ledger check (ms, log scale)")
    ax[0].set_title(f"{vals[1] / vals[0]:.0f}x longer on the device ({wb['tls_share']:.0%} is the TLS handshake)")
    peak = cmp_["peak_ram"]
    static_off, static_non = 29_400, 29_400 + 3_244
    heap_off, heap_non = peak["offloaded"] - static_off, peak["not_offloaded"] - static_non
    labels = ["Offloaded\n(updater only)", "Not offloaded\n(updater + Web3)"]
    ax[1].bar(labels, [static_off / 1024, static_non / 1024], color=A_COLOR, width=0.55, label="static RAM")
    ax[1].bar(labels, [heap_off / 1024, heap_non / 1024], bottom=[static_off / 1024, static_non / 1024], color=ACCENT, width=0.55, label="peak heap")
    ax[1].axhline(50, color="black", ls="--", lw=1.3)
    ax[1].text(-0.45, 51, "Class 2 budget 50 KiB", ha="left", fontsize=9)
    for x, v in enumerate((peak["offloaded"], peak["not_offloaded"])):
        ax[1].text(x, v / 1024 + 1.5, f"{v / 1024:.1f} KiB\n({v / 51_200:.0%})", ha="center")
    ax[1].set_ylabel("Peak RAM (KiB)")
    ax[1].set_ylim(0, peak["not_offloaded"] / 1024 * 1.25)
    ax[1].set_title(f"Offloading cuts peak RAM by {peak['reduction_pct']:.0f}%")
    ax[1].legend(frameon=False, loc="upper left")
    fig.suptitle("SOP 4: what offloading Web3 logic to the gateway saves on the device", y=1.02, fontweight="bold")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def fig_https(ctx: dict, path: Path) -> Path:
    """Baseline H (HTTPS full binary) against the proposed architecture: bytes on the wire and peak RAM against the Class 2 budget."""
    plt = _plt()
    h = ctx["h"]
    e3, e4 = h["eq3"], h["eq4"]
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1, 1.25, 1]})
    names = ["H: HTTPS\nfull binary", "A: proposed\ndelta"]
    ax[0].bar(names, [e3["h_mean"] / 1024, e3["a_mean"] / 1024], color=[B_COLOR, A_COLOR], width=0.55)
    for x, v in enumerate((e3["h_mean"], e3["a_mean"])):
        ax[0].text(x, v / 1024 + 6, f"{v:,.0f} B", ha="center")
    ax[0].set_ylabel("Bytes on the wire per update (KiB)")
    ax[0].set_title(f"Eq. 3: {e3['reduction_pct']:.1f}% fewer bytes")
    a_static, h_static = e4["a_static"], e4["h_static"]
    labels = ["H: HTTPS\nfull binary", "A: proposed\n(mean heap)", "A: proposed\n(max heap)"]
    statics = [h_static, a_static, a_static]
    heaps = [e4["h_heap_max"], e4["a_heap_mean"], e4["a_heap_max"]]
    ax[1].bar(labels, [v / 1024 for v in statics], color=A_COLOR, width=0.55, label="static RAM")
    ax[1].bar(labels, [v / 1024 for v in heaps], bottom=[v / 1024 for v in statics], color=ACCENT, width=0.55, label="peak heap")
    ax[1].axhline(50, color="black", ls="--", lw=1.3)
    ax[1].text(2.45, 51.5, "Class 2 budget 50 KiB", ha="right", fontsize=9)
    for x, (sv, hv) in enumerate(zip(statics, heaps)):
        ax[1].text(x, (sv + hv) / 1024 + 1.5, f"{(sv + hv) / 1024:.1f} KiB ({(sv + hv) / 51200:.0%})", ha="center", fontsize=9)
    ax[1].set_ylabel("Peak RAM (KiB)")
    ax[1].set_ylim(0, (statics[0] + heaps[0]) / 1024 * 1.2)
    ax[1].set_title(f"Eq. 4: {e4['reduction_pct_mean']:.0f}% (A mean) to {e4['reduction_pct_max']:.0f}% (A max) less")
    ax[1].legend(frameon=False, loc="upper right")
    t = h["ttc"]
    ax[2].bar(["H: HTTPS", "A: proposed"], [t["h"]["mean"] / 1000, t["a"]["mean"] / 1000], yerr=[t["h"]["sd"] / 1000, t["a"]["sd"] / 1000],
              color=[B_COLOR, A_COLOR], width=0.55, capsize=6)
    for x, v in enumerate((t["h"]["mean"], t["a"]["mean"])):
        ax[2].text(x, v / 1000 / 2, f"{v / 1000:.2f} s", ha="center", color="white", fontweight="bold")
    ax[2].set_ylabel("Time to completion (s, mean ± SD)")
    ax[2].set_title(f"Time: A is {abs(t['reduction_pct_a_vs_h']):.0f}% {'longer' if t['reduction_pct_a_vs_h'] < 0 else 'shorter'} than H")
    fig.suptitle("Chapter 3 Baseline A: the full binary over HTTPS (H) against the proposed architecture (A)", y=1.03, fontweight="bold")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def fig_security_tax(ctx: dict, path: Path) -> Path:
    """Baseline N (naked CoAP delta) against A: what the security costs, per update."""
    plt = _plt()
    n = ctx["n"]
    tab = {r["metric"]: r for r in n["table"]}
    fig, ax = plt.subplots(1, 3, figsize=(12.5, 4.4))
    panels = (("ttc_ms", "Time to completion (s)", 1000.0, 2), ("decrypt_recon_ms", "Decryption + reconstruction (s)", 1000.0, 3),
              ("wire_bytes", "Bytes on the wire (KiB)", 1024.0, 2))
    for axis, (metric, label, div, dec) in zip(ax, panels):
        r = tab[metric]
        axis.bar(["A: secured", "N: naked"], [r["mean_A"] / div, r["mean_N"] / div], yerr=[r["sd_A"] / div, r["sd_N"] / div],
                 color=[A_COLOR, GREY], width=0.55, capsize=6)
        lo = min(r["mean_A"], r["mean_N"]) / div
        axis.set_ylim(0, max(r["mean_A"] + r["sd_A"], r["mean_N"] + r["sd_N"]) / div * 1.22)
        txt = f"A - N = {r['mean_diff'] / div:+.{dec}f}"
        if not r["degenerate"]:
            txt += f"  (p = {r['p']:.0e})" if r["p"] < 0.001 else f"  (p = {r['p']:.2f})"
        axis.text(0.5, 0.97, txt, transform=axis.transAxes, ha="center", va="top", fontsize=9.5)
        axis.set_ylabel(label)
    fig.suptitle(f"Chapter 3 Baseline B: the security tax, secured delta (A) minus naked CoAP delta (N), {n['n_pairs']} matched pairs", y=1.02, fontweight="bold")
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def make_all(ctx: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = [fig_payload(ctx, out_dir / "fig1_payload.png"), fig_ttc(ctx, out_dir / "fig2_time_to_completion.png"),
            fig_ttc_spread(ctx, out_dir / "fig3_completion_time_spread.png"),
            fig_retransmissions(ctx, out_dir / "fig4_time_vs_repeated_requests.png")]
    if ctx.get("web3"):
        made.append(fig_sop4(ctx, out_dir / "fig5_ledger_check_and_ram.png"))
    if ctx.get("h"):
        made.append(fig_https(ctx, out_dir / "fig6_https_baseline.png"))
    if ctx.get("n"):
        made.append(fig_security_tax(ctx, out_dir / "fig7_security_tax.png"))
    return made


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("ab", "t3", "cde", "out"):
        ap.add_argument(f"--{name}", required=True)
    ap.add_argument("--web3")
    ap.add_argument("--n")
    ap.add_argument("--h")
    a = ap.parse_args(argv)
    ctx = c4.analyse(Path(a.ab).resolve(), Path(a.t3).resolve(), Path(a.cde).resolve(), Path(a.web3).resolve() if a.web3 else None,
                      Path(a.n).resolve() if a.n else None, Path(a.h).resolve() if a.h else None)
    out = Path(a.out).resolve() / "figures"
    made = make_all(ctx, out)
    print(f"wrote {len(made)} figures to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
