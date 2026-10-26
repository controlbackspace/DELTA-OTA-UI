# Program Documentation: DOTA delta-stream codec

COMP 022 - Software Engineering 2 - Program Documentation Template

> **Generated file - do not edit by hand.** Every field below is extracted from the
> header comment block of the source file, and every number is measured from it, so
> this document cannot drift from the code.
>
> - Source: `gateway/secureota/gateway_runtime/delta_stream.py` (256 lines: header comment block on lines 1-117, code on 118-256)
> - SHA-256: `c64d832a08fa6643f5db30d28529952a5e84807afc578fc6e1b6e1ebc44f9843`
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
| 7 | Line length | longest 96 chars (line 241), 0 lines over 100 | 100-character limit declared in the header block's STYLE note |
| 8 | Spacing | 0 trailing-whitespace lines in the file, 17 blank lines in the code region | two blank lines between top-level definitions, per PEP 8 |
| 9 | Function length | 6 functions: shortest 3, median 16, longest 45 lines | no function needed splitting |
| 10 | Error messages | 15 messages, each naming observed against expected | the module raises; the operator-facing wording belongs to the caller |

### 2.1 Functions

| Function | Visibility | Lines | Span | Max depth | Docstring | Raises |
|---|---|---|---|---|---|---|
| `_offtin` | private | 6 | 134-139 | 1 | yes | 0 |
| `_encode` | private | 16 | 142-157 | 1 | yes | 1 |
| `bsdiff40_to_dota` | public | 38 | 160-197 | 2 | yes | 7 |
| `full_image_to_dota` | public | 3 | 200-202 | 0 | yes | 0 |
| `to_dota` | public | 5 | 205-209 | 1 | yes | 0 |
| `apply_dota` | public | 45 | 212-256 | 2 | yes | 7 |

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
| 149 | `ValueError('deflate window must be 2^9 .. 2^15 bytes')` |
| 163 | `ValueError('not a BSDIFF40 patch')` |
| 168 | `ValueError('corrupt BSDIFF40 header')` |
| 178 | `ValueError(f'corrupt BSDIFF40 compressed block: {exc}')` |
| 180 | `ValueError('corrupt BSDIFF40 control block')` |
| 188 | `ValueError('BSDIFF40 control entry out of range')` |
| 190 | `ValueError('seek does not fit in i32')` |
| 196 | `ValueError(f'control block produces {produced} bytes, header says {new_size}')` |
| 219 | `ValueError(f'stream is {len(dota)} B, the header alone needs {HEADER.size} B')` |
| 222 | `ValueError('not a DOTA v1 stream')` |
| 225 | `ValueError(f'bad deflate window 2^{window_bits}')` |
| 227 | `ValueError(f'stream needs a 2^{window_bits} B window, decoder dictionary is 2^{dict_bits} B')` |
| 232 | `ValueError(f'corrupt deflate body: {exc}')` |
| 241 | `ValueError(f'stream ends after {len(out)} of {new_size} B: records exhausted')` |
| 245 | `ValueError('record overruns the stream')` |

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
  54 |   The idea in plain terms
  55 |     A firmware update normally ships a whole new program. This module ships only what
  56 |     changed between the old version and the new one, packaged so that a small device can
  57 |     unpack it unaided. On the v1.0 to v1.1 pair the device receives about 23 KB instead of
  58 |     the whole 282 KB image.
  59 |
  60 |   Data structures
  61 |     A DOTA stream is a 16-byte header followed by a compressed list of instructions for
  62 |     turning the old image into the new one.
  63 |
  64 |       header, 16 bytes, not compressed:
  65 |         0  4  magic b"DOTA", marks the format
  66 |         4  1  format version (1)
  67 |         5  1  memory the decoder needs, as log2 bytes (12 = 4 KB; 0 = an older 32 KB stream)
  68 |         6  2  reserved (zero)
  69 |         8  4  new_size: exact length of the finished image
  70 |        12  4  reserved (zero)
  71 |       body, deflate-compressed, one instruction at a time:
  72 |         add   how many bytes to build from the old image plus a correction
  73 |         copy  how many bytes to take straight from the stream
  74 |         seek  how far to move the reading position in the old image afterwards
  75 |       followed by those add and copy bytes themselves. Instructions repeat until new_size
  76 |       bytes exist.
  77 |
  78 |     HEADER and RECORD are struct.Struct constants that declare this layout once, so the
  79 |     encoder and the decoder cannot disagree about it.
  80 |
  81 |   Algorithms
  82 |     Encoding, bsdiff40_to_dota(), re-packages the patch the release builder produced. That
  83 |     patch is compressed with bzip2, which needs megabytes of memory to unpack - more than
  84 |     the ESP32 has - so the instructions are read out and re-compressed with deflate, which
  85 |     the chip unpacks in a 4 KB buffer. The instructions themselves are unchanged; only the
  86 |     wrapping is.
  87 |
  88 |     Decoding, apply_dota(), rebuilds the image. For each instruction: build `add` bytes
  89 |     from the old image plus its corrections, copy `copy` bytes straight from the stream,
  90 |     then move the old-image position by add + seek. Reading past the end of the old image
  91 |     gives zero. This function is the written specification of the decoder; the ESP32
  92 |     firmware performs the same steps in C++, reading the old image from its ota_1 backup.
  93 |
  94 |     full_image_to_dota() wraps a whole image as a single copy instruction, for bench runs
  95 |     where there is no patch to re-package.
  96 |
  97 |   Control
  98 |     - to_dota() is the only entry point a caller needs: a patch is re-packaged, anything
  99 |       else is treated as a whole image.
 100 |     - _encode() is the only place that compresses, so the memory limit is checked once on
 101 |       behalf of every path.
 102 |     - Every failure raises ValueError stating what was expected and what arrived. The
 103 |       module never prints and never returns an error code; the caller decides what to do,
 104 |       and the gateway's decision is to refuse to serve the release.
 105 |     - No foreign exception escapes: bz2 and zlib failures are converted where they arise,
 106 |       and both struct.unpack_from calls are guarded by length checks first, so ValueError
 107 |       is the only failure a caller has to handle.
 108 |     - Old and new devices interoperate: a device refuses a stream that needs more memory
 109 |       than it has, accepts one that needs less, and devices built before byte 5 existed
 110 |       ignore it.
 111 |
 112 | STYLE
 113 |     Four-space indentation, ASCII only, lines of at most 100 characters (the repository
 114 |     carries no linter configuration, so this limit is a convention declared here). Module
 115 |     state is seven UPPER_CASE constants and nothing else: no global variables and no `global`
 116 |     statements anywhere in the file.
 117 | """
 118 | import bz2
 119 | import struct
 120 | import zlib
 121 |
 122 | MAGIC = b"DOTA"
 123 | FORMAT_VERSION = 1
 124 | HEADER = struct.Struct("<4sBB2xI4x")     # 16 bytes: magic, version, window bits, new_size
 125 | RECORD = struct.Struct("<IIi")           # add, copy, seek
 126 | BSDIFF_MAGIC = b"BSDIFF40"
 127 |
 128 | # Deflate window the gateway compresses with, as log2(bytes). The device dictionary
 129 | # (DICT_BITS in the firmware's DeltaDecoder) must be at least this large.
 130 | WINDOW_BITS = 12
 131 | LEGACY_WINDOW_BITS = 15                  # streams with header byte 5 == 0
 132 |
 133 |
 134 | def _offtin(raw: bytes) -> int:
 135 |     """bsdiff's sign-magnitude 64-bit integer."""
 136 |     value = int.from_bytes(raw, "little")
 137 |     if value & (1 << 63):
 138 |         return -(value & ((1 << 63) - 1))
 139 |     return value
 140 |
 141 |
 142 | def _encode(new_size: int, records, window_bits: int = WINDOW_BITS) -> bytes:
 143 |     """Deflate a record sequence behind a DOTA header - the one compression chokepoint.
 144 |
 145 |     Every encoder path goes through here, so the window is validated once, in one place.
 146 |     `records` is an iterable of (add_diff, extra, seek) triples. Returns header + body.
 147 |     """
 148 |     if not 9 <= window_bits <= 15:
 149 |         raise ValueError("deflate window must be 2^9 .. 2^15 bytes")
 150 |     comp = zlib.compressobj(9, zlib.DEFLATED, -window_bits)
 151 |     body = []
 152 |     for add_diff, extra, seek in records:
 153 |         body.append(comp.compress(RECORD.pack(len(add_diff), len(extra), seek)))
 154 |         body.append(comp.compress(add_diff))
 155 |         body.append(comp.compress(extra))
 156 |     body.append(comp.flush())
 157 |     return HEADER.pack(MAGIC, FORMAT_VERSION, window_bits, new_size) + b"".join(body)
 158 |
 159 |
 160 | def bsdiff40_to_dota(patch: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 161 |     """Re-pack a BSDIFF40 patch (as produced by bsdiff4.diff) into DOTA."""
 162 |     if len(patch) < 32 or patch[:8] != BSDIFF_MAGIC:
 163 |         raise ValueError("not a BSDIFF40 patch")
 164 |     ctrl_len = _offtin(patch[8:16])
 165 |     diff_len = _offtin(patch[16:24])
 166 |     new_size = _offtin(patch[24:32])
 167 |     if ctrl_len < 0 or diff_len < 0 or new_size < 0 or 32 + ctrl_len + diff_len > len(patch):
 168 |         raise ValueError("corrupt BSDIFF40 header")
 169 |     # bz2 reports corruption three different ways: OSError for a bad stream, ValueError for
 170 |     # a truncated one, EOFError at an unexpected end. Normalise them, so every failure in this
 171 |     # module is a ValueError. An empty block decompresses to b"" without raising at all; the
 172 |     # length checks below catch that case instead.
 173 |     try:
 174 |         ctrl = bz2.decompress(patch[32:32 + ctrl_len])
 175 |         diff = bz2.decompress(patch[32 + ctrl_len:32 + ctrl_len + diff_len])
 176 |         extra = bz2.decompress(patch[32 + ctrl_len + diff_len:])
 177 |     except (OSError, EOFError, ValueError) as exc:
 178 |         raise ValueError(f"corrupt BSDIFF40 compressed block: {exc}") from exc
 179 |     if len(ctrl) % 24:
 180 |         raise ValueError("corrupt BSDIFF40 control block")
 181 |
 182 |     records, dpos, epos, produced = [], 0, 0, 0
 183 |     for off in range(0, len(ctrl), 24):
 184 |         add = _offtin(ctrl[off:off + 8])
 185 |         copy = _offtin(ctrl[off + 8:off + 16])
 186 |         seek = _offtin(ctrl[off + 16:off + 24])
 187 |         if add < 0 or copy < 0 or dpos + add > len(diff) or epos + copy > len(extra):
 188 |             raise ValueError("BSDIFF40 control entry out of range")
 189 |         if not -(1 << 31) <= seek < (1 << 31):
 190 |             raise ValueError("seek does not fit in i32")
 191 |         records.append((diff[dpos:dpos + add], extra[epos:epos + copy], seek))
 192 |         dpos += add
 193 |         epos += copy
 194 |         produced += add + copy
 195 |     if produced != new_size:
 196 |         raise ValueError(f"control block produces {produced} bytes, header says {new_size}")
 197 |     return _encode(new_size, records, window_bits)
 198 |
 199 |
 200 | def full_image_to_dota(image: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 201 |     """A whole image as one copy-only record (bench DELTA_PAYLOAD path)."""
 202 |     return _encode(len(image), [(b"", image, 0)], window_bits)
 203 |
 204 |
 205 | def to_dota(payload: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 206 |     """BSDIFF40 patches are re-packed; anything else is a full image."""
 207 |     if payload[:8] == BSDIFF_MAGIC:
 208 |         return bsdiff40_to_dota(payload, window_bits)
 209 |     return full_image_to_dota(payload, window_bits)
 210 |
 211 |
 212 | def apply_dota(old: bytes, dota: bytes, dict_bits: int = 15) -> bytes:
 213 |     """Reference decoder - the specification the ESP32 DeltaDecoder mirrors.
 214 |
 215 |     `dict_bits` is the decoder's ring-dictionary size (log2 bytes). Like the device,
 216 |     it refuses a stream compressed with a larger window instead of decoding garbage.
 217 |     """
 218 |     if len(dota) < HEADER.size:
 219 |         raise ValueError(f"stream is {len(dota)} B, the header alone needs {HEADER.size} B")
 220 |     magic, version, window_bits, new_size = HEADER.unpack_from(dota)
 221 |     if magic != MAGIC or version != FORMAT_VERSION:
 222 |         raise ValueError("not a DOTA v1 stream")
 223 |     window_bits = window_bits or LEGACY_WINDOW_BITS
 224 |     if not 9 <= window_bits <= 15:
 225 |         raise ValueError(f"bad deflate window 2^{window_bits}")
 226 |     if window_bits > dict_bits:
 227 |         raise ValueError(f"stream needs a 2^{window_bits} B window, "
 228 |                          f"decoder dictionary is 2^{dict_bits} B")
 229 |     try:
 230 |         body = zlib.decompress(dota[HEADER.size:], -window_bits)
 231 |     except zlib.error as exc:
 232 |         raise ValueError(f"corrupt deflate body: {exc}") from exc
 233 |     # Loop invariants: `out` grows to exactly new_size bytes and is never rewound; `pos` is the
 234 |     # read cursor into the inflated body; `oldpos` is the cursor into the base image, advanced
 235 |     # by add + seek once per record.
 236 |     out = bytearray()
 237 |     pos = oldpos = 0
 238 |     while len(out) < new_size:
 239 |         # One record: a fixed-size header, then `add` diff bytes, then `copy` verbatim bytes.
 240 |         if pos + RECORD.size > len(body):
 241 |             raise ValueError(f"stream ends after {len(out)} of {new_size} B: records exhausted")
 242 |         add, copy, seek = RECORD.unpack_from(body, pos)
 243 |         pos += RECORD.size
 244 |         if len(out) + add + copy > new_size or pos + add + copy > len(body):
 245 |             raise ValueError("record overruns the stream")
 246 |         for i in range(add):
 247 |             # An index outside the old image contributes 0, so the diff byte is used as is.
 248 |             # The firmware's _readOld() gets the same effect by zeroing its buffer first.
 249 |             o = oldpos + i
 250 |             base = old[o] if 0 <= o < len(old) else 0
 251 |             out.append((body[pos + i] + base) & 0xFF)
 252 |         pos += add
 253 |         out += body[pos:pos + copy]       # "extra" bytes: no base, copied straight out
 254 |         pos += copy
 255 |         oldpos += add + seek              # bspatch semantics: seek adjusts the base cursor
 256 |     return bytes(out)
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

