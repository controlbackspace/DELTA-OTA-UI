import tempfile
import unittest
from pathlib import Path

from sop import report
from sop.runlog import RunContext, StepResult, Table


class ReportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ctx = RunContext(Path(self._tmp.name) / "run")

    def tearDown(self):
        self._tmp.cleanup()

    def test_bad_status_and_kind_are_rejected(self):
        with self.assertRaises(ValueError):
            StepResult(sop="SOP1", title="x", status="great")
        with self.assertRaises(ValueError):
            StepResult(sop="SOP1", title="x", tables=[Table("t", ["a"], [[1]], kind="guessed")])

    def test_results_survive_a_reload(self):
        self.ctx.save(StepResult(sop="SOP1", title="Delta", claims=["a claim"]))
        again = RunContext(self.ctx.dir)
        self.assertEqual(again.results["SOP1"]["claims"], ["a claim"])

    def test_report_marks_unrun_sops_and_always_defers_sop5(self):
        self.ctx.save(StepResult(
            sop="SOP1", title="Delta footprint", claims=["[measured] 24 blocks"],
            tables=[Table("Sizes", ["Case", "Bytes"], [["real", "23,614"], ["pipe|case", "1"]], "measured", note="n")],
        ))
        text = report.render(self.ctx)
        self.assertIn("## SOP1 - Delta footprint", text)
        self.assertIn("[measured] 24 blocks", text)
        self.assertIn("| real | 23,614 |", text)
        self.assertIn("pipe\\|case", text)                 # table cells cannot break the grid
        self.assertIn("_Not run in this session._", text)  # SOP2-4 never ran
        self.assertIn("## SOP5", text)
        self.assertIn("Deferred", text)

    def test_skipped_and_unimplemented_steps_say_so_instead_of_inventing_data(self):
        self.ctx.save(StepResult(sop="SOP4", title="Footprint", status="skipped", mode="hw",
                                 reason="no device on a serial port"))
        self.ctx.save(StepResult(sop="SOP3", title="Ledger", status="not-implemented", reason="planned in P1"))
        text = report.render(self.ctx)
        self.assertIn("Status: **SKIPPED** (`hw`) - no device on a serial port", text)
        self.assertIn("Status: **not implemented yet** (`offline`) - planned in P1", text)

    def test_write_report_creates_the_file(self):
        path = report.write_report(self.ctx)
        self.assertTrue(Path(path).is_file())
        self.assertIn("# SOP Evidence Report", Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
