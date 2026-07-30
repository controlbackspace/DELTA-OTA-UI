from enum import Enum


class StagedPatchState(Enum):
    DISCOVERED = "discovered"
    FETCHING = "fetching"
    VERIFYING = "verifying"
    SERVING = "serving"
    REVOKED = "revoked"
    PURGED = "purged"


class CompressionType(int, Enum):
    RAW = 0
    HEATSHRINK = 1
    BZ2 = 2
