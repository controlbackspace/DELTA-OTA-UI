import tempfile
import unittest
from pathlib import Path

from sop import report
from sop.runlog import RunContext, StepResult, Table

# Phrases that belong in an operator console, not in a document shown to a review panel.
OPERATOR_PHRASES = ("SKIPPED", "REPLACE", "ready to cite", "Do not claim", "must not be quoted", "verify before",
                    "NOT run", "Honest", "FINDING")


class ReportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ctx = RunContext(Path(self._tmp.name) / "run")

    def tearDown(self):
        self._tmp.cleanup()

    def sop1(self, **kw):
        base = dict(
            sop="SOP1", title="Delta footprint", method="Artifacts were generated and measured.",
            summary="The update needs 24 blocks instead of 158.",
            claims=["[measured, production firmware] The patch is 22,497 B.", "[modelled, lower bound] 100 devices take 1.4 min."],
            tables=[Table("Sizes", ["Case", "Bytes"], [["real", "23,614"], ["pipe|case", "1"]], "measured", note="n")],
            notes=["Every case reconstructs the target."], limitations=["Airtime is a lower bound."],
        )
        base.update(kw)
        self.ctx.save(StepResult(**base))

    def test_bad_status_and_kind_are_rejected(self):
        with self.assertRaises(ValueError):
            StepResult(sop="SOP1", title="x", status="great")
        with self.assertRaises(ValueError):
            StepResult(sop="SOP1", title="x", tables=[Table("t", ["a"], [[1]], kind="guessed")])

    def test_results_survive_a_reload(self):
        self.ctx.save(StepResult(sop="SOP1", title="Delta", claims=["a claim"], limitations=["l"], not_performed=["n"]))
        again = RunContext(self.ctx.dir).results["SOP1"]
        self.assertEqual((again["claims"], again["limitations"], again["not_performed"]), (["a claim"], ["l"], ["n"]))

    def test_the_report_has_the_formal_structure_in_order(self):
        self.sop1()
        text = report.render(self.ctx)
        order = ["# Experimental Evidence Report", "## 1. Purpose and Scope", "## 2. Experimental Setup", "## 3. Results",
                 "### 3.1 Statement of the Problem 1", "### 3.4 Statement of the Problem 4",
                 "### 3.5 Statement of the Problem 5", "## 4. Summary of Findings",
                 "## 5. Limitations and Threats to Validity", "## 6. Reproducibility"]
        pos = [text.index(h) for h in order]
        self.assertEqual(pos, sorted(pos))
        self.assertIn("Securing Delta-OTA for Constrained IoT via OSCORE", text)

    def test_a_statement_renders_question_method_result_findings_tables_and_limits(self):
        self.sop1()
        text = report.render(self.ctx)
        self.assertIn("**Research question.** What is the measurable impact of binary volumetric differencing", text)
        self.assertIn("**Method.** Artifacts were generated and measured.", text)
        self.assertIn("**Principal result.** The update needs 24 blocks instead of 158.", text)
        self.assertIn("1. The patch is 22,497 B. *(Measured; production firmware.)*", text)
        self.assertIn("2. 100 devices take 1.4 min. *(Modelled; lower bound.)*", text)
        self.assertIn("**Table 1.** Sizes *(Measured)*", text)
        self.assertIn("| real | 23,614 |", text)
        self.assertIn("pipe\\|case", text)                      # cells cannot break the grid
        self.assertIn("**Observations.**", text)
        self.assertIn("- *SOP 1:* Airtime is a lower bound.", text)   # collected into Section 5

    def test_tables_are_numbered_across_the_whole_report(self):
        self.sop1(tables=[Table("A", ["x"], [[1]], "measured"), Table("B", ["x"], [[2]], "cited")])
        self.ctx.save(StepResult(sop="SOP2", title="x", tables=[Table("C", ["x"], [[3]], "modelled")]))
        text = report.render(self.ctx)
        for n, cap, basis in ((1, "A", "Measured"), (2, "B", "Literature"), (3, "C", "Modelled")):
            self.assertIn(f"**Table {n}.** {cap} *({basis})*", text)

    def test_unrun_and_unavailable_statements_are_stated_plainly(self):
        self.ctx.save(StepResult(sop="SOP4", title="Footprint", status="skipped", reason="the firmware project was not found"))
        self.ctx.save(StepResult(sop="SOP3", title="Ledger", status="not-implemented", reason="planned"))
        text = report.render(self.ctx)
        self.assertIn("*This statement could not be evaluated in this run: the firmware project was not found.*", text)
        self.assertIn("*This statement was not evaluated in this run.*", text)          # SOP 1 and 2 never ran
        self.assertIn("| SOP 4 | Not evaluated: the firmware project was not found | - |", text)

    def test_sop5_is_reserved_for_the_implementation_phase(self):
        text = report.render(self.ctx)
        self.assertIn("reserved for the implementation phase", text)
        self.assertIn("| SOP 5 | Reserved for the implementation phase (60 automated cycles) | - |", text)

    def test_parts_that_did_not_run_are_listed_in_the_limitations_section(self):
        self.sop1(not_performed=["Device-side measurements were not performed in this run."])
        text = report.render(self.ctx)
        self.assertIn("**Not performed in this run.**", text)
        self.assertIn("- *SOP 1:* Device-side measurements were not performed in this run.", text)

    def test_summary_table_carries_the_principal_result_and_its_basis(self):
        self.sop1()
        text = report.render(self.ctx)
        self.assertIn("| SOP 1 | The update needs 24 blocks instead of 158. | Measured |", text)

    def test_setup_lists_the_inputs_with_their_hashes(self):
        self.ctx.meta["inputs"] = [{"label": "firmware base", "path": "C:\\fw\\a.bin", "bytes": 1234, "sha256": "ab" * 32}]
        text = report.render(self.ctx)
        self.assertIn("**Input, firmware base:** `C:\\fw\\a.bin` (1,234 bytes; SHA-256 `" + "ab" * 32 + "`)", text)

    def test_no_operator_wording_reaches_the_document(self):
        self.sop1()
        text = report.render(self.ctx)
        for phrase in OPERATOR_PHRASES:
            self.assertNotIn(phrase, text, phrase)

    def test_write_report_creates_the_file(self):
        path = report.write_report(self.ctx)
        self.assertTrue(Path(path).is_file())
        self.assertIn("# Experimental Evidence Report", Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
