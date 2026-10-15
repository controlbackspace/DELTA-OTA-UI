import unittest

from sop import thesis_tables as tt


def trial(scenario, n, status="ok", rejected=True, warmup=False):
    return {"scenario": scenario, "trial": str(n), "warmup": str(warmup), "status": status,
            "rejected": str(rejected)}


def all_pass(cycles=60):
    return [trial(s, n) for s in "CDE" for n in range(1, cycles + 1)]


class Table1Tests(unittest.TestCase):
    def test_values_and_the_approved_headings(self):
        md = tt.table1(288880, 22497)
        self.assertIn("Table 1. Static Analysis of Volumetric Payload Optimization and Compression Ratio", md)
        self.assertIn("| Metric ID | Firmware Full Binary Version Pair Size (Bytes) | Delta Patch Size (Bytes) | Total Bytes Saved | Compression Ratio (%) |", md)
        self.assertIn("| VOL_01 | v1.0 to v1.1: 288,880 | 22,497 | 266,383 | 92.21 |", md)

    def test_ratio_is_saved_over_full(self):
        self.assertIn("| 50.00 |", tt.table1(1000, 500))

    def test_a_zero_size_is_rejected(self):
        with self.assertRaises(ValueError):
            tt.table1(0, 0)


class Table4Tests(unittest.TestCase):
    def test_sixty_clean_cycles_achieve_95_4_percent(self):
        md = tt.table4(all_pass())
        self.assertIn("| Cycle # | Scenario C: Tampered Patch (Rejected: Y/N) | Scenario D: Kill-Switch Revocation (Blocked: Y/N) | Scenario E: Incomplete Signature (Reverted: Y/N) | Success-Run Status |", md)
        self.assertIn("| 1 | Pass | Pass | Pass | Valid |", md)
        self.assertIn("| 60 | Pass | Pass | Pass | Valid |", md)
        self.assertIn("| RESULT | Total Failures 0 | Total Failures 0 | Total Failures 0 | 95.4% Confidence Achieved |", md)

    def test_a_failure_removes_the_confidence_claim(self):
        rows = all_pass()
        rows[10] = trial("C", 11, status="failed", rejected=False)
        md = tt.table4(rows)
        self.assertIn("| 11 | Fail | Pass | Pass | Not valid |", md)
        self.assertIn("Total Failures 1 |", md)
        self.assertNotIn("95.4%", md)

    def test_missing_cycles_are_not_counted_as_passes(self):
        rows = [r for r in all_pass() if not (r["scenario"] == "E" and int(r["trial"]) > 30)]
        md = tt.table4(rows)
        self.assertIn("| 31 | Pass | Pass | - | Pending |", md)
        self.assertIn("Incomplete: C 60/60, D 60/60, E 30/60", md)
        self.assertNotIn("95.4%", md)

    def test_invalid_and_warmup_trials_are_ignored(self):
        rows = all_pass()
        rows.append(trial("C", 5, status="invalid", rejected=False))
        rows.append(trial("D", 5, warmup=True, rejected=False))
        md = tt.table4(rows)
        self.assertIn("95.4% Confidence Achieved", md)

    def test_spreadsheet_spelling_of_booleans_is_understood(self):
        rows = [{**r, "warmup": "FALSE", "rejected": "TRUE"} for r in all_pass()]       # as Excel saves the CSV
        md = tt.table4(rows)
        self.assertIn("95.4% Confidence Achieved", md)
        rows[0] = {**rows[0], "rejected": "FALSE"}
        self.assertIn("| 1 | Fail | Pass | Pass | Not valid |", tt.table4(rows))

    def test_a_trial_that_passed_the_harness_but_was_not_rejected_is_a_fail(self):
        rows = all_pass()
        rows[0] = trial("C", 1, status="ok", rejected=False)
        self.assertIn("| 1 | Fail | Pass | Pass | Not valid |", tt.table4(rows))



def cycle(sc, n, ttc=None, recon=None, thr=None, ram="28.71", warmup=False, status="ok", **kw):
    r = {"scenario": sc, "trial": str(n), "warmup": str(warmup), "status": status, "ttc_ms": "" if ttc is None else str(ttc),
         "static_ram_kb": ram, "decrypt_recon_ms": "" if recon is None else str(recon), "flash_kbps": "" if thr is None else str(thr)}
    r.update({k: str(v) for k, v in kw.items()})
    return r


def ab_rows(cycles=60):
    rows = []
    for n in range(1, cycles + 1):
        rows.append(cycle("A", n, ttc=5000 + n, recon=446.0, thr=940.0))
        rows.append(cycle("B", n, ttc=36000 + n, recon=450.0, thr=960.0))
    return rows


class Table2Tests(unittest.TestCase):
    def test_headings_rows_and_the_na_cells_follow_the_approved_layout(self):
        md = tt.table2(ab_rows())
        self.assertIn("Table 2. Continuous Metrics for Hardware and Network Performance", md)
        self.assertIn("| Cycle # | Scenario Type | Wireshark TTC (ms) | ESP32 Peak Ram Allocation (KB) | "
                      "Decryption + Reconstruction Time (ms) | Total Flash Write Throughput (KB/s) |", md)
        self.assertIn("| 1 | A (Delta-OTA) | 5001.0 | 28.71 | 446.0 | 940.0 |", md)
        self.assertIn("| 1 | B (Full-Binary) | 36001.0 | 28.71 | N/A | 960.0 |", md)          # B stays N/A although 450.0 was recorded
        self.assertIn("| 60 | B (Full-Binary) | 36060.0 | 28.71 | N/A | 960.0 |", md)

    def test_stat_rows_are_per_scenario_and_use_n_minus_one(self):
        md = tt.table2(ab_rows())
        self.assertIn("| STAT | Arithmetic Mean (A (Delta-OTA)) | 5030.5 | 28.71 | 446.0 | 940.0 |", md)
        self.assertIn("| STAT | Standard Deviation (A (Delta-OTA)) | 17.5 | 0.00 | 0.0 | 0.0 |", md)       # RAM is constant: SD 0
        self.assertIn("| STAT | Arithmetic Mean (B (Full-Binary)) | 36030.5 | 28.71 | N/A | 960.0 |", md)

    def test_warmup_and_invalid_cycles_are_not_in_the_table_and_gaps_are_shown(self):
        rows = ab_rows(3) + [cycle("A", 1, ttc=999999, warmup=True)] + [cycle("B", 9, ttc=1, status="invalid")]
        md = tt.table2(rows, cycles=4)
        self.assertNotIn("999999", md)
        self.assertIn("| 4 | A (Delta-OTA) | - | - | - | - |", md)
        self.assertIn("Incomplete: A 3/4 cycles, B 3/4 cycles.", md)

    def test_the_note_about_scenario_b_is_under_the_table_not_in_it(self):
        md = tt.table2(ab_rows())
        self.assertIn("Scenario B's Decryption + Reconstruction cells stay N/A as approved", md)


class Table3Tests(unittest.TestCase):
    def rows(self, n=60):
        return [{"scenario": "T3", "trial": str(i), "warmup": "False", "status": "ok", "poll_ms": "4.5", "sha_ms": "0.025",
                 "encap_ms": "13.0", "gw_ram_mb": "71.0", "gw_cpu_pct": "6.0"} for i in range(1, n + 1)]

    def test_headings_rows_and_the_average(self):
        md = tt.table3(self.rows())
        self.assertIn("Table 3. Edge Gateway Computational Overhead and Security Tax Profiling", md)
        self.assertIn("| Cycle # | Web3 Smart Contract Polling (ms) | Local SHA-256 Hash Execution (ms) | "
                      "OSCORE AES-CCM Encapsulation (ms) | Peak Gateway RAM Utilized (MB) | Peak Gateway CPU Load (%) |", md)
        self.assertIn("| 1 | 4.50 | 0.025 | 13.00 | 71.0 | 6.0 |", md)
        self.assertIn("| STAT: Average | 4.50 | 0.025 | 13.00 | 71.0 | 6.0 |", md)

    def test_incomplete_runs_say_so(self):
        self.assertIn("Incomplete: 10/60 cycles.", tt.table3(self.rows(10)))


if __name__ == "__main__":
    unittest.main()
