"""OTA key tooling: generate the production key on the gateway.

    python provision_device.py --generate            # once per deployment

The key (AES-CCM-128, 16 random bytes) lives in the gateway config
(gateway_config.py, DELTA_OTA_KEY). It is never printed: a fingerprint (first
8 hex of SHA-256) is shown instead. Devices no longer take the key over USB:
the ESP32 reset tool (DeltaOTA-ESP32-Reset.exe / tools/reset_device.py) asks for
the key and compiles it into the factory image, which stores it in NVS on first
boot. Use the gateway console (menu 9) to import or reveal the key when moving
the gateway to another machine such as the Raspberry Pi.
"""
import argparse
import hashlib
import secrets
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / "secureota" / "gateway_runtime"
sys.path.insert(0, str(RUNTIME))

from gateway_config import load_config, save_config  # noqa: E402

KEY_BYTES = 16


def fingerprint(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:8]


def configured_key() -> bytes | None:
    raw = load_config().get("DELTA_OTA_KEY", "").strip()
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        return None
    return key if len(key) == KEY_BYTES else None


def generate(force: bool) -> int:
    existing = configured_key()
    if existing and not force:
        print(f"A key already exists (fp={fingerprint(existing)}). Not replacing it.")
        print("Rotating breaks every provisioned device; pass --force only if you "
              "will re-provision all of them.")
        return 1
    key = secrets.token_bytes(KEY_BYTES)
    path = save_config({"DELTA_OTA_KEY": key.hex()})
    print(f"Generated production OTA key fp={fingerprint(key)}")
    print(f"Stored in {path} (keep this file private; it is the only copy).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--generate", action="store_true", required=True,
                        help="create the production key")
    parser.add_argument("--force", action="store_true", help="replace an existing key")
    args = parser.parse_args()
    return generate(args.force)


if __name__ == "__main__":
    sys.exit(main())
