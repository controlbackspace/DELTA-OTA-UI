import tempfile
import unittest
from pathlib import Path

from sop.serial_capture import SerialCapture
from sop.serial_parse import parse_log, peak_heap, split_stamp

LOG = """\
[+0.010]
[+0.020] === SOP4 baseline: on-device Web3 (HTTPS + keccak + eth_call) ===
[+0.030] [MEM] phase=boot free=250000 min=248000
[+3.100] [MEM] phase=wifi-up free=190000 min=185000
[+3.110] [MEM] phase=web3-start free=190000 min=185000
[+5.900] [Web3] run=0 tls_connect_ms=2100 request_ms=640 keccak_us=210 decode_us=95 ok=1 approvals=2 live=1 revoked=0
[+6.000] [MEM] phase=web3-run free=186000 min=121000
[+9.500] [Web3] run=1 tls_connect_ms=1900 ok=0 why=connect
[+15.000] [MEM] phase=web3-end free=187000 min=120500
[+15.010] [Web3] summary ok=1/2
[+15.020] [SOP4] done
[+16.000] [Metrics] decrypt n=743 avg=3069us min=1495us max=3730us.
[+17.000] === Delta-OTA updater factory-1.0 (factory partition) ===
[+17.100] [Health] Application: v1.1
[+17.200] [OTA] Update available: v1.0 -> v1.1
"""


class ParseTests(unittest.TestCase):
    def test_parses_every_line_kind(self):
        d = parse_log(LOG)
        self.assertEqual([m["phase"] for m in d["mem"]], ["boot", "wifi-up", "web3-start", "web3-run", "web3-end"])
        self.assertEqual(d["mem"][3], {"t": 6.0, "phase": "web3-run", "free": 186000, "min": 121000})
        self.assertEqual(len(d["web3"]), 2)
        self.assertEqual(d["web3"][0]["tls_connect_ms"], 2100)
        self.assertEqual(d["web3"][0]["approvals"], 2)
        self.assertTrue(d["web3"][0]["ok"])
        self.assertFalse(d["web3"][1]["ok"])
        self.assertEqual(d["web3"][1]["why"], "connect")
        self.assertIsNone(d["web3"][1]["request_ms"])
        self.assertEqual(d["metrics"], [{"t": 16.0, "n": 743, "avg_us": 3069, "min_us": 1495, "max_us": 3730}])
        self.assertEqual(d["app_version"], "v1.1")
        self.assertEqual(d["updates"], [{"t": 17.2, "from": "v1.0", "to": "v1.1"}])
        self.assertEqual(len(d["banners"]), 2)

    def test_unstamped_lines_and_noise_are_fine(self):
        d = parse_log("junk\n[MEM] phase=a free=10 min=9\n\n[WiFi] Connected.\n")
        self.assertEqual(d["mem"], [{"t": None, "phase": "a", "free": 10, "min": 9}])
        self.assertEqual(split_stamp("[+1.500] x"), (1.5, "x"))
        self.assertEqual(split_stamp("x"), (None, "x"))

    def test_peak_heap_exact_when_the_phase_set_a_new_low(self):
        mem = parse_log(LOG)["mem"]
        p = peak_heap(mem, "web3-start", "web3-end")
        self.assertEqual(p["peak_bytes"], 190000 - 120500)
        self.assertTrue(p["exact"])
        self.assertEqual(p["class2_peak"], 185000 - 120500)

    def test_peak_heap_is_flagged_inexact_when_the_low_was_set_earlier(self):
        mem = [{"phase": "s", "free": 100, "min": 50, "t": None}, {"phase": "e", "free": 90, "min": 50, "t": None}]
        p = peak_heap(mem, "s", "e")
        self.assertFalse(p["exact"])
        self.assertEqual(p["peak_bytes"], 50)

    def test_missing_markers_are_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):
            peak_heap(parse_log(LOG)["mem"], "web3-start", "nope")


class FakeSerial:
    def __init__(self, port, baud, timeout=None, data=b""):
        self.data, self.dtr, self.rts, self.closed = bytearray(data), True, False, False
        self.rts_log = []

    def read(self, n):
        out, self.data = bytes(self.data[:n]), self.data[n:]
        return out

    def close(self):
        self.closed = True


class CaptureTests(unittest.TestCase):
    def make(self, payload: bytes, log=None):
        holder = {}

        def factory(port, baud, timeout=None):
            holder["s"] = FakeSerial(port, baud, timeout, payload)
            return holder["s"]
        return SerialCapture("COM9", log_path=log, serial_factory=factory).open(), holder

    def test_lines_are_host_stamped_and_logged(self):
        with tempfile.TemporaryDirectory() as d:
            cap, _ = self.make(b"hello\r\n[MEM] phase=x free=1 min=1\r\npartial", Path(d) / "cap.log")
            text = cap.capture(0.3)
            self.assertEqual(len(text.splitlines()), 2)          # the unterminated tail is not a line yet
            self.assertRegex(text.splitlines()[0], r"^\[\+\d+\.\d{3}\] hello$")
            self.assertEqual((Path(d) / "cap.log").read_text(encoding="utf-8"), text)
            self.assertEqual(parse_log(text)["mem"][0]["phase"], "x")

    def test_stops_early_on_the_until_pattern(self):
        cap, _ = self.make(b"a\nb\n[SOP4] done\nc\n")
        text = cap.capture(5.0, until=r"\[SOP4\] done")
        self.assertTrue(text.strip().endswith("[SOP4] done"))
        self.assertNotIn("] c", text)

    def test_reset_pulses_en_and_close_releases_the_port(self):
        cap, h = self.make(b"")
        cap.reset_board()
        self.assertFalse(h["s"].rts)
        self.assertFalse(h["s"].dtr)
        cap.close()
        self.assertTrue(h["s"].closed)


if __name__ == "__main__":
    unittest.main()
