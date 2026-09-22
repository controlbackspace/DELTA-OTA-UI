#!/usr/bin/env bash
# Delta-OTA Edge Gateway - Raspberry Pi 4 Model B deployment
#
#   Installs: Python venv (web3/aiocoap/cryptography),
#             Hardhat node + DeltaOTA contract as systemd services,
#             the main gateway as a systemd service.
#
#   Run once, from anywhere, as root:
#       sudo bash gateway/deploy/raspberry-pi/setup.sh
#
#   Assumes the repo is checked out at /home/pi/DELTA-OTA-UI
#   (override with DELTA_ROOT, and the service user with DELTA_USER).

set -euo pipefail

ROOT="${DELTA_ROOT:-/home/pi/DELTA-OTA-UI}"
SERVICE_USER="${DELTA_USER:-pi}"
ENV_FILE="/etc/delta-gateway.env"
RPC_URL="http://127.0.0.1:8545"

if [[ $EUID -ne 0 ]]; then
    echo "[ERROR] Run with sudo:  sudo bash gateway/deploy/raspberry-pi/setup.sh"
    exit 1
fi

if [[ ! -d "$ROOT/gateway" ]]; then
    echo "[ERROR] Repo not found at $ROOT. Set DELTA_ROOT to the checkout path."
    exit 1
fi

echo "==> [1/7] Installing system packages..."
apt-get update
apt-get install -y python3-venv python3-pip nodejs npm curl

echo "==> [2/7] Creating Python venv for the gateway..."
python3 -m venv "$ROOT/gateway/.venv"
"$ROOT/gateway/.venv/bin/pip" install --disable-pip-version-check -r "$ROOT/gateway/requirements.txt"

echo "==> [3/7] Installing Hardhat and compiling the DeltaOTA contract..."
cd "$ROOT/blockchain"
npm ci
npx hardhat compile

echo "==> [4/7] Installing systemd units..."
sed -e "s|__ROOT__|$ROOT|g" \
    -e "s|__USER__|$SERVICE_USER|g" \
    -e "s|__GROUP__|$SERVICE_USER|g" \
    "$ROOT/gateway/deploy/raspberry-pi/gateway.service"  > /etc/systemd/system/gateway.service
sed -e "s|__ROOT__|$ROOT|g" \
    -e "s|__USER__|$SERVICE_USER|g" \
    -e "s|__GROUP__|$SERVICE_USER|g" \
    "$ROOT/gateway/deploy/raspberry-pi/hardhat.service" > /etc/systemd/system/hardhat.service
systemctl daemon-reload

echo "==> [5/7] Starting the Hardhat node..."
systemctl enable --now hardhat.service

for i in $(seq 1 30); do
    if curl -s -H "Content-Type: application/json" \
        -X POST --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
        "$RPC_URL" | grep -q '"result"'; then
        echo "    Hardhat node is up."
        break
    fi
    sleep 1
done
if ! curl -s -H "Content-Type: application/json" \
    -X POST --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
    "$RPC_URL" | grep -q '"result"'; then
    echo "[ERROR] Hardhat node did not come up. Check: journalctl -u hardhat -f"
    exit 1
fi

echo "==> [6/7] Deploying DeltaOTA and capturing the contract address..."
ADDR=$(cd "$ROOT/blockchain" && npx hardhat run scripts/deploy.js --network localhost 2>/dev/null \
        | sed -n 's/.*CONTRACT ADDRESS: //p' | tail -n 1)
if [[ -z "$ADDR" ]]; then
    echo "[ERROR] Could not extract the deployed contract address from deploy.js output."
    exit 1
fi
umask 077
PREV_BIND="$(sed -n 's/^DELTA_BIND_ADDR=//p' "$ENV_FILE" 2>/dev/null | tail -n 1)"
printf 'DELTA_RPC_URL=%s\nDELTA_CONTRACT_ADDRESS=%s\n' "$RPC_URL" "$ADDR" > "$ENV_FILE"
if [[ -n "$PREV_BIND" ]]; then
    printf 'DELTA_BIND_ADDR=%s\n' "$PREV_BIND" >> "$ENV_FILE"
    echo "    Preserved DELTA_BIND_ADDR=$PREV_BIND from setup-network.sh"
fi
echo "    Contract address: $ADDR -> $ENV_FILE"

echo "==> [7/7] Starting the gateway..."
systemctl enable --now gateway.service

echo
echo "[OK] Gateway deployed on the Pi."
echo "     CoAP firmware endpoint:  UDP 5683 on this Pi's LAN IP"
echo "     Gateway logs:            journalctl -u gateway -f"
echo "     Ledger logs:             journalctl -u hardhat -f"