# Raspberry Pi 4 Model B Gateway Deployment

Deploys the full Delta-OTA edge gateway onto a Raspberry Pi 4 (arm64),
so the ledger, poller, and CoAP firmware server all run on IoT hardware —
independent of a workstation.

```
ESP32 (constrained node)  --CoAP/UDP 5683-->  Raspberry Pi 4  --RPC 8545-->  Hardhat node (on-board)
                                                    |                              ^
                                                    +------> DeltaOTA contract ---+
                                                     (installed; version + golden hash)
```

## 1. One-time prerequisites

- Raspberry Pi OS (Bookworm, 64-bit) with internet access and `git` installed.
- Repo checked out on the Pi:

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/controlbackspace/DELTA-OTA-UI.git /home/pi/DELTA-OTA-UI
```

> Default install root is `/home/pi/DELTA-OTA-UI`. Override with:
> `sudo DELTA_ROOT=/path/to/repo DELTA_USER=pi bash gateway/deploy/raspberry-pi/setup.sh`

## 2. Deploy

```bash
sudo bash gateway/deploy/raspberry-pi/setup.sh
```

The script:

1. Installs system packages (`python3-venv`, `nodejs`, `npm`, `curl`)
2. Builds the gateway venv (`web3`, `aiocoap`, `cryptography`)
3. Installs + compiles the Hardhat project
4. Installs two systemd units: `hardhat.service` and `gateway.service`
5. Starts the Hardhat node and waits for RPC `127.0.0.1:8545`
6. Deploys `DeltaOTA.sol` (`--network localhost`) and saves the deployed
   address to **`/etc/delta-gateway.env`**
7. Starts the gateway

## 3. Verify

```bash
systemctl status gateway hardhat          # both active (running)
journalctl -u gateway -f                  # live gateway log
cat /etc/delta-gateway.env                # RPC + contract address
```

Expected gateway log traffic:

```
Success!
[CoAP] Server active. Listening on <LAN-IP>:5683...
[Boot] Gateway loaded. Current version: v1.0
[Network] Polling ledger for firmware version: v1.1...
[Ledger] Successfully retrieved state for v1.1: Live=...
```

The gateway restarts itself on crashes (`Restart=always`); the CoAP server
re-binds to the Pi's LAN IP automatically via `get_lan_ip()`.

## 4. Pointing the ESP32 at the Pi

The ESP32 firmware must target the Pi's LAN address:

```cpp
DeltaOTAEngine otaEngine("192.168.x.x", 5683);   // the Pi's IP
```

- Pi and ESP32 must be on the same network.
- If the Pi has more than one interface and the wrong one is picked, force the
  address in `/etc/delta-gateway.env`:

```ini
DELTA_BIND_ADDR=192.168.x.x
```

## 5. Firewall (optional)

Raspberry Pi OS ships without a firewall, so UDP 5683 is open by default.
If you enable `ufw`, allow the CoAP port:

```bash
sudo ufw allow 5683/udp
sudo ufw enable
```

## 6. Notes / gotchas

- **Contract address is stable** across Hardhat restarts (deterministic
  accounts), but after any redeploy it is written to `/etc/delta-gateway.env`;
  restart the gateway to pick it up: `sudo systemctl restart gateway`.
- **`blockchain/package.json`** has `"type": "module"` so the ESM config
  (`hardhat.config.js`) and deployment script run on Node 18+.
- If the gateway logs `FATAL: Ledger poll failed`, it means the Hardhat node
  isn't reachable — bring `hardhat.service` back up; the gateway will recover
  on its next systemd restart.