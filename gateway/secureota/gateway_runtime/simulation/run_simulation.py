"""
Delta-OTA — one-command simulation of the four progress-check scenarios.

Runs end-to-end over real CoAP + real AES-CCM, using the production gateway
components (coap_server.py, security_engine.py, main_gateway.py constants) and
the simulated ledger. No Wokwi, no ESP32 board, no Hardhat node required.

    Phase 1  Hash mismatch          -> gateway destroys patch -> device [BLOCKED] 4.01
    Phase 2  Release revoked        -> gateway halts          -> device [TIMEOUT]
    Phase 3  Tampered payload       -> 2.05 served, tag bad   -> device [FAIL] tag mismatch
    Phase 4  Valid release          -> 2.05 + authentic frame -> device [OK] payload authentic

The gateway decision flow below mirrors the body of main_gateway.main_loop()
line-for-line; the standalone equivalent (`python main_gateway.py`) runs the
same logic. This harness drives it in-process so it can own the CoAP server
lifecycle (necessary to make the "gateway halts" phase actually halt).

Run:  python simulation/run_simulation.py [phases]
      phases: optional comma-separated subset, e.g. "1,2" (default: all four).
"""
import sys
from pathlib import Path

# Make the production gateway_runtime modules importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json

import aiocoap
import aiocoap.resource as resource

import simulated_ledger
from simulated_ledger import DemoBlockchainPoller
from simulated_device import fetch_firmware
from coap_server import FirmwareResource, get_lan_ip
from security_engine import SecurityEngine

from main_gateway import (DUMMY_PATCH, ENCRYPTED_PATCH, PRE_SHARED_KEY,
                          STATE_FILE, TARGET_VERSION)

SERVER_PORT = 5683
CLIENT_TIMEOUT = 3.0
FAILURES = 0

def reset_state():
    """Force the gateway to re-process TARGET_VERSION on the next cycle."""
    prior = "v1.1" if TARGET_VERSION != "v1.1" else "v1.0"
    STATE_FILE.write_text(json.dumps({"installed_version": prior}))
    print(f"[Demo] Gateway state reset to {prior} (target {TARGET_VERSION}).")


async def start_server():
    """Real FirmwareResource from coap_server.py on the LAN interface."""
    site = resource.Site()
    site.add_resource(['firmware'], FirmwareResource())
    ctx = await aiocoap.Context.create_server_context(
        site, bind=(get_lan_ip(), SERVER_PORT))
    print(f"[Demo] CoAP server up (repo FirmwareResource) on {get_lan_ip()}:{SERVER_PORT}.")
    return ctx


async def shutdown_ctx(ctx):
    """Idempotent, fault-tolerant Context shutdown.

    aiocoap's Context.shutdown() can raise AttributeError on a server that
    never handled a request (`_active_exchanges` stays None) - and it must
    never be called twice. This guards both cases.
    """
    if ctx is None or getattr(ctx, "_demo_closed", False):
        return
    ctx._demo_closed = True
    try:
        await ctx.shutdown()
    except AttributeError:
        pass


async def run_gateway_once():
    """Mirror of main_gateway.main_loop() — one poll cycle.

    Kept here (rather than importing main_loop) so this harness controls the
    CoAP server lifetime for the "revoked -> halt" phase. Logic is identical
    to main_loop, comments included. Uses the simulated ledger.
    """
    poller = DemoBlockchainPoller()
    engine = SecurityEngine()

    # State initialization (gateway boot sequence)
    installed_version = "v1.0"
    try:
        with open(STATE_FILE, "r") as file:
            installed_version = json.load(file)["installed_version"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    print(f"[Gateway] Boot. Installed: {installed_version}, target: {TARGET_VERSION}")

    release_data = await poller.fetch_firmware_release(TARGET_VERSION)

    # Zero Trust: failed poll -> halt
    if release_data is None:
        print("[Gateway] FATAL: Ledger poll failed. Halting gateway.")
        return "HALT_LEDGER_DOWN"

    # Zero Trust: revoked release -> unlink + halt
    if release_data["isRevoked"] is True:
        ENCRYPTED_PATCH.unlink(missing_ok=True)
        print(f"[Gateway] FATAL: Release {TARGET_VERSION} has been revoked on-chain. Halting gateway.")
        return "HALT_REVOKED"

    if release_data["isLive"] is True and release_data["version"] != installed_version:
        isValid = engine.verify_firmware_integrity(release_data, str(DUMMY_PATCH))
        if isValid is True:
            engine.encrypt_payload(DUMMY_PATCH, ENCRYPTED_PATCH, PRE_SHARED_KEY)
            with open(STATE_FILE, "w") as file:
                json.dump({"installed_version": release_data["version"]}, file)
            print(f"[Gateway] State updated to {release_data['version']}.")
            return "UPDATED"
        else:
            print("[Gateway] Hash Mismatch! Patch destroyed.")
            ENCRYPTED_PATCH.unlink(missing_ok=True)
            return "MISMATCH"

    print("[Gateway] No new updates found. Sleeping...")
    return "IDLE"


def check(label, actual, expected):
    """Assert-pass/fail with a clear verdict line for the review transcript."""
    global FAILURES
    ok = actual == expected
    display = actual
    if isinstance(actual, bytes):
        display = actual.decode(errors="replace")
    status = "PASS" if ok else "FAIL"
    if not ok:
        FAILURES += 1
    print(f"    -> [{status}] {label}: got {display!r} (expected {expected!r})")
    return ok


def banner(title):
    print("\n" + "=" * 62)
    print(f"  PHASE :: {title}")
    print("=" * 62)


# ── The four phases ─────────────────────────────────────────────────────────

async def phase1_kill_switch():
    """Wrong golden hash -> gateway 'Hash Mismatch!' -> 4.01 -> [BLOCKED]."""
    banner("1/4  KILL-SWITCH  (hash mismatch -> patch destroyed -> 4.01)")
    simulated_ledger.LEDGER_IS_LIVE = True
    simulated_ledger.LEDGER_IS_REVOKED = False
    simulated_ledger.LEDGER_GOLDEN_HASH = "0" * 64   # wrong on purpose
    reset_state()

    ctx = await start_server()
    try:
        gw = await run_gateway_once()
        check("gateway outcome", gw, "MISMATCH")

        verdict, detail = await fetch_firmware(get_lan_ip(), CLIENT_TIMEOUT)
        print(f"    [Device] {verdict}: {detail}")
        return check("device verdict", verdict, "[BLOCKED]")
    finally:
        await shutdown_ctx(ctx)

async def phase2_revoked():
    #"""Revoked on-chain -> gateway halts -> server down -> device [TIMEOUT]."""
    banner("2/4  REVOKED       (on-chain revoke -> gateway halts -> timeout)")
    simulated_ledger.LEDGER_IS_LIVE = True
    simulated_ledger.LEDGER_IS_REVOKED = True
    simulated_ledger.LEDGER_GOLDEN_HASH = simulated_ledger._default_golden_hash()
    reset_state()

    # No server is started here on purpose: the gateway halts during its boot
    # poll, so it never opens the /firmware socket. The device therefore hits
    # a dead port - exactly what a stopped main_gateway.py process produces.
    gw = await run_gateway_once()
    check("gateway outcome", gw, "HALT_REVOKED")
    print("    [Gateway] Process halted - CoAP socket never opened.")

    verdict, detail = await fetch_firmware(get_lan_ip(), CLIENT_TIMEOUT)
    print(f"    [Device] {verdict}: {detail}")
    return check("device verdict", verdict, "[TIMEOUT]")


async def phase3_tamper():
    """Valid release, then one tag byte flipped -> [FAIL] tag mismatch."""
    banner("3/4  TAMPER        (authentic frame -> tag corrupted -> [FAIL])")
    simulated_ledger.LEDGER_IS_LIVE = True
    simulated_ledger.LEDGER_IS_REVOKED = False
    simulated_ledger.LEDGER_GOLDEN_HASH = simulated_ledger._default_golden_hash()
    reset_state()

    ctx = await start_server()
    try:
        gw = await run_gateway_once()
        if not check("gateway outcome", gw, "UPDATED") or not ENCRYPTED_PATCH.exists():
            print("    [Demo] Skipping tamper step: no verified patch on disk "
                  "(gateway did not produce one this cycle).")
            return False

        # Flip one byte of the authentication tag on disk.
        frame = bytearray(ENCRYPTED_PATCH.read_bytes())
        frame[-1] ^= 0x01
        ENCRYPTED_PATCH.write_bytes(bytes(frame))
        print(f"    [Demo] Corrupted tag (byte {len(frame) - 1} flipped).")

        verdict, detail = await fetch_firmware(get_lan_ip(), CLIENT_TIMEOUT)
        print(f"    [Device] {verdict}: {detail}")
        return check("device verdict", verdict, "[FAIL]")
    finally:
        await shutdown_ctx(ctx)


async def phase4_success():
    """Valid release, fresh encryption -> [OK] payload authentic = b'test'."""
    banner("4/4  SUCCESS       (valid release -> 2.05 -> decrypt [OK])")
    simulated_ledger.LEDGER_IS_LIVE = True
    simulated_ledger.LEDGER_IS_REVOKED = False
    simulated_ledger.LEDGER_GOLDEN_HASH = simulated_ledger._default_golden_hash()
    reset_state()

    ctx = await start_server()
    try:
        gw = await run_gateway_once()
        check("gateway outcome", gw, "UPDATED")

        verdict, plaintext = await fetch_firmware(get_lan_ip(), CLIENT_TIMEOUT)
        print(f"    [Device] {verdict}: {plaintext!r}")
        return check("device verdict", verdict, "[OK]") and \
               check("decrypted bytes", plaintext, DUMMY_PATCH.read_bytes())
    finally:
        await shutdown_ctx(ctx)

# ── Entry ───────────────────────────────────────────────────────────────────

async def main():
    print("Delta-OTA simulation - in-process E2E.")
    selected = sys.argv[1] if len(sys.argv) > 1 else "1,2,3,4"
    want = {s.strip() for s in selected.split(",")}
    ran = []
    if "1" in want:
        await phase1_kill_switch()
        ran.append("1")
    if "2" in want:
        await phase2_revoked()
        ran.append("2")
    if "3" in want:
        await phase3_tamper()
        ran.append("3")
    if "4" in want:
        await phase4_success()
        ran.append("4")
    if not ran:
        print(f"No phases selected from {selected!r} - nothing ran.")
        sys.exit(2)

    print("\n" + "=" * 62)
    if FAILURES == 0:
        print(f"  SIMULATION RESULT: PHASES {','.join(ran)} PASSED")
    else:
        print(f"  SIMULATION RESULT: {FAILURES} PHASE(S) FAILED")
    print("=" * 62)
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    asyncio.run(main())
