# Project Status

Release checkpoint 2026-09-28: public version rebaselined to **0.167a**, succeeding
v0.3.0-alpha.3. Target milestone is **1.0 beta**. Current source suite: 48 tests
passed. Clean PyInstaller build and frozen EXE smoke check passed; Windows
product/file versions both read 0.167a. This alpha preserves remaining validation
items and does not claim complete feature or physical-hardware qualification.
Release notes: [0.167a](RELEASE_v0.167a.md).

User confirmed the stale-palette export guard works. At user request, banner
cancellation now uses a large red STOP button instead of X. Existing worker
enable/disable and cancellation behavior is retained; GUI regressions pass.

Output-validity follow-up: user reproduced stale palette export opening a save
dialog. GIF/COM/ASM/DSK now check a completed conversion's source/settings
signature before opening any save dialog. Preview zoom and export-only target
card/duration are excluded. Busy/incomplete output is blocked. Regression
exercises real conversion, palette change, all four blocked export paths, zoom,
reconversion and source replacement. User retest pending.

2026-09-28: user confirmed the GUI looks and works great, including the banner,
Stop button and preview zoom follow-ups. Next proposed closeout item is output
validity: prevent stale/mismatched exports after source/settings changes and
after canceled/failed conversions, while retaining preview-only adjustments.

Output Preview zoom now defaults to Auto (whole pixels), exposed in basic
settings. It repeats each source pixel into an identical integer-sized block,
approximating CRT aspect without uneven scanline replication. Panels smaller
than the minimum preview scroll rather than downsample. Export pixels are
unchanged. Pixel-by-pixel repetition and GUI regression tests pass.

Current 512-mode fix: conversion uses only the two repeating-row patterns;
export rejects unsupported patterns instead of substituting. The 1024-mode
palette is unchanged. Unit/export tests pass; native user approval pending.

512 native color follow-up: static text export now uses CRTC R3=0 (16-character
sync width), matching Mini-Frames. Previously R3=10 triggered Marty's explicit
80-column/black-border monochrome rule despite the mode color-burst bit being
enabled. All six Old/New CGA and dither export smoke cases and 21 unit/export
tests pass after regeneration; user confirmed the corrected disk displayed perfectly.
The 640x200 text exporter shares this builder. Raiders demo/release assets have
now been regenerated with the correction, with byte-exact ASM/COM and disk
integrity checks, and launched in native Marty with composite enabled.
User confirmed Raiders looks great in native Marty; visual acceptance complete.

Native GUI layout rebuild: compact Open/Convert/Export toolbar, grouped RGB
Graphics / Composite / RGB Text selectors, contextual settings in a scrollable
sidebar, collapsed advanced controls, theme-colored panels and hover/focus help.
Previews fit their panels by default; 1x-4x zoom remains available. Existing
converter mode identifiers and export callbacks are preserved. Source GUI
review was confirmed by the user; no standalone package rebuild requested.
Follow-up restores the dedicated full-width logo banner with a native activity
bar (unknown-progress animation, known percentage, Ready/Canceled/Failed).
Detailed messages remain at the bottom. Banner user review is pending.
Banner follow-up: text Viterbi startup now returns after launching its worker,
preventing the synchronous conversion tail from prematurely setting Ready.
Stop is a native X button at the right of the banner, enabled during background
encoding. Both text-mode startup/cancellation regression checks pass; an actual
640x100 K=8 conversion confirmed live banner progress and completion state.

Approved Raster CRT branding is integrated into the source GUI (logo, window
icon and title) and PyInstaller asset/icon configuration. Generated assets use
the exact identity.json crops with square padding, with no stretching. GUI
construction and launcher smoke checks pass. No standalone rebuild performed.

Demo direction: use **640x200 (1024 Colors)** full-screen text-composite output
as the featured Studio image. The user-supplied Raiders of the Lost Ark image
replaces the interim Picard artwork; Picard assets remain for comparison.
Demo assets and settings live under `files/demo/` and are
featured in README. This choice does not replace the separate timing-test demos
or imply native visual acceptance of this mode.

Mini-Frames is retained: user confirmed native MartyPC output with and without
dithering. Its exporter now matches the approved timed diagnostic and has a
GUI display-length selector: 5/10/30/60/120/300 seconds, default 30. No keypress
exit is attempted. Timings are approximate at nominal 60 Hz. Default COM is
byte-identical to the user-confirmed diagnostic; all six GUI duration exports
and 19 exporter tests / 54 subtests pass. The prior blanket Marty incompatibility
claim is withdrawn. Next proposed item is the 512-color preview/export mismatch.

User signoff: **640x200 Multicolor Composite implementation is complete.**
The user accepted the implementation after reviewing diffusion comparisons
and requested closing this item. Resume the Mini-Frames mode review next.
Native Marty composite visual qualification remains a separate release task.

Current extension: default-off **Diffuse error during search** for Multicolor
Composite. Survivor states carry horizontal residuals; this is intentionally
approximate, with the exact solver preserved when off. All 38 tests and 59
subtests pass across focused/regression runs. Both CGA models pass GUI export
checks and Marty core COM/cold-boot bitmap checks with the option on. User A/B
visual confirmation is pending; see the Multicolor document below.

Unreleased working-source candidate: **640x200 Multicolor Composite**, using
exhaustive mode-6 bitmap search adapted from the Prince converter. Six GUI
conversion/export cases and eight Marty core COM/disk cases pass; native
composite visual acceptance is pending. The current full test suite passes
35 tests and 59 subtests. The 160x200 converter is unchanged with a clarified
description. 640x200 Mode Switch was removed from the menu and user-confirmed;
Mini-Frames remains available pending review. No package rebuild requested.
See [Multicolor candidate](MULTICOLOR_COMPOSITE.md) and the
[interactive release checklist](INITIAL_RELEASE_CHECKLIST.md).

Latest release: **v0.3.0-alpha.3**, 2026-09-27. The 320x200 palette-write selection
is now **1 / 8 / 8 staggered**. Staggered uses a fixed alternating row layout;
all seven visible boundaries move between adjacent rows. It has a separate
template/profile and passes its own 44-case / 18,736-frame core suite. Both
eight-write choices pass all 12 GUI option combinations and NASM round trips.
All 31 regression tests and 59 subtests pass. Native visual confirmation for the
new staggered profile and physical hardware qualification remain outstanding.
See [alpha.3 notes](RELEASE_v0.3.0-alpha.3.md) and
[staggered evidence](research/staggered_validation.md).

The aligned profile's template remains byte-identical to alpha.2. Its earlier
native confirmation applies to aligned 8 only. The following alpha.2 details
remain the baseline for that selection.

Aligned baseline: **v0.3.0-alpha.2**, 2026-09-27. Eight-write conversion and
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
