"""Trial schedule and per-trial storage for the 60-cycle campaign (SOP 5).

Design rules taken from Chapter 3 and from the pairing the paired t-test needs:

* Scenarios A (delta, secured) and B (full binary, secured; the internal control) are
  *paired* by trial index. They run **interleaved**, one block per round, in a random order
  per round, on the same device and network, so slow drift hits both alike.
* Scenarios C (tampered patch), D (kill switch) and E (incomplete signatures) are
  deterministic checks and run sequentially, 60 trials each.
* A few warm-up rounds run first and are stored but never analysed.
* Every trial is appended to a CSV as soon as it finishes (flush + fsync), so an interrupted
  campaign resumes where it stopped. A trial is `ok`, `failed` (the system under test failed:
  it counts) or `invalid` (the harness failed, for example a serial drop: it is re-run).
"""
from __future__ import annotations

import csv
import os
import random
from dataclasses import dataclass
from pathlib import Path

PAIRED = ("A", "B")
NAKED = ("N",)                          # the naked-CoAP baseline (Chapter 3 Baseline B): interleaved with A in the same rounds
DETERMINISTIC = ("C", "D", "E")
GATEWAY_ONLY = ("T3",)                  # Table 3: gateway-only profiling cycles (no device), sequential, with warm-up
SCENARIO_TEXT = {
    "A": "Normal delta OTA update (secured)",
    "B": "Full-binary OTA update (secured): comparison baseline",
    "N": "Naked CoAP delta update (no AES-CCM, no key): Chapter 3 Baseline B for the security tax",
    "H": "HTTPS full-binary download (TLS 1.2): Chapter 3 Baseline A for Equations 3 and 4",
    "C": "Tampered patch (one byte altered)",
    "T3": "Gateway profiling cycle on the Raspberry Pi (Table 3)",
    "D": "Kill switch: a revoked release must not be served",
    "E": "Incomplete signatures: a release below the 2-of-3 threshold must not be served",
}
DONE_STATUSES = ("ok", "failed")        # `invalid` trials are run again

FIELDS = [
    "scenario", "trial", "warmup", "round", "position", "status", "note",
    "started_utc", "git_revision", "image_sha256",
    # transport and payload
    "ttc_ms", "payload_bytes", "wire_bytes", "blocks", "rssi_dbm",
    # device (from the serial log)
    "decrypt_avg_us", "decrypt_max_us", "reconstruct_us", "total_us", "heap_min_free", "heap_peak_used",
    # gateway
    "gateway_peak_rss_kb", "gateway_cpu_pct", "verify_ms",
    # deterministic scenarios
    "rejected", "delay_ms", "detect_ms",
    # Table 2 / Table 3 cells and the raw data behind them
    "static_ram_kb", "decrypt_recon_ms", "flash_kbps", "poll_ms", "sha_ms", "encap_ms", "gw_ram_mb", "gw_cpu_pct",
    "diff_ms", "to_dota_ms", "download_ms", "gas_propose", "gas_approve", "chain_ms", "stage_ms", "requests", "retransmissions",
]


@dataclass(frozen=True)
class Slot:
    scenario: str
    trial: int
    warmup: bool
    round: int
    position: int          # place inside its round, 0 for the first block run


def make_schedule(trials: int = 60, warmup: int = 3, seed: int = 20261015,
                  scenarios: tuple[str, ...] = PAIRED + DETERMINISTIC + GATEWAY_ONLY) -> list[Slot]:
    """The full ordered list of trials. Deterministic for a given seed."""
    rng = random.Random(seed)
    slots: list[Slot] = []
    paired = [s for s in scenarios if s in PAIRED or s in NAKED]
    for rnd in range(1, warmup + trials + 1):
        order = list(paired)
        rng.shuffle(order)
        is_warm = rnd <= warmup
        trial = rnd if is_warm else rnd - warmup
        for pos, scenario in enumerate(order):
            slots.append(Slot(scenario, trial, is_warm, rnd, pos))
    for scenario in (s for s in scenarios if s in DETERMINISTIC):
        for t in range(1, trials + 1):
            slots.append(Slot(scenario, t, False, 0, 0))
    for scenario in (s for s in scenarios if s in GATEWAY_ONLY):
        for rnd in range(1, warmup + trials + 1):
            is_warm = rnd <= warmup
            slots.append(Slot(scenario, rnd if is_warm else rnd - warmup, is_warm, rnd, 0))
    return slots


class TrialStore:
    """Append-only CSV of finished trials, safe to resume."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _ensure_header(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writeheader()
                f.flush()
                os.fsync(f.fileno())

    def append(self, row: dict) -> None:
        unknown = set(row) - set(FIELDS)
        if unknown:
            raise ValueError(f"unknown trial fields: {sorted(unknown)}")
        if row.get("status") not in ("ok", "failed", "invalid"):
            raise ValueError("status must be ok, failed or invalid")
        self._ensure_header()
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow({k: row.get(k, "") for k in FIELDS})
            f.flush()
            os.fsync(f.fileno())

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def done(self) -> set[tuple[str, int, bool]]:
        return {(r["scenario"], int(r["trial"]), truthy(r["warmup"]))
                for r in self.rows() if r["status"] in DONE_STATUSES}

    def remaining(self, schedule: list[Slot]) -> list[Slot]:
        finished = self.done()
        return [s for s in schedule if (s.scenario, s.trial, s.warmup) not in finished]


def truthy(value) -> bool:
    """A boolean read back from the CSV. Spreadsheet programs rewrite True/False as TRUE/FALSE, so accept any spelling."""
    return str(value).strip().lower() in ("true", "1", "yes", "y")


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def values(rows: list[dict], scenario: str, metric: str) -> dict[int, float]:
    """trial -> value for the analysed (non-warm-up, status ok) trials of one scenario."""
    out: dict[int, float] = {}
    for r in rows:
        if r["scenario"] == scenario and not truthy(r["warmup"]) and r["status"] == "ok":
            v = _num(r.get(metric))
            if v is not None:
                out[int(r["trial"])] = v
    return out


def paired_values(rows: list[dict], first: str, second: str, metric: str) -> tuple[list[float], list[float], int]:
    """Values of `metric` for two scenarios matched by trial index; returns (first, second, dropped)."""
    a, b = values(rows, first, metric), values(rows, second, metric)
    common = sorted(set(a) & set(b))
    dropped = len(set(a) | set(b)) - len(common)
    return [a[t] for t in common], [b[t] for t in common], dropped


def outcome_counts(rows: list[dict], scenario: str) -> dict:
    """Deterministic scenarios: how many of the analysed trials were rejected as required."""
    used = [r for r in rows if r["scenario"] == scenario and not truthy(r["warmup"]) and r["status"] in DONE_STATUSES]
    rejected = sum(1 for r in used if truthy(r.get("rejected")))
    return {"trials": len(used), "rejected": rejected, "failures": len(used) - rejected}
