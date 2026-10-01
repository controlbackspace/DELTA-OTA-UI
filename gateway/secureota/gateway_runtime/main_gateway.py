import asyncio
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from coap_server import get_lan_ip, start_coap_server
from blockchain_poller import BlockchainPoller
from security_engine import SecurityEngine
from delta_stream import to_dota
from simulation.simulated_ledger import DemoBlockchainPoller
from gateway_config import apply_config
import gateway_status

# Shared config file seeds unset env vars (console/.bat/service/exe all write
# the same file). No behavior change when no file exists: every os.getenv
# below keeps its built-in default. Core logic untouched.
apply_config()

# DELTA_ARTIFACT_DIR (set by the packaged exe) overrides the default gateway/artifacts.
ARTIFACT_DIR = (Path(os.environ["DELTA_ARTIFACT_DIR"]) if os.environ.get("DELTA_ARTIFACT_DIR") else Path(__file__).resolve().parent.parent.parent / "artifacts")
DUMMY_PATCH = ARTIFACT_DIR / "dummy_patch.bin"
ENCRYPTED_PATCH = ARTIFACT_DIR / "encrypted_patch.bin"
STATE_FILE = ARTIFACT_DIR / "gateway_state.json"

# The live loop follows the chain (newest ReleasePromotedToLive event), so no
# version is hardcoded there. This default is only used by pollers without
# event support (test doubles) and by the simulation harnesses that import it.
TARGET_VERSION = "v1.1"
POLL_INTERVAL = 5

# OTA key (AES-CCM-128). Production key: DELTA_OTA_KEY (32 hex chars, from
# the gateway config written by provision_device.py --generate). TEST_KEY is
# the published bench key: harnesses opt in with DELTA_USE_TEST_KEY=1, and the
# live gateway refuses to run on it (see the guard at the top of main_loop).
TEST_KEY = b"TEST_KEY_1234567"


def _load_key() -> tuple[bytes, str]:
    """(key, source) where source is test-forced | configured | missing | malformed.
    Missing/malformed fall back to TEST_KEY so harness imports keep working."""
    if os.environ.get("DELTA_USE_TEST_KEY") == "1":
        return TEST_KEY, "test-forced"
    raw = os.environ.get("DELTA_OTA_KEY", "").strip()
    if not raw:
        return TEST_KEY, "missing"
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        return TEST_KEY, "malformed"
    return (key, "configured") if len(key) == 16 else (TEST_KEY, "malformed")


def key_fingerprint(key: bytes) -> str:
    """First 8 hex of SHA-256(key): safe to print, matches the device's fp=."""
    return hashlib.sha256(key).hexdigest()[:8]


PRE_SHARED_KEY, KEY_SOURCE = _load_key()
BLOCKS_DIR = ARTIFACT_DIR / "blocks"  # per-chunk frames for the ESP32 /patch protocol

# Cap on downloaded patch bytes (DoS hygiene: never buffer unbounded remote
# bytes into memory, no matter what URL a release names).
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 30

# Simulated-ledger mode: SIM_LEDGER=1 polls DemoBlockchainPoller instead of
# web3 (bench/rehearsal seam — full OTA loop with zero blockchain processes).
# Payload bytes resolve to SIM_PAYLOAD_URL so the REAL download→hash→stage
# path still executes end to end; only the release dict is simulated.
# LEDGER_IS_LIVE / LEDGER_IS_REVOKED / LEDGER_GOLDEN_HASH knobs from the
# simulation package drive scenarios without any chain.
SIM_LEDGER = os.environ.get("SIM_LEDGER", "") == "1"
SIM_PAYLOAD_URL = DUMMY_PATCH.as_uri()


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
    for pattern in ("dl_*.bin", "dota_*.bin"):
        for stale in ARTIFACT_DIR.glob(pattern):
            stale.unlink(missing_ok=True)

def _start_artifact_server():
    """Serve patches + the live status feed on :8000 from inside the gateway,
    so the console's tracker works without a second process. The packaged exe
    starts its own (see gateway_console.py); a standalone serve_artifacts.py
    that already owns the port is left alone."""
    if getattr(sys, "frozen", False) or os.environ.get("DELTA_NO_ARTIFACT_SERVER") == "1":
        return
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        import serve_artifacts
        threading.Thread(target=serve_artifacts.make_server().serve_forever,
                         daemon=True).start()
    except OSError as exc:
        print(f"[Artifacts] not started ({exc}) - assuming another server owns the port")
    except ImportError as exc:
        print(f"[Artifacts] not started ({exc})")

## Main Loop

async def main_loop():

    # Key guard: a live gateway never serves updates under the published test
    # key. SIM_LEDGER rehearsals and explicit DELTA_USE_TEST_KEY=1 test runs
    # may; everything else needs the provisioned production key.
    if KEY_SOURCE in ("missing", "malformed") and not SIM_LEDGER:
        print(f"[Crypto] FATAL: production OTA key {KEY_SOURCE} (DELTA_OTA_KEY). "
              f"Run: python provision_device.py --generate  (in gateway/) or console menu 9. "
              f"Refusing to serve updates under the test key.")
        return
    if KEY_SOURCE == "configured":
        print(f"[Crypto] Production OTA key loaded fp={key_fingerprint(PRE_SHARED_KEY)}")
    else:
        print(f"[Crypto] WARNING: TEST key in use ({KEY_SOURCE}) - bench/simulation only.")

    # Ledger source: real web3 poller, or the simulated ledger when
    # SIM_LEDGER=1 (bench/rehearsal — no node required).
    if SIM_LEDGER:
        print("[Ledger] SIM_LEDGER=1: polling simulated ledger (no blockchain).")
        poller = DemoBlockchainPoller()
    else:
        # The Web3 HTTP connection is established exactly once at boot
        poller = BlockchainPoller()

    # The security engine handles payload verification and encryption
    engine = SecurityEngine()

    await start_coap_server()
    _start_artifact_server()

    # Bind self-check: a loopback bind means no default route, and the CoAP
    # server would be reachable from nothing (not even the ESP32). Say so
    # loudly instead of serving into the void; otherwise print usable URLs.
    bind_addr = os.getenv("DELTA_BIND_ADDR", get_lan_ip())
    if bind_addr.startswith("127."):
        print(f"[CoAP] WARNING: bound to loopback {bind_addr} - no default route. "
              f"ESP32 devices cannot reach this gateway; fix networking or set "
              f"DELTA_BIND_ADDR.")
    else:
        print(f"[CoAP] Reachable at coap://{bind_addr}:5683/firmware and "
              f"coap://{bind_addr}:5683/patch")

    # 1. State Initialization (The Gateway Boot Sequence)
    state_file = STATE_FILE
    # Installed version is only meaningful for the contract it came from: a
    # fresh chain (new address) starts over at v1.0, otherwise a release that
    # went live on the OLD chain would read as "already installed" forever.
    contract_id = "sim" if SIM_LEDGER else getattr(poller, "contract_address", "unknown")

    installed_version = "v1.0"
    try:
        with open(state_file, "r") as file:
            state_data = json.load(file)
        saved_contract = state_data.get("contract")
        saved_version = state_data["installed_version"]
        if saved_contract is not None and str(saved_contract).lower() == str(contract_id).lower():
            installed_version = saved_version
        elif saved_version != "v1.0":
            # Unbound (pre-binding file) or another contract's state: the
            # version cannot be trusted on this chain.
            print(f"[Boot] Saved {saved_version} belongs to contract "
                  f"{saved_contract or '(unrecorded)'}, now on {contract_id} - "
                  f"resetting installed version to v1.0.")
    except FileNotFoundError:
        pass  # first boot: v1.0
    except (json.JSONDecodeError, KeyError):
        print("[Boot] Unreadable gateway state file - assuming v1.0.")

    print(f"[Boot] Gateway loaded. Current version: {installed_version}")

    # Blocks on disk only count if they carry the device's DOTA stream for the
    # installed version (frames staged by an older gateway hold the raw patch,
    # which the factory updater cannot decode). Otherwise clear them and
    # re-stage from the chain.
    existing_blocks = len(list(BLOCKS_DIR.glob("block_*.bin")))
    if existing_blocks and not (ARTIFACT_DIR / f"dota_{_safe_tag(installed_version)}.bin").exists():
        print(f"[Boot] Block frames on disk are not a DOTA stream for {installed_version} - "
              f"clearing and re-staging from the chain.")
        ENCRYPTED_PATCH.unlink(missing_ok=True)
        _clear_block_frames()
        existing_blocks = 0
        installed_version = "v1.0"

    # Live status for the console tracker. Blocks already on disk from an
    # earlier run of this same contract are still being served.
    gateway_status.update(
        gateway_state="starting",
        contract=contract_id,
        key_fp=key_fingerprint(PRE_SHARED_KEY),
        staged_version=installed_version if existing_blocks and installed_version != "v1.0" else None,
        blocks_total=existing_blocks or None,
    )

    # Pollers without event support (test doubles) keep the fixed default.
    fetch_latest = getattr(poller, "fetch_latest_live_version", None)
    revoked_handled: set[str] = set()   # versions whose kill switch already ran
    revoked_announced: set[str] = set()  # versions already reported to the console

    while True:
        if fetch_latest is None:
            target = TARGET_VERSION
        else:
            target = await fetch_latest()
            if target is None:
                print("[Gateway] Ledger unreachable (node offline?). Waiting - "
                      "will retry next poll.")
                gateway_status.event_once("state", "Ledger unreachable (node offline?) - waiting",
                                          gateway_state="unreachable")
                await asyncio.sleep(POLL_INTERVAL)
                continue
            if target == "":
                print(f"[Gateway] No live release on contract {contract_id} yet. "
                      f"Waiting...")
                gateway_status.event_once("state", f"No live release on contract {contract_id} yet - waiting",
                                          gateway_state="waiting", target_version=None)
                await asyncio.sleep(POLL_INTERVAL)
                continue

        gateway_status.event_once("target", f"Following {target} (newest live release on the chain)",
                                  target_version=target)
        release_data = await poller.fetch_firmware_release(target)

        # Ledger unreachable (node offline, RPC error): this is WAITING, not
        # failure. Warn, sleep, and keep polling indefinitely - the gateway
        # must outlive transient outages with or without a process supervisor.
        # (Revocation below is the only terminal halt: a ledger verdict, not
        # an absence.)
        if release_data is None:
            print("[Gateway] Ledger unreachable (node offline?). Waiting - "
                  "will retry next poll.")
            gateway_status.event_once("state", "Ledger unreachable (node offline?) - waiting",
                                      gateway_state="unreachable")
            await asyncio.sleep(POLL_INTERVAL)
            continue

        # Zero Trust: never apply or serve a release that was revoked on-chain.
        # Kill switch destroys the artifacts once, then the gateway keeps
        # polling and serves nothing (devices get 4.01) until a NEWER release
        # goes live - a revoke is followed by a fix, not by a manual restart.
        if release_data["isRevoked"] is True:
            if target not in revoked_handled:
                ENCRYPTED_PATCH.unlink(missing_ok=True)
                _clear_block_frames()
                _clear_staged()
                revoked_handled.add(target)
                print(f"[Gateway] KILL SWITCH: Release {target} has been revoked on-chain. "
                      f"Artifacts destroyed; serving nothing until a newer release goes live.")
            else:
                print(f"[Gateway] Latest release {target} is revoked - waiting for a "
                      f"newer live release.")
            gateway_status.update(gateway_state="revoked", staged_version=None,
                                  blocks_total=None, revoked_version=target)
            if target not in revoked_announced:
                revoked_announced.add(target)
                gateway_status.event(f"KILL SWITCH: {target} revoked on-chain - artifacts destroyed, devices refused (4.01)")
            await asyncio.sleep(POLL_INTERVAL)
            continue

        if release_data["isLive"] is True and release_data["version"] != installed_version:
            print(f"Success! New Update ({release_data['version']}) is Live.")
            gateway_status.event(f"{release_data['version']} is live on-chain - downloading and verifying")

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
                # Download source: the on-chain URL in production; the local
                # fixture URI in SIM_LEDGER mode (the sim ledger's canned URL
                # is not fetchable by design, so resolve it here and keep the
                # download path below executing for real).
                source_url = SIM_PAYLOAD_URL if SIM_LEDGER else release_data.get("ipfsUrl", "")
                if SIM_LEDGER:
                    print(f"[Network] SIM_LEDGER payload resolves to {source_url}.")
                payload_bytes = await asyncio.to_thread(_download_patch, source_url)
                if payload_bytes is None:
                    gateway_status.event(f"Download of {release_data['version']} failed - will retry",
                                         gateway_state="download-failed")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                # Hash the DOWNLOADED bytes against the golden hash before
                # anything touches disk: transport-substituted bytes fail here,
                # never written, never served.
                if hashlib.sha256(payload_bytes).hexdigest() != release_data["goldenHash"]:
                    print("[Security] FATAL: Downloaded bytes do not match golden hash. "
                          "Payload destroyed (never written).")
                    gateway_status.event(f"{release_data['version']}: downloaded bytes do not match the on-chain golden hash - refused",
                                         gateway_state="hash-mismatch")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                staged = ARTIFACT_DIR / f"dl_{_safe_tag(release_data['version'])}.bin"
                staged.write_bytes(payload_bytes)
                payload_path = staged

            isValid = engine.verify_firmware_integrity(release_data, str(payload_path))

            if isValid is True:
                print("Verified! Moving to encryption!")
                gateway_status.event(f"{release_data['version']}: golden hash verified - encrypting")

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

                # Device format: re-pack the VERIFIED payload as a DOTA stream
                # (bsdiff semantics, deflate instead of bzip2 - the ESP32
                # rebuilds the new app from its ota_1 backup + this stream).
                # A full image (DELTA_PAYLOAD bench path) becomes one copy record.
                try:
                    dota_bytes = to_dota(Path(payload_path).read_bytes())
                except (ValueError, OSError) as e:
                    print(f"[Delta] FATAL: payload is not a usable patch/image ({e}). Not served.")
                    ENCRYPTED_PATCH.unlink(missing_ok=True)
                    _clear_block_frames()
                    _clear_staged()
                    gateway_status.event(f"{release_data['version']}: payload is not a usable patch/image - not served",
                                         gateway_state="invalid-payload",
                                          staged_version=None, blocks_total=None)
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                dota_path = ARTIFACT_DIR / f"dota_{_safe_tag(release_data['version'])}.bin"
                dota_path.write_bytes(dota_bytes)
                print(f"[Delta] Device stream: {Path(payload_path).stat().st_size} B payload -> "
                      f"{len(dota_bytes)} B DOTA.")
                gateway_status.event(f"Device stream built: {len(dota_bytes)} B DOTA")

                block_count = engine.encrypt_blocks(dota_path, BLOCKS_DIR, PRE_SHARED_KEY)

                installed_version = release_data["version"]

                with open(state_file, "w") as file:
                    json.dump({"installed_version": installed_version,
                               "contract": contract_id}, file)

                print(f"[System] Gateway state updated to {installed_version}")
                gateway_status.reset_device_progress()
                gateway_status.event(f"Staged {installed_version}: verified, encrypted, {block_count} blocks ready",
                                      gateway_state="staged",
                                      revoked_version=None,
                                      staged_version=installed_version,
                                      blocks_total=block_count,
                                      staged_at=time.time())
            else:
                print("Hash Mismatch!")
                ENCRYPTED_PATCH.unlink(missing_ok=True)
                _clear_block_frames()
                _clear_staged()
                gateway_status.event(f"{release_data['version']}: integrity check failed - artifacts destroyed",
                                     gateway_state="hash-mismatch",
                                     staged_version=None, blocks_total=None)
                await asyncio.sleep(POLL_INTERVAL)
        else:

            if installed_version != "v1.0":
                print(f"[Gateway] {installed_version} staged "
                      f"({gateway_status._state.get('blocks_total') or '?'} blocks) - "
                      f"waiting for devices. Next chain check in {POLL_INTERVAL}s.")
            else:
                print("[Gateway] No new updates found. Sleeping...")
            # Heartbeat: keeps updated_at fresh so the console shows "online".
            gateway_status.update(
                gateway_state="staged" if installed_version != "v1.0" else "waiting")
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())
