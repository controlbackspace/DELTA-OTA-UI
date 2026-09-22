#!/usr/bin/env bash
# Delta-OTA Pi network profiles.
#
# RUN ON THE RASPBERRY PI AS ROOT. NEVER run on a workstation - it rewrites
# NetworkManager connections and can drop your own network access.
#
#   sudo bash setup-network.sh hotspot
#       Pi hosts "DeltaOTA-demo" (WPA2), Pi = 192.168.50.1/24, DHCP for ESP32.
#       Primary profile: venue-independent, deterministic.
#
#   sudo bash setup-network.sh lan-static
#       Pin the ALREADY-CONNECTED Wi-Fi link to 192.168.100.50/24
#       (gw 192.168.100.1). Fallback profile for an existing demo LAN.
#       Override: sudo bash setup-network.sh lan-static <iface> <ip/prefix> <gw>
#
# Both profiles record DELTA_BIND_ADDR in /etc/delta-gateway.env so the CoAP
# server binds the reachable LAN address. This matters on isolated networks:
# without a default route, get_lan_ip() falls back to 127.0.0.1 and the ESP32
# cannot reach the gateway. Run this BEFORE setup.sh (which preserves the key).

set -euo pipefail

PROFILE="${1:-hotspot}"
ENV_FILE="/etc/delta-gateway.env"

HOTSPOT_SSID="DeltaOTA-demo"
HOTSPOT_PASS="delta-ota-2026"
HOTSPOT_IP="192.168.50.1"

LAN_IFACE="${2:-wlan0}"
LAN_ADDR="${3:-192.168.100.50/24}"
LAN_GW="${4:-192.168.100.1}"

if [[ $EUID -ne 0 ]]; then
    echo "[ERROR] Run with sudo on the Pi."
    exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
    echo "[ERROR] nmcli not found. On Raspberry Pi OS Bookworm: sudo apt install -y network-manager"
    exit 1
fi

record_bind_addr() {
    local ip="$1"
    touch "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    if grep -q '^DELTA_BIND_ADDR=' "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^DELTA_BIND_ADDR=.*|DELTA_BIND_ADDR=${ip}|" "$ENV_FILE"
    else
        printf 'DELTA_BIND_ADDR=%s\n' "$ip" >> "$ENV_FILE"
    fi
    echo "    DELTA_BIND_ADDR=${ip} -> $ENV_FILE"
}

case "$PROFILE" in
    hotspot)
        echo "==> Hotspot profile: SSID ${HOTSPOT_SSID}, Pi ${HOTSPOT_IP}"
        nmcli con delete delta-hotspot 2>/dev/null || true
        nmcli con add type wifi ifname wlan0 con-name delta-hotspot autoconnect yes \
            ssid "$HOTSPOT_SSID" \
            802-11-wireless.mode ap 802-11-wireless.band bg \
            ipv4.method shared ipv4.addresses "${HOTSPOT_IP}/24" \
            wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$HOTSPOT_PASS"
        nmcli con up delta-hotspot
        record_bind_addr "$HOTSPOT_IP"
        echo "    Join '${HOTSPOT_SSID}' from the ESP32 and the demo laptop."
        ;;
    lan-static)
        LAN_IP="${LAN_ADDR%%/*}"
        echo "==> LAN-static profile: ${LAN_IFACE} ${LAN_ADDR} gw ${LAN_GW}"
        if ping -c1 -W1 "$LAN_IP" >/dev/null 2>&1; then
            echo "[ERROR] ${LAN_IP} already answers ping - address collision. Pick another IP."
            exit 1
        fi
        ACTIVE="$(nmcli -t -f NAME,DEVICE,STATE con show --active | awk -F: -v dev="$LAN_IFACE" '$2==dev && $3=="activated" {print $1; exit}')"
        if [[ -z "$ACTIVE" ]]; then
            echo "[ERROR] No active connection on ${LAN_IFACE}. Join the demo AP first (imager/Raspbian), then re-run."
            exit 1
        fi
        nmcli con mod "$ACTIVE" ipv4.method manual ipv4.addresses "$LAN_ADDR" \
            ipv4.gateway "$LAN_GW" ipv4.dns "$LAN_GW,8.8.8.8"
        nmcli con up "$ACTIVE"
        record_bind_addr "$LAN_IP"
        ;;
    *)
        echo "Usage: sudo bash setup-network.sh [hotspot|lan-static] [iface] [ip/prefix] [gw]"
        exit 1
        ;;
esac

echo
echo "[OK] Network profile applied."
echo "     Restart the gateway to bind the new address: sudo systemctl restart gateway"
