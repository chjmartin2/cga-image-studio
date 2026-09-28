# CGA Image Studio 0.167a - alpha snapshot

September 28, 2026. This release succeeds v0.3.0-alpha.3 and rebaselines public
numbering around the v167 development line. We are working toward **1.0 beta**.

Download **CGAImageStudio.exe** and run it on Windows x64. No Python or NASM
installation is required. This is an unsigned standalone application.

## Changes since alpha.3

- Rebuilt Windows-themed GUI: RGB Graphics, Composite, and RGB Text groups;
  contextual settings, collapsed advanced controls, one Export menu, hover
  and focus help, and larger preview panels.
- Raster CRT branding, application icon, consistent public version and Windows
  executable metadata. Full-width progress banner with a large STOP button,
  gray when unavailable and red when cancellation is available.
- Fixed text-encoder startup prematurely clearing banner progress.
- Automatic whole-pixel output zoom avoids uneven pixel/scanline scaling.
  CRT proportions are approximate in this view; small panels scroll. Exports
  retain their original resolution.
- Added 640x200 Multicolor Composite bitmap conversion with exhaustive NTSC
  signal search, Old/New CGA models, and After each line / During line search
  error diffusion. During-search diffusion is an approximate option; it does
  not claim an exhaustive optimum over error-history states.
- Error diffusion with method None now disables diffusion.
- Fixed static 512-color text conversion to use its two supported repeating-row
  patterns. Unsupported patterns are rejected instead of silently replaced.
- Corrected static text sync width so composite color works in Marty.
- Mini-Frames exports have a selectable 5-300 second display duration.
- Removed the unimplemented 640x200 Mode Switch GUI entry; additional future
  modes are documented in the deferred-mode backlog.
- GIF/ASM/COM/DSK exports reject incomplete or stale conversions after relevant
  image/settings changes before opening a save dialog. Preview zoom and
  export-only duration/target-card choices do not require reconversion.
- Refreshed Raiders full-screen text-composite demo; user confirmed it in Marty.
- Added SCOPE8 to investigate aligned eight-write palette boundaries on an IBM
  5160 with New CGA and RGB output. Timing instructions are unchanged; this
  diagnostic does not fix or certify the physical-hardware issue.

## Downloads

- `CGAImageStudio.exe`: standalone Windows application.
- `RAIDERS.DSK` and `RAIDERS_preview.png`: bootable composite demo and reference.
- `SCOPE8-hardware-test.zip`: bootable diagnostic, DOS program, ASM, preview and
  scope instructions. Hardware results are pending.
- `windows-smoke.json`, `validation.txt`, and `SHA256SUMS.txt`: checks and hashes.

Enable composite rendering for Raiders. SCOPE8 uses RGB. A DOS computer or
emulator is required for exported programs; MartyPC is not bundled.

## Validation and remaining work

Current source regressions and a smoke check of the packaged executable are
included with this release. GUI and selected native Marty examples were reviewed
with the user. SCOPE8 matched 293 complete Marty-core RGBI frames. Existing
aligned/staggered timing templates are unchanged from their validated baseline.

This is a checkpoint alpha, not completed 100% validation. The mode/output
acceptance matrix, centered-mode display/exit behavior, additional interaction
and failure-path testing, Windows DPI/accessibility checks, and clean-machine
qualification remain open. Physical New CGA edge artifacts are under
investigation; emulator success is not hardware certification. See
[the checklist](INITIAL_RELEASE_CHECKLIST.md) and [Windows instructions](WINDOWS_BUILD.md).
