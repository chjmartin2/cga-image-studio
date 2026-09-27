# Project Status

Checkpoint release: **v0.3.0-alpha.1**, 2026-09-26. All 24 software regression
tests pass. Two serialization tests now explicitly enable a test-only profile;
the real withdrawn-profile export guard remains active and independently tested.
Windows standalone packaging and a repeatable runtime smoke check have been added.
This checkpoint does not certify the retuned raster or complete feature validation.
The agreed sequence is: finish eight-write exports, freeze features, then validate
every feature. See [release notes](RELEASE_v0.3.0-alpha.1.md).

Restart checkpoint: 2026-09-14. Active application: `cga_v167.py`.

**The native garbled-image failure is reproduced.** The original STARTLCK and
IMAGELOCK validation harnesses omitted `CpuOption::EnableWaitStates(true)`.
The native frontend sets this option explicitly. Without it, the CPU suppressed
memory/I/O waits and skipped refresh DMA stalls despite the requested refresh
setting. Enabling it in the harness reproduced the user's reported failure.
The earlier passing matrices do not validate the native configuration.

See the [investigation](research/garbled_export_investigation.md),
[source audit and untouched reports](research/waitstates_disabled_archive/README.md),
and [corrected wait-state-enabled validation](research/imagelock_waitstates_validation.md).
Do not combine old and corrected measurement counts.

## Current implementation

The application is `cga_v167.py`; the acquired mode-4 exporter is
`cga_mode4_lock.py`, with its template and geometry under `assets/mode4_lock`.
The eight-write GUI choice connects conversion, preview, COM, ASM, and DSK to
that shared profile. Seven writes divide the active picture; the eighth supplies
the following row's leading palette. Row-zero palette ownership is shared
between the initial bridge and the last row of each frame.

The original 40-NOP schedule and its measured boundaries were calibrated with
wait states disabled. They are not a valid native timing baseline. The current
[IMAGELOCK guide](IMAGELOCK.md) and corrected validation record identify the
replacement profile and the exact evidence supporting it. Hardware validation
remains outstanding.

The software still stores two bits per pixel in ordinary 320x200 CGA mode 04h.
Each region has four colors selected from CGA palettes; this is not unrestricted
sixteen-color selection at every pixel. GUI options include one or eight
writes, dithering, dither-aware palette optimization, and border constraints.
Historical programmatic callers without a timing backend retain legacy behavior.

## What the earlier checks do and do not establish

All 23 export regression checks passed, including exact NASM rebuilds and
palette/bitmap patch checks. The actual GUI conversion and disk-export methods
were also exercised across 12 combinations of dithering family, dither-aware
optimization, and black-border selection; every exported bitmap/palette plan
reconstructed to all 64,000 preview pixels. These establish software data
consistency, not raster timing.

The old harness reported 1,225 Picard frames, 269 REGLOCK frames, 2,162 independent
startup-matrix frames, and 14,396 cold-boot image frames. The marker harness
reported 1,225 matching visible frames and a separate 3,600-pulse disk run.
**All these counts are invalid as evidence for native wait-state-enabled timing.**
They remain preserved in the archive with their original JSON and hashes.

The original [STARTLCK timing claim](research/startlock_validation.md) is also
withdrawn. A bounded corrected run places its marker at x=25 for PIT phases
0-2 and x=17 for phase 3, on row 8: stationary within runs but not repeatable
across startup phases. Correcting the image kernel does not retrospectively
validate that older marker binary.

## Next steps

1. Measure the replacement raster with effective CPU wait states and refresh DMA
   execution enabled, matching the native frontend. Record actual options and
   binary hashes in the result artifact.
2. Compare every palette boundary and the first/last rows over startup phases,
   normal disk boots, and repeat launches. Confirm the same output in native MartyPC.
3. Only after that passes, test documented original IBM CGA hardware before
   increasing write density or treating the timing question as settled.

Published hardware research remains valid: the released Lake initializer has
20,445 matching observed instruction fetches in a physical IBM 5150 capture,
and measured main-ISR intervals of 79,648 CPU cycles. That evidence establishes
beam synchronization is possible; it does not certify this application's kernel.
See [CGA timing research](CGA_TIMING_RESEARCH.md).

## Local checks and historical references

Run `.venv/Scripts/python.exe -m unittest discover -s tests -v` for software
regressions. NASM is required for byte-exact assembly round trips, not normal
application export. Bootable DSK export requires `files/dos_boot_template.dsk`.
Existing experiment files and captures should retain their provenance.

- [CGA lockstep milestone](cga-lockstep-milestone.md): older timing experiments.
- [Mode Switch diagnostic](modeswitch-diagnostic.md): older two-write UI.
- [Refactor plan](REFACTOR_PLAN.md): historical modularization proposal.
