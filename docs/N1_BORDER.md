# Keep Border Black for single-line and Repeat modes

## Implemented behavior

The old N=1 exporter did not receive the checkbox value. It loaded the next
image palette in horizontal blanking and left the final background active
through vertical overscan. The displayed border consequently inherited image
background colors regardless of the checkbox.

The checkbox now selects a separate timed N=1 export routine for both
**320x200 (4 Colors) Mode Switch** with one palette per row and
**320x200 Mode Switch Repeat**. The routine writes the selected row palette
near the left edge and clears the background nibble near the right edge to
paint horizontal and vertical overscan black. Exact edge placement still has
the limitations recorded below. Foreground selection bits for
the next row are prepared with the black write, and that row's mode register is
set before its image begins. Thus the border setting does not constrain image
background or palette search. Bitmap bytes and selected image palettes are
preserved in the exported program.

COM, ASM, boot-disk and Open in MartyPC exports use the checkbox. For these
single-line paths it is now an export setting: changing it does not require a
new conversion. Unchecked uses the original polled N=1 builder. The eight-write
mode retains its existing conversion constraint and template; rebuilding that
template still matches its previously qualified SHA256.

## Observed limits: exact-edge timing is not fully solved

This is an **experimental timed border path**, not a claim that every border
pixel is black on every emulator or physical CGA card.

- In controlled direct-COM-load tests of the unchanged MartyPC core's
  **pixel-clock renderer**, PIT phases 0, 1 and
  2 produced exact 320x200 RGBI images and zero nonblack overscan pixels for
  standard, tweaked and mixed palettes. The nine runs covered 639 completed
  frames, including the first completed frame of each run.
- With the **default character-clock renderer**, phase 0 retained a one-pixel
  edge discrepancy. In each diagnostic image, 37 background-colored image
  pixels at the left edge were black, and 187 right-border pixels retained an
  image background. Foreground colors at the left edge were preserved by the
  preloaded foreground bits. This is a remaining visible defect, not an exact
  black-border pass. Switching the checkbox off restores the old display path.
- Pixel-clock phase 3 retained discrepancies in the first three image columns
  and two right-border columns in these tests. It did not pass exact comparison.
  Studio currently requests PIT phase 0 when launching MartyPC, but that alone
  does not enable pixel-clock rendering or establish arbitrary-entry robustness.
- An actual DOS boot followed by two consecutive launches confirmed timer
  expiry, return to text mode and successful reacquisition. It also exposed an
  entry-dependent defect even with pixel-clock rendering and PIT phase 0:
  both captured frames of the first launch had 148 mismatching dots (74 image
  pixels in the first two columns); both captures of the second launch matched
  exactly. Thus phase 0 is not sufficient to guarantee exact image edges.
  Evidence is in `artifacts/border-validation/acceptance/dos-reentry/`.
- Physical IBM CGA hardware, other emulators, arbitrary launch timing and CPU
  speeds have not been qualified. The observed renderer difference is evidence
  of different edge placement; it is not proof that all residual errors belong
  to the emulator. Further acquisition/edge qualification remains necessary.

The visible timing window measured in successful pixel-clock cases is dots
192 through 831, with black restored at dot 832. The image has one selected
four-color palette per row; the border write is separate from that palette.
No extra image palette switches are introduced.

## Implementation and evidence

The template shares the existing Lake/paired PREP-MAIN acquisition in
`tools/imagelock.asm`, selected by `N1_BORDER`. Its row kernel is in
`tools/n1_border_kernel.inc`. The row period is 304 CPU clocks and the frame
period is 79,648 clocks with wait states and raster DRAM refresh enabled.
PIT1 is restored to divisor 19 before the raster. As with the existing acquired
backend, brief refresh quiet windows occur during acquisition/frame preparation.

`cga_n1_border.py` patches declared immediate operands and the framebuffer in
`assets/mode4_lock/n1_border/template.bin`; no assembler is required at export.
The descriptor also identifies frame-count and keyboard settings. Cleanup uses
the shared restoration of timer, refresh, interrupt vectors, PIC mask and text
mode. A new key make code exits when enabled; the initial keyboard state is
sampled after the first raster so the launch key is not mistaken for a new key.

Rebuild the template explicitly with:

```powershell
.venv\Scripts\python.exe tools/build_n1_border.py --install
```

Rebuilding is not validation. Use `tools/validate_n1_border.py` with the locally
built `validate_imagelock.exe`. The harness's optional `--no-debug-video` removes
diagnostic I/O-marker colors from border captures; `--pixel-clock` selects the
existing precise renderer. Neither flag modifies the MartyPC core source.
The validation script checks all tested combinations and records failures in
`artifacts/border-validation/acceptance/report.json`. It checks every completed
image frame and the last complete field's overscan, using all four pixel indices
at both edges, all sixteen backgrounds, and changing intensity/palette bits.
Its default exit status is nonzero if any case fails; use
`--record-known-failures` only to collect measurements without requiring full
qualification. These direct-load checks do not replace DOS boot/reentry checks.

The register meaning and distinction between display-enable and visible image
edges are described in the primary implementation author's
[CGA hardware notes](https://book.martypc.net/display-graphics/cga). In particular,
background and overscan share the color register; simply clearing it without
timing the restore can damage the image edge.

Regression coverage: `tests/test_n1_border.py` and
`tests/test_mode_switch_repeat_export.py` verify operands, unchanged framebuffer
and palette tables, runtime options, checkbox routing without reconversion,
ASM round trips, boot-disk bytes and MartyPC launch routing.
