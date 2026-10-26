# Program Documentation: DOTA delta-stream codec

COMP 022 - Software Engineering 2 - Program Documentation Template

> **Generated file - do not edit by hand.** Every field below is extracted from the
> header comment block of the source file, and every number is measured from it, so
> this document cannot drift from the code.
>
> - Source: `gateway/secureota/gateway_runtime/delta_stream.py` (238 lines: header comment block on lines 1-99, code on 100-238)
> - SHA-256: `29aa2199a5239816012be73b41ed69d46574ca0ceb436569d1ebb1454de0ace0`
> - Regenerate: `python documentations/make_program_doc.py`
> - Verify in sync: `python documentations/make_program_doc.py --check`

*DOTA delta-stream codec - turns a firmware patch into a stream a small device can decode.*

## 1. Header comment block

The six fields the template requires, as they appear in the source file.

| Field | Value |
|---|---|
| Program Title | DOTA delta-stream codec (delta_stream.py) |
| Programmers | *(left blank for the group to fill in)* |
| Where the program fits in the general system designs | *expanded in the section below* |
| Date written and revised | Written 2026-10-01; revised 2026-10-07, when the compression window was reduced to 4 KB; 2026-10-26, a documentation pass that left the format unchanged |
| Purpose | *expanded in the section below* |
| Data structures, algorithms, and control | *expanded in the section below* |

### 1.1 Purpose

```
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
```

### 1.2 Where the program fits in the general system designs

```
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
```

### 1.3 Data structures, algorithms, and control

```
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
| 7 | Line length | longest 96 chars (line 223), 0 lines over 100 | 100-character limit declared in the header block's STYLE note |
| 8 | Spacing | 0 trailing-whitespace lines in the file, 17 blank lines in the code region | two blank lines between top-level definitions, per PEP 8 |
| 9 | Function length | 6 functions: shortest 3, median 16, longest 45 lines | no function needed splitting |
| 10 | Error messages | 15 messages, each naming observed against expected | the module raises; the operator-facing wording belongs to the caller |

### 2.1 Functions

| Function | Visibility | Lines | Span | Max depth | Docstring | Raises |
|---|---|---|---|---|---|---|
| `_offtin` | private | 6 | 116-121 | 1 | yes | 0 |
| `_encode` | private | 16 | 124-139 | 1 | yes | 1 |
| `bsdiff40_to_dota` | public | 38 | 142-179 | 2 | yes | 7 |
| `full_image_to_dota` | public | 3 | 182-184 | 0 | yes | 0 |
| `to_dota` | public | 5 | 187-191 | 1 | yes | 0 |
| `apply_dota` | public | 45 | 194-238 | 2 | yes | 7 |

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
| 131 | `ValueError('deflate window must be 2^9 .. 2^15 bytes')` |
| 145 | `ValueError('not a BSDIFF40 patch')` |
| 150 | `ValueError('corrupt BSDIFF40 header')` |
| 160 | `ValueError(f'corrupt BSDIFF40 compressed block: {exc}')` |
| 162 | `ValueError('corrupt BSDIFF40 control block')` |
| 170 | `ValueError('BSDIFF40 control entry out of range')` |
| 172 | `ValueError('seek does not fit in i32')` |
| 178 | `ValueError(f'control block produces {produced} bytes, header says {new_size}')` |
| 201 | `ValueError(f'stream is {len(dota)} B, the header alone needs {HEADER.size} B')` |
| 204 | `ValueError('not a DOTA v1 stream')` |
| 207 | `ValueError(f'bad deflate window 2^{window_bits}')` |
| 209 | `ValueError(f'stream needs a 2^{window_bits} B window, decoder dictionary is 2^{dict_bits} B')` |
| 214 | `ValueError(f'corrupt deflate body: {exc}')` |
| 223 | `ValueError(f'stream ends after {len(out)} of {new_size} B: records exhausted')` |
| 227 | `ValueError('record overruns the stream')` |

## 3. Source code

```text
   1 | """DOTA delta-stream codec - turns a firmware patch into a stream a small device can decode.
   2 |
   3 | =============================================================================================
   4 | COMP 022 Software Engineering 2 - Program Documentation
   5 | ---------------------------------------------------------------------------------------------
   6 | Program Title : DOTA delta-stream codec (delta_stream.py)
   7 | Programmers   :
   8 | System Design : The payload format of the edge gateway, the machine that sits between the
   9 |                 release ledger and the fleet of devices. Answered in full below.
  10 | Date Written  : 2026-10-01
  11 | Date Revised  : 2026-10-07, when the compression window was reduced to 4 KB;
  12 |                 2026-10-26, a documentation pass that left the format unchanged
  13 | Purpose       : Re-package a verified firmware patch into a stream that a decoder with
  14 |                 4 KB of working memory can rebuild in one pass. Answered in full below.
  15 | Structures    : A sixteen-byte header followed by a compressed list of instructions.
  16 |                 Answered in full below.
  17 | =============================================================================================
  18 |
  19 | PURPOSE
  20 |     A firmware update normally ships an entire new program to the device. This module ships
  21 |     only what changed between the old version and the new one, packaged so that a small
  22 |     device can unpack it unaided. On the v1.0 to v1.1 pair used throughout the study, the
  23 |     device receives about 23 KB instead of the whole 282 KB image.
  24 |
  25 |     A second format is needed because of memory. Patches are published in the standard
  26 |     bsdiff format, which compresses its contents with bzip2, and a bzip2 decompressor needs
  27 |     megabytes of working memory - far more than the 320 KB the target microcontroller has.
  28 |     This module keeps the patch instructions exactly as they are and re-compresses them with
  29 |     deflate instead, inside a window small enough that the decoder's dictionary, the largest
  30 |     single object it holds in memory, fits the project's constrained-device budget. On the
  31 |     real image pair that smaller window costs nothing in stream size.
  32 |
  33 | WHERE THE PROGRAM FITS IN THE GENERAL SYSTEM DESIGNS
  34 |     This module is the payload format of the edge gateway, the machine that sits between the
  35 |     release ledger and the fleet of devices. It owns the format and nothing else: it opens no
  36 |     network connection, reads no configuration and writes no files, which is what makes it
  37 |     testable on a workstation with no hardware present.
  38 |
  39 |     The gateway's release loop reaches this module once a release has been approved on the
  40 |     ledger and the downloaded bytes have been checked against the hash recorded there. The
  41 |     verified bytes are re-packaged here, and the block-encryption step that follows slices
  42 |     the result into independently encrypted frames, which a device then requests one at a
  43 |     time over its constrained-network protocol. If this module rejects a payload, the gateway
  44 |     refuses to serve that release at all.
  45 |
  46 |     The decoder in this module is also the written specification of the decoder on the
  47 |     device: the updater resident in the device's factory partition performs the same steps in
  48 |     C++, and the window this module compresses with must never exceed the dictionary size
  49 |     that updater reserves. The project's measurement harness calls this module directly as
  50 |     well, to time and size the conversion with no device attached.
  51 |
  52 | DATA STRUCTURES, ALGORITHMS, AND CONTROL
  53 |     The data structure this module produces is called a DOTA stream, and it consists of a
  54 |     sixteen-byte header followed by a compressed list of instructions for turning the old
  55 |     image into the new one. The header is never compressed, so a device can read it before
  56 |     committing any memory. Bytes 0 to 3 hold the characters DOTA, which mark the format; byte
  57 |     4 holds the format version, currently 1; byte 5 records how much memory the decoder will
  58 |     need, written as a power of two, so that a value of 12 means 4 KB while a value of 0
  59 |     identifies an older stream that assumed 32 KB; bytes 6 and 7 are reserved and set to
  60 |     zero; bytes 8 to 11 hold new_size, the exact length of the finished image; and bytes 12
  61 |     to 15 are reserved and also zero.
  62 |
  63 |     The body that follows is deflate-compressed and holds one instruction after another until
  64 |     new_size bytes of output exist. Each instruction begins with three numbers: add, the
  65 |     number of bytes to build from the old image plus a correction; copy, the number of bytes
  66 |     to take straight from the stream; and seek, how far to move the reading position in the
  67 |     old image once the instruction is finished. The add and copy bytes themselves follow those
  68 |     three numbers. Two constants, HEADER and RECORD, declare this layout once as struct.Struct
  69 |     specifications, so the encoder and the decoder cannot disagree about it.
  70 |
  71 |     Two algorithms work on that structure. Encoding, in bsdiff40_to_dota, re-packages a
  72 |     published patch: the instructions are read out of the bzip2 container they arrive in and
  73 |     re-compressed with deflate, which the device can unpack inside a 4 KB buffer. The
  74 |     instructions themselves are never altered, only their wrapping. Decoding, in apply_dota,
  75 |     rebuilds the image by working through the instructions in order: it builds add bytes from
  76 |     the old image plus their corrections, copies copy bytes straight from the stream, and then
  77 |     moves the old-image position forward by add plus seek. Reading past the end of the old
  78 |     image simply yields zero. The device does the same, reading the old image from its backup
  79 |     copy of the running application. A third function, full_image_to_dota, wraps a whole image
  80 |     as a single copy instruction, for bench runs where there is no patch to re-package.
  81 |
  82 |     Control through the module is deliberately narrow. to_dota is the only entry point a
  83 |     caller needs: a patch is re-packaged, and anything else is treated as a whole image.
  84 |     _encode is the only place that compresses, so the memory limit is checked once on behalf
  85 |     of every path that reaches it. Every failure raises a ValueError stating what was expected
  86 |     and what actually arrived; the module never prints and never returns an error code,
  87 |     because policy belongs to the caller, and the gateway's policy is to refuse to serve the
  88 |     release. No foreign exception escapes either: bz2 and zlib failures are converted where
  89 |     they arise, and both struct.unpack_from calls are guarded by length checks first, so
  90 |     ValueError is the only failure a caller has to handle. Finally, old and new devices
  91 |     interoperate: a device refuses a stream that needs more memory than it has, accepts one
  92 |     that needs less, and devices built before byte 5 existed ignore it.
  93 |
  94 | STYLE
  95 |     Four-space indentation, ASCII only, lines of at most 100 characters; the repository
  96 |     carries no linter configuration, so this limit is a convention declared here. Module
  97 |     state is seven named constants and nothing else: no global variables, no global
  98 |     statements.
  99 | """
 100 | import bz2
 101 | import struct
 102 | import zlib
 103 |
 104 | MAGIC = b"DOTA"
 105 | FORMAT_VERSION = 1
 106 | HEADER = struct.Struct("<4sBB2xI4x")     # 16 bytes: magic, version, window bits, new_size
 107 | RECORD = struct.Struct("<IIi")           # add, copy, seek
 108 | BSDIFF_MAGIC = b"BSDIFF40"
 109 |
 110 | # Deflate window the gateway compresses with, as log2(bytes). The device dictionary
 111 | # (DICT_BITS in the firmware's DeltaDecoder) must be at least this large.
 112 | WINDOW_BITS = 12
 113 | LEGACY_WINDOW_BITS = 15                  # streams with header byte 5 == 0
 114 |
 115 |
 116 | def _offtin(raw: bytes) -> int:
 117 |     """bsdiff's sign-magnitude 64-bit integer."""
 118 |     value = int.from_bytes(raw, "little")
 119 |     if value & (1 << 63):
 120 |         return -(value & ((1 << 63) - 1))
 121 |     return value
 122 |
 123 |
 124 | def _encode(new_size: int, records, window_bits: int = WINDOW_BITS) -> bytes:
 125 |     """Deflate a record sequence behind a DOTA header - the one compression chokepoint.
 126 |
 127 |     Every encoder path goes through here, so the window is validated once, in one place.
 128 |     `records` is an iterable of (add_diff, extra, seek) triples. Returns header + body.
 129 |     """
 130 |     if not 9 <= window_bits <= 15:
 131 |         raise ValueError("deflate window must be 2^9 .. 2^15 bytes")
 132 |     comp = zlib.compressobj(9, zlib.DEFLATED, -window_bits)
 133 |     body = []
 134 |     for add_diff, extra, seek in records:
 135 |         body.append(comp.compress(RECORD.pack(len(add_diff), len(extra), seek)))
 136 |         body.append(comp.compress(add_diff))
 137 |         body.append(comp.compress(extra))
 138 |     body.append(comp.flush())
 139 |     return HEADER.pack(MAGIC, FORMAT_VERSION, window_bits, new_size) + b"".join(body)
 140 |
 141 |
 142 | def bsdiff40_to_dota(patch: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 143 |     """Re-pack a BSDIFF40 patch (as produced by bsdiff4.diff) into DOTA."""
 144 |     if len(patch) < 32 or patch[:8] != BSDIFF_MAGIC:
 145 |         raise ValueError("not a BSDIFF40 patch")
 146 |     ctrl_len = _offtin(patch[8:16])
 147 |     diff_len = _offtin(patch[16:24])
 148 |     new_size = _offtin(patch[24:32])
 149 |     if ctrl_len < 0 or diff_len < 0 or new_size < 0 or 32 + ctrl_len + diff_len > len(patch):
 150 |         raise ValueError("corrupt BSDIFF40 header")
 151 |     # bz2 reports corruption three different ways: OSError for a bad stream, ValueError for
 152 |     # a truncated one, EOFError at an unexpected end. Normalise them, so every failure in this
 153 |     # module is a ValueError. An empty block decompresses to b"" without raising at all; the
 154 |     # length checks below catch that case instead.
 155 |     try:
 156 |         ctrl = bz2.decompress(patch[32:32 + ctrl_len])
 157 |         diff = bz2.decompress(patch[32 + ctrl_len:32 + ctrl_len + diff_len])
 158 |         extra = bz2.decompress(patch[32 + ctrl_len + diff_len:])
 159 |     except (OSError, EOFError, ValueError) as exc:
 160 |         raise ValueError(f"corrupt BSDIFF40 compressed block: {exc}") from exc
 161 |     if len(ctrl) % 24:
 162 |         raise ValueError("corrupt BSDIFF40 control block")
 163 |
 164 |     records, dpos, epos, produced = [], 0, 0, 0
 165 |     for off in range(0, len(ctrl), 24):
 166 |         add = _offtin(ctrl[off:off + 8])
 167 |         copy = _offtin(ctrl[off + 8:off + 16])
 168 |         seek = _offtin(ctrl[off + 16:off + 24])
 169 |         if add < 0 or copy < 0 or dpos + add > len(diff) or epos + copy > len(extra):
 170 |             raise ValueError("BSDIFF40 control entry out of range")
 171 |         if not -(1 << 31) <= seek < (1 << 31):
 172 |             raise ValueError("seek does not fit in i32")
 173 |         records.append((diff[dpos:dpos + add], extra[epos:epos + copy], seek))
 174 |         dpos += add
 175 |         epos += copy
 176 |         produced += add + copy
 177 |     if produced != new_size:
 178 |         raise ValueError(f"control block produces {produced} bytes, header says {new_size}")
 179 |     return _encode(new_size, records, window_bits)
 180 |
 181 |
 182 | def full_image_to_dota(image: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 183 |     """A whole image as one copy-only record (bench DELTA_PAYLOAD path)."""
 184 |     return _encode(len(image), [(b"", image, 0)], window_bits)
 185 |
 186 |
 187 | def to_dota(payload: bytes, window_bits: int = WINDOW_BITS) -> bytes:
 188 |     """BSDIFF40 patches are re-packed; anything else is a full image."""
 189 |     if payload[:8] == BSDIFF_MAGIC:
 190 |         return bsdiff40_to_dota(payload, window_bits)
 191 |     return full_image_to_dota(payload, window_bits)
 192 |
 193 |
 194 | def apply_dota(old: bytes, dota: bytes, dict_bits: int = 15) -> bytes:
 195 |     """Reference decoder - the specification the ESP32 DeltaDecoder mirrors.
 196 |
 197 |     `dict_bits` is the decoder's ring-dictionary size (log2 bytes). Like the device,
 198 |     it refuses a stream compressed with a larger window instead of decoding garbage.
 199 |     """
 200 |     if len(dota) < HEADER.size:
 201 |         raise ValueError(f"stream is {len(dota)} B, the header alone needs {HEADER.size} B")
 202 |     magic, version, window_bits, new_size = HEADER.unpack_from(dota)
 203 |     if magic != MAGIC or version != FORMAT_VERSION:
 204 |         raise ValueError("not a DOTA v1 stream")
 205 |     window_bits = window_bits or LEGACY_WINDOW_BITS
 206 |     if not 9 <= window_bits <= 15:
 207 |         raise ValueError(f"bad deflate window 2^{window_bits}")
 208 |     if window_bits > dict_bits:
 209 |         raise ValueError(f"stream needs a 2^{window_bits} B window, "
 210 |                          f"decoder dictionary is 2^{dict_bits} B")
 211 |     try:
 212 |         body = zlib.decompress(dota[HEADER.size:], -window_bits)
 213 |     except zlib.error as exc:
 214 |         raise ValueError(f"corrupt deflate body: {exc}") from exc
 215 |     # Loop invariants: `out` grows to exactly new_size bytes and is never rewound; `pos` is the
 216 |     # read cursor into the inflated body; `oldpos` is the cursor into the base image, advanced
 217 |     # by add + seek once per record.
 218 |     out = bytearray()
 219 |     pos = oldpos = 0
 220 |     while len(out) < new_size:
 221 |         # One record: a fixed-size header, then `add` diff bytes, then `copy` verbatim bytes.
 222 |         if pos + RECORD.size > len(body):
 223 |             raise ValueError(f"stream ends after {len(out)} of {new_size} B: records exhausted")
 224 |         add, copy, seek = RECORD.unpack_from(body, pos)
 225 |         pos += RECORD.size
 226 |         if len(out) + add + copy > new_size or pos + add + copy > len(body):
 227 |             raise ValueError("record overruns the stream")
 228 |         for i in range(add):
 229 |             # An index outside the old image contributes 0, so the diff byte is used as is.
 230 |             # The firmware's _readOld() gets the same effect by zeroing its buffer first.
 231 |             o = oldpos + i
 232 |             base = old[o] if 0 <= o < len(old) else 0
 233 |             out.append((body[pos + i] + base) & 0xFF)
 234 |         pos += add
 235 |         out += body[pos:pos + copy]       # "extra" bytes: no base, copied straight out
 236 |         pos += copy
 237 |         oldpos += add + seek              # bspatch semantics: seek adjusts the base cursor
 238 |     return bytes(out)
```

## 4. Verification

The module is held by 11 unit tests in the project's automated test suite:

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

- **There are no global variables to limit.** The measurement is 0 mutable module-level names and 0 `global` statements; module state is UPPER_CASE constants only. The consideration is met by the count being zero rather than by any refactoring, and that is deliberate: the module is a pure byte transform called from the gateway's asyncio loop, from two measurement scripts and from the test suite, so any module state would make it non-reentrant across those callers. For contrast, the repository does have a mutable global elsewhere, a failure counter rebound via `global` in the simulation driver used for bench runs without hardware.
- **No local-versus-global naming tension exists here.** With no globals, the convention reduces to UPPER_CASE constants, underscore-prefixed private helpers, and lower_snake_case locals and parameters. The usual teaching example, a local shadowing a global, cannot occur in this file.
- **`HEADER` and `RECORD` are `struct.Struct` objects, not primitives.** They are stateless and never rebound, which is why they are counted as constants; this is stated rather than implying all 7 constants are simple values.
- **The error convention is total, and that took work.** All 15 raise sites raise `ValueError` with observed-against-expected text, but three library exceptions used to escape on malformed input, because none of them derives from `ValueError`: `OSError` from `bz2` on a corrupt BSDIFF40 block, `zlib.error` on a corrupt or truncated deflate body, and `struct.error` from either `unpack_from` call when a short stream or a tampered `new_size` drove it past the end of a buffer. All three are now converted where they arise, the two `unpack_from` calls behind explicit length checks rather than a `try`. The documentation pass found these; they were not introduced by it, and closing them changed no output byte, only the exception type on input that was already invalid.
- **Error messages versus error display.** This module raises and never prints, so it has no user-facing output of its own. The operator-facing line is emitted by the caller, the gateway's release loop, which is outside this deliverable.
- **Considerations met without effort, stated plainly:** function length (nothing near a contested threshold), indentation (shallow nesting), and spacing (no trailing whitespace). Claiming credit for difficult work on these would be dishonest.

