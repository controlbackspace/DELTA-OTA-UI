"""D4 stress + D7 baseline metrics: bsdiff4 generation time/size/ratio.

Day-1 baseline cases (dummy-4B, image-3KB, synth-1.2MB) are frozen for
cross-day comparability. Day-4 stress cases probe the edges:

  identical-3KB  degenerate edge: empty diff must not choke the pipeline.
  noise-64KB     adversarial edge: incompressible input; the patch may exceed
                 the target (negative ratio is honest worst-case data).
  fw-bump-1.25MB realistic edge: OTA-slot-sized pair (0x140000) with scattered
                 localized edits, the true firmware-bump shape.

All inputs deterministic (no randomness) so Sept 29 reruns are comparable.
Writes one JSON object per case to stdout.

Run:  python simulation/measure_patch.py
"""
import sys
from pathlib import Path

# secureota/ lives three levels up: simulation/ -> gateway_runtime/ -> secureota/ -> gateway/
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import json
import time

from secureota.release_builder.core import build_release


def measure(label: str, base: bytes, target: bytes) -> dict:
    t0 = time.perf_counter()
    metadata, _patch_bytes = build_release(base, target, "v9.9-measure")
    dt_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "case": label,
        "base_bytes": len(base),
        "target_bytes": len(target),
        "patch_bytes": metadata.patch_size,
        "compression_ratio": round(metadata.compression_ratio, 4),
        "gen_ms": round(dt_ms, 1),
    }


def main():
    results = []
    results.append(measure("dummy-4B", b"test", b"test"))

    img = (b"firmware-image-v1.1:" * 160)[:3000]
    results.append(measure("image-3KB", img, img + b"!"))

    big_base = bytes((i * 7) & 0xFF for i in range(1_200_000))
    big_tgt = bytearray(big_base)
    for i in range(0, 1_200_000, 97):
        big_tgt[i] = (big_tgt[i] + 1) & 0xFF
    results.append(measure("synth-1.2MB", big_base, bytes(big_tgt)))

    # ── Day-4 stress cases ──────────────────────────────────────────────
    # Identical inputs: degenerate empty-diff edge.
    results.append(measure("identical-3KB", img, img))

    # Incompressible pair: xorshift32 pseudo-noise, target = independently
    # reseeded stream. Worst-case shape; patch may exceed target.
    def xorshift32(n, seed):
        x = seed
        out = bytearray()
        for _ in range(n):
            x ^= (x << 13) & 0xFFFFFFFF
            x ^= x >> 17
            x ^= (x << 5) & 0xFFFFFFFF
            out += x.to_bytes(4, "little")
        return bytes(out[:n])

    results.append(measure("noise-64KB", xorshift32(65536, 0x12345678),
                            xorshift32(65536, 0x87654321)))

    # OTA-slot-sized firmware bump: 1.25MB patterned image with scattered
    # localized edits (every 4091st byte block tweaked + version stamp).
    fw_base = bytearray((i * 13 + (i >> 8)) & 0xFF for i in range(1_310_720))
    fw_tgt = bytearray(fw_base)
    for i in range(0, 1_310_720, 4091):
        fw_tgt[i] = (fw_tgt[i] + 7) & 0xFF
    fw_tgt[:24] = b"firmware-image-v1.2\x00\x00\x00\x00\x00"
    results.append(measure("fw-bump-1.25MB", bytes(fw_base), bytes(fw_tgt)))

    for row in results:
        print(json.dumps(row))


if __name__ == "__main__":
    main()
