from dataclasses import dataclass
import hashlib
import socket
import bsdiff4

# Port served by gateway/serve_artifacts.py (stdlib HTTP, artifacts/ dir).
ARTIFACT_HTTP_PORT = 8000


def gateway_lan_ip() -> str:
    """This host's LAN IPv4 — the address other LAN hosts download from.

    Same socket trick as the CoAP server's get_lan_ip(); kept local so this
    module stays importable without aiocoap.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


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
        
    # Placeholder only: make_release.py overwrites this with the real
    # LAN URL (http://<lan-ip>:8000/patch_<tag>.bin) once the filename
    # exists. Never ship this default anywhere user-visible.
    patch_url = "http://localhost:8000/files/patch.bin"
    
    return ReleaseResult(
        version_tag=version_tag,
        golden_hash=golden_hash,
        patch_size=patch_size,
        compression_ratio=compression_ratio,
        patch_url=patch_url
    ), patch_bytes
