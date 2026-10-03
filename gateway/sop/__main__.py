"""python -m sop <command>

  preflight   check the environment (tools, inputs, ports)
  sop1        delta footprint and network load           [offline]
  sop2        OSCORE-style framing vs standard handshake [offline; device numbers if sop4/--factory-log]
  sop3        ledger reliability and revocation          [offline; live part needs Node]
  sop4        Web3 offloading: device footprint          [static: needs PlatformIO; --serial for heap]
  report      (re)build SOP-REPORT.md from a run directory
  all         preflight + every implemented step + report

Results go to sop-results/<UTC stamp>/ (or --run DIR to add to an existing run).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import report as report_mod
from . import footprint, sop1, sop2, sop3, sop4
from .runlog import RunContext, StepResult, Table

NOT_IMPLEMENTED = {
}


def step_preflight(ctx: RunContext, args) -> StepResult:
    res = StepResult(sop="ENV", title="Environment", mode="offline")
    rows = []

    def check(name: str, ok: bool, detail: str):
        rows.append([name, "ok" if ok else "MISSING", detail])
        return ok

    check("Python", sys.version_info >= (3, 11), sys.version.split()[0])
    try:
        import bsdiff4  # noqa: F401
        check("bsdiff4", True, "importable")
    except ImportError:
        check("bsdiff4", False, "pip install -r gateway/requirements.txt")
    real = sop1.find_real_pair(args.firmware_dir, args.base, args.target)
    check("Real firmware pair", real is not None,
          f"{real[0]} -> {real[1]}" if real else "release-images/app-v1.0.bin + app-v1.1.bin not found")
    for tool, why in (("git", "run metadata"), ("npx", "SOP3 contract tests and chain")):
        check(tool, shutil.which(tool) is not None, why)
    pio = footprint.find_pio()
    check("pio (PlatformIO)", pio is not None, pio or "SOP4 footprint builds")
    check("Firmware project", footprint.find_project(args.firmware_dir) is not None,
          str(footprint.find_project(args.firmware_dir) or "platformio.ini not found (--firmware-dir)"))
    try:
        import serial  # noqa: F401
        check("pyserial", True, "hardware steps available")
    except ImportError:
        check("pyserial", False, "needed only for [hw] steps")

    res.tables.append(Table("Preflight", ["Check", "Result", "Detail"], rows, "measured"))
    hard_missing = [r for r in rows if r[1] == "MISSING" and r[0] in ("bsdiff4",)]
    if hard_missing:
        res.status, res.reason = "failed", "required component missing"
    return res


def step_not_implemented(sop: str) -> StepResult:
    title, phase = NOT_IMPLEMENTED[sop]
    return StepResult(sop=sop, title=title, status="not-implemented",
                      reason=f"planned in phase {phase}; no data is reported until it exists")


def open_context(args, create: bool) -> RunContext | None:
    if args.run:
        return RunContext(Path(args.run))
    if create:
        return RunContext.new()
    return RunContext.latest()


def run_step(ctx: RunContext, name: str, args) -> StepResult:
    if name == "preflight":
        r = step_preflight(ctx, args)
    elif name == "sop2":
        r = sop2.run(ctx, ops=args.ops, handshakes=args.handshakes, firmware_dir=args.firmware_dir,
                     base=args.base, target=args.target, factory_log=args.factory_log)
    elif name == "sop4":
        r = sop4.run(ctx, firmware_dir=args.firmware_dir, serial=args.serial, allow_flash=args.allow_flash,
                     web3_host=args.web3_host, web3_port=args.web3_port, web3_contract=args.web3_contract,
                     web3_version=args.web3_version, factory_log=args.factory_log, hw_dry_run=args.hw_dry_run,
                     capture_seconds=args.capture_seconds)
    elif name == "sop3":
        r = sop3.run(ctx, trials=args.trials, n_latency=args.n_latency, live_trials=args.live_trials,
                     chain=not args.no_chain, hardhat_port=args.hardhat_port)
    elif name == "sop1":
        r = sop1.run(ctx, repeats=args.n, firmware_dir=args.firmware_dir, base=args.base, target=args.target,
                     synthetic=not args.no_synthetic)
    else:
        r = step_not_implemented(name.upper())
    ctx.save(r)
    print(f"[{r.sop}] {r.status}" + (f" - {r.reason}" if r.reason else ""))
    for c in r.claims:
        print("   " + c)
    return r


def main(argv=None) -> int:
    # Claims contain symbols (±, ≥) a legacy Windows console codepage cannot encode.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="sop", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["preflight", "sop1", "sop2", "sop3", "sop4", "report", "all"])
    ap.add_argument("--run", help="existing run directory to add to (default: new for steps, latest for report)")
    ap.add_argument("--n", type=int, default=5, help="timing repeats per case (default 5)")
    ap.add_argument("--firmware-dir", help="firmware project holding release-images/ (default: Thesis project)")
    ap.add_argument("--base", help="explicit base firmware image")
    ap.add_argument("--target", help="explicit target firmware image")
    ap.add_argument("--no-synthetic", action="store_true", help="skip the synthetic stress cases")
    ap.add_argument("--trials", type=int, default=30, help="SOP3: seeded trials per attack (default 30)")
    ap.add_argument("--n-latency", type=int, default=10, help="SOP3: revoke-to-halt latency trials (default 10)")
    ap.add_argument("--live-trials", type=int, default=3, help="SOP3: wrong-hash trials on the live chain (default 3)")
    ap.add_argument("--no-chain", action="store_true", help="SOP3: skip the live chain/gateway part")
    ap.add_argument("--serial", help="SOP4: ESP32 serial port (e.g. COM3) for the hardware part")
    ap.add_argument("--allow-flash", action="store_true",
                    help="SOP4: permit flashing web3_baseline (replaces the factory updater until restored)")
    ap.add_argument("--hw-dry-run", action="store_true", help="SOP4: print the hardware plan, flash nothing")
    ap.add_argument("--web3-host", help="SOP4: RPC host for the on-device ledger check (e.g. your Funnel hostname)")
    ap.add_argument("--web3-port", type=int, default=443)
    ap.add_argument("--web3-contract", help="SOP4: DeltaOTA contract address queried by the device")
    ap.add_argument("--web3-version", default="v1.1", help="SOP4: release tag the device looks up")
    ap.add_argument("--factory-log", help="SOP4: serial capture of a Delta-OTA update (for the engine's peak heap)")
    ap.add_argument("--capture-seconds", type=int, default=90, help="SOP4: serial capture length")
    ap.add_argument("--ops", type=int, default=2000, help="SOP2: timed AES-CCM operations per measurement (default 2000)")
    ap.add_argument("--handshakes", type=int, default=50, help="SOP2: TLS handshakes to time (default 50)")
    ap.add_argument("--hardhat-port", type=int, default=18545, help="SOP3: port of the throwaway Hardhat node")
    args = ap.parse_args(argv)

    if args.command == "report":
        ctx = open_context(args, create=False)
        if ctx is None:
            print("No run found - run a step first (e.g. python -m sop sop1).")
            return 2
        print("Report:", report_mod.write_report(ctx))
        return 0

    ctx = open_context(args, create=True)
    # sop2 last: it reuses the device numbers SOP4 stores in this run
    names = ["preflight", "sop1", "sop3", "sop4", "sop2"] if args.command == "all" else [args.command]
    failed = False
    for name in names:
        r = run_step(ctx, name, args)
        failed |= r.status == "failed"
    path = report_mod.write_report(ctx)
    print("Report:", path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
