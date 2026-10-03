"""The on-device Web3 baseline's Keccak-256 and ABI decoder, compiled with a host
C++ compiler and compared against web3's reference implementations. Skipped
when g++ or the firmware project is not available."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from eth_abi import encode
from web3 import Web3

from sop.sop1 import find_real_pair


def firmware_dir():
    pair = find_real_pair()
    return pair[0].parents[1] if pair else None


FW = firmware_dir()
GXX = shutil.which("g++") or (r"C:\msys64\ucrt64\bin\g++.exe" if Path(r"C:\msys64\ucrt64\bin\g++.exe").exists() else None)


@unittest.skipUnless(FW and GXX and (FW / "tools" / "host_test_baseline.cpp").exists(),
                     "needs g++ and the firmware project (src/baseline, tools/host_test_baseline.cpp)")
class BaselineHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls._tmp.name) / "host_test_baseline.exe"
        r = subprocess.run([GXX, "-std=c++17", "-Wall", "-Wextra", "-I", str(FW / "src" / "baseline"),
                            str(FW / "tools" / "host_test_baseline.cpp"), "-o", str(cls.exe)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("host build failed:\n" + r.stderr)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_tool(self, *args) -> str:
        return subprocess.run([str(self.exe), *args], capture_output=True, text=True).stdout.strip()

    def test_keccak_matches_web3_for_known_and_boundary_lengths(self):
        self.assertEqual(self.run_tool("keccak", ""), Web3.keccak(b"").hex().removeprefix("0x"))
        self.assertEqual(self.run_tool("keccak", ""), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        for n in (1, 3, 135, 136, 137, 200, 272, 300):       # around the 136-byte rate
            data = bytes((i * 7 + n) & 0xFF for i in range(n))
            self.assertEqual(self.run_tool("keccak-hex", data.hex()), Web3.keccak(data).hex().removeprefix("0x"), n)

    def test_function_selector_is_the_first_four_bytes(self):
        sig = "getRelease(bytes32)"
        self.assertEqual(self.run_tool("keccak", sig)[:8], Web3.keccak(text=sig).hex().removeprefix("0x")[:8])

    def encode_release(self, url: str, approvals=2, live=True, revoked=False) -> bytes:
        version = b"v1.1".ljust(32, b"\0")
        golden = bytes(range(32))
        return encode(["(bytes32,bytes32,string,uint8,bool,bool)"], [(version, golden, url, approvals, live, revoked)])

    def test_decodes_what_web3_encodes(self):
        for url, approvals, live, revoked in (
            ("http://100.101.102.103:8000/patch_v1.1.bin", 2, True, False),
            ("", 1, False, False),
            ("x" * 128, 2, False, True),
        ):
            raw = self.encode_release(url, approvals, live, revoked)
            out = self.run_tool("decode", raw.hex())
            self.assertTrue(out.startswith("ok "), out)
            self.assertIn(f"approvals={approvals} live={int(live)} revoked={int(revoked)} urllen={len(url)}", out)
            self.assertIn("golden=" + bytes(range(32)).hex(), out)
            self.assertTrue(out.endswith("url=" + url), out)

    def test_long_urls_are_truncated_safely_not_overflowed(self):
        out = self.run_tool("decode", self.encode_release("y" * 500).hex())
        self.assertIn("urllen=500", out)
        self.assertTrue(out.endswith("url=" + "y" * 128), "copy is capped at the 128-char buffer")

    def test_hostile_replies_are_rejected(self):
        good = self.encode_release("http://h/p.bin")
        cases = {
            "truncated": good[:100],
            "empty": b"",
            "huge string length": good[:-64] + (2**31).to_bytes(32, "big") + good[-32:],
            "offset beyond buffer": (10_000).to_bytes(32, "big") + good[32:],
            "bool not 0/1": good[:32 + 128] + (7).to_bytes(32, "big") + good[32 + 160:],
        }
        for name, raw in cases.items():
            self.assertEqual(self.run_tool("decode", raw.hex()).split()[0], "fail", name)


if __name__ == "__main__":
    unittest.main()
