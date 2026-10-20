# Project Status

2026-10-20 release candidate **v1.0.0-rc.1** brings the current converter,
standard RGB text controls, promoted 640x200 composite search, repeating
scanline palettes, black-border export and MartyPC link into one release.
The Windows x64 executable includes CPU acceleration and runs without Python;
CUDA remains optional for source installations. The approved 24-image demo
disk and gallery accompany the release unchanged. See the
[release notes](RELEASE_v1.0.0-rc.1.md) for downloads and validation.
Full interactive acceptance, clean-machine Windows qualification and physical
CGA hardware qualification remain open.

2026-10-19 Boundary-aware DCT removed at the owner's request after evaluation.
Removed its matching option, optimizer participation, refinement implementation
and dedicated tests. Standard DCT remains the stock default with preconversion
dithering off. GPU acceleration, the live DCT Tweaker and the diffusion overflow
fix remain in place. The earlier entry below records the historical experiment.

2026-10-19 text preconversion diffusion fix: bound corrected linear RGB before
both palette selection and residual calculation. Previously only selection was
clipped, so saturated patches accumulated impossible overflow and contaminated
following rows. Diffusion gain now follows the UI's 0-1 range, and text Optimize
canonicalizes the same range. Kernel weights, signed cross-row error, serpentine
scan order and optional preprocessing behavior are preserved. Regression coverage
includes all nine kernels, both scan directions, fractional/full gain, saturated
region depth, gray transitions, repeat-call isolation and optimizer gain bounds.
The RGB-to-gray fixture eliminated the old color tail; before/after captures and
measurements are in `artifacts/standard-text-validation/diffusion-fix/`.
Validation: 110 diffusion/engine/optimizer tests and the text preview/export UI
workflow passed. The saturated RGB-to-gray fixture's outgoing peak residual
fell from 7.65 to 0.091; its first 16 gray rows now reproduce the gray exactly.

2026-10-19 Boundary-aware DCT: removed Perceptual DCT at the owner's request.
The new text matcher preserves standard DCT's RGB channels and weights, seeds
from ordinary DCT, then refines all overlapping 2x2-character windows. Each
conditional cell update searches all 65,536 glyph/color combinations; four
independent phases batch safely on CUDA/CPU. Strict improvements repeat until
convergence, with cancellation, CPU restart on device failure and cached-cell
exports. This is a local optimum of a coupled objective, not a guarantee of
better-looking art or a global optimum. Standard DCT, stock weights and no
preconversion dithering remain the defaults. See [text matching](STANDARD_TEXT.md).
Validation passed 96 engine/search/GPU tests and both separate UI workflows.
Gadget's standard DCT output remained byte-identical to the saved prior baseline.
Boundary refinement changed 6/1 cells at 40/80 columns; both converged after two
passes, with exact CPU/GPU rendered parity. Warmed RTX 3090 runs took 0.20/0.32
seconds including the seed and refinement, excluding input preparation/UI.
Comparison images, HTML, COMs and JSON: `artifacts/standard-text-validation/boundary-dct/`.

2026-10-19 standard text GPU acceleration: normal conversion, live DCT and
Optimize now select the available CUDA backend automatically. All candidate
scores remain float64; CPU tie refinement preserves rendered output for
ambiguous averaging matches. Optimize combines CPU preparation/dithering with
a shared GPU matching pipeline and falls back to the full CPU search on device
failure. Native RTX 3090 checks passed; warmed DCT matching measured about
23/48 ms for 40/80-column Gadget, excluding preprocessing/UI. GPU and CPU
optimization selected identical Gadget settings/scores. Validation passed 80
engine/search/GPU tests, both separate UI workflows and 64 layout subtests.

2026-10-19 text Optimize and DCT Tweaker: both text column modes now expose
Optimize, comparing all matching methods, preprocessing and resize filters
against a fixed multiscale visual reference. Height and CGA-reduction remain
fixed. When reduction is selected, all dither families/kernels/matrix sizes and
directions are searched on a declared strength grid plus current values.
Parallel CPU workers share exact-equivalent input work and have deterministic
selection/cancellation. A live DCT window adds four weighting controls, 250 ms
debouncing, cancellation of superseded jobs and prepared-input reuse. Exports
use the latest valid cached result. Original + DCT remains the baseline when
selected; the optimizer can test whether other settings lower the common score.
See [text controls, search scope and measured results](STANDARD_TEXT.md).

2026-10-19 text input preview and height restriction: character heights now
accept only 2-8 scanlines in the UI and encoder. The Input pane switches between
Source and Text input; Preview text input runs preparation without character
matching, and Convert shows the exact same intermediate raster it uses. Stale
previews are hidden after settings/source changes. Cartoon simplify's median
filter and 16-level-per-channel posterization are explained in the help.
The updated text tests passed 56 cases; the all-mode layout check passed 64
subtests. Existing emulator captures cover all 14 remaining geometries.

2026-10-19 standard RGB text converter: added 40/80-column modes (40x25 and
80x25 at eight scanlines/cell), six exhaustive character-matching objectives,
optional simplification and preconversion dithering, and CGA character heights
2-32. Preview/export share encoded character attributes. All 62 column/height
configurations matched native MartyPC RGB captures exactly. Focused engine,
worker and export tests passed (114 tests, 9 subtests); the all-mode UI layout
check passed 64 subtests. No packaged release or hardware qualification yet.
The broader artist-style global optimizer remains a documented TODO.
See [standard text implementation](STANDARD_TEXT.md).

2026-10-19 per-line tweaked palette correction: Tweaked On now adds the two
tweaked families instead of removing all four standard families. The owner's
banded planet is exactly representable and now recovers all 64,000 pixels with
None, Ordered and Floyd–Steinberg dithering. Shared candidate construction keeps
Repeat's pool/order intact. See [planet audit](SCANLINE_PLANET_AUDIT.md) for
exhaustive bounds, reproduction and the required uniqueness setting.

2026-10-19 N=1 black-border export wiring: the checkbox now selects a separate
acquired overscan-write path for single-line and Repeat modes, retaining image
background/palette choices. Toggling it no longer requires reconversion for
these modes; COM/ASM/DSK/Marty routes share the flag. The unchecked legacy path
and eight-write binary remain intact. **Exact-edge qualification is incomplete:**
direct-load pixel-clock phases 0-2 passed 639 diagnostic frames, but the default MartyPC
renderer retains a one-pixel seam and pixel-clock phase 3 has wider edge errors.
DOS boot/reentry also produced a two-pixel image-edge error on one launch,
even with pixel-clock rendering and PIT phase 0; the next launch was exact.
This is an experimental implementation with documented residual defects, not a
universal black-border fix. See [border implementation and limits](N1_BORDER.md).

2026-10-19 Repeat efficiency evaluation: profiling identified candidate dithering
as 79% of a six-row run, with about 12% in palette-search functions. Removed
repeated fixed-palette setup, exact duplicate color matching, repeated source
scoring/pyramid work, unreachable target-union mask dimensions and linear
shortlist membership scans. Candidate counts, arithmetic and tie-breaking are
preserved. Six sequential full-size before/after pairs saved 7-43% of conversion
time, with identical pixels, palette schedules, COM bytes and non-timing search
diagnostics. Fifteen additional full-engine comparisons also matched exactly;
113 focused tests and 165 subtests passed. See
[performance evaluation](REPEAT_PERFORMANCE.md) for timings, limitations and
reproduction. Source launcher uses the optimized engine; no packaged release
or website publication was performed.

2026-10-19 Repeat background expansion: replaced Force black with all 16 named
CGA backgrounds. **Adjustable** remains the default. **Forced No Repeats**
optimizes backgrounds subject to unequal adjacent rows, including the last/first
cycle edge; nonadjacent reuse is legal. Foreground combinations remain unique
throughout the cycle independently of background selection. Fixed backgrounds
retain the existing four/six-foreground-family limits and tweaked behavior.

The new constraint participates in search through an exact additive ring DP for
shortlisted unions, with all foreground orders and legal background variants.
Broad union screening uses the relaxed phase lower bound. Export guards enforce
fixed colors and every cycle edge. Validation passed 132 focused tests and 231
subtests across targeted runs, including a brute-force ring oracle, all 16 fixed
background registers, cycle-wrap rejection and stale-export protection. One
known transient Tcl startup failure passed in an isolated process. Seven real
GUI conversions saved exact PNGs and independently decoded COMs, covering repeat
lengths 2-6, diffusion, ordered dithering, Brown and Blue. Three-/six-row diffusion
took 14.91/17.46 seconds. Artifacts and reproducible checks are in
`artifacts/repeat-background-validation/`; details are in [Repeat mode](REPEAT_MODE.md).
No executable rebuild, push or release was performed.

2026-10-19 Repeat correction: fixed excessive downward diffusion and replaced
duplicate cycle slots with mandatory **foreground-three uniqueness**, regardless
of background. The renderer now uses the same corrected linear RGB bounded to
`[0,1]` for palette matching and outgoing residual. Previously matching clipped
the value while the residual retained unbounded overflow. Fixed-source,
fixed-cycle tests isolate the correction: Floyd-Steinberg's maximum residual
dropped from 61.616 to 1.0 in a bright-to-gray test, with 83.5% less mean-color
error below the edge. Picard's fixed-cycle score improved from 0.03326 to 0.02430
and its downward cyan/magenta bleeding visibly decreased.

The owner clarified that Repeat's Tweaked option must add both tweaked foreground
combinations to the four standard ones. The exact phase DP now processes each
foreground group at most once while searching its background variants and cycle
position. Adjustable offers 2-6 rows; selecting 5 or 6 automatically enables
tweaked combinations. Force black offers up to four rows with Tweaked off, six
with it on. Explicitly turning Tweaked off clamps a longer cycle to four and
explains the change. Background differences never satisfy uniqueness. The
original independent-row mode retains its existing palette-family behavior.

Verification: 212 focused tests and 324 subtests passed across the final targeted
runs, including exhaustive grouped-search oracles, every diffusion kernel,
foreground/background independence, UI auto-enabling, stale-export rejection,
mixed-mode COM/ASM/DSK/Marty data paths, and original-mode regressions. Repeated
Tk construction still intermittently fails in Tcl startup; affected cases passed
in fresh processes, with no remaining assertion failure. Ten full-image cases
independently decoded to the exact preview pixels and unique foreground cycles.
Diffusion wall times were 14.39-31.12 seconds while other checks ran concurrently;
None cases took 0.65-6.74 seconds. An actual GUI six-row Force black/Ordered 2
conversion took 1.09 seconds and used all six foreground combinations. Mixed
cycles reuse the existing N=1 paired 3D8/3D9 register path; no assembly change or
new physical-hardware timing qualification was made.

See [Repeat correction details](REPEAT_MODE.md). Local before/after comparisons,
COMs, source hashes and reports are in `artifacts/repeat-diffusion-fix/` and
`artifacts/repeat-fix-validation/`. These supersede the earlier duplicate-slot
policy below. No executable rebuild, push or release was performed.

2026-10-19 repeating-palette source update: added **320x200 Mode Switch Repeat**
with a 2-to-6-row cycle (default 2). Each slot selects one complete legal CGA
four-color palette, and all 200 scanlines repeat that schedule. Its separate
**Background** selector offers **Force black** and **Adjustable** (default).
Adjustable selects a background for each cycle slot; Force black reserves the
background slot for black everywhere. The original mode retains its all-16-color
plus Per line selector and remembered settings. Repeat slots can reuse palettes;
the original adjacent-row uniqueness constraint does not apply to this mode.

The new `cga_repeat.py` engine exactly screens all reachable color unions using
all source pixels and an additive phase-cover dynamic program. It freely dithers
the entire image against up to ten shortlisted unions, then renders up to three
legal cycles against both the original and freely dithered targets. Diffusion
carries signed linear-light error across palette boundaries. None, ordered and
all existing diffusion kernels are supported, as are standard/tweaked palettes.
The final dithered search is bounded, not a global-optimality guarantee. The
ordinary independent-row encoder is unchanged; all 12 saved output/palette
baselines remain identical.

Validation: 145 focused tests passed across the final targeted runs, covering
brute-force checks of both exact search stages, independent diffusion oracles,
GUI visibility and conversion dispatch, both background policies, stale-output
protection, and original-mode regressions. COM/ASM/boot-disk/Marty routing tests
retain the exact preview pixels; ASM reassembles to the same COM. These are data
and launch-routing checks, not new emulator or physical-hardware qualification.
The existing single-palette-per-scanline COM kernel is reused unchanged.
An unmocked GUI open/convert/PNG-save/COM-export smoke also passed with six rows,
tweaked palettes, Force black and Ordered 2. Conversion took 2.02 seconds;
the saved PNG and independently decoded COM exactly matched the preview.
Its artifacts and reproduction script are in `artifacts/repeat-validation/gui-smoke/`.

Seven full-image benchmark cases and a comparison sheet are saved locally in
`artifacts/repeat-validation/`. Floyd-Steinberg conversions took 14.24-15.31
seconds; a six-row None case took 3.49 seconds. All seven COM files independently
decode to the preview's exact palettes and pixels. Results require owner visual
review: Picard's two-row cycle retains more facial detail than the three-row
standard cycle; Gadget's selected cycle reuses a single palette and loses yellow
facial color. Larger cycles and adjustable backgrounds do not guarantee better
results under the bounded search. The demo proposal/selection was not changed.
No executable rebuild, release or push was performed.

2026-10-19 layout-map update: the owner confirmed the optional unique-palette
constraint works well. The Mode Switch layout map now has independent Auto,
1x, 2x, 4x and 8x zoom, horizontal/vertical scrollbars and mouse-wheel scrolling
(Shift for horizontal). Integer nearest-neighbor scaling preserves every row;
the fixed viewport and independent resize callback prevent preview resize
feedback. Zoom does not reconvert or invalidate exports. Actual Tk checks
verified exact pixel repetition, scrolling, unchanged output preview/source
pixels/signature, and cleanup. Existing UI/export checks passed across the
aggregate run and one isolated rerun after a transient Tcl startup failure.

2026-10-19 follow-up: the owner accepted the new single-scanline encoder's
output quality as the baseline. Added **Force unique palette per scanline** to
Advanced settings for 320x200 Mode Switch with one palette per scanline. It is
off by default. When enabled, each row excludes the preceding row's three
foreground colors, regardless of background or foreground-slot order. Fixed
and Per line backgrounds remain independent; bright/dim combinations are
distinct, and A-B-A sequences remain allowed. All search and fallback passes
obey the constraint, and replay rejects a violating schedule.

Verification: 97 targeted tests and 143 subtests passed, including independent
COM register decoding, all dither families, standard/tweaked palettes, background
independence, exact replay, Advanced visibility, and export invalidation. All
12 pre-change pixel and palette-schedule baselines remain identical with the
option disabled. A full GUI Picard conversion completed in 32.07 seconds with
zero repeated foreground combinations across all 199 row boundaries; its COM
export retained the exact palette-register table. Artifacts are saved locally
as `artifacts/scanline-validation/picard-unique-palette.png` and `.com`.
No release or executable rebuild was performed.

2026-10-19 local source update: **320x200 Mode Switch, one palette per scanline**
now exposes all 16 fixed background colors plus **Per line**, with the selection
preserved through mode changes and honored by COM export. Dither-aware search
defaults on for this profile and shares its linear-light renderer with final
output: selected kernels, serpentine direction, ordered coverage, signed error
and winner-only carry agree. Up to three independent full-image passes are
compared by a two-dimensional perceptual score; this is a bounded search, not a
global-optimality guarantee. Multiple palettes within a scanline are outside
this change and remain excluded from the owner's demo proposal.

Validation covers independent diffusion transport, color/gamut math, exact
palette-schedule replay, full-image selection, all 16 backgrounds in both
standard/tweaked families, independently decoded COM pixels, and the visible
GUI controls. The aggregate run had 109 passing tests and 182 passing subtests;
two Tk interpreter startups failed while loading installed Tcl files. Both
cases passed in isolated processes; a third transient startup failure on the
GUI-only rerun also passed in isolation. No assertion failure was observed.
Gadget/Picard comparison images and measured timings are saved locally in
`artifacts/scanline-validation/`. Final full conversions measured 18.01 seconds
for fixed-black Picard and 34.18-34.59 seconds for floating Picard/Gadget.
Whole-frame scores improved about 4-6% against the former renderer, but visual
tradeoffs remain: less stripe clutter can come with broad gray/orange regions
in Picard and a less yellow Gadget face. Numerical scoring is not visual
acceptance. Native visual review remains with the owner;
no standalone executable rebuild, release or push was performed.

Export-validity closeout: new regression cases exercise all four export paths
for missing output, changed source/mode/settings, in-progress work, cancellation,
failure and successful reconversion. Preview/export-only changes remain allowed.
Fixed old text-worker callbacks overwriting newer conversions and completion
queued before STOP accepting a canceled result. Text chroma low-pass (tone)
is now included in its conversion signature. All 52 regression tests passed;
user confirmed the final interactive checks on 2026-09-28. Item closed.
Next: 640x100 text-composite exports in Marty (appearance, duration, exit, rerun).

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
