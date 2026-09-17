"""Simulated on-chain ledger for the Delta-OTA demonstration.

Stands in for the production `blockchain_poller.BlockchainPoller` so the
gateway can be exercised without a Hardhat node. `run_simulation.py` toggles
the module-level `LEDGER_*` knobs between phases to drive each scenario.
"""
import hashlib
from pathlib import Path

# artifacts/ lives three levels up from this file:
#   simulation/ -> gateway_runtime/ -> secureota/ -> gateway/
ARTIFACT_DIR = Path(__file__).resolve().parents[3] / "artifacts"
DUMMY_PATCH = ARTIFACT_DIR / "dummy_patch.bin"


def _default_golden_hash() -> str:
    """The success path must match this, so derive it from the real dummy
    patch on disk instead of hard-coding a possibly-stale hash."""
    try:
        return hashlib.sha256(DUMMY_PATCH.read_bytes()).hexdigest()
    except OSError:
        return "0" * 64


# ── Demo knobs: simulated on-chain state (toggle between phases) ─────────────
LEDGER_IS_LIVE = True
LEDGER_IS_REVOKED = False
LEDGER_GOLDEN_HASH = _default_golden_hash()


class DemoBlockchainPoller:
    """Drop-in stand-in for the production BlockchainPoller.

    Returns the same release dict shape that main_gateway.py and
    security_engine.py expect, but sourced from the LEDGER_* knobs above.
    """

    async def fetch_firmware_release(self, version_tag: str):
        print(f"[Ledger Bypass] Simulating on-chain state for {version_tag} "
              f"(live={LEDGER_IS_LIVE}, revoked={LEDGER_IS_REVOKED})")
        return {
            "version": version_tag,
            "goldenHash": LEDGER_GOLDEN_HASH,
            "isLive": LEDGER_IS_LIVE,
            "isRevoked": LEDGER_IS_REVOKED,
            "ipfsUrl": "ipfs://demo/dummy_patch.bin",
            "approvalCount": 1,
        }
