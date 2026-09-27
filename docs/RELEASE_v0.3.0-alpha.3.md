# v0.3.0-alpha.3 — 8 staggered

The **Mode Switch writes per line** selection now offers **1**, **8**, and
**8 staggered** in **320x200 (4 Colors) Mode Switch**.

Staggered breaks up vertically aligned palette boundaries with a fixed pattern
that alternates between adjacent rows. The pattern stays identical every frame
and for every image. Region widths differ slightly between the two row layouts.
Conversion, preview, palette diagnostics, COM, ASM and DSK exports share those
measured boundaries. Normal 8 retains its previous timing template.

Download **CGAImageStudio.exe**, close older copies, select **8 staggered**, then
load an image and click **Convert** before exporting. No Python or NASM is needed.
The historical window title remains **CGA Converter v167**. **STAGGER.DSK** is a
bootable Picard example; type **TEST** at DOS to repeat it after it finishes.

Validation: 31 tests / 59 subtests; 44 staggered timing cases / 18,736 exact
frames; all 12 GUI option combinations for each eight-write selection; byte-exact
ASM round trips; packaged Windows runtime checks. The tests use effective CPU
wait states and active raster refresh in the unchanged MartyPC core.

Native visual confirmation of the new staggered profile and physical CGA testing
remain outstanding. This is a prerelease pending the full studio feature audit.
The Windows executable is unsigned.

See [validation details](research/staggered_validation.md) and
[project status](PROJECT_STATUS.md).
