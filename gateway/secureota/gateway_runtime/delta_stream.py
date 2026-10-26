"""DOTA delta-stream codec - the gateway side of the gateway-to-device update format.

=============================================================================================
COMP 022 Software Engineering 2 - Program Documentation
---------------------------------------------------------------------------------------------
Program Title : DOTA delta-stream codec (delta_stream.py)
Programmers   :
System Design : Edge Gateway deploy unit - the gateway side of interface crossing 3
                (gateway -> device, CoAP /patch). Answered in full below.
Date Written  : 2026-10-01 (commit 050427b)
Date Revised  : 2026-10-07 (commit 87bfdf1, 4 KB deflate window);
                2026-10-26 (documentation pass, no change to the format)
Purpose       : Re-pack a ledger-verified BSDIFF40 patch into a stream an ESP32 can decode
                in one streaming pass inside a 4 KB window. Expanded under PURPOSE.
Structures    : A 16-byte header plus repeated (add, copy, seek) records, decoded in one
                streaming pass. Answered in full below.
=============================================================================================

PURPOSE
    Why a second format exists: releases are published on-chain as BSDIFF40 patches
    (bsdiff4). BSDIFF40 compresses its three blocks with bzip2 level 9, whose decompressor
    needs megabytes of RAM - impossible on an ESP32 (~320 KB). The gateway verifies the
    BSDIFF40 bytes against the on-chain golden hash FIRST, then re-packs the same bsdiff
    instructions into DOTA, which the device can decode in one streaming pass with the ROM's
    tinfl inflater. The deflate window is kept small (WINDOW_BITS = 12, 4 KB) so the device's
    ring dictionary - the largest RAM object of the updater - fits a Class 2 budget; on the
    real v1.0 -> v1.1 pair a 4 KB window costs nothing against 32 KB (see the SOP 1 report).

WHERE THE PROGRAM FITS IN THE GENERAL SYSTEM DESIGNS
    Deploy unit: Edge Gateway (see the deploy-unit table in documentations/ARCHITECTURE.md).
    This module implements the gateway half of interface crossing 3, "gateway -> device"
    (CoAP/UDP :5683). It owns the format and nothing else: it opens no socket, reads no
    configuration and touches no disk, which is what makes it testable on a workstation.

        ledger poll -> download -> golden-hash verify -> to_dota() -> encrypt_blocks()
                                                             |              |
                                                   artifacts/dota_*.bin   AES-CCM block
                                                                          frames served on
                                                                          CoAP /patch
                                                                               |
                                                                  ESP32 factory updater:
                                                                  DeltaDecoder, which
                                                                  mirrors apply_dota below

    main_gateway.py calls to_dota() inside its release loop, between hash verification and
    block framing; a ValueError raised here makes the gateway refuse to serve the release.
    apply_dota() is the reference decoder the firmware's DeltaDecoder class mirrors (firmware
    repository, src/factory/main.cpp), so WINDOW_BITS here must stay less than or equal to
    the firmware's DeltaDecoder::DICT_BITS, which is also 12. The SOP 1 and SOP 2 measurement
    runs (gateway/sop/sop1.py, gateway/sop/sop2.py) import this module directly.

DATA STRUCTURES, ALGORITHMS, AND CONTROL

  The idea in plain terms
    A firmware update normally ships a whole new program. This module ships only what
    changed between the old version and the new one, packaged so that a small device can
    unpack it unaided. On the v1.0 to v1.1 pair the device receives about 23 KB instead of
    the whole 282 KB image.

  Data structures
    A DOTA stream is a 16-byte header followed by a compressed list of instructions for
    turning the old image into the new one.

      header, 16 bytes, not compressed:
        0  4  magic b"DOTA", marks the format
        4  1  format version (1)
        5  1  memory the decoder needs, as log2 bytes (12 = 4 KB; 0 = an older 32 KB stream)
        6  2  reserved (zero)
        8  4  new_size: exact length of the finished image
       12  4  reserved (zero)
      body, deflate-compressed, one instruction at a time:
        add   how many bytes to build from the old image plus a correction
        copy  how many bytes to take straight from the stream
        seek  how far to move the reading position in the old image afterwards
      followed by those add and copy bytes themselves. Instructions repeat until new_size
      bytes exist.

    HEADER and RECORD are struct.Struct constants that declare this layout once, so the
    encoder and the decoder cannot disagree about it.

  Algorithms
    Encoding, bsdiff40_to_dota(), re-packages the patch the release builder produced. That
    patch is compressed with bzip2, which needs megabytes of memory to unpack - more than
    the ESP32 has - so the instructions are read out and re-compressed with deflate, which
    the chip unpacks in a 4 KB buffer. The instructions themselves are unchanged; only the
    wrapping is.

    Decoding, apply_dota(), rebuilds the image. For each instruction: build `add` bytes
    from the old image plus its corrections, copy `copy` bytes straight from the stream,
    then move the old-image position by add + seek. Reading past the end of the old image
    gives zero. This function is the written specification of the decoder; the ESP32
    firmware performs the same steps in C++, reading the old image from its ota_1 backup.

    full_image_to_dota() wraps a whole image as a single copy instruction, for bench runs
    where there is no patch to re-package.

  Control
    - to_dota() is the only entry point a caller needs: a patch is re-packaged, anything
      else is treated as a whole image.
    - _encode() is the only place that compresses, so the memory limit is checked once on
      behalf of every path.
    - Every failure raises ValueError stating what was expected and what arrived. The
      module never prints and never returns an error code; the caller decides what to do,
      and the gateway's decision is to refuse to serve the release.
    - No foreign exception escapes: bz2 and zlib failures are converted where they arise,
      and both struct.unpack_from calls are guarded by length checks first, so ValueError
      is the only failure a caller has to handle.
    - Old and new devices interoperate: a device refuses a stream that needs more memory
      than it has, accepts one that needs less, and devices built before byte 5 existed
      ignore it.

STYLE
    Four-space indentation, ASCII only, lines of at most 100 characters (the repository
    carries no linter configuration, so this limit is a convention declared here). Module
    state is seven UPPER_CASE constants and nothing else: no global variables and no `global`
    statements anywhere in the file.
"""
import bz2
import struct
import zlib

MAGIC = b"DOTA"
FORMAT_VERSION = 1
HEADER = struct.Struct("<4sBB2xI4x")     # 16 bytes: magic, version, window bits, new_size
RECORD = struct.Struct("<IIi")           # add, copy, seek
BSDIFF_MAGIC = b"BSDIFF40"

# Deflate window the gateway compresses with, as log2(bytes). The device dictionary
# (DICT_BITS in the firmware's DeltaDecoder) must be at least this large.
WINDOW_BITS = 12
LEGACY_WINDOW_BITS = 15                  # streams with header byte 5 == 0


def _offtin(raw: bytes) -> int:
    """bsdiff's sign-magnitude 64-bit integer."""
    value = int.from_bytes(raw, "little")
    if value & (1 << 63):
        return -(value & ((1 << 63) - 1))
    return value


def _encode(new_size: int, records, window_bits: int = WINDOW_BITS) -> bytes:
    """Deflate a record sequence behind a DOTA header - the one compression chokepoint.

    Every encoder path goes through here, so the window is validated once, in one place.
    `records` is an iterable of (add_diff, extra, seek) triples. Returns header + body.
    """
    if not 9 <= window_bits <= 15:
        raise ValueError("deflate window must be 2^9 .. 2^15 bytes")
    comp = zlib.compressobj(9, zlib.DEFLATED, -window_bits)
    body = []
    for add_diff, extra, seek in records:
        body.append(comp.compress(RECORD.pack(len(add_diff), len(extra), seek)))
        body.append(comp.compress(add_diff))
        body.append(comp.compress(extra))
    body.append(comp.flush())
    return HEADER.pack(MAGIC, FORMAT_VERSION, window_bits, new_size) + b"".join(body)


def bsdiff40_to_dota(patch: bytes, window_bits: int = WINDOW_BITS) -> bytes:
    """Re-pack a BSDIFF40 patch (as produced by bsdiff4.diff) into DOTA."""
    if len(patch) < 32 or patch[:8] != BSDIFF_MAGIC:
        raise ValueError("not a BSDIFF40 patch")
    ctrl_len = _offtin(patch[8:16])
    diff_len = _offtin(patch[16:24])
    new_size = _offtin(patch[24:32])
    if ctrl_len < 0 or diff_len < 0 or new_size < 0 or 32 + ctrl_len + diff_len > len(patch):
        raise ValueError("corrupt BSDIFF40 header")
    # bz2 reports corruption three different ways: OSError for a bad stream, ValueError for
    # a truncated one, EOFError at an unexpected end. Normalise them, so every failure in this
    # module is a ValueError. An empty block decompresses to b"" without raising at all; the
    # length checks below catch that case instead.
    try:
        ctrl = bz2.decompress(patch[32:32 + ctrl_len])
        diff = bz2.decompress(patch[32 + ctrl_len:32 + ctrl_len + diff_len])
        extra = bz2.decompress(patch[32 + ctrl_len + diff_len:])
    except (OSError, EOFError, ValueError) as exc:
        raise ValueError(f"corrupt BSDIFF40 compressed block: {exc}") from exc
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
    return _encode(new_size, records, window_bits)


def full_image_to_dota(image: bytes, window_bits: int = WINDOW_BITS) -> bytes:
    """A whole image as one copy-only record (bench DELTA_PAYLOAD path)."""
    return _encode(len(image), [(b"", image, 0)], window_bits)


def to_dota(payload: bytes, window_bits: int = WINDOW_BITS) -> bytes:
    """BSDIFF40 patches are re-packed; anything else is a full image."""
    if payload[:8] == BSDIFF_MAGIC:
        return bsdiff40_to_dota(payload, window_bits)
    return full_image_to_dota(payload, window_bits)


def apply_dota(old: bytes, dota: bytes, dict_bits: int = 15) -> bytes:
    """Reference decoder - the specification the ESP32 DeltaDecoder mirrors.

    `dict_bits` is the decoder's ring-dictionary size (log2 bytes). Like the device,
    it refuses a stream compressed with a larger window instead of decoding garbage.
    """
    if len(dota) < HEADER.size:
        raise ValueError(f"stream is {len(dota)} B, the header alone needs {HEADER.size} B")
    magic, version, window_bits, new_size = HEADER.unpack_from(dota)
    if magic != MAGIC or version != FORMAT_VERSION:
        raise ValueError("not a DOTA v1 stream")
    window_bits = window_bits or LEGACY_WINDOW_BITS
    if not 9 <= window_bits <= 15:
        raise ValueError(f"bad deflate window 2^{window_bits}")
    if window_bits > dict_bits:
        raise ValueError(f"stream needs a 2^{window_bits} B window, "
                         f"decoder dictionary is 2^{dict_bits} B")
    try:
        body = zlib.decompress(dota[HEADER.size:], -window_bits)
    except zlib.error as exc:
        raise ValueError(f"corrupt deflate body: {exc}") from exc
    # Loop invariants: `out` grows to exactly new_size bytes and is never rewound; `pos` is the
    # read cursor into the inflated body; `oldpos` is the cursor into the base image, advanced
    # by add + seek once per record.
    out = bytearray()
    pos = oldpos = 0
    while len(out) < new_size:
        # One record: a fixed-size header, then `add` diff bytes, then `copy` verbatim bytes.
        if pos + RECORD.size > len(body):
            raise ValueError(f"stream ends after {len(out)} of {new_size} B: records exhausted")
        add, copy, seek = RECORD.unpack_from(body, pos)
        pos += RECORD.size
        if len(out) + add + copy > new_size or pos + add + copy > len(body):
            raise ValueError("record overruns the stream")
        for i in range(add):
            # An index outside the old image contributes 0, so the diff byte is used as is.
            # The firmware's _readOld() gets the same effect by zeroing its buffer first.
            o = oldpos + i
            base = old[o] if 0 <= o < len(old) else 0
            out.append((body[pos + i] + base) & 0xFF)
        pos += add
        out += body[pos:pos + copy]       # "extra" bytes: no base, copied straight out
        pos += copy
        oldpos += add + seek              # bspatch semantics: seek adjusts the base cursor
    return bytes(out)
