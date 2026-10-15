"""Opt-in gateway telemetry for Table 3 of the experiment paper (Instrument 3).

Off unless DELTA_METRICS=1. When on, the gateway records, per release it stages:

  poll_ms          mean duration of one contract read (latest-version query or release query)
                   since the previous release          (paper: "Web3 Smart Contract Polling")
  sha_ms           SHA-256 of the downloaded patch      (paper: "Local SHA-256 Hash Execution")
  encap_ms         AES-CCM encapsulation of the stream  (paper: "AES-CCM Encapsulation")
  peak_rss_mb      peak resident memory of the gateway process, detect -> staged  (psutil)
  peak_cpu_pct     peak CPU of the gateway process over the same window, as a share of total
                   CPU capacity (0-100), sampled every 50 ms                      (psutil)
  also: download_ms, to_dota_ms, blocks, payload_bytes, stream_bytes (kept for the raw data)

Timing uses pyperf's clock (pyperf.perf_counter) when pyperf is installed, with the garbage
collector switched off during each synchronous timed span; the first cycles of a campaign are
warm-up and are discarded by the caller. Nothing here influences a gateway decision.

The file is written atomically next to gateway_status.json (gateway_metrics.json) and served by
the artifact server, so a controller on another machine reads it over HTTP.
"""
from __future__ import annotations

import gc
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

try:
    from pyperf import perf_counter as _default_clock
    CLOCK_NAME = "pyperf.perf_counter"
except Exception:                                   # pyperf not installed: the stdlib clock is the same call
    from time import perf_counter as _default_clock
    CLOCK_NAME = "time.perf_counter"

try:
    import psutil
except Exception:
    psutil = None

SAMPLE_S = 0.05
KEEP_RELEASES = 500
KEEP_POLLS = 2000


class NullMetrics:
    """What the gateway uses when telemetry is off: every call is a no-op."""
    enabled = False

    @contextmanager
    def span(self, name, gc_off=True):
        yield

    async def timed(self, name, awaitable):
        return await awaitable

    def window_begin(self):
        pass

    def finish_release(self, tag, **info):
        pass


class GatewayMetrics:
    enabled = True

    def __init__(self, path: Path, clock=_default_clock, sample_s: float = SAMPLE_S, sampler: bool = True):
        self.path = Path(path)
        self.clock = clock
        self.sample_s = sample_s
        self._lock = threading.Lock()
        self._polls: list[float] = []            # ms, since the previous release
        self._poll_log: list[dict] = []
        self._cur: dict[str, float] = {}
        self._t_detected: float | None = None
        self._window_open = False
        self._peak_rss = self._peak_cpu = None
        self._releases: list[dict] = []
        self._seq = 0
        self._proc = psutil.Process() if psutil else None
        self._cpus = (psutil.cpu_count() or 1) if psutil else 1
        if self._proc:
            self._proc.cpu_percent(None)         # prime: the first reading is always 0
        self._stop = threading.Event()
        if sampler and self._proc:
            threading.Thread(target=self._sample_loop, daemon=True, name="delta-metrics").start()

    @classmethod
    def from_env(cls):
        if os.environ.get("DELTA_METRICS") != "1":
            return NullMetrics()
        from gateway_config import metrics_path      # bare sibling import, as the rest of the runtime
        return cls(metrics_path())

    # -- sampler -------------------------------------------------------------------------
    def _sample_once(self) -> None:
        rss = self._proc.memory_info().rss / (1024 * 1024)
        cpu = self._proc.cpu_percent(None) / self._cpus
        with self._lock:
            if self._window_open:
                self._peak_rss = rss if self._peak_rss is None else max(self._peak_rss, rss)
                self._peak_cpu = cpu if self._peak_cpu is None else max(self._peak_cpu, cpu)

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.sample_s):
            try:
                self._sample_once()
            except Exception:
                pass

    def close(self) -> None:
        self._stop.set()

    # -- measurements --------------------------------------------------------------------
    @contextmanager
    def span(self, name: str, gc_off: bool = True):
        """Time a synchronous block, in ms, added to the current release under `name`."""
        was_on = gc.isenabled()
        if gc_off and was_on:
            gc.disable()
        t0 = self.clock()
        try:
            yield
        finally:
            ms = (self.clock() - t0) * 1000.0
            if gc_off and was_on:
                gc.enable()
            with self._lock:
                self._cur[name] = self._cur.get(name, 0.0) + ms

    async def timed(self, name: str, awaitable):
        """Time an awaitable. `poll` is kept as an individual sample; anything else is added to the current release."""
        t0 = self.clock()
        try:
            return await awaitable
        finally:
            ms = (self.clock() - t0) * 1000.0
            with self._lock:
                if name == "poll":
                    self._polls.append(ms)
                    self._poll_log.append({"t": time.time(), "ms": ms})
                    del self._poll_log[:-KEEP_POLLS]
                else:
                    self._cur[name] = self._cur.get(name, 0.0) + ms

    def window_begin(self) -> None:
        """A live release was just detected: start the per-release window."""
        with self._lock:
            self._cur = {}
            self._t_detected = time.time()
            self._window_open = True
            self._peak_rss = self._peak_cpu = None
        if self._proc:
            try:
                self._sample_once()
            except Exception:
                pass

    def finish_release(self, tag: str, **info) -> dict:
        """The release is staged: close the window, store its record, write the file."""
        if self._proc:
            try:
                self._sample_once()
            except Exception:
                pass
        with self._lock:
            self._window_open = False
            self._seq += 1
            polls = list(self._polls)
            self._polls.clear()
            rec = {
                "seq": self._seq, "tag": tag,
                "t_detected": self._t_detected, "t_staged": time.time(),
                "poll_ms": (sum(polls) / len(polls)) if polls else None, "poll_n": len(polls),
                "download_ms": self._cur.get("download"), "sha_ms": self._cur.get("sha"),
                "to_dota_ms": self._cur.get("to_dota"), "encap_ms": self._cur.get("encap"),
                "peak_rss_mb": self._peak_rss, "peak_cpu_pct": self._peak_cpu,
                **info,
            }
            self._releases.append(rec)
            del self._releases[:-KEEP_RELEASES]
            doc = {"schema": 1, "clock": CLOCK_NAME, "psutil": bool(self._proc), "cpu_count": self._cpus,
                   "releases": list(self._releases), "polls": list(self._poll_log[-200:])}
        self._write(doc)
        return rec

    def _write(self, doc: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass                                    # telemetry must never break the gateway
