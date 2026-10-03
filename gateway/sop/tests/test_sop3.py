import json
import random
import tempfile
import unittest
from pathlib import Path

from sop import coap_probe
from sop.attacks import ATTACKS, Corpus, run_matrix, run_trial
from sop.chain import version32
from sop.sop3 import parse_mocha_report
from sop.stats import wilson_interval


class WilsonTests(unittest.TestCase):
    def test_all_successes_is_not_reported_as_exactly_certain(self):
        lo, hi = wilson_interval(30, 30)
        self.assertAlmostEqual(lo, 0.886, places=3)
        self.assertAlmostEqual(hi, 1.0, places=3)

    def test_zero_successes_and_validation(self):
        lo, hi = wilson_interval(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.2)
        with self.assertRaises(ValueError):
            wilson_interval(1, 0)
        with self.assertRaises(ValueError):
            wilson_interval(11, 10)

    def test_more_trials_tighten_the_bound(self):
        self.assertGreater(wilson_interval(300, 300)[0], wilson_interval(30, 30)[0])


class CoapProbeTests(unittest.TestCase):
    def test_get_version_packet_layout(self):
        pkt = coap_probe.build_get("version", 0x1234)
        self.assertEqual(pkt[:4], bytes([0x40, 0x01, 0x12, 0x34]))      # CON GET, MID
        self.assertEqual(pkt[4], (11 << 4) | 7)                          # Uri-Path, len 7
        self.assertEqual(pkt[5:], b"version")

    def test_query_option_uses_delta_4(self):
        pkt = coap_probe.build_get("patch", 1, "b=7")
        self.assertEqual(pkt[4:10], bytes([(11 << 4) | 5]) + b"patch")
        self.assertEqual(pkt[10:], bytes([(4 << 4) | 3]) + b"b=7")

    def test_parse_replies(self):
        self.assertEqual(coap_probe.parse_response(bytes([0x60, 0x83, 0, 1, 0xFF]) + b"v1.1"), ("4.03", b"v1.1"))
        self.assertEqual(coap_probe.parse_response(bytes([0x60, 0x81, 0, 1])), ("4.01", b""))
        self.assertEqual(coap_probe.parse_response(bytes([0x60, 0x45, 0, 1, 0xFF]) + b"v1.1"), ("2.05", b"v1.1"))
        with self.assertRaises(ValueError):
            coap_probe.parse_response(b"\x60\x45")

    def test_option_too_long_is_refused(self):
        with self.assertRaises(ValueError):
            coap_probe.build_get("x" * 13, 1)


class MochaParserTests(unittest.TestCase):
    def test_parses_passes_failures_and_suite_names(self):
        report = {
            "stats": {"tests": 2, "passes": 1, "failures": 1, "duration": 42},
            "passes": [{"title": "goes live", "fullTitle": "Contract approving goes live", "duration": 3}],
            "failures": [{"title": "double vote", "fullTitle": "Contract approving double vote", "duration": 2,
                          "err": {"message": "boom"}}],
        }
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.json"
            p.write_text(json.dumps(report), encoding="utf-8")
            r = parse_mocha_report(p)
        self.assertEqual((r["tests"], r["passes"], r["failures"]), (2, 1, 1))
        self.assertEqual({c["suite"] for c in r["cases"]}, {"Contract approving"})
        self.assertEqual([c["error"] for c in r["cases"] if not c["ok"]], ["boom"])


class AttackMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = {r["key"]: r for r in run_matrix(trials=8)}

    def test_every_attack_is_stopped_by_the_expected_layer(self):
        for a in ATTACKS:
            r = self.rows[a.key]
            self.assertEqual(r["stopped"], r["trials"], a.key)
            self.assertEqual(set(r["layers"]), {a.expected_layer}, a.key)

    def test_authentic_replays_pass_the_frame_check(self):
        for key in ("replay", "reorder"):
            self.assertEqual(self.rows[key]["authentic_frames_accepted_by_aead"], 8)
        self.assertEqual(self.rows["bitflip"]["authentic_frames_accepted_by_aead"], 0)

    def test_trials_are_reproducible_for_a_seed(self):
        a = run_matrix(trials=4, seed=5)
        b = run_matrix(trials=4, seed=5)
        self.assertEqual(a, b)

    def test_a_good_release_is_accepted_so_the_checks_are_not_trivially_failing(self):
        c = Corpus(seed=1)
        try:
            self.assertTrue(c.gateway_accepts(c.good_ledger(), c.path))
            self.assertTrue(c.image_ok([Corpus.frame_decrypts(f) for f in c.frames]))
            self.assertIsNotNone(Corpus.frame_decrypts(c.frames[0]))
        finally:
            c.close()

    def test_unknown_attack_is_an_error(self):
        c = Corpus(seed=1)
        try:
            from sop.attacks import Attack
            with self.assertRaises(ValueError):
                run_trial(Attack("nope", "x", "x", "gateway"), c, random.Random(1))
        finally:
            c.close()


class ChainHelperTests(unittest.TestCase):
    def test_version_is_a_zero_padded_bytes32(self):
        v = version32("v1.1")
        self.assertEqual(len(v), 32)
        self.assertEqual(v[:4], b"v1.1")
        self.assertEqual(v[4:], b"\0" * 28)


if __name__ == "__main__":
    unittest.main()
