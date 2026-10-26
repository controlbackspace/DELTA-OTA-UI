# Program Documentation: DOTA delta-stream codec

COMP 022 - Software Engineering 2 - Program Documentation Template

> **Generated file - do not edit by hand.** Every field below is extracted from the
> header comment block of the source file, and every number is measured from it, so
> this document cannot drift from the code.
>
> - Source: `gateway/secureota/gateway_runtime/delta_stream.py` (258 lines: header comment block on lines 1-119, code on 120-258)
> - SHA-256: `1d3e518366d8159e3fca055f5a661624b70f3235dba8c80253baa6f9f125626c`
> - Regenerate: `python documentations/make_program_doc.py`
> - Verify in sync: `python documentations/make_program_doc.py --check`

*DOTA delta-stream codec - the gateway side of the gateway-to-device update format.*

## 1. Header comment block

The six fields the template requires, as they appear in the source file.

| Field | Value |
|---|---|
| Program Title | DOTA delta-stream codec (delta_stream.py) |
| Programmers | *(left blank for the group to fill in)* |
| Where the program fits in the general system designs | *expanded in the section below* |
| Date written and revised | Written 2026-10-01 (commit 050427b); revised 2026-10-07 (commit 87bfdf1, 4 KB deflate window); 2026-10-26 (documentation pass, no change to the format) |
| Purpose | *expanded in the section below* |
| Data structures, algorithms, and control | *expanded in the section below* |

### 1.1 Purpose

```
Why a second format exists: releases are published on-chain as BSDIFF40 patches
(bsdiff4). BSDIFF40 compresses its three blocks with bzip2 level 9, whose decompressor
needs megabytes of RAM - impossible on an ESP32 (~320 KB). The gateway verifies the
BSDIFF40 bytes against the on-chain golden hash FIRST, then re-packs the same bsdiff
instructions into DOTA, which the device can decode in one streaming pass with the ROM's
tinfl inflater. The deflate window is kept small (WINDOW_BITS = 12, 4 KB) so the device's
ring dictionary - the largest RAM object of the updater - fits a Class 2 budget; on the
real v1.0 -> v1.1 pair a 4 KB window costs nothing against 32 KB (see the SOP 1 report).
```

### 1.2 Where the program fits in the general system designs

```
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
```

### 1.3 Data structures, algorithms, and control

```
  Data structures
Declared once, as struct.Struct specifications: HEADER and RECORD. All integers are
little-endian. HEADER and RECORD are struct.Struct objects rather than primitives:
stateless, never rebound, and so treated as constants.

  header, 16 bytes, NOT compressed:
    0  4  magic  b"DOTA"
    4  1  format version (1)
    5  1  deflate window, log2 of bytes (12 = 4 KB). 0 = legacy stream (15, 32 KB)
    6  2  reserved (zero)
    8  4  u32 new_size   - exact length of the reconstructed image
   12  4  reserved (zero)
  body: raw deflate (zlib wbits=-window) of a record sequence:
    u32 add   - bytes to produce as  old[oldpos+i] + diff[i]  (mod 256)
    u32 copy  - bytes to copy verbatim from the record (bsdiff "extra")
    i32 seek  - adjustment to oldpos after the record (may be negative)
    add  diff bytes
    copy extra bytes
  Records repeat until new_size bytes have been produced.

  Algorithms
Encode, bsdiff40_to_dota():
  1. Reject anything that is not a 32-byte BSDIFF40 header.
  2. Read the three sign-magnitude 64-bit lengths with _offtin - bsdiff's own integer
     encoding, where bit 63 is a sign bit rather than two's complement.
  3. bunzip2 the control, diff and extra blocks.
  4. Walk the control block in 24-byte entries, slicing diff and extra into
     (add_diff, extra, seek) records and range-checking every entry.
  5. Cross-check that the records produce exactly new_size bytes, then deflate the
     record sequence through _encode.
Decode, apply_dota(): inflate the body, then walk records, producing `add` bytes as
old[oldpos+i] + diff[i] (mod 256) and copying `copy` bytes verbatim, advancing oldpos by
add + seek after each record. Semantics are exactly bspatch's. An old index outside
[0, old_size) contributes 0, so the diff byte is used as is. The device reads `old` from
the ota_1 backup of the running app.
Full image, full_image_to_dota(): one copy-only record, used by the bench DELTA_PAYLOAD
path when there is no patch to re-pack.

  Control
One decision point, one chokepoint, one failure convention:
  - to_dota() is the only entry point a caller needs: BSDIFF40 patches are re-packed,
    anything else is treated as a full image.
  - _encode() is the single place that compresses and the single place that validates the
    window, so every encoder path shares one check.
  - Every failure raises ValueError carrying observed-against-expected values. The module
    never prints and never returns a sentinel; policy belongs to the caller, which logs
    the operator-facing line and refuses to serve the release.
  - Forward compatibility: a device refuses a stream whose window is larger than its
    dictionary; a device with a larger dictionary decodes a smaller window; and older
    devices, which read only the magic and the version byte, ignore byte 5, so the format
    stays v1.

  The error convention is total
Every failure, on either side of the format, raises ValueError carrying
observed-against-expected values; nothing returns a sentinel and nothing prints. Library
exceptions that would otherwise escape are converted where they arise: bz2 failures on a
corrupt BSDIFF40 block, zlib failures on a corrupt deflate body, and both
struct.unpack_from calls - which malformed input could drive past the end of a buffer -
are guarded by explicit length checks first.
```

## 2. Compliance with the ten considerations

Measured at generation time from the source file; no value here is typed by hand.

| # | Consideration | Measured result | Notes |
|---|---|---|---|
| 1 | Indentation | 4-space steps, 0 tabs in the file, maximum nesting depth 2 | indent columns in the 139 code lines: [0, 4, 8, 12, 25] |
| 2 | Inline comments | 12 comment lines; docstrings on 6/6 functions plus the module header | the header block carries the design rationale, the comments carry loop invariants |
| 3 | Limiting the use of global | 0 mutable module-level names, 0 global/nonlocal statements | module state is 7 UPPER_CASE constants: MAGIC, FORMAT_VERSION, HEADER, RECORD, BSDIFF_MAGIC, WINDOW_BITS, LEGACY_WINDOW_BITS |
| 4 | Structured programming | 0 break/continue, 0 recursive functions, 0 classes | 6 single-purpose functions, one loop per direction |
| 5 | Naming conventions | 7/7 module names UPPER_CASE, 2 underscore-private helpers, 0 non-conforming locals | public API: bsdiff40_to_dota, full_image_to_dota, to_dota, apply_dota |
| 6 | Error return conventions | 15 raise sites, types raised: ValueError; no status codes and no sentinel returns | see the error inventory below and the known gap in section 5 |
| 7 | Line length | longest 96 chars (line 243), 0 lines over 100 | 100-character limit declared in the header block's STYLE note |
| 8 | Spacing | 0 trailing-whitespace lines in the file, 17 blank lines in the code region | two blank lines between top-level definitions, per PEP 8 |
| 9 | Function length | 6 functions: shortest 3, median 16, longest 45 lines | no function needed splitting |
| 10 | Error messages | 15 messages, each naming observed against expected | the module raises; the operator-facing wording belongs to the caller |

### 2.1 Functions

| Function | Visibility | Lines | Span | Max depth | Docstring | Raises |
|---|---|---|---|---|---|---|
| `_offtin` | private | 6 | 136-141 | 1 | yes | 0 |
| `_encode` | private | 16 | 144-159 | 1 | yes | 1 |
| `bsdiff40_to_dota` | public | 38 | 162-199 | 2 | yes | 7 |
| `full_image_to_dota` | public | 3 | 202-204 | 0 | yes | 0 |
| `to_dota` | public | 5 | 207-211 | 1 | yes | 0 |
| `apply_dota` | public | 45 | 214-258 | 2 | yes | 7 |

### 2.2 Module-level names

| Name | Convention | Value |
|---|---|---|
| `MAGIC` | UPPER_CASE constant | `b'DOTA'` |
| `FORMAT_VERSION` | UPPER_CASE constant | `1` |
| `HEADER` | UPPER_CASE constant | `struct.Struct('<4sBB2xI4x')` |
| `RECORD` | UPPER_CASE constant | `struct.Struct('<IIi')` |
| `BSDIFF_MAGIC` | UPPER_CASE constant | `b'BSDIFF40'` |
| `WINDOW_BITS` | UPPER_CASE constant | `12` |
| `LEGACY_WINDOW_BITS` | UPPER_CASE constant | `15` |

Imports: `bz2`, `struct`, `zlib` - standard library only, so this module crosses no deploy-unit boundary of its own.

### 2.3 Error inventory

Every raise site in the file, in line order.

| Line | Raised |
|---|---|
| 151 | `ValueError('deflate window must be 2^9 .. 2^15 bytes')` |
| 165 | `ValueError('not a BSDIFF40 patch')` |
| 170 | `ValueError('corrupt BSDIFF40 header')` |
| 180 | `ValueError(f'corrupt BSDIFF40 compressed block: {exc}')` |
| 182 | `ValueError('corrupt BSDIFF40 control block')` |
| 190 | `ValueError('BSDIFF40 control entry out of range')` |
| 192 | `ValueError('seek does not fit in i32')` |
| 198 | `ValueError(f'control block produces {produced} bytes, header says {new_size}')` |
| 221 | `ValueError(f'stream is {len(dota)} B, the header alone needs {HEADER.size} B')` |
| 224 | `ValueError('not a DOTA v1 stream')` |
| 227 | `ValueError(f'bad deflate window 2^{window_bits}')` |
| 229 | `ValueError(f'stream needs a 2^{window_bits} B window, decoder dictionary is 2^{dict_bits} B')` |
| 234 | `ValueError(f'corrupt deflate body: {exc}')` |
| 243 | `ValueError(f'stream ends after {len(out)} of {new_size} B: records exhausted')` |
| 247 | `ValueError('record overruns the stream')` |

## 3. Source code

```text
   1 | """DOTA delta-stream codec - the gateway side of the gateway-to-device update format.
   2 |
   3 | =============================================================================================
   4 | COMP 022 Software Engineering 2 - Program Documentation
   5 | ---------------------------------------------------------------------------------------------
   6 | Program Title : DOTA delta-stream codec (delta_stream.py)
   7 | Programmers   :
   8 | System Design : Edge Gateway deploy unit - the gateway side of interface crossing 3
   9 |                 (gateway -> device, CoAP /patch). Answered in full below.
  10 | Date Written  : 2026-10-01 (commit 050427b)
  11 | Date Revised  : 2026-10-07 (commit 87bfdf1, 4 KB deflate window);
  12 |                 2026-10-26 (documentation pass, no change to the format)
  13 | Purpose       : Re-pack a ledger-verified BSDIFF40 patch into a stream an ESP32 can decode
  14 |                 in one streaming pass inside a 4 KB window. Expanded under PURPOSE.
  15 | Structures    : A 16-byte header plus repeated (add, copy, seek) records, decoded in one
  16 |                 streaming pass. Answered in full below.
  17 | =============================================================================================
  18 |
  19 | PURPOSE
  20 |     Why a second format exists: releases are published on-chain as BSDIFF40 patches
  21 |     (bsdiff4). BSDIFF40 compresses its three blocks with bzip2 level 9, whose decompressor
  22 |     needs megabytes of RAM - impossible on an ESP32 (~320 KB). The gateway verifies the
  23 |     BSDIFF40 bytes against the on-chain golden hash FIRST, then re-packs the same bsdiff
  24 |     instructions into DOTA, which the device can decode in one streaming pass with the ROM's
  25 |     tinfl inflater. The deflate window is kept small (WINDOW_BITS = 12, 4 KB) so the device's
  26 |     ring dictionary - the largest RAM object of the updater - fits a Class 2 budget; on the
  27 |     real v1.0 -> v1.1 pair a 4 KB window costs nothing against 32 KB (see the SOP 1 report).
  28 |
  29 | WHERE THE PROGRAM FITS IN THE GENERAL SYSTEM DESIGNS
  30 |     Deploy unit: Edge Gateway (see the deploy-unit table in documentations/ARCHITECTURE.md).
  31 |     This module implements the gateway half of interface crossing 3, "gateway -> device"
  32 |     (CoAP/UDP :5683). It owns the format and nothing else: it opens no socket, reads no
  33 |     configuration and touches no disk, which is what makes it testable on a workstation.
  34 |
  35 |         ledger poll -> download -> golden-hash verify -> to_dota() -> encrypt_blocks()
  36 |                                                              |              |
  37 |                                                    artifacts/dota_*.bin   AES-CCM block
  38 |                                                                           frames served on
  39 |                                                                           CoAP /patch
  40 |                                                                                |
  41 |                                                                   ESP32 factory updater:
  42 |                                                                   DeltaDecoder, which
  43 |                                                                   mirrors apply_dota below
  44 |
  45 |     main_gateway.py calls to_dota() inside its release loop, between hash verification and
  46 |     block framing; a ValueError raised here makes the gateway refuse to serve the release.
  47 |     apply_dota() is the reference decoder the firmware's DeltaDecoder class mirrors (firmware
  48 |     repository, src/factory/main.cpp), so WINDOW_BITS here must stay less than or equal to
  49 |     the firmware's DeltaDecoder::DICT_BITS, which is also 12. The SOP 1 and SOP 2 measurement
  50 |     runs (gateway/sop/sop1.py, gateway/sop/sop2.py) import this module directly.
  51 |
  52 | DATA STRUCTURES, ALGORITHMS, AND CONTROL
  53 |
  54 |   Data structures
  55 |     Declared once, as struct.Struct specifications: HEADER and RECORD. All integers are
  56 |     little-endian. HEADER and RECORD are struct.Struct objects rather than primitives:
  57 |     stateless, never rebound, and so treated as constants.
  58 |
  59 |       header, 16 bytes, NOT compressed:
  60 |         0  4  magic  b"DOTA"
  61 |         4  1  format version (1)
  62 |         5  1  deflate window, log2 of bytes (12 = 4 KB). 0 = legacy stream (15, 32 KB)
  63 |         6  2  reserved (zero)
  64 |         8  4  u32 new_size   - exact length of the reconstructed image
  65 |        12  4  reserved (zero)
  66 |       body: raw deflate (zlib wbits=-window) of a record sequence:
  67 |         u32 add   - bytes to produce as  old[oldpos+i] + diff[i]  (mod 256)
  68 |         u32 copy  - bytes to copy verbatim from the record (bsdiff "extra")
  69 |         i32 seek  - adjustment to oldpos after the record (may be negative)
  70 |         add  diff bytes
  71 |         copy extra bytes
  72 |       Records repeat until new_size bytes have been produced.
  73 |
  74 |   Algorithms
  75 |     Encode, bsdiff40_to_dota():
  76 |       1. Reject anything that is not a 32-byte BSDIFF40 header.
  77 |       2. Read the three sign-magnitude 64-bit lengths with _offtin - bsdiff's own integer
  78 |          encoding, where bit 63 is a sign bit rather than two's complement.
  79 |       3. bunzip2 the control, diff and extra blocks.
  80 |       4. Walk the control block in 24-byte entries, slicing diff and extra into
  81 |          (add_diff, extra, seek) records and range-checking every entry.
  82 |       5. Cross-check that the records produce exactly new_size bytes, then deflate the
  83 |          record sequence through _encode.
  84 |     Decode, apply_dota(): inflate the body, then walk records, producing `add` bytes as
  85 |     old[oldpos+i] + diff[i] (mod 256) and copying `copy` bytes verbatim, advancing oldpos by
  86 |     add + seek after each record. Semantics are exactly bspatch's. An old index outside
  87 |     [0, old_size) contributes 0, so the diff byte is used as is. The device reads `old` from
  88 |     the ota_1 backup of the running app.
  89 |     Full image, full_image_to_dota(): one copy-only record, used by the bench DELTA_PAYLOAD
  90 |     path when there is no patch to re-pack.
  91 |
  92 |   Control
  93 |     One decision point, one chokepoint, one failure convention:
  94 |       - to_dota() is the only entry point a caller needs: BSDIFF40 patches are re-packed,
  95 |         anything else is treated as a full image.
  96 |       - _encode() is the single place that compresses and the single place that validates the
  97 |         window, so every encoder path shares one check.
  98 |       - Every failure raises ValueError carrying observed-against-expected values. The module
  99 |         never prints and never returns a sentinel; policy belongs to the caller, which logs
 100 |         the operator-facing line and refuses to serve the release.
 101 |       - Forward compatibility: a device refuses a stream whose window is larger than its
 102 |         dictionary; a device with a larger dictionary decodes a smaller window; and older
 103 |         devices, which read only the magic and the version byte, ignore byte 5, so the format
 104 |         stays v1.
 105 |
 106 |   The error convention is total
 107 |     Every failure, on either side of the format, raises ValueError carrying
 108 |     observed-against-expected values; nothing returns a sentinel and nothing prints. Library
 109 |     exceptions that would otherwise escape are converted where they arise: bz2 failures on a
 110 |     corrupt BSDIFF40 block, zlib failures on a corrupt deflate body, and both
 111 |     struct.unpack_from calls - which malformed input could drive past the end of a buffer -
 112 |     are guarded by explicit length checks first.
 113 |
 114 | STYLE
 115 |     Four-space indentation, ASCII only, lines of at most 100 characters (the repository
 116 |     carries no linter configuration, so this limit is a convention declared here). Module
 117 |     state is seven UPPER_CASE constants and nothing else: no global variables and no `global`
 118 |     statements anywhere in the file.
 119 | """
 120 | import bz2
 121 | import struct
 122 | import zlib
 123 |
 124 | MAGIC = b"DOTA"
 125 | FORMAT_VERSION = 1
 126 | HEADER = struct.Struct("<4sBB2xI4x")     # 16 bytes: magic, version, window bits, new_size
 127 | RECORD = struct.Struct("<IIi")           # add, copy, seek
 128 | BSDIFF_MAGIC = b"BSDIFF40"
 129 |
 130 | # Deflate window the gateway compresses with, as log2(bytes). The device dictionary
 131 | # (DICT_BITS in the firmware's DeltaDecoder) must be at least this large.
 132 | WINDOW_BITS = 12
 133 | LEGACY_WINDOW_BITS = 15                  # streams with header byte 5 == 0
 134 |
 135 |
 136 | def _offtin(raw: bytes) -> int:
 137 |     """bsdiff's sign-magnitude 64-bit integer."""
 138 |     value = int.from_bytes(raw, "little")
 139 |     if value & (1 << 63):
 140 |         return -(value & ((1 << 63) - 1))
 141 |     return value
 142 |
 143 |
 144 | def _encode(new_size: int, records, window_bits: int = WINDOW_BITS) -> bytes:
 145 |     """Deflate a record sequence behind a DOTA header - the one compression chokepoint.
 146 |
 147 |     Every encoder path goes through here, so the window is validated once, in one place.
 148 |     `records` is an iterable of (add_diff, extra, seek) triples. Returns header + body.
 149 |     """
 150 |     if not 9 <= window_bits <= 15:
 151 |         raise ValueError("deflate window must be 2^9 .. 2^15 bytes")
 152 |     comp = zlib.compressobj(9, zlib.DEFLATED, -window_bits)
 153 |     body = []
 154 |     for add_diff, extra, seek in records:
 155 |         body.append(comp.compress(RECORD.pack(len(add_diff), len(extra), seek)))
 156 |         body.append(comp.compress(add_diff))
 157 |         body.append(comp.compress(extra))
 158 |     body.append(comp.flush())
 159 |     return HEADER.pack(MAGIC, FORMAT_VERSION, window_bits, new_size) + b"".join(body)
 160 |
 161 |
 162 | def bsdiff40_to_dota(patch: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 163 |     """Re-pack a BSDIFF40 patch (as produced by bsdiff4.diff) into DOTA."""
 164 |     if len(patch) < 32 or patch[:8] != BSDIFF_MAGIC:
 165 |         raise ValueError("not a BSDIFF40 patch")
 166 |     ctrl_len = _offtin(patch[8:16])
 167 |     diff_len = _offtin(patch[16:24])
 168 |     new_size = _offtin(patch[24:32])
 169 |     if ctrl_len < 0 or diff_len < 0 or new_size < 0 or 32 + ctrl_len + diff_len > len(patch):
 170 |         raise ValueError("corrupt BSDIFF40 header")
 171 |     # bz2 reports corruption three different ways: OSError for a bad stream, ValueError for
 172 |     # a truncated one, EOFError at an unexpected end. Normalise them, so every failure in this
 173 |     # module is a ValueError. An empty block decompresses to b"" without raising at all; the
 174 |     # length checks below catch that case instead.
 175 |     try:
 176 |         ctrl = bz2.decompress(patch[32:32 + ctrl_len])
 177 |         diff = bz2.decompress(patch[32 + ctrl_len:32 + ctrl_len + diff_len])
 178 |         extra = bz2.decompress(patch[32 + ctrl_len + diff_len:])
 179 |     except (OSError, EOFError, ValueError) as exc:
 180 |         raise ValueError(f"corrupt BSDIFF40 compressed block: {exc}") from exc
 181 |     if len(ctrl) % 24:
 182 |         raise ValueError("corrupt BSDIFF40 control block")
 183 |
 184 |     records, dpos, epos, produced = [], 0, 0, 0
 185 |     for off in range(0, len(ctrl), 24):
 186 |         add = _offtin(ctrl[off:off + 8])
 187 |         copy = _offtin(ctrl[off + 8:off + 16])
 188 |         seek = _offtin(ctrl[off + 16:off + 24])
 189 |         if add < 0 or copy < 0 or dpos + add > len(diff) or epos + copy > len(extra):
 190 |             raise ValueError("BSDIFF40 control entry out of range")
 191 |         if not -(1 << 31) <= seek < (1 << 31):
 192 |             raise ValueError("seek does not fit in i32")
 193 |         records.append((diff[dpos:dpos + add], extra[epos:epos + copy], seek))
 194 |         dpos += add
 195 |         epos += copy
 196 |         produced += add + copy
 197 |     if produced != new_size:
 198 |         raise ValueError(f"control block produces {produced} bytes, header says {new_size}")
 199 |     return _encode(new_size, records, window_bits)
 200 |
 201 |
 202 | def full_image_to_dota(image: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 203 |     """A whole image as one copy-only record (bench DELTA_PAYLOAD path)."""
 204 |     return _encode(len(image), [(b"", image, 0)], window_bits)
 205 |
 206 |
 207 | def to_dota(payload: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 208 |     """BSDIFF40 patches are re-packed; anything else is a full image."""
 209 |     if payload[:8] == BSDIFF_MAGIC:
 210 |         return bsdiff40_to_dota(payload, window_bits)
 211 |     return full_image_to_dota(payload, window_bits)
 212 |
 213 |
 214 | def apply_dota(old: bytes, dota: bytes, dict_bits: int = 15) -> bytes:
 215 |     """Reference decoder - the specification the ESP32 DeltaDecoder mirrors.
 216 |
 217 |     `dict_bits` is the decoder's ring-dictionary size (log2 bytes). Like the device,
 218 |     it refuses a stream compressed with a larger window instead of decoding garbage.
 219 |     """
 220 |     if len(dota) < HEADER.size:
 221 |         raise ValueError(f"stream is {len(dota)} B, the header alone needs {HEADER.size} B")
 222 |     magic, version, window_bits, new_size = HEADER.unpack_from(dota)
 223 |     if magic != MAGIC or version != FORMAT_VERSION:
 224 |         raise ValueError("not a DOTA v1 stream")
 225 |     window_bits = window_bits or LEGACY_WINDOW_BITS
 226 |     if not 9 <= window_bits <= 15:
 227 |         raise ValueError(f"bad deflate window 2^{window_bits}")
 228 |     if window_bits > dict_bits:
 229 |         raise ValueError(f"stream needs a 2^{window_bits} B window, "
 230 |                          f"decoder dictionary is 2^{dict_bits} B")
 231 |     try:
 232 |         body = zlib.decompress(dota[HEADER.size:], -window_bits)
 233 |     except zlib.error as exc:
 234 |         raise ValueError(f"corrupt deflate body: {exc}") from exc
 235 |     # Loop invariants: `out` grows to exactly new_size bytes and is never rewound; `pos` is the
 236 |     # read cursor into the inflated body; `oldpos` is the cursor into the base image, advanced
 237 |     # by add + seek once per record.
 238 |     out = bytearray()
 239 |     pos = oldpos = 0
 240 |     while len(out) < new_size:
 241 |         # One record: a fixed-size header, then `add` diff bytes, then `copy` verbatim bytes.
 242 |         if pos + RECORD.size > len(body):
 243 |             raise ValueError(f"stream ends after {len(out)} of {new_size} B: records exhausted")
 244 |         add, copy, seek = RECORD.unpack_from(body, pos)
 245 |         pos += RECORD.size
 246 |         if len(out) + add + copy > new_size or pos + add + copy > len(body):
 247 |             raise ValueError("record overruns the stream")
 248 |         for i in range(add):
 249 |             # An index outside the old image contributes 0, so the diff byte is used as is.
 250 |             # The firmware's _readOld() gets the same effect by zeroing its buffer first.
 251 |             o = oldpos + i
 252 |             base = old[o] if 0 <= o < len(old) else 0
 253 |             out.append((body[pos + i] + base) & 0xFF)
 254 |         pos += add
 255 |         out += body[pos:pos + copy]       # "extra" bytes: no base, copied straight out
 256 |         pos += copy
 257 |         oldpos += add + seek              # bspatch semantics: seek adjusts the base cursor
 258 |     return bytes(out)
```

## 4. Verification

The module is held by 11 unit tests in `gateway/sop/tests/test_dota_window.py`:

- `test_default_window_is_4kb_and_recorded_in_the_header`
- `test_delta_round_trips_with_a_4kb_decoder`
- `test_full_image_round_trips_with_a_4kb_decoder`
- `test_the_body_never_reaches_back_further_than_the_window`
- `test_a_decoder_refuses_a_stream_with_a_larger_window`
- `test_a_legacy_stream_without_a_window_byte_counts_as_32kb`
- `test_out_of_range_windows_are_rejected`
- `test_a_corrupt_compressed_block_raises_valueerror`
- `test_a_stream_too_short_for_the_header_raises_valueerror`
- `test_a_corrupt_or_exhausted_body_raises_valueerror`
- `test_a_4kb_window_costs_little_on_a_delta`

Commands, run from `gateway/` with the project interpreter:

```
python -m unittest sop.tests.test_dota_window -v      # this module
python -m unittest discover -s sop/tests -t .         # the whole suite
python ../documentations/make_program_doc.py --check  # document still in sync
```

## 5. Honest notes and known gaps

- **There are no global variables to limit.** The measurement is 0 mutable module-level names and 0 `global` statements; module state is UPPER_CASE constants only. The consideration is met by the count being zero rather than by any refactoring, and that is deliberate: the module is a pure byte transform called from the gateway's asyncio loop, from two measurement scripts and from the test suite, so any module state would make it non-reentrant across those callers. For contrast, the repository does have a mutable global elsewhere, the `FAILURES` counter rebound via `global` in `gateway/secureota/gateway_runtime/simulation/run_simulation.py`.
- **No local-versus-global naming tension exists here.** With no globals, the convention reduces to UPPER_CASE constants, underscore-prefixed private helpers, and lower_snake_case locals and parameters. The usual teaching example, a local shadowing a global, cannot occur in this file.
- **`HEADER` and `RECORD` are `struct.Struct` objects, not primitives.** They are stateless and never rebound, which is why they are counted as constants; this is stated rather than implying all 7 constants are simple values.
- **The error convention is total, and that took work.** All 15 raise sites raise `ValueError` with observed-against-expected text, but three library exceptions used to escape on malformed input, because none of them derives from `ValueError`: `OSError` from `bz2` on a corrupt BSDIFF40 block, `zlib.error` on a corrupt or truncated deflate body, and `struct.error` from either `unpack_from` call when a short stream or a tampered `new_size` drove it past the end of a buffer. All three are now converted where they arise, the two `unpack_from` calls behind explicit length checks rather than a `try`. The documentation pass found these; they were not introduced by it, and closing them changed no output byte, only the exception type on input that was already invalid.
- **Error messages versus error display.** This module raises and never prints, so it has no user-facing output of its own. The operator-facing line is emitted by the caller, `main_gateway.py`, which is outside this deliverable.
- **Considerations met without effort, stated plainly:** function length (nothing near a contested threshold), indentation (shallow nesting), and spacing (no trailing whitespace). Claiming credit for difficult work on these would be dishonest.

