"""SOP 3 - how reliable is a ledger-anchored release at guaranteeing authenticity
and at executing absolute revocation?

Three measured parts:
  A. the smart-contract test suite (Hardhat): governance rules as executable facts
  B. a software attack matrix: injected faults against the production checks,
     with the layer that stopped each one and a Wilson 95% confidence interval
  C. a live local chain + the real gateway process: unauthorized callers,
     wrong-hash releases, and the revoke-to-halt latency (chain tx -> gateway
     kills its artifacts -> the gateway answers 4.03), plus gas per call

Part C needs Node (Hardhat) and a free UDP 5683; without them it is reported as
skipped and A+B still run.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import time
from pathlib import Path

from .attacks import ATTACKS, run_matrix
from .chain import BLOCKCHAIN_DIR, Chain, ChainUnavailable, HardhatNode
from .coap_probe import probe
from .gateway_proc import COAP_HOST, COAP_PORT, GatewayProc, poll_interval_s
from .runlog import RunContext, StepResult, Table
from .stats import fmt_ci, summarize, wilson_interval


# ------------------------------------------------------------------ part A
def parse_mocha_report(path: Path) -> dict:
    """Pure parser for mocha's JSON reporter output."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = []
    for ok, items in ((True, d.get("passes", [])), (False, d.get("failures", []))):
        for t in items:
            title, full = t.get("title", ""), t.get("fullTitle", "")
            suite = full[: -len(title)].strip() if title and full.endswith(title) else ""
            cases.append({"suite": suite, "title": title, "ok": ok, "ms": t.get("duration"),
                          "error": (t.get("err") or {}).get("message", "")})
    s = d.get("stats", {})
    return {"tests": s.get("tests", 0), "passes": s.get("passes", 0), "failures": s.get("failures", 0),
            "duration_ms": s.get("duration", 0), "cases": cases}


def run_contract_tests(ctx: RunContext) -> dict:
    npx = shutil.which("npx")
    if not npx:
        raise ChainUnavailable("npx (Node.js) not found on PATH")
    report = ctx.sub("raw") / "mocha.json"
    env = dict(os.environ, SOP_MOCHA_JSON=str(report))
    proc = subprocess.run([npx, "hardhat", "test"], cwd=BLOCKCHAIN_DIR, env=env,
                          capture_output=True, text=True, timeout=900)
    (ctx.sub("raw") / "hardhat-test.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if not report.is_file():
        raise ChainUnavailable("hardhat test produced no report: " + (proc.stderr or proc.stdout)[-300:])
    return parse_mocha_report(report)


# ------------------------------------------------------------------ part C
def _unauthorized(chain: Chain, trials: int) -> dict:
    """An outsider (account 3) tries every state-changing call; each must revert
    and leave the release untouched."""
    base = chain.propose("v0.9", hashlib.sha256(b"seed").hexdigest(), "file:///x", 0)
    before = chain.release("v0.9")
    stopped = {"propose": 0, "approve": 0, "revoke": 0}
    for i in range(trials):
        if not chain.propose(f"v0.8.{i}", hashlib.sha256(bytes([i])).hexdigest(), "file:///x", 3).ok:
            stopped["propose"] += 1
        if not chain.approve("v0.9", 3).ok:
            stopped["approve"] += 1
        if not chain.revoke("v0.9", 3).ok:
            stopped["revoke"] += 1
    untouched = chain.release("v0.9") == before and base.ok
    return {"trials": trials, "stopped": stopped, "state_untouched": untouched}


def _wrong_hash_live(chain: Chain, gw: GatewayProc, payload_url: str, good_hex: str, trials: int) -> list[dict]:
    """Anchor a hash that does not match the payload and approve it: the gateway
    must refuse to stage it and keep answering 4.01."""
    out = []
    for k in range(trials):
        tag = f"v9.{k}"
        bad = hashlib.sha256(b"not the payload" + bytes([k])).hexdigest()
        assert bad != good_hex
        last_event = max((e["id"] for e in gw.status().get("events", [])), default=0)
        chain.propose(tag, bad, payload_url, 0)
        t_live = chain.approve(tag, 1).t_mined
        # Wait for the gateway's OWN verdict on THIS release (a stale 'hash-mismatch'
        # state from the previous trial would pass without proving anything).
        verdict, st = gw.wait_for(
            lambda s: any(e["id"] > last_event and e["msg"].startswith(f"{tag}: downloaded bytes do not match")
                          for e in s.get("events", [])), timeout=40)
        code, _, _ = probe(COAP_HOST, COAP_PORT, "version")
        staged = bool(st.get("staged_version")) or gw.block_files() > 0
        out.append({
            "tag": tag, "refused": bool(verdict) and not staged and code == "4.01",
            "gateway_state": st.get("gateway_state"), "version_reply": code, "blocks_on_disk": gw.block_files(),
            "detect_s": (time.time() - t_live) if verdict else None,
        })
    return out


def _revoke_latency(chain: Chain, gw: GatewayProc, payload_url: str, good_hex: str, n: int) -> list[dict]:
    """Right after staging the gateway starts a fresh poll sleep, so revoking at
    that instant would measure the worst case every time. A real revoke can
    arrive at any moment of the poll cycle: the revoke is sent after a seeded
    random delay of 0..poll interval so the phase is uniformly distributed."""
    trials = []
    rng = random.Random(20261003)
    poll = poll_interval_s() or 5
    for i in range(n):
        rec = {"trial": i, "ok": False}
        p = chain.propose("v1.1", good_hex, payload_url, 0)
        a = chain.approve("v1.1", 1)
        rec["gas_propose"], rec["gas_approve"] = p.gas_used, a.gas_used
        if not (p.ok and a.ok):
            rec["error"] = f"setup tx failed: {p.error or a.error}"
            trials.append(rec)
            continue
        staged, _ = gw.wait_for(lambda s: s.get("gateway_state") == "staged" and s.get("staged_version") == "v1.1", 60)
        code, _, _ = probe(COAP_HOST, COAP_PORT, "version")
        if not staged or code != "2.05":
            rec["error"] = f"gateway did not stage v1.1 (state={gw.status().get('gateway_state')}, /version={code})"
            trials.append(rec)
            continue
        last_event = max((e["id"] for e in gw.status().get("events", [])), default=0)

        phase_delay = rng.uniform(0, poll)
        rec["phase_delay_s"] = phase_delay
        time.sleep(phase_delay)
        r = chain.revoke("v1.1", 2)
        rec["gas_revoke"] = r.gas_used
        t_halt = None
        deadline = time.time() + 30
        while time.time() < deadline:
            code, _, _ = probe(COAP_HOST, COAP_PORT, "version", timeout=0.25)
            if code == "4.03":
                t_halt = time.time()
                break
            time.sleep(0.02)
        if t_halt is None:
            rec["error"] = "gateway never answered 4.03 after the revoke"
            trials.append(rec)
            continue
        kill = next((e for e in gw.status().get("events", []) if e["id"] > last_event and e["msg"].startswith("KILL SWITCH")), None)
        if kill is None:                                    # the event is written right after the state flips
            time.sleep(0.2)
            kill = next((e for e in gw.status().get("events", []) if e["id"] > last_event and e["msg"].startswith("KILL SWITCH")), None)
        rec.update({
            "ok": True,
            "chain_ms": (r.t_mined - r.t_sent) * 1000,
            "detect_ms": (kill["t"] - r.t_mined) * 1000 if kill else None,
            "halt_ms": (t_halt - r.t_sent) * 1000,
            "blocks_left": gw.block_files(),
        })
        trials.append(rec)
    return trials


def run_chain_phase(ctx: RunContext, unauth_trials: int, live_trials: int, n_latency: int, port: int) -> dict:
    if not GatewayProc.port_free():
        raise ChainUnavailable(f"UDP {COAP_PORT} is in use (a gateway is running?) - stop it and re-run")
    raw = ctx.sub("raw")
    work = ctx.sub("work_sop3")
    payload = random.Random(7).randbytes(8192)
    (work / "payload.bin").write_bytes(payload)
    url = (work / "payload.bin").resolve().as_uri()
    good = hashlib.sha256(payload).hexdigest()

    node = HardhatNode(port, raw / "hardhat-node.log")
    gw: GatewayProc | None = None
    try:
        node.start()
        chain = Chain(node.url)
        addr = chain.deploy()
        out = {"contract": addr, "node": node.url}
        out["unauthorized"] = _unauthorized(chain, unauth_trials)

        gw = GatewayProc(node.url, addr, work, raw / "gateway.log")
        gw.start()
        ready, _ = gw.wait_for(lambda s: s.get("gateway_state") == "waiting", 90)
        if not ready:
            raise ChainUnavailable("gateway did not reach 'waiting' - see raw/gateway.log")
        out["wrong_hash"] = _wrong_hash_live(chain, gw, url, good, live_trials)
        out["revoke"] = _revoke_latency(chain, gw, url, good, n_latency)
        return out
    finally:
        if gw:
            gw.stop()
        node.stop()


# --------------------------------------------------------------------- step
def _layers_text(layers: dict) -> str:
    return " / ".join(k for k in layers if k != "NONE") or "-"


def run(ctx: RunContext, trials: int = 30, n_latency: int = 10, live_trials: int = 3,
        chain: bool = True, hardhat_port: int = 18545) -> StepResult:
    res = StepResult(sop="SOP3", title="Ledger reliability and revocation", mode="offline")
    failures: list[str] = []
    skipped: list[str] = []

    # ---- A. contract suite --------------------------------------------------
    try:
        t = run_contract_tests(ctx)
        by_suite: dict[str, list] = {}
        for c in t["cases"]:
            by_suite.setdefault(c["suite"] or "(root)", []).append(c)
        res.tables.append(Table(
            "Smart-contract test suite (Hardhat)", ["Suite", "Tests", "Passed"],
            [[s, len(cs), sum(c["ok"] for c in cs)] for s, cs in sorted(by_suite.items())]
            + [["**Total**", t["tests"], t["passes"]]], "measured",
            note=f"npx hardhat test; {t['duration_ms']} ms. Raw: raw/mocha.json, raw/hardhat-test.log.",
        ))
        res.files += ["raw/mocha.json", "raw/hardhat-test.log"]
        res.claims.append(
            f"[measured] {t['passes']}/{t['tests']} contract tests pass: the fixed 2-of-3 threshold, one signature per "
            "developer per round, authorization of every caller, finality of revocation, fresh rounds on re-proposal, "
            "and the events the gateway relies on."
        )
        if t["failures"]:
            failures.append(f"{t['failures']} contract test(s) failed")
    except (ChainUnavailable, subprocess.SubprocessError) as e:
        skipped.append(f"contract tests: {e}")

    # ---- B. attack matrix -----------------------------------------------------
    rows = run_matrix(trials)
    res.files.append(ctx.write_json("sop3/attack_matrix.json", rows))
    table_rows, total, stopped = [], 0, 0
    for r in rows:
        lo, hi = wilson_interval(r["stopped"], r["trials"])
        total += r["trials"]
        stopped += r["stopped"]
        table_rows.append([
            r["name"], r["description"], _layers_text(r["layers"]), r["trials"], r["stopped"],
            f"{r['stopped'] / r['trials']:.1%} (≥ {lo:.1%})", r["authentic_frames_accepted_by_aead"],
        ])
    res.files.append(ctx.write_csv("sop3/attack_matrix.csv",
                                   ["attack", "description", "layer", "trials", "stopped", "rate"], [row[:6] for row in table_rows]))
    res.tables.append(Table(
        f"Attack matrix ({trials} seeded trials per attack)",
        ["Attack", "Fault injected", "Stopped by", "Trials", "Stopped", "Detection rate (95% lower bound)",
         "Authentic frames accepted by AEAD"], table_rows, "measured",
        note="Layers: gateway = ledger state + SHA-256 vs golden hash; frame = per-block AES-CCM tag; image = "
             "end-of-transfer image digest (esp_ota_end), modelled here as the SHA-256 of the rebuilt image.",
    ))
    layer_counts: dict[str, int] = {}
    for r in rows:
        for k, v in r["layers"].items():
            layer_counts[k] = layer_counts.get(k, 0) + v
    lo_all, _ = wilson_interval(stopped, total)
    res.claims.append(
        f"[measured] {stopped}/{total} injected faults ({len(ATTACKS)} attack types x {trials} seeded trials) were "
        f"stopped (detection rate ≥ {lo_all:.1%} at 95% confidence): gateway layer {layer_counts.get('gateway', 0)}, "
        f"per-block AEAD layer {layer_counts.get('frame', 0)}, end-of-transfer image digest {layer_counts.get('image', 0)}."
    )
    replay = [r for r in rows if r["key"] in ("replay", "reorder")]
    if replay and all(r["authentic_frames_accepted_by_aead"] == r["trials"] for r in replay):
        res.notes.append(
            "Finding: a replayed or reordered AUTHENTIC block passes the per-block AES-CCM check "
            f"({sum(r['authentic_frames_accepted_by_aead'] for r in replay)}/{sum(r['trials'] for r in replay)}): "
            "the nonce travels inside the frame and the current framing does not bind a block to its release or "
            "position. These faults are stopped only by the end-of-transfer image digest. Real OSCORE sequence "
            "numbers with a replay window (SOP 2) would stop them at the frame layer."
        )
    if stopped != total:
        failures.append(f"{total - stopped} injected fault(s) were NOT stopped")

    # ---- C. live chain + gateway ----------------------------------------------
    if not chain:
        skipped.append("live chain part: --no-chain")
    else:
        try:
            live = run_chain_phase(ctx, trials, live_trials, n_latency, hardhat_port)
            res.files.append(ctx.write_json("sop3/live_chain.json", live))
            res.files += ["raw/hardhat-node.log", "raw/gateway.log"]

            u = live["unauthorized"]
            u_total = sum(u["stopped"].values())
            u_trials = u["trials"] * 3
            wh = live["wrong_hash"]
            wh_ok = sum(1 for x in wh if x["refused"])
            res.tables.append(Table(
                "Live chain: calls the contract / gateway must refuse",
                ["Scenario", "Trials", "Refused", "Result"],
                [["Outsider proposes / approves / revokes", u_trials, u_total,
                  "release untouched" if u["state_untouched"] else "STATE CHANGED"],
                 ["Approved release whose on-chain hash does not match the payload", len(wh), wh_ok,
                  "never staged; /version answers 4.01" if wh_ok == len(wh) else "see live_chain.json"]],
                "measured"))
            res.claims.append(
                f"[measured, local chain] {u_total}/{u_trials} state-changing calls by a non-developer were rejected by the "
                f"contract, and {wh_ok}/{len(wh)} releases whose anchored hash did not match the payload were refused by the "
                "gateway (never staged, /version stayed 4.01)."
            )
            if u_total != u_trials or not u["state_untouched"] or wh_ok != len(wh):
                failures.append("a live-chain refusal did not hold")

            ok = [t for t in live["revoke"] if t["ok"]]
            bad = [t for t in live["revoke"] if not t["ok"]]
            poll = poll_interval_s()
            if ok:
                chain_s = summarize([t["chain_ms"] for t in ok])
                halt_s = summarize([t["halt_ms"] for t in ok])
                det = [t["detect_ms"] for t in ok if t["detect_ms"] is not None]
                lat_rows = [["Chain confirmation (tx sent → receipt)", *_row(chain_s)]]
                if det:
                    lat_rows.append(["Gateway detection (receipt → KILL SWITCH event)", *_row(summarize(det))])
                lat_rows.append(["Distribution halted (tx sent → first 4.03 answer)", *_row(halt_s)])
                res.tables.append(Table(
                    f"Revoke-to-halt latency on a local chain (n={len(ok)} revokes)",
                    ["Stage", "Mean ± 95% CI (ms)", "Median", "p95", "Min", "Max"], lat_rows, "measured",
                    note=f"The revoke is sent at a seeded random point of the gateway's {poll} s poll cycle (uniform phase), so "
                         f"detection is expected to be spread between 0 and {poll} s. A local Hardhat node mines instantly, so "
                         "chain confirmation understates a real network.",
                ))
                gas_rows = []
                for name, key in (("proposeRelease", "gas_propose"), ("approveRelease (promotes to live)", "gas_approve"),
                                  ("revokeRelease", "gas_revoke")):
                    vals = [t[key] for t in live["revoke"] if t.get(key)]
                    if vals:
                        s = summarize(vals)
                        gas_rows.append([name, f"{s['mean']:,.0f}", f"{s['min']:,.0f}", f"{s['max']:,.0f}", s["n"]])
                res.tables.append(Table(
                    "Gas per call", ["Call", "Mean gas", "Min", "Max", "n"], gas_rows, "measured",
                    note="The first proposal of a version writes fresh storage and costs more; re-proposals after a "
                         "revoke reuse the slots (the max is the first proposal)."))
                res.claims.append(
                    f"[measured, local chain] After a revoke transaction was sent, the gateway stopped distributing the release "
                    f"(destroyed its blocks and answered 4.03 to devices) in a median of {halt_s['median'] / 1000:.2f} s "
                    f"(p95 {halt_s['p95'] / 1000:.2f} s, max {halt_s['max'] / 1000:.2f} s, n={len(ok)}; revokes sent at a random point of the "
                    f"gateway's {poll} s poll cycle, so the worst case is about {poll} s plus processing). "
                    f"Blocks left on disk after the halt: {sum(t['blocks_left'] for t in ok)}."
                )
                if any(t["blocks_left"] for t in ok):
                    failures.append("blocks remained on disk after a revoke")
            if bad:
                failures.append(f"{len(bad)}/{len(live['revoke'])} revoke trials failed: {bad[0].get('error')}")
        except ChainUnavailable as e:
            skipped.append(f"live chain part: {e}")

    res.notes.append(
        "Not measured here (needs the ESP32, a hardware step): the device's own rollback after a revoke "
        "([Revoke] ... Rolled back) and its refusal of tampered blocks on real flash."
    )
    for s in skipped:
        res.notes.append(f"SKIPPED - {s}")
    if failures:
        res.status, res.reason = "failed", "; ".join(failures)
    elif skipped:
        res.reason = "partial: " + "; ".join(skipped)
    return res


def _row(s: dict) -> list[str]:
    ci = f" ± {s['ci95']:.1f}" if s["ci95"] is not None else ""
    return [f"{s['mean']:.1f}{ci}", f"{s['median']:.1f}", f"{s['p95']:.1f}", f"{s['min']:.1f}", f"{s['max']:.1f}"]
