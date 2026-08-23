import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

class SecurityEngine:
    def encrypt_payload(self, input_path, output_path, key) -> bool:
        print("[Encryption] Wrapping payload in OSCORE AES-CCM layer...")

        nonce = os.urandom(13)

        with open(input_path, "rb") as file:
            raw_bytes = file.read()

        cipher = AESCCM(key)
        ciphertext = cipher.encrypt(nonce, raw_bytes, None)

        with open(output_path, "wb") as file:
            file.write(nonce)
            file.write(ciphertext)

        print(f"[Encryption] Payload secured and saved to {output_path}.")
        return True

    def verify_firmware_integrity(self, ledger_data: dict, file_path: str) -> bool:
        # 1. State Check
        # Reject immediately if the release is unauthorized on-chain.
        if ledger_data["isLive"] == False or ledger_data["isRevoked"] == True:
            print("[Security] FATAL: Release rejected by ledger state check.")
            return False

        # 2. File Verification
        # Ensure the payload is actually on the drive before reading it.
        if not os.path.exists(file_path):
            print("[Security] FATAL: Payload file missing from disk.")
            return False

        # 3. Native Hashing
        computed_hash = ""
        with open(file_path, 'rb') as f:
            raw_bytes = f.read()
            computed_hash = hashlib.sha256(raw_bytes).hexdigest()

        # 4. Zero Trust Comparison
        print(f"[Security] Expected Hash: {ledger_data['goldenHash']}")
        print(f"[Security] Computed Hash: {computed_hash}")

        if computed_hash == ledger_data["goldenHash"]:
            print("[Security] Verification Passed. Payload is authentic.")
            return True
        else:
            print("[Security] FATAL: Hash mismatch. Payload destroyed.")
            return False
