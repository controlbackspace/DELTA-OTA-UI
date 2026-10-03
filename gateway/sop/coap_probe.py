"""A tiny CoAP client for probing a running gateway with raw UDP.

The runner only needs "what code does /version answer right now?", measured with
sub-100 ms granularity and no asyncio. Frame layout follows RFC 7252 and mirrors
what the ESP32 sends (CON GET, Uri-Path, optional Uri-Query).
"""
from __future__ import annotations

import os
import socket
import time


def build_get(path: str, mid: int, query: str | None = None) -> bytes:
    """CON GET /<path>[?query] with no token."""
    p, q = path.encode(), query.encode() if query else b""
    if len(p) > 12 or len(q) > 12:
        raise ValueError("option too long for the one-byte length form")
    out = bytes([0x40, 0x01, mid >> 8, mid & 0xFF])
    out += bytes([(11 << 4) | len(p)]) + p             # Uri-Path = 11
    if q:
        out += bytes([(4 << 4) | len(q)]) + q          # Uri-Query = 15 (delta 4 from 11)
    return out


def code_name(code_byte: int) -> str:
    return f"{code_byte >> 5}.{code_byte & 0x1F:02d}"


def parse_response(datagram: bytes) -> tuple[str, bytes]:
    """('2.05', payload) from a CoAP reply; raises ValueError on a runt/malformed one."""
    if len(datagram) < 4:
        raise ValueError("runt datagram")
    tkl = datagram[0] & 0x0F
    i = 4 + tkl
    while i < len(datagram) and datagram[i] != 0xFF:       # skip options
        opt = datagram[i]
        i += 1
        for nib in (opt >> 4, opt & 0x0F):
            if nib == 13:
                i += 1
            elif nib == 14:
                i += 2
            elif nib == 15:
                raise ValueError("reserved option nibble")
        length = opt & 0x0F
        length = length if length < 13 else (datagram[i - 1] + 13 if length == 13 else 269)
        i += length
    payload = datagram[i + 1:] if i < len(datagram) and datagram[i] == 0xFF else b""
    return code_name(datagram[1]), payload


def probe(host: str, port: int, path: str, query: str | None = None, timeout: float = 0.3):
    """Send one GET and return (code, payload, rtt_s); (None, b"", None) if no reply."""
    mid = int.from_bytes(os.urandom(2), "big")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t0 = time.perf_counter()
        s.sendto(build_get(path, mid, query), (host, port))
        try:
            data, _ = s.recvfrom(2048)
        except (socket.timeout, ConnectionResetError, OSError):
            return None, b"", None
        rtt = time.perf_counter() - t0
    try:
        code, payload = parse_response(data)
    except ValueError:
        return None, b"", None
    return code, payload, rtt


def udp_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False
