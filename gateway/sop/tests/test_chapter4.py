import csv
import tempfile
import unittest
from pathlib import Path

from sop import campaign, chapter4 as c4, inference as inf

WEB3_LOG = """\
[+1.000] [MEM] phase=boot free=300000 min=299000
[+3.000] [MEM] phase=web3-start free=250000 min=248000
[+5.000] [Web3] run=0 tls_connect_ms=1300 request_ms=40 keccak_us=500 decode_us=100 ok=1 approvals=2 live=1 revoked=0
[+5.100] [MEM] phase=web3-run free=249000 min=200000
[+7.000] [Web3] run=1 tls_connect_ms=1400 request_ms=60 keccak_us=520 decode_us=120 ok=1 approvals=2 live=1 revoked=0
[+7.100] [MEM] phase=web3-run free=249000 min=198000
[+9.000] [Web3] run=2 tls_connect_ms=1500 ok=0 why=connect
[+9.500] [MEM] phase=web3-end free=249500 min=198000
[+9.600] [Web3] summary ok=2/3
"""


def row(scenario, trial, status="ok", warmup=False, **kw):
    r = {k: "" for k in campaign.FIELDS}
    r.update(scenario=scenario, trial=str(trial), warmup=str(warmup), status=status, note=kw.pop("note", ""))
    r.update({k: str(v) for k, v in kw.items()})
    return r


def campaign_rows(n=8, fail_a=(3,), fail_b=(5,), heap_missing_a=(2,)):
    rows = [row("A", 1, warmup=True, ttc_ms=1), row("B", 1, warmup=True, ttc_ms=1)]           # warm-up: never analysed
    for t in range(1, n + 1):
        for sc, fails in (("A", fail_a), ("B", fail_b)):
            if t in fails:
                rows.append(row(sc, t, status="failed", note="attempt 1: the device reported: update to v1.1 failed: delta decode error"))
                continue
            base = 5000 if sc == "A" else 30000
            rt = (t % 3) if sc == "A" else (t % 4)
            heap = "" if (sc == "A" and t in heap_missing_a) else 6000 + 100 * t + (500 if sc == "B" else 0)
            rows.append(row(sc, t, ttc_ms=base + 200 * rt + t, wire_bytes=base * 5 + t, blocks=24 if sc == "A" else 168,
                            requests=24 + rt, retransmissions=rt, decrypt_recon_ms=1750 + t if sc == "A" else 1840 + t,
                            flash_kbps=184 + 0.1 * t if sc == "A" else 196 + 0.1 * t, heap_peak_used=heap, static_ram_kb=28.73))
    return rows


class PairSelectionTests(unittest.TestCase):
    def test_pairs_need_both_scenarios_ok_and_skip_warmup(self):
        pairs = c4.select_pairs(campaign_rows())
        self.assertEqual([p["trial"] for p in pairs], [1, 2, 4, 6, 7, 8])            # 3 (A failed) and 5 (B failed) are not pairs
        self.assertEqual([p["pair"] for p in pairs], [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(p["A"]["trial"] == p["B"]["trial"] for p in pairs))

    def test_only_the_first_n_pairs_are_taken(self):
        self.assertEqual(len(c4.select_pairs(campaign_rows(n=12), wanted=4)), 4)

    def test_a_metric_missing_in_one_cycle_drops_the_whole_pair_for_that_metric(self):
        pairs = c4.select_pairs(campaign_rows())
        table = {r["metric"]: r for r in c4.paired_table(pairs)}
        self.assertEqual(table["ttc_ms"]["n"], 6)
        self.assertEqual(table["heap_peak_used"]["n"], 5)                             # trial 2 has no A heap value
        self.assertEqual(c4.column(pairs, "A", "heap_peak_used")[0], 6100.0)


class PairedTableTests(unittest.TestCase):
    def setUp(self):
        self.pairs = c4.select_pairs(campaign_rows())
        self.table = {r["metric"]: r for r in c4.paired_table(self.pairs)}

    def test_reduction_and_test_agree_with_inference(self):
        r = self.table["ttc_ms"]
        a, b = c4.column(self.pairs, "A", "ttc_ms"), c4.column(self.pairs, "B", "ttc_ms")
        self.assertAlmostEqual(r["reduction_pct"], inf.relative_reduction_pct(inf.mean(b), inf.mean(a)))
        self.assertAlmostEqual(r["t"], inf.paired_t_test(a, b)["t"])
        self.assertEqual(r["a_lower"], 6)
        self.assertLess(r["ci_high"], 0)
        self.assertLess(r["utl_A"], r["utl_B"])

    def test_zero_variance_columns_are_reported_not_tested(self):
        for m in ("blocks", "static_ram_kb"):
            self.assertTrue(self.table[m]["degenerate"])
            self.assertIsNone(self.table[m]["t"])
        self.assertEqual(self.table["blocks"]["mean_diff"], -144)


class RootCauseAndFailureTests(unittest.TestCase):
    def test_root_cause_finds_the_repeated_request_effect(self):
        rc = c4.root_cause(c4.select_pairs(campaign_rows(n=12, fail_a=(), fail_b=(), heap_missing_a=())))
        self.assertGreater(rc["A"]["r"], 0.9)
        self.assertAlmostEqual(rc["A"]["slope_ms_per_retransmission"], 200, delta=25)
        self.assertGreater(rc["A"]["n_clean"], 0)

    def test_classify_failure_uses_the_device_words(self):
        self.assertEqual(c4.classify_failure("x", "[+1] [Delta] FAILED: flash write failed\n"), "flash write failed")
        self.assertEqual(c4.classify_failure("update failed: transfer stalled (281 s)", ""), "transfer stalled")
        self.assertEqual(c4.classify_failure("", ""), "unknown")

    def test_failure_accounting_counts_only_counted_cycles(self):
        rows = campaign_rows() + [row("A", 99, status="invalid", note="flash_device.bat app failed"), row("A", 2, status="failed", warmup=True)]
        f = c4.failures(rows)
        self.assertEqual(f["by_scenario"]["A"]["failed"], 1)
        self.assertEqual(f["by_scenario"]["A"]["invalid"], 1)
        self.assertEqual(f["by_scenario"]["B"]["failed"], 1)
        self.assertEqual(f["by_scenario"]["A"]["attempts"], 8)                       # 7 ok + 1 failed; warm-up and invalid excluded
        self.assertAlmostEqual(f["fisher_p"], 1.0)
        self.assertEqual(len(f["detail"]), 2)
        self.assertLess(f["both"]["low"], f["both"]["rate"])

    def test_cycles_after_a_failure_are_compared_with_the_others(self):
        a = c4.after_failure_effect(campaign_rows(n=12))
        self.assertGreater(a["A"]["n_after"], 0)
        self.assertGreater(a["A"]["n_rest"], a["A"]["n_after"])


class ScenarioAndGatewayTests(unittest.TestCase):
    def test_success_run_confidence_only_when_every_trial_passed(self):
        rows = [row("C", t, rejected="True", delay_ms=5000 + t) for t in range(1, 61)]
        s = c4.scenario_stats(rows)["C"]
        self.assertEqual((s["trials"], s["rejected"], s["failures"]), (60, 60, 0))
        self.assertAlmostEqual(s["confidence"], 1 - 0.95 ** 60)
        rows[0]["rejected"] = "False"
        self.assertIsNone(c4.scenario_stats(rows)["C"]["confidence"])

    def test_booleans_rewritten_by_a_spreadsheet_are_still_read(self):
        rows = [row("D", 1, rejected="TRUE"), row("D", 2, rejected="FALSE")]
        self.assertEqual(c4.scenario_stats(rows)["D"]["rejected"], 1)

    def test_table3_statistics_skip_warmup_and_failed_rows(self):
        rows = [row("T3", t, poll_ms=50 + t, sha_ms=0.2, encap_ms=6, gw_ram_mb=80, gw_cpu_pct=30, diff_ms=32, to_dota_ms=140) for t in range(1, 11)]
        rows.append(row("T3", 11, warmup=True, poll_ms=9999, sha_ms=0, encap_ms=0, gw_ram_mb=0, gw_cpu_pct=0, diff_ms=0, to_dota_ms=0))
        poll = c4.table3_stats(rows)[0]
        self.assertEqual(poll["n"], 10)
        self.assertAlmostEqual(poll["mean"], 55.5)
        self.assertGreater(poll["utl"], poll["max"] - 1)


class Sop4Tests(unittest.TestCase):
    def test_web3_statistics_from_a_serial_log(self):
        w = c4.web3_stats(WEB3_LOG)
        self.assertEqual((w["n_ok"], w["n_all"]), (2, 3))
        self.assertAlmostEqual(w["metrics"]["tls_connect_ms"]["mean"], 1350.0)
        self.assertEqual(w["heap"]["peak_bytes"], 250000 - 198000)
        self.assertEqual(len(w["mem_runs"]), 2)
        self.assertAlmostEqual(w["total_ms"]["mean"], ((1300 + 40 + 0.6) + (1400 + 60 + 0.64)) / 2, places=6)

    def test_like_for_like_comparison_reproduces_the_reported_figures(self):
        cmp_ = c4.sop4_comparison(heap_mean_A=6148.0, heap_utl_A=11057.0, web3_heap_peak=52000)
        self.assertAlmostEqual(cmp_["flash"]["reduction_pct"], 78.47, places=2)
        self.assertAlmostEqual(cmp_["static_ram"]["reduction_pct"], 9.94, places=2)
        self.assertEqual(cmp_["peak_ram"]["not_offloaded"], 29400 + 3244 + 52000)
        self.assertAlmostEqual(cmp_["peak_ram"]["reduction_pct"], 58.00, places=2)
        self.assertAlmostEqual(cmp_["peak_ram"]["not_offloaded_pct_budget"], 165.3, places=1)
        self.assertAlmostEqual(cmp_["web3_alone_pct_budget"], 107.9, places=1)


class EndToEndTests(unittest.TestCase):
    def test_analyse_render_and_export_write_consistent_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ab, t3, cde = d / "ab" / "campaign", d / "t3" / "campaign", d / "cde"
            for p in (ab, t3, cde):
                p.mkdir(parents=True)
            for path, rows in ((ab / "trials.csv", campaign_rows(n=12, fail_a=(3,), fail_b=(5,), heap_missing_a=())),
                               (t3 / "table3.csv", [row("T3", t, poll_ms=50 + t, sha_ms=0.2, encap_ms=6, gw_ram_mb=80, gw_cpu_pct=30,
                                                        diff_ms=32, to_dota_ms=140) for t in range(1, 8)]),
                               (cde / "trials.csv", [row(s, t, rejected="True", delay_ms=5000) for s in "CDE" for t in range(1, 6)])):
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=campaign.FIELDS)
                    w.writeheader()
                    w.writerows(rows)
            ctx = c4.analyse(d / "ab", d / "t3", cde / "trials.csv")
            text = c4.render(ctx)
            self.assertIn("## 3. Table 2 metrics", text)
            self.assertIn("Wireshark TTC (ms)", text)
            self.assertIn("C: tampered patch", text)
            out = d / "out"
            written = c4.export(ctx, out, None)
            self.assertEqual({p.name for p in written}, {"ab_pairs.csv", "failures.csv", "table3_cycles.csv", "scenarios_cde_trials.csv"})
            with open(out / "data" / "ab_pairs.csv", newline="", encoding="utf-8") as f:
                pairs = list(csv.DictReader(f))
            self.assertEqual(len(pairs), len(ctx["pairs"]))
            self.assertEqual(pairs[0]["pair"], "1")
            self.assertIn("A_ttc_ms", pairs[0])
            (out / "STATISTICS.md").write_text(text, encoding="utf-8")
            man = c4.write_manifest(out, [])
            self.assertIn("STATISTICS.md", man.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
