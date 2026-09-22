"""D7 baseline metrics: bsdiff4 generation time/size/ratio across payload scales.

Deterministic inputs (no randomness) so Sept 29 reruns are comparable.
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

    for row in results:
        print(json.dumps(row))


if __name__ == "__main__":
    main()
