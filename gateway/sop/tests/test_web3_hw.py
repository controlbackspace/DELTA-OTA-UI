import tempfile
import unittest
from pathlib import Path

from sop import web3_hw


class DriverHelperTests(unittest.TestCase):
    def test_build_flags_quote_the_strings_for_the_compiler(self):
        f = web3_hw.build_flags("192.168.100.94", 8545, "0x5FbDB2315678afecb367f032d93F642f64180aa3", "v1.1", 60)
        self.assertIn('-DWEB3_RPC_HOST=\\"192.168.100.94\\"', f)
        self.assertIn("-DWEB3_RPC_PORT=8545", f)
        self.assertIn("-DWEB3_RUNS=60", f)
        self.assertIn('-DWEB3_VERSION_TAG=\\"v1.1\\"', f)

    def test_the_capture_window_scales_with_the_number_of_checks(self):
        self.assertEqual(web3_hw.capture_seconds_for(5), 120)
        self.assertEqual(web3_hw.capture_seconds_for(60), 300)

    def test_certificate_is_a_p256_certificate_for_the_lan_address(self):
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import ec
        with tempfile.TemporaryDirectory() as d:
            cert, key = Path(d) / "c.pem", Path(d) / "k.pem"
            web3_hw.make_certificate("192.168.100.94", cert, key)
            c = x509.load_pem_x509_certificate(cert.read_bytes())
            self.assertIsInstance(c.public_key(), ec.EllipticCurvePublicKey)
            self.assertEqual(c.public_key().curve.name, "secp256r1")
            san = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            self.assertEqual([str(i) for i in san.get_values_for_type(x509.IPAddress)], ["192.168.100.94"])
            self.assertIn(b"PRIVATE KEY", key.read_bytes())

    def test_flashing_needs_explicit_authorisation(self):
        self.assertEqual(web3_hw.main(["--serial", "COM3", "--lan-ip", "10.0.0.2"]), 2)


if __name__ == "__main__":
    unittest.main()
