# PIT9 / cycle-clock Cheetara investigation — 2026-10-07

**Superseded by the [full-palette timing repair](pit9_locked_validation.md).**
The report below records the earlier guarded workaround and its limitations.

The supplied MartyPC changes reproduce the hardware-tested Cheetara failure.
The normal MartyPC checkout and executable remain unchanged. A separate guarded
encoding passes the modified emulator, with reduced color freedom around seams.
**Lockstep acquisition itself remains unresolved; the guarded encoder is an
experimental workaround, not a replacement production timing profile.**

## Isolated emulator

The owner supplied `martypc_pit9_cycle.zip` in the project parent directory.
Its three files differ from local MartyPC commit
`05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44` by:

- Selecting `ClockingMode::Cycle` instead of `Default` when installing video.
- Passing the frontend PIT offset without the previous `& 0x03` mask.
- Setting the example configuration's PIT offset to 9.

The private copy lives at `external/research/pit9-cycle/martypc`, with its own
desktop target and install directory. The headless validator has a separate
target and also passes the PIT offset without masking. The toolchain cache is
shared; the original source, target and configuration are preserved. SHA-256
checks confirm the original executable and all three ZIP-target files are
unchanged. Desktop version, machine scan and ROM scan pass after correcting the
isolated configuration's relative project-files path.

`adjust_pit` takes **system-clock ticks**, not PIT counter ticks. Testing offsets
0 through 11 covers a complete 12-system-tick PIT input period. For this setup,
offsets 0/3/6/9 exercise the four distinct groups observed in the measurements.
These are not hardware phase-detector signature labels.

## Exact original and reproduction

The owner identified `cga_320_startlock (1).zip` in Downloads as the hardware
test. Its disk contains `TEST.COM`, SHA-256
`dc2311e92d0262e8e39ea6e3629aaf9b4d5405691a4811c8e4b28610af4b6f89`.
After excluding palette immediates and VRAM, it matches the current aligned
eight-write template byte-for-byte. Its intended image was reconstructed from
those original palette operands and VRAM; no source artwork was assumed.

The exact original matches all 117 captured frames in the normal core at offset
0. In the modified core at offset 9, all 110 captured frames have 4,252 incorrect
visible dots. The image is stable in time; palette registration is wrong.

Independent registration tests cover 12 offsets × eight entry paddings:
0, 1, 2, 3, 7, 13, 31 and 127 NOPs. All 96 cases produce consistent boundaries
within each launch, but the positions differ between launches:

| Boundary | Existing preview | Measured minimum | Measured maximum |
| --- | ---: | ---: | ---: |
| 1 | 25 | 24 | 29 |
| 2 | 65 | 64 | 70 |
| 3 | 113 | 112 | 118 |
| 4 | 161 | 159 | 164 |
| 5 | 209 | 207 | 212 |
| 6 | 249 | 247 | 253 |
| 7 | 289 | 288 | 293 |

A fixed offset-9 geometry adjustment passed the default injected startup but
failed entry perturbations. Experiments with VRAM reads, multiplication delays,
additional sub-tick status feedback and direct graphics acquisition did not
establish exact registration across the tested starts. Their sources and raw
results remain private under the isolated research directory. None was installed
as a production timing change.

## Guarded encoding

`tools/build_pit9_guarded.py` optimizes palettes and indices using a dynamic
program over each row's eight regions. Neighboring palettes must share their
background or foreground triple. Around each uncertain boundary, pixels use
only VRAM indices whose RGBI interpretation is identical in both palettes.

The seven guard strips are `[22,31)`, `[62,72)`, `[110,120)`, `[157,166)`,
`[205,214)`, `[245,255)` and `[286,295)`. They cover the measured intervals
with two additional pixels on each side. Palette movement inside a strip
therefore cannot change its displayed colors. This reduces color choices in
those 9–10-pixel strips and can also influence neighboring palette selection.
The original two-bit framebuffer, timing instructions and refresh protocol
are unchanged. This does not establish tolerance to arbitrary timing errors,
vertical displacement or untested hardware behavior.

The candidate is encoded from the original intended RGBI image, which was
already quantized and dithered. Its preview is the appropriate hardware target;
it is not identical to the original preview.

## Validation

Every captured frame is compared pixel-for-pixel with the candidate's own
expected RGBI image, including unequal pairs of output dots. Effective CPU
wait states and active raster refresh remain asserted by the validator.

| Gate | Cases | Exact frames |
| --- | ---: | ---: |
| Guarded Cheetara, 12 offsets × eight entry paddings | 96 | 11,094 |
| DOS boot, modified offsets 0/3/6/9 and normal-core offset 0 | 5 | 376 |
| Five successive DOS launches, modified offsets 0/3/6/9 | 4 | 460 |
| Full 3,600-frame display and DOS return, modified offset 9 | 1 | 3,599 |
| Guarded registration, modified offsets 0/3/6/9 | 4 | 461 |
| Delivered comparison disk boot, modified offsets 0/3/6/9 | 4 | 788 |
| **Total** | **114** | **16,778** |

The guarded registration uses all four VRAM indices. Complete-display timing
has the usual last incomplete buffer: 3,600 raster executions yield 3,599
completed visible frames. The original control still reproduces the error.
No physical hardware test has been performed in this session.

Details and hashes: [validation JSON](pit9_cycle_validation.json). Raw captures,
copied source, binaries, artwork and failed candidates stay in ignored local
research/artifact directories.

## Run and compare

From Source, the separate launcher defaults to the exact original Cheetara disk
and offset 9. It makes and verifies a fresh runtime mount:

```powershell
.\run_martypc_pit9.cmd
```

Run the guarded comparison disk in the same isolated build:

```powershell
.\run_martypc_pit9.cmd artifacts\pit9-cycle\CGATEST.DSK --program GUARD --phase 9
```

Use `--program ORIG`, `RAWREG` or `GREG` for the other programs. Offsets 0–11
are supported; `--prepare-only` verifies the mount without opening a window.

To rebuild the guarded image and registration:

```powershell
.venv\Scripts\python.exe tools\build_pit9_guarded.py --registration external\research\pit9-cycle\calibration\expected.rgbi
.venv\Scripts\python.exe tools\package_pit9_test.py
```

`artifacts/pit9-cycle/Cheetara-hardware-comparison.zip` contains a bootable
360 KiB comparison disk, the four COM programs, expected previews, instructions
and SHA-256 hashes. ORIG is the exact hardware-tested program; RAWREG exposes
the timing variation; GUARD and GREG test the encoding workaround. The packet
contains no emulator or ROM. It has been prepared locally, not sent to Kevju.
