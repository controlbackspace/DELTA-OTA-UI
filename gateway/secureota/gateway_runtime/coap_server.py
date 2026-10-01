import aiocoap.resource as resource
import aiocoap
import os
import re
import socket
import time
from pathlib import Path

import gateway_status

# DELTA_ARTIFACT_DIR (set by the packaged exe) overrides the default gateway/artifacts.
_ARTIFACTS = (Path(os.environ["DELTA_ARTIFACT_DIR"]) if os.environ.get("DELTA_ARTIFACT_DIR") else Path(__file__).resolve().parent.parent.parent / "artifacts")
ENCRYPTED_PATCH = _ARTIFACTS / "encrypted_patch.bin"
BLOCKS_DIR = _ARTIFACTS / "blocks"
BLOCK_SIZE = 1024  # must match SLIDING_WINDOW_SIZE in ESP32 main.cpp


def _block_files():
    """Ordered block_<N>.bin frames; ignores strays that are not numeric."""
    indexed = []
    if BLOCKS_DIR.is_dir():
        for path in BLOCKS_DIR.glob("block_*.bin"):
            try:
                indexed.append((int(path.stem.split("_", 1)[1]), path))
            except (ValueError, IndexError):
                continue
    return [path for _, path in sorted(indexed)]


def get_lan_ip() -> str:
    """Resolve the machine's active LAN IPv4 - the address ESP32 devices connect to.

    aiocoap refuses to bind to the 0.0.0.0 wildcard, so we determine the real
    address of the interface used for the default route (the Wi-Fi/LAN adapter).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _device_ip(request) -> str:
    """Requesting device's IP (aiocoap hostinfo is "ip:port" for IPv4)."""
    host = str(getattr(getattr(request, "remote", None), "hostinfo", "") or "?")
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def _requested_block(request) -> int:
    """Block index from the Uri-Query "b=<n>" (factory updater), falling back
    to the message ID (older firmware used MID = block number). The query
    form exists because CoAP servers replay cached replies for a repeated
    (endpoint, MID) for ~4 minutes: a device that reboots between releases
    would otherwise be handed the PREVIOUS release's block."""
    for q in getattr(request.opt, "uri_query", ()) or ():
        if q.startswith("b="):
            try:
                return int(q[2:])
            except ValueError:
                return -1
    mid = getattr(request, "mid", 0)
    return 0 if mid is None else mid


class FirmwareResource(resource.Resource):
    async def render_get(self, request):
        print("[CoAP] Firmware requested by device.")
        
        try:
            with open(ENCRYPTED_PATCH, "rb") as file:
                secure_bytes = file.read()
            
            return aiocoap.Message(payload=secure_bytes, code=aiocoap.CONTENT)
            
        except FileNotFoundError:
            print("[CoAP] Blocked: no verified firmware on disk. Device is not authorized (4.01).")
            gateway_status.event(f"Device {_device_ip(request)} requested /firmware - refused (4.01, nothing verified)")
            return aiocoap.Message(code=aiocoap.UNAUTHORIZED)


class PatchBlockResource(resource.Resource):
    """Block-wise /patch endpoint for the ESP32 chunk protocol.

    The firmware sends CON GET /patch?b=<n> (block number in the query; older
    firmware used the message ID - see _requested_block). Each block is an
    independent nonce||cipher||tag frame: data blocks answer 2.05, the final
    block answers 2.04 CHANGED (commit + reboot). No verified payload on disk
    answers 4.01 (kill-switch parity with /firmware); an unknown index
    answers 4.04.
    """
    async def render_get(self, request):
        blocks = _block_files()
        if not blocks:
            print("[CoAP] Block requested but no verified payload on disk (4.01).")
            gateway_status.event(f"Device {_device_ip(request)} requested a block - refused (4.01, nothing staged)")
            return aiocoap.Message(code=aiocoap.UNAUTHORIZED)

        block = _requested_block(request)
        print(f"[CoAP] Block {block} requested by device.")
        if block < 0 or block >= len(blocks):
            gateway_status.event(f"Device {_device_ip(request)} requested block {block} - out of range (4.04)")
            return aiocoap.Message(code=aiocoap.NOT_FOUND)
        payload = blocks[block].read_bytes()
        final = block == len(blocks) - 1
        # Tracker: real progress as seen by the gateway (reporting only).
        # Every block is recorded: a transfer is seconds long, and sparse
        # writes (or one lost to a file lock) left the console blind to it.
        ip = _device_ip(request)
        note = f"Device {ip}: block {block + 1}/{len(blocks)} sent"
        gateway_status.event(note + (" (final - device commits and reboots)" if final else ""),
                             device_ip=ip,
                             device_last_block=block,
                             device_final_sent=final,
                             device_last_seen=time.time())
        if final:
            return aiocoap.Message(payload=payload, code=aiocoap.CHANGED)
        return aiocoap.Message(payload=payload, code=aiocoap.CONTENT)


class VersionResource(resource.Resource):
    """GET /version: the release whose block frames are being served, as
    plain text (2.05), or 4.01 when nothing is staged. The factory updater
    asks this on every boot to decide whether to update ota_0.

    Kill switch: when the release the gateway follows was revoked on-chain,
    answer 4.03 with the revoked version as the body. A device running that
    version rolls back to its ota_1 backup (a 4.01 alone would leave an
    already-installed bad release running forever)."""
    async def render_get(self, request):
        staged = gateway_status._state.get("staged_version")
        if not staged or not _block_files():
            revoked = gateway_status._state.get("revoked_version")
            if revoked and gateway_status._state.get("gateway_state") == "revoked":
                ip = _device_ip(request)
                gateway_status.event(f"Device {ip} told {revoked} is REVOKED (4.03) - it rolls back at boot")
                return aiocoap.Message(code=aiocoap.FORBIDDEN, payload=str(revoked).encode("ascii"))
            gateway_status.event(f"Device {_device_ip(request)} asked /version - nothing staged (4.01)")
            return aiocoap.Message(code=aiocoap.UNAUTHORIZED)
        gateway_status.event(f"Device {_device_ip(request)} asked /version - staged {staged}")
        return aiocoap.Message(code=aiocoap.CONTENT, payload=str(staged).encode("ascii"))


class HelloResource(resource.Resource):
    """POST /hello <FIRMWARE_VERSION>: a device announces the version it is
    running, once per boot. After an OTA reboot this is the NEW image
    speaking - the console's proof that the update actually took effect.
    Reporting only: the gateway never trusts or acts on this value."""
    async def render_post(self, request):
        raw = request.payload[:32].decode("ascii", errors="replace").strip()
        version = re.sub(r"[^A-Za-z0-9._-]", "", raw)
        if not version:
            return aiocoap.Message(code=aiocoap.BAD_REQUEST)
        ip = _device_ip(request)
        print(f"[CoAP] Device {ip} reports firmware {version}.")
        gateway_status.event(f"Device {ip} reports firmware {version}",
                             device_reported_version=version,
                             device_reported_ip=ip,
                             device_reported_at=time.time())
        # MUST stay payload-free: the firmware drops empty-body replies before
        # code handling; a 2.04 WITH a body would read as a final OTA block.
        return aiocoap.Message(code=aiocoap.CHANGED)


async def start_coap_server():
    root = resource.Site()
    root.add_resource(['firmware'], FirmwareResource())
    root.add_resource(['patch'], PatchBlockResource())
    root.add_resource(['hello'], HelloResource())
    root.add_resource(['version'], VersionResource())

    # Bind to the LAN interface so ESP32 devices can reach the gateway.
    # Override the detected address with DELTA_BIND_ADDR if needed.
    bind_addr = os.getenv("DELTA_BIND_ADDR", get_lan_ip())
    await aiocoap.Context.create_server_context(root, bind=(bind_addr, 5683))
    print(f"[CoAP] Server active. Listening on {bind_addr}:5683...")