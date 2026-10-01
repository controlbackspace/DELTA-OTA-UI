# DeltaOTA engine footprint (measured, not estimated)

Engine code (Flash): **1578 B** across 12 symbols.
Engine static RAM: **3261 B** (global `otaEngine` instance + guards).

| Component | Flash (B) | Static RAM (B) | IRAM (B) | Port fate |
|---|---|---|---|---|
| WiFi + UDP radio | 205477 | 5537 | 20 | deleted on port |
| Bluetooth (linked shims) | 500 | 84 | 32 | deleted on port |
| lwIP (TCP/IP) | 104167 | 3115 | 0 | deleted on port |
| FreeRTOS | 4930 | 765 | 14279 | replaced by class-2 RTOS (reference row) |
| mbedTLS (CCM+SHA kept) | 2477 | 0 | 0 | kept (or tinyAES-class equivalent) |
| Arduino core | 29518 | 702 | 4039 | deleted on port |
| NVS / Preferences glue | 13698 | 24 | 0 | replaced by tiny NVS equivalent |
| App glue (setup/loop, incl. inlined engine) | 3417 | 3266 | 0 | kept (port rewritten, same logic) |
| Other libs (newlib, drivers, glue) | 201614 | 6807 | 18157 | kept/minimized |
| Unattributed (alignment, COMMON, linker-owned) | 0 | 14652 | 0 | measured remainder vs nm totals (conservative: kept) |

Notes (read before quoting numbers):
- App-glue static RAM (~3.2 KiB) is the same `otaEngine` instance already counted in the engine row above — same bytes, two lenses, counted once in totals.
- ESP32 mask-ROM residents (bulk WiFi/BT ROM code) execute from ROM and never appear in this image; the port deletes the need for them, stated qualitatively, not measured here.
