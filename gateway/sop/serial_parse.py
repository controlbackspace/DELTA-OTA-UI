"""Parse the ESP32's serial output (firmware src/factory/main.cpp, src/baseline/main.cpp).

Pure functions over text, so they are tested against fixture logs and shared by
every hardware step. Capture lines may carry a host timestamp prefix
"[+12.345] " (added by serial_capture); it is stripped and kept as `t`.
"""
from __future__ import annotations

import re

STAMP = re.compile(r"^\[\+(\d+\.\d+)\]\s?")
MEM = re.compile(r"\[MEM\] phase=(\S+) free=(\d+) min=(\d+)")
METRICS = re.compile(r"\[Metrics\] decrypt n=(\d+) avg=(\d+)us min=(\d+)us max=(\d+)us")
WEB3 = re.compile(
    r"\[Web3\] run=(\d+) tls_connect_ms=(\d+)"
    r"(?: request_ms=(\d+) keccak_us=(\d+) decode_us=(\d+))?"
    r" ok=([01])(?: why=(\S+))?"
    r"(?: approvals=(\d+) live=([01]) revoked=([01]))?"
)
BANNER = re.compile(r"=== (Delta-OTA updater|SOP4 baseline[^=]*)")
APP_VERSION = re.compile(r"\[Health\] Application: (\S+)")
UPDATE = re.compile(r"\[OTA\] Update available: (\S+) -> (\S+)")


def split_stamp(line: str) -> tuple[float | None, str]:
    m = STAMP.match(line)
    return (float(m.group(1)), line[m.end():]) if m else (None, line)


def parse_log(text: str) -> dict:
    out = {"mem": [], "metrics": [], "web3": [], "banners": [], "app_version": None, "updates": []}
    for raw in text.splitlines():
        t, line = split_stamp(raw)
        if m := MEM.search(line):
            out["mem"].append({"t": t, "phase": m.group(1), "free": int(m.group(2)), "min": int(m.group(3))})
        elif m := METRICS.search(line):
            out["metrics"].append({"t": t, "n": int(m.group(1)), "avg_us": int(m.group(2)),
                                   "min_us": int(m.group(3)), "max_us": int(m.group(4))})
        elif m := WEB3.search(line):
            out["web3"].append({
                "t": t, "run": int(m.group(1)), "tls_connect_ms": int(m.group(2)),
                "request_ms": int(m.group(3)) if m.group(3) else None,
                "keccak_us": int(m.group(4)) if m.group(4) else None,
                "decode_us": int(m.group(5)) if m.group(5) else None,
                "ok": m.group(6) == "1", "why": m.group(7),
                "approvals": int(m.group(8)) if m.group(8) else None,
            })
        elif m := BANNER.search(line):
            out["banners"].append({"t": t, "text": m.group(1).strip()})
        elif m := APP_VERSION.search(line):
            out["app_version"] = m.group(1)
        elif m := UPDATE.search(line):
            out["updates"].append({"t": t, "from": m.group(1), "to": m.group(2)})
    return out


def peak_heap(mem: list[dict], start_phase: str, end_phase: str) -> dict:
    """Peak heap use between two [MEM] markers.

    The firmware reports `min` = the lowest free heap since boot. The use above the
    level at the start marker is therefore  start.free - end.min  and is EXACT only
    when the phase set a new low (end.min < start.min); otherwise the low was set
    earlier and the phase's own peak is only bounded above (exact=False).
    class2_peak is the definition class2_budget.py uses (start.min - end.min).
    """
    starts = [m for m in mem if m["phase"] == start_phase]
    ends = [m for m in mem if m["phase"] == end_phase]
    if not starts or not ends:
        raise ValueError(f"need [MEM] phase={start_phase} and phase={end_phase}")
    s, e = starts[0], ends[-1]
    return {
        "start_free": s["free"], "start_min": s["min"], "end_min": e["min"],
        "peak_bytes": max(0, s["free"] - e["min"]),
        "exact": e["min"] < s["min"],
        "class2_peak": max(0, s["min"] - e["min"]),
    }
