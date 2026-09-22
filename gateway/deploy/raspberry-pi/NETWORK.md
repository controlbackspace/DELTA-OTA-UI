# Delta-OTA Pi Networking: Profiles, Runbook, Pre-flight

Two network profiles. **Hotspot is primary** (venue-independent, deterministic);
LAN-static is the fallback for an existing demo LAN. Both are applied by
`setup-network.sh` — run it **before** `setup.sh` (which preserves the key).

## Profiles

| | Hotspot (primary) | LAN-static (fallback) |
|---|---|---|
| Pi address | `192.168.50.1/24` | `192.168.100.50/24` |
| SSID | `DeltaOTA-demo` (WPA2, Pi-hosted) | existing demo AP |
| ESP32 joins | `DeltaOTA-demo` | the demo AP |
| DHCP | Pi serves it (`ipv4.method shared`) | venue router |
| Command | `sudo bash setup-network.sh hotspot` | `sudo bash setup-network.sh lan-static` |

Both write `DELTA_BIND_ADDR=<pi-ip>` to `/etc/delta-gateway.env`, which
`gateway.service` loads via `EnvironmentFile`. **Do not skip this step:**
on an isolated network the Pi has no default route, so `get_lan_ip()` falls
back to `127.0.0.1` and the CoAP server binds loopback — reachable from
nothing, including the ESP32.

## ESP32 side (Thesis `src/main.cpp`, network profile block)

| Pi profile | `WIFI_SSID` | `WIFI_PASS` | `GATEWAY_IP` |
|---|---|---|---|
| Hotspot | `DeltaOTA-demo` | `delta-ota-2026` | `192.168.50.1` |
| LAN-static | your AP SSID | your AP password | `192.168.100.50` |

The ESP32 needs **no static IP of its own** — it is a DHCP client that only
initiates outbound CON GETs. Only the server address is baked in. (History:
`main.cpp` once pointed at `192.168.1.100` and `mainv2.cpp` at
`192.168.100.94` — two subnets. `mainv2.cpp` is deleted; `main.cpp` is
canonical and reads the single profile block.)

## Arrival-day runbook (no Pi/ESP32 boards yet — run on arrival)

1. Flash Pi OS (Bookworm 64-bit), boot, `sudo apt update`.
2. Clone repo, run `sudo bash gateway/deploy/raspberry-pi/setup-network.sh hotspot`
   (or `lan-static`; collision check is built in).
3. Run `sudo bash gateway/deploy/raspberry-pi/setup.sh` (venv, Hardhat,
   contract deploy, services). `DELTA_BIND_ADDR` survives step 6.
4. Flash ESP32 with the matching profile block; `pio run -t upload`.
5. Pre-flight below. Then the D1 hardware pass.

## Pre-flight checklist (Sept 28 + Oct 1, on the FINAL profile)

- [ ] `ip -4 addr` on Pi shows the expected address (`.50.1` or `.100.50`).
- [ ] `cat /etc/delta-gateway.env` contains the same `DELTA_BIND_ADDR`.
- [ ] `journalctl -u gateway` shows `Listening on <that-ip>:5683` (not `127.0.0.1`).
- [ ] Laptop ↔ Pi ping succeeds both ways (same subnet).
- [ ] CoAP probe from laptop: `GET coap://<pi-ip>:5683/firmware` answers
      `2.05` (or `4.01` pre-update — either proves UDP routing).
- [ ] ESP32 serial: Wi-Fi connected with a DHCP lease + `GATEWAY_IP` in the
      flashed binary matches the Pi (`grep GATEWAY_IP src/main.cpp`).
- [ ] First `requestChunk` gets `2.05`/`2.04` (not timeouts) — routing proven.
