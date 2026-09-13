import asyncio
from aiocoap import Context, Message, GET
from coap_server import get_lan_ip

async def main():
    print("[Client] Booting mock ESP32...")
    
    protocol = await Context.create_client_context()

    server_ip = get_lan_ip()
    request = Message(code=GET, uri=f"coap://{server_ip}/firmware")

    try:
        print(f"[Client] Sending GET request to {request.get_request_uri()}...")
        
        response = await protocol.request(request).response
        
        print(f"[Client] Success! Response Code: {response.code}")
        print(f"[Client] Encrypted Payload received: {len(response.payload)} bytes")
        
    except Exception as e:
        print(f"[Client] Failed to fetch resource: {e}")

if __name__ == "__main__":
    asyncio.run(main())