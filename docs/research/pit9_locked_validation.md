# Full-palette Cheetara timing repair in modified MartyPC

The new experimental export renders Cheetara correctly in the supplied
PIT9/cycle MartyPC core. It uses the normal eight-region quantizer with full
palette freedom, without seam guard strips or shared-color constraints.
All **217 qualified cases and 25,309 completed frames** match the encoder's
expected RGBI image pixel for pixel, with no split logical pixels.

This supersedes the earlier [guarded workaround](pit9_cycle_validation.md).
The standard studio encoder and primary MartyPC remain unchanged. The new
source and builder are separate, so the hardware test can be reviewed first.

## What changed

The original export was stable within a run but acquired different palette
positions across startup and PIT phase variations. Four changes address this:

1. A three-read CGA memory/MUL sequence establishes a consistent CPU/CGA phase.
   The two middle multiplication inputs are 63, rather than assuming that the
   original Lake sequence will also align our new graphics raster.
2. A one-character, two-line graphics CRTC setup and conditional 48-dot delay
   establish consistent CRTC parity before restoring the full screen geometry.
   An accelerated refresh/RAM sweep allows the old geometry to settle first.
3. Acquisition and drawing use matching CGA lock prefixes and post-sample
   delays. PIT1 restarts at a consistent instruction position; its divisor stays
   19 while the raster runs. Initial acquisition advances by 100 PIT ticks to
   account for the additional prefix, reducing the acquisition time.
4. One NOP moves from gap 1 to gap 2, keeping the total at 33. This avoids the
   refresh collision that had made writes 3 and 4 move between PIT phase groups.

The row period remains 304 CPU clocks. PREP and MAIN still use PIT0 intervals
19760 and 152, totaling 19912 ticks per frame. The original Lake initializer at
COM addresses 0182h through 03FFh is preserved byte for byte. The new graphics
acquisition follows it; this is not a claim that the complete program is Lake.

Measured region boundaries are **0,24,59,113,159,207,248,288,320**. Re-encoding
uses this measured geometry. The image is consequently a new quantization,
not an assertion that the original flawed export is now byte-identical. The
source is the intended RGBI image recovered from the hardware-tested COM,
because the original source artwork was unavailable.

## Validation

Every completed frame is checked against the image's expected 320x200 RGBI
pixels, including both output dots of every logical pixel. The validator asserts
CPU wait states, scheduled DMA refresh, and active PIT1 mode 2/count 19.

| Check | Cases | Exact frames |
| --- | ---: | ---: |
| Initial Cheetara offsets 0/3/6/9 | 4 | 338 |
| Cheetara and registration, 12 offsets x eight startup paddings | 192 | 16,224 |
| DOS boot, all 12 offsets | 12 | 3,516 |
| Five successive DOS launches, offsets 0/3/6/9 | 4 | 460 |
| Full 3600-raster run and DOS return, offset 9 | 1 | 3,599 |
| Actual packaged comparison disk boot, offsets 0/3/6/9 | 4 | 1,172 |
| **Total** | **217** | **25,309** |

Startup paddings are 0,1,2,3,7,13,31,127 NOPs, applied before acquisition. PIT
offsets are system/master-clock ticks; 0 through 11 spans its input period.
The independent registration image uses all four framebuffer indices, all 16
RGBI colors, changing row palettes, and the inherited leading palette.
The final partial frame before DOS cleanup is excluded from completed-frame
counts. Full machine and binary identities are in
[the validation record](pit9_locked_validation.json).

The PNG `artifacts/pit9-locked/CHEETL-modified-MartyPC.png` is made from the
modified core's actual captured display buffer, enlarged with nearest-neighbor
scaling. It is not an encoder preview. The isolated native desktop executable
was launched at offset 9 with the tested boot disk; native window capture could
not be obtained because the computer-use native pipe was unavailable. Native
visual confirmation is therefore not claimed by this report.

Physical hardware qualification remains outstanding. Nothing has been sent to
Kevju, committed, pushed, or published.

## Build and run

```powershell
.venv\Scripts\python.exe tools\build_pit9_locked.py
.venv\Scripts\python.exe tools\package_pit9_locked.py
.\run_martypc_pit9.cmd artifacts\pit9-locked\CGATEST.DSK --program TEST --phase 9
```

The builder also accepts `--image path` for new artwork. It applies the updated
geometry only inside its own conversion process and patches its separately
assembled template. Production profiles and GUI behavior are unchanged.

`artifacts/pit9-locked/Cheetara-PIT9-locked-test.zip` contains the boot disk,
image COM, registration COM, exact original COM, expected previews, actual
modified-core output, instructions and SHA-256 hashes. The boot disk autoruns
TEST; REGLOCK shows the registration pattern and ORIG reproduces the control.
Escape or the 60-second timeout returns to DOS. No emulator or ROM is included.

New sources:

- `tools/imagelock_pit9.asm`: acquired raster and graphics CRTC initialization.
- `tools/build_pit9_locked.py`: normal quantizer with the measured geometry.
- `tools/package_pit9_locked.py`: verified hardware comparison packet.

Qualification scripts, copied emulator sources, source images, raw captures and
failed timing experiments remain in ignored local research/artifact folders.
