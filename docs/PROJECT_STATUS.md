# Project Status

Current release: **v0.3.0-alpha.2**, 2026-09-27. Eight-write conversion and
COM/ASM/DSK exports are enabled. All 26 regression tests and 59 subtests pass.
The corrected core acceptance suite passes 44 cases / 18,736 exact frames with
CPU wait states and active raster refresh. The user confirmed the native MartyPC
visualization was perfect. See [release notes](RELEASE_v0.3.0-alpha.2.md) and
the [current validation record](research/eight_write_validation.md).

## Current implementation

The active application is `cga_v167.py`; the exporter is `cga_mode4_lock.py`.
Profile and template live under `assets/mode4_lock`; assembly is
`tools/imagelock.asm`. Seven writes divide each visible row; the eighth sets the
next row's leading palette during blanking. The measured bounds are
0, 25, 65, 113, 161, 209, 249, 289, 320. Each region has four CGA colors;
the bitmap remains ordinary two-bit-per-pixel mode 4.

Paired PREP/MAIN timing and brief PIT1 refresh quiet windows establish repeatable
entry with normal CPU waits. Refresh mode 2/count 19 is restored before each
raster. Rows are 304 CPU clocks and frames are 79,648 clocks. The final template
rebuilds byte-for-byte from default assembly settings.

## Next steps

1. Freeze feature additions and validate the entire studio feature set, including
   all conversion modes, controls, save/load behavior, exports and error paths.
2. Record a feature-by-feature pass/fail checklist and fix discovered regressions.
3. Separately qualify timing and refresh behavior on documented physical IBM CGA
   hardware before making hardware reliability claims.

## Reproduce checks

```powershell
.venv/Scripts/python.exe -m pytest -q
tools/validate_imagelock.cmd
.venv/Scripts/python.exe tools/validate_mode4_release.py
.venv/Scripts/python.exe tools/smoke_mode4_gui.py
.venv/Scripts/python.exe tools/validate_mode4_gui_exports.py
```

The core validator requires the local MartyPC source/toolchain; NASM is needed
for validation rebuilds, but neither is required for the standalone converter.
See [Windows packaging](WINDOWS_BUILD.md) and [Picard demo](IMAGELOCK.md).

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
