from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .enums import CompressionType, StagedPatchState

Bytes32 = bytes  # SHA-256 digest; exactly 32 bytes at runtime


@dataclass(frozen=True)
class ReleaseManifest:
    version_tag: str
    golden_hash: Bytes32
    base_hash: Bytes32
    ipfs_cid: str
    min_node_revision: int
    signatures: list[bytes] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name, value in [("golden_hash", self.golden_hash), ("base_hash", self.base_hash)]:
            if len(value) != 32:
                raise ValueError(
                    f"{name} must be exactly 32 bytes, got {len(value)}"
                )


@dataclass
class StagedPatch:
    manifest: ReleaseManifest
    state: StagedPatchState = StagedPatchState.DISCOVERED
    patch_bytes: Optional[bytes] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0

    def transition(self, to: StagedPatchState) -> None:
        valid: dict[StagedPatchState, set[StagedPatchState]] = {
            StagedPatchState.DISCOVERED: {StagedPatchState.FETCHING},
            StagedPatchState.FETCHING: {StagedPatchState.VERIFYING, StagedPatchState.REVOKED, StagedPatchState.PURGED},
            StagedPatchState.VERIFYING: {StagedPatchState.SERVING, StagedPatchState.REVOKED, StagedPatchState.PURGED},
            StagedPatchState.SERVING: {StagedPatchState.REVOKED, StagedPatchState.PURGED},
            StagedPatchState.REVOKED: {StagedPatchState.PURGED},
            StagedPatchState.PURGED: set(),
        }
        allowed = valid.get(self.state, set())
        if to not in allowed:
            raise ValueError(
                f"Invalid transition: {self.state.value} -> {to.value}"
            )
        self.state = to


@dataclass(frozen=True)
class JanpatchHeader:
    magic: bytes
    source_size: int
    target_size: int
    patch_size: int
    compression_type: CompressionType

    WIRE_FORMAT = "<4sIIIB"

    def __post_init__(self) -> None:
        if len(self.magic) != 4:
            raise ValueError(f"magic must be exactly 4 bytes, got {len(self.magic)}")
        for name, value in [
            ("source_size", self.source_size),
            ("target_size", self.target_size),
            ("patch_size", self.patch_size),
        ]:
            if not (0 <= value <= 0xFFFFFFFF):
                raise ValueError(f"{name} must fit in uint32, got {value}")

    def serialize(self) -> bytes:
        return struct.pack(
            self.WIRE_FORMAT,
            self.magic,
            self.source_size,
            self.target_size,
            self.patch_size,
            self.compression_type.value,
        )

    @classmethod
    def deserialize(cls, data: bytes) -> JanpatchHeader:
        expected_size = struct.calcsize(cls.WIRE_FORMAT)
        if len(data) != expected_size:
            raise ValueError(
                f"expected {expected_size} bytes, got {len(data)}"
            )
        magic, source_size, target_size, patch_size, comp_raw = struct.unpack(
            cls.WIRE_FORMAT, data
        )
        try:
            comp = CompressionType(comp_raw)
        except ValueError:
            raise ValueError(f"unknown compression type: {comp_raw}")
        return cls(
            magic=magic,
            source_size=source_size,
            target_size=target_size,
            patch_size=patch_size,
            compression_type=comp,
        )
