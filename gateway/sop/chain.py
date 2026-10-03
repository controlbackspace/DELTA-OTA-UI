"""A throwaway local chain for experiments: start a fresh Hardhat node, deploy
DeltaOTA, and drive propose / approve / revoke with Hardhat's unlocked dev
accounts - no wallet involved. Always a fresh node on its own port, so a run
never touches the operator's real chain (port 8545).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from web3 import Web3

from .runlog import REPO_ROOT

BLOCKCHAIN_DIR = REPO_ROOT / "blockchain"
ARTIFACT = BLOCKCHAIN_DIR / "artifacts" / "contracts" / "DeltaOTA.sol" / "DeltaOTA.json"


class ChainUnavailable(RuntimeError):
    """The chain part cannot run here (tool missing, port busy, compile failed)."""


def kill_tree(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def tcp_port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def version32(tag: str) -> bytes:
    return tag.encode("utf-8").ljust(32, b"\0")


@dataclass
class Tx:
    ok: bool
    gas_used: int | None = None
    block: int | None = None
    t_sent: float = 0.0           # host wall clock (time.time()) just before sending
    t_mined: float = 0.0          # host wall clock when the receipt came back
    error: str = ""               # revert reason when ok is False


class HardhatNode:
    def __init__(self, port: int, log_path: Path):
        self.port = port
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None
        self.url = f"http://127.0.0.1:{port}"

    def start(self, timeout: float = 120.0) -> None:
        npx = shutil.which("npx")
        if not npx:
            raise ChainUnavailable("npx (Node.js) not found on PATH")
        if not tcp_port_free(self.port):
            raise ChainUnavailable(f"port {self.port} is already in use")
        if not ARTIFACT.is_file():
            res = subprocess.run([npx, "hardhat", "compile"], cwd=BLOCKCHAIN_DIR, capture_output=True, text=True)
            if res.returncode != 0 or not ARTIFACT.is_file():
                raise ChainUnavailable("hardhat compile failed: " + (res.stderr or res.stdout)[-300:])
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [npx, "hardhat", "node", "--port", str(self.port)],
            cwd=BLOCKCHAIN_DIR, stdout=log, stderr=subprocess.STDOUT,
        )
        w3 = Web3(Web3.HTTPProvider(self.url, request_kwargs={"timeout": 3}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise ChainUnavailable("hardhat node exited early - see " + str(self.log_path))
            try:
                if w3.is_connected():
                    return
            except Exception:
                pass
            time.sleep(0.5)
        self.stop()
        raise ChainUnavailable(f"hardhat node did not answer within {timeout:.0f}s")

    def stop(self) -> None:
        kill_tree(self.proc)
        self.proc = None


class Chain:
    """DeltaOTA on a fresh node. Accounts 0/1/2 are the authorized developers,
    account 3 is an outsider."""

    def __init__(self, url: str):
        self.w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))
        art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.abi, self.bytecode = art["abi"], art["bytecode"]
        self.accounts = self.w3.eth.accounts
        self.contract = None
        self.address = ""

    def deploy(self) -> str:
        factory = self.w3.eth.contract(abi=self.abi, bytecode=self.bytecode)
        h = factory.constructor(self.accounts[:3]).transact({"from": self.accounts[0]})
        rcpt = self.w3.eth.wait_for_transaction_receipt(h)
        self.address = rcpt["contractAddress"]
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)
        return self.address

    def _send(self, fn, sender_idx: int) -> Tx:
        t_sent = time.time()
        try:
            h = fn.transact({"from": self.accounts[sender_idx]})
            rcpt = self.w3.eth.wait_for_transaction_receipt(h)
        except Exception as e:                       # reverts surface at gas estimation
            return Tx(False, t_sent=t_sent, t_mined=time.time(), error=str(e)[:200])
        return Tx(rcpt["status"] == 1, rcpt["gasUsed"], rcpt["blockNumber"], t_sent, time.time(),
                  "" if rcpt["status"] == 1 else "reverted in block")

    def propose(self, tag: str, golden_hex: str, url: str, sender_idx: int = 0) -> Tx:
        return self._send(self.contract.functions.proposeRelease(
            version32(tag), bytes.fromhex(golden_hex), url), sender_idx)

    def approve(self, tag: str, sender_idx: int = 1) -> Tx:
        return self._send(self.contract.functions.approveRelease(version32(tag)), sender_idx)

    def revoke(self, tag: str, sender_idx: int = 2) -> Tx:
        return self._send(self.contract.functions.revokeRelease(version32(tag)), sender_idx)

    def release(self, tag: str) -> dict:
        v, golden, url, approvals, live, revoked = self.contract.functions.getRelease(version32(tag)).call()
        return {"approvals": approvals, "live": live, "revoked": revoked, "url": url, "golden": golden.hex()}
