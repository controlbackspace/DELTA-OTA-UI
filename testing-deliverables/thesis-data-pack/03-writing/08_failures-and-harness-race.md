# Failures and the harness race

Text of Section 4.7.5 of the chapter draft (keep in sync). The tables behind it are in `01_statistical-analysis.md` (section 5), `01-raw-data/tidy-csv/table2_failures.csv` and `01-raw-data/RUNS-INDEX.csv` (which runs used which harness).

*Hand-written source (not generated). Numbers are from `01_statistical-analysis.md`; update both together.*


Chapter 3 defines the update integrity rate as the percentage of successful, verified updates. Counting every attempt of the main A/B campaign:

| | Successful | Failed | Rate (Wilson 95% interval) |
|---|---|---|---|
| A: delta | 65 | 4 | 94.2% (86.0% to 97.7%) |
| B: full binary | 64 | 5 | 92.8% (84.1% to 96.9%) |
| Both | 129 | 9 | 93.5% (88.1% to 96.5%) |

All nine were detected by the device and reported as failed updates, and none of the nine logs shows a reconstructed image. A and B failed at the same rate (Fisher exact p = 1.0). The causes were four flash-write errors in A, and in B three stalled transfers and two corrupted-header rejections.

**The cause of most failures was found in the serial logs, and it was a race in the test harness, not the architecture.** The updater starts an update by itself once the gateway has staged the release. The harness then pulsed the board's reset pin to start the update. When the device had already begun, the reset landed in the middle of the updater's ota_0 -> ota_1 backup copy. After the reboot the backup was incomplete, so the delta had no base image and failed ("delta decode error"). A full binary does not need a base, so B survives an interrupted backup.

| Cycles (counted) | Update interrupted by the harness: ok / failed | Update started cleanly: ok / failed |
|---|---|---|
| A, main campaign | 5 / 4 | **60 / 0** |
| B, main campaign | 11 / 2 | 53 / 3 |
| A, naked-CoAP campaign | 5 / 7 | **59 / 0** |
| N, naked-CoAP campaign | 4 / 4 | **63 / 0** |

No delta cycle (A or N) failed when the device had not already started, in 182 clean starts across the two campaigns. Of the nine failures of the main campaign, six (all four of A and two stalls of B) were interrupted cycles; the other three, all in B (two corrupted headers, one stalled transfer), had a clean start and **remain unexplained**.

**Verification.** The harness was corrected: the capture now starts before the release is published, and the board is reset only if the update has not begun; a device that began on its own is left alone. A 20-pair A/B confirmation run on the corrected harness had no failure in 40 counted cycles (a single B harness stall, re-run), and 77 consecutive cycles of the naked-CoAP campaign after the correction had none. The confirmation run agrees with the main campaign (Section 4.7.6), so the main results stand. The 6.5% failure rate of the main campaign is an artifact of the earlier harness and is **not** a property of the architecture; the update integrity rate of cleanly started delta updates was 100% in these runs.

**A real property of the updater remains.** An interruption of the backup copy breaks the delta, so the backup is not power-safe: a genuine power loss at that moment would fail the update in the same way (without installing a bad image). A verified or atomic backup would remove the dependence (Chapter 5).

Cycles that ran straight after a failure and a device reset were not different from the others (A: p = 0.10; B: p = 0.44), and repeating the paired test without them gives the same result (84.8%, p = 7 × 10⁻³³).
