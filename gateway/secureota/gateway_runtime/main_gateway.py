import asyncio
import json
from pathlib import Path
from coap_server import start_coap_server
from blockchain_poller import mock_fetch_smart_contract_state
from security_engine import fetch_and_verify_payload, encrypt_for_device, PRE_SHARED_KEY

ARTIFACT_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"
DUMMY_PATCH = ARTIFACT_DIR / "dummy_patch.bin"
ENCRYPTED_PATCH = ARTIFACT_DIR / "encrypted_patch.bin"
STATE_FILE = ARTIFACT_DIR / "gateway_state.json"

## Main Loop

async def main_loop():

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
        release_data = await mock_fetch_smart_contract_state()

        if release_data["isLive"] == True and release_data["version"] != installed_version:
            print(f"Success! New Update ({release_data['version']}) is Live.")
            
            isValid = await fetch_and_verify_payload(release_data["goldenHash"])

            if isValid == True:
                print("Verified! Moving to encryption!")

                await encrypt_for_device(
                    DUMMY_PATCH, 
                    ENCRYPTED_PATCH, 
                    PRE_SHARED_KEY
                )
                
                installed_version = release_data["version"]
                
                with open(state_file, "w") as file:
                    json.dump({"installed_version": installed_version}, file)
                
                print(f"[System] Gateway state updated to {installed_version}")
            else:
                print("Hash Mismatch!")
                continue
        else:
            
            print("[Gateway] No new updates found. Sleeping...")
            await asyncio.sleep(5)

asyncio.run(main_loop())