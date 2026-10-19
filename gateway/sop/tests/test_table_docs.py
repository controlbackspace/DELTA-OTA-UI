import tempfile
import unittest
from pathlib import Path

import bsdiff4

from sop import campaign, table_docs, thesis_tables as tt
from sop.tests.test_chapter4 import campaign_rows, row


def write_csv(path: Path, rows):
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campaign.FIELDS)
        w.writeheader()
        w.writerows(rows)


def table_block(text: str, n: int) -> str:
    """The approved table: its title line and every table row (blank lines and notes around it are ignored)."""
    i = text.index(f"**Table {n}.")
    lines = text[i:].splitlines()
    out, started = [lines[0]], False
    for line in lines[1:]:
        if line.startswith("|"):
            started = True
            out.append(line)
        elif started:
            break
    return chr(10).join(out)


class TableDocumentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.base, self.target = self.d / "v1.0.bin", self.d / "v1.1.bin"
        self.base.write_bytes(bytes(range(256)) * 40)
        self.target.write_bytes(bytes(range(256)) * 38 + b"changed tail" * 50)
        self.patch = bsdiff4.diff(self.base.read_bytes(), self.target.read_bytes())
        self.cde_rows = [row(s, t, rejected="True", delay_ms=5000, git_revision="abc1234") for s in "CDE" for t in range(1, 61)]
        self.cde_csv = self.d / "cde" / "trials.csv"
        write_csv(self.cde_csv, self.cde_rows)
        self.ab_rows = campaign_rows(n=70, fail_a=(3, 9), fail_b=(5,), heap_missing_a=())
        self.ab_csv = self.d / "ab" / "campaign" / "trials.csv"
        write_csv(self.ab_csv, self.ab_rows)
        self.t3_rows = [row("T3", t, poll_ms=50 + t % 7, sha_ms=0.2, encap_ms=6, gw_ram_mb=80, gw_cpu_pct=30, diff_ms=32, to_dota_ms=140) for t in range(1, 61)]
        self.t3_rows[5]["status"], self.t3_rows[5]["note"] = "invalid", "superseded: contract read stalled (21.8 s); re-run"
        self.t3_rows.append(row("T3", 6, poll_ms=55, sha_ms=0.2, encap_ms=6, gw_ram_mb=80, gw_cpu_pct=30, diff_ms=32, to_dota_ms=140))
        self.t3_csv = self.d / "t3" / "campaign" / "table3.csv"
        write_csv(self.t3_csv, self.t3_rows)

    def tearDown(self):
        self._tmp.cleanup()

    def doc14(self):
        return table_docs.table1_and_4_doc(base=self.base, target=self.target, patch=self.patch, cde_csv=self.cde_csv, cde_rows=self.cde_rows, head="deadbee")

    def doc23(self):
        return table_docs.table2_and_3_doc(ab_csv=self.ab_csv, t3_csv=self.t3_csv, ab_rows=self.ab_rows, t3_rows=self.t3_rows, head="deadbee")

    def test_table_1_and_4_blocks_are_exactly_the_approved_renderers(self):
        doc = self.doc14()
        self.assertEqual(table_block(doc, 1), table_block(tt.table1(self.target.stat().st_size, len(self.patch)), 1))
        self.assertEqual(table_block(doc, 4), table_block(tt.table4(self.cde_rows), 4))
        self.assertIn("95.4% Confidence Achieved", doc)
        self.assertIn("1 - 0.95^59 = 95.15%", doc)

    def test_table_2_and_3_blocks_use_complete_pairs_renumbered(self):
        doc = self.doc23()
        pairs = table_docs.c4.select_pairs(self.ab_rows)
        render = []
        for p in pairs:
            for sc in "AB":
                r = dict(p[sc]); r["trial"] = str(p["pair"]); render.append(r)
        self.assertEqual(table_block(doc, 2), table_block(tt.table2(render), 2))
        self.assertEqual(table_block(doc, 3), table_block(tt.table3(self.t3_rows), 3))
        self.assertIn("Table cycle to campaign trial number: 1=1, 2=2, 3=4, 4=6", doc)         # trials 3 and 5 are not pairs
        self.assertIn("A trial 3:", doc)
        self.assertIn("Cycle 6 was run twice", doc)

    def test_fewer_than_sixty_pairs_is_an_error(self):
        with self.assertRaises(ValueError):
            table_docs.table2_and_3_doc(ab_csv=self.ab_csv, t3_csv=self.t3_csv, ab_rows=campaign_rows(n=20), t3_rows=self.t3_rows, head="x")

    def test_appendix_is_cut_from_the_documents_and_replaces_the_old_one(self):
        d14, d23 = self.doc14(), self.doc23()
        app = table_docs.appendix_from_docs(d14, d23)
        for n in (1, 2, 3, 4):
            self.assertIn(f"**Table {n}.", app)
        self.assertNotIn("How to read it", app)
        draft = "# Title\n\nbody text\n\n---\n\n# APPENDIX: THE APPROVED INSTRUMENTS FILLED FROM THE RECORDED DATA\n\nold appendix\n"
        out = table_docs.replace_appendix(draft, app)
        self.assertTrue(out.startswith("# Title\n\nbody text\n\n---\n\n# APPENDIX"))
        self.assertNotIn("old appendix", out)
        self.assertEqual(out.count("# APPENDIX: THE APPROVED"), 1)
        with self.assertRaises(ValueError):
            table_docs.replace_appendix("no appendix here", app)


if __name__ == "__main__":
    unittest.main()
