# CGA Image Studio v0.3.0-alpha.1 — development checkpoint

This prerelease preserves the v167 converter and eight-write timing investigation
before the remaining timing repair and full feature-validation pass.

## Windows download

Download and run **CGAImageStudio.exe** on Windows x64. No Python installation
is required. The app title retains the historical version `CGA Converter v167`.
The executable is unsigned. `SHA256SUMS.txt` provides its checksum, and
`windows-smoke.json` records the packaged-runtime checks.

## Included

- Classic CGA, composite and text-mode conversion, image adjustments, dithering,
  palette optimization, GIF saving, and supported COM/ASM/DSK exporters.
- Dither-aware palette selection for one- and eight-write Mode Switch previews.
- Shared mode-4 geometry and template-based export implementation.
- Byte-exact NASM export regressions and preserved timing research and diagnostics.
- Repeatable PyInstaller build and a VS Code workspace file.

## Known limitation: eight-write exports remain disabled

The previous timing validator omitted CPU wait states, also bypassing effective
refresh DMA delays. Corrected settings reproduce the garbled image. The old
profile is withdrawn; the application blocks its COM, ASM, and DSK exports.
Historical experiment binaries and screenshots are research evidence, not repaired
exports. A retuned assembly source is preserved but is not a validated replacement
for the packaged template. Physical-hardware qualification remains outstanding.

## Validation and next milestone

All 24 software regression tests pass, including NASM round trips. Serialization
tests explicitly enable their test fixture without changing the production guard.
The standalone smoke check verifies GUI construction, bundled dependencies and
assets, static exports, eight-write preview, and guard behavior. This is not a
complete feature acceptance test or a raster-timing certification.

Next: finish eight-write export timing, freeze the feature set, then validate every
feature. See `docs/PROJECT_STATUS.md` and `docs/WINDOWS_BUILD.md` in the source.
