import tempfile
import unittest
from pathlib import Path

from sop import chapter4 as c4
from sop.tests.test_chapter4 import campaign_rows

CLEAN_LOG = ("[+0.000] [App] v1.0 alive\n[+0.1] rst:0x1 (POWERON_RESET),boot:0x13\n[+6.0] [OTA] Update available: v1.0 -> v1.1\n"
             "[+6.1] [OTA] Backing up ota_0 -> ota_1 (279328 bytes)...\n")
INTERRUPTED_LOG = ("[+0.000] [OTA] Update available: v1.0 -> v1.1\n[+0.0] [OTA] Backing up ota_0 -> ota_1 (279328 bytes)...\n"
                   "[+0.2] rst:0x1 (POWERON_RESET),boot:0x13\n[+6.0] [OTA] Update available: v1.0 -> v1.1\n")
UNPROMPTED_LOG = ("[+0.000] [App] v1.0 alive\n[+0.5] [OTA] Update available: v1.0 -> v1.1\n[+0.6] [OTA] Backing up ota_0 -> ota_1\n"
                  "[+9] [Delta] Reconstructed 288880 bytes\n")


def make_raw(d: Path, spec: dict) -> Path:
    raw = d / "raw"
    raw.mkdir()
    for (sc, trial), text in spec.items():
        (raw / f"cycle-{sc}-c{trial:03d}-1.serial.log").write_text(text, encoding="utf-8")
    return raw


class InterruptionTests(unittest.TestCase):
    def test_only_an_update_followed_by_a_reset_counts_as_interrupted(self):
        self.assertTrue(c4.update_interrupted(INTERRUPTED_LOG))
        self.assertFalse(c4.update_interrupted(CLEAN_LOG))              # the update starts after the reset
        self.assertFalse(c4.update_interrupted(UNPROMPTED_LOG))         # began on its own, left alone (fixed harness)
        self.assertFalse(c4.update_interrupted(""))
        self.assertFalse(c4.update_interrupted("[+0.0] rst:0x1 (POWERON_RESET)\n"))

    def test_flags_and_outcomes_by_start_type(self):
        rows = campaign_rows(n=6, fail_a=(3,), fail_b=(), heap_missing_a=())
        with tempfile.TemporaryDirectory() as d:
            spec = {("A", t): CLEAN_LOG for t in range(1, 7)}
            spec[("A", 3)] = INTERRUPTED_LOG                                # the failed A cycle was interrupted
            spec[("B", 2)] = INTERRUPTED_LOG                                # a B cycle interrupted but completed
            spec.update({("B", t): CLEAN_LOG for t in (1, 3, 4, 5, 6)})
            raw = make_raw(Path(d), spec)
            flags = c4.interrupted_map(rows, raw)
            self.assertTrue(flags[("A", 3)] and flags[("B", 2)])
            self.assertFalse(flags[("A", 1)])
            by = c4.outcomes_by_start(rows, flags)
            self.assertEqual(by["A"]["interrupted"], {"ok": 0, "failed": 1})
            self.assertEqual(by["A"]["clean"], {"ok": 5, "failed": 0})
            self.assertEqual(by["B"]["interrupted"], {"ok": 1, "failed": 0})

    def test_failures_report_whether_each_failed_cycle_was_interrupted(self):
        rows = campaign_rows(n=6, fail_a=(3,), fail_b=(), heap_missing_a=())
        with tempfile.TemporaryDirectory() as d:
            raw = make_raw(Path(d), {("A", 3): INTERRUPTED_LOG})
            detail = c4.failures(rows, raw)["detail"]
            self.assertEqual(len(detail), 1)
            self.assertIs(detail[0]["interrupted"], True)

    def test_sensitivity_drops_pairs_with_an_interrupted_cycle(self):
        rows = campaign_rows(n=12, fail_a=(), fail_b=(), heap_missing_a=())
        pairs = c4.select_pairs(rows)
        s = c4.interruption_sensitivity(pairs, {("A", 2): True, ("B", 5): True})
        self.assertEqual((s["n_all"], s["n_clean"]), (12, 10))
        ttc = next(r for r in s["rows"] if r["metric"] == "ttc_ms")
        self.assertEqual((ttc["all"]["n"], ttc["clean"]["n"]), (12, 10))
        every = {(sc, p["trial"]): True for p in pairs for sc in "AB"}
        self.assertIsNone(c4.interruption_sensitivity(pairs, every)["rows"][0]["clean"])


if __name__ == "__main__":
    unittest.main()
