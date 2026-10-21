import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sop import campaign, device_cycle as dc
from sop.tests.test_naked_baseline import FakeRig


class ScriptedSerial:
    """Stands in for SerialCapture: returns the scripted text of each capture() call and records resets."""

    def __init__(self, pre, after):
        self.pre, self.after = pre, after
        self.calls, self.resets, self.log_path = [], 0, None

    def capture(self, seconds, until=None):
        self.calls.append((seconds, until))
        return self.pre if len(self.calls) == 1 else self.after

    def reset_board(self):
        self.resets += 1


def make_rig(tmp: Path, ser):
    rig = object.__new__(dc.LocalRig)
    rig.ctx = SimpleNamespace(sub=lambda name: tmp)
    rig._label, rig._stamp, rig.ser, rig._tshark = "A-c001", 1, ser, None
    rig.started_unprompted = False
    return rig


IDLE = "[+0.5] [App] v1.0 alive, uptime 20s, free heap 345668 B\n"
STARTED = "[+0.0] [OTA] Update available: v1.0 -> v1.1\n[+0.0] [OTA] Backing up ota_0 -> ota_1 (279328 bytes)...\n[+0.0] [CoAP] Requesting block 0...\n"
DONE = "[+9.0] [Delta] Reconstructed 288880 bytes, esp_ota_end OK.\n[+12.0] [Health] Application: v1.1\n"


class RunUpdateTests(unittest.TestCase):
    def test_an_idle_device_is_reset_to_start_the_update(self):
        with tempfile.TemporaryDirectory() as d:
            ser = ScriptedSerial(IDLE, STARTED + DONE)
            rig = make_rig(Path(d), ser)
            text = rig.run_update(120)
            self.assertEqual(ser.resets, 1)
            self.assertFalse(rig.started_unprompted)
            self.assertEqual(text, IDLE + STARTED + DONE)
            self.assertEqual(ser.calls[1][1], r"Application: v1\.1")
            self.assertEqual((Path(d) / "cycle-A-c001-1.serial.log").read_text(encoding="utf-8"), text)

    def test_a_device_that_already_began_is_never_reset(self):
        with tempfile.TemporaryDirectory() as d:
            ser = ScriptedSerial(IDLE + STARTED, DONE)
            rig = make_rig(Path(d), ser)
            text = rig.run_update(120)
            self.assertEqual(ser.resets, 0)                      # a reset here would interrupt the ota_0 -> ota_1 backup
            self.assertTrue(rig.started_unprompted)
            self.assertEqual(text, IDLE + STARTED + DONE)
            self.assertEqual((Path(d) / "cycle-A-c001-1.serial.log").read_text(encoding="utf-8"), text)

    def test_an_update_that_already_finished_needs_no_more_reading(self):
        with tempfile.TemporaryDirectory() as d:
            ser = ScriptedSerial(STARTED + DONE, "SHOULD NOT BE READ")
            rig = make_rig(Path(d), ser)
            text = rig.run_update(120)
            self.assertEqual(ser.resets, 0)
            self.assertEqual(len(ser.calls), 1)
            self.assertEqual(text, STARTED + DONE)

    def test_the_flag_is_cleared_for_the_next_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            rig = make_rig(Path(d), ScriptedSerial(IDLE + STARTED, DONE))
            rig.run_update(120)
            self.assertTrue(rig.started_unprompted)
            rig.ser = ScriptedSerial(IDLE, STARTED + DONE)
            rig.run_update(120)
            self.assertFalse(rig.started_unprompted)


class OrderingFakeRig(FakeRig):
    capture_before_publish = True

    def __init__(self):
        super().__init__()
        self.events = []
        self.started_unprompted = False

    def set_label(self, label):
        pass

    def capture_start(self):
        self.events.append("capture_start")

    def publish(self, scenario):
        self.events.append("publish")
        return {"payload_bytes": 22497}

    def run_update(self, timeout):
        self.events.append("run_update")
        return super().run_update(timeout)

    def capture_abort(self):
        self.events.append("capture_abort")


class RunCycleOrderTests(unittest.TestCase):
    def test_the_capture_starts_before_the_release_is_published_and_only_once(self):
        rig = OrderingFakeRig()
        row = dc.run_cycle(rig, campaign.Slot("A", 1, False, 1, 0), 28.73)
        self.assertEqual(rig.events, ["capture_start", "publish", "run_update"])
        self.assertEqual(row["status"], "ok")

    def test_a_note_says_when_the_device_began_on_its_own(self):
        rig = OrderingFakeRig()
        rig.started_unprompted = True
        row = dc.run_cycle(rig, campaign.Slot("A", 1, False, 1, 0), 28.73)
        self.assertIn("not reset", row["note"])

    def test_a_cycle_that_ends_before_the_update_stops_the_early_capture(self):
        rig = OrderingFakeRig()
        rig.wait_staged = lambda: {"ok": False}
        row = dc.run_cycle(rig, campaign.Slot("A", 1, False, 1, 0), 28.73)
        self.assertEqual(row["status"], "invalid")
        self.assertIn("capture_abort", rig.events)

    def test_rigs_without_the_flag_keep_the_old_order(self):
        rig = FakeRig()
        events = []
        rig.capture_start = lambda: events.append("capture_start")
        rig.publish = lambda s: (events.append("publish"), {"payload_bytes": 1})[1]
        dc.run_cycle(rig, campaign.Slot("A", 1, False, 1, 0), 28.73)
        self.assertEqual(events, ["publish", "capture_start"])


if __name__ == "__main__":
    unittest.main()
