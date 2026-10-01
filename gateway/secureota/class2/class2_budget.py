"""Assemble the Class-2 viability budget (RFC 7228: ~50 KiB RAM, ~250 KiB flash).

Inputs (all measured, never typed):
  engine-footprint.json ... engine_flash_bytes, engine_static_ram_bytes
  serial-mem.log .......... [MEM] phase=stream-start/end lines from a live OTA
                            (peak RAM = start.min - end.min)
  reference-stack.json .... cited literature rows (Zephyr/Contiki-class
                            6LoWPAN+CoAP footprints) WITH provenance strings.
                            These are estimates by declaration, never measured.

Output: class2-budget.md — the panel table with headroom math and a
measured-vs-reference column discipline. Exit nonzero on missing inputs.
"""
import json
import re
import sys
from pathlib import Path

MEM_LINE = re.compile(r"\[MEM\] phase=(\S+) free=(\d+) min=(\d+)")


def parse_serial(log_path: Path) -> dict:
    start = end = None
    for line in log_path.read_text(errors="replace").splitlines():
        m = MEM_LINE.search(line)
        if not m:
            continue
        phase, _free, minv = m.group(1), int(m.group(2)), int(m.group(3))
        if phase == "stream-start" and start is None:
            start = minv
        elif phase == "stream-end":
            end = minv
    if start is None or end is None:
        raise SystemExit(f"need both stream-start and stream-end [MEM] lines in {log_path}")
    return {"heap_min_start": start, "heap_min_end": end, "peak_ram_bytes": start - end}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: class2_budget.py <evidence-dir> <reference-stack.json>")
        return 2
    ev = Path(sys.argv[1])
    fp = json.loads((ev / "engine-footprint.json").read_text())
    mem = parse_serial(ev / "serial-mem.log")
    ref = json.loads(Path(sys.argv[2]).read_text())

    eng_flash = fp["engine_flash_bytes"]
    eng_ram_static = fp["engine_static_ram_bytes"]
    eng_ram_peak = mem["peak_ram_bytes"]
    # Conservative engine RAM: static instance and live peak overlap almost
    # entirely (peak window contains the static instance); take the max, and
    # say so, instead of summing both.
    eng_ram = max(eng_ram_static, eng_ram_peak)

    lines = [
        "# Class-2 viability budget (RFC 7228: 50 KiB RAM / 250 KiB flash)",
        "",
        "| Component | Flash (B) | RAM (B) | Provenance |",
        "|---|---|---|---|",
        f"| DeltaOTA engine code (measured ELF) | {eng_flash} | — | measured, engine-footprint.json |",
        f"| DeltaOTA engine RAM = max(static {eng_ram_static}, live peak {eng_ram_peak}) | — | {eng_ram} | measured (ELF + live serial) |",
    ]
    ref_flash = ref_ram = 0
    for row in ref["rows"]:
        lines.append(f"| {row['component']} | {row['flash_bytes']} | {row['ram_bytes']} | reference ({row['source']}) |")
        ref_flash += row["flash_bytes"]
        ref_ram += row["ram_bytes"]
    tot_flash, tot_ram = eng_flash + ref_flash, eng_ram + ref_ram
    lines += [
        f"| **Total vs Class-2 budget** | **{tot_flash} / {250 * 1024} flash** | **{tot_ram} / {50 * 1024} RAM** | — |",
        "",
        f"Flash headroom: {(250 * 1024 - tot_flash) / (250 * 1024) * 100:.1f} pct, "
        f"RAM headroom: {(50 * 1024 - tot_ram) / (50 * 1024) * 100:.1f} pct",
        "",
        "Claim boundary: architectural fit with measured margin. The Class-2 "
        "port (bare-metal C + 802.15.4 stack integration) is future work; no "
        "ESP32 binary is claimed to boot on Class-2 silicon.",
    ]
    (ev / "class2-budget.md").write_text("\n".join(lines) + "\n")
    print(f"engine_ram_static={eng_ram_static} peak={eng_ram_peak} chosen={eng_ram}")
    print(f"total flash={tot_flash}B ram={tot_ram}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
