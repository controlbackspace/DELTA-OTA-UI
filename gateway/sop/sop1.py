"""SOP 1 - what delta differencing does to the firmware payload footprint and to
the network load of a constrained node.

For each firmware pair the step builds the real artifacts with the production
code (bsdiff4 -> BSDIFF40 -> DOTA stream) and compares what a device would have
to receive:

  delta         the DOTA stream built from the BSDIFF40 patch (what we ship)
  full (DOTA)   the whole new image as one copy-only DOTA record (our own
                full-image path: deflated, window-dependent block count)
  full (raw)    the whole new image, uncompressed (a classic full-image OTA)

Everything about sizes, block counts and generation time is MEASURED. The wire
bytes use the exact CoAP framing of the /patch protocol (a documented formula,
not a capture); the airtime and fleet times are MODELLED from stated link
rates and are lower bounds (no retransmissions, ACKs or back-off).
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path

import bsdiff4

from secureota.gateway_runtime.delta_stream import apply_dota, full_image_to_dota, to_dota
from secureota.gateway_runtime.simulation.measure_patch import build_cases
from secureota.release_builder.core import build_release

from .runlog import RunContext, StepResult, Table
from .stats import fmt_ci, summarize

# --- protocol constants (must match coap_server.py / security_engine.py / main.cpp) ---
BLOCK = 1024            # plaintext bytes per block (SLIDING_WINDOW_SIZE)
NONCE_LEN = 13
TAG_LEN = 16
UDP_IP_HEADERS = 28     # IPv4 (20) + UDP (8) per datagram, each direction

# Link rates used for the modelled airtime (documented assumptions, editable).
DEFAULT_RATES = [
    ("802.15.4 (250 kbit/s)", 250_000),
    ("BLE-class (1 Mbit/s)", 1_000_000),
    ("Wi-Fi goodput (10 Mbit/s)", 10_000_000),
]
FLEET_SIZES = (1, 10, 100)


# ---------------------------------------------------------------- wire model
def blocks_for(stream_len: int) -> int:
    return max(1, math.ceil(stream_len / BLOCK))


def coap_request_bytes(block: int) -> int:
    """CON GET /patch?b=<n>: 4-byte header, Uri-Path 'patch' and Uri-Query 'b=<n>'
    (one option header byte each, no token)."""
    return 4 + (1 + len("patch")) + (1 + len(f"b={block}"))


def coap_response_bytes(chunk_len: int) -> int:
    """2.05/2.04 reply: 4-byte header + 0xFF payload marker + nonce||cipher||tag."""
    return 4 + 1 + NONCE_LEN + chunk_len + TAG_LEN


def wire_bytes(stream_len: int) -> dict:
    """Bytes exchanged to deliver one stream block by block (request + reply per
    block). 'coap' counts CoAP+AEAD framing; 'l4' adds UDP/IP headers."""
    n = blocks_for(stream_len)
    coap = 0
    for i in range(n):
        chunk = BLOCK if i < n - 1 else (stream_len - BLOCK * (n - 1))
        coap += coap_request_bytes(i) + coap_response_bytes(chunk)
    return {"blocks": n, "coap": coap, "l4": coap + 2 * n * UDP_IP_HEADERS}


def airtime_s(l4_bytes: int, rate_bps: int) -> float:
    """Lower-bound transfer time at a link rate: bits / rate."""
    return l4_bytes * 8 / rate_bps


def fmt_duration(seconds: float) -> str:
    """'4.2 s' below a minute, '1.4 min' above: tiny fleet times stay readable."""
    return f"{seconds:.1f} s" if seconds < 60 else f"{seconds / 60:.1f} min"


# ------------------------------------------------------------------- measure
def _time_repeats(fn, n: int):
    """Run fn n times; return (last result, list of elapsed ms)."""
    out, ms = None, []
    for _ in range(n):
        t0 = time.perf_counter()
        out = fn()
        ms.append((time.perf_counter() - t0) * 1000.0)
    return out, ms


def measure_pair(label: str, kind: str, base: bytes, target: bytes, repeats: int) -> dict:
    (meta, patch), gen_ms = _time_repeats(lambda: build_release(base, target, "v9.9-sop"), repeats)
    dota, conv_ms = _time_repeats(lambda: to_dota(patch), repeats)
    full_dota = full_image_to_dota(target)

    # Correctness: both reconstructions must reproduce the target byte for byte.
    t0 = time.perf_counter()
    rebuilt = apply_dota(base, dota)
    apply_ms = (time.perf_counter() - t0) * 1000.0
    roundtrip_ok = rebuilt == target and bsdiff4.patch(base, patch) == target

    streams = {"delta": len(dota), "full_dota": len(full_dota), "full_raw": len(target)}
    wires = {k: wire_bytes(v) for k, v in streams.items()}
    return {
        "case": label,
        "kind": kind,
        "base_bytes": len(base),
        "target_bytes": len(target),
        "bsdiff_bytes": len(patch),
        "dota_bytes": streams["delta"],
        "full_dota_bytes": streams["full_dota"],
        "ratio_bsdiff": 1 - len(patch) / len(target) if target else 0.0,
        "ratio_dota": 1 - streams["delta"] / len(target) if target else 0.0,
        "blocks_delta": wires["delta"]["blocks"],
        "blocks_full_dota": wires["full_dota"]["blocks"],
        "blocks_full_raw": wires["full_raw"]["blocks"],
        "l4_delta": wires["delta"]["l4"],
        "l4_full_dota": wires["full_dota"]["l4"],
        "l4_full_raw": wires["full_raw"]["l4"],
        "saved_vs_full_dota": 1 - wires["delta"]["l4"] / wires["full_dota"]["l4"],
        "saved_vs_full_raw": 1 - wires["delta"]["l4"] / wires["full_raw"]["l4"],
        "roundtrip_ok": roundtrip_ok,
        "repeats": repeats,
        "gen_ms": summarize(gen_ms),
        "dota_convert_ms": summarize(conv_ms),
        "apply_dota_ms": apply_ms,
    }


# ----------------------------------------------------------- input discovery
def find_real_pair(firmware_dir: str | None = None, base: str | None = None, target: str | None = None):
    """(base_path, target_path) of the real firmware images, or None."""
    if base and target:
        b, t = Path(base), Path(target)
        return (b, t) if b.is_file() and t.is_file() else None
    roots = []
    if firmware_dir:
        roots.append(Path(firmware_dir))
    if os.environ.get("DELTA_FIRMWARE_DIR"):
        roots.append(Path(os.environ["DELTA_FIRMWARE_DIR"]))
    roots.append(Path.home() / "Documents" / "PlatformIO" / "Projects" / "Thesis")
    for root in roots:
        b, t = root / "release-images" / "app-v1.0.bin", root / "release-images" / "app-v1.1.bin"
        if b.is_file() and t.is_file():
            return b, t
    return None


def _fixtures_pair():
    here = Path(__file__).resolve().parents[1] / "fixtures"
    b, t = here / "v1.0.bin", here / "v1.1.bin"
    return (b, t) if b.is_file() and t.is_file() else None


# --------------------------------------------------------------------- step
def _row(c: dict) -> list:
    return [
        c["case"], c["kind"], f"{c['target_bytes']:,}", f"{c['bsdiff_bytes']:,}", f"{c['dota_bytes']:,}",
        f"{c['ratio_dota']:.1%}", c["blocks_delta"], c["blocks_full_dota"], c["blocks_full_raw"],
        f"{c['saved_vs_full_dota']:.1%}", f"{c['saved_vs_full_raw']:.1%}",
        "yes" if c["roundtrip_ok"] else "NO", fmt_ci(c["gen_ms"], 1, " ms"),
    ]


SIZE_COLUMNS = [
    "Case", "Kind", "New image (B)", "BSDIFF40 (B)", "DOTA delta (B)", "DOTA vs image",
    "Blocks: delta", "Blocks: full (DOTA)", "Blocks: full (raw)",
    "Wire saved vs full (DOTA)", "Wire saved vs full (raw)", "Round-trip OK", "bsdiff time",
]


def run(ctx: RunContext, repeats: int = 5, firmware_dir=None, base=None, target=None,
        rates=None, synthetic: bool = True) -> StepResult:
    rates = rates or DEFAULT_RATES
    res = StepResult(sop="SOP1", title="Delta footprint and network load", mode="offline")
    res.method = (
        "Update artifacts were generated with the production release builder (bsdiff4, producing a BSDIFF40 patch) and "
        "re-packed into the device stream format (DOTA). Payload sizes, block counts and generation times were measured "
        "for the real firmware pair, a 100 KB test pair and six synthetic stress cases. Bytes on the wire were derived "
        "from the exact frame layout of the update protocol (CoAP request and reply, AEAD framing and UDP/IP headers "
        "for every block). Each reconstruction was verified byte for byte. Airtime and fleet-update durations were "
        "modelled from stated link rates."
    )
    res.limitations += [
        "Airtime and fleet-update durations are modelled lower bounds computed from stated link rates; they exclude "
        "acknowledgements, retransmissions and medium-access delays.",
        "Generation and decoding times were measured on the build host, not on the target microcontroller.",
    ]

    cases: list[dict] = []
    real = find_real_pair(firmware_dir, base, target)
    if real:
        b, t = real
        ctx.add_input("real firmware base", b)
        ctx.add_input("real firmware target", t)
        cases.append(measure_pair(f"{b.name} -> {t.name}", "real", b.read_bytes(), t.read_bytes(), repeats))
    else:
        res.not_performed.append(
            "The production firmware image pair (app-v1.0.bin, app-v1.1.bin) was not available; no result for the "
            "production firmware is reported."
        )

    fx = _fixtures_pair()
    if fx:
        ctx.add_input("fixture base", fx[0])
        ctx.add_input("fixture target", fx[1])
        cases.append(measure_pair("fixtures v1.0 -> v1.1", "fixture", fx[0].read_bytes(), fx[1].read_bytes(), repeats))

    if synthetic:
        for label, sb, st in build_cases():
            reps = min(repeats, 3) if len(st) > 1_000_000 else repeats
            cases.append(measure_pair(label, "synthetic", sb, st, reps))

    if not cases:
        res.status, res.reason = "failed", "no inputs"
        return res

    # --- files ---------------------------------------------------------------
    flat_cols = [k for k in cases[0] if k not in ("gen_ms", "dota_convert_ms")] + [
        "gen_ms_mean", "gen_ms_sd", "gen_ms_ci95", "dota_convert_ms_mean",
    ]
    flat_rows = [
        [c[k] for k in cases[0] if k not in ("gen_ms", "dota_convert_ms")]
        + [c["gen_ms"]["mean"], c["gen_ms"]["sd"], c["gen_ms"]["ci95"], c["dota_convert_ms"]["mean"]]
        for c in cases
    ]
    res.files.append(ctx.write_csv("sop1/cases.csv", flat_cols, flat_rows))
    res.files.append(ctx.write_json("sop1/cases.json", cases))

    # --- tables ----------------------------------------------------------------
    res.tables.append(Table(
        "Payload and block counts per firmware pair", SIZE_COLUMNS, [_row(c) for c in cases], "measured",
        note=f"Sizes, block counts and times were measured with the production code ({repeats} timing repeats; "
             f"{BLOCK}-byte blocks). Wire savings are derived from the frame layout of the update protocol "
             "(CoAP request and reply, AEAD framing, UDP/IP headers per exchange).",
    ))

    primary = cases[0]
    # airtime table (modelled)
    air_rows = []
    for name, bps in rates:
        air_rows.append([
            name,
            f"{airtime_s(primary['l4_delta'], bps):.2f} s",
            f"{airtime_s(primary['l4_full_dota'], bps):.2f} s",
            f"{airtime_s(primary['l4_full_raw'], bps):.2f} s",
        ])
    res.tables.append(Table(
        f"Modelled airtime for one device - {primary['case']}",
        ["Link", "Delta (DOTA)", "Full image (DOTA)", "Full image (raw)"], air_rows, "modelled",
        note="Lower bound: wire bits divided by link rate; acknowledgements, retransmission, back-off and processing are excluded.",
    ))
    fleet_rows = []
    for name, bps in rates:
        for n in FLEET_SIZES:
            fleet_rows.append([
                name, n,
                fmt_duration(n * airtime_s(primary['l4_delta'], bps)),
                fmt_duration(n * airtime_s(primary['l4_full_dota'], bps)),
                fmt_duration(n * airtime_s(primary['l4_full_raw'], bps)),
            ])
    res.tables.append(Table(
        f"Modelled time to update a fleet on one shared channel - {primary['case']}",
        ["Link", "Devices", "Delta (DOTA)", "Full image (DOTA)", "Full image (raw)"], fleet_rows, "modelled",
        note="Proxy for bandwidth saturation: devices update one after another on a shared medium "
             "(devices x single-device airtime).",
    ))

    # --- claims ----------------------------------------------------------------
    p = primary
    label = "production firmware" if p["kind"] == "real" else f"{p['kind']} data, not the production firmware"
    res.summary = (
        f"For {p['case']}, the update is delivered in {p['blocks_delta']} blocks instead of {p['blocks_full_dota']} "
        f"for a full image, {p['saved_vs_full_dota']:.1%} less traffic on the wire."
    )
    res.claims.append(
        f"[measured, {label}] For the pair {p['case']}, the new image is {p['target_bytes']:,} B. The BSDIFF40 patch is "
        f"{p['bsdiff_bytes']:,} B and the device stream (DOTA) is {p['dota_bytes']:,} B "
        f"({p['ratio_dota']:.1%} smaller than the image). It is delivered in {p['blocks_delta']} blocks, compared with "
        f"{p['blocks_full_dota']} blocks for the same image sent as a full deflated image and "
        f"{p['blocks_full_raw']} blocks sent raw. On the wire (CoAP, AEAD framing and UDP/IP) this is {p['l4_delta']:,} B "
        f"against {p['l4_full_dota']:,} B ({p['saved_vs_full_dota']:.1%} less) for the full deflated image and "
        f"{p['l4_full_raw']:,} B ({p['saved_vs_full_raw']:.1%} less) for the raw image."
    )
    bps = rates[0][1]
    n_big = FLEET_SIZES[-1]
    res.claims.append(
        f"[modelled, lower bound] Updating {n_big} devices one after another on a shared {rates[0][0]} channel would take "
        f"{fmt_duration(n_big * airtime_s(p['l4_delta'], bps))} with the delta versus "
        f"{fmt_duration(n_big * airtime_s(p['l4_full_dota'], bps))} with a full (DOTA) image and "
        f"{fmt_duration(n_big * airtime_s(p['l4_full_raw'], bps))} with a raw image."
    )
    worst = [c for c in cases if c["kind"] == "synthetic" and c["ratio_dota"] < 0]
    if worst:
        res.notes.append(
            "Unfavourable cases: " + ", ".join(f"{c['case']} ({c['ratio_dota']:.1%} relative to the image)" for c in worst)
            + ". A delta can exceed the image when the two inputs are unrelated, as with incompressible noise."
        )
    bad = [c["case"] for c in cases if not c["roundtrip_ok"]]
    if bad:
        res.status, res.reason = "failed", "round-trip failed for: " + ", ".join(bad)
    else:
        res.notes.append("Every case reconstructs the target image byte for byte, using both the DOTA reference decoder and bsdiff4.")
    res.data = {"primary_case": p["case"], "block_size": BLOCK, "rates": rates}
    return res
