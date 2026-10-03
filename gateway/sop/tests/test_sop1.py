import unittest

from sop import sop1


class WireModelTests(unittest.TestCase):
    def test_request_size_matches_the_frame_layout(self):
        # 4 header + (1+5 'patch') + (1+len('b=0')=3)  = 14
        self.assertEqual(sop1.coap_request_bytes(0), 14)
        self.assertEqual(sop1.coap_request_bytes(10), 15)      # 'b=10'
        self.assertEqual(sop1.coap_request_bytes(158), 16)     # 'b=158'

    def test_response_size_adds_marker_nonce_and_tag(self):
        # 4 header + 1 marker + 13 nonce + chunk + 16 tag
        self.assertEqual(sop1.coap_response_bytes(1024), 4 + 1 + 13 + 1024 + 16)

    def test_block_count_rounds_up_and_is_at_least_one(self):
        self.assertEqual(sop1.blocks_for(0), 1)
        self.assertEqual(sop1.blocks_for(1), 1)
        self.assertEqual(sop1.blocks_for(1024), 1)
        self.assertEqual(sop1.blocks_for(1025), 2)
        self.assertEqual(sop1.blocks_for(23614), 24)           # the real v1.1 DOTA stream

    def test_wire_bytes_of_a_two_block_stream(self):
        w = sop1.wire_bytes(1500)       # blocks of 1024 and 476
        expected_coap = (
            sop1.coap_request_bytes(0) + sop1.coap_response_bytes(1024)
            + sop1.coap_request_bytes(1) + sop1.coap_response_bytes(476)
        )
        self.assertEqual(w["blocks"], 2)
        self.assertEqual(w["coap"], expected_coap)
        self.assertEqual(w["l4"], expected_coap + 2 * 2 * sop1.UDP_IP_HEADERS)

    def test_airtime_and_duration_format(self):
        self.assertAlmostEqual(sop1.airtime_s(31250, 250_000), 1.0)   # 250 kbit in 1 s
        self.assertEqual(sop1.fmt_duration(4.24), "4.2 s")
        self.assertEqual(sop1.fmt_duration(84.0), "1.4 min")


class MeasurePairTests(unittest.TestCase):
    def test_small_pair_round_trips_and_reports_consistent_numbers(self):
        base = bytes((i * 7) & 0xFF for i in range(40_000))
        target = bytearray(base)
        for i in range(0, 40_000, 997):
            target[i] ^= 0x55
        c = sop1.measure_pair("unit", "synthetic", base, bytes(target), repeats=2)
        self.assertTrue(c["roundtrip_ok"])
        self.assertEqual(c["target_bytes"], 40_000)
        self.assertLess(c["dota_bytes"], c["target_bytes"])
        self.assertEqual(c["blocks_full_raw"], sop1.blocks_for(40_000))
        self.assertLess(c["blocks_delta"], c["blocks_full_raw"])
        self.assertEqual(c["gen_ms"]["n"], 2)
        self.assertGreater(c["saved_vs_full_raw"], 0.5)

    def test_unrelated_data_is_honestly_worse_than_the_image(self):
        import os
        base, target = os.urandom(20_000), os.urandom(20_000)
        c = sop1.measure_pair("noise", "synthetic", base, target, repeats=1)
        self.assertTrue(c["roundtrip_ok"])
        self.assertLess(c["ratio_dota"], 0.01)       # no meaningful saving on noise


if __name__ == "__main__":
    unittest.main()
