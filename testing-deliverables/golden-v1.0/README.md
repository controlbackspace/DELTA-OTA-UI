# Golden v1.0 factory image (doors-open / revert target)

Archived 2026-09-28 from `.pio/build/esp32dev/` after the verified Day-6
bring-up (partition fix + home profile + TX-power cap + request driver).

Source state (Thesis `src/main.cpp` at archive time):
- Network profile: home AP "2.4GHZ", GATEWAY_IP 192.168.100.94 (laptop)
- `WiFi.setTxPower(WIFI_POWER_11dBm)` test-facility cap present
- `pollTransfer()` request driver present (1.5 s interval)
- NO `FIRMWARE_VERSION` marker (predates tagging; banner reads
  "Delta-OTA Engine ready for Phase 3 & 4 testing.")

Revert procedure (morning of Oct 1):
  pio run -t erase && flash bootloader.bin + partitions.bin + firmware-v1.0.bin
  (or `pio run -t upload` from the tagged source state, then re-verify serial).
After revert: factory = v1.0 golden, OTA slots empty, zero residue.
