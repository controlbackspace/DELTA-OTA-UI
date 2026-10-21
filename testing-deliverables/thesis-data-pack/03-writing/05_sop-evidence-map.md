# SOP evidence map

For each Statement of the Problem: the instrument, the formula, the headline result and where it sits in the chapter draft. What can and cannot be claimed is in `02_claims.md`.

*Hand-written source (not generated). Numbers are from `01_statistical-analysis.md`; update both together.*

### SOP 1: payload optimisation by binary differencing
- **Question:** the measurable impact of binary differencing on payload footprint and bandwidth saturation.
- **Instrument / formula:** Table 1 (static) and the wire-byte and block columns of the A/B data; Equation 3.
- **Result:** patch 22,497 B against image 288,880 B, 266,383 B saved, **92.21%**. On the wire: 27,499 B against 198,211 B, **86.13%** fewer (paired t = -50.20, p = 4.2e-50, dz = -6.48, A fewer in 60 of 60). Blocks: 24 against 168 (**85.71%**).
- **Draft:** Section 4.3. **Figure:** `fig-01_payload.png`.

### SOP 2: OSCORE-style framing against standard handshakes
- **Question:** memory and latency reduction of the OSCORE approach against standard cryptographic handshakes.
- **Instrument / formula:** per-block timings from the A/B serial logs, Table 3 (encapsulation), the SOP 2 evidence report; Eq. 1, 2.
- **Result:** on the ESP32 one 1 KiB block decrypts in 1,528.6 µs (SD 3.1); a whole delta update spends about 36.7 ms decrypting, 0.66% of its time to completion. Gateway encapsulation: 6.13 ms for 24 blocks. Framing overhead 29 B per block, **no handshake**; a TLS 1.2 handshake would add 1,021 B in 4 flights (3.7% of a delta update's bytes) and an assumed ~101 ms (1.8% of its time).
- **Draft:** Section 4.4.

### SOP 3: deterministic reliability of ledger-anchored authenticity and revocation
- **Question:** the deterministic reliability of ledger-anchored smart contracts for authenticity and absolute revocation.
- **Instrument / formula:** Table 4 (Scenarios C, D, E); Equation 6; the SOP 3 evidence report (27 of 27 contract tests, 270 of 270 injected faults stopped).
- **Result:** 60 of 60 in each scenario, **0 failures**; C = 1 - 0.95^60 = **95.39%**. Kill-switch delay (revocation sent to refusal) mean 2,785 ms, range 176 to 4,981 ms, bounded by the 5 s polling interval.
- **Draft:** Section 4.5.

### SOP 4: offloading Web3 logic to the Edge Gateway
- **Question:** efficiency of offloading Web3 logic to the gateway in preserving the device's memory envelope (SRAM) and processing cycles.
- **Instrument / formula:** Table 3 (gateway profile), the SOP 4 supporting data, heap peaks from the A/B logs; Eq. 1, 2, 4, 5.
- **Result:** gateway per release: polling 54.13 ms, SHA-256 0.230 ms, AES-CCM 6.13 ms, 80.9 MB, 30.4% CPU. On the ESP32, one on-device ledger check takes 1,414 ms and peaks at 52,000 B of heap. Like-for-like (updater against updater + on-device Web3): flash **-78.47%**, static RAM -9.94%, peak RAM **-58.00%** (84,644 B = 165% of the 50 KiB Class 2 budget against 35,548 B = 69%).
- **Draft:** Section 4.6. **Figure:** `fig-05_ledger-check-and-ram.png`. **Data:** `03-writing/11_sop4-supporting-data.md`.

### SOP 5: systemic performance over 60 automated cycles
- **Question:** performance of the complete architecture across cryptographic time, memory and CoAP latency over multi-cycle testing.
- **Instrument / formula:** Tables 2 and 3; Eq. 1, 2, 5; paired t-test.
- **Result:** time to completion **5,571.1 ms against 37,051.8 ms (-84.96%)**, t = -29.49, p = 5.2e-37, A faster in 60 of 60 pairs, 99%/95% limits 9.0 s against 60.5 s. Decryption + reconstruction 1,753.9 ms (SD 16.3). Flash write 184.3 against 195.9 KB/s (A **5.9% lower**). Static RAM 28.73 KB (SD 0). Spread of completion time explained by repeated block requests (r = 0.999; cycles with none: SD 38 ms).
- **Draft:** Section 4.7. **Figures:** `fig2`, `fig3`, `fig4`.
