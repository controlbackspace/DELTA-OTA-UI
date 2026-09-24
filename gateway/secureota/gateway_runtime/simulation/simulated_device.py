"""Mock ESP32 device for the Delta-OTA demonstration.

CoAP GET /firmware -> code check -> frame slice -> AES-CCM auth-decrypt,
printing the same `[BLOCKED]` / `[FAIL]` / `[OK]` verdicts the ESP32 firmware
produces. Simulation/test tooling only.

Run standalone:  python simulation/simulated_device.py
"""
import sys
from pathlib import Path

# Make the production gateway_runtime modules importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
from aiocoap import CONTENT, Context, GET, Message, NOT_FOUND, UNAUTHORIZED
from aiocoap.error import NetworkError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from coap_server import get_lan_ip

# ── Device-side protocol contract (must match main_gateway.py) ───────────────
NONCE_LEN = 13      # 13-byte OSCORE nonce written by the gateway
TAG_LEN = 16        # 16-byte tag == cryptography.AESCCM() default
PRE_SHARED_KEY = b"TEST_KEY_1234567"

# Consecutive-fault abort threshold - MUST match AUTH_FAIL_THRESHOLD in
# ESP32 main.cpp. A healthy block resets the counter; the 3rd consecutive
# fault aborts the transfer (device rolls back to the previous firmware).
AUTH_FAIL_THRESHOLD = 3


class DeviceSession:
    """Stateful per-transfer fault tracker: the Python mirror of the ESP32
    `_authFaults` counter (main.cpp processIncomingPacket).

    Feed one boolean per received block: True = auth-decrypt OK, False =
    fault (tag mismatch, oversized chunk, transport error). Returns
    "CONTINUE" until the threshold trip, then "ABORT" - the rollback
    *decision*. Rollback *execution* (esp_ota_mark_app_invalid_rollback_and_
    reboot) needs real flash and stays hardware-side.
    """

    def __init__(self):
        self.auth_faults = 0
        self.blocks_ok = 0
        self.aborted = False

    def feed(self, ok: bool):
        """Record one block outcome. Returns "CONTINUE" or "ABORT"."""
        if self.aborted:
            return "ABORT"
        if ok:
            self.auth_faults = 0
            self.blocks_ok += 1
            return "CONTINUE"
        self.auth_faults += 1
        if self.auth_faults >= AUTH_FAIL_THRESHOLD:
            self.aborted = True
            return "ABORT"
        return "CONTINUE"


def process_frame(code, payload):
    """Mirror of the ESP32 D2-D4 pipeline, as importable Python.

    Returns a (status, detail) tuple:
      ("[BLOCKED]", str)  -> gateway refused (4.01 kill-switch / 4.04 missing)
      ("[TIMEOUT]", str)  -> gateway halted, no reply received
      ("[FAIL]",    str)  -> frame received but auth-decrypt rejected it
      ("[OK]",      bytes)-> frame authenticated and decrypted successfully
    """
    if code is None or str(code) == "TIMEOUT":
        return "[TIMEOUT]", "Gateway halted (revoked?) - no reply received."

    if code in (UNAUTHORIZED, NOT_FOUND):
        return "[BLOCKED]", f"Gateway refused (CoAP {code}). Verified patch missing or revoked."

    if code != CONTENT:
        return "[GATE]", f"Unexpected CoAP code {code}."

    if len(payload) < NONCE_LEN + TAG_LEN:
        return "[FAIL]", f"Frame too short ({len(payload)} bytes, need >= {NONCE_LEN + TAG_LEN})."

    # Nonce is the first 13 bytes; the tag is the final 16 aead bytes.
    nonce = payload[:NONCE_LEN]
    ciphertext_with_tag = payload[NONCE_LEN:]

    try:
        plaintext = AESCCM(PRE_SHARED_KEY).decrypt(nonce, ciphertext_with_tag, None)
        return "[OK]", plaintext
    except InvalidTag:
        return "[FAIL]", "Tag mismatch - payload tampered or wrong key."


async def fetch_firmware(server_ip: str, timeout: float = 5.0):
    """CoAP GET /firmware. Returns a (status, detail) tuple from process_frame."""
    print(f"[Client] Sending GET /firmware to coap://{server_ip}:5683 ...")

    protocol = await Context.create_client_context()
    try:
        request = Message(code=GET, uri=f"coap://{server_ip}/firmware")
        response = await asyncio.wait_for(protocol.request(request).response,
                                          timeout=timeout)
        return process_frame(response.code, response.payload)
    except asyncio.TimeoutError:
        return process_frame(None, b"")
    except NetworkError:
        # No reply and the socket reports the peer is gone - the gateway
        # process halted (e.g. revoked release) or is unreachable.
        return "[TIMEOUT]", "Gateway unreachable (halted/revoked?) - no reply received."
    except Exception as e:
        return "[GATE]", f"Request failed: {e}"
    finally:
        await protocol.shutdown()


async def main():
    print("[Client] Booting mock ESP32...")
    server_ip = get_lan_ip()
    status, detail = await fetch_firmware(server_ip)
    print(f"[Client] {status} - {detail}")

if __name__ == "__main__":
    asyncio.run(main())
