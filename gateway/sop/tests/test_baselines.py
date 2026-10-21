import csv
import json
import tempfile
import unittest
from pathlib import Path

from sop import baselines as bl, campaign, chapter4 as c4, https_hw as hh
from sop.tests.test_chapter4 import row


def an_rows(n=8, fail_n=(), blocks=24):
    rows = []
    for t in range(1, n + 1):
        rt = t % 3
        for sc in ("A", "N"):
            if sc == "N" and t in fail_n:
                rows.append(row("N", t, status="failed", note="attempt 1: the device reported: update to v1.1 failed: delta decode error"))
                continue
            saved = 0 if sc == "A" else 29 * blocks
            rows.append(row(sc, t, ttc_ms=5000 + 200 * rt + t, wire_bytes=27000 + 220 * rt - saved + t, blocks=blocks,
                            decrypt_recon_ms=1750 + t if sc == "A" else 1700 + t, decrypt_avg_us=1530 if sc == "A" else 0,
                            reconstruct_us=1.71e6 + 1000 * t, flash_kbps=184 + 0.1 * t, heap_peak_used=6000 + 50 * t + (0 if sc == "A" else 7),
                            static_ram_kb=28.73 if sc == "A" else 27.66, retransmissions=rt))
    return rows


def h_folder(d: Path, runs=8, warmup=3):
    (d / "campaign").mkdir(parents=True)
    rows = []
    for i in range(runs):
        rows.append({k: "" for k in hh.RUN_FIELDS} | {"run": i, "warmup": i < warmup, "status": "ok", "ttc_ms": 3700 + 10 * i, "wire_bytes": 307000 + i,
                                                       "connect_ms": 1360, "download_ms": 2400 + i, "device_ms": 3760 + i, "flash_us": 1500000,
                                                       "flash_bytes": 288880, "flash_kbps": 188.0 + i * 0.1, "bytes": 288880,
                                                       "capture_minus_device_ms": -55, "static_ram_kb": 6.18})
    with open(d / "campaign" / "https_runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hh.RUN_FIELDS)
        w.writeheader()
        w.writerows(rows)
    (d / "summary.json").write_text(json.dumps({"heap": {"peak_bytes": 65_344, "exact": True}}), encoding="utf-8")
    (d / "static_increments.json").write_text(json.dumps({
        "https_control": {"ram_used": 43408, "flash_used": 724465},
        "https_baseline": {"static_ram_increment_b": 6324, "flash_increment_b": 156548},
        "factory": {"static_ram_increment_b": 29416, "flash_increment_b": 43340},
        "factory_naked": {"static_ram_increment_b": 28328, "flash_increment_b": 26400}}), encoding="utf-8")
    return d


class NakedBaselineAnalysisTests(unittest.TestCase):
    def test_a_minus_n_is_paired_by_trial_and_failed_cycles_are_not_pairs(self):
        n = bl.n_analysis(an_rows(n=8, fail_n=(3,)))
        self.assertEqual([p["trial"] for p in n["pairs"]], [1, 2, 4, 5, 6, 7, 8])
        tab = {r["metric"]: r for r in n["table"]}
        wire = tab["wire_bytes"]
        self.assertAlmostEqual(wire["mean_diff"], 29 * 24)                       # the framing bytes, exactly, in the synthetic data
        self.assertAlmostEqual(n["expected_wire_diff"], 696.0)
        self.assertTrue(tab["static_ram_kb"]["degenerate"])
        self.assertAlmostEqual(tab["static_ram_kb"]["mean_diff"], 28.73 - 27.66)
        self.assertEqual(n["counts"]["N"]["failed"], 1)
        self.assertFalse(n["complete"])

    def test_too_few_pairs_is_an_error(self):
        with self.assertRaises(ValueError):
            bl.n_analysis(an_rows(n=2))


class HttpsAnalysisTests(unittest.TestCase):
    def test_equations_3_and_4_use_the_recorded_series_and_the_build_sizes(self):
        with tempfile.TemporaryDirectory() as d:
            h = bl.load_h(h_folder(Path(d) / "h"))
            ab = campaign_rows_for_a()
            pairs = c4.select_pairs(ab)
            res = bl.h_analysis(h, pairs)
            self.assertEqual((res["n_ok"], res["n_failed"]), (5, 0))                 # 3 warm-up runs are not counted
            e3 = res["eq3"]
            self.assertAlmostEqual(e3["static_reduction_pct"], (288880 - 22497) / 288880 * 100, places=6)
            self.assertAlmostEqual(e3["reduction_pct"], (e3["h_mean"] - e3["a_mean"]) / e3["h_mean"] * 100)
            e4 = res["eq4"]
            self.assertEqual(e4["h_total"], 6324 + 65344)
            self.assertAlmostEqual(e4["h_budget_pct"], (6324 + 65344) / 51200 * 100)
            self.assertAlmostEqual(e4["reduction_pct_max"], (e4["h_total"] - e4["a_total_max"]) / e4["h_total"] * 100)
            self.assertGreater(e4["reduction_pct_mean"], e4["reduction_pct_max"])    # A at its mean looks better than at its maximum
            self.assertAlmostEqual(res["flash"]["reduction_pct_a_vs_h"], (156548 - 43340) / 156548 * 100)
            self.assertEqual(res["static"], {"h": 6324, "a": 29416, "n": 28328})
            self.assertEqual(res["ttc"]["welch"]["n_second"], 5)

    def test_the_report_text_is_generated_from_the_numbers(self):
        with tempfile.TemporaryDirectory() as d:
            h = bl.h_analysis(bl.load_h(h_folder(Path(d) / "h")), c4.select_pairs(campaign_rows_for_a()))
            n = bl.n_analysis(an_rows(n=8))
            text = bl.render(n, h)
            for needle in ("10.1 N", "10.2 H", "Equation 3", "Equation 4", "unpaired", "exceeds", "A - N"):
                self.assertIn(needle, text)
            self.assertIn("no certificate validation", text)
            self.assertEqual(bl.render(None, None).count("10.1"), 0)


def campaign_rows_for_a():
    from sop.tests.test_chapter4 import campaign_rows
    return campaign_rows(n=10, fail_a=(), fail_b=(), heap_missing_a=())


class EndToEndTests(unittest.TestCase):
    def test_analyse_export_and_render_with_both_baselines(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            from sop.tests.test_chapter4 import campaign_rows
            for sub, name, rows in (("ab", "trials.csv", campaign_rows(n=12, fail_a=(), fail_b=(), heap_missing_a=())),
                                    ("t3", "table3.csv", [row("T3", t, poll_ms=50, sha_ms=0.2, encap_ms=6, gw_ram_mb=80, gw_cpu_pct=30, diff_ms=32,
                                                              to_dota_ms=140) for t in range(1, 8)]),
                                    ("n", "trials.csv", an_rows(n=10))):
                (d / sub / "campaign").mkdir(parents=True)
                with open(d / sub / "campaign" / name, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=campaign.FIELDS)
                    w.writeheader()
                    w.writerows(rows)
            (d / "cde").mkdir()
            with open(d / "cde" / "trials.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=campaign.FIELDS)
                w.writeheader()
                w.writerows([row(s, t, rejected="True", delay_ms=5000) for s in "CDE" for t in range(1, 6)])
            h_folder(d / "h")
            ctx = c4.analyse(d / "ab", d / "t3", d / "cde" / "trials.csv", None, d / "n", d / "h")
            text = c4.render(ctx)
            self.assertIn("10.1 N", text)
            self.assertIn("10.2 H", text)
            out = d / "out"
            written = {p.name for p in c4.export(ctx, out, None)}
            self.assertIn("baseline_n_pairs.csv", written)
            self.assertIn("baseline_h_runs.csv", written)
            with open(out / "data" / "baseline_n_pairs.csv", newline="", encoding="utf-8") as f:
                first = next(csv.DictReader(f))
            self.assertIn("N_wire_bytes", first)
            self.assertIn("A_ttc_ms", first)


class ConfirmationTests(unittest.TestCase):
    def test_the_confirmation_run_is_compared_with_the_main_campaign(self):
        from sop.tests.test_chapter4 import campaign_rows
        main = c4.select_pairs(campaign_rows(n=14, fail_a=(), fail_b=(), heap_missing_a=()))
        conf_rows = campaign_rows(n=8, fail_a=(), fail_b=(), heap_missing_a=())
        c = bl.confirmation(conf_rows, None, main, wanted=8)
        self.assertEqual(c["n_pairs"], 8)
        self.assertEqual(c["counts"]["A"]["ok"], 8)
        metrics = [r["metric"] for r in c["rows"]]
        self.assertIn("ttc_ms", metrics)
        self.assertIn("heap_peak_used", metrics)
        text = bl.render_confirmation(c)
        for needle in ("11. Confirmation run", "main campaign", "Welch", "complete A/B pairs"):
            self.assertIn(needle, text)

    def test_too_few_pairs_is_an_error(self):
        from sop.tests.test_chapter4 import campaign_rows
        with self.assertRaises(ValueError):
            bl.confirmation(campaign_rows(n=2, fail_a=(), fail_b=(), heap_missing_a=()), None, [], wanted=8)


if __name__ == "__main__":
    unittest.main()
