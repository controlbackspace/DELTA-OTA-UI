#!/usr/bin/env bash
# Delta-OTA gateway - one-shot installer for a Raspberry Pi (gateway only).
#
# The blockchain node stays on the developer PC; the Pi runs the gateway as a
# systemd service and installs a `deltaota-gateway` command for day-to-day use.
#
#   sudo bash gateway/deploy/raspberry-pi/install-gateway.sh
#
# Asks for what it needs (PC node address, contract, OTA key). Everything can
# also be passed as flags for an unattended install:
#   --rpc http://<PC-IP>:8545   --contract 0x...   --bind <Pi-IP>
#   --key <32 hex> | --generate-key        --user <service user>   --yes
#
# Safe to run again: existing values are kept as the defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="${DELTA_ENV_FILE:-/etc/delta-gateway.env}"
SERVICE_FILE="${DELTA_SERVICE_FILE:-/etc/systemd/system/gateway.service}"
CLI_PATH="${DELTA_CLI_PATH:-/usr/local/bin/deltaota-gateway}"
SERVICE_USER="${DELTA_USER:-${SUDO_USER:-}}"
SKIP_SYSTEM="${DELTA_SKIP_SYSTEM:-0}"   # tests only: skip apt/systemd

RPC="" CONTRACT="" BIND="" KEY="" GEN_KEY=0 ASSUME_YES=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rpc)          RPC="$2"; shift 2 ;;
        --contract)     CONTRACT="$2"; shift 2 ;;
        --bind)         BIND="$2"; shift 2 ;;
        --key)          KEY="$2"; shift 2 ;;
        --generate-key) GEN_KEY=1; shift ;;
        --user)         SERVICE_USER="$2"; shift 2 ;;
        --yes|-y)       ASSUME_YES=1; shift ;;
        -h|--help)      sed -n '2,15p' "$0"; exit 0 ;;
        *) echo "[ERROR] Unknown option: $1"; exit 1 ;;
    esac
done

die()  { echo "[ERROR] $*" >&2; exit 1; }
info() { echo "==> $*"; }

[[ $EUID -eq 0 || "$SKIP_SYSTEM" == "1" ]] || die "Run with sudo:  sudo bash $0"
[[ -f "$ROOT/gateway/requirements.txt" ]] || die "Not a Delta-OTA checkout: $ROOT"
[[ -n "$SERVICE_USER" && ( "$SERVICE_USER" != "root" || "$SKIP_SYSTEM" == "1" ) ]] || \
    die "Run via sudo from your normal user, or pass --user <name> (the gateway should not run as root)."
[[ "$SKIP_SYSTEM" == "1" ]] || id "$SERVICE_USER" >/dev/null 2>&1 || die "User '$SERVICE_USER' does not exist."

# ---- helpers ---------------------------------------------------------------
env_get() { [[ -f "$ENV_FILE" ]] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 || true; }

env_set() {   # env_set KEY VALUE : replace or append, file stays 0600
    local tmp; tmp="$(mktemp)"
    [[ -f "$ENV_FILE" ]] && grep -v "^$1=" "$ENV_FILE" > "$tmp" || true
    printf '%s=%s\n' "$1" "$2" >> "$tmp"
    install -m 600 "$tmp" "$ENV_FILE"
    rm -f "$tmp"
}

ask() {       # ask "prompt" "default" -> echoes the answer
    local prompt="$1" default="$2" reply=""
    if [[ $ASSUME_YES -eq 1 || ! -t 0 ]]; then echo "$default"; return; fi
    read -r -p "$prompt${default:+ [$default]}: " reply
    echo "${reply:-$default}"
}

detect_ip() {
    local ip
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')"
    [[ -n "$ip" ]] || ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "$ip"
}

PY="${DELTA_PY:-$ROOT/gateway/.venv/bin/python}"
fingerprint() { "$PY" -c "import hashlib,sys;print(hashlib.sha256(bytes.fromhex(sys.argv[1])).hexdigest()[:8])" "$1"; }

# ---- 1. system packages + venv ---------------------------------------------
if [[ "$SKIP_SYSTEM" != "1" ]]; then
    info "[1/5] Installing system packages..."
    apt-get update -qq
    apt-get install -y -qq python3-venv python3-pip curl >/dev/null
fi

if [[ "$SKIP_SYSTEM" != "1" ]]; then
    info "[2/5] Python environment (gateway/.venv)..."
    sudo -u "$SERVICE_USER" python3 -m venv "$ROOT/gateway/.venv"
    sudo -u "$SERVICE_USER" "$ROOT/gateway/.venv/bin/pip" install --disable-pip-version-check -q -r "$ROOT/gateway/requirements.txt"
fi

# ---- 2. configuration -------------------------------------------------------
info "[3/5] Configuration ($ENV_FILE)"
echo "    Node URL: the dev PC's Tailscale Funnel URL (https://<laptop>.<tailnet>.ts.net,"
echo "    the fixed phone-RPC URL printed by demo-up) or, on one LAN, http://<PC-IP>:8545."
RPC="${RPC:-$(ask "Blockchain node URL" "$(env_get DELTA_RPC_URL)")}"
RPC="${RPC%/}"
[[ -n "$RPC" ]] || RPC="http://127.0.0.1:8545"
[[ "$RPC" =~ ^https?://[^[:space:]]+$ ]] || die "Node URL must look like https://<laptop>.<tailnet>.ts.net or http://<PC-IP>:8545"

CONTRACT="${CONTRACT:-$(ask "Contract address" "$(env_get DELTA_CONTRACT_ADDRESS)")}"
[[ "$CONTRACT" =~ ^0x[0-9a-fA-F]{40}$ ]] || die "Contract address must be 0x + 40 hex characters."

# The default is the address this Pi has RIGHT NOW, not the saved one: after a
# move to another network the saved address is stale and the CoAP server would
# bind an IP the Pi no longer owns.
CURRENT_IP="$(detect_ip)"
SAVED_BIND="$(env_get DELTA_BIND_ADDR || true)"
if [[ -n "$SAVED_BIND" && -n "$CURRENT_IP" && "$SAVED_BIND" != "$CURRENT_IP" ]]; then
    echo "    NETWORK CHANGED: saved address $SAVED_BIND, this Pi is now $CURRENT_IP."
    echo "    The ESP32 firmware has its gateway IP compiled in (secrets.h): it must be reflashed"
    echo "    with the new address, or give the Pi a fixed IP (setup-network.sh hotspot|lan-static)."
fi
BIND="${BIND:-$(ask "This Pi's LAN IP (the ESP32 connects here)" "${CURRENT_IP:-$SAVED_BIND}")}"
[[ -n "$BIND" ]] || BIND="$CURRENT_IP"
[[ "$BIND" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Pi IP must be an IPv4 address (got '$BIND')."
[[ ! "$BIND" =~ ^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\. ]] ||     die "$BIND is a Tailscale address. The ESP32 is not on the tailnet: use this Pi's LAN/hotspot IP (ip -4 addr)."
[[ "$BIND" != 127.* ]] || die "Bind address is loopback - the ESP32 could never reach it. Pass --bind <Pi-IP>."

EXISTING_KEY="$(env_get DELTA_OTA_KEY || true)"
if [[ -z "$KEY" && $GEN_KEY -eq 0 ]]; then
    if [[ -n "$EXISTING_KEY" ]]; then
        KEY="$EXISTING_KEY"
        echo "    Keeping the existing OTA key (fp=$(fingerprint "$KEY"))."
    else
        KEY="$(ask "OTA key, 32 hex (PC console menu 9 -> Reveal; Enter = generate a new one)" "")"
    fi
fi
if [[ -z "$KEY" ]]; then
    KEY="$("$PY" -c 'import secrets;print(secrets.token_hex(16))')"
    NEW_KEY=1
fi
KEY="${KEY,,}"
[[ "$KEY" =~ ^[0-9a-f]{32}$ ]] || die "OTA key must be exactly 32 hex characters."

env_set DELTA_RPC_URL "$RPC"
env_set DELTA_CONTRACT_ADDRESS "$CONTRACT"
env_set DELTA_BIND_ADDR "$BIND"
env_set DELTA_OTA_KEY "$KEY"
echo "    Saved. OTA key fp=$(fingerprint "$KEY")"
if [[ "${NEW_KEY:-0}" == "1" ]]; then
    echo "    A NEW key was generated. The ESP32 must be provisioned with it:"
    echo "      deltaota-gateway key --reveal     (then paste it into DeltaOTA-ESP32-Reset.exe)"
fi

# reachability is advisory only: the PC may simply not be running yet
if curl -s -m 4 -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' "$RPC" | grep -q '"result"'; then
    echo "    Node reachable at $RPC."
else
    echo "    WARNING: node not reachable at $RPC yet (saved anyway)."
    if [[ "$RPC" == *.ts.net* ]]; then
        echo "             Funnel is only on while the PC runs demo-up (demo-down switches it off)."
    else
        echo "             On the PC: 'npx hardhat node --hostname 0.0.0.0' and open TCP 8545."
    fi
fi

# ---- 3. service --------------------------------------------------------------
info "[4/5] Service + command"
if [[ "$SKIP_SYSTEM" != "1" ]]; then
cat > "$SERVICE_FILE" <<UNIT
[Unit]
Description=Delta-OTA Edge Gateway (CoAP firmware + blockchain poller)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$ROOT/gateway/secureota/gateway_runtime
ExecStart=$PY -u main_gateway.py
EnvironmentFile=$ENV_FILE
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable gateway.service >/dev/null 2>&1
    systemctl restart gateway.service
fi

# `deltaota-gateway` command (paths baked in at install time)
cat > "$CLI_PATH" <<CLI
#!/usr/bin/env bash
# Delta-OTA gateway control (installed by install-gateway.sh)
ROOT="$ROOT"
ENV_FILE="$ENV_FILE"
PY="$PY"
SERVICE_USER="$SERVICE_USER"
CLI
cat >> "$CLI_PATH" <<'CLI'
need_root() { [[ $EUID -eq 0 ]] || exec sudo "$0" "$@"; }
env_get() { sed -n "s/^$1=//p" "$ENV_FILE" 2>/dev/null | tail -n 1; }
env_set() {
    local tmp; tmp="$(mktemp)"
    grep -v "^$1=" "$ENV_FILE" > "$tmp" 2>/dev/null || true
    printf '%s=%s\n' "$1" "$2" >> "$tmp"
    install -m 600 "$tmp" "$ENV_FILE"; rm -f "$tmp"
}
fp() { "$PY" -c "import hashlib,sys;print(hashlib.sha256(bytes.fromhex(sys.argv[1])).hexdigest()[:8])" "$1"; }

case "${1:-help}" in
    status)
        need_root "$@"   # the config file is root-only (it holds the OTA key)
        systemctl is-active gateway >/dev/null && echo "service : RUNNING" || echo "service : STOPPED"
        echo "node    : $(env_get DELTA_RPC_URL)"
        echo "contract: $(env_get DELTA_CONTRACT_ADDRESS)"
        echo "bind    : $(env_get DELTA_BIND_ADDR)   (ESP32 GATEWAY_IP must be this)"
        k="$(env_get DELTA_OTA_KEY)"; echo "key fp  : ${k:+$(fp "$k")}"
        curl -s -m 3 "http://127.0.0.1:8000/gateway_status.json" | "$PY" -c '
import json,sys,time
try: d=json.load(sys.stdin)
except Exception: print("feed    : not answering on :8000 (is the gateway starting?)"); sys.exit()
age=time.time()-d.get("updated_at",0)
print("gateway : %s  following=%s staged=%s blocks=%s  (updated %.0fs ago)"%(d.get("gateway_state"),d.get("target_version"),d.get("staged_version"),d.get("blocks_total"),age))
if d.get("device_ip"): print("device  : %s last block %s final=%s"%(d["device_ip"],d.get("device_last_block"),d.get("device_final_sent")))
if d.get("device_reported_version"): print("device  : reports %s"%d["device_reported_version"])' ;;
    logs)     exec journalctl -u gateway -f -n 40 ;;
    start|stop|restart) need_root "$@"; systemctl "$1" gateway && echo "gateway: $1 done" ;;
    contract) [[ "${2:-}" =~ ^0x[0-9a-fA-F]{40}$ ]] || { echo "usage: deltaota-gateway contract 0x<40 hex>"; exit 1; }
              need_root "$@"; env_set DELTA_CONTRACT_ADDRESS "$2"; systemctl restart gateway; echo "contract set, gateway restarted" ;;
    rpc)      [[ "${2:-}" =~ ^https?:// ]] || { echo "usage: deltaota-gateway rpc http://<PC-IP>:8545"; exit 1; }
              need_root "$@"; env_set DELTA_RPC_URL "$2"; systemctl restart gateway; echo "node URL set, gateway restarted" ;;
    bind)     [[ "${2:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "usage: deltaota-gateway bind <Pi-IP>"; exit 1; }
              need_root "$@"; env_set DELTA_BIND_ADDR "$2"; systemctl restart gateway; echo "bind address set, gateway restarted" ;;
    key)      need_root "$@"; k="$(env_get DELTA_OTA_KEY)"
              if [[ "${2:-}" == "--reveal" ]]; then echo "DELTA_OTA_KEY = $k   (fp=$(fp "$k"))"
              elif [[ "${2:-}" == "--set" && "${3:-}" =~ ^[0-9a-fA-F]{32}$ ]]; then
                  env_set DELTA_OTA_KEY "${3,,}"; systemctl restart gateway; echo "key set (fp=$(fp "${3,,}")), gateway restarted"
              else echo "key fp = $(fp "$k")    (--reveal to print it, --set <32 hex> to replace it)"; fi ;;
    update)   need_root "$@"
              sudo -u "$SERVICE_USER" git -C "$ROOT" pull --ff-only &&
              sudo -u "$SERVICE_USER" "$ROOT/gateway/.venv/bin/pip" install -q -r "$ROOT/gateway/requirements.txt" &&
              systemctl restart gateway && echo "updated to $(git -C "$ROOT" log --oneline -1), gateway restarted" ;;
    doctor)   need_root "$@"
              RPC="$(env_get DELTA_RPC_URL)" CONTRACT="$(env_get DELTA_CONTRACT_ADDRESS)"               BIND="$(env_get DELTA_BIND_ADDR)" KEY="$(env_get DELTA_OTA_KEY)"               NOW_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')"               "$PY" - <<'PYDOC'
import hashlib, json, os, subprocess, time, urllib.request
E = os.environ
def rpc(method, params=()):
    req = urllib.request.Request(E["RPC"], json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)}).encode(),
                                 {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=6).read())["result"]
def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""
def line(ok, name, detail):
    print("%-4s %-14s %s" % ("OK" if ok else "FAIL", name, detail))
active = run("systemctl", "is-active", "gateway") or "unknown"
line(active == "active", "service", active)
now, bind = E["NOW_IP"], E["BIND"]
line(bool(bind) and bind == now, "bind address", "saved %s, Pi is now %s%s" % (bind or "(none)", now or "(no route)",
     "" if bind == now else "  -> deltaota-gateway bind %s  (and reflash the ESP32 with it)" % now))
try:
    cid = rpc("eth_chainId")
    line(cid == "0x7a69", "node", "%s answers, chain %s%s" % (E["RPC"], cid, "" if cid == "0x7a69" else " (expected 0x7a69 = 31337)"))
    try:
        code = rpc("eth_getCode", [E["CONTRACT"], "latest"])
        line(code not in ("0x", "0x0", None), "contract", "%s %s" % (E["CONTRACT"], "has code" if code not in ("0x", "0x0", None) else
             "has NO code on this chain -> deltaota-gateway contract <address from the latest deploy>"))
    except Exception as e:
        line(False, "contract", "check failed: %s" % e)
except Exception as e:
    line(False, "node", "%s unreachable (%s). On the PC: demo-up running? Funnel on?" % (E["RPC"], e))
try:
    line(True, "key", "fp=%s  (must equal the ESP32 'Key loaded fp=')" % hashlib.sha256(bytes.fromhex(E["KEY"])).hexdigest()[:8])
except Exception:
    line(False, "key", "missing or malformed")
try:
    d = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/gateway_status.json", timeout=4).read())
    age = time.time() - d.get("updated_at", 0)
    line(age < 30, "status feed", "state=%s following=%s staged=%s (updated %.0fs ago)" % (d.get("gateway_state"), d.get("target_version"), d.get("staged_version"), age))
except Exception as e:
    line(False, "status feed", "not answering on :8000 (%s)" % e)
ss = run("ss", "-lun")
line(":5683" in ss and (bind in ss), "CoAP socket", "UDP 5683 %s" % ("listening on %s" % bind if bind in ss else "NOT bound to %s (restart after a network change)" % bind))
PYDOC
              ;;
    config)   need_root "$@"; sed -E 's/^(DELTA_OTA_KEY)=.*/\1=********/' "$ENV_FILE" ;;
    *)        cat <<'HELP'
deltaota-gateway <command>
  status                  service, config, live feed, device progress
  logs                    follow the gateway log (Ctrl+C to leave)
  start | stop | restart  control the service
  contract 0x...          set the contract address (after every redeploy) and restart
  rpc http://PC:8545      set the blockchain node URL and restart
  bind <Pi-IP>            set the address the ESP32 connects to and restart
  key [--reveal|--set H]  show the key fingerprint / print it / replace it
  update                  git pull + dependencies + restart
  doctor                  check service, IP, node, contract, key, feed, CoAP socket
  config                  show the configuration (key masked)
HELP
              ;;
esac
CLI
chmod 755 "$CLI_PATH"

# ---- 4. verify ---------------------------------------------------------------
if [[ "$SKIP_SYSTEM" != "1" ]]; then
    info "[5/5] Verifying..."
    ok=0
    for _ in $(seq 1 20); do
        if curl -s -m 2 "http://127.0.0.1:8000/gateway_status.json" | grep -q gateway_state; then ok=1; break; fi
        sleep 1
    done
    if [[ $ok -eq 1 ]]; then echo "    Gateway is up and its status feed answers on :8000."
    else echo "    WARNING: no status feed yet - check: deltaota-gateway logs"; fi
fi

echo
echo "[OK] Done. Pi gateway: coap://$BIND:5683   status: http://$BIND:8000/gateway_status.json"
echo "     deltaota-gateway status | logs | contract 0x... | update | help"
TS_IP=""
command -v tailscale >/dev/null 2>&1 && TS_IP="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
echo "     ESP32 GATEWAY_IP (secrets.h / reset tool) = $BIND   (LAN address: the ESP32 is not on the tailnet)"
if [[ -n "$TS_IP" ]]; then
    echo "     Console 'Gateway address' = $TS_IP   (this Pi's Tailscale IP, works from the PC anywhere)"
else
    echo "     Console 'Gateway address' = $BIND   (install Tailscale on the Pi to reach it from outside this LAN)"
fi
echo "     Patch downloads: on the PC set DELTA_ARTIFACT_HOST=<PC Tailscale IP> (setx) if the Pi is not on the PC's LAN."
