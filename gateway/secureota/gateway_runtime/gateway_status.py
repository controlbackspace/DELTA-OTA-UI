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
  revoked_version ....... release the chain revoked while it was the newest
                          (served to devices as 4.03 on /version)
  events, event_seq ..... ring buffer of the last EVENT_LIMIT gateway log lines
                          ({id, t, msg}); the console mirrors new ones into its
                          terminal so the operator sees what the gateway sees
"""
import json
import os
import time
from pathlib import Path

from gateway_config import status_path

# One fixed location (the per-user config dir), NOT the artifact dir: the exe,
# the plain-Python gateway and a separately started serve_artifacts.py each
# have a different artifact dir, and the feed was invisible whenever they
# disagreed. DELTA_STATUS_FILE overrides it.
STATUS_FILE = status_path()

_state: dict = {}
EVENT_LIMIT = 200
_last_once: dict = {}


def update(**fields) -> None:
    """Merge fields and rewrite the file atomically. A failed write (e.g. the
    artifact server holding the file open on Windows) is skipped - the next
    update rewrites everything, so nothing is lost but a heartbeat."""
    _state.update(fields)
    _state["updated_at"] = time.time()
    tmp = STATUS_FILE.with_name(STATUS_FILE.name + ".tmp")
    payload = json.dumps(_state)
    err = None
    # Windows: os.replace fails while the artifact server has the file open for
    # a read. That window is milliseconds, so retry briefly before giving up.
    for _ in range(5):
        try:
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(payload)
            os.replace(tmp, STATUS_FILE)
            return
        except OSError as e:
            err = e
            time.sleep(0.02)
    print(f"[Status] Could not write {STATUS_FILE.name}: {err}")


def event_once(key: str, msg: str, **fields) -> None:
    """Like event(), but silent while `key` keeps the same message: loop
    heartbeats ("still waiting") must not flood the console every 5 s. Fields
    are always applied."""
    if _last_once.get(key) == msg:
        update(**fields)
        return
    _last_once[key] = msg
    event(msg, **fields)


def event(msg: str, **fields) -> None:
    """Record one human-readable gateway event (and any status fields) in the
    status file's ring buffer."""
    seq = int(_state.get("event_seq", 0)) + 1
    events = list(_state.get("events", []))[-(EVENT_LIMIT - 1):]
    events.append({"id": seq, "t": time.time(), "msg": msg})
    update(events=events, event_seq=seq, **fields)


def reset_device_progress() -> None:
    """New release staged: block progress from the previous release is void.
    The device's last reported version is kept - it is still true."""
    update(device_ip=None, device_last_block=None, device_final_sent=False,
           device_last_seen=None)
