import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from secureota.gateway_runtime.security_engine import SecurityEngine
from sop import campaign, device_cycle as dc

KEY = bytes(range(16))
PAYLOAD = bytes((i * 7) % 251 for i in range(2500))              # 3 blocks of 1,024 / 1,024 / 452


class NakedFramingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.src = self.d / "payload.bin"
        self.src.write_bytes(PAYLOAD)
        self._env = {k: os.environ.pop(k, None) for k in ("DELTA_NAKED", "DELTA_NAKED_FILE")}

    def tearDown(self):
        for k, v in self._env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        self._tmp.cleanup()

    def frames(self, out):
        return [(out / f"block_{i}.bin").read_bytes() for i in range(3)]

    def test_secured_frames_are_nonce_ciphertext_tag(self):
        out = self.d / "secured"
        self.assertEqual(SecurityEngine().encrypt_blocks(self.src, out, KEY), 3)
        sizes = [len(f) for f in self.frames(out)]
        self.assertEqual(sizes, [1024 + 29, 1024 + 29, 452 + 29])                 # 13 B nonce + 16 B tag per block

    def test_naked_frames_are_the_plaintext_blocks_alone(self):
        os.environ["DELTA_NAKED"] = "1"
        out = self.d / "naked"
        self.assertEqual(SecurityEngine().encrypt_blocks(self.src, out, KEY), 3)
        f = self.frames(out)
        self.assertEqual(b"".join(f), PAYLOAD)
        self.assertEqual([len(x) for x in f], [1024, 1024, 452])

    def test_the_naked_flag_file_switches_the_mode_without_a_restart(self):
        flag = self.d / "naked.flag"
        os.environ["DELTA_NAKED_FILE"] = str(flag)
        eng = SecurityEngine()
        self.assertFalse(eng.naked_mode())                                        # no file: secured
        flag.write_text("1", encoding="utf-8")
        self.assertTrue(eng.naked_mode())
        flag.write_text("0", encoding="utf-8")
        self.assertFalse(eng.naked_mode())
        flag.unlink()
        self.assertFalse(eng.naked_mode())

    def test_naked_mode_saves_exactly_29_bytes_per_block(self):
        secured, naked = self.d / "s", self.d / "n"
        SecurityEngine().encrypt_blocks(self.src, secured, KEY)
        os.environ["DELTA_NAKED"] = "1"
        SecurityEngine().encrypt_blocks(self.src, naked, KEY)
        total = lambda p: sum(len(f) for f in self.frames(p))
        self.assertEqual(total(secured) - total(naked), 29 * 3)


class SchedulingAndRowsTests(unittest.TestCase):
    def test_a_and_n_are_interleaved_in_the_same_rounds(self):
        slots = campaign.make_schedule(trials=4, warmup=1, seed=7, scenarios=("A", "N"))
        rounds = {}
        for s in slots:
            rounds.setdefault(s.round, []).append(s.scenario)
        self.assertEqual(len(rounds), 5)
        self.assertTrue(all(sorted(v) == ["A", "N"] for v in rounds.values()))
        self.assertEqual({s.scenario for s in slots if s.warmup}, {"A", "N"})

    def test_ab_schedules_are_unchanged_by_the_new_scenario(self):
        ab = campaign.make_schedule(trials=6, warmup=2, seed=20261015, scenarios=("A", "B"))
        self.assertTrue(all(s.scenario in ("A", "B") for s in ab))
        self.assertEqual(ab, campaign.make_schedule(trials=6, warmup=2, seed=20261015, scenarios=("A", "B")))

    def test_the_delta_is_the_payload_of_a_and_n_but_not_of_b(self):
        self.assertEqual(dc.DELTA_SCENARIOS, ("A", "N"))
        self.assertIn("N", dc.UPDATE_TIMEOUT_S)


class FakeRig:
    lan_ip = "192.168.100.94"
    image_sha256 = "abc"

    def __init__(self):
        self.scenarios = []

    def set_scenario(self, s):
        self.scenarios.append(s)

    def prepare(self):
        pass

    def publish(self, scenario):
        return {"payload_bytes": 22497}

    def wait_staged(self):
        return {"ok": True, "blocks": 24, "stage_ms": 10}

    def set_label(self, label):
        pass

    def capture_start(self):
        pass

    def run_update(self, timeout):
        return ("=== Delta-OTA updater factory-1.0 (factory partition) ===\n[OTA] Update available: v1.0 -> v1.1\n"
                "[Metrics2] decrypt_us=2 feed_us=1700000 flash_us=1500000 flash_bytes=288880 stream_us=5600000 blocks=24\n"
                "[Delta] Reconstructed 288880 bytes, esp_ota_end OK.\n[Health] Application: v1.1\n")

    def capture_stop(self):
        t = 1000.0
        rows = [f"{t}\t192.168.100.181\t192.168.100.94\t1\tpatch\tb=0\t60", f"{t + 5.6}\t192.168.100.94\t192.168.100.181\t68\t\t\t1000"]
        return "\n".join(rows)

    def gateway_record(self):
        return None

    def cleanup(self):
        pass


class RunCycleTests(unittest.TestCase):
    def test_static_ram_can_differ_per_scenario(self):
        rig = FakeRig()
        slot_n = campaign.Slot("N", 1, False, 4, 1)
        row = dc.run_cycle(rig, slot_n, {"A": 28.73, "N": 27.66})
        self.assertEqual(rig.scenarios, ["N"])
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["static_ram_kb"], 27.66)
        self.assertEqual(row["image_sha256"], "abc")
        row_a = dc.run_cycle(FakeRig(), campaign.Slot("A", 1, False, 4, 0), {"A": 28.73, "N": 27.66})
        self.assertEqual(row_a["static_ram_kb"], 28.73)

    def test_a_single_figure_still_works_for_ab_campaigns(self):
        row = dc.run_cycle(FakeRig(), campaign.Slot("A", 1, False, 1, 0), 28.73)
        self.assertEqual(row["static_ram_kb"], 28.73)


class UpdaterSwitchingTests(unittest.TestCase):
    def make_rig(self, tmp: Path):
        rig = object.__new__(dc.LocalRig)
        rig.ctx = SimpleNamespace(sub=lambda name: tmp)
        rig.project, rig.serial_port, rig.pio = tmp, "COM3", str(tmp / ".platformio" / "penv" / "Scripts" / "pio.exe")
        rig.work = tmp
        rig._updater, rig.scenario, rig.naked = "factory", "A", True
        rig.updater_sha256 = {"secured": "s" * 64, "naked": "n" * 64}
        rig.image_sha256 = ""
        rig.ser = SimpleNamespace(close=lambda: None)
        return rig

    def test_the_naked_updater_is_flashed_once_and_then_kept(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dc.subprocess, "run") as run, \
                mock.patch("sop.serial_capture.SerialCapture") as cap:
            run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            cap.return_value.open.return_value = SimpleNamespace(close=lambda: None)
            rig = self.make_rig(Path(d))
            rig.set_scenario("N")
            rig._ensure_updater()
            cmds = [" ".join(map(str, c.args[0])) for c in run.call_args_list]
            self.assertEqual(len(cmds), 2)                                      # write the image, erase otadata
            self.assertIn("write_flash", cmds[0])
            self.assertIn("0x10000", cmds[0])
            self.assertIn("factory_naked", cmds[0])
            self.assertIn("erase_region 0xd000 0x2000", cmds[1])
            self.assertEqual(rig._updater, "naked")
            cap.assert_not_called()                                             # the serial port is reopened once, by prepare()
            self.assertEqual(rig.image_sha256, "n" * 64)
            self.assertEqual((Path(d) / "naked.flag").read_text(), "1")
            rig._ensure_updater()                                               # a second N cycle: no new flashing
            self.assertEqual(len(run.call_args_list), 2)

    def test_going_back_to_a_flashes_the_secured_updater_and_clears_the_flag(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dc.subprocess, "run") as run, \
                mock.patch("sop.serial_capture.SerialCapture") as cap:
            run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            rig = self.make_rig(Path(d))
            rig._updater = "naked"
            rig.set_scenario("A")
            rig._ensure_updater()
            first = " ".join(map(str, run.call_args_list[0].args[0]))
            self.assertIn("firmware.bin", first)
            self.assertNotIn("factory_naked", first)
            self.assertEqual(rig._updater, "factory")
            self.assertEqual(rig.image_sha256, "s" * 64)
            self.assertEqual((Path(d) / "naked.flag").read_text(), "0")

    def test_a_flash_failure_is_a_harness_fault_after_one_slower_retry(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dc.subprocess, "run") as run:
            run.return_value = SimpleNamespace(returncode=2, stdout="", stderr="boom")
            rig = self.make_rig(Path(d))
            with self.assertRaises(dc.RigError):
                rig._flash_updater("naked")
            cmds = [" ".join(map(str, c.args[0])) for c in run.call_args_list]
            self.assertEqual(len(cmds), 2)
            self.assertIn("--baud 460800", cmds[0])
            self.assertNotIn("--baud", cmds[1])

    def test_the_fast_flash_is_used_first_and_a_failure_falls_back_to_the_default_speed(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dc.subprocess, "run") as run:
            results = [SimpleNamespace(returncode=1, stdout="", stderr="fail"), SimpleNamespace(returncode=0, stdout="", stderr=""),
                       SimpleNamespace(returncode=0, stdout="", stderr="")]
            run.side_effect = results
            rig = self.make_rig(Path(d))
            rig._flash_updater("naked")
            cmds = [" ".join(map(str, c.args[0])) for c in run.call_args_list]
            self.assertEqual(len(cmds), 3)                                      # fast try, slow retry, otadata erase
            self.assertIn("erase_region", cmds[2])
            self.assertEqual(rig._updater, "naked")


    def test_the_updater_in_the_board_is_unknown_at_start_so_the_first_cycle_always_flashes(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(dc.subprocess, "run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
            rig = self.make_rig(Path(d))
            rig._updater = None
            rig.set_scenario("A")
            rig._ensure_updater()
            self.assertEqual(len(run.call_args_list), 2)
            self.assertEqual(rig._updater, "factory")


if __name__ == "__main__":
    unittest.main()
