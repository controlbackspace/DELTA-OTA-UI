"""Software attack matrix for SOP 3: inject a fault, ask the production check
whether it notices, and record which layer stopped it.

Layers (the defence in depth the architecture claims):
  gateway   SecurityEngine.verify_firmware_integrity: ledger state + SHA-256 of
            the downloaded bytes against the on-chain golden hash
  frame     the device's AES-CCM tag check on every block (AuthenticationFailed)
  image     the end-of-transfer image digest (esp_ota_end verifies the image's
            built-in SHA-256). MODELLED here by the SHA-256 of the rebuilt image.

Every trial is seeded, so a run can be reproduced exactly.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from secureota.gateway_runtime.security_engine import SecurityEngine

KEY = b"TEST_KEY_1234567"          # the published bench key; a throwaway here
NONCE_LEN, TAG_LEN = 13, 16


@dataclass(frozen=True)
class Attack:
    key: str
    name: str
    description: str
    expected_layer: str


ATTACKS = [
    Attack("wrong-hash", "Wrong golden hash", "the on-chain hash does not match the payload", "gateway"),
    Attack("substituted", "Payload substituted", "one bit of the downloaded payload is flipped", "gateway"),
    Attack("revoked", "Revoked release", "the ledger marks the release revoked", "gateway"),
    Attack("pending", "Not yet live", "the release has not reached 2-of-3 approvals", "gateway"),
    Attack("bitflip", "Block bit-flip", "one bit of a nonce/ciphertext/tag byte is flipped in transit", "frame"),
    Attack("truncated", "Block truncated", "a block frame is cut short in transit", "frame"),
    Attack("wrong-key", "Frame under another key", "a forger encrypts a block with a different key", "frame"),
    Attack("replay", "Replay of an authentic block", "a valid block of an OLD release replaces one block", "image"),
    Attack("reorder", "Reordered blocks", "two authentic blocks of this release are swapped", "image"),
]


class Corpus:
    """One payload encrypted into block frames, plus a second release for replays."""

    def __init__(self, seed: int = 1, payload_bytes: int = 6000):
        rng = random.Random(seed)
        self.payload = bytes(rng.randrange(256) for _ in range(payload_bytes))
        self.other = bytes(rng.randrange(256) for _ in range(payload_bytes))
        self.golden = hashlib.sha256(self.payload).hexdigest()
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "payload.bin"
        self.path.write_bytes(self.payload)
        self.frames = self._frames(self.payload, "a")
        self.other_frames = self._frames(self.other, "b")
        self.engine = SecurityEngine()

    def close(self):
        self._tmp.cleanup()

    def _frames(self, data: bytes, tag: str) -> list[bytes]:
        src, out = Path(self._tmp.name) / f"src_{tag}.bin", Path(self._tmp.name) / f"blocks_{tag}"
        src.write_bytes(data)
        with contextlib.redirect_stdout(io.StringIO()):          # the engine prints progress
            count = SecurityEngine().encrypt_blocks(src, out, KEY)
        return [(out / f"block_{i}.bin").read_bytes() for i in range(count)]

    # -- what the production code decides --------------------------------------
    def gateway_accepts(self, ledger: dict, path: Path) -> bool:
        with contextlib.redirect_stdout(io.StringIO()):
            return bool(self.engine.verify_firmware_integrity(ledger, str(path)))

    @staticmethod
    def frame_decrypts(frame: bytes, key: bytes = KEY) -> bytes | None:
        """The device's per-block check. None = rejected (tag mismatch / runt)."""
        if len(frame) < NONCE_LEN + TAG_LEN:
            return None
        try:
            return AESCCM(key).decrypt(frame[:NONCE_LEN], frame[NONCE_LEN:], None)
        except InvalidTag:
            return None

    def good_ledger(self) -> dict:
        return {"isLive": True, "isRevoked": False, "goldenHash": self.golden}

    def image_ok(self, chunks: list[bytes]) -> bool:
        return hashlib.sha256(b"".join(chunks)).hexdigest() == self.golden


def run_trial(attack: Attack, corpus: Corpus, rng: random.Random) -> dict:
    """One injected fault. Returns {'stopped_by': layer|None, 'passed_frame': bool}."""
    k = attack.key
    if k == "wrong-hash":
        h = list(corpus.golden)
        i = rng.randrange(len(h))
        h[i] = rng.choice([c for c in "0123456789abcdef" if c != h[i]])
        ok = corpus.gateway_accepts({**corpus.good_ledger(), "goldenHash": "".join(h)}, corpus.path)
        return {"stopped_by": None if ok else "gateway", "passed_frame": False}
    if k == "substituted":
        bad = bytearray(corpus.payload)
        bad[rng.randrange(len(bad))] ^= 1 << rng.randrange(8)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "payload.bin"
            p.write_bytes(bytes(bad))
            ok = corpus.gateway_accepts(corpus.good_ledger(), p)
        return {"stopped_by": None if ok else "gateway", "passed_frame": False}
    if k == "revoked":
        ok = corpus.gateway_accepts({**corpus.good_ledger(), "isRevoked": True}, corpus.path)
        return {"stopped_by": None if ok else "gateway", "passed_frame": False}
    if k == "pending":
        ok = corpus.gateway_accepts({**corpus.good_ledger(), "isLive": False}, corpus.path)
        return {"stopped_by": None if ok else "gateway", "passed_frame": False}
    if k == "bitflip":
        f = bytearray(rng.choice(corpus.frames))
        f[rng.randrange(len(f))] ^= 1 << rng.randrange(8)
        rejected = Corpus.frame_decrypts(bytes(f)) is None
        return {"stopped_by": "frame" if rejected else None, "passed_frame": not rejected}
    if k == "truncated":
        f = rng.choice(corpus.frames)
        rejected = Corpus.frame_decrypts(f[: rng.randrange(1, len(f))]) is None
        return {"stopped_by": "frame" if rejected else None, "passed_frame": not rejected}
    if k == "wrong-key":
        forged_key = bytes(rng.randrange(256) for _ in range(16))
        nonce = os.urandom(NONCE_LEN)
        forged = nonce + AESCCM(forged_key).encrypt(nonce, bytes(rng.randrange(256) for _ in range(1024)), None)
        rejected = Corpus.frame_decrypts(forged) is None
        return {"stopped_by": "frame" if rejected else None, "passed_frame": not rejected}
    if k in ("replay", "reorder"):
        frames = list(corpus.frames)
        i = rng.randrange(len(frames))
        if k == "replay":
            frames[i] = corpus.other_frames[i]
        else:
            j = rng.choice([x for x in range(len(frames)) if x != i])
            frames[i], frames[j] = frames[j], frames[i]
        plain = [Corpus.frame_decrypts(f) for f in frames]
        if any(p is None for p in plain):                       # caught per block
            return {"stopped_by": "frame", "passed_frame": False}
        # Every frame is authentic: the AEAD cannot object. The image digest can.
        return {"stopped_by": None if corpus.image_ok(plain) else "image", "passed_frame": True}
    raise ValueError(f"unknown attack {k}")


def run_matrix(trials: int, seed: int = 20261003) -> list[dict]:
    """Run every attack `trials` times. One row per attack."""
    corpus = Corpus(seed=1)
    rows = []
    try:
        for a in ATTACKS:
            rng = random.Random(f"{seed}:{a.key}")
            layers: dict[str, int] = {}
            passed_frame = 0
            for _ in range(trials):
                r = run_trial(a, corpus, rng)
                layers[r["stopped_by"] or "NONE"] = layers.get(r["stopped_by"] or "NONE", 0) + 1
                passed_frame += r["passed_frame"]
            stopped = trials - layers.get("NONE", 0)
            rows.append({
                "key": a.key, "name": a.name, "description": a.description,
                "expected_layer": a.expected_layer, "trials": trials, "stopped": stopped,
                "layers": layers, "authentic_frames_accepted_by_aead": passed_frame,
            })
    finally:
        corpus.close()
    return rows
