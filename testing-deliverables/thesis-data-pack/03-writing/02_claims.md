# Claims: what the data allow, and what they do not

Use this when writing the Results and Discussion and the Conclusions. Each SOP lists what can be claimed and what cannot, then a one-page checklist.

*Hand-written source (not generated). Numbers are from `01_statistical-analysis.md`; update both together.*

### SOP 1: payload optimisation by binary differencing
- **We can claim:** delta differencing removes 92.2% of the stored payload and 86.1% of the traffic for a minor patch (v1.0 to v1.1). The result is significant under every test we ran.
- **We cannot claim:** that every update shrinks this much. One firmware pair was tested; the SOP 1 evidence shows unrelated inputs (incompressible noise) give no reduction. B is the full image **deflated** (168 blocks); raw it would be 283 blocks. Airtime and fleet times in the draft are **modelled** lower bounds.
- **Against the standard approach (Chapter 3 Baseline A, Eq. 3):** the full image over HTTPS puts 307,411 B on the wire against 27,499 B for the delta: **91.05% fewer bytes** (measured, 60 downloads, `03-writing/07_baselines-results.md`). H is a lower bound (no certificate validation, default TLS buffers).

### SOP 2: OSCORE-style framing against standard handshakes
- **We can claim:** the security cost per block is small, constant and predictable on the device, and there is no handshake state or traffic.
- **We cannot claim:** that we measured a TLS or DTLS stack on the ESP32. The TLS figures are host measurements and specification values (**modelled/literature**), not device measurements. The framing is **OSCORE-style**, not RFC 8613 (no key derivation, no sequence numbers or replay window, no binding of release and block position into the authenticated data).
- **Security tax measured (Chapter 3 Baseline B, Absolute Difference):** secured delta (A) minus the same delta over naked CoAP (N), 60 matched pairs: **+42.7 ms** of decryption + reconstruction (95% CI 33.9 to 51.6, p = 8e-14; 0.8% of the time), time to completion **+179 ms, not significant (p = 0.20)**, +1,628 B on the wire (CI 69 to 3,188; the framing arithmetic is 696 B), +1.07 KB static RAM, +16.9 KB flash. A TLS handshake still rests on host measurements.

### SOP 3: deterministic reliability of ledger-anchored authenticity and revocation
- **We can claim:** in 180 of 180 trials a tampered patch was never staged, a revoked release was never served, and a release without 2-of-3 approvals never went live; the data support at least 95% reliability at 95.39% confidence.
- **We cannot claim:** absolute security or a zero failure probability (Eq. 6 is a bound). Replay and reorder of authentic blocks are accepted by the per-block check and stopped only by the image digest (60 of 60 in the evidence report). Revocation timing was measured on a local chain (no block-confirmation delay). Device-side rollback after revocation and rejection of tampered blocks on flash were not recorded as 60-cycle series.

### SOP 4: offloading Web3 logic to the Edge Gateway
- **We can claim:** offloading keeps the device inside the Class 2 envelope; doing the Web3 work on the device does not (the minimal client alone needs 108% of the RAM budget once its heap is counted).
- **We cannot claim:** that the updater has less static RAM than a minimal read-only Web3 client taken alone (it has more: 29,400 B against 3,244 B, because it also reconstructs firmware). We cannot claim a RAM reduction of delta over full binary (static RAM identical; heap difference not significant, p = 0.158). The on-device client is a lower bound (read-only, no certificate validation, default TLS buffers, local TLS endpoint). The gateway and device ledger-check times are not exactly comparable (HTTP against TLS).
- **Against an HTTPS client (Eq. 4):** peak RAM (static + heap) is **71,668 B = 140%** of 50 KiB for HTTPS, against 35,534 B (69%, A's mean heap) to 46,072 B (90%, A's maximum): **50.4% to 35.7% less**. Flash: 72.3% less. Static RAM alone is higher for A (29.4 KB against 6.3 KB, the delta decoder). Say "exceeds / fits the Class 2 budget", never "runs / does not run on a Class 2 device" (the board has 520 KB).

### SOP 5: systemic performance over 60 automated cycles
- **We can claim:** delta cuts update time by about 85% on this test bed and the result is robust (paired t, sign test, with and without cycles after a failure, unpaired). Device-side work is very stable (CV below 1%); variability comes from the Wi-Fi link.
- **We cannot claim:** that delta is faster on the device's flash path (throughput is 5.9% lower; the decoder takes 136 ms longer and decryption 227 ms less, net 91 ms faster), that the system is free of failures (9 of 138 counted attempts failed, 6.5%, cause unresolved), or generality beyond one device, one firmware pair and one Wi-Fi network. Energy was not measured.
- **Time against HTTPS: the delta is slower.** H completes in 3,733 ms (SD 405) against 5,571 ms for A (A is 49% longer; Welch p = 5e-17). It comes from the block protocol's 200 ms request pause, a tunable design parameter (Chapter 5). Report it plainly.
- **Failures: a test-harness race, not the architecture.** The updater starts updating by itself once the release is staged; the old harness then pulsed the reset pin, which interrupted the ota_0 -> ota_1 backup copy so the delta had no base. **0 of 182 cleanly started delta cycles failed**; a corrected harness had 0 failures in 40 confirmation cycles. Three B failures (2 bad headers, 1 stall) remain unexplained.

## Quick claims checklist

**Safe to state (with the numbers in `03-writing/01_statistical-analysis.md`)**
- Patch 92.21% smaller; 86.13% fewer bytes on the wire; 85.71% fewer blocks.
- Time to completion 84.96% shorter, highly significant, in 60 of 60 pairs; 99%/95% worst case 9.0 s against 60.5 s.
- 180 of 180 security trials passed; Success-Run 95.39%.
- Offloading saves 78.5% of flash and 58% of peak RAM against a non-offloaded design, and 1.4 s per ledger check.
- The gateway's work per release is small (about 60 ms of security work; 81 MB; 30% CPU on 3B+ limits).

**Must be stated with its caveat**
- RAM: static RAM is a build property; delta against full binary shows no RAM difference.
- The flash write rate is 5.9% lower for delta; the net decrypt + reconstruct gain is 4.9%.
- The 6.5% failure rate of the main A/B campaign is a harness artifact (6 of 9 failures were interrupted updates); 0 of 182 cleanly started delta cycles failed; 3 B failures are unexplained.
- TLS/DTLS comparison is modelled (host and specifications), not measured on the device.
- The on-device Web3 client is a lower bound; its comparison with the gateway poll is HTTP against TLS.

**Do not state**
- "Zero failures" overall (3 B failures are unexplained) or "absolute security".
- "RAM reduction of delta over full binary".
- Any energy saving.
- Generalisation to other devices or firmware without a caveat.

