"""Simulated-ledger test for the gateway flow, no Hardhat contract required.

Verifies: boot sequence -> poll -> verify -> encrypt -> state update.
The blockchain response is faked, so the whole pipeline can be exercised
before the real contract is deployed.

Usage (from gateway_runtime/):
    python test_gateway_flow.py
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

import main_gateway

ARTIFACT_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"
DUMMY_PATCH = ARTIFACT_DIR / "dummy_patch.bin"
ENCRYPTED_PATCH = ARTIFACT_DIR / "encrypted_patch.bin"
STATE_FILE = ARTIFACT_DIR / "gateway_state.json"


class _StopTestLoop(Exception):
    """Raised by the fake poller to end the infinite gateway loop."""


class FakeBlockchainPoller:
    """Drop-in replacement for BlockchainPoller (no Web3 connection needed)."""

    def __init__(self):
        print("[Test] FakeBlockchainPoller booted (no Hardhat required).")
        self._pending = None

    async def fetch_firmware_release(self, version_tag):
        print(f"[Test] Ledger asked about version '{version_tag}'")
        if self._pending is not None:
            release = self._pending
            self._pending = None
            return release
        raise _StopTestLoop()


async def run_flow_test():
    print("\n=== TEST 1: Full gateway flow with simulated live release ===")

    # Force the update path: reset state to v1.0
    with open(STATE_FILE, "w") as file:
        json.dump({"installed_version": "v1.0"}, file)

    # The fake ledger returns the real golden hash of the dummy patch,
    # so fetch_and_verify_payload must succeed.
    with open(DUMMY_PATCH, "rb") as file:
        golden_hash = hashlib.file_digest(file, "sha256").hexdigest()

    class FakePoller(FakeBlockchainPoller):
        def __init__(self):
            super().__init__()
            self._pending = {
                "version": main_gateway.TARGET_VERSION,
                "goldenHash": golden_hash,
                "ipfsUrl": "ipfs://test-cid",
                "approvalCount": 2,
                "isLive": True,
                "isRevoked": False,
            }

    main_gateway.BlockchainPoller = FakePoller

    try:
        await main_gateway.main_loop()
    except _StopTestLoop:
        pass

    with open(STATE_FILE, "r") as file:
        state = json.load(file)

    assert state["installed_version"] == main_gateway.TARGET_VERSION, (
        f"State was not updated: {state['installed_version']}"
    )
    assert ENCRYPTED_PATCH.exists(), "Encrypted patch was not produced"
    print(f"[Test] PASS: Gateway applied {state['installed_version']} and encrypted payload is ready.")


async def run_offline_check():
    print("\n=== TEST 2: Zero-trust guard with no Hardhat node ===")

    from blockchain_poller import BlockchainPoller

    poller = BlockchainPoller()

    result = await poller.fetch_firmware_release("v1.1")

    if result is None:
        print("[Test] PASS: poller returned None (main_gateway will halt safely).")
    elif result["isLive"] is False:
        print("[Test] NOTE: node answered but release is not live (main_gateway will just sleep).")
    else:
        print("[Test] WARN: a live release was returned - is a contract deployed?")


if __name__ == "__main__":
    try:
        asyncio.run(run_flow_test())
        asyncio.run(run_offline_check())
    except OSError as e:
        print(f"[Test] FAIL: {e} (is another gateway instance running on port 5683?)")
        sys.exit(1)
    print("\n=== ALL TESTS DONE ===")
