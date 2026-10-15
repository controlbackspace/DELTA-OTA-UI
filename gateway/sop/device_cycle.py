"""Scenarios A and B (Table 2) and the Table 3 gateway-profiling cycles of the experiment paper.

One *cycle* is one complete OTA update, driven from this PC:

  prepare   put the ESP32 back on app v1.0 (light reset; a full reset after a failed cycle)
  publish   A: the bsdiff4 patch v1.0 -> v1.1     B: the full v1.1 image
            hash it, serve it, propose and approve v1.1 on the local chain
  stage     wait until the gateway has downloaded, verified, encapsulated and staged it
  update    capture UDP/5683 (tshark) and the serial log, reset the ESP32, wait for the new app
  collect   TTC from the capture, device counters from the serial log, gateway telemetry
  clean up  revoke v1.1 so the next cycle can propose it again

Table 3 uses the same pieces without the device: the gateway runs on the Raspberry Pi, the PC publishes
and the cycle ends when the Pi reports the release staged and its telemetry record is read over HTTP.

The decision rules and every number's derivation are pure functions (tested without hardware).
The classes that touch the board, tshark, the chain and the Pi (LocalRig, GatewayRig) are written
against the real tools but are first exercised at the pilot run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import campaign, sop1
from .campaign import Slot, TrialStore, make_schedule
from .serial_parse import parse_log, peak_heap

VERSION = "v1.1"
TSHARK = Path(r"C:\Program Files\Wireshark\tshark.exe")
TSHARK_FIELDS = ["frame.time_epoch", "ip.src", "ip.dst", "coap.code", "coap.opt.uri_path", "coap.opt.uri_query", "udp.length"]
UPDATE_TIMEOUT_S = {"A": 120, "B": 240}
MAX_ATTEMPTS = 3
IPV4_HEADER = 20


# ============================================================= pure: capture -> TTC
@dataclass(frozen=True)
class Packet:
    t: float
    src: str
    dst: str
    code: str
    path: str
    query: str
    length: int


def norm_code(raw) -> str:
    """CoAP code as 'c.dd'. tshark prints it as the byte value (69) or dotted (2.05)."""
    s = str(raw).strip()
    if not s:
        return ""
    if "." in s:
        return s
    n = int(s)
    return f"{n >> 5}.{n & 31:02d}"


def parse_tshark(text: str) -> list[Packet]:
    """Tab-separated tshark field output -> packets. Malformed lines are skipped."""
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        try:
            out.append(Packet(float(parts[0]), parts[1], parts[2], norm_code(parts[3]),
                              parts[4].split(",")[0], parts[5], int(parts[6] or 0)))
        except ValueError:
            continue
    return out


def compute_ttc(packets: list[Packet], gateway_ip: str) -> dict:
    """Time-to-completion: the device's first GET /patch to the gateway's final (2.04) response."""
    gets = sorted((p for p in packets if p.src != gateway_ip and p.dst == gateway_ip and p.code == "0.01" and p.path == "patch"),
                  key=lambda p: p.t)
    if not packets:
        return {"ok": False, "reason": "the capture holds no CoAP packets", "requests": 0}
    if not gets:
        return {"ok": False, "reason": "the device sent no GET /patch", "requests": 0}
    first = gets[0]
    finals = [p for p in packets if p.src == gateway_ip and p.code == "2.04" and p.t >= first.t]
    base = {"requests": len(gets), "retransmissions": len(gets) - len({p.query for p in gets})}
    if not finals:
        return {"ok": False, "reason": "no final (2.04) response from the gateway", **base}
    last = max(finals, key=lambda p: p.t)
    span = [p for p in packets if first.t <= p.t <= last.t]
    return {"ok": True, "ttc_ms": (last.t - first.t) * 1000.0, "wire_bytes": sum(p.length + IPV4_HEADER for p in span), **base}


# ============================================================= pure: judging and rows
def pick_gateway_record(doc: dict | None, tag: str, after_seq: int) -> dict | None:
    """The first telemetry record for `tag` newer than `after_seq`, or None."""
    for rec in (doc or {}).get("releases", []):
        if rec.get("tag") == tag and rec.get("seq", 0) > after_seq:
            return rec
    return None


def judge_cycle(serial: dict, ttc: dict, expected_version: str = VERSION) -> tuple[str, str]:
    """(status, note). `invalid` = the harness or network failed before the update could be judged (the cycle is re-run);
    `failed` = the update started and did not complete correctly (the system failed: it counts)."""
    if not (serial["banners"] or serial["mem"] or serial["updates"] or serial["app_versions"]):
        return "invalid", "no serial output from the device"
    if not serial["updates"]:
        why = serial["no_release"][-1]["why"] if serial["no_release"] else "no 'Update available' line"
        return "invalid", f"the device never started an update ({why})"
    if serial["update_failed"]:
        f = serial["update_failed"][-1]
        return "failed", f"the device reported: update to {f['version']} failed: {f['why']}"
    if not serial["reconstructed"]:
        return "failed", "the update started but never reached esp_ota_end OK"
    if not ttc.get("ok"):
        if ttc.get("requests", 0) == 0:
            return "invalid", f"the capture is unusable ({ttc.get('reason')})"
        return "failed", f"transfer incomplete ({ttc.get('reason')})"
    if not any(v["version"] == expected_version for v in serial["app_versions"]):
        return "failed", f"the new application never reported {expected_version}"
    return "ok", "update completed and confirmed"


def device_columns(serial: dict) -> dict:
    """Table 2 device cells from the serial log (empty when the firmware did not print them)."""
    out: dict = {}
    if serial["metrics2"]:
        m = serial["metrics2"][-1]
        out["decrypt_recon_ms"] = (m["decrypt_us"] + m["feed_us"]) / 1000.0
        if m["flash_us"] > 0:
            out["flash_kbps"] = (m["flash_bytes"] / 1024.0) / (m["flash_us"] / 1e6)
        out["total_us"], out["reconstruct_us"] = m["stream_us"], m["feed_us"]
    if serial["metrics"]:
        out["decrypt_avg_us"], out["decrypt_max_us"] = serial["metrics"][-1]["avg_us"], serial["metrics"][-1]["max_us"]
    try:
        h = peak_heap(serial["mem"], "stream-start", "stream-end")
        out["heap_min_free"], out["heap_peak_used"] = h["end_min"], h["peak_bytes"]
    except (ValueError, KeyError, TypeError):
        pass
    return out


def gateway_columns(rec: dict | None) -> dict:
    """Table 3 cells from a gateway telemetry record."""
    if not rec:
        return {}
    return {"poll_ms": rec.get("poll_ms"), "sha_ms": rec.get("sha_ms"), "encap_ms": rec.get("encap_ms"),
            "gw_ram_mb": rec.get("peak_rss_mb"), "gw_cpu_pct": rec.get("peak_cpu_pct"),
            "to_dota_ms": rec.get("to_dota_ms"), "download_ms": rec.get("download_ms")}


def static_ram_kb(updater_increment_bytes: int) -> float:
    """Table 2 'ESP32 Peak RAM': static RAM of our technology only (updater minus the Wi-Fi-only control), in KB."""
    return round(updater_increment_bytes / 1024.0, 2)


# ============================================================= orchestration (rig injected)
class RigError(RuntimeError):
    """The harness could not do its part (flash failed, chain down, ...): the cycle is `invalid`."""


def run_cycle(rig, slot: Slot, static_ram: float | None, with_device: bool = True) -> dict:
    """One cycle on a rig. Returns the campaign-row fields (status, note and the measured cells)."""
    t0 = time.time()
    try:
        if with_device:
            rig.prepare()
        pub = rig.publish(slot.scenario)
        staged = rig.wait_staged()
    except RigError as e:
        return {"status": "invalid", "note": str(e)}
    if not staged.get("ok"):
        rig.cleanup()
        return {"status": "invalid", "note": "the gateway did not stage the release in time"}
    row = {"payload_bytes": pub.get("payload_bytes"), "diff_ms": pub.get("diff_ms"), "gas_propose": pub.get("gas_propose"),
           "gas_approve": pub.get("gas_approve"), "chain_ms": pub.get("chain_ms"), "blocks": staged.get("blocks"),
           "stage_ms": staged.get("stage_ms")}
    if not with_device:
        gw = rig.gateway_record()
        rig.cleanup()
        row.update(gateway_columns(gw))
        row["status"], row["note"] = (("ok", "gateway profiled") if gw else ("invalid", "no telemetry record for this release"))
        return row
    try:
        rig.capture_start()
        log_text = rig.run_update(UPDATE_TIMEOUT_S.get(slot.scenario, 240))
        capture_text = rig.capture_stop()
    except RigError as e:
        rig.cleanup()
        return {"status": "invalid", "note": str(e)}
    gw = rig.gateway_record()
    rig.cleanup()
    serial = parse_log(log_text)
    ttc = compute_ttc(parse_tshark(capture_text), rig.lan_ip)
    status, note = judge_cycle(serial, ttc)
    row.update(device_columns(serial))
    row.update(gateway_columns(gw))
    row["static_ram_kb"] = static_ram
    if ttc.get("ok"):
        row.update({"ttc_ms": ttc["ttc_ms"], "wire_bytes": ttc["wire_bytes"], "requests": ttc["requests"],
                    "retransmissions": ttc["retransmissions"]})
    row["status"], row["note"] = status, f"{note} ({time.time() - t0:.0f} s)"
    return row


def run_campaign(rig, store: TrialStore, schedule: list[Slot], static_ram: float | None, *, with_device: bool = True,
                 git_revision: str = "", say=print) -> int:
    """Run (or resume) every remaining slot; returns the number of rows written."""
    written = 0
    todo = store.remaining(schedule)
    say(f"[cycles] {len(todo)} cycle(s) to run.")
    for slot in todo:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            res = run_cycle(rig, slot, static_ram, with_device)
            row = {"scenario": slot.scenario, "trial": slot.trial, "warmup": slot.warmup, "round": slot.round,
                   "position": slot.position, "started_utc": started, "git_revision": git_revision, **res}
            row["note"] = f"attempt {attempt}: {row.get('note', '')}"
            store.append(row)
            written += 1
            if with_device and hasattr(rig, "note_result"):
                rig.note_result(res["status"])
            if res["status"] != "invalid":
                break
        tag = "warm-up " if slot.warmup else ""
        say(f"[cycles] {tag}{slot.scenario} {slot.trial}: {res['status']} - {res.get('note', '')[:90]}")
    return written


# ============================================================= real rigs (exercised at the pilot)
def read_ota_key(project: Path) -> str:
    m = re.search(r'DELTA_OTA_KEY_HEX\s+"([0-9a-fA-F]{32})"', (project / "include" / "secrets.h").read_text(encoding="utf-8"))
    if not m:
        raise RigError("include/secrets.h has no DELTA_OTA_KEY_HEX")
    return m.group(1).lower()


class _BaseRig:
    """The chain and the release publishing, shared by both rigs."""

    def __init__(self, ctx, lan_ip: str, firmware_dir=None, hardhat_port: int = 18545, say=print):
        pair = sop1.find_real_pair(firmware_dir)
        if not pair:
            raise RigError("release images app-v1.0.bin / app-v1.1.bin not found (--firmware-dir)")
        self.ctx, self.lan_ip, self.say, self.hardhat_port = ctx, lan_ip, say, hardhat_port
        self.base, self.target = pair
        self.project = self.base.parents[1]
        self.work = ctx.sub("work_cycles")
        self.artifacts = self.work / "artifacts"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.node = self.chain = None
        self._last_seq = 0

    def _publish(self, scenario: str) -> dict:
        import bsdiff4
        base, target = self.base.read_bytes(), self.target.read_bytes()
        t0 = time.perf_counter()
        payload = bsdiff4.diff(base, target) if scenario == "A" else target
        diff_ms = (time.perf_counter() - t0) * 1000.0 if scenario == "A" else None
        golden = hashlib.sha256(payload).hexdigest()
        (self.artifacts / f"patch_{VERSION}.bin").write_bytes(payload)
        url = f"http://{self.lan_ip}:8000/patch_{VERSION}.bin"
        p = self.chain.propose(VERSION, golden, url, 0)
        a = self.chain.approve(VERSION, 1)
        if not (p.ok and a.ok):
            raise RigError(f"propose/approve failed: {p.error or a.error}")
        self._t_sent = p.t_sent
        return {"payload_bytes": len(payload), "diff_ms": diff_ms, "gas_propose": p.gas_used, "gas_approve": a.gas_used,
                "chain_ms": (a.t_mined - p.t_sent) * 1000.0}

    def _revoke(self) -> None:
        self.chain.revoke(VERSION, 2)

    def _start_chain(self, bind: str) -> None:
        from .chain import Chain, HardhatNode
        self.node = HardhatNode(self.hardhat_port, self.ctx.sub("raw") / "cycles-node.log", bind=bind)
        self.node.start()
        self.chain = Chain(self.node.url)
        self.address = self.chain.deploy()

    def _stop_chain(self) -> None:
        if self.node:
            self.node.stop()


class LocalRig(_BaseRig):
    """Scenarios A and B: gateway process on this PC, ESP32 on the serial port, capture with tshark."""

    def __init__(self, ctx, *, serial_port: str, lan_ip: str, iface: str, firmware_dir=None, hardhat_port: int = 18545, say=print):
        super().__init__(ctx, lan_ip, firmware_dir, hardhat_port, say)
        self.serial_port, self.iface = serial_port, iface
        self._full_reset = False
        self.gw = self.ser = None
        self._tshark = self._pcap = None

    def __enter__(self):
        from .gateway_proc import GatewayProc
        from .serial_capture import SerialCapture
        raw = self.ctx.sub("raw")
        self._start_chain("127.0.0.1")
        self.gw = GatewayProc(self.node.url, self.address, self.work, raw / "cycles-gateway.log", bind=self.lan_ip,
                              key_hex=read_ota_key(self.project), artifact_server=True,
                              extra_env={"DELTA_METRICS": "1", "DELTA_METRICS_FILE": str(self.work / "gateway_metrics.json")})
        self.gw.start()
        ready, _ = self.gw.wait_for(lambda s: s.get("gateway_state") == "waiting", 90)
        if not ready:
            raise RigError("gateway did not reach 'waiting' - see raw/cycles-gateway.log")
        self.ser = SerialCapture(self.serial_port).open()
        return self

    def __exit__(self, *exc):
        if self.ser:
            self.ser.close()
        if self.gw:
            self.gw.stop()
        self._stop_chain()

    def note_result(self, status: str) -> None:
        self._full_reset = status == "failed"        # a version recorded as failed is never retried: wipe and re-provision

    def _flash(self, mode: str) -> None:
        bat = self.project / "tools" / "flash_device.bat"
        args = [str(bat), mode, self.serial_port] + (["v1.0"] if mode == "app" else [])
        env = {**os.environ, "NOPAUSE": "1"}
        r = subprocess.run(args, cwd=self.project, env=env, capture_output=True, text=True, timeout=600)
        (self.ctx.sub("raw") / f"flash-{mode}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        if r.returncode != 0:
            raise RigError(f"flash_device.bat {mode} failed (exit {r.returncode})")

    def prepare(self) -> None:
        self.ser.close()
        self._flash("reset" if self._full_reset else "app")
        self._full_reset = False
        from .serial_capture import SerialCapture
        self.ser = SerialCapture(self.serial_port).open()
        self.ser.reset_board()
        self.ser.capture(60, until=r"Starting application")        # let the v1.0 app run once so it registers itself
        time.sleep(4)

    def publish(self, scenario: str) -> dict:
        return self._publish(scenario)

    def wait_staged(self) -> dict:
        ok, st = self.gw.wait_for(lambda s: s.get("gateway_state") == "staged" and s.get("staged_version") == VERSION
                                  and s.get("staged_at", 0) >= self._t_sent, 90)
        return {"ok": bool(ok), "blocks": st.get("blocks_total"),
                "stage_ms": ((st.get("staged_at", 0) - self._t_sent) * 1000.0) if ok else None}

    def capture_start(self) -> None:
        self._pcap = self.work / "cycle.pcap"
        self._pcap.unlink(missing_ok=True)
        self._tshark = subprocess.Popen([str(TSHARK), "-i", self.iface, "-f", "udp port 5683", "-w", str(self._pcap)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.0)                                            # let the capture attach before the device speaks

    def run_update(self, timeout: float) -> str:
        self.ser.reset_board()
        return self.ser.capture(timeout, until=r"Application: v1\.1")

    def capture_stop(self) -> str:
        time.sleep(1.0)
        if self._tshark:
            self._tshark.terminate()
            try:
                self._tshark.wait(10)
            except subprocess.TimeoutExpired:
                self._tshark.kill()
        cmd = [str(TSHARK), "-r", str(self._pcap), "-Y", "coap", "-T", "fields", "-E", "separator=/t"]
        for f in TSHARK_FIELDS:
            cmd += ["-e", f]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        shutil.copy(self._pcap, self.ctx.sub("raw") / f"cycle-{int(time.time())}.pcap")
        return r.stdout

    def gateway_record(self) -> dict | None:
        try:
            doc = json.loads((self.work / "gateway_metrics.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        rec = pick_gateway_record(doc, VERSION, self._last_seq)
        if rec:
            self._last_seq = rec["seq"]
        return rec

    def cleanup(self) -> None:
        self._revoke()
        self.gw.wait_for(lambda s: s.get("gateway_state") == "revoked", 30)


class GatewayRig(_BaseRig):
    """Table 3: the gateway runs on the Raspberry Pi; this PC hosts the chain and the patch and reads the Pi over HTTP."""

    def __init__(self, ctx, *, gateway_url: str, lan_ip: str, firmware_dir=None, hardhat_port: int = 8545, say=print, fetch=None):
        super().__init__(ctx, lan_ip, firmware_dir, hardhat_port, say)
        self.gateway_url = gateway_url.rstrip("/")
        self._fetch = fetch or self._http_json
        self._server = None

    @staticmethod
    def _http_json(url: str) -> dict:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))

    def status(self) -> dict:
        try:
            return self._fetch(f"{self.gateway_url}/gateway_status.json")
        except Exception:
            return {}

    def __enter__(self):
        import serve_artifacts
        self._start_chain("0.0.0.0")                                # the Pi must reach the node
        os.environ["DELTA_ARTIFACT_DIR"] = str(self.artifacts)
        self._server = serve_artifacts.make_server(8000)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.say(f"[table3] node on {self.lan_ip}:{self.hardhat_port}, contract {self.address}, patches on :8000.")
        self.say(f"[table3] the Pi must use: install-gateway.sh rpc http://{self.lan_ip}:{self.hardhat_port}  and  contract {self.address}")
        deadline = time.time() + 300
        while time.time() < deadline:
            st = self.status()
            if st.get("contract", "").lower() == self.address.lower() and st.get("gateway_state") in ("waiting", "revoked", "staged"):
                return self
            time.sleep(2)
        raise RigError("the Pi gateway did not report this contract within 5 minutes")

    def __exit__(self, *exc):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        self._stop_chain()

    def publish(self, scenario: str) -> dict:
        return self._publish("A")

    def wait_staged(self) -> dict:
        deadline = time.time() + 120
        st: dict = {}
        while time.time() < deadline:
            st = self.status()
            if st.get("gateway_state") == "staged" and st.get("staged_version") == VERSION and st.get("staged_at", 0) >= self._t_sent:
                return {"ok": True, "blocks": st.get("blocks_total"), "stage_ms": (st["staged_at"] - self._t_sent) * 1000.0}
            time.sleep(0.5)
        return {"ok": False}

    def gateway_record(self) -> dict | None:
        try:
            doc = self._fetch(f"{self.gateway_url}/gateway_metrics.json")
        except Exception:
            return None
        rec = pick_gateway_record(doc, VERSION, self._last_seq)
        if rec:
            self._last_seq = rec["seq"]
        return rec

    def cleanup(self) -> None:
        self._revoke()
        deadline = time.time() + 40
        while time.time() < deadline and self.status().get("gateway_state") != "revoked":
            time.sleep(0.5)


# ============================================================= command line
def plan_text(args, schedule: list[Slot]) -> str:
    n = len(schedule)
    per = 100 if not args.table3 else 25
    return (f"{n} cycle(s) ({'Table 3 gateway profiling' if args.table3 else 'Scenarios ' + args.scenarios}), "
            f"about {n * per / 3600:.1f} h at ~{per} s each; trials={args.trials} warm-up={args.warmup}")


def main(argv=None) -> int:
    from .runlog import RunContext
    ap = argparse.ArgumentParser(description="Run Scenarios A/B (Table 2) or the Table 3 gateway cycles.")
    ap.add_argument("--scenarios", default="A,B")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--run", help="existing run directory to add to / resume (default: a new one)")
    ap.add_argument("--serial", help="ESP32 serial port, e.g. COM3 (Table 2)")
    ap.add_argument("--lan-ip", help="this PC's LAN address (the gateway binds to it; the ESP32 must point at it)")
    ap.add_argument("--iface", default="6", help="tshark capture interface number or name (default 6 = Ethernet)")
    ap.add_argument("--firmware-dir")
    ap.add_argument("--table3", action="store_true", help="gateway-only profiling cycles against a gateway on the Pi")
    ap.add_argument("--gateway-url", help="Table 3: the Pi's artifact server, e.g. http://192.168.100.50:8000")
    ap.add_argument("--static-ram-bytes", type=int, default=29400, help="Table 2 RAM column: updater static RAM increment (SOP 4)")
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--dry-run", action="store_true", help="print the plan and touch nothing")
    args = ap.parse_args(argv)

    scenarios = ("T3",) if args.table3 else tuple(s.strip().upper() for s in args.scenarios.split(","))
    schedule = make_schedule(trials=args.trials, warmup=args.warmup, seed=args.seed, scenarios=scenarios)
    print(plan_text(args, schedule))
    if args.dry_run:
        return 0
    if not args.lan_ip:
        ap.error("--lan-ip is required")
    if args.table3 and not args.gateway_url:
        ap.error("--table3 needs --gateway-url")
    if not args.table3 and not args.serial:
        ap.error("--serial is required for Scenarios A and B")
    ctx = RunContext(Path(args.run)) if args.run else RunContext.new()
    store = TrialStore(ctx.dir / "campaign" / ("table3.csv" if args.table3 else "trials.csv"))
    git = ctx.meta.get("git_commit", "")
    ram = static_ram_kb(args.static_ram_bytes)
    rig = (GatewayRig(ctx, gateway_url=args.gateway_url, lan_ip=args.lan_ip, firmware_dir=args.firmware_dir) if args.table3
           else LocalRig(ctx, serial_port=args.serial, lan_ip=args.lan_ip, iface=args.iface, firmware_dir=args.firmware_dir))
    with rig:
        run_campaign(rig, store, schedule, ram, with_device=not args.table3, git_revision=git)
    print(f"Cycles: {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
