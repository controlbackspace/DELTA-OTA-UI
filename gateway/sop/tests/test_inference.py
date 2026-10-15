import math
import unittest

from sop import inference as inf

# Reference values from scipy (ttest_rel, nct) for the same inputs.
A = [102.1, 98.4, 101.7, 99.9, 103.2, 100.5, 97.8, 101.1, 99.4, 102.6]
B = [95.0, 94.1, 96.3, 93.8, 97.9, 95.2, 94.6, 96.0, 93.5, 97.1]
REF_T, REF_P, REF_MEAN_D, REF_SD_D = 16.17493724579809, 5.850377730902796e-08, 5.320000000000002, 1.0400854665736725


class DescriptiveTests(unittest.TestCase):
    def test_mean_and_sample_sd_use_n_minus_one(self):
        xs = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        self.assertEqual(inf.mean(xs), 5.0)
        self.assertAlmostEqual(inf.sample_sd(xs), math.sqrt(32 / 7), places=12)

    def test_degenerate_inputs_are_errors(self):
        with self.assertRaises(ValueError):
            inf.mean([])
        with self.assertRaises(ValueError):
            inf.sample_sd([1.0])

    def test_relative_reduction(self):
        self.assertAlmostEqual(inf.relative_reduction_pct(100, 20), 80.0)
        self.assertAlmostEqual(inf.relative_reduction_pct(100, 130), -30.0)       # larger than the baseline
        with self.assertRaises(ValueError):
            inf.relative_reduction_pct(0, 5)

    def test_absolute_difference(self):
        r = inf.absolute_difference([12.0, 14.0, 13.0], [10.0, 11.0, 10.0])
        self.assertAlmostEqual(r["difference"], 13.0 - 31 / 3)                    # mean 13 minus mean 10.333...
        self.assertIn("sd_of_differences", r)


class PairedTTests(unittest.TestCase):
    def test_matches_the_reference_implementation(self):
        r = inf.paired_t_test(A, B)
        self.assertEqual((r["n"], r["df"]), (10, 9))
        self.assertAlmostEqual(r["t"], REF_T, places=9)
        self.assertAlmostEqual(r["mean_difference"], REF_MEAN_D, places=9)
        self.assertAlmostEqual(r["sd_of_differences"], REF_SD_D, places=9)
        self.assertAlmostEqual(r["p_two_sided"] / REF_P, 1.0, places=6)
        self.assertFalse(r["degenerate"])

    def test_a_non_significant_pair(self):
        c = [x + 0.05 * ((i % 3) - 1) for i, x in enumerate(A)]
        r = inf.paired_t_test(A, c)
        self.assertAlmostEqual(r["t"], 0.3611575592573076, places=9)
        self.assertAlmostEqual(r["p_two_sided"], 0.7263142108887258, places=9)

    def test_identical_differences_have_no_t_statistic(self):
        r = inf.paired_t_test([10, 11, 12, 13], [4, 5, 6, 7])                       # always exactly 6 apart
        self.assertTrue(r["degenerate"])
        self.assertEqual(r["mean_difference"], 6.0)
        self.assertIsNone(r["t"])
        self.assertIsNone(r["p_two_sided"])

    def test_unmatched_samples_are_rejected(self):
        with self.assertRaises(ValueError):
            inf.paired_t_test([1, 2, 3], [1, 2])

    def test_t_distribution_p_values(self):
        self.assertAlmostEqual(inf.t_two_sided_p(0.0, 5), 1.0, places=12)
        self.assertAlmostEqual(inf.t_two_sided_p(2.000995378088267, 59), 0.05, places=9)   # scipy t.ppf(0.975, 59)
        self.assertAlmostEqual(inf.t_two_sided_p(-2.000995378088267, 59), 0.05, places=9)  # symmetric


class ToleranceTests(unittest.TestCase):
    def test_exact_factor_for_the_campaign_sample_size(self):
        k, exact = inf.tolerance_factor(60)
        self.assertTrue(exact)
        self.assertEqual(k, 2.8071)

    def test_other_sizes_use_the_approximation(self):
        for n in (15, 45, 200):
            k, exact = inf.tolerance_factor(n)
            self.assertFalse(exact)
            self.assertTrue(1.5 < k < 4.5)
        # n = 31 is not tabulated; the approximation stays close to the exact n = 30 value.
        self.assertAlmostEqual(inf.tolerance_factor(31)[0], 3.0639, delta=0.06)

    def test_upper_limit_is_mean_plus_k_sd(self):
        xs = [float(i % 7) + 100.0 for i in range(60)]
        r = inf.upper_tolerance_limit(xs)
        self.assertEqual(r["n"], 60)
        self.assertAlmostEqual(r["upper_limit"], r["mean"] + 2.8071 * r["sd"], places=9)
        self.assertTrue(r["k_exact"])
        self.assertGreater(r["upper_limit"], max(xs))                              # the bound sits above every observation


class SuccessRunTests(unittest.TestCase):
    def test_sixty_failure_free_trials_give_95_4_percent(self):
        self.assertAlmostEqual(inf.success_run_confidence(0.95, 60), 0.9539, places=4)

    def test_trials_needed_for_95_over_95(self):
        self.assertEqual(inf.success_run_trials(0.95, 0.95), 59)

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            inf.success_run_confidence(1.0, 60)
        with self.assertRaises(ValueError):
            inf.success_run_trials(0.95, 1.0)


if __name__ == "__main__":
    unittest.main()
