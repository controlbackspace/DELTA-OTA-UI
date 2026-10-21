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
# Experiment baseline H (HTTPS full-binary download), one line per run:
#   [HTTPS] run=N connect_ms=.. download_ms=.. flash_us=.. flash_bytes=.. bytes=.. ok=1      or    ... ok=0 why=..
HTTPS = re.compile(
    r"\[HTTPS\] run=(\d+)(?: connect_ms=(\d+))?(?: download_ms=(\d+) flash_us=(\d+) flash_bytes=(\d+) bytes=(\d+))?"
    r" ok=([01])(?: why=(\S+))?")
# Added for the experiment's Table 2: the device's busy time and flash writes during one update stream.
#   decrypt_us   time in AES-CCM decryption of all blocks
#   feed_us      time in the DOTA decoder (inflate + merge + flash writes, incl. esp_ota_begin's erase)
#   flash_us     time inside esp_ota_begin + esp_ota_write (a part of feed_us)
#   flash_bytes  bytes written to flash;  stream_us  first accepted block -> last;  blocks  blocks decoded
METRICS2 = re.compile(
    r"\[Metrics2\] decrypt_us=(\d+) feed_us=(\d+) flash_us=(\d+) flash_bytes=(\d+) stream_us=(\d+) blocks=(\d+)")
RECONSTRUCTED = re.compile(r"\[Delta\] Reconstructed (\d+) bytes, esp_ota_end OK")
UPDATE_FAILED = re.compile(r"\[OTA\] Update to (\S+) FAILED: (.*)")
WIFI_IP = re.compile(r"\[WiFi\] Connected\. IP=(\S+)")
VERSION_ANSWER = re.compile(r"\[OTA\] (Gateway did not answer /version|Gateway has no release staged)")
BANNER = re.compile(r"=== (Delta-OTA updater|SOP4 baseline[^=]*)")
APP_VERSION = re.compile(r"\[Health\] Application: (\S+)")
UPDATE = re.compile(r"\[OTA\] Update available: (\S+) -> (\S+)")


def split_stamp(line: str) -> tuple[float | None, str]:
    m = STAMP.match(line)
    return (float(m.group(1)), line[m.end():]) if m else (None, line)


def parse_log(text: str) -> dict:
    out = {"mem": [], "metrics": [], "web3": [], "banners": [], "app_version": None, "updates": [],
           "metrics2": [], "reconstructed": [], "update_failed": [], "wifi_ip": None, "app_versions": [], "no_release": [],
           "https": []}
    for raw in text.splitlines():
        t, line = split_stamp(raw)
        if m := MEM.search(line):
            out["mem"].append({"t": t, "phase": m.group(1), "free": int(m.group(2)), "min": int(m.group(3))})
        elif m := METRICS.search(line):
            out["metrics"].append({"t": t, "n": int(m.group(1)), "avg_us": int(m.group(2)),
                                   "min_us": int(m.group(3)), "max_us": int(m.group(4))})
        elif m := HTTPS.search(line):
            out["https"].append({
                "t": t, "run": int(m.group(1)), "connect_ms": int(m.group(2)) if m.group(2) else None,
                "download_ms": int(m.group(3)) if m.group(3) else None, "flash_us": int(m.group(4)) if m.group(4) else None,
                "flash_bytes": int(m.group(5)) if m.group(5) else None, "bytes": int(m.group(6)) if m.group(6) else None,
                "ok": m.group(7) == "1", "why": m.group(8)})
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
        elif m := METRICS2.search(line):
            d, f, fl, fb, st, bl = (int(g) for g in m.groups())
            out["metrics2"].append({"t": t, "decrypt_us": d, "feed_us": f, "flash_us": fl, "flash_bytes": fb,
                                    "stream_us": st, "blocks": bl})
        elif m := RECONSTRUCTED.search(line):
            out["reconstructed"].append({"t": t, "bytes": int(m.group(1))})
        elif m := UPDATE_FAILED.search(line):
            out["update_failed"].append({"t": t, "version": m.group(1), "why": m.group(2).strip()})
        elif m := WIFI_IP.search(line):
            out["wifi_ip"] = m.group(1)
        elif m := VERSION_ANSWER.search(line):
            out["no_release"].append({"t": t, "why": m.group(1)})
        elif m := APP_VERSION.search(line):
            out["app_version"] = m.group(1)
            out["app_versions"].append({"t": t, "version": m.group(1)})
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
