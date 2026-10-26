"""DOTA delta-stream codec - turns a firmware patch into a stream a small device can decode.

=============================================================================================
COMP 022 Software Engineering 2 - Program Documentation
---------------------------------------------------------------------------------------------
Program Title : DOTA delta-stream codec (delta_stream.py)
Programmers   :
System Design : The payload format of the edge gateway, the machine that sits between the
                release ledger and the fleet of devices. Answered in full below.
Date Written  : 2026-10-01
Date Revised  : 2026-10-07, when the compression window was reduced to 4 KB;
                2026-10-26, a documentation pass that left the format unchanged
Purpose       : Re-package a verified firmware patch into a stream that a decoder with
                4 KB of working memory can rebuild in one pass. Answered in full below.
Structures    : A sixteen-byte header followed by a compressed list of instructions.
                Answered in full below.
=============================================================================================

PURPOSE
    A firmware update normally ships an entire new program to the device. This module ships
    only what changed between the old version and the new one, packaged so that a small
    device can unpack it unaided. On the v1.0 to v1.1 pair used throughout the study, the
    device receives about 23 KB instead of the whole 282 KB image.

    A second format is needed because of memory. Patches are published in the standard
    bsdiff format, which compresses its contents with bzip2, and a bzip2 decompressor needs
    megabytes of working memory - far more than the 320 KB the target microcontroller has.
    This module keeps the patch instructions exactly as they are and re-compresses them with
    deflate instead, inside a window small enough that the decoder's dictionary, the largest
    single object it holds in memory, fits the project's constrained-device budget. On the
    real image pair that smaller window costs nothing in stream size.

WHERE THE PROGRAM FITS IN THE GENERAL SYSTEM DESIGNS
    This module is the payload format of the edge gateway, the machine that sits between the
    release ledger and the fleet of devices. It owns the format and nothing else: it opens no
    network connection, reads no configuration and writes no files, which is what makes it
    testable on a workstation with no hardware present.

    The gateway's release loop reaches this module once a release has been approved on the
    ledger and the downloaded bytes have been checked against the hash recorded there. The
    verified bytes are re-packaged here, and the block-encryption step that follows slices
    the result into independently encrypted frames, which a device then requests one at a
    time over its constrained-network protocol. If this module rejects a payload, the gateway
    refuses to serve that release at all.

    The decoder in this module is also the written specification of the decoder on the
    device: the updater resident in the device's factory partition performs the same steps in
    C++, and the window this module compresses with must never exceed the dictionary size
    that updater reserves. The project's measurement harness calls this module directly as
    well, to time and size the conversion with no device attached.

DATA STRUCTURES, ALGORITHMS, AND CONTROL
    The data structure this module produces is called a DOTA stream, and it consists of a
    sixteen-byte header followed by a compressed list of instructions for turning the old
    image into the new one. The header is never compressed, so a device can read it before
    committing any memory. Bytes 0 to 3 hold the characters DOTA, which mark the format; byte
    4 holds the format version, currently 1; byte 5 records how much memory the decoder will
    need, written as a power of two, so that a value of 12 means 4 KB while a value of 0
    identifies an older stream that assumed 32 KB; bytes 6 and 7 are reserved and set to
    zero; bytes 8 to 11 hold new_size, the exact length of the finished image; and bytes 12
    to 15 are reserved and also zero.

    The body that follows is deflate-compressed and holds one instruction after another until
    new_size bytes of output exist. Each instruction begins with three numbers: add, the
    number of bytes to build from the old image plus a correction; copy, the number of bytes
    to take straight from the stream; and seek, how far to move the reading position in the
    old image once the instruction is finished. The add and copy bytes themselves follow those
    three numbers. Two constants, HEADER and RECORD, declare this layout once as struct.Struct
    specifications, so the encoder and the decoder cannot disagree about it.

    Two algorithms work on that structure. Encoding, in bsdiff40_to_dota, re-packages a
    published patch: the instructions are read out of the bzip2 container they arrive in and
    re-compressed with deflate, which the device can unpack inside a 4 KB buffer. The
    instructions themselves are never altered, only their wrapping. Decoding, in apply_dota,
    rebuilds the image by working through the instructions in order: it builds add bytes from
    the old image plus their corrections, copies copy bytes straight from the stream, and then
    moves the old-image position forward by add plus seek. Reading past the end of the old
    image simply yields zero. The device does the same, reading the old image from its backup
    copy of the running application. A third function, full_image_to_dota, wraps a whole image
    as a single copy instruction, for bench runs where there is no patch to re-package.

    Control through the module is deliberately narrow. to_dota is the only entry point a
    caller needs: a patch is re-packaged, and anything else is treated as a whole image.
    _encode is the only place that compresses, so the memory limit is checked once on behalf
    of every path that reaches it. Every failure raises a ValueError stating what was expected
    and what actually arrived; the module never prints and never returns an error code,
    because policy belongs to the caller, and the gateway's policy is to refuse to serve the
    release. No foreign exception escapes either: bz2 and zlib failures are converted where
    they arise, and both struct.unpack_from calls are guarded by length checks first, so
    ValueError is the only failure a caller has to handle. Finally, old and new devices
    interoperate: a device refuses a stream that needs more memory than it has, accepts one
    that needs less, and devices built before byte 5 existed ignore it.

STYLE
    Four-space indentation, ASCII only, lines of at most 100 characters; the repository
    carries no linter configuration, so this limit is a convention declared here. Module
    state is seven named constants and nothing else: no global variables, no global
    statements.
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
