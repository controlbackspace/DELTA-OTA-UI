import asyncio
import json
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
            print(f"[Gateway] FATAL: Release {TARGET_VERSION} has been revoked on-chain. Halting gateway.")
            return

        if release_data["isLive"] is True and release_data["version"] != installed_version:
            print(f"Success! New Update ({release_data['version']}) is Live.")
            
            isValid = engine.verify_firmware_integrity(release_data, str(DUMMY_PATCH))

            if isValid is True:
                print("Verified! Moving to encryption!")

                engine.encrypt_payload(
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
                ENCRYPTED_PATCH.unlink(missing_ok=True)
                await asyncio.sleep(POLL_INTERVAL)
        else:
            
            print("[Gateway] No new updates found. Sleeping...")
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())
