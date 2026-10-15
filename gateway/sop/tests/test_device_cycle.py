import tempfile
import unittest
from pathlib import Path

from sop import campaign as cp
from sop import device_cycle as dc
from sop.serial_parse import parse_log

GW, DEV = "192.168.100.94", "192.168.100.77"


def line(t, src, dst, code, path="", query="", length=24):
    return "\t".join([f"{t:.6f}", src, dst, str(code), path, query, str(length)])


def good_capture():
    """Device asks for 3 blocks (one asked twice); the gateway answers; the last answer is the final 2.04."""
    return "\n".join([
        line(100.000, DEV, GW, 1, "version"),
        line(100.010, GW, DEV, 69, length=20),
        line(100.500, DEV, GW, 1, "patch", "b=0"),
        line(100.520, GW, DEV, 69, length=1060),
        line(100.700, DEV, GW, 1, "patch", "b=1"),
        line(100.900, DEV, GW, 1, "patch", "b=1"),                       # retransmission
        line(100.910, GW, DEV, 69, length=1060),
        line(101.100, DEV, GW, 1, "patch", "b=2"),
        line(101.130, GW, DEV, 68, length=200),                          # final, 2.04
    ])


SERIAL_OK = """\
[+0.1] === Delta-OTA updater ===
[+0.5] [WiFi] Connected. IP=192.168.100.77  gateway=192.168.100.94
[+1.0] [OTA] Update available: v1.0 -> v1.1
[+3.0] [MEM] phase=stream-start free=200000 min=180000
[+9.0] [MEM] phase=stream-end free=150000 min=120000
[+9.0] [Metrics] decrypt n=24 avg=1500us min=1400us max=1800us.
[+9.1] [Metrics2] decrypt_us=36000 feed_us=410000 flash_us=300000 flash_bytes=288880 stream_us=6200000 blocks=24
[+9.2] [Delta] Reconstructed 288880 bytes, esp_ota_end OK.
[+12.0] [Health] Application: v1.1
"""


class CaptureTests(unittest.TestCase):
    def test_code_normalisation(self):
        self.assertEqual([dc.norm_code(c) for c in ("1", "69", "68", "129", "2.05", "")], ["0.01", "2.05", "2.04", "4.01", "2.05", ""])

    def test_ttc_runs_from_the_first_patch_get_to_the_final_response(self):
        r = dc.compute_ttc(dc.parse_tshark(good_capture()), GW)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["ttc_ms"], (101.130 - 100.500) * 1000, places=3)        # not from the /version query
        self.assertEqual((r["requests"], r["retransmissions"]), (4, 1))
        self.assertGreater(r["wire_bytes"], 1000)

    def test_a_transfer_without_a_final_response_is_not_ok(self):
        text = "\n".join(good_capture().splitlines()[:-1])
        r = dc.compute_ttc(dc.parse_tshark(text), GW)
        self.assertFalse(r["ok"])
        self.assertIn("no final", r["reason"])
        self.assertGreater(r["requests"], 0)

    def test_an_empty_or_patchless_capture(self):
        self.assertFalse(dc.compute_ttc([], GW)["ok"])
        only_version = dc.parse_tshark("\n".join(good_capture().splitlines()[:2]))
        self.assertEqual(dc.compute_ttc(only_version, GW)["requests"], 0)

    def test_malformed_lines_are_skipped(self):
        self.assertEqual(len(dc.parse_tshark("junk\n" + line(1.0, DEV, GW, 1, "patch", "b=0") + "\n\t\t")), 1)


class JudgeTests(unittest.TestCase):
    def ok_ttc(self):
        return dc.compute_ttc(dc.parse_tshark(good_capture()), GW)

    def test_a_complete_confirmed_update_is_ok(self):
        self.assertEqual(dc.judge_cycle(parse_log(SERIAL_OK), self.ok_ttc())[0], "ok")

    def test_no_serial_output_is_invalid(self):
        self.assertEqual(dc.judge_cycle(parse_log(""), self.ok_ttc())[0], "invalid")

    def test_a_device_that_never_started_an_update_is_invalid(self):
        log = "[+0.1] === Delta-OTA updater ===\n[+2.0] [OTA] Gateway did not answer /version.\n"
        status, note = dc.judge_cycle(parse_log(log), {"ok": False, "requests": 0})
        self.assertEqual(status, "invalid")
        self.assertIn("/version", note)

    def test_a_reported_failure_is_a_failure_and_counts(self):
        log = SERIAL_OK.replace("[+9.2] [Delta] Reconstructed 288880 bytes, esp_ota_end OK.",
                                "[+9.2] [OTA] Update to v1.1 FAILED: image verification failed")
        status, note = dc.judge_cycle(parse_log(log), self.ok_ttc())
        self.assertEqual(status, "failed")
        self.assertIn("image verification failed", note)

    def test_started_but_never_finished_is_a_failure(self):
        log = "\n".join(l for l in SERIAL_OK.splitlines() if "Reconstructed" not in l and "Health" not in l)
        self.assertEqual(dc.judge_cycle(parse_log(log), self.ok_ttc())[0], "failed")

    def test_an_unusable_capture_is_invalid_but_an_incomplete_transfer_is_a_failure(self):
        self.assertEqual(dc.judge_cycle(parse_log(SERIAL_OK), {"ok": False, "requests": 0, "reason": "empty"})[0], "invalid")
        self.assertEqual(dc.judge_cycle(parse_log(SERIAL_OK), {"ok": False, "requests": 5, "reason": "no final"})[0], "failed")

    def test_the_new_application_must_confirm_its_version(self):
        log = SERIAL_OK.replace("Application: v1.1", "Application: v1.0")
        self.assertEqual(dc.judge_cycle(parse_log(log), self.ok_ttc())[0], "failed")


class ColumnTests(unittest.TestCase):
    def test_device_cells_follow_the_stated_definitions(self):
        c = dc.device_columns(parse_log(SERIAL_OK))
        self.assertAlmostEqual(c["decrypt_recon_ms"], (36000 + 410000) / 1000)            # decrypt + decode/merge/flash busy time
        self.assertAlmostEqual(c["flash_kbps"], (288880 / 1024) / 0.3)                    # bytes over time inside the flash calls
        self.assertEqual((c["decrypt_avg_us"], c["decrypt_max_us"]), (1500, 1800))
        self.assertEqual(c["heap_peak_used"], 200000 - 120000)

    def test_missing_device_lines_leave_cells_empty(self):
        c = dc.device_columns(parse_log("[+0.1] === Delta-OTA updater ===\n"))
        self.assertNotIn("decrypt_recon_ms", c)
        self.assertNotIn("heap_peak_used", c)

    def test_gateway_cells(self):
        rec = {"poll_ms": 4.5, "sha_ms": 0.03, "encap_ms": 13.0, "peak_rss_mb": 71.0, "peak_cpu_pct": 6.0, "to_dota_ms": 36.0}
        g = dc.gateway_columns(rec)
        self.assertEqual((g["poll_ms"], g["gw_ram_mb"], g["gw_cpu_pct"]), (4.5, 71.0, 6.0))
        self.assertEqual(dc.gateway_columns(None), {})

    def test_the_gateway_record_picked_is_the_next_one_for_the_tag(self):
        doc = {"releases": [{"seq": 1, "tag": "v1.1"}, {"seq": 2, "tag": "v9"}, {"seq": 3, "tag": "v1.1"}]}
        self.assertEqual(dc.pick_gateway_record(doc, "v1.1", 1)["seq"], 3)
        self.assertIsNone(dc.pick_gateway_record(doc, "v1.1", 3))
        self.assertIsNone(dc.pick_gateway_record(None, "v1.1", 0))

    def test_static_ram_is_the_stated_build_figure(self):
        self.assertEqual(dc.static_ram_kb(29400), 28.71)


class FakeRig:
    lan_ip = GW

    def __init__(self, serial=SERIAL_OK, capture=None, staged=True, publish_error=None, record=True):
        self.serial, self.capture = serial, capture if capture is not None else good_capture()
        self.staged, self.publish_error, self.record = staged, publish_error, record
        self.calls, self.results = [], []

    def prepare(self):
        self.calls.append("prepare")

    def publish(self, scenario):
        self.calls.append(f"publish-{scenario}")
        if self.publish_error:
            raise dc.RigError(self.publish_error)
        return {"payload_bytes": 22497 if scenario == "A" else 288880, "diff_ms": 120.0 if scenario == "A" else None,
                "gas_propose": 150000, "gas_approve": 90000, "chain_ms": 35.0}

    def wait_staged(self):
        return {"ok": self.staged, "blocks": 24, "stage_ms": 900.0}

    def capture_start(self):
        self.calls.append("capture")

    def run_update(self, timeout):
        self.calls.append(f"update-{timeout}")
        return self.serial

    def capture_stop(self):
        return self.capture

    def gateway_record(self):
        return {"seq": 1, "tag": "v1.1", "poll_ms": 4.0, "sha_ms": 0.02, "encap_ms": 13.0, "peak_rss_mb": 70.0,
                "peak_cpu_pct": 5.0} if self.record else None

    def cleanup(self):
        self.calls.append("cleanup")

    def note_result(self, status):
        self.results.append(status)


class CycleTests(unittest.TestCase):
    slot = cp.Slot("A", 1, False, 4, 0)

    def test_a_good_cycle_fills_the_table_2_and_table_3_cells(self):
        rig = FakeRig()
        row = dc.run_cycle(rig, self.slot, 28.71)
        self.assertEqual(row["status"], "ok")
        self.assertAlmostEqual(row["ttc_ms"], 630.0, places=3)
        self.assertEqual((row["static_ram_kb"], row["blocks"], row["payload_bytes"]), (28.71, 24, 22497))
        self.assertAlmostEqual(row["decrypt_recon_ms"], 446.0)
        self.assertEqual((row["poll_ms"], row["gw_ram_mb"]), (4.0, 70.0))
        self.assertEqual(rig.calls[:3], ["prepare", "publish-A", "capture"])
        self.assertEqual(rig.calls[-1], "cleanup")                                   # always revoked afterwards
        self.assertIn("update-120", rig.calls)                                       # A gets the shorter timeout

    def test_scenario_b_uses_the_longer_timeout(self):
        rig = FakeRig()
        dc.run_cycle(rig, cp.Slot("B", 1, False, 4, 0), 28.71)
        self.assertIn("update-240", rig.calls)

    def test_a_harness_error_is_invalid_and_does_not_touch_the_device(self):
        rig = FakeRig(publish_error="propose/approve failed")
        row = dc.run_cycle(rig, self.slot, 28.71)
        self.assertEqual(row["status"], "invalid")
        self.assertNotIn("capture", rig.calls)

    def test_a_release_that_never_stages_is_invalid_and_cleaned_up(self):
        rig = FakeRig(staged=False)
        self.assertEqual(dc.run_cycle(rig, self.slot, 28.71)["status"], "invalid")
        self.assertEqual(rig.calls[-1], "cleanup")

    def test_a_device_failure_is_recorded_as_failed(self):
        bad = SERIAL_OK.replace("[+9.2] [Delta] Reconstructed 288880 bytes, esp_ota_end OK.",
                                "[+9.2] [OTA] Update to v1.1 FAILED: flash write failed")
        self.assertEqual(dc.run_cycle(FakeRig(serial=bad), self.slot, 28.71)["status"], "failed")

    def test_a_gateway_only_cycle_needs_no_device(self):
        rig = FakeRig()
        row = dc.run_cycle(rig, cp.Slot("T3", 1, False, 4, 0), None, with_device=False)
        self.assertEqual(row["status"], "ok")
        self.assertEqual((row["poll_ms"], row["encap_ms"]), (4.0, 13.0))
        self.assertNotIn("prepare", rig.calls)
        self.assertNotIn("capture", rig.calls)
        self.assertEqual(dc.run_cycle(FakeRig(record=False), cp.Slot("T3", 1, False, 4, 0), None, with_device=False)["status"], "invalid")


class CampaignLoopTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = cp.TrialStore(Path(self._tmp.name) / "trials.csv")

    def tearDown(self):
        self._tmp.cleanup()

    def test_invalid_cycles_are_retried_up_to_the_limit_then_kept(self):
        rig = FakeRig(publish_error="chain down")
        schedule = cp.make_schedule(trials=1, warmup=0, scenarios=("A",))
        dc.run_campaign(rig, self.store, schedule, 28.71, say=lambda *_: None)
        rows = self.store.rows()
        self.assertEqual(len(rows), dc.MAX_ATTEMPTS)
        self.assertTrue(all(r["status"] == "invalid" for r in rows))

    def test_a_good_cycle_is_written_once_and_not_repeated_on_resume(self):
        rig = FakeRig()
        schedule = cp.make_schedule(trials=2, warmup=1, scenarios=("A", "B"))
        n = dc.run_campaign(rig, self.store, schedule, 28.71, git_revision="abc", say=lambda *_: None)
        self.assertEqual(n, 6)                                                       # (1 warm-up + 2) x 2 scenarios
        again = dc.run_campaign(FakeRig(), self.store, schedule, 28.71, say=lambda *_: None)
        self.assertEqual(again, 0)
        first = self.store.rows()[0]
        self.assertEqual(first["git_revision"], "abc")
        self.assertIn("ttc_ms", first)

    def test_failures_tell_the_rig_to_do_a_full_reset_next(self):
        bad = SERIAL_OK.replace("[+9.2] [Delta] Reconstructed 288880 bytes, esp_ota_end OK.",
                                "[+9.2] [OTA] Update to v1.1 FAILED: boom")
        rig = FakeRig(serial=bad)
        dc.run_campaign(rig, self.store, cp.make_schedule(trials=1, warmup=0, scenarios=("A",)), 28.71, say=lambda *_: None)
        self.assertEqual(rig.results, ["failed"])

    def test_gateway_only_campaign_with_warmup(self):
        rig = FakeRig()
        schedule = cp.make_schedule(trials=3, warmup=2, scenarios=("T3",))
        dc.run_campaign(rig, self.store, schedule, None, with_device=False, say=lambda *_: None)
        rows = self.store.rows()
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(1 for r in rows if cp.truthy(r["warmup"])), 2)
        self.assertEqual(cp.values(rows, "T3", "poll_ms"), {1: 4.0, 2: 4.0, 3: 4.0})


if __name__ == "__main__":
    unittest.main()
