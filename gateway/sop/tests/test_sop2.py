import tempfile
import unittest
from pathlib import Path

from sop import sop2
from sop.runlog import RunContext, StepResult
from sop.tests.test_serial import LOG


class MicrobenchTests(unittest.TestCase):
    def test_aead_bench_reports_all_three_operations(self):
        b = sop2.bench_aead(60)
        for k in ("seal_us", "open_us", "key_schedule_us"):
            self.assertGreater(b[k]["mean"], 0)
        self.assertEqual(b["seal_us"]["n"], 60)
        self.assertEqual(b["frame_overhead_bytes"], 29)

    def test_a_complete_tls12_handshake_is_measured_with_exact_bytes(self):
        c, s = sop2._contexts()
        one = sop2.tls_handshake_once(c, s)
        self.assertEqual(one["version"], "TLSv1.2")
        self.assertEqual(one["cipher"], "ECDHE-ECDSA-AES128-GCM-SHA256")
        self.assertGreaterEqual(one["flights"], 3)
        self.assertGreater(one["bytes_s2c"], one["bytes_c2s"])      # certificate comes from the server
        self.assertGreater(one["bytes_c2s"] + one["bytes_s2c"], 500)
        self.assertGreater(one["total_ms"], one["client_ms"] > 0 and 0)

    def test_handshake_bench_summarises_repeats(self):
        h = sop2.bench_handshake(4)
        self.assertEqual(h["n"], 4)
        self.assertEqual(h["total_ms"]["n"], 4)
        self.assertEqual(h["version"], "TLSv1.2")

    def test_stream_falls_back_to_random_data_without_the_real_pair(self):
        chunks, label = sop2._stream_chunks(base="/no/such/base", target="/no/such/target")
        self.assertEqual(len(chunks), 24)
        self.assertIn("not found", label)
        b = sop2.bench_stream(chunks, repeats=3)
        self.assertEqual(b["blocks"], 24)


class StepTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ctx = RunContext(Path(self._tmp.name) / "run")

    def tearDown(self):
        self._tmp.cleanup()

    def run_step(self, **kw):
        return sop2.run(self.ctx, ops=40, handshakes=3, base="/no/such/base", target="/no/such/target", **kw)

    def test_gateway_numbers_always_and_device_side_is_skipped_when_absent(self):
        r = self.run_step()
        self.assertEqual(r.status, "ok")
        self.assertEqual(self.ctx.meta["oscore_mode"], "emulated")
        self.assertIn("29 B", r.claims[0])
        self.assertTrue(any("SKIPPED - device side" in n for n in r.notes))
        self.assertTrue(any("Do not claim RFC 8613 compliance" in n for n in r.notes))
        kinds = {t.caption.split(":")[0].split(" (")[0]: t.kind for t in r.tables}
        self.assertEqual(sum(t.kind == "cited" for t in r.tables), 1)
        self.assertEqual(sum(t.kind == "modelled" for t in r.tables), 1)

    def test_our_row_is_measured_overhead_and_the_others_are_labelled_cited(self):
        r = self.run_step()
        table = next(t for t in r.tables if t.caption.startswith("Per-message overhead"))
        self.assertIn("measured", table.rows[0][-1])
        for row in table.rows[1:]:
            self.assertTrue(row[-1].startswith("cited"), row)

    def test_device_log_and_sop4_hardware_data_produce_the_esp32_claim(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "factory.log"
            p.write_text(LOG + "[+20.0] [MEM] phase=stream-start free=200000 min=180000\n"
                               "[+21.0] [MEM] phase=stream-end free=150000 min=120000\n", encoding="utf-8")
            self.ctx.save(StepResult(sop="SOP4", title="x", data={
                "engine": {"flash": 1873, "ram": 3260, "symbols": 10},
                "web3_hw": {"peak_heap_bytes": 70000, "peak_exact": True, "runs_ok": 4,
                            "tls_connect_ms": {"n": 4, "mean": 2100.0, "sd": 100.0, "min": 2000.0, "max": 2200.0,
                                               "median": 2100.0, "p95": 2190.0, "ci95": 150.0}}}))
            r = self.run_step(factory_log=str(p))
        esp = next(c for c in r.claims if "ESP32" in c)
        self.assertIn("3,069 µs", esp)
        self.assertIn("2,100 ms", esp)
        self.assertIn("70,000 B of heap", esp)
        dev = next(t for t in r.tables if t.caption == "Device side (ESP32)")
        flat = " ".join(" ".join(map(str, row)) for row in dev.rows)
        self.assertIn("60,000 B", flat)                    # stream peak heap, class2 definition
        self.assertIn("3,260 B", flat)
        self.assertFalse(any("SKIPPED - device side" in n for n in r.notes))


if __name__ == "__main__":
    unittest.main()
