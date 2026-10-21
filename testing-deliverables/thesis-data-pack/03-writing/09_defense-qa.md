# Defense Q&A notes

Likely panel questions with answers that match the recorded data. Numbers come from `03-writing/01_statistical-analysis.md`. Where the honest answer is "we did not measure that", it says so: that is the stronger position in a defense.

### 1. Why compare against your own full-binary run and not against an HTTPS update or naked CoAP?
Because that is the comparison Chapter 3 defines. Its *Test Scenarios* section describes Scenario B as the full-binary update through the same pipeline, "acting as the internal control benchmark", and the *Research Design* and *Data Analysis* sections compare against "Full-OTA". The approved Experiment Paper states the same for Table 2 ("isolates the architectural efficiency against the Internal Control"). The Equation 3 and 4 passage that mentions a standard-HTTPS "Baseline A" and a naked-CoAP "Baseline B" refers to scenarios that are not among the five scenarios, so we followed the five scenarios and the approved paper. An internal control also isolates one variable, delta differencing: device, network, framing and ledger checks are identical, so the difference in time and bytes is due to the delta.
**The security tax** (Chapter 3's Absolute Difference) is reported as the sum of the directly measured security steps, so no naked-CoAP run is needed: on the device about 36.7 ms of AES-CCM decryption per delta update (0.66% of its time) and 696 bytes of framing (2.5% of the bytes on the wire); on the gateway about 60.5 ms per release. An unsecured run would differ from the secured one by exactly these steps. An external HTTPS or DTLS baseline on the board is future work, and a naked-CoAP supplementary run (about 2.5 hours) is available if the panel asks.

### 2. What is a "pair" and why do the trials go up to 69?
A pair is the same trial number completed by both A and B. Nine counted cycles failed, and a failed cycle has no completion time, so trials were added (same seed, same interleaving) until 60 complete pairs existed. The failed cycles are kept in the raw record and reported; they were not deleted.

### 3. You tested one device and one firmware pair. Is this general?
No, and the thesis says so. The result describes this test bed: one ESP32, one v1.0 to v1.1 minor patch, one 2.4 GHz Wi-Fi network. A minor patch is where differencing helps most (a typical case). The SOP 1 evidence shows the opposite case (unrelated data gives no gain). Other devices and larger changes are future work.

### 4. 9 of 138 updates failed. Is the system reliable?
The failures of the main A/B campaign were mostly a race in **our test harness**, not the architecture. The updater starts an update by itself once the gateway has staged the release; the old harness then pulsed the board's reset pin, and when the update had already begun the reset landed in the middle of the ota_0 -> ota_1 backup copy. The delta then had no base image and failed ("delta decode error"). A full binary does not need a base, so B survives it. Evidence from the serial logs: **no delta cycle failed when the device had not already started (0 of 182 clean starts across the A/B and A/N campaigns)**, against 11 of 21 interrupted A cycles. Six of the nine failures were interrupted cycles; three (all B: two corrupted headers, one stalled transfer) remain unexplained.
We corrected the harness (capture first, never reset a device that has begun) and ran a **20-pair confirmation run**: 0 failures in 40 cycles, and the results match the main campaign (time -84.65% against -84.96%). So the 6.5% (integrity rate 93.5%) describes the old harness, and the main results stand. One real property remains: the backup copy is not power-safe (an interruption leaves the delta without a base), which is why Chapter 5 recommends a verified or atomic backup. The security checks of Scenarios C, D and E are a separate matter: 180 of 180 passed.

### 5. Why is the RAM column the same for delta and full binary? Where is the RAM saving?
The approved Table 2 column is the static RAM of our technology, a build property, so it is identical in every row (28.73 KB, SD 0). Both scenarios run the same updater. The memory benefit of the architecture is not delta against full binary; it is **offloading Web3 logic to the gateway** (SOP 4): against a design that does the Web3 work on the device, offloading saves 78.5% of flash and 58% of peak RAM. Heap during the update did not differ significantly between A and B (p = 0.158).

### 6. An on-device Web3 client has less static RAM than your updater. Why offload?
True, taken alone: 3,244 B against 29,400 B. But the updater also reconstructs firmware (its largest item is the 20,312 B delta decoder), which any delta-capable device needs. The fair comparison is the updater **with** and **without** the Web3 client: 29,400 B against 32,644 B static (-9.9%), and once the TLS heap measured on the board (52,000 B) is counted, 34.7 KiB against 82.7 KiB: 165% of the 50 KiB Class 2 budget when not offloaded, 69% when offloaded. A check on the device also takes 1.41 s (96% TLS handshake), against 54 ms at the gateway.

### 7. Delta does not make flash writes faster. Does it help the device at all?
It saves transmission, not flash work. Both scenarios write the same 288,880-byte image. Flash write throughput is 5.9% lower for delta (184.3 against 195.9 KB/s), and the decoder spends 136 ms more because it reads the old image to apply the patch. Decryption is 227 ms shorter (24 blocks against 168), so decryption + reconstruction is 4.9% faster (91 ms). The benefit is transmission: 85% less time to completion and 86% fewer bytes, which on a constrained link and a battery means less radio-on time (we did not measure energy).

### 8. Is it really OSCORE?
It is OSCORE-style: pre-shared key, AES-CCM per 1 KiB block, 13-byte nonce, 16-byte tag, no handshake. It is not RFC 8613: no key derivation, no sender sequence numbers or replay window, no binding of release and block position into the authenticated data. Consequence found in testing: replayed and reordered authentic blocks pass the per-block check and are stopped by the end-of-transfer image digest. Closing this at the frame layer is listed as a recommendation.

### 9. Does the Success-Run result prove the system is secure?
No. Equation 6 gives the confidence that reliability is at least 95% after 60 failure-free trials: 1 - 0.95^60 = 95.39%. It bounds reliability for the tested faults; it is not a proof of absolute security or a zero failure probability.

### 10. Is a kill-switch delay of 2.8 seconds acceptable?
It is bounded by the gateway's 5 s polling interval (observed 0.18 to 4.98 s, mean 2.78 s) and can be tuned (shorter interval or a contract-event subscription). It was measured on a local chain; a deployed network adds block-confirmation time.

### 11. Why was the gateway a PC for A/B and a Raspberry Pi for Table 3?
The Table 2 metrics (time to completion, device timings) are measured at the device and on the wire, and do not depend on which computer runs the gateway. Table 3 is about the gateway's own cost, so it was measured on a Raspberry Pi 4 limited to Raspberry Pi 3B+ memory (1 GB, 905 MB visible) and clock (1.4 GHz). It is a faithful limit on memory and clock, not a physical 3B+ (swap was enabled).

### 12. The completion times vary a lot (22% CV). Is the result robust?
The variation is network jitter, not the device: cycles with no repeated block request are almost identical (A 5,312 ms, SD 38 ms; B 34,080 ms, SD 21 ms), and completion time rises by about 200 ms per repeated request (r = 0.999 for A). Device-side times vary by under 1%. The conclusion holds under the paired t-test, the sign test (A faster in 60 of 60), excluding cycles after a failure (84.8%), and unpaired (85.1%). The 99%/95% limits already include the jitter.

### 13. p = 10^-37 is not believable.
Paired design, 60 pairs, and a very large effect (dz = -3.8; median ratio B/A 6.4; even the smallest pair ratio is 2.9). The sign test, which makes no normality assumption, gives p = 1.7e-18 (A faster in all 60). The time differences are skewed by rare retransmissions, which is why both tests are reported.

### 14. Did you add energy or battery claims?
No. Energy (mA) was not measured. The thesis can say less radio-on time is expected from 86% fewer bytes, but must not give an energy figure.

### 15. Table 3, cycle 6, was re-run. Why?
The first run of cycle 6 had a stalled contract read (21.8 s, an RPC call to the chain on the PC). It was marked superseded and the cycle was re-measured once; the table shows the re-run. The original row is kept in the raw CSV (`table3.before-cycle6-rerun.csv`) and the provenance note under Table 3 records it. With the original value the polling average would have been 414.9 ms; the median is 51.9 ms either way.

### 16. Does resetting the device after a failure bias the next cycle?
Cycles that ran straight after a failed or invalid cycle (and so after a full device reset) were not different in completion time: A 5,313 against 5,586 ms (p = 0.10), B 40,314 against 36,839 ms (p = 0.44). The paired result without those cycles is unchanged (84.8%, p = 7e-33).

### 17. Why not simply use HTTPS? It was faster in your own test.
It was faster on time: 3.7 s against 5.6 s for the delta on this link, because our block protocol pauses 200 ms per block (a tunable design parameter, not a property of differencing). But HTTPS sent 91% more bytes (307 KB against 27 KB), needed **140%** of the 50 KiB Class 2 RAM budget (the TLS heap peaked at 65 KB) against 69% to 90% for the updater, and added 61% of the flash budget against 17%. It also secures only the channel: no multi-party approval, no revocation, and in our lower-bound test not even certificate validation. The 50 KiB is an accounting budget on a 520 KB ESP32, so the claim is "exceeds / fits the Class 2 budget", not "does not run".

### 18. What does the security cost, measured against a naked CoAP transfer?
We built that baseline: the same delta over CoAP without AES-CCM, interleaved with the secured delta, 60 matched pairs. The tax is about **43 ms** of device time per update (0.8% of the time; 95% interval 34 to 52 ms), 1.07 KB of static RAM and 17 KB of flash, with no statistically detectable effect on the time to completion (+179 ms, p = 0.20) or on peak heap. The framing adds 696 bytes by arithmetic; the measured byte difference (1,628 B, interval 69 to 3,188) contains that figure. On the gateway the security steps cost about 60 ms per release, mostly the ledger poll.

### 19. Did the harness problem affect the A/B results?
Only the failed cycles, which were excluded and replaced by extra rounds. Completed cycles are clean: early-start cycles that finished show normal times and bytes. Removing the 14 pairs with an interrupted cycle gives the same conclusions (time -85.44%, bytes -86.71%), and the independent confirmation run on the corrected harness agrees. One result is not robust: the peak-heap difference between A and B (p = 0.158 on 58 pairs, 0.040 on 45, 0.122 in the confirmation run); we report it as possible, not demonstrated.

### 20. Where is the data? Can we check it?
`sop-results/` holds the raw runs (every attempt, per-cycle serial logs and Wireshark captures) and `01-raw-data/tidy-csv/` the tidy CSVs, with SHA-256 hashes in `MANIFEST.sha256` and in the table documents. Every number in Chapter 4 is regenerated by `python -m sop.chapter4`, and the statistical functions have unit tests.
