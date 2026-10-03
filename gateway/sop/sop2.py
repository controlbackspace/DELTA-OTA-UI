"""SOP 2 - cost of our pre-shared-key AEAD framing versus a standard handshake.

HONEST SCOPE: the framing under test is **OSCORE-style AEAD framing**, not RFC 8613
OSCORE. It uses a pre-shared AES-128 key and AES-CCM per block with a 13-byte
nonce and a 16-byte tag, and has no handshake. It has no HKDF context derivation,
no sender sequence numbers / replay window, no AAD binding and no OSCORE option.
The report says so and records `oscore_mode: emulated`.

Measured here (gateway host): per-block AES-CCM seal/open time, key-schedule time,
sealing the real update stream, and a complete TLS 1.2 handshake (ECDHE + X.509)
between two in-memory endpoints: its CPU time and exact bytes/flights.
Taken from hardware when available: AES-CCM decrypt time per block from the
firmware's `[Metrics]` line (--factory-log) and the TLS handshake time / peak
heap measured on the same ESP32 by the SOP 4 hardware run.
Cited (literature, labelled): per-message overhead of RFC 8613 / TLS 1.2 / DTLS 1.2.
Modelled: airtime of the handshake at stated link rates.
"""
from __future__ import annotations

import datetime as dt
import os
import ssl
import tempfile
import time
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.x509.oid import NameOID

from secureota.gateway_runtime.delta_stream import to_dota
from secureota.release_builder.core import build_release

from .runlog import RunContext, StepResult, Table
from .serial_parse import parse_log, peak_heap
from .sop1 import BLOCK, DEFAULT_RATES, NONCE_LEN, TAG_LEN, airtime_s, find_real_pair
from .stats import fmt_ci, summarize

KEY = b"TEST_KEY_1234567"          # bench key: the cost does not depend on the key value
ASSUMED_RTT_MS = 50                 # modelled round-trip time for handshake flights


# ------------------------------------------------------------ AEAD micro-benchmarks
def bench_aead(ops: int) -> dict:
    """Per-block seal/open (1 KiB, 13-byte nonce, 16-byte tag, as security_engine) and key schedule, in µs."""
    aes = AESCCM(KEY)
    block = os.urandom(BLOCK)
    prefix = os.urandom(8)
    nonces = [prefix + i.to_bytes(5, "big") for i in range(ops + 200)]
    for n in nonces[:200]:                                         # warm-up
        aes.decrypt(n, aes.encrypt(n, block, None), None)
    seal, opened, sched = [], [], []
    frames = []
    for n in nonces[200:]:
        t0 = time.perf_counter_ns()
        ct = aes.encrypt(n, block, None)
        seal.append((time.perf_counter_ns() - t0) / 1000)
        frames.append((n, ct))
    for n, ct in frames:
        t0 = time.perf_counter_ns()
        aes.decrypt(n, ct, None)
        opened.append((time.perf_counter_ns() - t0) / 1000)
    for _ in range(min(ops, 500)):
        t0 = time.perf_counter_ns()
        AESCCM(KEY)
        sched.append((time.perf_counter_ns() - t0) / 1000)
    return {"seal_us": summarize(seal), "open_us": summarize(opened), "key_schedule_us": summarize(sched),
            "frame_overhead_bytes": NONCE_LEN + TAG_LEN}


def _stream_chunks(firmware_dir=None, base=None, target=None) -> tuple[list[bytes], str]:
    pair = find_real_pair(firmware_dir, base, target)
    if pair:
        b, t = pair
        _meta, patch = build_release(b.read_bytes(), t.read_bytes(), "v9.9-sop2")
        stream, label = to_dota(patch), f"real DOTA stream ({b.name} -> {t.name})"
    else:
        stream, label = os.urandom(24 * BLOCK), "24 KiB of random bytes (real firmware pair not found)"
    return [stream[i:i + BLOCK] for i in range(0, len(stream), BLOCK)], label


def bench_stream(chunks: list[bytes], repeats: int) -> dict:
    aes = AESCCM(KEY)
    prefix = os.urandom(8)
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        for i, c in enumerate(chunks):
            aes.encrypt(prefix + i.to_bytes(5, "big"), c, None)
        times.append((time.perf_counter() - t0) * 1000)
    return {"blocks": len(chunks), "bytes": sum(map(len, chunks)), "seal_ms": summarize(times)}


# ----------------------------------------------------------- TLS handshake (in memory)
def _contexts():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "gw.local")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    with tempfile.TemporaryDirectory() as d:
        cert_pem, key_pem = Path(d) / "c.pem", Path(d) / "k.pem"
        cert_pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.minimum_version = server.maximum_version = ssl.TLSVersion.TLSv1_2
        server.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
        server.load_cert_chain(cert_pem, key_pem)
        client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client.minimum_version = client.maximum_version = ssl.TLSVersion.TLSv1_2
        client.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")
        client.check_hostname = False                       # certificate IS verified against the trust anchor
        client.load_verify_locations(cafile=str(cert_pem))
    return client, server


def tls_handshake_once(client_ctx: ssl.SSLContext, server_ctx: ssl.SSLContext) -> dict:
    """One complete TLS 1.2 handshake between two in-memory endpoints (no sockets, no
    network): CPU time of both ends and the exact bytes/flights exchanged."""
    c_in, c_out, s_in, s_out = (ssl.MemoryBIO() for _ in range(4))
    client = client_ctx.wrap_bio(c_in, c_out, server_hostname="gw.local")
    server = server_ctx.wrap_bio(s_in, s_out, server_side=True)
    c2s = s2c = flights = 0
    last = None
    client_s = 0.0
    done_c = done_s = False
    t0 = time.perf_counter()
    for _ in range(40):
        if not done_c:
            t = time.perf_counter()
            try:
                client.do_handshake()
                done_c = True
            except ssl.SSLWantReadError:
                pass
            client_s += time.perf_counter() - t
        data = c_out.read()
        if data:
            c2s += len(data)
            if last != "c":
                flights, last = flights + 1, "c"
            s_in.write(data)
        if not done_s:
            try:
                server.do_handshake()
                done_s = True
            except ssl.SSLWantReadError:
                pass
        data = s_out.read()
        if data:
            s2c += len(data)
            if last != "s":
                flights, last = flights + 1, "s"
            c_in.write(data)
        if done_c and done_s:
            break
    else:
        raise RuntimeError("TLS handshake did not complete")
    return {"total_ms": (time.perf_counter() - t0) * 1000, "client_ms": client_s * 1000,
            "bytes_c2s": c2s, "bytes_s2c": s2c, "flights": flights,
            "version": client.version(), "cipher": client.cipher()[0]}


def bench_handshake(n: int) -> dict:
    client_ctx, server_ctx = _contexts()
    runs = [tls_handshake_once(client_ctx, server_ctx) for _ in range(n)]
    first = runs[0]
    return {
        "n": n, "version": first["version"], "cipher": first["cipher"], "flights": first["flights"],
        "bytes": first["bytes_c2s"] + first["bytes_s2c"], "bytes_c2s": first["bytes_c2s"], "bytes_s2c": first["bytes_s2c"],
        "total_ms": summarize([r["total_ms"] for r in runs]), "client_ms": summarize([r["client_ms"] for r in runs]),
    }


# --------------------------------------------------------------------------- step
CITED_OVERHEAD = [
    # design, per-message overhead description, bytes (low, high), handshake note, source
    ("Delta-OTA framing (this work, OSCORE-style)", "13 B nonce + 16 B tag", (29, 29), "none: pre-shared key",
     "measured: frame layout of security_engine.encrypt_blocks"),
    ("OSCORE, RFC 8613 (AES-CCM-16-64-128)", "8 B tag + OSCORE option (flags + 1-5 B Partial IV)", (11, 17),
     "none (key from a master secret; EDHOC optional)", "cited: RFC 8613 sections 5-6 - verify before quoting"),
    ("TLS 1.2, AES-128-GCM record", "5 B header + 8 B explicit nonce + 16 B tag", (29, 29), "full handshake (measured below)",
     "cited: RFC 5246 / RFC 5288"),
    ("DTLS 1.2, AES-128-GCM record", "13 B header + 8 B explicit nonce + 16 B tag", (37, 37), "full handshake + cookie exchange",
     "cited: RFC 6347 section 4.1 / RFC 5288"),
]


def _device_section(res: StepResult, ctx: RunContext, factory_log: str | None, blocks: int) -> dict:
    """Device-side numbers from a serial capture and/or the SOP4 hardware run. Returns facts for the claims."""
    facts: dict = {}
    rows = []
    if factory_log:
        try:
            lp = parse_log(Path(factory_log).read_text(encoding="utf-8", errors="replace"))
            if lp["metrics"]:
                m = lp["metrics"][-1]
                facts["decrypt"] = m
                rows += [["AES-CCM decrypt per block (ESP32, mbedTLS)", f"avg {m['avg_us']:,} µs (min {m['min_us']:,}, max {m['max_us']:,}; n={m['n']} blocks)"],
                         [f"Decrypt time for a {blocks}-block update", f"{blocks * m['avg_us'] / 1000:.1f} ms (avg x {blocks})"]]
            else:
                res.notes.append(f"No [Metrics] line in {factory_log}.")
            try:
                p = peak_heap(lp["mem"], "stream-start", "stream-end")
                facts["stream_peak"] = p["class2_peak"]
                rows.append(["Peak heap of the whole update stream (our design)", f"{p['class2_peak']:,} B"])
            except ValueError:
                pass
        except OSError as e:
            res.notes.append(f"Supplied capture not readable: {e}")
    sop4 = (ctx.results.get("SOP4") or {}).get("data", {})
    hw = sop4.get("web3_hw")
    if hw and hw.get("tls_connect_ms"):
        t = hw["tls_connect_ms"]
        facts["tls_ms"] = t["mean"]
        facts["tls_heap"] = hw["peak_heap_bytes"]
        rows += [["Standard TLS connect + handshake (ESP32, from the SOP 4 hardware run)", fmt_ci(t, 0, " ms")],
                 ["Peak heap of that TLS client (ESP32)", f"{hw['peak_heap_bytes']:,} B" + ("" if hw["peak_exact"] else " (upper bound)")]]
    if sop4.get("engine"):
        e = sop4["engine"]
        rows.append(["Static RAM of the AEAD receive path (otaEngine: two packet buffers + CCM context; "
                     "excludes the DOTA decoder, see SOP 4)", f"{e['ram']:,} B"])
    if rows:
        res.tables.append(Table("Device side (ESP32)", ["Metric", "Value"], rows, "measured",
                                note="Only what was captured: a supplied serial log (--factory-log) and/or the SOP 4 hardware run in this "
                                     "run directory. The TLS figure is certificate-based HTTPS, not DTLS-PSK."))
    else:
        res.notes.append("SKIPPED - device side: no --factory-log and no SOP 4 hardware data in this run. Gateway-host "
                         "numbers above are NOT device numbers.")
    return facts


def run(ctx: RunContext, ops: int = 2000, handshakes: int = 50, firmware_dir=None, base=None, target=None,
        factory_log: str | None = None) -> StepResult:
    res = StepResult(sop="SOP2", title="OSCORE-style framing vs a standard handshake", mode="offline")
    ctx.meta["oscore_mode"] = "emulated"

    aead = bench_aead(ops)
    chunks, label = _stream_chunks(firmware_dir, base, target)
    stream = bench_stream(chunks, repeats=30)
    hs = bench_handshake(handshakes)
    res.files.append(ctx.write_json("sop2/bench.json", {"aead": aead, "stream": stream, "handshake": hs}))

    def row(name, s, unit):
        return [name, fmt_ci(s, 2, unit), f"{s['median']:.2f}", f"{s['p95']:.2f}", f"{s['n']}"]

    res.tables.append(Table(
        "Gateway host: crypto cost of our framing vs a TLS 1.2 handshake",
        ["Operation", "Mean ± 95% CI", "Median", "p95", "n"],
        [row("AES-CCM seal, 1 KiB block (13 B nonce, 16 B tag)", aead["seal_us"], " µs"),
         row("AES-CCM open, 1 KiB block", aead["open_us"], " µs"),
         row("AES-CCM key schedule (once per session/boot)", aead["key_schedule_us"], " µs"),
         row(f"Seal the whole stream: {stream['blocks']} blocks, {stream['bytes']:,} B ({label})", stream["seal_ms"], " ms"),
         row(f"TLS 1.2 handshake, both ends ({hs['cipher']}, X.509 verified)", hs["total_ms"], " ms"),
         row("   of which the client side", hs["client_ms"], " ms")],
        "measured",
        note="Timed in-process on the gateway host (not the ESP32). The handshake runs between two in-memory endpoints, "
             "so it contains CPU time only, no network time. Our framing needs no handshake at all.",
    ))

    ours = BLOCK  # per-block message; overhead in bytes
    over_rows = []
    for design, what, (lo, hi), hs_note, src in CITED_OVERHEAD:
        b = f"{lo} B" if lo == hi else f"{lo}-{hi} B"
        stream_extra = f"{stream['blocks'] * lo:,}" if lo == hi else f"{stream['blocks'] * lo:,}-{stream['blocks'] * hi:,}"
        over_rows.append([design, what, b, f"{stream_extra} B", hs_note, src])
    res.tables.append(Table(
        f"Per-message overhead and session set-up ({stream['blocks']}-block update)",
        ["Design", "Per-message overhead", "Bytes per message", f"Extra bytes for {stream['blocks']} messages", "Session set-up", "Source"],
        over_rows, "cited",
        note="Our row is measured from the frame layout; the other rows are literature values (labelled cited) and must be "
             "checked against the RFC text before they are quoted.",
    ))

    hs_rows = []
    for name, bps in DEFAULT_RATES:
        air = airtime_s(hs["bytes"] + 4 * 28, bps)            # + UDP/IP headers for ~4 datagrams (lower bound)
        hs_rows.append([name, f"{air * 1000:.1f} ms", f"{air * 1000 + 2 * ASSUMED_RTT_MS:.1f} ms"])
    res.tables.append(Table(
        f"Modelled network cost of ONE TLS 1.2 handshake ({hs['bytes']:,} B in {hs['flights']} flights) - ours is zero",
        ["Link", "Handshake airtime", f"Airtime + 2 x {ASSUMED_RTT_MS} ms RTT (assumed)"], hs_rows, "modelled",
        note="Lower bound: bits/rate for the measured handshake bytes plus UDP/IP headers; ignores loss and processing."))

    facts = _device_section(res, ctx, factory_log, stream["blocks"])

    # ---------------- claims -----------------------------------------------------
    res.claims.append(
        f"[measured, gateway host] Sealing or opening one 1 KiB block with the pre-shared-key AES-CCM framing takes "
        f"{fmt_ci(aead['seal_us'], 1, ' µs')} / {fmt_ci(aead['open_us'], 1, ' µs')}; the framing adds {aead['frame_overhead_bytes']} B "
        f"per block and needs no handshake, whereas a complete TLS 1.2 handshake ({hs['version']}, {hs['cipher']}) costs "
        f"{fmt_ci(hs['total_ms'], 2, ' ms')} of CPU and {hs['bytes']:,} B in {hs['flights']} flights - about "
        f"{hs['total_ms']['mean'] / stream['seal_ms']['mean']:.0f}x the time to seal the whole {stream['blocks']}-block update."
    )
    if "decrypt" in facts and "tls_ms" in facts:
        d = facts["decrypt"]
        total_ms = stream["blocks"] * d["avg_us"] / 1000
        res.claims.append(
            f"[measured, ESP32] Decrypting a block takes {d['avg_us']:,} µs on average (n={d['n']}), i.e. {total_ms:.0f} ms for a "
            f"{stream['blocks']}-block update, while a standard TLS connect on the same device takes {facts['tls_ms']:,.0f} ms and "
            f"peaks at {facts['tls_heap']:,} B of heap."
        )
    elif "decrypt" in facts:
        d = facts["decrypt"]
        res.claims.append(f"[measured, ESP32] Decrypting a block takes {d['avg_us']:,} µs on average (n={d['n']}, min {d['min_us']:,}, "
                          f"max {d['max_us']:,}).")

    res.notes += [
        "SCOPE: this is OSCORE-style AEAD framing, not RFC 8613 OSCORE. Absent compared with real OSCORE: HKDF context "
        "derivation, sender sequence numbers with a replay window, AAD binding of release/block, and the OSCORE option. "
        "Do not claim RFC 8613 compliance. (SOP 3 measured the consequence: authentic replayed/reordered blocks pass the per-block check.)",
        "The measured handshake uses a minimal self-signed ECDSA certificate; a real certificate chain adds roughly "
        "1-3 KB more, so the handshake bytes here are a lower bound. The host has AES hardware acceleration, so the "
        "microsecond figures are not ESP32 figures.",
        "The key is pre-shared and long-lived: there is no session key establishment, so there is no forward secrecy; the cost "
        "saved is exactly the handshake a standard stack would pay.",
    ]
    return res
