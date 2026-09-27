# CGA Image Studio

**Checkpoint prerelease: v0.3.0-alpha.1.** A standalone Windows x64 executable is
available on the [releases page](https://github.com/chjmartin2/cga-image-studio/releases).
Eight-write COM/ASM/DSK exports are intentionally disabled pending the timing
repair. See [Windows build and use](docs/WINDOWS_BUILD.md) and
[checkpoint release notes](docs/RELEASE_v0.3.0-alpha.1.md).

CGA Image Studio is a Python/Tkinter desktop tool for converting modern images into IBM CGA-style graphics outputs. It can preview classic CGA modes, composite artifact color modes, text-mode color tricks, mode-switch palette experiments, and export many results as DOS `.COM` programs.

This repository starts from the historical manually versioned source file `cga_v165.py`. The first GitHub baseline is version `0.1.0`, corresponding to the working `v165` application. Current development continues in `cga_v167.py`.

## Project Status

This project is in early active development. The current version is buggy, some features are incomplete, and several planned features are not implemented yet. Expect rough edges while the app is being cleaned up, refactored, and prepared for more stable releases.

The current production Mode Switch controls offer **1 or 8 writes per scanline**.
The acquired eight-write timing profile is currently being corrected after a
validation-harness error: CPU wait states were omitted, also bypassing refresh
DMA delays. The previous passing emulator counts do not validate normal native
MartyPC operation. See the [reproduced failure](docs/research/garbled_export_investigation.md).
The 8-write GUI profile uses the acquired STARTLCK mode-4 timing implementation,
with an independent leading-edge palette set during horizontal blanking. Both profiles support
optional dither-aware palette optimization. The older 13-write dense profile
remains in the source and diagnostic tools as a historical experiment.

See [Project status and restart notes](docs/PROJECT_STATUS.md) for the current
development checkpoint, validation commands, and the next work to tackle.

The [Picard image test](docs/IMAGELOCK.md) uses this core converter and includes
a bootable disk, expected preview and registration pattern. Double-click
`Picard CGA Demo.lnk` to boot it in the local MartyPC build.

## Quick Start

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the application:

```powershell
.\.venv\Scripts\python.exe cga_v167.py
```

On Windows, you can also run:

```text
run_cga_v167.cmd
```

The application window title should show `CGA Converter v167`.

## Requirements

- Python 3.12
- Pillow
- NumPy
- Tkinter, included with standard Windows Python installs

## Main Features

- Load common image formats such as PNG, JPEG, BMP, GIF, and TIFF.
- Convert images into classic and experimental CGA-oriented modes.
- Preview output inside a Tkinter GUI.
- Adjust brightness, contrast, RGB gains, scaling mode, and resampling filter.
- Apply no dithering, ordered dithering, or multiple error diffusion kernels.
- Optimize palettes for selected modes.
- Simulate NTSC composite artifact color behavior.
- Export preview GIFs.
- Export DOS `.COM` files for many modes.
- Export NASM-compatible `.ASM` source that rebuilds the generated `.COM` exactly.
- Export a bootable DOS `.DSK` image containing the generated program as `TEST.COM`.
- Use `320x200 (4 Colors) Mode Switch` with either one palette write per
  scanline or the acquired 8-write mode-4 profile. The 8-write profile uses
  fixed, calibrated palette boundaries and an independent leading-edge palette.
- Optionally choose palettes with `Dither aware optimization (Lab, slower)`
  for either production Mode Switch profile.

## Supported Mode Families

- `320x200 (4 Colors)`
- `640x200 (2 Colors)`
- `160x200 (16 Colors) Composite`
- `160x100 (16 Colors)`
- `640x200 (16 Colors) Char`
- `80x100 (4352 Colors) HiColor`
- `80x100 (512 Colors)`
- `80x100 (1024 Colors) Mini-Frames`
- `80x100 (1024 Colors)`
- `640x100 (1024 Colors)`
- `640x200 (1024 Colors)`
- `320x200 (4 Colors) Mode Switch`
- `640x200 (2 Colors) Mode Switch`

## Versioning

This project is moving from manual filename revisioning, such as `cga_v165.py`, to semantic versioning.

- `0.1.0`: first GitHub baseline, historical app version `v165`
- `0.2.0` development: two-write lockstep Mode Switch encoder, app version `v166`
- `0.3.0` development: app version `v167`; began with the 13-write dense
  lockstep encoder and now uses 1-or-8-write production Mode Switch controls
- `0.x`: active development and refactoring
- `1.0.0`: future stable release milestone

Git tags should mark release points, for example:

```powershell
git tag v0.1.0
```

## Quick Validation

Check syntax and import without opening the GUI:

```powershell
.\.venv\Scripts\python.exe -m py_compile cga_v167.py
.\.venv\Scripts\python.exe -B -c "import cga_v167; print(cga_v167.__version__)"
```

Run the export regression suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

NASM is optional for running the application. Byte-for-byte ASM rebuild tests
require it; the tests accept a `NASM` environment variable, search `PATH`, and
detect a local Windows installation.

Run the application with `run_cga_v167.cmd` to check the GUI. Exported raster
timing still needs a MartyPC run and screenshot comparison; syntax checks and
binary round trips cannot establish hardware timing or boot-to-boot stability.

## Timing Feasibility and MartyPC

The [CGA timing research](docs/CGA_TIMING_RESEARCH.md) examines Reenigne's source,
historical measurements, and a published physical bus capture. Stable beam
synchronization is demonstrated in reference work; this project's eight-write
export remains unvalidated on hardware. The next gate is a bounded palette-marker
diagnostic across startup phases before further palette-density work.

The [AREA 5150 disassembly](docs/research/area5150/README.md) recovers the released
Lake initializer and matches its automatic acquisition to the physical capture.
It includes the annotated assembly, loader contract and reproducible byte checks.

The [STARTLCK demo](docs/STARTLCK.md) packages a mode-4 start-line marker as
`files/STARTLCK.COM` and the bootable `files/STARTLCK.DSK`. Run
`run_startlock.cmd` to open the separate MartyPC build with the disk mounted.
Its first four configured PIT-phase tests produced the same visible marker
position; this is emulator evidence for the diagnostic, not production validation.

A separate MartyPC 0.5.0 source build is available through
`run_martypc_latest.cmd`. See the [build and update guide](docs/MARTYPC_BUILD.md)
for the pinned upstream revision, local toolchain, CGA configuration and checks.

## Refactor Direction

The current application is intentionally preserved as a single working file. Future refactors should be small, reversible commits that move code into modules without changing behavior.

Proposed future layout:

```text
src/
  cga_converter/
    app.py
    palettes.py
    dithering.py
    resize.py
    composite.py
    ntsc_text.py
    mode_switch.py
    dos_com.py
    image_adjust.py
tests/
docs/
```
