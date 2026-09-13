import aiocoap.resource as resource
import aiocoap
import os
import socket
from pathlib import Path

ENCRYPTED_PATCH = Path(__file__).resolve().parent.parent.parent / "artifacts" / "encrypted_patch.bin"


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
        
async def start_coap_server():
    root = resource.Site()
    root.add_resource(['firmware'], FirmwareResource())

    # Bind to the LAN interface so ESP32 devices can reach the gateway.
    # Override the detected address with DELTA_BIND_ADDR if needed.
    bind_addr = os.getenv("DELTA_BIND_ADDR", get_lan_ip())
    await aiocoap.Context.create_server_context(root, bind=(bind_addr, 5683))
    print(f"[CoAP] Server active. Listening on {bind_addr}:5683...")