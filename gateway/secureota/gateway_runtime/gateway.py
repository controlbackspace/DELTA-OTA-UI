from web3 import Web3
import asyncio
import hashlib
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESCCM


ARTIFACT_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"
DUMMY_PATCH = ARTIFACT_DIR / "dummy_patch.bin"
ENCRYPTED_PATCH = ARTIFACT_DIR / "encrypted_patch.bin"
STATE_FILE = ARTIFACT_DIR / "gateway_state.json"

PRE_SHARED_KEY = b"TEST_KEY_1234567"

## AESCCM Encryption using OSCORE

async def encrypt_for_device(input_filename, output_filename, key):
    print("[Encryption] Wrapping payload in OSCORE AES-CCM layer...")
    
    nonce = os.urandom(13)
    
    with open(input_filename, "rb") as file:
        raw_bytes = file.read()
    
    cipher = AESCCM(key)
    ciphertext = cipher.encrypt(nonce, raw_bytes, None)
    
    with open(output_filename, "wb") as file:
        file.write(nonce)
        file.write(ciphertext)
    
    print(f"[Encryption] Payload secured and saved to {output_filename}.")
    return True

## GoldenHash Computation and Verification

async def fetch_and_verify_payload(goldenHash):
    print("[Gateway] Downloading payload from URL...")

    await asyncio.sleep(2)

    with open(DUMMY_PATCH, "rb") as file:
        digest = hashlib.file_digest(file, "sha256")    
        computed_hash = digest.hexdigest()

    print(f"[Gateway] Expected Hash: {goldenHash}")
    print(f"[Gateway] Computed Hash: {computed_hash}")

    if computed_hash == goldenHash:
        print("[Security] Verification Passed. Payload is authentic.")
        return True
    else:
        print("[Security] FATAL: Hash mismatch. Payload destroyed.")
        return False

## Simulated network call/polling to the Ethereum Blockchain

# This function fakes a network call to the Ethereum blockchain
async def mock_fetch_smart_contract_state():
    print("\n[Network] Polling blockchain for updates...")
    
    # Simulate a 2 second network delay
    await asyncio.sleep(2) 
    
    # This matches the exact Solidity struct we agreed upon
    dummy_firmware_release = {
        "version": "v1.1",
        "goldenHash": '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
        "ipfsUrl": "http://local-test-server/patch_v1.1.bin",
        "approvalCount": 3,
        "isLive": True,
        "isRevoked": False
    }
    
    return dummy_firmware_release


## Main Loop

async def main_loop():
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
                break
            else:
                print("Hash Mismatch!")
                continue
        else:
            
            print("[Gateway] No new updates found. Sleeping...")
            await asyncio.sleep(5)

asyncio.run(main_loop())