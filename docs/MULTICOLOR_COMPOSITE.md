# 640x200 Multicolor Composite — implementation candidate

The new mode optimizes every bit of a standard 640x200 mode-6 bitmap against
Studio's Old/New CGA NTSC simulation. It is distinct from both the 160x200
16-color palette converter and the character-based 640x200 composite mode.

## Method

Exhaustive is an exact Viterbi/dynamic-programming search over the decoder's
2048 possible eleven-bit history states. Each decoded sample depends on twelve
bitmap bits. The objective minimizes summed squared RGB error over each row,
including neighbor effects, with black borders and a fixed carrier phase.
This is exact for that model and objective, not a guarantee of an exact match
to every monitor or of a perceptually superior result for every image.

The implementation follows the formulation in Prince DAT Explorer's
`editor/composite_converter.py` (`artifact_window_table`, `_optimize_row_exhaustive`).
Reference checkout HEAD: `6787a178d4fc7698f5a18f62d825853448b5ba6a`;
inspected converter SHA256:
`d525e0372dd304447d6e9d90799ac200d5b816ff5128bf35b6d4cce6e9219911`.
Studio's separate NumPy implementation uses its existing decoder directly;
it has no runtime dependency on the Prince repository.

The existing text Viterbi converters search character/attribute candidates
and use perceptual Lab scoring. Comparing those against this bitmap solver
is a comparison of different representable images as well as different metrics.
No extra solver selector or beam-search implementation is introduced here.

Input adjustment, resizing, Old/New model selection, and dithering are supported.
Ordered dithering adjusts the RGB target; diffusion distributes residual error
to future rows using the selected kernel, normalized after dropping same-row
terms because each row is solved jointly. Thus dithering intentionally changes
the target being optimized. Preview pixels are decoded directly from the final
bitmap, with no RGB444 reduction. The GUI applies its existing display-aspect
correction. GIF saving retains the existing palette-limited GIF behavior.

Conversion runs in a background worker with progress and Stop encode. Cancel,
superseded conversions, mode switches, and changed settings cannot publish a
stale result. COM/ASM/DSK export requires the current completed conversion.
The new mode's disk auto-runs TEST.COM; the program waits for a key and restores
DOS text mode. Exit and rerun still need user validation in native MartyPC.

The 160x200 algorithm and existing export remain unchanged. A description now
states that it uses nearest RGB matching to a selected 16-color composite
palette and renders an NTSC-simulated preview. No preview toggle was added.

## Checks completed

### Optional diffusion during search

**Composite error diffusion** is a selector shown only for Multicolor Composite:
**After each line** (default, original algorithm) or **During line search**
(experimental). It applies only to Error diffusion with a real method selected
and positive strength. None/Ordered retain their existing behavior.

Each surviving 11-bit state carries pending horizontal RGB error (including
two-pixel recipients for kernels that use them). Each predecessor scores the
newly determined NTSC pixel against its own clipped, rounded, error-adjusted
target, then propagates its residual using the selected kernel and strength.
State merges retain the lower accumulated-cost path and that path's residuals.
No blocks, top-ten list, or backwards refinement are used. This is approximate:
discarded paths can have different residuals despite identical bit histories.

The final selected row is replayed to recover its actual scoring residuals for
future-row diffusion. Kernel weights use their original divisors, so Floyd–
Steinberg uses 7/16 horizontally and 3/16, 5/16, 1/16 on the following row.
Atkinson retains its original divisor of 8. Strength applies once to each
distributed residual. Contributions outside the image are discarded.

Search direction is always left to right. Serpentine mirrors future-row taps
on alternating rows; it does not reverse the candidate search. Selecting
After each line restores the existing exhaustive search and normalized
vertical-only diffusion. Changing the selector requires reconversion before export.
Horizontal Striped has no horizontal taps, so it gains no horizontal diffusion
from this option; use Floyd–Steinberg for the initial comparison.

Regression tests include an independent scalar state-merging implementation,
disabled/None/Ordered/zero-strength equivalence, an effective nonzero-diffusion
case, direct preview decoding, and the GUI Diffusion-method-None regression
with the new checkbox enabled. GUI and Marty export checks can be run with
`--during-search` on both multicolor validation scripts. Visual acceptance of
the experimental result remains a user decision.

Completed for this extension: seven focused tests pass, and the remaining
31 regression tests plus 59 subtests pass (38 tests total, run across focused
and regression invocations). Old/New CGA GUI conversions with the option on
pass preview decoding, COM/ASM/DSK round trips, cancellation, and stale-setting
guards. Both COMs captured 48 Marty core frames; both disks captured 372.
The final ten frames per case match every expected bitmap sample. Reports are
in `external/research/multicolor-search-gui`. No native composite visual approval
or package rebuild is claimed.

### Baseline checks

- All four new solver tests pass: signal-window equivalence including borders
  for both models; independent brute-force optimum on eight-bit rows;
  preview equality to direct decoding across dither families; cancellation.
- A random 32-pixel target produces exactly the same bitmap bits as Prince's
  exhaustive implementation for both Old and New CGA.
- Six real Tk conversion cases: Old/New CGA × None/Ordered/Error diffusion.
  Exact preview-to-bitmap decoding, COM/ASM/DSK export, NASM byte equality,
  and disk file integrity pass. Sample end-to-end times were about 13–16 seconds
  on this workstation, including export checks, not a general performance claim.
- GUI cancellation, mode-switch cancellation, and stale-model export guard pass.
- Marty core: all six COMs reproduce all 128,000 expected RGBI bitmap samples;
  both no-dither disks cold-boot and reproduce the same signal pixels.
  Each COM captured 48 frames; each disk captured 372. Final ten frame hashes
  per case match the expected bitmap. Initial setup frames are not acceptance frames.
- Core configuration: IBM 5160, GLaBIOS 0.2.6 XT, CPU wait states and refresh
  enabled. Static programs retain BIOS PIT1 divisor 18. The validator's explicit
  `--static-mode6` path does not relax the existing acquired-kernel divisor-19
  checks. RGBI bitmap verification is not frontend composite-color verification.

Reproduce:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe tools/smoke_multicolor_gui.py
tools/validate_imagelock.cmd external/research/multicolor-gui/old-none.com 0 4000000 external/research/multicolor-core/old-none 10C --static-mode6
.venv/Scripts/python.exe tools/validate_multicolor_exports.py
```

Generated previews, exports, and reports are in `external/research/multicolor-gui`.
Native MartyPC composite visual comparison and user acceptance remain pending.
No standalone package rebuild or release publication is part of this change.

## User validation

1. Launch `run_cga_v167.cmd` and choose **640x200 Multicolor Composite**.
2. Start with **None** dithering and the desired Old/New CGA model. Convert a
   familiar image and review the result, progress, and responsiveness.
3. Compare against **160x200 (16 Colors) Composite** using the same source/model.
4. Export and boot the new DSK in MartyPC with composite output enabled. Match
   the card model/settings where supported; compare appearance, then press a
   key to return to DOS and type `TEST` to rerun.
5. Confirm this checklist item or report differences before we move on.
