import hashlib
import os
from pathlib import Path
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

    def encrypt_blocks(self, input_path, output_dir, key, chunk_size: int = 1024) -> int:
        """Slice plaintext into chunk_size pieces; encrypt each as an
        independent nonce||cipher||tag frame: block_<N>.bin in output_dir.

        Serves the ESP32 chunk protocol (main.cpp requestChunk): every block
        independently auth-decodes on the device. Nonce = b"BLK" + 8-byte
        big-endian block index + 2 zero bytes (13 bytes, unique per block
        under one key). Returns the block count.
        """
        print("[Encryption] Slicing payload into block frames...")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for old in output_dir.glob("block_*.bin"):
            old.unlink()

        with open(input_path, "rb") as file:
            raw_bytes = file.read()

        cipher = AESCCM(key)
        count = 0
        for offset in range(0, len(raw_bytes), chunk_size):
            index = offset // chunk_size
            nonce = b"BLK" + index.to_bytes(8, "big") + b"\x00\x00"
            frame = nonce + cipher.encrypt(nonce, raw_bytes[offset:offset + chunk_size], None)
            (output_dir / f"block_{index}.bin").write_bytes(frame)
            count += 1

        print(f"[Encryption] Wrote {count} block frame(s) to {output_dir}.")
        return count

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
