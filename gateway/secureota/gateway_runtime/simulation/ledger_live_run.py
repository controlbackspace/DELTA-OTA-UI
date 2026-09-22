"""Live-ledger baseline driver (Day 1, Deliverable 1).

Resets gateway state to v1.0, launches the REAL main_gateway.py (real web3
BlockchainPoller, no mocks) as a subprocess, waits for state -> TARGET plus
encrypted_patch.bin, fetches /firmware via the simulated device against the
live server, then terminates the gateway.

Requires: hardhat node up + v1.1 proposed and approved on-chain (see
blockchain/scripts/propose-v11.js) + DELTA_CONTRACT_ADDRESS set in env.
Gateway stdout is tee'd to testing-deliverables/<EVIDENCE_DAY>/05-gateway-live.log.

Run:  DELTA_CONTRACT_ADDRESS=0x... python simulation/ledger_live_run.py
"""
import sys
from pathlib import Path

# Make the production gateway_runtime modules importable regardless of CWD.
RUNTIME_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_DIR))

import asyncio
import json
import os
import subprocess
import time

from coap_server import get_lan_ip
from simulated_device import fetch_firmware
from main_gateway import DUMMY_PATCH, ENCRYPTED_PATCH, STATE_FILE, TARGET_VERSION

EVIDENCE_DAY = os.environ.get("EVIDENCE_DAY", "day-01-2026-09-23")
EVIDENCE_DIR = Path(__file__).resolve().parents[4] / "testing-deliverables" / EVIDENCE_DAY
TIMEOUT = 45.0
FAILURES = 0


def check(label, actual, expected):
    """Assert-pass/fail with a clear verdict line."""
    global FAILURES
    ok = actual == expected
    display = actual.decode(errors="replace") if isinstance(actual, bytes) else actual
    print(f"    -> [{'PASS' if ok else 'FAIL'}] {label}: got {display!r} (expected {expected!r})")
    if not ok:
        FAILURES += 1
    return ok


def main():
    if not os.environ.get("DELTA_CONTRACT_ADDRESS"):
        print("[Driver] FATAL: DELTA_CONTRACT_ADDRESS is not set (run deploy.js first).")
        sys.exit(2)

    STATE_FILE.write_text(json.dumps({"installed_version": "v1.0"}))
    ENCRYPTED_PATCH.unlink(missing_ok=True)
    print(f"[Driver] State reset to v1.0 (target {TARGET_VERSION}). Launching real gateway...")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    gateway_log = open(EVIDENCE_DIR / "05-gateway-live.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-u", "main_gateway.py"],
        cwd=str(RUNTIME_DIR),
        stdout=gateway_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + TIMEOUT
        updated = False
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                installed = json.loads(STATE_FILE.read_text())["installed_version"]
            except (OSError, ValueError, KeyError):
                continue
            if installed == TARGET_VERSION and ENCRYPTED_PATCH.exists():
                updated = True
                break
        check("gateway applied update", updated, True)
        if not updated:
            print("[Driver] Gateway did not update in time - see 05-gateway-live.log.")
            sys.exit(1)

        status, detail = asyncio.run(fetch_firmware(get_lan_ip()))
        print(f"    [Device] {status}: {detail!r}" if isinstance(detail, bytes) else f"    [Device] {status}: {detail}")
        check("device verdict", status, "[OK]")
        if status == "[OK]":
            check("decrypted bytes", detail, DUMMY_PATCH.read_bytes())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        gateway_log.close()

    print("\n" + "=" * 62)
    if FAILURES == 0:
        print("  LIVE-LEDGER RESULT: BASELINE GREEN")
    else:
        print(f"  LIVE-LEDGER RESULT: {FAILURES} CHECK(S) FAILED")
    print("=" * 62)
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
