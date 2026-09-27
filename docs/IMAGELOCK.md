# Picard CGA image test

**Repaired release (2026-09-27):** eight-write conversion and COM/ASM/DSK
exports are enabled. The corrected timing passes the wait-state-enabled core
acceptance suite; the user confirmed the native MartyPC visualization was perfect.
See the [current validation report](research/eight_write_validation.md).

Double-click **Picard CGA Demo.lnk** in the project folder. It launches the local
MartyPC build with its configuration and a fresh copy of the correct boot disk.
DOS starts Picard automatically. The launcher checks that both test programs are
actually present on drive A before opening the emulator.

The intended picture is a stationary Picard portrait. This is an image rendered with
the core program's eight-write mode-4 converter. Each frame repeats 1,600 writes
to the CGA color-select register while the bitmap stays in VRAM.

Press Escape to return to DOS; the display also ends after about 60 seconds.
Type `IMGLCK` to repeat Picard, or `REGLOCK` for the palette registration pattern.
The registration pattern deliberately changes palettes by row and exercises all
four bitmap indices, so incorrect palette boundaries cannot hide in a photograph.

## Files

- `files/IMGLCK.COM`: Picard executable, 57,088 bytes.
- `files/IMGLCK.DSK`: bootable 360 KiB DOS disk, automatically runs Picard.
- `files/IMGLCK_preview.png`: expected 320x200 output from the core converter.
- `files/IMGLCK_source.png`: resized source image before conversion.
- `files/IMGLCK.asm`: byte-exact NASM export with the 1,600 palette writes exposed.
- `files/REGLOCK.COM` and `files/REGLOCK_preview.png`: registration diagnostic.
- `files/IMGLCK.json`: input, output, disk-content and SHA256 manifest.

From PowerShell in the project folder, `.\run_imagelock.cmd` is equivalent to
the shortcut.
For a different emulator PIT phase, run `.\run_imagelock.cmd 3`; phases 0 through
3 are accepted. The script prepares a separate disk/configuration for each phase.

## Core program integration

In CGA Image Studio choose **320x200 (4 Colors) Mode Switch**, select **8 writes**,
load an image and convert it. The eight-write GUI path now uses `startlock-mode4`.
The preview, quantizer, COM, ASM and DSK exports share the same measured palette
geometry. Existing research scripts can still explicitly use the legacy backend.
Restart an already-open copy of the app to load the changed code.

The image is ordinary CGA mode 4: 320x200, two bits per pixel, with the normal
16 KiB even/odd VRAM banks. Beam-timed changes select different four-color
palettes in different parts of each row. This can use the full 16-color RGBI
set across the screen; it does not provide an independent choice of 16 colors
at every pixel. This Picard conversion uses 14 of those colors; REGLOCK uses all 16.

The measured region boundaries are x = 0, 25, 65, 113, 161, 209, 249, 289,
and 320. Seven writes divide the visible row. The eighth occurs in horizontal
blanking and supplies the next row's leading palette. The final row's eighth
write and a startup operand both carry row zero's leading palette.

The renderer retains the released Lake acquisition bytes and uses a new paired
PREP/MAIN graphics handoff. Each row executes 33 NOPs and eight immediate
MOV/OUT pairs in 304 CPU clocks; frame spacing is 79,648 CPU clocks. A brief
PIT1 quiet window drains refresh DMA before each raster; refresh is restored to
mode 2, divisor 19 before visible writes. Refresh therefore runs during the
raster, but is not uninterrupted during acquisition and frame preparation.

## Validation and limits

The unchanged MartyPC core uses IBM 5160, normal-speed 8088, CGA, effective
CPU waits and active raster refresh. The final acceptance suite passes 44 cases
and 18,736 exact frames: all four PIT phases, eight entry-padding variants,
all four bitmap indices, photo output, four full DOS boots and repeated launches.
First and last frames, all 200 rows and row-zero palette ownership are checked.
Twelve GUI option combinations also pass conversion and COM/ASM/DSK generation.
The user confirmed native MartyPC visually on 2026-09-27.

Physical IBM CGA hardware remains unqualified, including the brief refresh
quiet windows. Published acquisition research does not certify this new handoff.
Older reports remain historical and do not contribute to the current counts.

## Rebuild

```powershell
.\.venv\Scripts\python.exe tools/build_imagelock.py
```

This uses the application's quantizer and the packaged template; no NASM is
required. The default image is `test_images/picard_input_copy.bmp`.
An optional image path selects a different source.

To reassemble the timing template as well:

```powershell
.\.venv\Scripts\python.exe tools/build_imagelock.py --rebuild-template
```

The rebuild verifies the released acquisition bytes and requires the binary to
match the calibrated template hash. If timing instructions change, measure the
new kernel before replacing the profile and template assets.
