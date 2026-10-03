import math
import unittest

from sop.stats import fmt_ci, percentile, summarize, t_critical_95


class StatsTests(unittest.TestCase):
    def test_two_samples_use_the_wide_t_interval(self):
        s = summarize([1, 3])
        self.assertEqual(s["n"], 2)
        self.assertAlmostEqual(s["mean"], 2.0)
        self.assertAlmostEqual(s["sd"], math.sqrt(2))
        # t(df=1)=12.706; ci = t*sd/sqrt(n) = 12.706
        self.assertAlmostEqual(s["ci95"], 12.706, places=3)

    def test_known_sample(self):
        s = summarize([2, 4, 4, 4, 5, 5, 7, 9])
        self.assertAlmostEqual(s["mean"], 5.0)
        self.assertAlmostEqual(s["sd"], 2.13809, places=4)   # sample SD
        self.assertEqual((s["min"], s["max"]), (2.0, 9.0))
        self.assertAlmostEqual(s["median"], 4.5)

    def test_single_sample_has_no_spread_and_no_ci(self):
        s = summarize([7.5])
        self.assertEqual(s["n"], 1)
        self.assertIsNone(s["sd"])
        self.assertIsNone(s["ci95"])
        self.assertEqual(s["p95"], 7.5)

    def test_empty_input_is_refused(self):
        with self.assertRaises(ValueError):
            summarize([])

    def test_percentile_interpolates(self):
        xs = [10.0, 20.0, 30.0, 40.0, 50.0]
        self.assertAlmostEqual(percentile(xs, 0.5), 30.0)
        self.assertAlmostEqual(percentile(xs, 0.95), 48.0)
        self.assertAlmostEqual(percentile(xs, 0.0), 10.0)
        self.assertAlmostEqual(percentile(xs, 1.0), 50.0)

    def test_t_table_edges(self):
        self.assertEqual(t_critical_95(1), 12.706)
        self.assertEqual(t_critical_95(30), 2.042)
        self.assertEqual(t_critical_95(45), 2.000)
        self.assertEqual(t_critical_95(1000), 1.960)
        with self.assertRaises(ValueError):
            t_critical_95(0)

    def test_format(self):
        self.assertEqual(fmt_ci(summarize([1, 3]), 1, " ms"), "2.0 ± 12.7 ms (n=2)")
        self.assertEqual(fmt_ci(summarize([4.0]), 1, " ms"), "4.0 ms (n=1)")


if __name__ == "__main__":
    unittest.main()
