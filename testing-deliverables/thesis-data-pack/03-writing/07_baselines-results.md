# Chapter 3 comparators on the same board: results (HTTPS full binary H, naked CoAP delta N)

Generated from recorded data (`python -m sop.pack build`). Specification: `03-writing/06_baselines-spec.md`.
**Supplementary**: the approved Tables 1 to 4 are not changed. H and N exist because Chapter 3's statistical treatment names a standard HTTPS full-binary update (Equations 3 and 4) and an unsecured naked CoAP transfer (the Absolute Difference). They share the setup of Scenarios A and B (same ESP32, Wi-Fi, gateway PC, firmware pair, tshark and serial measurement) but are separate conditions, not one architecture.

Supplementary Table S2 is in `02-interpretation/tables/table-s2_baselines-h-n.md`.

## Chapter 3 comparators on the same board: HTTPS full binary (H) and naked CoAP delta (N)

Specification: `03-writing/06_baselines-spec.md`. Both are supplementary: they are not part of the approved Tables 1 to 4.

### 1 N: the security tax (Absolute Difference, A minus N, paired)

60 complete A/N pairs. Counted attempts: A ok 64, failed 7; N ok 67, failed 4; harness faults re-run: A 12, N 10.

| Metric | A (secured) mean (SD) | N (naked) mean (SD) | A - N (95% CI) | t | p | dz |
|---|---|---|---|---|---|---|
| Wireshark TTC (ms) | 5,576.1 (1,056.4) | 5,397.6 (237.4) | 178.6 (-97.3 to 454.4) | 1.30 | 0.200 | 0.17 |
| Bytes on the wire | 27,407 (5,925) | 25,778 (1,260) | 1,628 (69 to 3,188) | 2.09 | 0.041 | 0.27 |
| Decryption + reconstruction (ms) | 1,783.6 (27.6) | 1,740.8 (24.7) | 42.7 (33.9 to 51.6) | 9.71 | 7.8e-14 | 1.25 |
| Flash write throughput (KB/s) | 180.8 (3.2) | 181.5 (2.9) | -0.7 (-1.7 to 0.4) | -1.29 | 0.201 | -0.17 |
| AES-CCM decryption per block (us) | 1,528.6 (3.5) | 0.0 (0.0) | 1,528.6 (1,527.7 to 1,529.5) | 3,369.39 | 1.3e-157 | 434.99 |
| Decoder time: inflate, merge, flash (us) | 1,746,885 (27,635) | 1,740,824 (24,733) | 6,061 (-2,754 to 14,876) | 1.38 | 0.174 | 0.18 |
| Peak heap used during the update (B) | 6,218 (2,807) | 5,996 (1,443) | 223 (-589 to 1,034) | 0.55 | 0.585 | 0.07 |
| Static RAM of the technology (KB) | 28.73 (0.00) | 27.66 (0.00) | 1.07 (no variance) | - | - | - |

Framing arithmetic: 29 B (13 B nonce + 16 B tag) x 24 blocks = 696 B expected per update; the measured difference also contains the effect of repeated block requests.

| Scenario | Harness interrupted the update: ok / failed | Clean start: ok / failed |
|---|---|---|
| A | 5 / 7 | 59 / 0 |
| N | 4 / 4 | 63 / 0 |

Security tax on all 60 pairs and on the 53 pairs in which neither cycle was interrupted by the old harness:

| Metric | A - N, all pairs (95% CI), p | A - N, clean pairs (95% CI), p |
|---|---|---|
| Wireshark TTC (ms) | 178.6 (-97.3 to 454.4), p = 0.200 | 188.8 (-124.0 to 501.5), p = 0.231 |
| Bytes on the wire | 1,628.2 (68.8 to 3,187.6), p = 0.041 | 1,706.5 (-62.7 to 3,475.6), p = 0.058 |
| Decryption + reconstruction (ms) | 42.7 (33.9 to 51.6), p = 7.8e-14 | 41.4 (31.7 to 51.2), p = 2.0e-11 |

### 2 H: HTTPS full binary (Equations 3 and 4)

60 counted downloads ok, 0 failed (one boot, 3 warm-up discarded). H against A is **unpaired** (H is a single-boot series).

| H column | Mean | SD | UTL (Eq. 5) | Min | Max |
|---|---|---|---|---|---|
| Time to completion (ms) | 3,732.9 | 404.9 | 4,869.6 | 3,458.5 | 5,641.1 |
| Bytes on the wire | 307,411 | 1,111 | 310,530 | 306,215 | 312,479 |
| TCP + TLS connect (ms) | 1,362.1 | 27.0 | 1,438.0 | 1,341.0 | 1,479.0 |
| Download incl. flash (ms) | 2,423.7 | 389.7 | 3,517.8 | 2,161.0 | 4,219.0 |
| Device total (ms) | 3,785.8 | 406.5 | 4,926.9 | 3,510.0 | 5,698.0 |
| Flash write throughput (KB/s) | 189.6 | 3.8 | 200.4 | 178.1 | 200.4 |

**Equation 3 (payload).** Static: (288,880 - 22,497) / 288,880 = **92.21%** (Table 1). On the wire: H 307,411 B against A 27,499 B = **91.05% fewer bytes** (Welch t = -311.5, p = 9.2e-101).

**Time to completion.** H 3,733 ms (SD 405) against A 5,571 ms (SD 1,230): A is 49.2% longer than H (Welch t = 11.0, p = 4.6e-17).

**Equation 4 (RAM) and flash.**

| | H (HTTPS) | A (proposed) | Reduction % (Eq. 4) |
|---|---|---|---|
| Static RAM added (B) | 6,324 | 29,416 | -365.1 (A is higher: it carries the delta decoder) |
| Peak heap (B): H series maximum, A at its mean / maximum | 65,344 | 6,118 / 16,656 | 90.6 / 74.5 |
| **Peak RAM, static + heap (B)** | 71,668 (140% of 50 KiB) | 35,534 (69%) mean; 46,072 (90%) max | **50.4** (A mean) / **35.7** (A max) |
| Flash added (B) | 156,548 (61.2% of 250 KiB) | 43,340 (16.9%) | 72.3 |

H is a lower bound: no certificate validation and the framework's default TLS buffers. The 50 KiB and 250 KiB figures are an accounting budget on a 520 KB ESP32, not a hardware limit: read the result as 'fits' or 'exceeds' the Class 2 budget.

Cross-check: the capture's time to completion minus the device's own time is -53 ms on average (SD 8), the device total including the final image verification.

## Provenance
- N campaign (A and N, interleaved): `01-raw-data/runs/R07_baseline-N_naked-coap-delta_2026-10-21/campaign/trials.csv` (sha256 `866abb1009bef0983ecf9a7de71ffdb602162ed1a9923209cbad25556d33555d`)
- H run: `01-raw-data/runs/R06_baseline-H_https-full-binary_2026-10-21/campaign/https_runs.csv` (sha256 `b8379b6c97968fa038ae7a8e688b0682178a01b285c45fdcad84f6f5f0be5289`), `summary.json`, `static_increments.json`
- Firmware: separate PlatformIO environments `https_baseline`, `https_control` and `factory_naked` of the firmware repository; the standard `factory` environment is unchanged in code (its image differs from the original in the 64 bytes derived from the ELF checksum only).
- Table code revision: c0f8205.
