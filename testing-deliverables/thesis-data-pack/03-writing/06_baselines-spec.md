# Baseline specifications: HTTPS full binary (H) and naked-CoAP delta (N)

**Status: executed (2026-10-21).** H and N were built and measured as specified; results are in `03-writing/07_baselines-results.md`. Differences from the first draft of this specification are listed in section 13. (The text below is the specification as reviewed.) The approved Experiment Paper (Tables 1 to 4) and Chapter 3 are not changed; the new results go into a **Supplementary Table S2** and into new Chapter 4 sections.

## 1. Why these two comparators
Chapter 3's statistical treatment (Equations 3 and 4, and the Absolute Difference) compares the proposed architecture with:
- **Baseline A, "the Standard HTTPS Full-Binary Update"**: payload reduction (Eq. 3) and RAM reduction (Eq. 4).
- **Baseline B, "Unsecured Naked CoAP"**: the execution time and memory it subtracts from the secured protocol give the security tax.

The approved scenarios A to E contain neither (Scenario B is the full binary through the same secured pipeline, the internal control). H and N are built so that these three Chapter 3 comparisons are measured, not only argued. To avoid confusion with the Chapter 3 letters, they are called **H** (HTTPS) and **N** (naked CoAP) here.

## 2. The four conditions side by side
| | **A** proposed (done) | **B** internal control (done) | **H** HTTPS full binary (new) | **N** naked CoAP delta (new) |
|---|---|---|---|---|
| Role | the architecture | approved Table 2 control | Chapter 3 Baseline A (Eq. 3, Eq. 4) | Chapter 3 Baseline B (security tax) |
| Payload | DOTA delta stream, 24 blocks, 22,497 B patch | full image, deflated, 168 blocks | raw `app-v1.1.bin`, 288,880 B, as received | **the same** DOTA delta stream as A, 24 blocks |
| Transport | CoAP over UDP, 1 KiB blocks, 200 ms request timer | same as A | HTTP/1.1 over TLS 1.2 over TCP, one GET | CoAP over UDP, **same** block protocol and timer |
| Protection | AES-CCM per block (13 B nonce + 16 B tag), ledger-anchored hash, 2-of-3, kill switch | same as A | TLS 1.2 (ECDHE-ECDSA-AES128-GCM-SHA256, as in SOP 2 and 4); nothing else | **none**: plaintext blocks, no tag |
| Device program | factory updater (`campaign-fw-1`) | same | new PlatformIO env `https_baseline` | new env `factory_naked` (= factory source with `-DNAKED_COAP=1`) |
| Cycle model | reflash app v1.0, update, capture; 3 warm-up + 60 matched pairs with B | same | **one boot: 3 warm-up + 60 consecutive downloads** | as A: interleaved rounds of A and N (seeded random order), 3 warm-up + 60 matched pairs |
| Compared with A by | | paired t-test | unpaired Welch (not interleaved) | paired t-test |

## 3. H: HTTPS full binary
**What it represents.** A device that downloads the whole new image from a standard HTTPS server and writes it to flash. No delta, no per-block framing, no ledger.

**Server (gateway PC).** A TLS 1.2 HTTP server on port **8545** (already open in the Windows firewall) with a self-signed ECDSA P-256 certificate, serving `GET /app-v1.1.bin` as the unmodified image with a `Content-Length` header (code reused from `gateway/sop/web3_hw.py`, `make_certificate` and `tls_front`). One TCP connection per download.

**Device (`https_baseline`).** Separate PlatformIO env, same board, same Wi-Fi and `secrets.h` as the other builds. It connects, then repeats the cycle below 63 times in one boot, pausing 500 ms between downloads (as the Web3 baseline does):
1. open a TLS connection (`WiFiClientSecure`, certificate **not** validated: a lower bound for H, stated in the thesis);
2. `GET /app-v1.1.bin`;
3. stream the body into `esp_ota_begin` / `esp_ota_write` / `esp_ota_end` on `ota_0` (the same calls as the delta decoder, with the same time and byte counters), so the image is verified by `esp_ota_end` as in A and B;
4. print one line per run: `[HTTPS] run=N connect_ms= download_ms= flash_us= flash_bytes= bytes= ok=`, plus `[MEM]` markers (`https-start`, `https-run`, `https-end`) with free and minimum free heap.

It does not reboot into the new image and does not touch the boot selector, so it does not disturb the next run. `ota_0` ends up holding v1.1; the demonstration state is restored afterwards.

**Measured per run (same measurement points as Table 2).**
| Measure | Source |
|---|---|
| Time to completion | tshark capture: first packet of the TCP connection to the last data packet of the response (one TCP stream per run); cross-checked against `connect_ms + download_ms` |
| Bytes on the wire | the same capture, all packets of the stream (TCP/IP and TLS overhead included, as for A and B) |
| Peak heap | `[MEM]` markers (start free heap minus lowest free heap), same function as the other builds (`peak_heap`) |
| Static RAM of the technology | build size of `https_baseline` minus `web3_control` (the Wi-Fi-only control), as in SOP 4 |
| Flash write throughput | `flash_bytes` over `flash_us`, as for A and B |
| Receive and decrypt processing time | `download_ms` minus the flash time (TLS record decryption, TCP, HTTP parsing and buffering are not separable on the device) |

## 4. N: naked CoAP delta
**What it represents.** Exactly the proposed transfer with the security removed from the data path: same delta, same CoAP block protocol, same decoder and flash writes, but the block frames carry plaintext, with no nonce, no tag and no decryption.

**Frame change.** A: `nonce (13 B) || ciphertext || tag (16 B)`. N: `plaintext` only.

**Device (`factory_naked`).** The factory updater source built with `-DNAKED_COAP=1`: `_sliceFrame` takes the whole CoAP body as the block and `_decryptInto` is skipped (the block goes straight to `g_decoder.feed`). Counters and `[Metrics2]` are kept (`decrypt_us` = 0). It is a **separate env**; the `factory` env, its image and the demonstration firmware are not modified (checked by hash).

**Gateway.** `DELTA_NAKED=1`: `SecurityEngine.encrypt_blocks` writes plaintext frames instead of AES-CCM frames. Everything else is the real gateway and chain flow.

**Design decision to confirm (differs slightly from the plan text).** In N the real gateway and chain still run, so the cycle harness is unchanged. The ledger poll and the SHA-256 check happen *before* the first block is served, so they are **outside the device-observed time to completion and the wire bytes**. N therefore removes exactly the AES-CCM framing and decryption from the device path, and the gateway-side costs (polling 54.13 ms, SHA-256 0.23 ms, encapsulation 6.13 ms) come from Table 3. The Absolute Difference is then reported as: **device path = A minus N (measured)**, plus **gateway = Table 3 components**. The alternative, a gateway with no chain at all (`SIM_LEDGER`), would give the same device numbers and is available if you prefer "no ledger" to be literal.

**Cycle model.** The existing `LocalRig` flow (flash the naked updater and app v1.0, start the gateway, capture with tshark, read the serial log). Each round runs a **fresh A and N** in seeded random order, so A and N are paired (drift cancels) and the existing A/B data are not reused for this comparison.

**Measured per cycle.** Same fields as Table 2 (time to completion, bytes on the wire, static RAM, peak heap, decoder time, flash throughput) plus the per-block timing of the frame path.

## 5. How the results enter the equations
| Chapter 3 item | Computation | Notes |
|---|---|---|
| **Eq. 3**, payload reduction against Baseline A | (H bytes on the wire minus A bytes on the wire) / H x 100; static: (288,880 minus 22,497) / 288,880 = 92.21% (Table 1) | H includes TLS and TCP overhead |
| **Eq. 4**, RAM reduction against Baseline A | (H peak RAM minus A peak RAM) / H x 100, with peak RAM = static RAM + peak heap, measured on the same board | reported with static and heap shown separately, as in Section 4.6.4 |
| **Absolute Difference**, security tax | A minus N per metric (time to completion, bytes, decoder/decrypt time, static RAM, heap), paired t-test and 95% interval; gateway components from Table 3 | cross-checked against the component sum of Section 4.4.5 (36.7 ms and 696 B per update on the device) |
| **Eq. 1, 2, 5** | mean, SD, upper tolerance limit (K from the actual n) for every new column | same `inference.py` |

## 6. Supplementary Table S2 (not one of the approved tables)
Same columns as Table 2 in the same order, with two added columns that Equations 3 and 4 need, and a clear label that the table is supplementary:

| Cycle # | Scenario Type | Wireshark TTC (ms) | ESP32 Peak RAM Allocation (KB, static) | Decryption + Reconstruction Time (ms) | Total Flash Write Throughput (KB/s) | *Bytes on the wire* | *Peak heap (B)* |
|---|---|---|---|---|---|---|---|

Scenario types: `A (Delta-OTA, paired with N)`, `N (Naked CoAP delta)`, `H (HTTPS full binary)`. For H the "Decryption + Reconstruction" cell is the receive-and-decrypt time defined in section 3 and is footnoted. STAT rows (mean, SD) per scenario, as in Table 2.

## 7. Acceptance checks before any number is used
- **Capture against device.** For N and H, the capture's time to completion agrees with the device's own time within the usual margin (A showed 70 to 220 ms).
- **N bytes.** N's wire bytes equal A's minus 29 B x 24 blocks (696 B) plus the same retransmission effects; N's decoder output is byte-identical (`esp_ota_end` OK, 288,880 B, same SHA-256 as the target image).
- **H bytes.** H's wire bytes are at least 288,880 B; the written image has the SHA-256 of `app-v1.1.bin`.
- **Static RAM.** N and H static figures come from the build, are constant, and are tied to the firmware image hash.
- **Isolation.** The `factory` env output is byte-identical before and after the change; existing tests still pass.
- **State.** After the runs the board is reset to the demonstration state (factory updater, app v1.0, gateway = this PC) and boots.

## 8. Run sizes and time
| Run | Size | Estimated time |
|---|---|---|
| H pilot | 3 warm-up + 5 downloads | about 2 minutes |
| N pilot | 3 warm-up + 5 pairs | about 15 minutes |
| H full | 3 warm-up + 60 downloads, one boot | about 15 minutes |
| N full | 3 warm-up + 60 pairs (63 rounds of A + N), extra rounds for failed cycles | about 1 to 1.5 hours |

## 9. What to expect, and how it will be reported
- **Time to completion may favour HTTPS.** A 289 KB TLS download on a clean LAN may take 2 to 4 s, against about 5.6 s for the delta, because the CoAP protocol requests one block per 200 ms. If so, it is reported as measured; the delta's advantages are bytes and RAM (Eq. 3 and 4) and governance, and the block pacing is a tunable design parameter (recommendation in Chapter 5).
- **RAM against the Class 2 budget.** Expected from the Web3 client measurement: the default TLS stack needs a heap of about 50 KiB, so H is expected to exceed the 50 KiB budget while A and N fit. This is an **expectation until measured**. The 50 KiB and 250 KiB figures are an accounting budget applied to the added code on a 520 KB ESP32, not a hardware limit, so results are worded "fits / exceeds the Class 2 budget", never "runs / does not run on a Class 2 device".
- **Lower bound.** H uses default TLS buffers and no certificate validation, so real HTTPS would need at least as much. A tuned lightweight TLS is not measured and is not claimed.
- **Governance is by design.** HTTPS authenticates the server, not the release: it has no multi-party approval and no revocation. This is stated as a design property, not measured; Scenarios C, D, E apply to the proposed architecture only.
- **Statistics.** N against A is paired (interleaved). H against A is unpaired (Welch) because H is a single-boot series; this is stated.

## 10. Limits that stay
One device, one firmware pair, one Wi-Fi network, the gateway PC; H is a repeated measurement in one boot, not 60 independent sessions; energy is not measured; the TLS comparison is on the ESP32 only (no Class 2 part).

## 11. Review decisions (2026-10-21)
1. **N and the ledger:** keep the real gateway and chain, with plaintext framing (as recommended). The gateway-side costs come from Table 3.
2. **H without certificate validation** is accepted as the H configuration (a lower bound, stated).
3. **H cycle model:** one boot of 3 warm-up + 60 consecutive downloads, about 15 minutes.

## 12. Same setup, separate conditions
H, N, A and B share one setup: the same ESP32, Wi-Fi network, gateway PC, firmware pair (v1.0 to v1.1) and measurement chain (tshark and serial log), and they are reported side by side in Supplementary Table S2.
They are **not one architecture**: N travels over UDP (CoAP) and H over TCP with TLS, so no single system contains both, and each answers a different question.
- **H** answers how the proposed architecture compares with the standard approach (Equations 3 and 4).
- **N** answers what the security costs (Absolute Difference). N must differ from A **only** in the security, so that A minus N isolates the tax. H differs from A in transport, payload and protection together, so it is kept out of that subtraction.
Chapter 3 likewise names them as two separate baselines for two separate equations.

## 13. Differences between this specification and what was done
1. **N uses a flag file** (`DELTA_NAKED_FILE`) read by the gateway for each release, so A and N interleave without restarting the gateway; the real gateway and chain run for both (as decided in section 11).
2. **Updater switching.** Each A/N round switches the secured and the naked updater in the board's factory slot with esptool at 460800 baud (fallback to the default speed), with otadata erased after each write.
3. **Harness race found and fixed during the N campaign.** The harness reset a device that had already started its update on its own, interrupting the backup copy. The capture now starts before the release is published and a device that has begun is not reset. The main A/B campaign used the earlier harness; a 20-pair A/B confirmation run on the corrected harness agrees with it.
4. **H statistics.** Peak heap for H is one value for the series (the highest of the 60 downloads) because the device's minimum-free-heap marker is cumulative; the comparison with A uses A's mean and maximum heap.
5. **Hardware.** The first N attempt ran on a USB port whose auto-reset into flash mode failed; the board was moved to another port. That period produced only harness faults (not counted).
