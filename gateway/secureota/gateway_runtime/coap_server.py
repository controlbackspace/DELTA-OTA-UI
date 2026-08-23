import aiocoap.resource as resource
import aiocoap
from pathlib import Path

ENCRYPTED_PATCH = Path(__file__).resolve().parent.parent.parent / "artifacts" / "encrypted_patch.bin"

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

    # Bind explicitly to localhost to bypass the Windows error
    await aiocoap.Context.create_server_context(root, bind=('127.0.0.1', 5683))
    print("[CoAP] Server active. Listening on 127.0.0.1:5683...")