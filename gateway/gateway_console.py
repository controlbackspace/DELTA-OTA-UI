"""DeltaOTA gateway supervisor console (terminal UI, stdlib only).

The gateway itself runs untouched as a child process; this console owns the
lifecycle around it: start/stop/restart, contract + RPC editing with live
validation, SIM/live mode, log tail, and the fresh-chain reminder flow.

  python gateway/gateway_console.py      (from the repo root)

One instance only (lockfile). Exiting stops the child first, so no orphaned
CoAP server ever squats on UDP 5683 afterwards.
"""
import collections
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "secureota" / "gateway_runtime"
sys.path.insert(0, str(RUNTIME))

from gateway_config import (  # noqa: E402
    load_config,
    probe_rpc,
    save_config,
    validate_contract,
)

LOCKFILE = Path(tempfile.gettempdir()) / "deltaota-console.lock"
LOGFILE = Path(tempfile.gettempdir()) / "deltaota-demo" / "gateway.log"
STARTUP_WAIT_S = 25


def clear() -> None:
    os.system("cls" if sys.platform == "win32" else "clear")


def key_pressed() -> bool:
    """Non-blocking keypress check (Windows + POSIX, stdlib only)."""
    try:
        if sys.platform == "win32":
            import msvcrt

            return msvcrt.kbhit()
        import select

        return bool(select.select([sys.stdin], [], [], 0)[0])
    except (ImportError, OSError, ValueError):
        return False


def follow_log(path: Path, snapshot_n: int = 15, poll_s: float = 0.5,
               stop_after_s: float | None = None) -> None:
    """Print the last snapshot_n lines, then stream appended bytes live.
    Any keypress returns to the menu. Handles truncation (child restart).
    """
    print("--- live log (any key to return) ---")
    try:
        with open(path, errors="replace") as f:
            f.seek(0, os.SEEK_END)
            pos = max(0, f.tell() - 8000)
            f.seek(pos)
            tail = collections.deque(f.read().splitlines(), maxlen=snapshot_n)
            for line in tail:
                print(line)
            pos = f.tell()
            deadline = None if stop_after_s is None else time.time() + stop_after_s
            while True:
                if key_pressed():
                    try:
                        input()
                    except (EOFError, KeyboardInterrupt):
                        pass
                    print("--- end of live log ---")
                    return
                if deadline is not None and time.time() >= deadline:
                    return
                f.seek(0, os.SEEK_END)
                end = f.tell()
                if end < pos:
                    pos = 0  # truncated/rotated: re-snapshot from head
                if end > pos:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                    print(chunk, end="" if chunk.endswith("\n") else "\n")
                time.sleep(poll_s)
    except OSError:
        print("(no log yet — start the gateway first)")


def pause(msg: str = "Press Enter to continue...") -> None:
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        print()


class Supervisor:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.log_handle = None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> bool:
        if self.running():
            print("Gateway is already running (PID %s)." % self.proc.pid)
            return True
        LOGFILE.parent.mkdir(parents=True, exist_ok=True)
        self.log_handle = open(LOGFILE, "ab", buffering=0)
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "main_gateway.py"],
            cwd=str(RUNTIME),
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            env=env,
        )
        print("Started gateway (PID %s). Waiting for bind + first poll..." % self.proc.pid)
        deadline = time.time() + STARTUP_WAIT_S
        seen_bind = seen_poll = False
        while time.time() < deadline:
            if not self.running():
                print("Gateway exited during startup (code %s). Read the log tail (7)." % self.proc.poll())
                return False
            try:
                tail = LOGFILE.read_bytes().decode(errors="replace")[-4000:]
            except OSError:
                tail = ""
            seen_bind = seen_bind or "Server active" in tail or "WARNING: bound" in tail
            seen_poll = seen_poll or "Polling ledger" in tail or "SIM_LEDGER" in tail or "polling simulated" in tail
            if seen_bind and seen_poll:
                print("Healthy: CoAP bound and ledger polling. Gateway is UP.")
                return True
            time.sleep(1)
        print("Started, but bind/poll proof did not appear within %ss — check log tail (7)." % STARTUP_WAIT_S)
        return self.running()

    def stop(self) -> None:
        if not self.running():
            print("Gateway is not running.")
            self.proc = None
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        print("Gateway stopped.")
        self.proc = None
        if self.log_handle:
            self.log_handle.close()
            self.log_handle = None

    def restart(self) -> None:
        self.stop()
        time.sleep(1)
        self.start()

    def tail(self, n: int = 25) -> None:
        try:
            lines = LOGFILE.read_text(errors="replace").splitlines()
        except OSError:
            print("(no log yet — start the gateway first)")
            return
        for line in collections.deque(lines, maxlen=n):
            print(line)

    def follow(self, stop_after_s: float | None = None) -> None:
        """Live log view: snapshot, then print appended bytes until a keypress.
        stop_after_s exists for automated tests only (default: follow forever).
        """
        follow_log(LOGFILE, stop_after_s=stop_after_s)


def show_status(sup: Supervisor) -> None:
    cfg = load_config()
    print("=" * 64)
    print("  DeltaOTA Gateway Console  |  child: %s" % ("UP" if sup.running() else "DOWN"))
    print("=" * 64)
    print("  Contract : %s" % (cfg["DELTA_CONTRACT_ADDRESS"] or "(not set)"))
    print("  RPC      : %s" % cfg["DELTA_RPC_URL"])
    print("  Bind     : %s" % (cfg["DELTA_BIND_ADDR"] or "(auto LAN IP)"))
    print("  Ledger   : %s" % ("SIMULATED (no chain)" if cfg["SIM_LEDGER"] == "1" else "LIVE chain"))
    print("-" * 64)


def edit_contract(sup: Supervisor) -> None:
    cfg = load_config()
    print("Current contract: %s" % (cfg["DELTA_CONTRACT_ADDRESS"] or "(not set)"))
    addr = input("Paste new DeltaOTA contract address (empty = cancel): ").strip()
    if not addr:
        return
    try:
        validate_contract(addr, cfg["DELTA_RPC_URL"])
    except (ValueError, ConnectionError) as exc:
        print("REFUSED: %s" % exc)
        print("Fix the node/address first — nothing was saved, child untouched.")
        return
    save_config({"DELTA_CONTRACT_ADDRESS": addr})
    os.environ["DELTA_CONTRACT_ADDRESS"] = addr
    print("Saved + verified (code present). Restarting child to take effect...")
    sup.restart()


def edit_rpc(sup: Supervisor) -> None:
    cfg = load_config()
    print("Current RPC: %s" % cfg["DELTA_RPC_URL"])
    url = input("New node RPC URL (empty = cancel): ").strip().rstrip("/")
    if not url:
        return
    try:
        ident = probe_rpc(url)
    except ConnectionError as exc:
        print("REFUSED: %s" % exc)
        print("Start the node first — nothing was saved, child untouched.")
        return
    save_config({"DELTA_RPC_URL": url})
    os.environ["DELTA_RPC_URL"] = url
    print("Saved (%s). Restarting child to take effect..." % ident)
    sup.restart()


def toggle_sim(sup: Supervisor) -> None:
    cfg = load_config()
    if cfg["SIM_LEDGER"] == "1":
        save_config({"SIM_LEDGER": ""})
        os.environ.pop("SIM_LEDGER", None)
        print("Mode -> LIVE chain. Restarting...")
    else:
        save_config({"SIM_LEDGER": "1"})
        os.environ["SIM_LEDGER"] = "1"
        print("Mode -> SIMULATED ledger (no blockchain processes). Restarting...")
    sup.restart()


def fresh_chain_flow(sup: Supervisor) -> None:
    print("Fresh chain = new addresses everywhere. In order:")
    print("  1. Restart the node (or demo-up.bat) — old chain is wiped.")
    print("  2. npx hardhat run scripts/deploy.js --network localhost")
    print("  3. Paste the fresh address below (validated before save).")
    edit_contract(sup)


def acquire_lock() -> bool:
    try:
        fd = os.open(str(LOCKFILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def main() -> int:
    if not acquire_lock():
        print("Another gateway console already holds the lock (%s)." % LOCKFILE)
        print("One supervisor per machine — use the running one.")
        return 1
    sup = Supervisor()
    try:
        while True:
            clear()
            show_status(sup)
            print("  1 Start gateway      2 Stop gateway       3 Restart")
            print("  4 Contract address   5 Node RPC URL       6 SIM/live toggle")
            print("  7 Log tail           8 Fresh-chain flow   0 Exit (stops child)")
            try:
                choice = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                choice = "0"
            if choice == "1":
                sup.start()
            elif choice == "2":
                sup.stop()
            elif choice == "3":
                sup.restart()
            elif choice == "4":
                edit_contract(sup)
            elif choice == "5":
                edit_rpc(sup)
            elif choice == "6":
                toggle_sim(sup)
            elif choice == "7":
                sup.follow()
            elif choice == "8":
                fresh_chain_flow(sup)
            elif choice == "0":
                sup.stop()
                print("Console exiting. Gateway stopped, port 5683 free.")
                return 0
            else:
                print("Unknown choice.")
            pause()
    finally:
        try:
            sup.stop()
        finally:
            try:
                LOCKFILE.unlink()
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
