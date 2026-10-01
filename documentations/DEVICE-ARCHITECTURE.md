# Device Architecture: factory updater + delta-rebuilt application

How the ESP32 side of Delta-OTA is laid out, boots, updates and recovers.
Source: PlatformIO project `Documents\PlatformIO\Projects\Thesis`.

## 1. Flash layout (`partitions.csv`, 4 MB)

| Partition | Offset | Size | Holds |
|---|---|---|---|
| nvs | 0x9000 | 16 KB | OTA key (`delta-sec`), app health record (`delta-app`) |
| otadata | 0xd000 | 8 KB | which app slot boots next |
| phy_init | 0xf000 | 4 KB | RF calibration |
| **factory** | 0x10000 | 1280 KB | **updater** (`src/factory/main.cpp`), never touched by OTA |
| **ota_0** | 0x150000 | 1280 KB | **application** (`src/app/app_main.cpp`), what updates replace |
| **ota_1** | 0x290000 | 1280 KB | **backup** of the previous application (delta base + restore source) |

The factory updater is the permanent recovery point. A bad application can
never remove the code that repairs it.

## 2. Boot flow (every reset)

```
reset ──► factory updater
           ├─ no OTA key?           → store the key compiled in from secrets.h (first boot only)
           ├─ last install pending? → confirmed by app? clear it
           │                          not yet?  boot it again (max 3 tries)
           │                          3 tries?  restore ota_1 → ota_0, mark failed
           ├─ Wi-Fi (20 s max)       → no network: boot the app anyway
           ├─ /hello <app version>   → console tracker "Running vX"
           ├─ GET /version           → staged release?
           │     newer & not failed  → UPDATE (below)
           └─ boot ota_0 ──► application
                              ├─ hand next boot back to factory (otadata)
                              ├─ first boot of this version? confirm in NVS, reboot once
                              └─ run (banner + version-coded LED blink)
```

## 3. Update sequence

1. **Backup:** copy the valid image in ota_0 to ota_1 (length from `esp_image_verify`).
2. **Pull:** request encrypted blocks `GET /patch?b=N` (AES-CCM, per-block tag).
3. **Rebuild:** each authenticated block feeds the DOTA decoder, which inflates
   the stream (ROM `tinfl`) and applies bsdiff records against **ota_1**,
   writing the new image straight into **ota_0** (`esp_ota_write`).
4. **Verify:** the size must equal the header's `new_size`; `esp_ota_end`
   checks the image's built-in SHA-256, so a wrong base or corruption is caught.
5. **Boot + confirm:** the updater records `pending`, the new app confirms
   itself in NVS and reboots once, and the updater reports the version.
6. **Any failure** (3 auth failures, decoder error, verification, 60 s stall,
   3 unconfirmed boots): restore ota_1 → ota_0 and record the version as
   `failed`. It is never retried automatically; stage a newer release.

### Revoke (kill switch) on the device

When the newest release is revoked on-chain the gateway destroys its blocks
and answers `GET /version` with **4.03 + the revoked version**. The updater
checks this at every boot: if the device runs that version it restores
ota_1 (the previous application) into ota_0, records the version as `failed`
(never reinstalled) and boots the old app, which reports itself via `/hello`.
The app has no networking, so a running device picks the revoke up at its
next reset or power cycle. Needs the updated factory image
(`toolslash_device.bat factory COM3`).

## 4. Gateway side and the DOTA stream

Releases stay **BSDIFF40** on-chain (the golden hash covers those exact
bytes). bsdiff4 compresses with bzip2 level 9, which needs megabytes of RAM to
decompress, so the gateway re-packs the *verified* patch as **DOTA**
(`gateway/secureota/gateway_runtime/delta_stream.py`; `apply_dota()` is the
reference decoder):

- 16-byte header: `"DOTA"`, version 1, `u32 new_size`
- raw-deflate body of records: `u32 add, u32 copy, i32 seek`, then `add` diff
  bytes (`new = old + diff`), then `copy` literal bytes, then `oldpos += seek`

A full image (bench `DELTA_PAYLOAD`) becomes a single copy-only record, so it
also installs into an empty ota_0.

Measured on the demo app builds (v1.1 adds the GPIO4 touch feature, a new
heartbeat and a heap report): v1.0 (279 KB) → v1.1 (289 KB) = BSDIFF40 22.4 KB
→ DOTA 23.6 KB → **24 blocks**. The same update as a full image is 158 blocks.

Gateway CoAP resources: `/patch?b=N` (blocks), `/version` (staged release or
4.01), `/hello` (device report). Message IDs are random per boot. CoAP
servers replay cached replies for a repeated (endpoint, ID) for about 4
minutes, which would hand a rebooting device the previous release's blocks.

## 5. Build, flash, reset (runbook)

```bat
cd Documents\PlatformIO\Projects\Thesis
pio run                                   :: builds factory + apps; publishes release-images\app-v1.0.bin, app-v1.1.bin
tools\flash_device.bat erase   COM3       :: clean chip (wipes the key too)
tools\flash_device.bat factory COM3       :: updater -> factory, boot = factory (stores the key from secrets.h)
tools\flash_device.bat app     COM3 v1.0  :: application -> ota_0 (byte-exact)
```

There is no USB key handshake. `include\secrets.h` carries Wi-Fi, gateway IP
and `DELTA_OTA_KEY_HEX` (the gateway's 32-hex key; template:
`secrets.example.h`); the factory image writes that key to NVS on first boot
and logs `Key loaded fp=<fp>`, which must match the gateway console's
fingerprint. Moving the gateway to another machine (e.g. the Raspberry Pi)
needs only the same key there (gateway console menu 9, or `gateway.json`).

**Packaged tools:** `DeltaOTA-Gateway.exe` (gateway console, built with
`gateway\build-exe.bat`) and `DeltaOTA-ESP32-Reset.exe` (built with
`tools\build-exe.bat`; prompts for Wi-Fi, gateway IP and key, rewrites
`secrets.h`, then does the full reset below).

Release v1.1 from the console (files in `Projects\Thesis\release-images\`,
with SHA-256 checksums in `SHA256SUMS.txt`):
- **Base** = `release-images\app-v1.0.bin`
- **Target** = `release-images\app-v1.1.bin`
- Propose, approve, then **Track Deployment**.

The console takes the release version from the target's filename
(`app-v1.1.bin` → `v1.1`). That is why the release images are named by
version: every PlatformIO build output is called `firmware.bin`.

**Rule:** the base must be the exact file in ota_0. `flash_device app` writes
`release-images\app-<ver>.bin` with esptool `keep` flags for that reason.
Never put an app in ota_0 with plain `pio run -t upload`.

Next version: copy an app env as `[env:app_v1_2]` with `-DAPP_VERSION=\"v1.2\"`
and keep its `extra_scripts` line. The base is whatever version the device
runs now.

### Reset the device to v1.0

| Situation | Command |
|---|---|
| Replay the demo after a successful update | `demo-down` / `demo-up` (fresh chain), then `tools\flash_device.bat app COM3 v1.0` |
| A version was recorded as failed (the updater never retries it), or anything looks wrong | `DeltaOTA-ESP32-Reset.exe` (or `tools\flash_device.bat reset COM3` with an existing `secrets.h`): erase + factory + key + app v1.0 |

- **The light reset** rewrites only ota_0. The factory updater, key and
  health record stay, and the v1.0 app re-registers itself on its next boot.
- **The full reset** wipes the whole chip. The key is re-installed from
  `secrets.h`, so the fingerprint is unchanged as long as the key is.
- **Always start a fresh chain before replaying.** Otherwise the updater
  pulls a release that is still live on the old chain as soon as it boots.

## 6. Known limitations

- The application must not damage NVS `delta-app` or otadata. It runs with
  full privileges (no isolation on ESP32 without secure boot).
- The base is not identified explicitly. A release built against the wrong
  base is caught by `esp_ota_end` and rolled back, not prevented up front.
- The OTA key sits unencrypted in NVS (no flash encryption; see the security
  scope discussion).
