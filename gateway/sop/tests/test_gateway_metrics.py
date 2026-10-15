import asyncio
import gc
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from secureota.gateway_runtime import metrics as gm


class FakeClock:
    """perf_counter stand-in: each call advances by the next step (seconds)."""

    def __init__(self, steps):
        self.steps, self.now = list(steps), 0.0

    def __call__(self):
        if self.steps:
            self.now += self.steps.pop(0)
        return self.now


class NullTests(unittest.TestCase):
    def test_disabled_telemetry_is_inert(self):
        os.environ.pop("DELTA_METRICS", None)
        m = gm.GatewayMetrics.from_env()
        self.assertFalse(m.enabled)
        with m.span("sha"):
            pass
        self.assertEqual(asyncio.run(m.timed("poll", asyncio.sleep(0, "x"))), "x")
        m.window_begin()
        m.finish_release("v1.1", blocks=1)


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "gateway_metrics.json"

    def tearDown(self):
        self._tmp.cleanup()

    def make(self, steps=()):
        m = gm.GatewayMetrics(self.path, clock=FakeClock(steps), sampler=False)
        self.addCleanup(m.close)
        return m

    def test_a_release_record_has_the_table_3_fields(self):
        # span: 0.000 -> 0.004 s = 4 ms ; second span 0.000 -> 0.012 s = 12 ms
        m = self.make([0, 0.004, 0, 0.012])
        m.window_begin()
        with m.span("sha"):
            pass
        with m.span("encap"):
            pass
        rec = m.finish_release("v1.1", blocks=24, stream_bytes=23596, payload_bytes=22497)
        self.assertAlmostEqual(rec["sha_ms"], 4.0)
        self.assertAlmostEqual(rec["encap_ms"], 12.0)
        self.assertEqual((rec["tag"], rec["seq"], rec["blocks"]), ("v1.1", 1, 24))
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema"], 1)
        self.assertEqual(doc["releases"][0]["tag"], "v1.1")
        self.assertIn(doc["clock"], ("pyperf.perf_counter", "time.perf_counter"))

    def test_polling_is_the_mean_of_the_samples_since_the_previous_release(self):
        m = self.make([0, 0.010, 0, 0.030, 0, 0.020])
        for _ in range(3):
            asyncio.run(m.timed("poll", asyncio.sleep(0)))
        m.window_begin()
        first = m.finish_release("v1.1")
        self.assertAlmostEqual(first["poll_ms"], 20.0)
        self.assertEqual(first["poll_n"], 3)
        m.window_begin()
        second = m.finish_release("v1.1")                          # no polls since the last release
        self.assertIsNone(second["poll_ms"])
        self.assertEqual(second["seq"], 2)

    def test_garbage_collection_is_off_during_a_span_and_restored(self):
        m = self.make([0, 0.001])
        seen = []
        gc.enable()
        with m.span("sha"):
            seen.append(gc.isenabled())
        self.assertEqual(seen, [False])
        self.assertTrue(gc.isenabled())

    def test_gc_is_left_alone_when_it_was_already_off(self):
        m = self.make([0, 0.001])
        gc.disable()
        try:
            with m.span("sha"):
                pass
            self.assertFalse(gc.isenabled())
        finally:
            gc.enable()

    @unittest.skipUnless(gm.psutil, "psutil not installed")
    def test_process_peaks_are_recorded_for_the_window(self):
        m = self.make([0] * 10)
        m.window_begin()
        blob = bytearray(20 * 1024 * 1024)                         # make the resident set visibly larger
        blob[::4096] = b"x" * len(blob[::4096])
        rec = m.finish_release("v1.1")
        del blob
        self.assertGreater(rec["peak_rss_mb"], 10)
        self.assertGreaterEqual(rec["peak_cpu_pct"], 0)
        self.assertLessEqual(rec["peak_cpu_pct"], 100.0 + 1e-9)

    def test_the_release_ring_is_bounded(self):
        m = self.make([0] * 5)
        for _ in range(gm.KEEP_RELEASES + 5):
            m.window_begin()
            m.finish_release("v1.1")
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(doc["releases"]), gm.KEEP_RELEASES)
        self.assertEqual(doc["releases"][-1]["seq"], gm.KEEP_RELEASES + 5)

    def test_an_unwritable_path_never_breaks_the_gateway(self):
        m = gm.GatewayMetrics(Path(self._tmp.name) / "a" / "b", clock=FakeClock([]), sampler=False)
        self.addCleanup(m.close)
        (Path(self._tmp.name) / "a").write_text("a file, not a folder", encoding="utf-8")
        m.window_begin()
        m.finish_release("v1.1")                                   # must not raise


class ServedFileTests(unittest.TestCase):
    def test_the_artifact_server_serves_the_metrics_file_and_nothing_else_new(self):
        import serve_artifacts
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "gateway_metrics.json").write_text('{"schema": 1}', encoding="utf-8")
            (d / "secret.txt").write_text("x", encoding="utf-8")
            old = {k: os.environ.get(k) for k in ("DELTA_METRICS_FILE", "DELTA_ARTIFACT_DIR")}
            os.environ["DELTA_METRICS_FILE"] = str(d / "gateway_metrics.json")
            os.environ["DELTA_ARTIFACT_DIR"] = str(d)
            srv = serve_artifacts.make_server(0)
            port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                r = urllib.request.urlopen(f"http://127.0.0.1:{port}/gateway_metrics.json")
                self.assertEqual((r.status, r.headers.get("Access-Control-Allow-Origin"), r.read()), (200, "*", b'{"schema": 1}'))
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/secret.txt")
                self.assertEqual(cm.exception.code, 404)
            finally:
                srv.shutdown()
                srv.server_close()
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
