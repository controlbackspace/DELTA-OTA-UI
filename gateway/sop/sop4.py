"""SOP 4 - what does offloading the Web3 logic to the Edge Gateway save the device?

Compared on the same ESP32 framework base (Arduino + Wi-Fi):
  control        Wi-Fi only                                   (shared cost)
  factory        our updater: AES-CCM blocks + DOTA decoder   (what the device runs)
  web3_baseline  control + HTTPS (mbedTLS) + keccak256 + JSON-RPC eth_call +
                 ABI decode: a LOWER BOUND of an on-device Web3 client
                 (read-only: no signing, no JSON library, no certificate check)

Static part [offline, needs the PlatformIO toolchain]: build all three, compare
flash and static RAM, attribute the extra flash to link-map groups, and put the
numbers against the Class 2 budget (50 KiB RAM / 250 KiB flash).

Hardware part [hw]: static RAM says little about TLS, whose cost is dynamic heap.
The runner can flash web3_baseline, capture its [MEM]/[Web3] lines, and RESTORE
the factory updater afterwards. Flashing replaces the updater, so it only runs
with --allow-flash. Heap and timing numbers exist only when that part ran (or a
capture is supplied); otherwise the report says so.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from . import footprint as fp
from .runlog import REPO_ROOT, RunContext, StepResult, Table
from .serial_capture import SerialCapture
from .serial_parse import parse_log, peak_heap
from .stats import fmt_ci, summarize

ENVS = ("factory", "web3_control", "web3_baseline")
CPU_MHZ = 240                       # ESP32 default; cycles = ms * 1000 * MHz (modelled)
REFERENCE_STACK = REPO_ROOT / "gateway" / "secureota" / "class2" / "reference-stack.json"


def _kb(n: int) -> str:
    return f"{n / 1024:.1f} KB"


def _pct(n: int, budget: int) -> str:
    return f"{n / budget:.1%}"


# ------------------------------------------------------------------ hardware
def hw_session(ctx: RunContext, project: Path, pio: str, port: str, build_flags: str, seconds: int,
               run=subprocess.run, capture_cls=SerialCapture) -> dict:
    """Flash web3_baseline, capture it, and always restore the factory updater.
    `run` and `capture_cls` are injectable so the sequence is testable without a board."""
    raw = ctx.sub("raw")
    flashed = False
    result: dict = {"port": port, "restored": None, "log": None}
    env = dict(os.environ)
    if build_flags:
        env["PLATFORMIO_BUILD_FLAGS"] = build_flags
    try:
        up = run([pio, "run", "-e", "web3_baseline", "-t", "upload", "--upload-port", port],
                 cwd=project, env=env, capture_output=True, text=True, timeout=900)
        flashed = True                                   # something may have been written
        (raw / "pio-upload-web3_baseline.log").write_text((up.stdout or "") + (up.stderr or ""), encoding="utf-8")
        if up.returncode != 0:
            raise RuntimeError("upload of web3_baseline failed - see raw/pio-upload-web3_baseline.log")
        cap = capture_cls(port, log_path=raw / "serial-web3_baseline.log").open()
        try:
            cap.reset_board()
            text = cap.capture(seconds, until=r"\[SOP4\] done")
        finally:
            cap.close()
        result["log"] = "raw/serial-web3_baseline.log"
        result["parsed"] = parse_log(text)
        return result
    finally:
        if flashed:                                      # never leave the board without its updater
            restore = [os.environ.get("COMSPEC", "cmd"), "/c", str(project / "tools" / "flash_device.bat"), "factory", port]
            try:
                r = run(restore, cwd=project, env=dict(os.environ, NOPAUSE="1"), capture_output=True, text=True, timeout=900)
                (raw / "restore-factory.log").write_text((r.stdout or "") + (r.stderr or ""), encoding="utf-8")
                result["restored"] = r.returncode == 0
            except (OSError, subprocess.SubprocessError) as e:    # do not mask the original error
                result["restored"] = False
                (raw / "restore-factory.log").write_text(f"restore raised: {e}\n", encoding="utf-8")


# ---------------------------------------------------------------------- step
def run(ctx: RunContext, firmware_dir: str | None = None, serial: str | None = None, allow_flash: bool = False,
        web3_host: str | None = None, web3_port: int = 443, web3_contract: str | None = None,
        web3_version: str = "v1.1", factory_log: str | None = None, hw_dry_run: bool = False,
        capture_seconds: int = 90, hw_runner=subprocess.run, capture_cls=SerialCapture) -> StepResult:
    res = StepResult(sop="SOP4", title="Web3 offloading: device footprint", mode="offline")
    project, pio = fp.find_project(firmware_dir), fp.find_pio()
    if project is None or pio is None:
        res.status = "skipped"
        res.reason = "firmware project not found" if project is None else "PlatformIO (pio) not found"
        return res

    # ---- static: build the three environments ---------------------------------
    builds: dict[str, fp.BuildResult] = {}
    for env in ENVS:
        builds[env] = fp.build_env(project, env, ctx.sub("raw") / f"pio-{env}.log", pio=pio)
    failed = [b for b in builds.values() if not b.ok]
    if failed:
        res.status = "failed"
        res.reason = "; ".join(f"{b.env}: {b.error}" for b in failed)
        return res
    c, f, w = builds["web3_control"], builds["factory"], builds["web3_baseline"]

    data = {e: {"flash": b.flash_used, "ram": b.ram_used} for e, b in builds.items()}
    inc = {
        "updater": {"flash": f.flash_used - c.flash_used, "ram": f.ram_used - c.ram_used},
        "web3": {"flash": w.flash_used - c.flash_used, "ram": w.ram_used - c.ram_used},
    }
    res.data = {"builds": data, "incremental": inc}
    res.files.append(ctx.write_json("sop4/footprint.json", {"builds": data, "incremental": inc}))
    res.files += [f"raw/pio-{e}.log" for e in ENVS]

    res.tables.append(Table(
        "Whole-image footprint per build (PlatformIO, ESP32 + Arduino)",
        ["Build", "Flash used", "Static RAM used", "What it is"],
        [["web3_control", f"{c.flash_used:,} B", f"{c.ram_used:,} B", "Wi-Fi only: the framework cost every build shares"],
         ["factory (Delta-OTA updater)", f"{f.flash_used:,} B", f"{f.ram_used:,} B", "AES-CCM block receiver + DOTA decoder + partition handling"],
         ["web3_baseline", f"{w.flash_used:,} B", f"{w.ram_used:,} B", "control + HTTPS + keccak256 + eth_call + ABI decode"]],
        "measured",
        note="These are ESP32 images, so the absolute sizes are not Class 2 sizes: the framework alone is "
             f"{_kb(c.flash_used)} of flash. The meaningful quantity is the increment over the shared control.",
    ))

    inc_rows = []
    for label, v in (("Delta-OTA updater (offloaded design)", inc["updater"]),
                     ("On-device Web3, lower bound (no offloading)", inc["web3"])):
        inc_rows.append([label, f"{v['flash']:+,} B ({_kb(abs(v['flash']))})", _pct(v["flash"], fp.CLASS2_FLASH_BYTES),
                         f"{v['ram']:+,} B", _pct(v["ram"], fp.CLASS2_RAM_BYTES)])
    res.tables.append(Table(
        "Cost over the Wi-Fi-only control, against the Class 2 budget (250 KiB flash / 50 KiB RAM)",
        ["Design", "Added flash", "% of Class 2 flash", "Added static RAM", "% of Class 2 RAM"],
        inc_rows, "measured",
        note="Static RAM only. TLS buffers and handshake state live on the heap: see the hardware table below "
             "(present only when the hardware part ran).",
    ))

    ga, gb = fp.map_groups(c.build_dir), fp.map_groups(w.build_dir)
    if ga and gb:
        relabel = {"mbedTLS (CCM+SHA kept)": "mbedTLS (the TLS client stack here)"}
        rows = [[relabel.get(g, g), f"{df:+,}", f"{dr:+,}"] for g, df, dr in fp.group_delta(ga, gb)]
        res.tables.append(Table("Where the on-device Web3 flash goes (link-map groups, baseline − control)",
                                ["Group", "Δ flash (B)", "Δ static RAM (B)"], rows, "measured"))

    eng = None
    try:
        eng = fp.engine_symbols(f.build_dir)
    except Exception as e:                                # nm missing / unreadable map: report, don't guess
        res.notes.append(f"Engine symbol attribution unavailable: {e}")
    if eng:
        res.tables.append(Table(
            "Delta-OTA engine alone (symbol-attributed, factory build)", ["Item", "Size"],
            [["Engine code (flash)", f"{eng['flash']:,} B across {eng['symbols']} symbols"],
             ["Engine static RAM", f"{eng['ram']:,} B"]], "measured",
            note="DeltaOTAEngine::* and the otaEngine instance only (class2/measure_engine.py); shared libraries "
                 "such as mbedTLS CCM are not in this row, so compare designs with the increment table above."))
    try:
        ref = json.loads(REFERENCE_STACK.read_text(encoding="utf-8"))
        res.tables.append(Table(
            "Class 2 reference stack (cited)", ["Component", "Flash (B)", "RAM (B)", "Source"],
            [[r["component"], f"{r['flash_bytes']:,}", f"{r['ram_bytes']:,}", r["source"]] for r in ref["rows"]], "cited"))
        if any("REPLACE" in r["source"] for r in ref["rows"]):
            res.notes.append("The cited reference-stack row is still a placeholder (class2/reference-stack.json): "
                             "replace it with the exact Zephyr/Contiki figures before quoting it.")
    except (OSError, ValueError, KeyError):
        pass

    wf, uf = inc["web3"]["flash"], inc["updater"]["flash"]
    res.claims.append(
        f"[measured] On the same ESP32 + Wi-Fi base, the lowest-possible on-device Web3 client (HTTPS, Keccak-256, "
        f"eth_call, ABI decode; read-only) adds {wf:,} B of flash ({_pct(wf, fp.CLASS2_FLASH_BYTES)} of a 250 KiB "
        f"Class 2 flash budget by itself) and {inc['web3']['ram']:,} B of static RAM, before any heap for TLS; the "
        f"whole Delta-OTA updater adds {uf:,} B of flash"
        + (f" - the Web3 client needs {wf / uf:.1f}x that." if uf > 0 else ".")
    )

    # What dominates the updater's static RAM (the engine-only row cannot see it).
    try:
        top = fp.top_ram_symbols(f.build_dir)
    except Exception as e:
        top = None
        res.notes.append(f"Largest-symbol table unavailable: {e}")
    if top:
        res.tables.append(Table(
            "Largest static-RAM symbols in the Delta-OTA updater (factory build)", ["Symbol", "Size (B)", "% of Class 2 RAM"],
            [[name, f"{size:,}", _pct(size, fp.CLASS2_RAM_BYTES)] for name, size in top], "measured"))
        biggest = top[0]
        if biggest[1] >= 0.5 * fp.CLASS2_RAM_BYTES:
            res.claims.append(
                f"[measured, FINDING] The updater's static RAM is dominated by `{biggest[0]}` ({biggest[1]:,} B, "
                f"{_pct(biggest[1], fp.CLASS2_RAM_BYTES)} of the 50 KiB Class 2 RAM budget on its own) - the DOTA decoder "
                f"and its inflate dictionary. The updater adds {inc['updater']['ram']:,} B of static RAM in total "
                f"({_pct(inc['updater']['ram'], fp.CLASS2_RAM_BYTES)} of the budget). The earlier engine-only figure "
                f"({eng['ram']:,} B) counts only DeltaOTAEngine symbols and excludes this decoder, so it must not be "
                "quoted as the engine's total RAM." if eng else
                f"[measured, FINDING] The updater's static RAM is dominated by `{biggest[0]}` ({biggest[1]:,} B), "
                f"{_pct(biggest[1], fp.CLASS2_RAM_BYTES)} of the 50 KiB Class 2 RAM budget on its own."
            )
            res.notes.append(
                "Possible reduction (not done here): compress the DOTA stream with a smaller deflate window on the gateway "
                "and shrink the decoder's circular dictionary to match; the dictionary is the bulk of this symbol.")

    # ---- hardware: heap and timing ----------------------------------------------
    hw_parsed = None
    flags = " ".join(filter(None, [
        f'-DWEB3_RPC_HOST=\\"{web3_host}\\"' if web3_host else "", f"-DWEB3_RPC_PORT={web3_port}",
        f'-DWEB3_CONTRACT=\\"{web3_contract}\\"' if web3_contract else "", f'-DWEB3_VERSION_TAG=\\"{web3_version}\\"']))
    if serial and allow_flash and not hw_dry_run:
        try:
            hw = hw_session(ctx, project, pio, serial, flags, capture_seconds, run=hw_runner, capture_cls=capture_cls)
            hw_parsed = hw.get("parsed")
            res.files.append(hw["log"])
            if hw["restored"]:
                res.notes.append("Factory updater restored on the device after the measurement.")
            else:
                res.notes.append("WARNING: restoring the factory updater did not report success - run "
                                 f"`tools\\flash_device.bat factory {serial}` before using the board (raw/restore-factory.log).")
        except Exception as e:
            res.notes.append(f"SKIPPED - hardware part failed: {e}. The factory updater restore was attempted; "
                             f"if the board does not boot the updater run `tools\\flash_device.bat factory {serial}`.")
    elif serial and hw_dry_run:
        res.notes.append("Hardware dry run - nothing was flashed. Plan: pio run -e web3_baseline -t upload --upload-port "
                         f"{serial}; capture {capture_seconds} s; restore with tools\\flash_device.bat factory {serial}.")
    elif serial:
        res.notes.append("SKIPPED - hardware part: --allow-flash was not given (flashing replaces the factory updater "
                         "until it is restored).")
    else:
        res.notes.append("SKIPPED - hardware part: no --serial port. Heap and timing of the on-device Web3 client are "
                         "NOT reported; only static sizes above.")

    if hw_parsed:
        _hardware_tables(res, hw_parsed)
    if factory_log:
        try:
            lp = parse_log(Path(factory_log).read_text(encoding="utf-8", errors="replace"))
            p = peak_heap(lp["mem"], "stream-start", "stream-end")
            res.tables.append(Table(
                "Peak heap of the Delta-OTA update stream (from the supplied serial capture)", ["Item", "Value"],
                [["[MEM] stream-start / stream-end min free", f"{p['start_min']:,} / {p['end_min']:,} B"],
                 ["Peak heap during the stream (Class 2 definition)", f"{p['class2_peak']:,} B"]], "measured",
                note=f"From {factory_log}."))
            res.claims.append(f"[measured] Peak heap of a Delta-OTA update stream: {p['class2_peak']:,} B "
                              f"({_pct(p['class2_peak'], fp.CLASS2_RAM_BYTES)} of 50 KiB).")
        except (OSError, ValueError) as e:
            res.notes.append(f"Supplied factory capture not usable: {e}")

    res.notes.append(
        "The baseline is a lower bound (read-only, no transaction signing, no JSON library, no certificate "
        "validation); a real on-device Web3 client costs more, which strengthens the offloading result.")
    return res


def _hardware_tables(res: StepResult, parsed: dict) -> None:
    try:
        p = peak_heap(parsed["mem"], "web3-start", "web3-end")
    except ValueError:
        res.notes.append("The capture has no web3-start/web3-end [MEM] markers (did Wi-Fi connect?).")
        return
    ok = [w for w in parsed["web3"] if w["ok"]]
    rows = [["Heap free at web3-start", f"{p['start_free']:,} B"],
            ["Lowest free heap during the Web3 phase", f"{p['end_min']:,} B"],
            ["Peak heap used by the on-device Web3 client", f"{p['peak_bytes']:,} B" + ("" if p["exact"] else " (upper bound)")],
            ["Share of the Class 2 RAM budget (50 KiB)", _pct(p["peak_bytes"], fp.CLASS2_RAM_BYTES)],
            ["Successful ledger checks", f"{len(ok)}/{len(parsed['web3'])}"]]
    if ok:
        for key, label, unit in (("tls_connect_ms", "TLS connect + handshake", " ms"), ("request_ms", "HTTP request/response", " ms"),
                                 ("keccak_us", "Keccak-256 selector", " µs"), ("decode_us", "ABI decode", " µs")):
            s = summarize([w[key] for w in ok if w[key] is not None])
            rows.append([label, fmt_ci(s, 1, unit)])
        cyc = summarize([(w["tls_connect_ms"] + (w["request_ms"] or 0)) * 1000 * CPU_MHZ for w in ok])
        rows.append([f"CPU cycles per ledger check at {CPU_MHZ} MHz (modelled from wall time)", f"{cyc['mean']:,.0f}"])
    res.tables.append(Table("On-device Web3 client on the ESP32 (hardware capture)", ["Metric", "Value"], rows, "measured",
                            note="Cycles are wall time x clock (modelled): the radio wait is included, so this "
                                 "over-counts pure CPU work."))
    res.claims.append(
        f"[measured, hardware] One on-device ledger check peaks at {p['peak_bytes']:,} B of heap "
        f"({_pct(p['peak_bytes'], fp.CLASS2_RAM_BYTES)} of a 50 KiB Class 2 RAM budget)"
        + (f" and takes {fmt_ci(summarize([w['tls_connect_ms'] + (w['request_ms'] or 0) for w in ok]), 0, ' ms')} "
           "of device time; with offloading the device does none of this." if ok else ".")
    )
