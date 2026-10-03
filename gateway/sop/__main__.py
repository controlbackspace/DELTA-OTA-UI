"""python -m sop <command>

  preflight   check the environment (tools, inputs, ports)
  sop1        delta footprint and network load           [offline]
  sop2        OSCORE vs standard handshakes              [P3 - not implemented yet]
  sop3        ledger reliability and revocation          [P1 - not implemented yet]
  sop4        Web3 offloading footprint                  [P2 - not implemented yet]
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
from . import sop1
from .runlog import RunContext, StepResult, Table

NOT_IMPLEMENTED = {
    "SOP2": ("OSCORE vs standard handshakes", "P3"),
    "SOP3": ("Ledger reliability and revocation", "P1"),
    "SOP4": ("Web3 offloading footprint", "P2"),
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
    for tool, why in (("git", "run metadata"), ("pio", "SOP4 footprint (P2)"), ("npx", "SOP3 contract tests (P1)")):
        check(tool, shutil.which(tool) is not None, why)
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
    ap = argparse.ArgumentParser(prog="sop", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["preflight", "sop1", "sop2", "sop3", "sop4", "report", "all"])
    ap.add_argument("--run", help="existing run directory to add to (default: new for steps, latest for report)")
    ap.add_argument("--n", type=int, default=5, help="timing repeats per case (default 5)")
    ap.add_argument("--firmware-dir", help="firmware project holding release-images/ (default: Thesis project)")
    ap.add_argument("--base", help="explicit base firmware image")
    ap.add_argument("--target", help="explicit target firmware image")
    ap.add_argument("--no-synthetic", action="store_true", help="skip the synthetic stress cases")
    args = ap.parse_args(argv)

    if args.command == "report":
        ctx = open_context(args, create=False)
        if ctx is None:
            print("No run found - run a step first (e.g. python -m sop sop1).")
            return 2
        print("Report:", report_mod.write_report(ctx))
        return 0

    ctx = open_context(args, create=True)
    names = ["preflight", "sop1", "sop2", "sop3", "sop4"] if args.command == "all" else [args.command]
    failed = False
    for name in names:
        r = run_step(ctx, name, args)
        failed |= r.status == "failed"
    path = report_mod.write_report(ctx)
    print("Report:", path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
