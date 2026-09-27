# Acquired mode-4 image kernel: calibration correction

**The original 40-NOP raster calibration is withdrawn.** Its harness had CPU
wait states disabled and skipped refresh DMA stalls. The native frontend
explicitly enables that CPU option; enabling it in the harness reproduced the
user's garbled image. The [source audit](waitstates_disabled_archive/README.md)
records the exact gate and constructor defaults.

Use [IMAGELOCK](../IMAGELOCK.md) and the
[corrected wait-state-enabled measurements](imagelock_waitstates_validation.md)
for the replacement kernel, geometry, and supported runtime settings. The
[original kernel notes](waitstates_disabled_archive/imagelock_kernel.md) are
preserved as historical evidence, not implementation guidance for the corrected
schedule.

## Architecture retained independently of timing calibration

The program uses ordinary CGA mode 04h: a 320 x 200 bitmap with two stored bits
per pixel. Seven timed palette writes divide the active scanline into regions;
a further blanking write supplies the following row's leading palette. This
is a constrained four-color palette per region, not independent sixteen-color
selection at every pixel.

The released Lake acquisition bytes remain a reference for synchronization.
A separate mode-4 handoff and feedback stage must acquire the target geometry.
The PIT channel-1 divisor written by the program is only one part of the timing
model: actual CPU wait states and refresh DMA bus interference must operate
when measuring the replacement raster.

The converter and exporter must share the replacement kernel's measured
boundaries and palette ownership. Row 199's blanking write and the first-frame
bridge must both supply row zero's leading palette. Export may patch palette
immediates and framebuffer data only; changing timing instructions requires
new measurements. The versioned descriptor and template hash identify the
specific binary being tested.

## Withdrawn numerical claims

The old schedule used 40 NOPs per row and claimed boundaries
`0,33,73,113,169,201,241,281,320`. Its local diagnostic reported 154,421 adjacent-row
intervals of 304 CPU clocks and 754 frame intervals of 79,648 clocks; a separate
32-startup image matrix reported 2,162 matching frames. All are **invalid for
native wait-state-enabled timing validation**. Their raw results and the
original explanatory tables remain in the archive; do not reuse those values
as replacement-kernel constants.

Physical CGA testing remains separate from corrected emulator validation.
