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

    @staticmethod
    def naked_mode() -> bool:
        """DELTA_NAKED=1: the experiment's naked-CoAP baseline (Chapter 3 Baseline B). Block frames carry the plaintext
        block alone: no nonce, no AES-CCM, no tag. Never set in the product; the device must be the naked build too."""
        if os.environ.get("DELTA_NAKED", "") == "1":
            return True
        flag = os.environ.get("DELTA_NAKED_FILE", "")          # lets the experiment switch modes without restarting the gateway
        try:
            return bool(flag) and Path(flag).read_text(encoding="utf-8").strip() == "1"
        except OSError:
            return False

    def encrypt_blocks(self, input_path, output_dir, key, chunk_size: int = 1024) -> int:
        """Slice plaintext into chunk_size pieces; encrypt each as an
        independent nonce||cipher||tag frame: block_<N>.bin in output_dir.

        Serves the ESP32 chunk protocol (main.cpp requestChunk): every block
        independently auth-decodes on the device. Nonce = 8 random bytes
        drawn once per call (per release) + 5-byte big-endian block index
        (13 bytes). The random prefix keeps nonces unique ACROSS releases
        under the one long-lived key - a counter-only nonce would repeat
        block N's nonce in every release, and CCM nonce reuse leaks the XOR
        of the plaintexts. Returns the block count.
        """
        naked = self.naked_mode()
        print("[Encryption] Slicing payload into block frames..." + (" (NAKED: plaintext frames, no AES-CCM)" if naked else ""))
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for old in output_dir.glob("block_*.bin"):
            old.unlink()

        with open(input_path, "rb") as file:
            raw_bytes = file.read()

        cipher = None if naked else AESCCM(key)
        release_prefix = os.urandom(8)
        count = 0
        for offset in range(0, len(raw_bytes), chunk_size):
            index = offset // chunk_size
            if naked:
                frame = raw_bytes[offset:offset + chunk_size]
            else:
                nonce = release_prefix + index.to_bytes(5, "big")
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
