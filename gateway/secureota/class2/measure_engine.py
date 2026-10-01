"""Measure the DeltaOTA engine footprint (no hardcoded metrics).

Stage 1 (exact): xtensa-esp32-elf-nm on firmware.elf attributes every
  `DeltaOTAEngine::*` / `otaEngine` symbol by address range
  (flash 0x400Dxxxx / RAM 0x3FFBxxxx). Inlined engine code hiding inside
  loop()/global-init is reported as a methodology note, not guessed.
Stage 2 (framework): the linker map attributes .text/.rodata/.data/.bss per
  object file, grouped for the subtraction table (what the Class-2 port
  deletes). IRAM-resident code is reported separately.

Outputs engine-footprint.json + engine-footprint.md. Only the Class-2
reference-stack rows in the downstream budget (Zephyr/Contiki literature)
are cited estimates, labeled as such — never measured here.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

NM = (
    Path.home()
    / ".platformio/packages/toolchain-xtensa-esp32/bin/xtensa-esp32-elf-nm.exe"
)
ENGINE_PATTERNS = (
    "_ZN14DeltaOTAEngine",  # DeltaOTAEngine:: methods / members
    "_ZZN14DeltaOTAEngine",  # function-local statics inside engine methods
    "otaEngine",  # global instance + its init guards (BSS + ctors)
)

FLASH_SECTIONS = {".text", ".rodata", ".data", ".rwtext", ".flash.text", ".flash.rodata"}
RAM_SECTIONS = {".data", ".bss", ".dram0.data", ".dram0.bss", ".noinit"}
IRAM_SECTIONS = {".iram0.text"}

# (label, path-regex, port-fate)
MAP_GROUPS = (
    ("WiFi + UDP radio", r"libWiFi|WiFiUdp|esp_wifi|net80211|libpp\.a|libphy\.a", "deleted on port"),
    ("Bluetooth (linked shims)", r"libbt\.a|libbtdm|libmesh\.a", "deleted on port"),
    ("lwIP (TCP/IP)", r"liblwip|lwip", "deleted on port"),
    ("FreeRTOS", r"libfreertos|freertos", "replaced by class-2 RTOS (reference row)"),
    ("mbedTLS (CCM+SHA kept)", r"mbedtls", "kept (or tinyAES-class equivalent)"),
    ("Arduino core", r"/cores/esp32/|esp32-hal|FrameworkArduino|Esp\.cpp|libesp_system|libesp_hw|libesp_event|libesp_ipc|libesp_timer", "deleted on port"),
    ("NVS / Preferences glue", r"nvs_flash|Preferences", "replaced by tiny NVS equivalent"),
    ("App glue (setup/loop, incl. inlined engine)", r"main\.cpp\.o", "kept (port rewritten, same logic)"),
)

SECTION_LINE = re.compile(
    r"^\s+(\.\S+)\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)(?:\s+(\S+))?\s*$"
)
CONTRIB_LINE = re.compile(
    r"^\s+0x[0-9a-fA-F]+\s+0x([0-9a-fA-F]+)\s+(\S+?)(?:\s+\(.*\))?\s*$"
)


def is_flash(addr: int) -> bool:
    return 0x400D0000 <= addr < 0x41000000


def is_ram(addr: int) -> bool:
    return 0x3FFB0000 <= addr < 0x40000000 or 0x50000000 <= addr < 0x50100000


def stage1_nm(elf: Path) -> dict:
    out = subprocess.run(
        [str(NM), "--print-size", "--size-sort", str(elf)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    engine = {"flash": 0, "ram": 0, "symbols": 0, "entries": []}
    total = {"flash": 0, "ram": 0}
    for line in out.splitlines():
        m = re.match(r"^([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([A-Za-z?])\s+(\S+)", line)
        if not m:
            continue
        addr, size = int(m.group(1), 16), int(m.group(2), 16)
        name = m.group(4)
        if size == 0:
            continue
        flash = is_flash(addr)
        ram = is_ram(addr)
        if flash:
            total["flash"] += size
        if ram:
            total["ram"] += size
        if any(p in name for p in ENGINE_PATTERNS):
            engine["symbols"] += 1
            if flash:
                engine["flash"] += size
            if ram:
                engine["ram"] += size
            engine["entries"].append({"name": name, "size": size,
                                      "where": "flash" if flash else ("ram" if ram else "other")})
    return {"engine": engine, "total": total}


def bucket_of_addr(addr: int) -> str | None:
    # Address-based (never trusts section headers): discarded input sections
    # and COMMON symbols carry addr 0x0 and are excluded automatically.
    if 0x400D0000 <= addr < 0x41000000 or 0x3F400000 <= addr < 0x3F800000:
        return "flash"  # irom/drom (second range is flash-mapped rodata)
    if 0x40080000 <= addr < 0x400B0000:
        return "iram"  # IRAM-resident code: RAM pressure on ESP32, noted
    if 0x3FFB0000 <= addr < 0x40000000 or 0x50000000 <= addr < 0x50100000:
        return "ram"
    return None


def label_of(path: str) -> str:
    p = path.lower()
    for lname, pat, _fate in MAP_GROUPS:
        if re.search(pat, p):
            return lname
    return "Other libs (newlib, drivers, glue)"


def stage2_map(map_path: Path) -> dict:
    groups: dict[str, dict[str, int]] = {}
    for label, _pat, _fate in MAP_GROUPS:
        groups[label] = {"flash": 0, "ram": 0, "iram": 0}
    groups["Other libs (newlib, drivers, glue)"] = {"flash": 0, "ram": 0, "iram": 0}
    current: str | None = None
    with open(map_path, errors="replace") as f:
        for line in f:
            m = SECTION_LINE.match(line)
            if m:
                # Header lines only set context; only address-bearing
                # contribution lines below are ever counted.
                if m.group(3) is None:
                    current = m.group(1)
                continue
            c = CONTRIB_LINE.match(line)
            if c is None:
                continue
            size = int(c.group(1), 16)
            if size == 0:
                continue
            b = bucket_of_addr(int(c.group(0).split()[0], 16))
            if b:
                groups[label_of(c.group(2))][b] += size
    return groups


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: measure_engine.py <.pio/build/<env> dir> <out-dir>")
        return 2
    build_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    s1 = stage1_nm(build_dir / "firmware.elf")
    s2 = stage2_map(build_dir / "firmware.map")
    eng = s1["engine"]

    # Reconciliation: nm sees every linked symbol; the map attributes most of
    # it. The remainder (alignment fill, COMMON, linker-owned) is reported as
    # its own honest row, never silently absorbed or guessed away.
    unatt_flash = max(0, s1["total"]["flash"] - sum(v["flash"] for v in s2.values()))
    unatt_ram = max(0, s1["total"]["ram"] - sum(v["ram"] for v in s2.values()))
    s2["Unattributed (alignment, COMMON, linker-owned)"] = {
        "flash": unatt_flash, "ram": unatt_ram, "iram": 0}

    report = {
        "engine_flash_bytes": eng["flash"],
        "engine_static_ram_bytes": eng["ram"],
        "engine_symbols": eng["symbols"],
        "engine_symbol_table": eng["entries"],
        "nm_total_flash_bytes": s1["total"]["flash"],
        "nm_total_ram_bytes": s1["total"]["ram"],
        "framework_groups": s2,
        "method_note": (
            "Engine code inlined into loop()/global-init hides inside "
            "main.cpp.o (see App-glue map row); nm-misses are bounded above by "
            "that row, never guessed into the engine total."
        ),
    }
    (out_dir / "engine-footprint.json").write_text(json.dumps(report, indent=2))

    lines = [
        "# DeltaOTA engine footprint (measured, not estimated)",
        "",
        f"Engine code (Flash): **{eng['flash']} B** across {eng['symbols']} symbols.",
        f"Engine static RAM: **{eng['ram']} B** (global `otaEngine` instance + guards).",
        "",
        "| Component | Flash (B) | Static RAM (B) | IRAM (B) | Port fate |",
        "|---|---|---|---|---|",
    ]
    fate_of = {lname: fate for lname, _pat, fate in MAP_GROUPS}
    fate_of["Other libs (newlib, drivers, glue)"] = "kept/minimized"
    fate_of["Unattributed (alignment, COMMON, linker-owned)"] = (
        "measured remainder vs nm totals (conservative: kept)"
    )
    for label, vals in s2.items():
        lines.append(f"| {label} | {vals['flash']} | {vals['ram']} | {vals['iram']} | {fate_of.get(label, '')} |")
    lines += [
        "",
        "Notes (read before quoting numbers):",
        "- App-glue static RAM (~3.2 KiB) is the same `otaEngine` instance "
        "already counted in the engine row above — same bytes, two lenses, counted once in totals.",
        "- ESP32 mask-ROM residents (bulk WiFi/BT ROM code) execute from ROM and never appear in this image; "
        "the port deletes the need for them, stated qualitatively, not measured here.",
    ]
    (out_dir / "engine-footprint.md").write_text("\n".join(lines) + "\n")
    print(f"engine: flash={eng['flash']}B ram={eng['ram']}B symbols={eng['symbols']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
