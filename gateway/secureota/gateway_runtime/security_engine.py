import hashlib
import os
import asyncio
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

ARTIFACT_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"
DUMMY_PATCH = ARTIFACT_DIR / "dummy_patch.bin"

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