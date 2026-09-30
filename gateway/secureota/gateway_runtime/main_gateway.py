import asyncio
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from coap_server import start_coap_server
from blockchain_poller import BlockchainPoller
from security_engine import SecurityEngine

ARTIFACT_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"
DUMMY_PATCH = ARTIFACT_DIR / "dummy_patch.bin"
ENCRYPTED_PATCH = ARTIFACT_DIR / "encrypted_patch.bin"
STATE_FILE = ARTIFACT_DIR / "gateway_state.json"

TARGET_VERSION = "v1.1"
POLL_INTERVAL = 5
PRE_SHARED_KEY = b"TEST_KEY_1234567"
BLOCKS_DIR = ARTIFACT_DIR / "blocks"  # per-chunk frames for the ESP32 /patch protocol

# Cap on downloaded patch bytes (DoS hygiene: never buffer unbounded remote
# bytes into memory, no matter what URL a release names).
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 30


def _safe_tag(version_tag: str) -> str:
    """Filename-safe version tag (mirrors make_release.sanitize_version_tag;
    duplicated, not imported: gateway code must never import builder code)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", version_tag)


def _download_patch(url: str) -> bytes | None:
    """Fetch patch bytes from the on-chain release URL.

    http(s) + file (tests) only. Anything else — notably bare ipfs:// with
    no gateway in front — is refused with a clear log, never fetched.
    Returns None on any failure; the caller sleeps and re-polls.
    """
    scheme = urllib.parse.urlparse(url).scheme
    if scheme not in ("http", "https", "file"):
        print(f"[Network] Refusing unsupported URL scheme {scheme!r} in release "
              f"(need http(s); native ipfs:// requires a gateway in front).")
        return None
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_S) as resp:
            data = resp.read(MAX_DOWNLOAD_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[Network] Patch download failed ({e}); will retry next poll.")
        return None
    if len(data) > MAX_DOWNLOAD_BYTES:
        print(f"[Network] Patch exceeds {MAX_DOWNLOAD_BYTES} bytes; refusing.")
        return None
    print(f"[Network] Downloaded {len(data)} bytes from release URL.")
    return data


def _clear_block_frames():
    """Kill-switch parity: never serve stale chunks after revoke/mismatch."""
    for stale in BLOCKS_DIR.glob("block_*.bin"):
        stale.unlink(missing_ok=True)


def _clear_staged():
    """Remove downloaded staging files (revoke/mismatch hygiene)."""
    for stale in ARTIFACT_DIR.glob("dl_*.bin"):
        stale.unlink(missing_ok=True)

## Main Loop

async def main_loop():

    # The Web3 HTTP connection is established exactly once at boot
    poller = BlockchainPoller()

    # The security engine handles payload verification and encryption
    engine = SecurityEngine()

    await start_coap_server()

    # 1. State Initialization (The Gateway Boot Sequence)
    state_file = STATE_FILE
    
    try:
        with open(state_file, "r") as file:
            state_data = json.load(file)
            installed_version = state_data["installed_version"]
    except FileNotFoundError:
        # If the file doesn't exist yet, we default to v1.0
        installed_version = "v1.0"  
        
    print(f"[Boot] Gateway loaded. Current version: {installed_version}")

    while True:
        release_data = await poller.fetch_firmware_release(TARGET_VERSION)

        # Zero Trust: if the ledger poll failed (node offline, RPC error),
        # halt the gateway immediately instead of crashing.
        if release_data is None:
            print("[Gateway] FATAL: Ledger poll failed (Hardhat offline?). Halting gateway.")
            return

        # Zero Trust: never apply or serve a release that was revoked on-chain
        if release_data["isRevoked"] is True:
            ENCRYPTED_PATCH.unlink(missing_ok=True)
            _clear_block_frames()
            _clear_staged()
            print(f"[Gateway] FATAL: Release {TARGET_VERSION} has been revoked on-chain. Halting gateway.")
            return

        if release_data["isLive"] is True and release_data["version"] != installed_version:
            print(f"Success! New Update ({release_data['version']}) is Live.")

            # Payload source: an explicit DELTA_PAYLOAD file wins when set
            # (bench/test seam only). Otherwise the gateway DOWNLOADS the
            # release from its on-chain URL — the only production path. There
            # is no shared-disk fallback: console and gateway share nothing
            # but the network.
            payload_override = os.environ.get("DELTA_PAYLOAD")
            if payload_override:
                print(f"[Network] Using local payload override {payload_override} "
                      f"(bench/test only - production downloads the release URL).")
                payload_path = Path(payload_override)
            else:
                payload_bytes = await asyncio.to_thread(
                    _download_patch, release_data.get("ipfsUrl", ""))
                if payload_bytes is None:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                # Hash the DOWNLOADED bytes against the golden hash before
                # anything touches disk: transport-substituted bytes fail here,
                # never written, never served.
                if hashlib.sha256(payload_bytes).hexdigest() != release_data["goldenHash"]:
                    print("[Security] FATAL: Downloaded bytes do not match golden hash. "
                          "Payload destroyed (never written).")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                staged = ARTIFACT_DIR / f"dl_{_safe_tag(release_data['version'])}.bin"
                staged.write_bytes(payload_bytes)
                payload_path = staged

            isValid = engine.verify_firmware_integrity(release_data, str(payload_path))

            if isValid is True:
                print("Verified! Moving to encryption!")

                try:
                    engine.encrypt_payload(
                        payload_path,
                        ENCRYPTED_PATCH,
                        PRE_SHARED_KEY
                    )
                except ValueError as e:
                    # CCM with a 13-byte nonce caps a single frame at 64 KB
                    # (L=2 length field). Firmware-scale payloads skip the
                    # whole-frame artifact and serve block frames only - the
                    # production OTA path. Remove any stale frame so
                    # /firmware answers 4.01 instead of serving old bytes.
                    print(f"[Encryption] Whole-frame skipped ({e}); "
                          f"serving block frames only.")
                    ENCRYPTED_PATCH.unlink(missing_ok=True)

                engine.encrypt_blocks(payload_path, BLOCKS_DIR, PRE_SHARED_KEY)

                installed_version = release_data["version"]
                
                with open(state_file, "w") as file:
                    json.dump({"installed_version": installed_version}, file)
                
                print(f"[System] Gateway state updated to {installed_version}")
            else:
                print("Hash Mismatch!")
                ENCRYPTED_PATCH.unlink(missing_ok=True)
                _clear_block_frames()
                _clear_staged()
                await asyncio.sleep(POLL_INTERVAL)
        else:
            
            print("[Gateway] No new updates found. Sleeping...")
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())
