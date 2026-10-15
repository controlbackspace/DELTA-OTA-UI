import unittest

from sop import host_scenarios as hs


class TamperTests(unittest.TestCase):
    def test_a_refused_tampered_patch_is_a_pass(self):
        self.assertEqual(hs.judge_tamper(True, False, "4.01", 0)[:2], ("ok", True))

    def test_a_staged_tampered_patch_is_a_failure_even_without_a_verdict(self):
        self.assertEqual(hs.judge_tamper(False, True, "2.05", 24)[:2], ("failed", False))
        self.assertEqual(hs.judge_tamper(True, False, "2.05", 0)[:2], ("failed", False))
        self.assertEqual(hs.judge_tamper(True, False, "4.01", 3)[:2], ("failed", False))

    def test_no_verdict_and_nothing_served_is_a_harness_problem_not_a_pass(self):
        status, rejected, _ = hs.judge_tamper(False, False, "4.01", 0)
        self.assertEqual((status, rejected), ("invalid", False))

    def test_a_silent_gateway_is_invalid(self):
        self.assertEqual(hs.judge_tamper(True, False, None, 0)[:2], ("invalid", False))


class KillTests(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(hs.judge_kill(True, True, "4.01", 0)[:2], ("ok", True))

    def test_setup_failure_is_invalid(self):
        self.assertEqual(hs.judge_kill(False, False, None, 0)[:2], ("invalid", False))

    def test_no_halt_is_a_failure(self):
        self.assertEqual(hs.judge_kill(True, False, "2.05", 24)[:2], ("failed", False))

    def test_blocks_still_served_after_the_halt_is_a_failure(self):
        self.assertEqual(hs.judge_kill(True, True, "2.05", 0)[:2], ("failed", False))
        self.assertEqual(hs.judge_kill(True, True, "4.01", 2)[:2], ("failed", False))


class IncompleteSignatureTests(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(hs.judge_incomplete(True, "", True, True, True)[:2], ("ok", True))

    def test_each_breach_is_a_failure_and_is_named(self):
        for args, word in (
            ((True, "staged an unapproved release", True, True, True), "staged"),
            ((True, "", False, True, True), "proposer"),
            ((True, "", True, False, True), "outsider"),
            ((True, "", True, True, False), "pending"),
        ):
            status, rejected, note = hs.judge_incomplete(*args)
            self.assertEqual((status, rejected), ("failed", False))
            self.assertIn(word, note)

    def test_a_failed_proposal_is_invalid(self):
        self.assertEqual(hs.judge_incomplete(False, "", True, True, True)[:2], ("invalid", False))


if __name__ == "__main__":
    unittest.main()
