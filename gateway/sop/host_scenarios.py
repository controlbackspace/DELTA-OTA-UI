"""Scenarios C, D and E of the 60-cycle campaign: the deterministic security checks.

They need no ESP32. Each runs the real gateway process against a fresh local Hardhat chain
and asks one yes/no question per trial:

  C  Tampered patch      A patch altered by one byte (seeded position and bit) is served at the
                         anchored URL. The gateway must refuse it, answer 4.01 and hold no blocks.
  D  Kill switch         A staged release is revoked at a random point of the gateway's poll
                         cycle. The gateway must answer 4.03, refuse a block request (4.01) and
                         hold no blocks; the revocation propagation delay is recorded.
  E  Incomplete          A release with one of the two required signatures is proposed. The gateway
     signatures          must never stage it, a second signature by the proposer and a signature by
                         an outsider must both revert, and the release must stay pending.

The decision rules are pure functions (judge_*), tested without hardware. A trial is `invalid`
when the harness could not set the test up (a transaction failed, the gateway never reached the
point being tested); it is run again, never counted as a pass. `failed` means the system under
test did the wrong thing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import random
import time
from pathlib import Path

from .campaign import TrialStore, Slot, make_schedule
from .chain import Chain, ChainUnavailable, HardhatNode
from .coap_probe import probe
from .gateway_proc import COAP_HOST, COAP_PORT, GatewayProc, poll_interval_s
from .runlog import RunContext

MAX_ATTEMPTS = 3        # tries per trial when the harness (not the system) fails


# ---------------------------------------------------------------- decision rules (pure)
def judge_tamper(verdict: bool, staged: bool, version_reply: str | None, blocks: int) -> tuple[str, bool, str]:
    """(status, rejected, note) for Scenario C."""
    if staged or blocks > 0 or version_reply not in (None, "4.01"):
        return "failed", False, f"tampered patch was accepted (staged={staged}, blocks={blocks}, /version={version_reply})"
    if not verdict:
        return "invalid", False, "the gateway gave no hash verdict for this release in time"
    if version_reply != "4.01":
        return "invalid", False, "no answer from the gateway's /version"
    return "ok", True, "hash mismatch detected, nothing staged"


def judge_kill(setup_ok: bool, halt_seen: bool, patch_reply: str | None, blocks_left: int) -> tuple[str, bool, str]:
    """(status, rejected, note) for Scenario D."""
    if not setup_ok:
        return "invalid", False, "the release could not be staged before the revoke"
    if not halt_seen:
        return "failed", False, "the gateway never answered 4.03 after the revoke"
    if patch_reply != "4.01" or blocks_left > 0:
        return "failed", False, f"revoked release still served (/patch={patch_reply}, blocks={blocks_left})"
    return "ok", True, "4.03 on /version, block request refused, no blocks held"


def judge_incomplete(setup_ok: bool, breached: str, duplicate_reverted: bool, outsider_reverted: bool,
                     still_pending: bool) -> tuple[str, bool, str]:
    """(status, rejected, note) for Scenario E."""
    if not setup_ok:
        return "invalid", False, "the proposal transaction failed"
    problems = []
    if breached:
        problems.append(f"gateway {breached}")
    if not duplicate_reverted:
        problems.append("a second signature by the proposer was accepted")
    if not outsider_reverted:
        problems.append("a signature by an outsider was accepted")
    if not still_pending:
        problems.append("the release left the pending state")
    if problems:
        return "failed", False, "; ".join(problems)
    return "ok", True, "never staged, extra signatures reverted, release stayed pending"


# ---------------------------------------------------------------- test bench
def load_patch(firmware_dir: str | None = None) -> tuple[bytes, str]:
    """A real BSDIFF40 patch (app v1.0 -> v1.1) when the images exist, else a seeded synthetic payload."""
    from . import sop1
    pair = sop1.find_real_pair(firmware_dir)
    if pair:
        import bsdiff4
        return bsdiff4.diff(pair[0].read_bytes(), pair[1].read_bytes()), f"real patch {pair[0].name} -> {pair[1].name}"
    return random.Random(7).randbytes(8192), "synthetic 8 KiB payload (release images not found)"


class HostBench:
    """One fresh Hardhat node, one deployed contract and one real gateway process."""

    def __init__(self, ctx: RunContext, patch: bytes, label: str, port: int, name: str):
        self.ctx, self.patch, self.label, self.port, self.name = ctx, patch, label, port, name
        self.good_hex = hashlib.sha256(patch).hexdigest()
        self.node = self.chain = self.gw = None
        self.work = ctx.sub(f"work_campaign_{name}")
        (self.work / "patch.bin").write_bytes(patch)
        self.url = (self.work / "patch.bin").resolve().as_uri()

    def __enter__(self):
        if not GatewayProc.port_free():
            raise ChainUnavailable(f"UDP {COAP_PORT} is in use (a gateway is running?) - stop it and re-run")
        raw = self.ctx.sub("raw")
        self.node = HardhatNode(self.port, raw / f"campaign-{self.name}-node.log")
        self.node.start()
        self.chain = Chain(self.node.url)
        addr = self.chain.deploy()
        self.gw = GatewayProc(self.node.url, addr, self.work, raw / f"campaign-{self.name}-gateway.log")
        self.gw.start()
        ready, _ = self.gw.wait_for(lambda s: s.get("gateway_state") == "waiting", 90)
        if not ready:
            raise ChainUnavailable("gateway did not reach 'waiting' - see raw/campaign-*-gateway.log")
        return self

    def __exit__(self, *exc):
        if self.gw:
            self.gw.stop()
        if self.node:
            self.node.stop()

    # -- one trial per scenario; each returns the campaign row fields
    def trial_c(self, slot: Slot, rng: random.Random) -> dict:
        tag = f"v9.{slot.trial}"
        pos, bit = rng.randrange(len(self.patch)), 1 << rng.randrange(8)
        bad = bytearray(self.patch)
        bad[pos] ^= bit
        path = self.work / f"tampered_{slot.trial}.bin"
        path.write_bytes(bytes(bad))
        last = max((e["id"] for e in self.gw.status().get("events", [])), default=0)
        p = self.chain.propose(tag, self.good_hex, path.resolve().as_uri(), 0)
        a = self.chain.approve(tag, 1)
        if not (p.ok and a.ok):
            return {"status": "invalid", "rejected": False, "note": f"setup tx failed: {p.error or a.error}"}
        verdict, st = self.gw.wait_for(
            lambda s: any(e["id"] > last and e["msg"].startswith(f"{tag}: downloaded bytes do not match")
                          for e in s.get("events", [])), timeout=45)
        code, _, _ = probe(COAP_HOST, COAP_PORT, "version")
        staged = bool(st.get("staged_version")) or self.gw.block_files() > 0
        status, rejected, note = judge_tamper(bool(verdict), staged, code, self.gw.block_files())
        return {"status": status, "rejected": rejected, "note": f"{note}; byte {pos} bit {bit:#04x}",
                "delay_ms": round((time.time() - a.t_mined) * 1000) if verdict else ""}

    def trial_d(self, slot: Slot, rng: random.Random) -> dict:
        tag, poll = "v1.1", poll_interval_s() or 5
        p = self.chain.propose(tag, self.good_hex, self.url, 0)
        a = self.chain.approve(tag, 1)
        staged = False
        if p.ok and a.ok:
            staged, _ = self.gw.wait_for(
                lambda s: s.get("gateway_state") == "staged" and s.get("staged_version") == tag, 60)
            code, _, _ = probe(COAP_HOST, COAP_PORT, "version")
            staged = bool(staged) and code == "2.05"
        if not staged:
            return {"status": "invalid", "rejected": False, "note": "setup failed: release not staged"}
        last = max((e["id"] for e in self.gw.status().get("events", [])), default=0)
        time.sleep(rng.uniform(0, poll))                  # revoke arrives at any point of the poll cycle
        r = self.chain.revoke(tag, 2)
        t_halt, deadline = None, time.time() + 30
        while time.time() < deadline:
            code, _, _ = probe(COAP_HOST, COAP_PORT, "version", timeout=0.25)
            if code == "4.03":
                t_halt = time.time()
                break
            time.sleep(0.02)
        patch_reply, _, _ = probe(COAP_HOST, COAP_PORT, "patch", query="b=0")
        status, rejected, note = judge_kill(True, t_halt is not None, patch_reply, self.gw.block_files())
        kill = next((e for e in self.gw.status().get("events", [])
                     if e["id"] > last and e["msg"].startswith("KILL SWITCH")), None)
        out = {"status": status, "rejected": rejected, "note": note}
        if t_halt is not None:
            out["delay_ms"] = round((t_halt - r.t_sent) * 1000)
            if kill:
                out["detect_ms"] = round((kill["t"] - r.t_mined) * 1000)
        return out

    def trial_e(self, slot: Slot, rng: random.Random) -> dict:
        tag, poll = f"v8.{slot.trial}", poll_interval_s() or 5
        p = self.chain.propose(tag, self.good_hex, self.url, 0)
        if not p.ok:
            return {"status": "invalid", "rejected": False, "note": f"proposal failed: {p.error}"}
        breached, deadline = "", time.time() + poll + 2           # at least one full poll cycle plus margin
        while time.time() < deadline and not breached:
            st = self.gw.status()
            code, _, _ = probe(COAP_HOST, COAP_PORT, "version", timeout=0.25)
            if st.get("gateway_state") == "staged" or st.get("staged_version") or self.gw.block_files() > 0:
                breached = "staged an unapproved release"
            elif code not in (None, "4.01"):
                breached = f"answered /version with {code}"
            time.sleep(0.25)
        dup = self.chain.approve(tag, 0)                          # the proposer already holds signature 1
        out = self.chain.approve(tag, 3)                          # an outsider
        rel = self.chain.release(tag)
        status, rejected, note = judge_incomplete(
            True, breached, not dup.ok, not out.ok, rel["approvals"] == 1 and not rel["live"] and not rel["revoked"])
        return {"status": status, "rejected": rejected, "note": note}


TRIALS = {"C": "trial_c", "D": "trial_d", "E": "trial_e"}


def run_host(ctx: RunContext, store: TrialStore, scenarios=("C", "D", "E"), trials: int = 60, seed: int = 20261015,
             firmware_dir: str | None = None, hardhat_port: int = 18545, say=print) -> dict:
    """Run (or resume) the deterministic scenarios; returns {scenario: rows written}."""
    patch, label = load_patch(firmware_dir)
    schedule = [s for s in make_schedule(trials=trials, warmup=0, seed=seed, scenarios=tuple(scenarios))
                if s.scenario in TRIALS]
    todo = store.remaining(schedule)
    written: dict[str, int] = {}
    git = ctx.meta.get("git_commit", "")
    sha = hashlib.sha256(patch).hexdigest()
    say(f"[campaign] {len(todo)} trial(s) to run ({label}).")
    for scenario in scenarios:
        mine = [s for s in todo if s.scenario == scenario]
        if not mine:
            continue
        with HostBench(ctx, patch, label, hardhat_port, scenario.lower()) as bench:
            for slot in mine:
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    # Seeded per trial: reproducible, and a resumed run never repeats an earlier trial's choice.
                    rng = random.Random(f"{seed}-{scenario}-{slot.trial}-{attempt}")
                    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
                    res = getattr(bench, TRIALS[scenario])(slot, rng)
                    row = {"scenario": scenario, "trial": slot.trial, "warmup": False, "round": 0, "position": 0,
                           "started_utc": started, "git_revision": git, "image_sha256": sha, **res}
                    row["note"] = f"attempt {attempt}: {row.get('note', '')}"
                    store.append(row)
                    written[scenario] = written.get(scenario, 0) + 1
                    if res["status"] != "invalid":
                        break
                say(f"[campaign] {scenario} {slot.trial}/{trials}: {res['status']} - {res.get('note', '')[:80]}")
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the host-side campaign scenarios C, D and E.")
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--scenarios", default="C,D,E")
    ap.add_argument("--run", help="existing run directory (default: a new one)")
    ap.add_argument("--firmware-dir")
    ap.add_argument("--hardhat-port", type=int, default=18545)
    args = ap.parse_args(argv)
    ctx = RunContext(Path(args.run)) if args.run else RunContext.new()
    store = TrialStore(ctx.dir / "campaign" / "trials.csv")
    run_host(ctx, store, tuple(args.scenarios.split(",")), args.trials, firmware_dir=args.firmware_dir,
             hardhat_port=args.hardhat_port)
    print(f"Trials: {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
