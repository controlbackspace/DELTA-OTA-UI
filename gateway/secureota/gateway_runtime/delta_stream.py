"""DOTA: the device-side delta stream format (bsdiff semantics, ESP32-sized).

Why a second format: releases are published on-chain as BSDIFF40 patches
(bsdiff4). BSDIFF40 compresses its three blocks with bzip2 level 9, whose
decompressor needs megabytes of RAM - impossible on an ESP32 (~320 KB). The
gateway verifies the BSDIFF40 bytes against the on-chain golden hash FIRST,
then re-packs the same bsdiff instructions into DOTA, which the device can
decode in one streaming pass with the ROM's tinfl inflater (32 KB window).

Layout (all integers little-endian):
  header, 16 bytes, NOT compressed:
    0  4  magic  b"DOTA"
    4  1  format version (1)
    5  3  reserved (zero)
    8  4  u32 new_size   - exact length of the reconstructed image
   12  4  reserved (zero)
  body: raw deflate (zlib wbits=-15) of a record sequence:
    u32 add   - bytes to produce as  old[oldpos+i] + diff[i]  (mod 256)
    u32 copy  - bytes to copy verbatim from the record (bsdiff "extra")
    i32 seek  - adjustment to oldpos after the record (may be negative)
    add  diff bytes
    copy extra bytes
  Records repeat until new_size bytes have been produced.

Semantics are exactly bspatch's: after a record, oldpos += add + seek; an
old index outside [0, old_size) contributes 0 (the diff byte is used as is).
The device reads `old` from the ota_1 backup of the running app.
"""
import bz2
import struct
import zlib

MAGIC = b"DOTA"
FORMAT_VERSION = 1
HEADER = struct.Struct("<4sB3xI4x")      # 16 bytes
RECORD = struct.Struct("<IIi")           # add, copy, seek
BSDIFF_MAGIC = b"BSDIFF40"


def _offtin(raw: bytes) -> int:
    """bsdiff's sign-magnitude 64-bit integer."""
    value = int.from_bytes(raw, "little")
    if value & (1 << 63):
        return -(value & ((1 << 63) - 1))
    return value


def _encode(new_size: int, records) -> bytes:
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = []
    for add_diff, extra, seek in records:
        body.append(comp.compress(RECORD.pack(len(add_diff), len(extra), seek)))
        body.append(comp.compress(add_diff))
        body.append(comp.compress(extra))
    body.append(comp.flush())
    return HEADER.pack(MAGIC, FORMAT_VERSION, new_size) + b"".join(body)


def bsdiff40_to_dota(patch: bytes) -> bytes:
    """Re-pack a BSDIFF40 patch (as produced by bsdiff4.diff) into DOTA."""
    if len(patch) < 32 or patch[:8] != BSDIFF_MAGIC:
        raise ValueError("not a BSDIFF40 patch")
    ctrl_len = _offtin(patch[8:16])
    diff_len = _offtin(patch[16:24])
    new_size = _offtin(patch[24:32])
    if ctrl_len < 0 or diff_len < 0 or new_size < 0 or 32 + ctrl_len + diff_len > len(patch):
        raise ValueError("corrupt BSDIFF40 header")
    ctrl = bz2.decompress(patch[32:32 + ctrl_len])
    diff = bz2.decompress(patch[32 + ctrl_len:32 + ctrl_len + diff_len])
    extra = bz2.decompress(patch[32 + ctrl_len + diff_len:])
    if len(ctrl) % 24:
        raise ValueError("corrupt BSDIFF40 control block")

    records, dpos, epos, produced = [], 0, 0, 0
    for off in range(0, len(ctrl), 24):
        add = _offtin(ctrl[off:off + 8])
        copy = _offtin(ctrl[off + 8:off + 16])
        seek = _offtin(ctrl[off + 16:off + 24])
        if add < 0 or copy < 0 or dpos + add > len(diff) or epos + copy > len(extra):
            raise ValueError("BSDIFF40 control entry out of range")
        if not -(1 << 31) <= seek < (1 << 31):
            raise ValueError("seek does not fit in i32")
        records.append((diff[dpos:dpos + add], extra[epos:epos + copy], seek))
        dpos += add
        epos += copy
        produced += add + copy
    if produced != new_size:
        raise ValueError(f"control block produces {produced} bytes, header says {new_size}")
    return _encode(new_size, records)


def full_image_to_dota(image: bytes) -> bytes:
    """A whole image as one copy-only record (bench DELTA_PAYLOAD path)."""
    return _encode(len(image), [(b"", image, 0)])


def to_dota(payload: bytes) -> bytes:
    """BSDIFF40 patches are re-packed; anything else is a full image."""
    if payload[:8] == BSDIFF_MAGIC:
        return bsdiff40_to_dota(payload)
    return full_image_to_dota(payload)


def apply_dota(old: bytes, dota: bytes) -> bytes:
    """Reference decoder - the specification the ESP32 DeltaDecoder mirrors."""
    magic, version, new_size = HEADER.unpack_from(dota)
    if magic != MAGIC or version != FORMAT_VERSION:
        raise ValueError("not a DOTA v1 stream")
    body = zlib.decompress(dota[HEADER.size:], -15)
    out = bytearray()
    pos = oldpos = 0
    while len(out) < new_size:
        add, copy, seek = RECORD.unpack_from(body, pos)
        pos += RECORD.size
        if len(out) + add + copy > new_size or pos + add + copy > len(body):
            raise ValueError("record overruns the stream")
        for i in range(add):
            o = oldpos + i
            base = old[o] if 0 <= o < len(old) else 0
            out.append((body[pos + i] + base) & 0xFF)
        pos += add
        out += body[pos:pos + copy]
        pos += copy
        oldpos += add + seek
    return bytes(out)
