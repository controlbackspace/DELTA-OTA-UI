import aiocoap.resource as resource
import aiocoap
import os
import socket
from pathlib import Path

ENCRYPTED_PATCH = Path(__file__).resolve().parent.parent.parent / "artifacts" / "encrypted_patch.bin"
BLOCKS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "blocks"
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

class FirmwareResource(resource.Resource):
    async def render_get(self, request):
        print("[CoAP] Firmware requested by device.")
        
        try:
            with open(ENCRYPTED_PATCH, "rb") as file:
                secure_bytes = file.read()
            
            return aiocoap.Message(payload=secure_bytes, code=aiocoap.CONTENT)
            
        except FileNotFoundError:
            print("[CoAP] Blocked: no verified firmware on disk. Device is not authorized (4.01).")
            return aiocoap.Message(code=aiocoap.UNAUTHORIZED)


class PatchBlockResource(resource.Resource):
    """Block-wise /patch endpoint for the ESP32 chunk protocol.

    The firmware sends CON GET with Uri-Path "patch" and the block number in
    the CoAP message ID (see requestChunk in ESP32 main.cpp). Each block is an
    independent nonce||cipher||tag frame: data blocks answer 2.05, the final
    block answers 2.04 CHANGED (commit + reboot). No verified payload on disk
    answers 4.01 (kill-switch parity with /firmware); an unknown index
    answers 4.04.
    """
    async def render_get(self, request):
        blocks = _block_files()
        if not blocks:
            print("[CoAP] Block requested but no verified payload on disk (4.01).")
            return aiocoap.Message(code=aiocoap.UNAUTHORIZED)

        block = getattr(request, "mid", 0)
        if block is None:
            block = 0
        print(f"[CoAP] Block {block} requested by device.")
        if block < 0 or block >= len(blocks):
            return aiocoap.Message(code=aiocoap.NOT_FOUND)
        payload = blocks[block].read_bytes()
        if block == len(blocks) - 1:
            return aiocoap.Message(payload=payload, code=aiocoap.CHANGED)
        return aiocoap.Message(payload=payload, code=aiocoap.CONTENT)
        
async def start_coap_server():
    root = resource.Site()
    root.add_resource(['firmware'], FirmwareResource())
    root.add_resource(['patch'], PatchBlockResource())

    # Bind to the LAN interface so ESP32 devices can reach the gateway.
    # Override the detected address with DELTA_BIND_ADDR if needed.
    bind_addr = os.getenv("DELTA_BIND_ADDR", get_lan_ip())
    await aiocoap.Context.create_server_context(root, bind=(bind_addr, 5683))
    print(f"[CoAP] Server active. Listening on {bind_addr}:5683...")