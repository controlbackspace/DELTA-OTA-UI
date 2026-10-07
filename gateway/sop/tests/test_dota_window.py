import random
import unittest
import zlib

import bsdiff4

from secureota.gateway_runtime import delta_stream as ds


def _image(seed: int, size: int = 30000) -> bytes:
    rnd = random.Random(seed)
    return bytes(rnd.randrange(256) for _ in range(size))


def _far_repeat() -> bytes:
    """20 KB of noise followed by the same 20 KB: a match 20,000 bytes back, beyond a 4 KB window."""
    block = _image(7, 20000)
    return block + block


class DotaWindowTests(unittest.TestCase):
    def setUp(self):
        self.old = _image(1)
        self.new = self.old[:12000] + _image(2, 3000) + self.old[12000:]
        self.patch = bsdiff4.diff(self.old, self.new)

    def test_default_window_is_4kb_and_recorded_in_the_header(self):
        dota = ds.to_dota(self.patch)
        self.assertEqual(ds.WINDOW_BITS, 12)
        self.assertEqual(dota[:4], b"DOTA")
        self.assertEqual(dota[4], 1)                    # format version unchanged
        self.assertEqual(dota[5], 12)                   # window log2
        self.assertEqual(len(dota[:16]), 16)

    def test_delta_round_trips_with_a_4kb_decoder(self):
        dota = ds.to_dota(self.patch)
        self.assertEqual(ds.apply_dota(self.old, dota, dict_bits=12), self.new)

    def test_full_image_round_trips_with_a_4kb_decoder(self):
        dota = ds.to_dota(self.new)                     # not BSDIFF40: a full image
        self.assertEqual(ds.apply_dota(b"", dota, dict_bits=12), self.new)

    def test_the_body_never_reaches_back_further_than_the_window(self):
        image = _far_repeat()
        small = ds.full_image_to_dota(image)            # 4 KB window
        zlib.decompress(small[ds.HEADER.size:], -12)    # a 4 KB decoder can inflate it
        big = ds.full_image_to_dota(image, window_bits=15)
        with self.assertRaises(zlib.error):             # the 32 KB stream needs a 20,000-byte history
            zlib.decompress(big[ds.HEADER.size:], -12)

    def test_a_decoder_refuses_a_stream_with_a_larger_window(self):
        big = ds.full_image_to_dota(self.new, window_bits=15)
        with self.assertRaisesRegex(ValueError, "window"):
            ds.apply_dota(b"", big, dict_bits=12)
        self.assertEqual(ds.apply_dota(b"", big, dict_bits=15), self.new)   # a 32 KB decoder is fine

    def test_a_legacy_stream_without_a_window_byte_counts_as_32kb(self):
        legacy = bytearray(ds.full_image_to_dota(self.new, window_bits=15))
        legacy[5] = 0
        self.assertEqual(ds.apply_dota(b"", bytes(legacy), dict_bits=15), self.new)
        with self.assertRaises(ValueError):
            ds.apply_dota(b"", bytes(legacy), dict_bits=12)

    def test_out_of_range_windows_are_rejected(self):
        with self.assertRaises(ValueError):
            ds.full_image_to_dota(self.new, window_bits=8)
        dota = bytearray(ds.to_dota(self.patch))
        dota[5] = 8
        with self.assertRaises(ValueError):
            ds.apply_dota(self.old, bytes(dota))

    def test_a_4kb_window_costs_little_on_a_delta(self):
        small = len(ds.to_dota(self.patch))
        large = len(ds.to_dota(self.patch, window_bits=15))
        self.assertLessEqual(small, large * 1.05)


if __name__ == "__main__":
    unittest.main()
