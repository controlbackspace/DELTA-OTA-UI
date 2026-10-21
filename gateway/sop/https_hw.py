"""Baseline H: the full v1.1 binary over HTTPS (Chapter 3's "Standard HTTPS Full-Binary Update"), measured on the ESP32.

    python -m sop.https_hw --serial COM3 --lan-ip 192.168.100.94 --iface 6 [--runs 63] [--out <folder>] --allow-flash

What it does (see 03-writing/06_baselines-spec.md in the data pack):

1. serves the unmodified `app-v1.1.bin` over HTTPS (TLS 1.2, self-signed ECDSA P-256 certificate, port 8545) on this PC;
2. captures the LAN traffic of that port with tshark;
3. builds and flashes the `https_baseline` firmware with `-DHTTPS_RUNS=<runs>` (sop4.hw_session erases otadata after the
   upload so the factory slot boots), captures the serial output (one boot = `runs` consecutive downloads), and restores
   the factory updater;
4. joins the device's `[HTTPS]` lines with the capture, one TCP stream per run (time to completion and bytes on the wire),
   and writes campaign/https_runs.csv, summary.json and the raw files.

The first 3 runs are warm-up (stored, never analysed). It replaces the factory updater until restored, so it needs
--allow-flash; afterwards put the board back in demonstration state with `tools\\flash_device.bat reset COMx`.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import subprocess
import time
from pathlib import Path

from . import footprint as fp, sop1, sop4
from .inference import mean
from .runlog import DEFAULT_RESULTS_ROOT, RunContext
from .serial_parse import parse_log, peak_heap

TSHARK = Path(r"C:\Program Files\Wireshark\tshark.exe")
TSHARK_FIELDS = ["tcp.stream", "frame.time_epoch", "ip.src", "ip.dst", "ip.len", "tcp.len", "tcp.flags.syn"]
WARMUP = 3
PORT = 8545
RUN_FIELDS = ["run", "warmup", "status", "note", "ttc_ms", "wire_bytes", "connect_ms", "download_ms", "device_ms", "capture_minus_device_ms",
              "flash_us", "flash_bytes", "flash_kbps", "bytes", "static_ram_kb"]


# ----------------------------------------------------------------------------------------------- pure analysis
def parse_streams(text: str, server_ip: str) -> list[dict]:
    """Per-TCP-stream capture metrics from tshark field output (tab separated, TSHARK_FIELDS order).

    ttc_ms = first packet of the connection (the SYN) to the last server data packet (the last byte of the response or of the
    TLS close alert); wire_bytes = every packet of the stream counted as IP total length (IP + TCP headers + payload), the same
    convention as the UDP captures of Scenarios A and B. Streams are returned in the order they started.
    """
    streams: dict[str, dict] = {}
    for line in text.splitlines():
        p = line.split("\t")
        if len(p) < 7:
            continue
        try:
            sid, t, src, dst = p[0], float(p[1]), p[2], p[3]
            ip_len, tcp_len = int(p[4] or 0), int(p[5] or 0)
        except ValueError:
            continue
        s = streams.setdefault(sid, {"stream": sid, "start": t, "last_data": None, "wire_bytes": 0, "packets": 0, "syn": False})
        s["start"] = min(s["start"], t)
        s["wire_bytes"] += ip_len
        s["packets"] += 1
        s["syn"] = s["syn"] or p[6] in ("1", "True", "true")
        if src == server_ip and tcp_len > 0:
            s["last_data"] = t if s["last_data"] is None else max(s["last_data"], t)
    out = []
    for s in sorted(streams.values(), key=lambda x: x["start"]):
        s["ttc_ms"] = (s["last_data"] - s["start"]) * 1000.0 if s["last_data"] is not None else None
        out.append(s)
    return out


def join_runs(https_lines: list[dict], streams: list[dict], static_ram_kb: float | None = None, warmup: int = WARMUP) -> list[dict]:
    """One row per run: the device's own numbers joined with the capture of the same run (run i = stream i, in order).

    Every attempt opens exactly one TCP connection (a failed connect included), so the counts must agree; if they do not,
    nothing is joined and every row says so (the cycle is not silently mis-matched).
    """
    runs = sorted(https_lines, key=lambda r: r["run"])
    aligned = len(runs) == len(streams)
    rows = []
    for r in runs:
        row = {k: "" for k in RUN_FIELDS}
        row.update(run=r["run"], warmup=r["run"] < warmup, static_ram_kb=static_ram_kb)
        if not r["ok"]:
            row.update(status="failed", note=f"device: {r['why']}")
            rows.append(row)
            continue
        row.update(status="ok", note="", connect_ms=r["connect_ms"], download_ms=r["download_ms"], bytes=r["bytes"],
                   device_ms=r["connect_ms"] + r["download_ms"], flash_us=r["flash_us"], flash_bytes=r["flash_bytes"],
                   flash_kbps=round((r["flash_bytes"] / 1024.0) / (r["flash_us"] / 1e6), 3) if r["flash_us"] else "")
        if aligned:
            st = streams[runs.index(r)]
            if st["ttc_ms"] is None:
                row.update(status="invalid", note="the capture holds no server data for this run")
            else:
                row.update(ttc_ms=round(st["ttc_ms"], 3), wire_bytes=st["wire_bytes"],
                           capture_minus_device_ms=round(st["ttc_ms"] - row["device_ms"], 3))
        else:
            row.update(status="invalid", note=f"capture/device mismatch: {len(streams)} TCP streams for {len(runs)} runs")
        rows.append(row)
    return rows


def summarise(rows: list[dict]) -> dict:
    counted = [r for r in rows if not r["warmup"] and r["status"] == "ok"]

    def col(k):
        return [float(r[k]) for r in counted if r[k] != ""]

    out = {"counted_ok": len(counted), "counted_failed": sum(1 for r in rows if not r["warmup"] and r["status"] != "ok")}
    for k in ("ttc_ms", "wire_bytes", "connect_ms", "download_ms", "flash_kbps"):
        v = col(k)
        out[k + "_mean"] = mean(v) if v else None
    return out


# ----------------------------------------------------------------------------------------------- hardware
def static_increments(project: Path, ctx: RunContext, pio: str) -> dict:
    """Static RAM and flash of the baselines over the Wi-Fi-only control, from the build sizes (as in SOP 4)."""
    res = {}
    for env in ("https_control", "https_baseline", "factory", "factory_naked"):
        b = fp.build_env(project, env, ctx.sub("raw") / f"build-{env}.log", pio)
        if not b.ok:
            raise RuntimeError(f"building {env} failed: {b.error}")
        res[env] = {"ram_used": b.ram_used, "flash_used": b.flash_used}
    base = res["https_control"]
    for env in ("https_baseline", "factory", "factory_naked"):
        res[env]["static_ram_increment_b"] = res[env]["ram_used"] - base["ram_used"]
        res[env]["flash_increment_b"] = res[env]["flash_used"] - base["flash_used"]
    return res


def _tshark_start(iface: str, pcap: Path):
    proc = subprocess.Popen([str(TSHARK), "-i", iface, "-f", f"tcp port {PORT}", "-w", str(pcap)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)
    return proc


def _tshark_text(pcap: Path) -> str:
    cmd = [str(TSHARK), "-r", str(pcap), "-Y", "tcp", "-T", "fields", "-E", "separator=/t"]
    for f in TSHARK_FIELDS:
        cmd += ["-e", f]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300).stdout


def run(serial: str, lan_ip: str, iface: str, runs: int, out: Path, project: Path) -> dict:
    from .web3_hw import capture_seconds_for, make_certificate

    ctx = RunContext(out.resolve())
    raw = ctx.sub("raw")
    pio = fp.find_pio()
    if pio is None:
        raise RuntimeError("PlatformIO (pio) not found")
    base, target = sop1.find_real_pair(str(project))
    image = target.read_bytes()
    sizes = static_increments(project, ctx, pio)
    (out / "static_increments.json").write_text(json.dumps(sizes, indent=1), encoding="utf-8")
    ram_kb = round(sizes["https_baseline"]["static_ram_increment_b"] / 1024.0, 2)

    cert, key = raw / "https-cert.pem", raw / "https-key.pem"
    make_certificate(lan_ip, cert, key)
    httpd = https_server(image, cert, key)
    pcap = raw / "https-runs.pcap"
    tshark = _tshark_start(iface, pcap)
    try:
        flags = " ".join([f'-DHTTPS_HOST=\\"{lan_ip}\\"', f"-DHTTPS_PORT={PORT}", '-DHTTPS_PATH=\\"/app-v1.1.bin\\"', f"-DHTTPS_RUNS={runs}"])
        hw = sop4.hw_session(ctx, project, pio, serial, flags, max(capture_seconds_for(runs) * 2, 600), env_name="https_baseline")
    finally:
        time.sleep(1.0)
        tshark.terminate()
        try:
            tshark.wait(10)
        except subprocess.TimeoutExpired:
            tshark.kill()
        httpd.shutdown()
        key.unlink(missing_ok=True)
    parsed = hw.get("parsed") or {}
    streams = parse_streams(_tshark_text(pcap), lan_ip)
    rows = join_runs(parsed.get("https", []), streams, ram_kb)
    (out / "campaign").mkdir(parents=True, exist_ok=True)
    with open(out / "campaign" / "https_runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RUN_FIELDS)
        w.writeheader()
        w.writerows(rows)
    heap = None
    try:
        heap = peak_heap(parsed["mem"], "https-start", "https-end")
    except (ValueError, KeyError):
        pass
    summary = {"summary": summarise(rows), "heap": heap, "streams": len(streams), "restored": hw.get("restored"),
               "image_sha256": hashlib.sha256(image).hexdigest(), "static_ram_kb": ram_kb}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return summary


def https_server(image: bytes, cert: Path, key: Path):
    """TLS 1.2 HTTPS server on all interfaces, port 8545, serving the unmodified image (one connection per download)."""
    import ssl
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            if self.path != "/app-v1.1.bin":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(image)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(image)
            self.close_connection = True

        def log_message(self, *a):
            pass

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert), str(key))
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--lan-ip", required=True)
    ap.add_argument("--iface", default="6")
    ap.add_argument("--runs", type=int, default=63, help="downloads in the one boot: 3 warm-up + 60 counted")
    ap.add_argument("--project")
    ap.add_argument("--out")
    ap.add_argument("--allow-flash", action="store_true")
    a = ap.parse_args(argv)
    if not a.allow_flash:
        print("This replaces the factory updater until it is restored: pass --allow-flash.")
        return 2
    project = fp.find_project(a.project)
    if project is None:
        print("Firmware project not found: pass --project.")
        return 2
    out = Path(a.out) if a.out else DEFAULT_RESULTS_ROOT / f"baseline-H-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}"
    s = run(a.serial, a.lan_ip, a.iface, a.runs, out, Path(project))
    print(json.dumps(s, indent=1, default=str))
    print(f"Next: tools\\flash_device.bat reset {a.serial}   (demonstration state)")
    return 0 if s["summary"]["counted_ok"] == a.runs - WARMUP and s["restored"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
