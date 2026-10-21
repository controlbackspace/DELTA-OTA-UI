import ssl
import tempfile
import unittest
import urllib.request
from pathlib import Path

from sop import https_hw as hh
from sop.serial_parse import parse_log

SERVER, DEVICE = "192.168.100.94", "192.168.100.181"


def pkt(stream, t, src, dst, ip_len, tcp_len, syn=0):
    return "\t".join([str(stream), str(t), src, dst, str(ip_len), str(tcp_len), str(syn)])


CAPTURE = "\n".join([
    # stream 0: SYN at t=100.0, server data until t=102.5, FIN after
    pkt(0, 100.0, DEVICE, SERVER, 60, 0, 1), pkt(0, 100.001, SERVER, DEVICE, 60, 0, 1), pkt(0, 100.002, DEVICE, SERVER, 52, 0),
    pkt(0, 100.5, SERVER, DEVICE, 1400, 1348), pkt(0, 102.5, SERVER, DEVICE, 1400, 1348), pkt(0, 102.6, DEVICE, SERVER, 52, 0),
    pkt(0, 102.7, SERVER, DEVICE, 52, 0),
    # stream 1 starts later; its packets are listed first to prove the order comes from the start time
    pkt(1, 110.0, DEVICE, SERVER, 60, 0, 1), pkt(1, 111.0, SERVER, DEVICE, 1400, 1348),
])
SERIAL = """\
[+1.0] [HTTPS] run=0 connect_ms=1300 download_ms=2400 flash_us=1500000 flash_bytes=288880 bytes=288880 ok=1
[+5.0] [HTTPS] run=1 connect_ms=1310 download_ms=900 flash_us=1000000 flash_bytes=288880 bytes=288880 ok=1
"""


class StreamParsingTests(unittest.TestCase):
    def test_per_stream_ttc_and_wire_bytes(self):
        s = hh.parse_streams(CAPTURE, SERVER)
        self.assertEqual([x["stream"] for x in s], ["0", "1"])
        self.assertAlmostEqual(s[0]["ttc_ms"], 2500.0, places=3)                 # SYN to the last server data packet
        self.assertEqual(s[0]["wire_bytes"], 60 + 60 + 52 + 1400 + 1400 + 52 + 52)
        self.assertAlmostEqual(s[1]["ttc_ms"], 1000.0, places=3)
        self.assertTrue(s[0]["syn"])

    def test_malformed_lines_are_skipped_and_a_stream_without_server_data_has_no_ttc(self):
        s = hh.parse_streams("junk\n" + pkt(5, 1.0, DEVICE, SERVER, 60, 0, 1) + "\nx\ty\n", SERVER)
        self.assertEqual(len(s), 1)
        self.assertIsNone(s[0]["ttc_ms"])


class JoinTests(unittest.TestCase):
    def setUp(self):
        self.lines = parse_log(SERIAL)["https"]
        self.streams = hh.parse_streams(CAPTURE, SERVER)

    def test_runs_are_joined_with_their_stream_in_order(self):
        rows = hh.join_runs(self.lines, self.streams, static_ram_kb=6.18, warmup=1)
        self.assertEqual([r["status"] for r in rows], ["ok", "ok"])
        self.assertEqual((rows[0]["warmup"], rows[1]["warmup"]), (True, False))
        self.assertEqual(rows[0]["device_ms"], 3700)
        self.assertAlmostEqual(rows[0]["ttc_ms"], 2500.0)
        self.assertAlmostEqual(rows[0]["capture_minus_device_ms"], -1200.0)
        self.assertAlmostEqual(rows[0]["flash_kbps"], (288880 / 1024) / 1.5, places=2)
        self.assertEqual(rows[1]["wire_bytes"], 60 + 1400)
        self.assertEqual(rows[0]["static_ram_kb"], 6.18)

    def test_a_mismatch_between_runs_and_streams_is_never_silently_joined(self):
        rows = hh.join_runs(self.lines, self.streams[:1])
        self.assertTrue(all(r["status"] == "invalid" and "mismatch" in r["note"] for r in rows))

    def test_a_failed_device_run_is_a_failed_row(self):
        lines = parse_log("[+1.0] [HTTPS] run=0 connect_ms=1300 ok=0 why=header\n")["https"]
        rows = hh.join_runs(lines, self.streams[:1])
        self.assertEqual((rows[0]["status"], rows[0]["note"]), ("failed", "device: header"))

    def test_summary_counts_only_counted_ok_runs(self):
        rows = hh.join_runs(self.lines, self.streams, warmup=1)
        s = hh.summarise(rows)
        self.assertEqual(s["counted_ok"], 1)
        self.assertAlmostEqual(s["ttc_ms_mean"], 1000.0)


class ServerTests(unittest.TestCase):
    def test_the_server_serves_the_unmodified_image_over_tls(self):
        from sop.web3_hw import make_certificate
        image = bytes(range(256)) * 50
        with tempfile.TemporaryDirectory() as d:
            cert, key = Path(d) / "c.pem", Path(d) / "k.pem"
            make_certificate("127.0.0.1", cert, key)
            old = hh.PORT
            hh.PORT = 18549
            try:
                httpd = hh.https_server(image, cert, key)
                try:
                    unverified = ssl._create_unverified_context()
                    r = urllib.request.urlopen("https://127.0.0.1:18549/app-v1.1.bin", context=unverified, timeout=10)
                    self.assertEqual(r.read(), image)
                    self.assertEqual(r.headers["Content-Length"], str(len(image)))
                    with self.assertRaises(urllib.error.HTTPError):
                        urllib.request.urlopen("https://127.0.0.1:18549/other", context=unverified, timeout=10)
                finally:
                    httpd.shutdown()
            finally:
                hh.PORT = old

    def test_flashing_needs_explicit_authorisation(self):
        self.assertEqual(hh.main(["--serial", "COM3", "--lan-ip", "10.0.0.2"]), 2)


if __name__ == "__main__":
    unittest.main()
