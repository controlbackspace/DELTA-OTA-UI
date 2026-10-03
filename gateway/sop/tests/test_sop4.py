import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from sop import footprint as fp
from sop import sop4
from sop.runlog import RunContext
from sop.tests.test_serial import FakeSerial, LOG

PIO_OK = """\
Processing web3_control (platform: espressif32; board: esp32dev; framework: arduino)
RAM:   [=         ]  13.2% (used 43408 bytes from 327680 bytes)
Flash: [======    ]  55.3% (used 724465 bytes from 1310720 bytes)
========================= [SUCCESS] Took 14.48 seconds =========================
"""


class PioParseTests(unittest.TestCase):
    def test_summary_bytes(self):
        self.assertEqual(fp.parse_pio_summary(PIO_OK),
                         {"ram_used": 43408, "ram_total": 327680, "flash_used": 724465, "flash_total": 1310720})

    def test_missing_summary_is_an_error(self):
        with self.assertRaises(ValueError):
            fp.parse_pio_summary("nothing useful here")

    def test_group_delta_orders_by_flash_growth_and_hides_unchanged(self):
        a = {"x": {"flash": 10, "ram": 1}, "y": {"flash": 5, "ram": 0}, "z": {"flash": 7, "ram": 7}}
        b = {"x": {"flash": 110, "ram": 1}, "y": {"flash": 5, "ram": 9}, "z": {"flash": 7, "ram": 7}, "n": {"flash": 20, "ram": 0}}
        self.assertEqual(fp.group_delta(a, b), [["x", 100, 0], ["n", 20, 0], ["y", 0, 9]])

    def test_build_env_reports_failures_without_inventing_numbers(self):
        with tempfile.TemporaryDirectory() as d:
            ok = lambda *a, **k: SimpleNamespace(returncode=0, stdout=PIO_OK, stderr="")
            bad = lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="error: boom\nline2\nline3")
            r = fp.build_env(Path(d), "web3_control", Path(d) / "x.log", pio="pio", run=ok)
            self.assertTrue(r.ok)
            self.assertEqual(r.flash_used, 724465)
            r = fp.build_env(Path(d), "web3_control", Path(d) / "y.log", pio="pio", run=bad)
            self.assertFalse(r.ok)
            self.assertEqual(r.flash_used, 0)
            self.assertIn("boom", r.error)


class RunnerRecorder:
    """Stands in for subprocess.run; records commands and can fail on demand."""

    def __init__(self, fail_upload=False):
        self.calls, self.fail_upload = [], fail_upload

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        joined = " ".join(map(str, cmd))
        rc = 1 if (self.fail_upload and "-t upload" in joined) else 0
        return SimpleNamespace(returncode=rc, stdout="", stderr="")


class FakeCapture:
    behaviour = "ok"

    def __init__(self, port, baud=115200, log_path=None, serial_factory=None):
        self.log_path = log_path

    def open(self):
        return self

    def reset_board(self):
        pass

    def capture(self, seconds, until=None):
        if FakeCapture.behaviour == "boom":
            raise OSError("serial gone")
        Path(self.log_path).write_text(LOG, encoding="utf-8")
        return LOG

    def close(self):
        pass


class HwSessionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ctx = RunContext(Path(self._tmp.name) / "run")
        self.project = Path(self._tmp.name) / "fw"
        FakeCapture.behaviour = "ok"

    def tearDown(self):
        self._tmp.cleanup()

    def test_flashes_baseline_captures_then_restores_the_updater(self):
        rec = RunnerRecorder()
        out = sop4.hw_session(self.ctx, self.project, "pio", "COM7", '-DWEB3_RPC_HOST=\\"h\\"', 30, run=rec, capture_cls=FakeCapture)
        cmds = [" ".join(map(str, c)) for c, _ in rec.calls]
        self.assertIn("run -e web3_baseline -t upload --upload-port COM7", cmds[0])
        self.assertIn("flash_device.bat factory COM7", cmds[1])
        self.assertEqual(rec.calls[0][1]["env"]["PLATFORMIO_BUILD_FLAGS"], '-DWEB3_RPC_HOST=\\"h\\"')
        self.assertEqual(rec.calls[1][1]["env"]["NOPAUSE"], "1")
        self.assertTrue(out["restored"])
        self.assertEqual(len(out["parsed"]["web3"]), 2)

    def test_the_updater_is_restored_even_when_the_capture_fails(self):
        rec = RunnerRecorder()
        FakeCapture.behaviour = "boom"
        with self.assertRaises(OSError):
            sop4.hw_session(self.ctx, self.project, "pio", "COM7", "", 30, run=rec, capture_cls=FakeCapture)
        self.assertIn("flash_device.bat factory COM7", " ".join(map(str, rec.calls[-1][0])))

    def test_a_failed_upload_still_triggers_the_restore(self):
        rec = RunnerRecorder(fail_upload=True)
        with self.assertRaises(RuntimeError):
            sop4.hw_session(self.ctx, self.project, "pio", "COM7", "", 30, run=rec, capture_cls=FakeCapture)
        self.assertEqual(len(rec.calls), 2)                       # upload attempted, then restore

    def test_a_restore_that_raises_does_not_mask_the_original_error(self):
        def run(cmd, **kw):
            if "flash_device.bat" in " ".join(map(str, cmd)):
                raise OSError("no cmd")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        FakeCapture.behaviour = "boom"
        with self.assertRaises(OSError) as cm:
            sop4.hw_session(self.ctx, self.project, "pio", "COM7", "", 30, run=run, capture_cls=FakeCapture)
        self.assertIn("serial gone", str(cm.exception))


class StepTests(unittest.TestCase):
    """The whole SOP4 step with builds mocked: claims, tables, and the safe defaults."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ctx = RunContext(Path(self._tmp.name) / "run")
        sizes = {"factory": (767549, 101480), "web3_control": (724465, 43408), "web3_baseline": (881337, 46652)}

        def fake_build(project, env, log, pio=None, **kw):
            flash, ram = sizes[env]
            return fp.BuildResult(env, True, Path(self._tmp.name) / env, "", ram, 327680, flash, 1310720)
        grp = {"WiFi": {"flash": 1, "ram": 1}}
        patches = [
            mock.patch.object(fp, "find_project", return_value=Path(self._tmp.name)),
            mock.patch.object(fp, "find_pio", return_value="pio"),
            mock.patch.object(fp, "build_env", side_effect=fake_build),
            mock.patch.object(fp, "map_groups", return_value=grp),
            mock.patch.object(fp, "engine_symbols", return_value={"flash": 1873, "ram": 3260, "symbols": 10}),
            mock.patch.object(fp, "top_ram_symbols", return_value=[("g_decoder", 48984), ("g_copyBuf", 4096)]),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def test_static_claims_and_the_ram_finding(self):
        r = sop4.run(self.ctx)
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.data["incremental"]["web3"], {"flash": 156872, "ram": 3244})
        self.assertEqual(r.data["incremental"]["updater"], {"flash": 43084, "ram": 58072})
        text = " ".join(r.claims)
        self.assertIn("156,872 B of flash", text)
        self.assertIn("3.6x", text)
        self.assertIn("FINDING", text)                              # g_decoder dominates the updater's RAM
        self.assertIn("g_decoder", text)
        self.assertTrue(any("SKIPPED - hardware part: no --serial" in n for n in r.notes))
        self.assertTrue(any("lower bound" in n for n in r.notes))

    def test_serial_without_allow_flash_never_flashes(self):
        with mock.patch.object(sop4, "hw_session") as hw:
            r = sop4.run(self.ctx, serial="COM7")
        hw.assert_not_called()
        self.assertTrue(any("--allow-flash was not given" in n for n in r.notes))

    def test_dry_run_prints_the_plan_and_flashes_nothing(self):
        with mock.patch.object(sop4, "hw_session") as hw:
            r = sop4.run(self.ctx, serial="COM7", allow_flash=True, hw_dry_run=True)
        hw.assert_not_called()
        note = next(n for n in r.notes if "dry run" in n)
        self.assertIn("web3_baseline", note)
        self.assertIn("flash_device.bat factory COM7", note)

    def test_hardware_capture_adds_heap_timing_and_a_measured_claim(self):
        parsed = sop4.parse_log(LOG)
        with mock.patch.object(sop4, "hw_session", return_value={"log": "raw/serial.log", "restored": True, "parsed": parsed}):
            r = sop4.run(self.ctx, serial="COM7", allow_flash=True)
        titles = [t.caption for t in r.tables]
        self.assertIn("On-device Web3 client on the ESP32 (hardware capture)", titles)
        hw_claim = next(c for c in r.claims if "hardware" in c)
        self.assertIn(f"{190000 - 120500:,} B of heap", hw_claim)
        self.assertTrue(any("restored" in n for n in r.notes))

    def test_a_failed_hardware_part_degrades_to_a_note_not_a_crash(self):
        with mock.patch.object(sop4, "hw_session", side_effect=RuntimeError("upload failed")):
            r = sop4.run(self.ctx, serial="COM7", allow_flash=True)
        self.assertEqual(r.status, "ok")
        self.assertTrue(any("hardware part failed: upload failed" in n for n in r.notes))

    def test_failed_build_is_reported_failed(self):
        bad = fp.BuildResult("web3_baseline", False, Path("."), "pio run failed: x")
        with mock.patch.object(fp, "build_env", return_value=bad):
            r = sop4.run(self.ctx)
        self.assertEqual(r.status, "failed")
        self.assertIn("pio run failed", r.reason)

    def test_factory_capture_gives_the_engine_peak_heap(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "factory.log"
            p.write_text("[MEM] phase=stream-start free=200000 min=180000\n[MEM] phase=stream-end free=150000 min=120000\n", encoding="utf-8")
            r = sop4.run(self.ctx, factory_log=str(p))
        self.assertTrue(any("Peak heap of a Delta-OTA update stream: 60,000 B" in c for c in r.claims))

    def test_no_project_or_pio_is_skipped(self):
        with mock.patch.object(fp, "find_pio", return_value=None):
            r = sop4.run(self.ctx)
        self.assertEqual(r.status, "skipped")


if __name__ == "__main__":
    unittest.main()
