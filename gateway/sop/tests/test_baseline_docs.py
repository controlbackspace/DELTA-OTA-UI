import csv
import tempfile
import unittest
from pathlib import Path

from sop import campaign, chapter4 as c4, table_docs, thesis_tables as tt
from sop.tests.test_baselines import an_rows, h_folder
from sop.tests.test_chapter4 import campaign_rows, row


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campaign.FIELDS)
        w.writeheader()
        w.writerows(rows)


class TableS2Tests(unittest.TestCase):
    def pairs(self, n):
        return c4.select_pairs(an_rows(n=n), 60, ("A", "N"))

    def h_rows(self, n):
        return [{"ttc_ms": 3700 + i, "static_ram_kb": 6.18, "download_ms": 2400, "flash_us": 1500000, "flash_kbps": 190, "wire_bytes": 307000} for i in range(n)]

    def test_rows_are_a_and_n_per_pair_then_h_then_stats_and_the_footer(self):
        text = tt.table2s(self.pairs(4), self.h_rows(3), 65344, cycles=4)
        rows = [l for l in text.splitlines() if l.startswith("| ")]
        self.assertEqual(rows[0].split(" | ")[0], "| Cycle #")
        self.assertIn("A (Delta-OTA, paired with N)", rows[1])
        self.assertIn("N (Naked CoAP delta)", rows[2])
        self.assertEqual(sum(1 for l in rows if "H (HTTPS full binary)" in l and "STAT" not in l), 4)    # 3 runs + one missing row
        self.assertEqual(sum(1 for l in rows if l.startswith("| STAT")), 6)
        self.assertIn("| FOOTER | H peak heap, highest of the downloads", text)
        self.assertIn("65,344", text)
        self.assertIn("not an approved instrument", text)
        self.assertIn("H 3/4", text.split("Incomplete:")[1].splitlines()[0])

    def test_the_h_receive_time_is_download_minus_flash_time(self):
        text = tt.table2s(self.pairs(1), self.h_rows(1), None, cycles=1)
        h_line = next(l for l in text.splitlines() if l.startswith("| 1 | H"))
        self.assertIn("| 900.0 |", h_line)                                   # 2400 ms - 1500 ms
        self.assertIn("| - |", h_line)                                       # no per-run heap for H

    def test_the_approved_tables_are_untouched(self):
        self.assertEqual(tt.TABLE2_COLUMNS[2], "Wireshark TTC (ms)")
        self.assertNotIn("Supplementary", tt.TABLE2_TITLE)


class BaselinesDocTests(unittest.TestCase):
    def test_the_document_carries_the_table_the_analysis_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_csv(d / "ab" / "campaign" / "trials.csv", campaign_rows(n=12, fail_a=(), fail_b=(), heap_missing_a=()))
            write_csv(d / "t3" / "campaign" / "table3.csv", [row("T3", t, poll_ms=50, sha_ms=0.2, encap_ms=6, gw_ram_mb=80, gw_cpu_pct=30, diff_ms=32,
                                                                to_dota_ms=140) for t in range(1, 8)])
            write_csv(d / "n" / "campaign" / "trials.csv", an_rows(n=10))
            write_csv(d / "cde" / "trials.csv", [row(s, t, rejected="True", delay_ms=5000) for s in "CDE" for t in range(1, 6)])
            h_folder(d / "h")
            ctx = c4.analyse(d / "ab", d / "t3", d / "cde" / "trials.csv", None, d / "n", d / "h")
            doc = table_docs.baselines_doc(ctx=ctx, n_csv=d / "n" / "campaign" / "trials.csv", h_dir=d / "h", head="abc1234")
            for needle in ("Supplementary Table S2", "N: the security tax", "H: HTTPS full binary", "## Provenance", "abc1234", "sha256", "not one architecture"):
                self.assertIn(needle, doc)
            self.assertNotIn("## 10.", doc)


if __name__ == "__main__":
    unittest.main()
