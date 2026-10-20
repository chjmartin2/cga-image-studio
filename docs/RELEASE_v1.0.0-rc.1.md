# CGA Image Studio 1.0.0-rc.1

October 20, 2026. The first 1.0 release candidate succeeds 0.167a.
This is a GitHub prerelease; physical CGA hardware qualification and the
remaining interactive acceptance checks are still open.

## Downloads

- **CGAImageStudio.exe**: standalone Windows x64 application. Download and
  double-click; Python and NASM are not required. Includes Numba CPU acceleration
  for composite search. The executable is unsigned.
- **cga-studio-demo-disk.zip**: reviewed 24-picture bootable 720 KiB FreeDOS disk,
  menu source, instructions, and corresponding FreeDOS source/license packages.
- **cga-studio-demo-exports.zip**: all 24 PNG, lossless WebP and DOS COM exports,
  an HTML preview gallery, and the disk archive above.
- **windows-smoke.json**, **validation.txt**, **SHA256SUMS.txt**: packaged-runtime
  checks, validation details and download hashes.

The executable uses CPU conversion and needs no NVIDIA GPU or CUDA toolkit.
Source installations retain optional CUDA acceleration for composite search
and standard RGB text. MartyPC and ROMs are not included.

## Changes since 0.167a

- Standard 40/80-column RGB text conversion with character heights 2-8,
  exhaustive glyph/color matching, DCT and other matching methods,
  preprocessing, input preview, optional CGA reduction and dithering.
  Optimize compares settings; the live DCT Tweaker exposes matching weights.
- The promoted 640x200 1024-color composite encoder supports CPU acceleration,
  optional CUDA, direct matching, ordered dithering and error diffusion.
  CPU fallback preserves conversion when CUDA is absent or unavailable.
- Mode Switch Repeat searches cycles of 2-6 distinct foreground palettes,
  with fixed, adjustable or nonrepeating adjacent backgrounds. Preview,
  layout map and exports share the same encoded schedule.
- Single-palette-per-scanline conversion adds background selection,
  optional unique adjacent foregrounds, dither-aware search and independent
  layout-map zoom. Single-scanline and Repeat exports support a black border.
- Corrected bounded error diffusion, centered text-composite display/exit
  behavior, preview/export consistency and stale-output handling.
- Lossless PNG/WebP preview exports and optional remembered MartyPC linking,
  with isolated run disks/configurations and RGB/composite selection.

## Reviewed demonstration

The approved 24-picture demo published October 20 is included unchanged,
with its recorded encoder settings and build evidence. It is a separate
reviewed demonstration, not a regeneration after the RC version bump.
All 24 actual exported programs completed the native MartyPC playback check.

Extract the disk ZIP and boot `CGADEMO.DSK`. Select 1-24 for a picture, N/P
for menu pages, R for the RGB cycle, C for the composite cycle, or Q for DOS.
Both cycles play once and return to the menu. Images 1-14 use RGB; 15-24 use
composite. Leah (#21) uses New CGA; other composite selections use Old CGA.
The emulator/display selection must be changed accordingly.

Mode Switch demonstrations require stock 4.77 MHz 8088/CGA timing, turbo off,
wait states and DRAM refresh on, and PIT phase 0. See the
[demo guide](https://github.com/chjmartin2/cga-image-studio/blob/v1.0.0-rc.1/docs/DEMO_DISK.md).

## Validation and remaining work

The release includes regression results, an expanded smoke check of the actual
packaged executable and SHA-256 hashes. The smoke check constructs the GUI,
checks bundled assets, and exercises static, aligned/staggered, Repeat,
black-border and standard-text exports plus the compiled CPU search.
See the attached `validation.txt` and `windows-smoke.json` for exact results.

The final source suite passed **522 tests and 578 subtests**. The packaged
executable passed both its regular smoke check and a second run from an
isolated directory with only Windows system directories on PATH.

The demo archives were checked for CRC integrity, all 24 disk COM payloads,
PNG/WebP pixel parity, and matching playback evidence. Existing native
MartyPC playback completed all 24 programs in 361.61 seconds.

The complete interactive acceptance matrix, clean-machine Windows/DPI checks
and physical CGA hardware qualification remain open. Experimental raster
timing and emulator success do not establish compatibility with every CGA
card. See the
[acceptance checklist](https://github.com/chjmartin2/cga-image-studio/blob/v1.0.0-rc.1/docs/INITIAL_RELEASE_CHECKLIST.md).

The optional single-scanline/Repeat black-border path has known edge-pixel
discrepancies with MartyPC's default renderer and some DOS entry timings.
Turn **Keep Border Black** off to use the original display path. See
[border timing limits](https://github.com/chjmartin2/cga-image-studio/blob/v1.0.0-rc.1/docs/N1_BORDER.md).
