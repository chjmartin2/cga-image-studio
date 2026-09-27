# v0.3.0-alpha.2 — working eight-write exports

Eight-write conversion and COM, ASM and bootable DSK exports are enabled with
corrected raster timing. The user confirmed the native MartyPC visualization:
“The visualization in Marty was perfect.”

Download **CGAImageStudio.exe**, close older copies, and launch it. No Python or
NASM installation is needed. Select **320x200 (4 Colors) Mode Switch**, choose
**8 writes**, load an image, convert and export. The historical window title is
still **CGA Converter v167**. **IMGLCK.DSK** is the ready-to-boot Picard demo.

The repair aligns preview and exports with measured CGA palette boundaries and
uses paired interrupt timing to account for CPU wait states and refresh DMA.
Seven writes occur across the visible row; the eighth sets the next row's
leading palette during horizontal blanking.

Validation:

- 26 regression tests and 59 subtests pass, including byte-exact NASM rebuilds.
- 44 core acceptance cases / 18,736 exact frames, including startup variations,
  full DOS boots and repeated launches with waits and active raster refresh.
- All 12 GUI option combinations pass conversion, COM/ASM/DSK generation,
  NASM round trips and emulator pixel comparison (1,383 exact frames).
- Final demo disk boots across all four PIT phases (1,803 exact frames).
- Standalone Windows runtime smoke test passes with bundled export assets.

This remains a prerelease pending the complete studio feature audit. Physical
IBM CGA hardware, including the brief refresh quiet windows used before each
raster, remains unqualified. The Windows executable is unsigned.

See [validation evidence](research/eight_write_validation.md) and
[project status](PROJECT_STATUS.md). Older withdrawn timing results remain
archived and are not counted toward this release.
