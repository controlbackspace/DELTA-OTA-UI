"""Live gateway status for the console's deployment tracker.

The gateway loop (main_gateway.py) and the CoAP resources (coap_server.py)
record what is REALLY happening into artifacts/gateway_status.json; the
artifact server exposes that one file over HTTP and the desktop console polls
it. Nothing here influences gateway decisions - it is reporting only.

Fields (all optional until first written):
  gateway_state ......... starting | waiting | unreachable | staged | revoked
                          | hash-mismatch | download-failed | invalid-payload
  target_version ........ newest live release on the chain (what we follow)
  staged_version ........ release whose encrypted blocks are being served
  blocks_total .......... block frames on disk for staged_version
  contract, key_fp ...... which chain, which key (fingerprint only, never key)
  device_ip, device_last_block, device_final_sent, device_last_seen
                          ......... block-request progress seen by /patch
  device_reported_version, device_reported_ip, device_reported_at
                          ......... the version a device announced via /hello
  staged_at ............. epoch seconds when staged_version was staged
  updated_at ............ epoch seconds of the last write (heartbeat)
"""
import json
import os
import time
from pathlib import Path

STATUS_FILE = Path(__file__).resolve().parent.parent.parent / "artifacts" / "gateway_status.json"

_state: dict = {}


def update(**fields) -> None:
    """Merge fields and rewrite the file atomically. A failed write (e.g. the
    artifact server holding the file open on Windows) is skipped - the next
    update rewrites everything, so nothing is lost but a heartbeat."""
    _state.update(fields)
    _state["updated_at"] = time.time()
    tmp = STATUS_FILE.with_name(STATUS_FILE.name + ".tmp")
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(_state))
        os.replace(tmp, STATUS_FILE)
    except OSError as e:
        print(f"[Status] Could not write {STATUS_FILE.name}: {e}")


def reset_device_progress() -> None:
    """New release staged: block progress from the previous release is void.
    The device's last reported version is kept - it is still true."""
    update(device_ip=None, device_last_block=None, device_final_sent=False,
           device_last_seen=None)
