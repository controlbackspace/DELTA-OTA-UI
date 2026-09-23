"""Live-ledger driver (Day 1 baseline + Day 2 kill-switch).

Resets gateway state to v1.0, launches the REAL main_gateway.py (real web3
BlockchainPoller, no mocks) as a subprocess, then asserts the mode outcome:

  DRIVER_MODE=baseline     wait for state -> TARGET + artifact, fetch [OK]
  DRIVER_MODE=kill-revoke  gateway halts on revoked release, fetch [TIMEOUT]
  DRIVER_MODE=kill-mismatch gateway destroys artifact, fetch [BLOCKED] (4.01)

Requires: hardhat node up + v1.1 on-chain in the matching state (see
blockchain/scripts/propose-v11.js: default, REVOKE_RELEASE=1, BAD_HASH=1)
+ DELTA_CONTRACT_ADDRESS set in env. Gateway stdout is tee'd to
testing-deliverables/<EVIDENCE_DAY>/<GATEWAY_LOG>.

Run:  DELTA_CONTRACT_ADDRESS=0x... [DRIVER_MODE=...] [EVIDENCE_DAY=...] \
        python simulation/ledger_live_run.py
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

# DRIVER_MODE=baseline   (default): expect update + [OK]  (Day 1)
# DRIVER_MODE=kill-revoke: expect gateway HALT, no artifact, device [TIMEOUT] (Day 2)
# DRIVER_MODE=kill-mismatch: expect hash-mismatch destroy, device [BLOCKED] 4.01 (Day 2)
DRIVER_MODE = os.environ.get("DRIVER_MODE", "baseline")
# Gateway transcript filename inside EVIDENCE_DIR (override per run).
GATEWAY_LOG_NAME = os.environ.get(
    "GATEWAY_LOG",
    "05-gateway-kill.log" if DRIVER_MODE.startswith("kill") else "05-gateway-live.log",
)


def check(label, actual, expected):
    """Assert-pass/fail with a clear verdict line."""
    global FAILURES
    ok = actual == expected
    display = actual.decode(errors="replace") if isinstance(actual, bytes) else actual
    print(f"    -> [{'PASS' if ok else 'FAIL'}] {label}: got {display!r} (expected {expected!r})")
    if not ok:
        FAILURES += 1
    return ok


def launch_gateway():
    """Spawn the real main_gateway.py with unbuffered stdout to the log file."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    gateway_log = open(EVIDENCE_DIR / GATEWAY_LOG_NAME, "w")
    proc = subprocess.Popen(
        [sys.executable, "-u", "main_gateway.py"],
        cwd=str(RUNTIME_DIR),
        stdout=gateway_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, gateway_log


def stop_gateway(proc, gateway_log):
    """Terminate (escalating to kill) and close the log file."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    gateway_log.close()


def wait_for_proc_exit(proc, deadline):
    """True if the gateway process exits on its own before the deadline."""
    while time.time() < deadline:
        if proc.poll() is not None:
            return True
        time.sleep(0.5)
    return False


def wait_for_log_marker(marker, deadline):
    """True if the gateway transcript contains marker before the deadline."""
    log_path = EVIDENCE_DIR / GATEWAY_LOG_NAME
    while time.time() < deadline:
        try:
            if marker in log_path.read_text(errors="replace"):
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def run_baseline(proc):
    """Day 1: wait for state -> TARGET plus artifact, then expect [OK]."""
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
        print(f"[Driver] Gateway did not update in time - see {GATEWAY_LOG_NAME}.")
        return False

    status, detail = asyncio.run(fetch_firmware(get_lan_ip()))
    print(f"    [Device] {status}: {detail!r}" if isinstance(detail, bytes) else f"    [Device] {status}: {detail}")
    check("device verdict", status, "[OK]")
    if status == "[OK]":
        check("decrypted bytes", detail, DUMMY_PATCH.read_bytes())
    return True


def run_kill_revoke(proc):
    """Day 2a: revoked release -> gateway halts itself -> device [TIMEOUT]."""
    halted = wait_for_proc_exit(proc, time.time() + 30.0)
    check("gateway halted on revoke", halted, True)
    if halted:
        check("gateway exit code", proc.returncode, 0)
    check("gateway log shows revoke halt",
          wait_for_log_marker("has been revoked on-chain", time.time() + 5.0), True)
    try:
        installed = json.loads(STATE_FILE.read_text())["installed_version"]
    except (OSError, ValueError, KeyError):
        installed = None
    check("installed version unchanged", installed, "v1.0")
    check("no encrypted artifact served", ENCRYPTED_PATCH.exists(), False)

    status, detail = asyncio.run(fetch_firmware(get_lan_ip()))
    print(f"    [Device] {status}: {detail}")
    check("device verdict", status, "[TIMEOUT]")
    return True


def run_kill_mismatch(proc):
    """Day 2b: wrong golden hash -> artifact destroyed -> device [BLOCKED] 4.01."""
    seen = wait_for_log_marker("Hash Mismatch!", time.time() + 30.0)
    check("gateway logged hash mismatch", seen, True)
    try:
        installed = json.loads(STATE_FILE.read_text())["installed_version"]
    except (OSError, ValueError, KeyError):
        installed = None
    check("installed version unchanged", installed, "v1.0")
    check("encrypted artifact destroyed", ENCRYPTED_PATCH.exists(), False)

    status, detail = asyncio.run(fetch_firmware(get_lan_ip()))
    print(f"    [Device] {status}: {detail}")
    check("device verdict", status, "[BLOCKED]")
    return True


RESULT_LINES = {
    "baseline": "LIVE-LEDGER RESULT: BASELINE GREEN",
    "kill-revoke": "KILL-SWITCH RESULT: REVOKE GREEN",
    "kill-mismatch": "KILL-SWITCH RESULT: MISMATCH GREEN",
}


def main():
    if not os.environ.get("DELTA_CONTRACT_ADDRESS"):
        print("[Driver] FATAL: DELTA_CONTRACT_ADDRESS is not set (run deploy.js first).")
        sys.exit(2)
    if DRIVER_MODE not in RESULT_LINES:
        print(f"[Driver] FATAL: unknown DRIVER_MODE={DRIVER_MODE!r} "
              f"(expected one of {sorted(RESULT_LINES)}).")
        sys.exit(2)

    STATE_FILE.write_text(json.dumps({"installed_version": "v1.0"}))
    ENCRYPTED_PATCH.unlink(missing_ok=True)
    print(f"[Driver] State reset to v1.0 (target {TARGET_VERSION}, mode {DRIVER_MODE}). "
          f"Launching real gateway...")

    proc, gateway_log = launch_gateway()
    try:
        if DRIVER_MODE == "baseline":
            ok = run_baseline(proc)
        elif DRIVER_MODE == "kill-revoke":
            ok = run_kill_revoke(proc)
        else:
            ok = run_kill_mismatch(proc)
        if not ok:
            sys.exit(1)
    finally:
        # kill-revoke already exited on its own; terminate() on a dead proc is a no-op.
        stop_gateway(proc, gateway_log)

    print("\n" + "=" * 62)
    if FAILURES == 0:
        print(f"  {RESULT_LINES[DRIVER_MODE]}")
    else:
        print(f"  LIVE-LEDGER RESULT: {FAILURES} CHECK(S) FAILED")
    print("=" * 62)
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
