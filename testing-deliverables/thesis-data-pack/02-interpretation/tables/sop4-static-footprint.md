# SOP 4 static footprint (copied from the SOP evidence report)

Source: `Reference/SOP-REPORT.md`, section 3.4 (evidence run of 2026-10-07, software revision `87bfdf1`; PlatformIO builds of the ESP32 + Arduino project:
`web3_control` = Wi-Fi only, `factory` = the Delta-OTA updater, `web3_baseline` = control + HTTPS + keccak256 + `eth_call` + ABI decode).
These tables are the **static** half of the SOP 4 evidence (flash and static RAM taken from the build tool). The heap and timing half was measured on the
board: see `SOP4-SUMMARY.md` and `01-raw-data/runs/R05_sop4_web3-client-on-device_2026-10-19/`.

**Table 10.** Whole-image footprint per build (PlatformIO, ESP32 + Arduino) *(Measured)*

| Build | Flash used | Static RAM used | What it is |
|---|---|---|---|
| web3_control | 724,465 B | 43,408 B | Wi-Fi only: the framework cost every build shares |
| factory (Delta-OTA updater) | 767,505 B | 72,808 B | AES-CCM block receiver + DOTA decoder + partition handling |
| web3_baseline | 881,337 B | 46,652 B | control + HTTPS + keccak256 + eth_call + ABI decode |

*These are ESP32 images, so the absolute sizes are not Class 2 sizes: the framework alone is 707.5 KB of flash. The meaningful quantity is the increment over the shared control.*

**Table 11.** Cost over the Wi-Fi-only control, against the Class 2 budget (250 KiB flash / 50 KiB RAM) *(Measured)*

| Design | Added flash | % of Class 2 flash | Added static RAM | % of Class 2 RAM |
|---|---|---|---|---|
| Delta-OTA updater (offloaded design) | +43,040 B (42.0 KB) | 16.8% | +29,400 B (28.7 KiB) | 57.4% |
| On-device Web3, lower bound (no offloading) | +156,872 B (153.2 KB) | 61.3% | +3,244 B | 6.3% |

*Static RAM only. TLS buffers and handshake state live on the heap: see the hardware table below (present only when the hardware part ran).*

**Table 12.** Where the on-device Web3 flash goes (link-map groups, baseline − control) *(Measured)*

| Group | Δ flash (B) | Δ static RAM (B) |
|---|---|---|
| Other libs (newlib, drivers, glue) | +86,254 | +412 |
| mbedTLS (the TLS client stack here) | +44,480 | +548 |
| lwIP (TCP/IP) | +7,257 | +1,235 |
| App glue (setup/loop, incl. inlined engine) | +3,525 | +1,024 |
| NVS / Preferences glue | +223 | +0 |
| Arduino core | +178 | +0 |
| WiFi + UDP radio | +83 | +0 |
| FreeRTOS | +42 | +0 |

**Table 13.** Delta-OTA engine alone (symbol-attributed, factory build) *(Measured)*

| Item | Size |
|---|---|
| Engine code (flash) | 1,841 B across 10 symbols |
| Engine static RAM | 3,260 B |

*The row covers only the DeltaOTAEngine symbols; shared libraries such as the mbedTLS CCM code are not included, so the designs are compared with the increment table above.*

**Table 14.** Largest static-RAM symbols in the Delta-OTA updater (factory build) *(Measured)*

| Symbol | Size (B) | % of Class 2 RAM |
|---|---|---|
| g_decoder | 20,312 | 39.7% |
| g_copyBuf | 4,096 | 8.0% |
| g_cnxMgr | 3,800 | 7.4% |
| otaEngine | 3,260 | 6.4% |
| dns_table | 1,184 | 2.3% |
| s_wifi_nvs | 1,180 | 2.3% |
| s_coredump_stack | 1,124 | 2.2% |
| TxRxCxt | 960 | 1.9% |

**Observations.**

- The inflate dictionary is sized to the deflate window the gateway compresses with (4 KB). An earlier build with tinfl's default 32 KB dictionary measured 48,984 B for this symbol and 58,072 B for the updater's static RAM increment (113% of the budget); the 4 KB window cost no compression on the v1.0 -> v1.1 pair (24 blocks either way).

Note: the updater's static RAM increment in the Table 2 campaign build is 29,416 B (28.73 KiB); the 29,400 B above is the SOP 4 evidence figure
(a slightly earlier build). Both are 57.4% of the 50 KiB Class 2 RAM budget.
