"""Shared gateway configuration (console, .bat, service, future exe).

One JSON file + environment overrides. Precedence: explicit environment
variable wins, then the config file, then built-in default. Nothing here
touches gateway behavior — it only resolves *where the gateway points*.

Keys:
  DELTA_CONTRACT_ADDRESS ... redeployed often; empty until configured.
  DELTA_RPC_URL ............ node endpoint (default localhost).
  DELTA_BIND_ADDR .......... CoAP bind (default: auto LAN IP at boot).
  SIM_LEDGER ............... "1" = simulated ledger rehearsal mode.
  DELTA_OTA_KEY ............ 128-bit AES-CCM OTA key, 32 hex chars. SECRET:
                             written only by provision_device.py --generate,
                             never printed (callers show a fingerprint).

File: %APPDATA%\\DeltaOTA\\gateway.json on Windows,
      ~/.config/deltaota/gateway.json elsewhere. Stdlib only.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

KEYS = (
    "DELTA_CONTRACT_ADDRESS",
    "DELTA_RPC_URL",
    "DELTA_BIND_ADDR",
    "SIM_LEDGER",
    "DELTA_OTA_KEY",
)

DEFAULTS = {
    "DELTA_CONTRACT_ADDRESS": "",
    "DELTA_RPC_URL": "http://127.0.0.1:8545",
    "DELTA_BIND_ADDR": "",
    "SIM_LEDGER": "",
    "DELTA_OTA_KEY": "",
}


def config_path() -> Path:
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        base = Path(os.environ["APPDATA"]) / "DeltaOTA"
    else:
        base = Path.home() / ".config" / "deltaota"
    return base / "gateway.json"


def load_config() -> dict:
    """File values merged under live environment variables (env wins)."""
    try:
        stored = json.loads(config_path().read_text())
    except (OSError, ValueError):
        stored = {}
    resolved = {}
    for key in KEYS:
        env_val = os.environ.get(key)
        if env_val is not None and env_val != "":
            resolved[key] = env_val
        elif stored.get(key):
            resolved[key] = stored[key]
        else:
            resolved[key] = DEFAULTS[key]
    return resolved


def save_config(values: dict) -> Path:
    """Persist known keys only; unknown keys are dropped, never stored."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        stored = json.loads(path.read_text())
    except (OSError, ValueError):
        stored = {}
    for key in KEYS:
        if key in values:
            stored[key] = values[key]
    path.write_text(json.dumps(stored, indent=2))
    return path


def apply_config() -> dict:
    """Seed os.environ from the config file wherever env is unset.

    Lets the untouched gateway code keep reading os.getenv exactly as today.
    Returns the resolved mapping for banners and health checks.
    """
    resolved = load_config()
    for key, value in resolved.items():
        if value and not os.environ.get(key):
            os.environ[key] = value
    return resolved


def _rpc_call(rpc_url: str, method: str, params: list, timeout: float = 5.0):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    req = urllib.request.Request(
        rpc_url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["result"]


def probe_rpc(rpc_url: str, timeout: float = 5.0) -> str:
    """Handshake check. Returns node client string or raises with context."""
    try:
        return str(_rpc_call(rpc_url, "web3_clientVersion", [], timeout))
    except Exception as exc:
        raise ConnectionError(
            f"Node unreachable at {rpc_url} ({exc}). Start it first "
            f"(demo-up.bat) and check firewall TCP 8545."
        ) from exc


def validate_contract(address: str, rpc_url: str, timeout: float = 5.0) -> None:
    """Refuse ghosts: malformed or codeless addresses raise loudly."""
    clean = (address or "").strip()
    if not clean or len(clean) != 42 or not clean.startswith("0x"):
        raise ValueError(
            f'Invalid contract address "{address}" — expected 0x + 40 hex chars. Nothing saved.'
        )
    try:
        code = _rpc_call(rpc_url, "eth_getCode", [clean, "latest"], timeout)
    except Exception as exc:
        raise ConnectionError(
            f"Cannot verify {clean}: {rpc_url} unreachable ({exc})."
        ) from exc
    if code == "0x":
        raise ValueError(
            f"No contract code at {clean} on {rpc_url} — deploy first "
            f"(npx hardhat run scripts/deploy.js --network localhost)."
        )
