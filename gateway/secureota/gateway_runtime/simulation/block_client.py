"""Block-protocol harness for the /patch endpoint (no ESP32 required).

Mirrors ESP32 main.cpp requestChunk/processIncomingPacket over raw UDP:
CON GET, Uri-Path "patch", block number in the CoAP message ID. Verifies
every block independently auth-decodes, the reassembled bytes equal the
verified payload, the final block answers 2.04, and out-of-range answers
4.04. Uses a thread-pooled blocking socket (Windows Proactor has no
async datagram recv).

CoAP note: servers dedup CONs by (source port, MID) for EXCHANGE_LIFETIME,
so each pass uses a FRESH socket - reusing MIDs from the same port would
replay the previous pass's cached responses (RFC 7252, section 4.5).

Run:  python simulation/block_client.py
"""
import sys
from pathlib import Path

# Make the production gateway_runtime modules importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import socket

import aiocoap
import aiocoap.resource as resource
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from coap_server import FirmwareResource, PatchBlockResource, get_lan_ip
from security_engine import SecurityEngine
from main_gateway import ARTIFACT_DIR, BLOCKS_DIR, DUMMY_PATCH, PRE_SHARED_KEY

SERVER_PORT = 5683
TIMEOUT = 3.0
FAILURES = 0

# CoAP codes relevant to the chunk protocol.
CONTENT = 0x45      # 2.05 data block
CHANGED = 0x44      # 2.04 final block (commit + reboot)
UNAUTHORIZED = 0x81  # 4.01 kill-switch
NOT_FOUND = 0x84    # 4.04 unknown block


def check(label, actual, expected):
    """Assert-pass/fail with a clear verdict line."""
    global FAILURES
    ok = actual == expected
    print(f"    -> [{'PASS' if ok else 'FAIL'}] {label}: got {actual!r} (expected {expected!r})")
    if not ok:
        FAILURES += 1
    return ok


class RawBlockClient:
    """Minimal CON GET client with explicit message IDs (what aiocoap hides)."""

    def __init__(self, server_ip: str, port: int = SERVER_PORT, timeout: float = TIMEOUT):
        self.addr = (server_ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)

    def get_block(self, index: int):
        """One exchange. Returns (code, body) or (None, b"") on timeout."""
        hi, lo = (index >> 8) & 0xFF, index & 0xFF
        # ver=1, CON, TKL=0 | GET | MID=index, then Uri-Path "patch" (delta 11, len 5).
        datagram = bytes([0x40, 0x01, hi, lo, 0xB5]) + b"patch"
        try:
            self.sock.sendto(datagram, self.addr)
            raw, _ = self.sock.recvfrom(65535)
        except socket.timeout:
            return None, b""
        tkl = raw[0] & 0x0F
        code = raw[1]
        mid = (raw[2] << 8) | raw[3]
        if mid != (index & 0xFFFF):
            return -1, b""
        marker = raw.find(b"\xFF", 4 + tkl)
        body = raw[marker + 1:] if marker != -1 else b""
        return code, body

    def close(self):
        self.sock.close()


async def shutdown_ctx(ctx):
    """Idempotent Context shutdown (aiocoap quirk, see run_simulation.py)."""
    if ctx is None or getattr(ctx, "_demo_closed", False):
        return
    ctx._demo_closed = True
    try:
        await ctx.shutdown()
    except AttributeError:
        pass


async def run_pass(loop, server_ip: str, payload_path: Path, label: str):
    """One full fetch: all blocks auth-decode, reassembly matches, range checked."""
    print(f"\n--- {label} ---")
    engine = SecurityEngine()
    count = await loop.run_in_executor(
        None, engine.encrypt_blocks, payload_path, BLOCKS_DIR, PRE_SHARED_KEY)
    print(f"[Harness] {count} block frame(s) staged from {payload_path.name}.")
    if not check("block count > 0", count > 0, True):
        return

    # Fresh socket per pass (see module docstring: MID dedup replay).
    client = RawBlockClient(server_ip)
    try:
        plaintext_parts = []
        for index in range(count):
            code, body = await loop.run_in_executor(None, client.get_block, index)
            expected = CHANGED if index == count - 1 else CONTENT
            check(f"block {index} code", code, expected)
            if code not in (CONTENT, CHANGED):
                continue
            try:
                plaintext_parts.append(
                    AESCCM(PRE_SHARED_KEY).decrypt(body[:13], body[13:], None))
                print(f"    -> [PASS] block {index} auth-decrypt ({len(body)} B frame)")
            except InvalidTag:
                check(f"block {index} auth-decrypt", "InvalidTag", "OK")

        reassembled = b"".join(plaintext_parts)
        check("reassembled bytes", reassembled, payload_path.read_bytes())

        code, _ = await loop.run_in_executor(None, client.get_block, count)
        check("out-of-range block code", code, NOT_FOUND)
    finally:
        client.close()


async def main():
    print("Delta-OTA block-protocol harness - raw UDP, MID-indexed GET /patch.")
    loop = asyncio.get_running_loop()
    server_ip = get_lan_ip()

    site = resource.Site()
    site.add_resource(['firmware'], FirmwareResource())
    site.add_resource(['patch'], PatchBlockResource())
    ctx = await aiocoap.Context.create_server_context(
        site, bind=(server_ip, SERVER_PORT))
    print(f"[Harness] Server up on {server_ip}:{SERVER_PORT}.")

    try:
        # Pass 1: the real verified payload (single block exercises 2.04-final).
        await run_pass(loop, server_ip, DUMMY_PATCH, "pass 1/2: real payload")

        # Pass 2: deterministic 3000-byte image -> 3 blocks, multi-chunk path.
        big = ARTIFACT_DIR / "harness_payload.bin"
        big.write_bytes((b"firmware-image-v1.1:" * 160)[:3000])
        try:
            await run_pass(loop, server_ip, big, "pass 2/2: multi-block image")
        finally:
            big.unlink(missing_ok=True)
    finally:
        await shutdown_ctx(ctx)

    print("\n" + "=" * 62)
    if FAILURES == 0:
        print("  BLOCK HARNESS RESULT: ALL CHECKS PASSED")
    else:
        print(f"  BLOCK HARNESS RESULT: {FAILURES} CHECK(S) FAILED")
    print("=" * 62)
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    asyncio.run(main())
