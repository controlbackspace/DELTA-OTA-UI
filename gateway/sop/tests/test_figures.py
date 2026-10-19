import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

from sop import campaign, chapter4 as c4, figures
from sop.tests.test_chapter4 import campaign_rows, row


@unittest.skipUnless(importlib.util.find_spec("matplotlib"), "matplotlib is optional (only needed to draw the figures)")
class FigureSmokeTests(unittest.TestCase):
    def test_the_four_data_figures_are_written_from_a_synthetic_campaign(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for sub, name, rows in (("ab", "trials.csv", campaign_rows(n=14, fail_a=(3,), fail_b=(5,), heap_missing_a=())),
                                    ("t3", "table3.csv", [row("T3", t, poll_ms=50 + t, sha_ms=0.2, encap_ms=6, gw_ram_mb=80, gw_cpu_pct=30,
                                                              diff_ms=32, to_dota_ms=140) for t in range(1, 8)]),
                                    ("cde", "trials.csv", [row(s, t, rejected="True", delay_ms=5000) for s in "CDE" for t in range(1, 6)])):
                (d / sub / "campaign").mkdir(parents=True)
                with open(d / sub / "campaign" / name, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=campaign.FIELDS)
                    w.writeheader()
                    w.writerows(rows)
            ctx = c4.analyse(d / "ab", d / "t3", d / "cde" / "campaign" / "trials.csv")
            out = d / "figs"
            out.mkdir()
            made = [figures.fig_payload(ctx, out / "a.png"), figures.fig_ttc(ctx, out / "b.png"),
                    figures.fig_ttc_spread(ctx, out / "c.png"), figures.fig_retransmissions(ctx, out / "d.png")]
            for p in made:
                self.assertTrue(p.exists() and p.stat().st_size > 5000, p)


if __name__ == "__main__":
    unittest.main()
