# Limitations and threats to validity

Same list as Section 4.9 of the chapter draft (keep the two in sync). State them as limitations of this test bed, not as apologies.

*Hand-written source (not generated). Numbers are from `01_statistical-analysis.md`; update both together.*

1. **One device, one firmware pair, one Wi-Fi network.** The results describe this test bed. The generalisation to other devices and image sizes is a hypothesis for future work.
2. **Baselines.** The comparison of Table 2 is delta against full binary through the same secured pipeline, the internal control of Chapter 3. The standard-HTTPS (H) and naked-CoAP (N) baselines of the statistical treatment were measured as supplementary conditions (Sections 4.4.5 and 4.6.5). H is a **lower bound** (no certificate validation, default TLS buffers) and a single-boot series compared with A unpaired; no DTLS stack was run on the device.
3. **Gateway hardware differs between tables.** Scenarios A and B used the development PC as the gateway (the device-side and capture-side figures do not depend on it). Table 3 used a Raspberry Pi 4 limited to Raspberry Pi 3B+ memory and clock, with swap enabled. It is a faithful limit on memory and clock, not a physical 3B+.
4. **Update failures and the harness race.** 9 of 138 counted attempts of the main A/B campaign failed. Six were caused by the test harness resetting a device that had already begun to update (Section 4.7.5); three failures in B have no known cause. The main campaign used the earlier harness: 14 of its 60 pairs involve an interrupted cycle. The headline results are unchanged without them and a 20-pair confirmation run on the corrected harness agrees, but the failure rate of the main campaign must not be read as a rate of the architecture.
5. **Skewed timing data.** Retransmissions create a heavy tail in time to completion. The sign test and the tolerance limits account for it, but the normality assumption of the t-test is not met strictly.
6. **On-device Web3 client.** It is a read-only lower bound without certificate validation, measured with the default TLS buffer sizes of the ESP32 framework, against a TLS front on the local network. A tuned TLS configuration (smaller record buffers) would reduce its heap, and a remote endpoint would add network delay to its time. The 60 checks are repeated measurements in one boot, not 60 independent sessions.
7. **Static RAM is a build property.** The peak heap is an upper bound that includes framework allocations. The total with static RAM (39.5 and 46.4 KiB) is therefore conservative, but it is not a Class 2 measurement taken on a Class 2 part.
8. **Framing.** The framing is OSCORE-style, not RFC 8613: no key derivation, no sequence numbers or replay window, and no binding of release and block position into the authenticated data. Replayed and reordered authentic blocks are accepted at the frame layer and caught only by the final image digest.
9. **Handshake comparison.** TLS/DTLS figures come from host measurements and specifications, not from the ESP32.
10. **Revocation timing.** Measured on a local chain; a deployed network adds block-confirmation time. The gateway's detection time is bounded by its 5 s polling interval.
11. **Device rollback after revocation** and device rejection of tampered blocks on flash were not recorded as 60-cycle series.
12. **Energy** was not measured.
13. **Table 3 cycle 6** was re-run after a stalled contract read; the superseded row is kept in the raw CSV.
14. **Backup not power-safe.** The updater copies the running application to a backup slot before every update; an interruption of that copy leaves the delta without a base. It was caused here by the harness, but a real power loss would do the same.
15. **Block pacing.** The proposed protocol requests one block per 200 ms and is slower than the HTTPS download on this link (Section 4.6.5). The pacing was not tuned in this study.

## Still open (not resolved in this study)

- Three failures of Scenario B (two corrupted DOTA headers, one stalled transfer) had a clean start and have no known cause.
- The peak-heap difference between A and B is not robust (p = 0.158 on 58 pairs, 0.040 on 45 pairs without an interrupted cycle, 0.122 in the confirmation run).
- Device-side rollback after a revocation and rejection of tampered blocks on flash were not recorded as 60-cycle series.
- Energy (mA) was not measured; the TLS/DTLS handshake on the device was not measured.
