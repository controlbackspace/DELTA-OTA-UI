"""Quick smoke test for domain model boundaries — run with `python quick_test.py`"""
import sys
sys.path.insert(0, ".")

from secureota.domain import (
    CompressionType,
    ReleaseManifest,
    StagedPatch,
    StagedPatchState,
    JanpatchHeader,
)


def make_manifest(version: str = "v1.1") -> ReleaseManifest:
    """Helper: a valid ReleaseManifest with 32-byte hashes"""
    return ReleaseManifest(
        version_tag=version,
        golden_hash=b"\x8e" * 32,
        base_hash=b"\x7f" * 32,
        ipfs_cid="QmXf7kp...2bCd",
        min_node_revision=1,
        signatures=[b"\x00" * 65, b"\x01" * 65],
    )


# ── 1. ReleaseManifest validation ──────────────────────────────────
print("=== ReleaseManifest boundary ===")

# Should reject short golden_hash
try:
    ReleaseManifest(
        version_tag="v1.1",
        golden_hash=b"\x00" * 31,  # only 31 bytes
        base_hash=b"\x00" * 32,
        ipfs_cid="cid",
        min_node_revision=1,
    )
    print("FAIL: should have raised on short golden_hash")
    sys.exit(1)
except ValueError:
    print("OK: invalid golden_hash rejected")

# Should accept valid manifest
m = make_manifest()
print(f"OK: ReleaseManifest created (version={m.version_tag}, sigs={len(m.signatures)})")
assert m.golden_hash == b"\x8e" * 32
assert m.base_hash == b"\x7f" * 32


# ── 2. StagedPatch state machine ───────────────────────────────────
print("\n=== StagedPatch boundary ===")

s = StagedPatch(manifest=m)
assert s.state == StagedPatchState.DISCOVERED
print(f"OK: initial state = {s.state.value}")

# Walk forward: DISCOVERED → FETCHING → VERIFYING → SERVING
s.transition(StagedPatchState.FETCHING)
print(f"OK: transitioned to {s.state.value}")

s.patch_bytes = b"\xab" * 1024  # simulate download
s.transition(StagedPatchState.VERIFYING)
print(f"OK: transitioned to {s.state.value} (patch_bytes={len(s.patch_bytes)} bytes)")

s.transition(StagedPatchState.SERVING)
print(f"OK: transitioned to {s.state.value}")

# Should reject illegal back-transition
try:
    s.transition(StagedPatchState.FETCHING)
    print("FAIL: should have raised on SERVING → FETCHING")
    sys.exit(1)
except ValueError:
    print("OK: illegal SERVING → FETCHING rejected")

# Kill-switch path
s.transition(StagedPatchState.REVOKED)
print(f"OK: transitioned to {s.state.value}")
s.transition(StagedPatchState.PURGED)
assert s.patch_bytes is not None  # purge doesn't clear bytes by default
print(f"OK: transitioned to {s.state.value} (terminal)")

# Terminal state rejects any further transition
try:
    s.transition(StagedPatchState.REVOKED)
    print("FAIL: should have raised on PURGED → REVOKED")
    sys.exit(1)
except ValueError:
    print("OK: illegal transition from terminal state rejected")

# ── 3. JanpatchHeader binary roundtrip ─────────────────────────────
print("\n=== JanpatchHeader boundary ===")

h = JanpatchHeader(
    magic=b"JNP2",
    source_size=1_200_000,
    target_size=1_250_000,
    patch_size=45_000,
    compression_type=CompressionType.HEATSHRINK,
)
wire = h.serialize()
print(f"OK: serialized to {len(wire)} bytes ({wire.hex()})")

h2 = JanpatchHeader.deserialize(wire)
assert h == h2
assert h2.compression_type == CompressionType.HEATSHRINK
print(f"OK: deserialized: magic={h2.magic} src={h2.source_size} tgt={h2.target_size} patch={h2.patch_size}")

# Should reject bad wire length
try:
    JanpatchHeader.deserialize(b"\x00" * 3)
    print("FAIL: should have raised on short wire")
    sys.exit(1)
except ValueError:
    print("OK: short wire rejected")


# ── 4. Boundary proof: ReleaseManifest → StagedPatch → Janpatch ────
print("\n=== Cross-boundary flow ===")
manifest = make_manifest("v1.1")
patch = StagedPatch(manifest=manifest)
patch.transition(StagedPatchState.FETCHING)
patch.patch_bytes = b"\x00" * 45_000
patch.transition(StagedPatchState.VERIFYING)
patch.transition(StagedPatchState.SERVING)

header = JanpatchHeader(
    magic=b"JNP2",
    source_size=1_200_000,
    target_size=1_250_000,
    patch_size=len(patch.patch_bytes),
    compression_type=CompressionType.HEATSHRINK,
)
assert patch.manifest.golden_hash == manifest.golden_hash
print(f"Boundary flow OK: {manifest.version_tag} → {patch.state.value} → wire={header.serialize().hex()[:20]}...")


print("\n=== ALL CHECKS PASSED ===")
