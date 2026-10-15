import tempfile
import unittest
from collections import Counter
from pathlib import Path

from sop import campaign as cp


def row(scenario, trial, status="ok", warmup=False, **kw):
    return {"scenario": scenario, "trial": trial, "warmup": warmup, "status": status, **kw}


class ScheduleTests(unittest.TestCase):
    def test_every_scenario_gets_the_requested_trials_plus_warmups(self):
        slots = cp.make_schedule(trials=60, warmup=3)
        counts = Counter((s.scenario, s.warmup) for s in slots)
        for sc in cp.PAIRED:
            self.assertEqual(counts[(sc, False)], 60)
            self.assertEqual(counts[(sc, True)], 3)
        for sc in cp.DETERMINISTIC:
            self.assertEqual(counts[(sc, False)], 60)
            self.assertEqual(counts[(sc, True)], 0)

    def test_paired_scenarios_run_once_per_round_in_a_shuffled_order(self):
        slots = cp.make_schedule(trials=20, warmup=2)
        rounds = {}
        for s in slots:
            if s.scenario in cp.PAIRED:
                rounds.setdefault(s.round, []).append(s)
        self.assertEqual(len(rounds), 22)
        orders = set()
        for blocks in rounds.values():
            self.assertEqual(sorted(b.scenario for b in blocks), sorted(cp.PAIRED))
            self.assertEqual({b.trial for b in blocks}, {blocks[0].trial})        # same trial index inside a round
            orders.add(tuple(b.scenario for b in blocks))
        self.assertGreater(len(orders), 1)                                       # the order is not fixed

    def test_trial_numbers_start_after_the_warmups(self):
        slots = [s for s in cp.make_schedule(trials=5, warmup=2) if s.scenario == "A"]
        self.assertEqual([(s.trial, s.warmup) for s in slots], [(1, True), (2, True), (1, False), (2, False), (3, False), (4, False), (5, False)])

    def test_schedule_is_reproducible_for_a_seed_and_differs_across_seeds(self):
        a = cp.make_schedule(seed=1)
        self.assertEqual(a, cp.make_schedule(seed=1))
        self.assertNotEqual(a, cp.make_schedule(seed=2))

    def test_a_subset_of_scenarios(self):
        slots = cp.make_schedule(trials=4, warmup=1, scenarios=("A", "C"))
        self.assertEqual({s.scenario for s in slots}, {"A", "C"})


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = cp.TrialStore(Path(self._tmp.name) / "trials.csv")

    def tearDown(self):
        self._tmp.cleanup()

    def test_append_writes_a_header_once_and_rows_round_trip(self):
        self.store.append(row("A", 1, ttc_ms=5200))
        self.store.append(row("B", 1, ttc_ms=36100))
        text = self.store.path.read_text(encoding="utf-8")
        self.assertEqual(text.count("scenario,trial"), 1)
        self.assertEqual([r["scenario"] for r in self.store.rows()], ["A", "B"])

    def test_unknown_fields_and_statuses_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.append(row("A", 1, bogus=1))
        with self.assertRaises(ValueError):
            self.store.append(row("A", 1, status="great"))

    def test_resume_skips_finished_trials_but_reruns_invalid_ones(self):
        schedule = cp.make_schedule(trials=2, warmup=0, scenarios=("A", "B"))
        self.store.append(row("A", 1, status="ok"))
        self.store.append(row("B", 1, status="invalid"))               # harness fault: must run again
        self.store.append(row("A", 2, status="failed"))                # the system failed: it counts, not re-run
        left = {(s.scenario, s.trial) for s in self.store.remaining(schedule)}
        self.assertEqual(left, {("B", 1), ("B", 2)})

    def test_warmup_and_real_trials_with_the_same_number_are_different(self):
        self.store.append(row("A", 1, warmup=True))
        self.assertEqual(self.store.done(), {("A", 1, True)})
        schedule = cp.make_schedule(trials=1, warmup=1, scenarios=("A",))
        self.assertEqual([(s.trial, s.warmup) for s in self.store.remaining(schedule)], [(1, False)])


class PairingTests(unittest.TestCase):
    def test_pairs_are_matched_by_trial_and_exclude_warmups_and_invalid_rows(self):
        rows = [
            row("A", 1, ttc_ms=10), row("B", 1, ttc_ms=40),
            row("A", 2, ttc_ms=11), row("B", 2, status="invalid", ttc_ms=99),
            row("A", 3, ttc_ms=12), row("B", 3, ttc_ms=43),
            row("A", 1, warmup=True, ttc_ms=500), row("B", 1, warmup=True, ttc_ms=900),
        ]
        a, b, dropped = cp.paired_values([{k: str(v) for k, v in r.items()} for r in rows], "A", "B", "ttc_ms")
        self.assertEqual((a, b, dropped), ([10.0, 12.0], [40.0, 43.0], 1))

    def test_truthy_accepts_any_spelling_a_spreadsheet_may_write(self):
        for v in ("True", "TRUE", "true", " 1 ", "yes", True):
            self.assertTrue(cp.truthy(v), v)
        for v in ("False", "FALSE", "", "0", None, False):
            self.assertFalse(cp.truthy(v), v)

    def test_outcome_counts_for_a_deterministic_scenario(self):
        rows = [{k: str(v) for k, v in r.items()} for r in
                [row("C", 1, rejected=True), row("C", 2, rejected=True), row("C", 3, rejected=False),
                 row("C", 4, status="invalid", rejected=True), row("C", 1, warmup=True, rejected=True)]]
        self.assertEqual(cp.outcome_counts(rows, "C"), {"trials": 3, "rejected": 2, "failures": 1})


if __name__ == "__main__":
    unittest.main()
