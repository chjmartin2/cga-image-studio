# Project Status

Restart checkpoint: 2026-09-14. Active application: `cga_v167.py`.

**Open runtime discrepancy:** the user reports a garbled native MartyPC image
from a converter export despite a correct preview. The exact exported disk and
COM pass independent frame comparisons and manual DOS-boot tests; the native
failure is not yet reproduced or explained. See the
[investigation](research/garbled_export_investigation.md). A fresh-disk launcher
is prepared, with user confirmation pending. Do not treat the earlier passing
matrix as proof that this reported failure is resolved.

## Current behavior

The main application is `cga_v167.py`, with the acquired raster backend in
`cga_mode4_lock.py` and its packaged template in `assets/mode4_lock`. Run it with
`run_cga_v167.cmd` or `.\.venv\Scripts\python.exe cga_v167.py`. Historical
`cga_v165.py` and `cga_v166.py` are preserved alongside it.

The production `320x200 (4 Colors) Mode Switch` controls offer **1 or 8 writes
per scanline**. The GUI's 8-write profile uses the new `startlock-mode4` backend.
Seven writes create active-picture boundaries at
`x = 33, 73, 113, 169, 201, 241, 281`. The eighth write occurs during horizontal
blanking and supplies the following line's leading `[0, 33)` zone independently
of the current line's trailing zone. The layout is fixed. The black-border
option constrains both edge palettes.

Optional `Dither aware optimization (Lab, slower)` applies to both production
profiles. The latest committed work, `6e8c191` (2026-06-21), enabled it for the
one-write profile after adding it to the eight-write profile.

COM, NASM ASM, preview GIF, and bootable DOS DSK exports are available. DSK
export requires `files/dos_boot_template.dsk`.

## Work at this checkpoint

The [Picard image test](IMAGELOCK.md) now goes through the core quantizer and
exporter. It extends the working start-line marker to a 200-row, eight-write
raster with refresh still enabled. The preview and binary share measured
geometry; palette immediates and VRAM are the only per-image binary patches.
First-row palette ownership is correct both after acquisition and across frame
wrap. COM, annotated NASM and bootable DSK use the same backend. Existing
programmatic callers with no `timing_backend` retain legacy behavior.

All 23 regression tests pass, including byte-exact NASM rebuilds for the new
backend. The actual GUI export method also passed headless COM/ASM/DSK checks.
The standalone demo includes Picard and an independent registration pattern:
double-click `Picard CGA Demo.lnk`, or use `files/IMGLCK.DSK` directly.

The restart work completed the annotated ASM exporter repairs in
`cga_v167.py`. Exported source now avoids duplicate labels, preserves short
conditional jumps explicitly, handles truncated instructions and instruction
boundaries safely, and uses the conversion plan to annotate the eight-write
FREE16 profile correctly. Assembly instructions respect the selected output
filename, and eight-write exports use `n8` in the default filename.

Focused regression tests cover these changes, including NASM byte-for-byte
COM rebuilds. The working tree still contains numerous untracked calibration
programs, disk images, screenshots, ASM files, and diagnostic scripts. Keep
existing experimental artifacts until their provenance and usefulness have
been reviewed.

The source still includes older two-, three-, and thirteen-write experiments.
They are useful references but are not the current GUI production choices.
Some inline comments and diagnostic scripts predate the eight-write profile;
check their assumptions before treating their output as current validation.

## Validation

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m py_compile cga_v167.py
.\.venv\Scripts\python.exe -B -c "import cga_v167; print(cga_v167.__version__)"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The restart audit passed an in-memory syntax/import check and static mode-04h
VRAM packing, COM construction, and bootable DSK construction smoke checks.
GUI initialization and the export regression suite passed, including NASM
byte-for-byte rebuild cases. An independent check rebuilt all 196 existing
repository COM files exactly. A production FREE16 conversion also passed the
GUI ASM-save workflow and NASM rebuild, including the selected filename,
8-write/22-preroll annotations, and preview-to-VRAM index consistency.
The local environment used Python 3.12.0, NumPy 2.4.6, Pillow 12.2.0, and Tk 8.6.

NASM is optional for application use but required for the byte-rebuild
integration tests. The suite accepts a `NASM` environment variable, searches
`PATH`, and detects a local Windows installation.

The earlier restart checks above did not validate raster timing. The new
unchanged-Marty-core harness now independently compares complete RGBI frames
against expected images. The final schedule passed all 32 tested startup
combinations (four PIT phases and eight entry delays), including all four VRAM
indices and the first completed visible frame. Exported Picard passed 1,225
completed frames across all four PIT phases with zero differing dots; REGLOCK
passed another 269. See [the full validation report](research/imagelock_validation.md)
for timing, input hashes, complete counts and DOS-boot evidence. Physical hardware
has not been tested with this full mode-4 image kernel.

## Next steps

The timing feasibility gate takes priority over image optimization, increasing
write density and module extraction. See [CGA timing research](CGA_TIMING_RESEARCH.md)
for the primary-source analysis, newly measured results from a published physical
bus capture, current-code gaps, and explicit acceptance criteria.

1. Repeat the Picard and registration image tests on documented physical IBM CGA
   hardware, including cold boots and sustained frame captures. Verify every
   palette seam and the row-zero leading palette against the expected image.
2. Extend startup coverage beyond the tested emulator configurations, including
   supported CPU/BIOS/card variants. The fixed schedule currently targets the
   normal-speed IBM 5160/8088 configuration, with refresh and wait states enabled.
3. Once hardware evidence passes, improve image quantization and consider denser
   write schedules. The current image is still two-bit mode-4 VRAM with a
   constrained four-color palette per zone, not unrestricted 16-color pixels.

Published hardware data establishes that beam-synchronized execution is possible;
it does not certify this application's current palette loop. The hardware test
recorded in the PDF under `Extras` did not reproduce the intended picture.

The Area 5150 follow-up recovered all 29 released executable modules. Its actual
Lake initializer performs automatic acquisition, and all 20,445 observed
initializer fetches match the published IBM 5150 capture with released defaults.
Both measured main-ISR intervals are 79,648 CPU cycles. This supersedes using the
2017 experimental source as a description of the released effect; all power-on
phases and the application's visible palette transitions still need testing.

The first independent [mode-4 marker demo](STARTLCK.md) is now built:
`files/STARTLCK.COM`, auto-running 360 KiB `files/STARTLCK.DSK`, and
`run_startlock.cmd`. The unchanged MartyPC core produced the same visible
marker onset at image pixel (9,8) for all four configured PIT phases, with
79,648-cycle marker periods. A BIOS/DOS disk boot completed all 3,600 display
frames and returned to DOS. That marker was the first diagnostic step. The new
image test now covers varied entry delays and all eight writes in the emulator;
physical hardware validation remains outstanding.

## Historical references

- [CGA lockstep milestone](cga-lockstep-milestone.md) records the progression
  from two writes to thirteen-write dense timing and its drain-tail schedule.
- [Mode Switch diagnostic](modeswitch-diagnostic.md) describes the older
  two-write GUI configuration; its instructions do not match the current UI.
- [Refactor plan](REFACTOR_PLAN.md) preserves the original modularization plan.
  Its `v165` compile command predates the current `v167` entry point.
