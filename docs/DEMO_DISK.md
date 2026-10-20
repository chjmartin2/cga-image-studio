# Reviewed CGA demo slideshow

The current demo is `artifacts/demo-slideshow/CGADEMO.DSK`: one bootable 720 KiB
FreeDOS disk containing all **24 owner-approved conversions**, grouped by mode.
The earlier 25-image experiment remains under `artifacts/demo-disk`; it is not
used by this slideshow or the default launcher.

Double-click `run_demo_disk.cmd` in the master Source folder. It opens the local
MartyPC installation with a 720K A: drive and an isolated writable disk copy.
The disk boots directly to its 8086-compatible menu. Enter 1-24 for a picture,
N/P to change page, R to **Cycle through RGB images**, C to **Cycle through
Composite Images**, or Q to exit to DOS. Both cycles play once and return to the
menu. Run MENU at the DOS prompt to reopen it.

## Downloads and previews

- `artifacts/demo-slideshow/cga-studio-demo-disk.zip`: boot disk, menu/source,
  instructions, settings/build evidence, FreeDOS source packages and licenses.
- `artifacts/demo-slideshow/cga-studio-demo-exports.zip`: all 24 PNG, lossless
  WebP and COM exports, gallery, previews, and the disk download above.
- `artifacts/demo-slideshow/index.html`: browse every rendered output and its
  settings, with individual PNG/WebP/COM links.
- `artifacts/demo-slideshow/SHA256SUMS.txt`: disk and archive checksums.

RGB selections are 1-14; Composite selections are 15-24. Display selection stays
in the emulator or physical connection. Use Old CGA for composite except Leah
(#21), which retains the approved New CGA encoding. Select New CGA manually for
Leah's intended colors, or view it separately. No image is re-encoded to hide
that display-model difference.

Ordinary slideshow pictures use an approximately ten-second BIOS-clock timeout.
Mode Switch programs retain their approximately 30-second frame counter.
Esc stops the cycle in pictures using
the BIOS keyboard; other keys advance. Mode Switch uses its own keyboard handler
(a key advances). Individual selections retain
normal exported key/timer behavior. Loading/setup adds time.

Mode Switch requires stock 4.77 MHz 8088/CGA timing: turbo off, wait states and
DRAM refresh on, PIT phase 0. Native emulator execution is verified; physical
hardware qualification remains separate.

## Build and validation

`artifacts/demo-slideshow/approved-proposal.json` freezes the reviewed proposal.
Its 24 sources are cached under `sources/` and retain their original SHA-256s.
These private source assets are not included in the download or Git. Settings
estimated from screenshots remain identified as estimates in the proposal.

```powershell
.venv\Scripts\python.exe tools\render_reviewed_demo.py --resume
.venv\Scripts\python.exe tools\validate_demo_slideshow.py
.venv\Scripts\python.exe tools\validate_demo_slideshow.py --real
.venv\Scripts\python.exe tools\package_reviewed_demo.py
```

The rendering script uses the latest Studio Convert and Export COM callbacks
with an actual Tk main loop. It waits for asynchronous encoders without reducing
search quality. Every output records exact settings, source hash, encoder hash,
export hash and duration. The 640x200 text-composite conversions used CUDA on the
RTX 3090. PNG and WebP decoded pixels are verified identical.

The launcher leaves the COM files unchanged. During a cycle only, it installs
a BIOS INT 16h handler for keyboard status/read calls, returning an automatic
key after the timer. It restores the original vector after each child and
never hooks the raster timer IRQ. Native MartyPC tests use the same menu logic
with start/end markers on diagnostic port E9h. All 24 actual exported programs
executed and returned in order, both cycle branches returned to the menu, and
Q returned to DOS. The current run's evidence is in
`artifacts/demo-slideshow/validation-real/report.json`. The production menu omits
diagnostic writes. Packaging checks that tested COMs and menu logic still match.

The FreeDOS boot sector and KERNEL.SYS come from the official FreeDOS 1.4 720K
floppy image. COMMAND.COM comes from that image's FREEDOS/BIN folder. The builder
removes installer utilities and rebuilds the FAT without changing system binary
bytes. Kernel 2043 and FreeCOM 0.86a match the bundled official package binaries;
their corresponding source archives and license notices accompany the download.
The floppy download itself is retained locally in `freedos/` for reproducibility.

Official inputs:
- https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/distributions/1.4/FD14-FloppyEdition.zip
- https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/repositories/1.4/base/kernel/20250409.9/kernel.zip
- https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/repositories/1.4/base/freecom.zip

## Corrected demo settings

John Wick (#12) uses brightness -35, contrast +95, and RGB gains 80/100/100.
All 16,000 output pixels match the intended source-region mapping to CGA red,
black, cyan and light cyan. The earlier estimated screenshot sliders crushed
the red background into black. Diffusion method remains None as requested.

Leah (#21) uses 640x200 Multicolor Composite, New CGA, Lanczos and
Floyd-Steinberg strength 1.0 after each line. The proposal, menu and output
gallery retain mode grouping after the change from Mini-Frames.

## Website handoff

A data-driven Demo tab is published from the designated website checkout:
`D:/RetroComputerist/Website/content/projects/cga-image-studio.json`.
It includes the preview sheet and actual disk ZIP under the project's assets.
The website validates the ZIP hash/size and includes download bytes in the
project's approval digest. The preview build and website tests pass.

Public: https://retrocomputerist.com/projects/cga-image-studio/#demo

Published October 20, 2026 with the owner's explicit authorization, including
the corrected Wick colors and Leah's New CGA Multicolor Composite conversion.
Cloudflare version: `a0655449-0811-4321-a002-40a56f193dc1`.
All 24 actual COMs passed playback (361.610 seconds); 22 demo tests, 23 website
tests, three Worker checks and the public build/deployment dry run passed.
All 27 public demo assets match local bytes, all 24 gallery images load, and
the private review route returns 404. Verification evidence is retained in
`artifacts/demo-slideshow/publication-verification.json`.
No Git commit, source push or new converter release was made. Existing
unrelated website edits and approval receipts are preserved.
