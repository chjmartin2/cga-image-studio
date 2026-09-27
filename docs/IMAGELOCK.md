# Picard CGA image test

**Validation correction (2026-09-14):** the original image kernel was calibrated
with CPU wait states inadvertently disabled in the harness, which also bypassed
DMA refresh delays. Its old passing frame counts do not validate the native
MartyPC configuration. Enabling the missing option reproduces the user's garbled
converter export. See the [investigation](research/garbled_export_investigation.md).
The harness and image schedule are being corrected. Exporting this withdrawn
profile is disabled in new app sessions until a replacement passes the corrected
validator. The disk and launch instructions below currently reproduce the old
experiment; they are not a repaired release.

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

The withdrawn preview profile assumed boundaries at x = 33, 73, 113, 169, 201,
241 and 281. Those positions do not describe native execution with waits enabled.
The eighth write occurs in horizontal blanking and supplies the next row's
leading palette. The final row's eighth write and a separate startup operand must
both carry row zero's leading palette. This ownership also needs verification
against the first completed frame after every acquisition.

The renderer reuses the released Lake acquisition bytes, restores standard
mode-4 geometry, then acquires a frame entry for the graphics raster. It keeps
DRAM refresh running at PIT divisor 19. The timed body has no bitmap loads,
palette-table loads or conditional branches: export patches palette immediates
in a fixed, unrolled instruction template. The target is 304 CPU cycles for each
of the 200 rows, with 79,648 CPU cycles between frames. The withdrawn kernel
actually takes 331-338 cycles per row with CPU waits enabled. A memory
and timing explanation is in [the kernel notes](research/imagelock_kernel.md).

## Validation and limits

The corrected harness uses the unchanged local MartyPC core with an IBM 5160,
normal-speed 8088, CGA, and explicitly asserted CPU waits and refresh scheduling.
Replacement acceptance requires all four configured PIT phases and eight entry
delay variants. Full RGBI comparison must include the first completed visible
frame, all four bitmap indices and the last-row/first-row palette wrap, followed
by an actual DOS boot. See [the corrected validation report](research/imagelock_waitstates_validation.md)
for the reproduced failure and the replacement's current status.

These are emulator measurements. This application's full mode-4 image routine
still needs repeated cold boots and sustained display on documented physical
IBM CGA hardware before claiming hardware reliability. Published Area 5150
hardware evidence validates the original acquisition, not this graphics handoff.

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
