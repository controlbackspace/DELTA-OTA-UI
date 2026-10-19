"""SOP 4, hardware part: the on-device Web3 client, N ledger checks in one boot.

    python -m sop.web3_hw --serial COM3 --lan-ip 192.168.100.94 [--runs 60] [--out <folder>] --allow-flash

What it does (the same steps as the recorded measurement of 2026-10-19):

1. starts a local Hardhat node, deploys the contract and makes release v1.1 live (2 of 3 approvals);
2. puts a TLS front on the LAN (self-signed ECDSA P-256 certificate, TLS 1.2, port 8545) in front of the node, because the
   baseline firmware speaks HTTPS; the firmware does not validate the certificate, as stated in the SOP 4 limitations;
3. flashes the `web3_baseline` build with `-DWEB3_RUNS=<runs>` (sop4.hw_session erases otadata after the upload so the
   factory slot boots), captures the serial output, and restores the factory updater;
4. writes the log, the parsed result and the certificate into <out>.

Afterwards put the board back in demonstration state with `tools\\flash_device.bat reset COMx` (firmware repo).
It replaces the factory updater until restored, so it needs --allow-flash.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
import ssl
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import footprint as fp, sop4
from .chain import Chain, HardhatNode
from .runlog import DEFAULT_RESULTS_ROOT, RunContext


def build_flags(host: str, port: int, contract: str, version: str, runs: int) -> str:
    """The PLATFORMIO_BUILD_FLAGS string for the baseline build (quotes as the compiler needs them)."""
    return " ".join([f'-DWEB3_RPC_HOST=\\"{host}\\"', f"-DWEB3_RPC_PORT={port}", f'-DWEB3_CONTRACT=\\"{contract}\\"',
                     f'-DWEB3_VERSION_TAG=\\"{version}\\"', f"-DWEB3_RUNS={runs}"])


def make_certificate(lan_ip: str, cert_path: Path, key_path: Path) -> None:
    """A throwaway self-signed ECDSA P-256 certificate for the LAN address (like the ECDHE-ECDSA handshake of SOP 2)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, lan_ip)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(lan_ip))]), False)
            .sign(key, hashes.SHA256()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


def tls_front(lan_port: int, node_port: int, cert: Path, key: Path) -> ThreadingHTTPServer:
    """An HTTPS server that forwards each JSON-RPC POST to the plain local node."""
    class Front(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            req = urllib.request.Request(f"http://127.0.0.1:{node_port}", body, {"Content-Type": "application/json"})
            data = urllib.request.urlopen(req, timeout=10).read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def log_message(self, *a):
            pass

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2          # the Arduino-ESP32 mbedTLS client speaks TLS 1.2
    ctx.load_cert_chain(str(cert), str(key))
    httpd = ThreadingHTTPServer(("0.0.0.0", lan_port), Front)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run(serial: str, lan_ip: str, runs: int, out: Path, project: Path, lan_port: int = 8545, node_port: int = 18545) -> dict:
    ctx = RunContext(out.resolve())
    raw = ctx.sub("raw")
    cert, key = raw / "front-cert.pem", raw / "front-key.pem"
    make_certificate(lan_ip, cert, key)
    node, httpd = HardhatNode(node_port, raw / "hardhat-node.log"), None
    try:
        node.start()
        chain = Chain(node.url)
        address = chain.deploy()
        p = chain.propose("v1.1", hashlib.sha256(b"sop4-hw-web3").hexdigest(), f"http://{lan_ip}:8000/patch_v1.1.bin", 0)
        a = chain.approve("v1.1", 1)
        if not (p.ok and a.ok):
            raise RuntimeError(f"propose/approve failed: {p.error or a.error}")
        httpd = tls_front(lan_port, node_port, cert, key)
        pio = fp.find_pio()
        if pio is None:
            raise RuntimeError("PlatformIO (pio) not found")
        flags = build_flags(lan_ip, lan_port, address, "v1.1", runs)
        hw = sop4.hw_session(ctx, project, pio, serial, flags, capture_seconds_for(runs))
        (out / "parsed.json").write_text(json.dumps(hw.get("parsed") or {}, indent=1, default=str), encoding="utf-8")
        return hw
    finally:
        # the throwaway TLS key is not kept
        key.unlink(missing_ok=True)
        if httpd:
            httpd.shutdown()
        node.stop()


def capture_seconds_for(runs: int) -> int:
    """About 2 s per check plus start-up, with headroom."""
    return max(120, int(runs * 4 + 60))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--lan-ip", required=True, help="this PC's LAN address (the ESP32 connects here)")
    ap.add_argument("--runs", type=int, default=60)
    ap.add_argument("--project", help="the firmware project (default: found automatically)")
    ap.add_argument("--out", help="output folder (default: sop-results/sop4-hw-web3-<stamp>)")
    ap.add_argument("--allow-flash", action="store_true", help="authorise replacing the factory updater until it is restored")
    a = ap.parse_args(argv)
    if not a.allow_flash:
        print("This replaces the factory updater until it is restored: pass --allow-flash.")
        return 2
    out = Path(a.out) if a.out else DEFAULT_RESULTS_ROOT / f"sop4-hw-web3-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}"
    project = fp.find_project(a.project)
    if project is None:
        print("Firmware project not found: pass --project.")
        return 2
    hw = run(a.serial, a.lan_ip, a.runs, out, Path(project))
    ok = [w for w in (hw.get("parsed") or {}).get("web3", []) if w.get("ok")]
    print(f"{len(ok)} of {a.runs} checks ok; factory updater restored: {hw.get('restored')}; output: {out}")
    print(f"Next: tools\\flash_device.bat reset {a.serial}   (demonstration state)")
    return 0 if len(ok) == a.runs and hw.get("restored") else 1


if __name__ == "__main__":
    raise SystemExit(main())
