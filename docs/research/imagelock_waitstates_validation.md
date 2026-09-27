# IMAGELOCK wait-state correction

Historical failure report. The repaired 2026-09-27 release and its separate
acceptance results are documented in [eight-write validation](eight_write_validation.md).

**The earlier harness configuration was wrong. Its reported normal wait-state/DRAM-refresh validation is withdrawn.** The failure has now been reproduced with the CPU options used by desktop MartyPC. A retuned kernel is still under validation; this document does not yet certify a replacement.

MartyPC's `Intel808x` derives `Default`, so `enable_wait_states` initially equals `false`. `MachineBuilder` leaves that setting unchanged, while the desktop frontend explicitly enables it. The original validation harness omitted that frontend step. In `cpu_808x/cycle.rs`, the false flag both suppresses memory/I/O wait states and prevents `tick_dma()` from running, even when the core configuration requests DRAM refresh simulation.

Changing only that CPU option reproduced the user's garbled exported image. The exact `TEST.COM` from `Desktop/CGAFun/cga_320_startlock.dsk` has SHA-256 `5ffd2e5ef829ae7d4b25d9aeced1b262ad8e21aa5db47d8b5078b1d53b264968`. Its code matches the delivered IMAGELOCK template outside the intended bitmap/palette patches.

With actual waits and refresh active, its corresponding palette-write intervals between rows are **331, 332, 335, 336 and 338 CPU cycles**, rather than 304. The outer frame interval remains 79,648 cycles. This produces a stationary image whose internal palette changes progressively miss their intended pixels. Phases 0–2 show 78,398 mismatching displayed dots per frame; phase 3 shows 78,050. The [captured failure](imagelock_waitstates_failure.png) matches the reported symptom.

Both permanent Rust harnesses now explicitly enable CPU wait states before executing the first CPU instruction and assert the setting. At the first timed OUT they also require the refresh-scheduling flag and independently inspect PIT1: reload 19, actively counting, retrigger enabled, and mode 2 (`RateGenerator`). These PIT observations read existing state without clocking the timer or clearing display-state flags. Each run records `phaseN-cpu-options.json`; both summarizers reject missing or incorrect evidence. A negative test that changes PIT1 to divisor 18 immediately before the first visible OUT correctly fails the assertion. New output defaults use separate `waitstates-on` directories, preserving old captures for audit.

A bounded corrected STARTLCK run also changes its interpretation: the marker is stationary within each run, but its visible onset is x=25 for phases 0–2 and x=17 for phase 3, on row 8. Its earlier all-phase x=9 claim was measured with wait states disabled and is invalid for desktop settings.

The [current evidence record](imagelock_waitstates_validation.json) includes the original disk manifest, all four corrected failure runs, the corrected STARTLCK runs, and recorded CPU-option assertions. All measurements use the unchanged Marty core at commit `05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44`; no physical hardware was tested.
