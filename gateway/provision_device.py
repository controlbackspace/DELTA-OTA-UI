"""Production OTA key: generate it on the gateway, provision it into an ESP32.

    python provision_device.py --generate            # once per deployment
    python provision_device.py --port COM3           # once per device

The key (AES-CCM-128, 16 random bytes) lives only in the gateway config
(gateway_config.py, DELTA_OTA_KEY) and in each device's NVS. It is never
printed: both sides show a fingerprint (first 8 hex of SHA-256) instead, and
provisioning succeeds only when the device echoes the matching fingerprint.

Devices accept a key exactly once (write-once NVS). Rotating the key means
re-provisioning every device: erase flash (pio run -t erase), reflash, and
run --port again.
"""
import argparse
import hashlib
import secrets
import sys
import time
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / "secureota" / "gateway_runtime"
sys.path.insert(0, str(RUNTIME))

from gateway_config import load_config, save_config  # noqa: E402

KEY_BYTES = 16
READY_TIMEOUT_S = 30
REPLY_TIMEOUT_S = 10


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


def _read_line(ser, deadline: float) -> str | None:
    while time.time() < deadline:
        raw = ser.readline()
        if raw:
            return raw.decode(errors="replace").strip()
    return None


def provision(port: str, baud: int) -> int:
    key = configured_key()
    if key is None:
        print("No valid DELTA_OTA_KEY in the gateway config. Run --generate first.")
        return 1
    try:
        import serial  # pyserial
    except ImportError:
        print("pyserial missing: pip install -r requirements.txt")
        return 1

    expected = fingerprint(key)
    print(f"Provisioning {port} with key fp={expected}. Reset the board (EN) if "
          f"nothing appears within {READY_TIMEOUT_S}s.")
    with serial.Serial(port, baud, timeout=0.5) as ser:
        deadline = time.time() + READY_TIMEOUT_S
        while True:
            line = _read_line(ser, deadline)
            if line is None:
                print("No '[Provision] READY' from the device. Either it already "
                      "holds a key (boot log shows 'Key loaded fp=...'), or it is "
                      "not running the provisioning firmware.")
                return 1
            if "Key loaded fp=" in line:
                fp = line.split("fp=", 1)[1][:8]
                verdict = "MATCHES" if fp == expected else "DOES NOT MATCH"
                print(f"Device already provisioned (fp={fp}) - {verdict} the gateway key.")
                return 0 if fp == expected else 1
            if "[Provision] READY" in line:
                break

        ser.write(f"KEY {key.hex()}\n".encode())
        ser.flush()
        deadline = time.time() + REPLY_TIMEOUT_S
        while True:
            line = _read_line(ser, deadline)
            if line is None:
                print("Device did not confirm provisioning.")
                return 1
            if "[Provision] OK fp=" in line:
                fp = line.split("fp=", 1)[1][:8]
                if fp == expected:
                    print(f"Provisioned. Device fp={fp} matches the gateway key.")
                    return 0
                print(f"MISMATCH: device fp={fp}, gateway fp={expected}.")
                return 1
            if "[Provision] ERR" in line:
                print(f"Device rejected the key: {line}")
                return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="create the production key")
    group.add_argument("--port", help="serial port of the ESP32, e.g. COM3")
    parser.add_argument("--force", action="store_true", help="replace an existing key")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()
    if args.generate:
        return generate(args.force)
    return provision(args.port, args.baud)


if __name__ == "__main__":
    sys.exit(main())
