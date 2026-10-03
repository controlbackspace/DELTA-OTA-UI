"""Run the real gateway (main_gateway.py) as a subprocess against a test chain and
watch it through its own status feed (gateway_status.json + events with epoch
timestamps), the same feed the dev console reads.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .chain import kill_tree
from .coap_probe import udp_port_free
from .runlog import REPO_ROOT

RUNTIME_DIR = REPO_ROOT / "gateway" / "secureota" / "gateway_runtime"
COAP_HOST, COAP_PORT = "127.0.0.1", 5683     # the gateway's CoAP port is fixed in coap_server.py


def poll_interval_s() -> int | None:
    """The gateway's chain poll period, read from the source (it bounds how fast
    a revoke can be noticed)."""
    m = re.search(r"^POLL_INTERVAL\s*=\s*(\d+)", (RUNTIME_DIR / "main_gateway.py").read_text(encoding="utf-8"), re.M)
    return int(m.group(1)) if m else None


class GatewayProc:
    def __init__(self, rpc_url: str, contract: str, work_dir: Path, log_path: Path):
        self.work = Path(work_dir)
        self.log_path = Path(log_path)
        self.rpc_url, self.contract = rpc_url, contract
        self.status_file = self.work / "gateway_status.json"
        self.artifacts = self.work / "artifacts"
        self.proc: subprocess.Popen | None = None

    @staticmethod
    def port_free() -> bool:
        return udp_port_free(COAP_HOST, COAP_PORT)

    def start(self) -> None:
        self.artifacts.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.pop("DELTA_PAYLOAD", None)                      # bench seam: never in a measurement
        env.update({
            "DELTA_RPC_URL": self.rpc_url,
            "DELTA_CONTRACT_ADDRESS": self.contract,
            "DELTA_ARTIFACT_DIR": str(self.artifacts),
            "DELTA_STATUS_FILE": str(self.status_file),
            "DELTA_USE_TEST_KEY": "1",                      # published bench key, test only
            "DELTA_BIND_ADDR": COAP_HOST,
            "DELTA_NO_ARTIFACT_SERVER": "1",
            "SIM_LEDGER": "0",                              # a user's gateway.json must not switch on the simulator
            "PYTHONUNBUFFERED": "1",
        })
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "main_gateway.py"], cwd=RUNTIME_DIR, env=env,
            stdout=log, stderr=subprocess.STDOUT,
        )

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def status(self) -> dict:
        for _ in range(3):                                  # the file is replaced atomically; retry a torn read
            try:
                return json.loads(self.status_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                time.sleep(0.01)
        return {}

    def block_files(self) -> int:
        return len(list((self.artifacts / "blocks").glob("block_*.bin")))

    def wait_for(self, predicate, timeout: float, poll: float = 0.05):
        """Poll status() until predicate(status) is truthy; returns (value, status) or (None, status)."""
        deadline = time.time() + timeout
        st: dict = {}
        while time.time() < deadline:
            if not self.alive():
                return None, st
            st = self.status()
            v = predicate(st)
            if v:
                return v, st
            time.sleep(poll)
        return None, st

    def stop(self) -> None:
        kill_tree(self.proc)
        self.proc = None
