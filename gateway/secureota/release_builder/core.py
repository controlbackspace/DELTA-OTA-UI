from dataclasses import dataclass
import hashlib
import bsdiff4

@dataclass
class ReleaseResult:
    version_tag: str
    golden_hash: str
    patch_size: int
    compression_ratio: float
    patch_url: str

def build_release(base_bytes: bytes, target_bytes: bytes, version_tag: str) -> ReleaseResult:
    # Generate the patch bytes
    patch_bytes = bsdiff4.diff(base_bytes, target_bytes)
    
    # Create SHA-256 hash of the patch bytes and extract the hex string
    golden_hash = hashlib.sha256(patch_bytes).hexdigest()
    
    # Get exact byte lengths
    patch_size = len(patch_bytes)
    target_size = len(target_bytes)
    
    # Calculate compression ratio safely avoiding division by zero
    if target_size == 0:
        compression_ratio = 0.0
    else:
        compression_ratio = 1.0 - (patch_size / target_size)
        
    # Hardcoded patch URL
    patch_url = "http://localhost:8000/files/patch.bin"
    
    return ReleaseResult(
        version_tag=version_tag,
        golden_hash=golden_hash,
        patch_size=patch_size,
        compression_ratio=compression_ratio,
        patch_url=patch_url
    ), patch_bytes
