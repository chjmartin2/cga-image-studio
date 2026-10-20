# CGA Image Studio

**Current release candidate: 1.0.0-rc.1.** Download the
[standalone Windows x64 executable](https://github.com/chjmartin2/cga-image-studio/releases/download/v1.0.0-rc.1/CGAImageStudio.exe)
or open the [release page](https://github.com/chjmartin2/cga-image-studio/releases/tag/v1.0.0-rc.1)
for the approved 24-image bootable demo, exported gallery and checksums.
No Python installation is needed for the executable; CPU acceleration is bundled.
Mode Switch offers **1**, **8**, and **8 staggered** writes for 320x200 conversion
and COM/ASM/DSK export. The staggered selection uses a fixed alternating pattern;
every visible palette boundary moves between adjacent rows without animation.
See [Windows build and use](docs/WINDOWS_BUILD.md) and
[release notes](docs/RELEASE_v1.0.0-rc.1.md).

CGA Image Studio is a Python/Tkinter desktop tool for converting modern images into IBM CGA-style graphics outputs. It can preview classic CGA modes, composite artifact color modes, text-mode color tricks, mode-switch palette experiments, and export many results as DOS `.COM` programs.

This repository starts from the historical manually versioned source file `cga_v165.py`, now preserved in `Old Storage/legacy-root/`. The first GitHub baseline is version `0.1.0`, corresponding to the working `v165` application. Current development continues in `cga_v167.py`.

## Standard CGA text conversion

Choose **RGB Text** > **40-column Text (RGB)** or **80-column Text (RGB)**.
At character height 8 these are standard 40x25 and 80x25 text. Choose pixel,
2x2/4x4/whole-character averaging, weighted DCT or multiscale matching; optional
preprocessing and CGA-color dithering run before the character search. The
converter evaluates all 256 glyphs and all foreground/background color pairs.
Text defaults to **DCT (structure)** at stock weights, Original preprocessing,
and CGA reduction/preconversion dithering off.
Use **Preview text input** to inspect the downconverted image before matching,
or switch the Input pane between **Source** and **Text input**.
**Optimize** compares conversion settings with a fixed visual score while keeping
the chosen character height and CGA-reduction checkbox. **DCT Tweaker** adjusts
frequency/color weights with automatic preview updates as you move its sliders.
Source installations can use an available CUDA GPU automatically, including DCT
Tweaker and Optimize, with full CPU fallback. The standalone executable uses CPU
matching. Optional CUDA dependencies are listed in
`requirements-cuda.txt`; the status bar identifies the active backend.
Character heights 2-8 respect CGA timing and video memory limits, with matching
previews and COM/ASM/DSK exports. See [options and artist-mode TODO](docs/STANDARD_TEXT.md).

## One palette per scanline

For **320x200 (4 Colors) Mode Switch**, select **1** to use one four-color
palette across each complete scanline. **Background color** offers all 16 CGA
colors and **Per line**: a named color fixes the background for the whole image,
while Per line lets the encoder choose it separately for each row.

In advanced settings, **Force unique palette per scanline** prevents adjacent
rows from using the same three foreground colors. Background changes do not
count as a new palette: the background still follows its fixed-color or Per
line setting. The first row is unrestricted, and a palette can return after
one intervening row (A, B, A). Bright and dim combinations are distinct. This
option is off by default and applies to the single-palette-per-scanline profile.

The **Mode Switch layout map** has its own **Zoom** selector: Auto, 1x, 2x,
4x and 8x. Whole-pixel enlargement preserves individual scanlines. Scroll to
inspect enlarged areas; Shift + mouse wheel scrolls horizontally. Map zoom
updates immediately without reconversion or changing the output preview zoom.

Single-line conversion uses a shared linear-light dithering renderer for palette
search and output. Dither-aware optimization is enabled by default for this
profile; candidate trials respect the selected diffusion kernel, serpentine
direction, ordered matrix, or no-dither setting. Only the winning row's error
is carried forward. With dither-aware search enabled, complete-image comparison selects
among up to three palette-selection passes using perceptual color, spatial
detail and edge errors. Every pass starts with fresh diffusion state. This
bounded search does not guarantee a globally optimal image. Multiple palettes
within a scanline remain experimental and are excluded from the reviewed demo.

## Repeating scanline palettes

**320x200 Mode Switch Repeat** searches for a global cycle of **2 to 6** legal
CGA four-color palettes. Two rows means A, B, A, B; three means A, B, C, A, B, C.
Choose **Repeat rows** in the basic settings; the default is 2.

The search evaluates the palettes' combined colors across the whole image,
including unrestricted dithering, before encoding the repeating scanlines.
The final preview and exports use only the four colors assigned to each row.
Error diffusion carries signed color error between rows of the cycle. Color
selection and outgoing error use the same bounded linear-light value, preventing
unrepresentable overflow from accumulating and bleeding into later rows. The
combined set can contain fewer than four times the repeat length because
palettes share colors, and CGA RGB has only 16 hardware colors in total.

Repeat mode's **Background** defaults to **Adjustable**, which lets each cycle
slot choose its own background. Select any of the **16 named CGA colors** to
force that background on every row. **Forced No Repeats** chooses backgrounds
with no equal adjacent rows, including the last-to-first cycle boundary.
Nonadjacent reuse is allowed: black/gray/black/gray is a legal four-row cycle;
black/gray/black is not a legal three-row cycle because its wrap repeats black.
Every slot must use a **different three-color foreground
combination**, regardless of background; no combination may repeat within the
cycle. Standard palettes provide four combinations. Enabling Tweaked adds the
two tweaked combinations, for six total. Selecting 5 or 6 rows automatically
enables those combinations. Fixed backgrounds support up to four rows with
Tweaked off, or six with it on. Background selection remains independent of
foreground uniqueness.
The ordinary mode's optional adjacent-row constraint is separate; Repeat always
enforces uniqueness across the entire cycle.

The palette layout map and its independent zoom display the actual repeating
schedule. PNG/WEBP, COM, ASM, bootable disk and MartyPC exports share the same
encoded rows. Search uses bounded dithered finalists; it does not guarantee a
globally optimal dithered image.

## Reviewed demo disk

The release includes **24 owner-reviewed conversions** on one bootable 720 KiB
FreeDOS floppy, with a DOS menu and separate RGB/composite slideshow cycles.
Download the [demo disk ZIP](https://github.com/chjmartin2/cga-image-studio/releases/download/v1.0.0-rc.1/cga-studio-demo-disk.zip)
or [complete exports and preview gallery](https://github.com/chjmartin2/cga-image-studio/releases/download/v1.0.0-rc.1/cga-studio-demo-exports.zip).
The approved demo is included unchanged from its October 20 publication.

Extract the disk ZIP and mount `CGADEMO.DSK` in your DOS emulator. Select RGB
for images 1-14 and composite for 15-24. Leah (#21) uses New CGA; the other
composite selections use Old CGA. The menu offers individual pictures and
one-pass slideshow cycles. See the [demo guide](docs/DEMO_DISK.md) for timing,
display settings, provenance and playback evidence. MartyPC and ROMs are not
bundled. In the development checkout, `run_demo_disk.cmd` launches the local
reviewed disk when its generated artifacts are present.

## Project Status

Version 1.0.0-rc.1 is the first 1.0 release candidate. It includes the standard
RGB text converter, CPU/GPU composite search, repeating scanline palettes,
export fixes and optional MartyPC linking developed since the previous alpha.
The complete interactive acceptance matrix, clean-machine Windows qualification
and physical CGA hardware qualification remain open; this is a prerelease.

The current 320x200 Mode Switch controls offer **1, 8 or 8 staggered writes per scanline**.
The [staggered profile](docs/research/staggered_validation.md) has independent
geometry and timing assets. Region widths vary slightly between alternating rows;
the pattern is identical every frame and for every image.
The corrected eight-write profile passes the wait-state-enabled MartyPC core
acceptance suite, and the user confirmed the native MartyPC picture. See the
[validation report](docs/research/eight_write_validation.md). Physical CGA
hardware validation and the full studio feature audit remain outstanding.
The 8-write GUI profile uses the acquired STARTLCK mode-4 timing implementation,
with an independent leading-edge palette set during horizontal blanking. Both profiles support
optional dither-aware palette optimization. The older 13-write dense profile
remains in the source and diagnostic tools as a historical experiment.

See [Project status and restart notes](docs/PROJECT_STATUS.md) for the current
development checkpoint, validation commands, and the next work to tackle.

The [Picard image test](docs/IMAGELOCK.md) uses this core converter and includes
a bootable disk, expected preview and registration pattern. Run
[`tools/launchers/run_imagelock.cmd`](tools/launchers/run_imagelock.cmd) to boot it
in the local MartyPC build.

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

The application window title should show `CGA Image Studio 1.0.0-rc.1`.

## Requirements

- Python 3.12
- Pillow
- NumPy
- Tkinter, included with standard Windows Python installs

The **640x200 (1024 Colors)** mode uses the promoted CPU/GPU encoder, formerly
named **640x200x1024 NEW**, and can use optional Numba CPU acceleration
or an NVIDIA CUDA GPU, with legacy-compatible error diffusion, ordered dithering,
or direct matching. See [NEW text search setup and comparisons](docs/NEW_TEXT_SEARCH.md)
for installation, search guarantees, and the reproducible benchmark.

## Main Features

- Load common image formats such as PNG, WebP, JPEG, BMP, GIF, and TIFF.
- Convert images into classic and experimental CGA-oriented modes.
- Preview output inside a Tkinter GUI.
- Adjust brightness, contrast, RGB gains, scaling mode, and resampling filter.
- Apply no dithering, ordered dithering, or multiple error diffusion kernels.
- Optimize palettes for selected modes.
- Simulate NTSC composite artifact color behavior.
- Export previews as PNG (default) or lossless WebP, preserving all simulated colors; GIF is also available with its 256-color limit.
- Export DOS `.COM` files for many modes.
- Export NASM-compatible `.ASM` source that rebuilds the generated `.COM` exactly.
- Export a bootable DOS `.DSK` image containing the generated program as `TEST.COM`.
- Open the current conversion in MartyPC with one button: create a bootable disk and run its COM automatically.
- Use `320x200 (4 Colors) Mode Switch` with either one palette write per
  scanline or the acquired 8-write mode-4 profile. The 8-write profile uses
  fixed, calibrated palette boundaries and an independent leading-edge palette.
- Optionally choose palettes with `Dither aware optimization (Lab, slower)`
  for either production Mode Switch profile.

## Supported Mode Families

### Optional MartyPC link

After conversion, click **Open in MartyPC**. Studio creates a bootable disk,
starts `TEST.COM` automatically, and selects RGB or composite rendering for the
current mode. The 640x200 **RGB text** preview selection is respected. No Save As
dialog is needed. **Export > Save DSK and launch in MartyPC...** remains available
when you also want a named disk file. Stale or unfinished conversions cannot launch.

Studio detects the working MartyPC build in this checkout and relocates a saved
project link from the older checkout. For another installation, choose
**Export > Link to MartyPC...**, then select `martypc.exe` and its working main
TOML configuration. The integration supports MartyPC 0.5. MartyPC and ROMs are
not bundled. Runtime configurations match 360/720 KB disks to drive A and use
stock 8088 timing with wait states and DRAM refresh for the raster programs.

The link is remembered in `%LOCALAPPDATA%\CGAImageStudio\marty-link.json`.
Separate launch configurations, disk copies, and logs are stored under
`%LOCALAPPDATA%\CGAImageStudio\marty-runs`. These folders can be removed after
closing their MartyPC windows. Saved master disks and the installation's original
configuration are left intact; emulator output paths are isolated in each run.
Use **Link to MartyPC...** again to change the link.

### Available modes

- `320x200 (4 Colors)`
- `640x200 (2 Colors)`
- `160x200 (16 Colors) Composite`
- `640x200 Multicolor Composite`
- `160x100 (16 Colors)`
- `640x200 (16 Colors) Char`
- `80x100 (4352 Colors) HiColor`
- `80x100 (512 Colors)`
- `80x100 (1024 Colors) Mini-Frames`
- `80x100 (1024 Colors)`
- `640x100 (1024 Colors)`
- `640x200 (1024 Colors)` — automatic CPU/GPU NTSC optimization, with Composite and RGB text previews
- `320x200 (4 Colors) Mode Switch`
- `320x200 Mode Switch Repeat`
- `40-column Text (RGB)` and `80-column Text (RGB)`

## Versioning

This project is moving from manual filename revisioning, such as `cga_v165.py`, to semantic versioning.

- `0.1.0`: first GitHub baseline, historical app version `v165`
- `0.2.0` development: two-write lockstep Mode Switch encoder, app version `v166`
- `0.3.0` development: app version `v167`; began with the 13-write dense
  lockstep encoder and now uses 1-or-8-write production Mode Switch controls
- `0.x`: active development and refactoring
- `1.0.0-rc.1`: first 1.0 release candidate, with Windows executable and reviewed demo
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

Install NASM and add it to `PATH` before running the full export regression suite:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
```

NASM is optional for running the application, but required for the full test
suite's assembly and demo-menu checks. The ASM round-trip tests and reviewed
demo menu also accept a `NASM` environment variable pointing to the executable;
they can detect a local Windows installation.

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
[`tools/launchers/run_startlock.cmd`](tools/launchers/run_startlock.cmd) to open
the separate MartyPC build with the disk mounted.
Its first four configured PIT-phase tests produced the same visible marker
position; this is emulator evidence for the diagnostic, not production validation.

A separate MartyPC 0.5.0 source build is available through
[`tools/launchers/run_martypc_latest.cmd`](tools/launchers/run_martypc_latest.cmd).
See the [build and update guide](docs/MARTYPC_BUILD.md)
for the pinned upstream revision, local toolchain, CGA configuration and checks.

## Repository layout

The root contains the 20 current application Python files, including
`cga_v167.py`, the packaged entry point `studio_launcher.py`, and the supporting
conversion, UI, version and MartyPC modules. `run_cga_v167.cmd` starts the app;
`run_demo_disk.cmd` starts the reviewed demo.

| Location | Contents |
| --- | --- |
| `assets/` | Application branding and runtime resources |
| `tools/` | Current build, demo, diagnostic and validation tools |
| `tools/launchers/` | Windows launchers for the optional MartyPC diagnostics |
| `tests/`, `test_images/` | Regression tests and their existing image inputs |
| `files/` | Boot templates, demo data and diagnostic fixtures used by current tools |
| `docs/` | Application documentation and retained research evidence |
| [`Old Storage/`](<Old Storage/README.md>) | Historical app versions, root experiments and reference source |

The existing `.venv/`, `external/`, `artifacts/`, `build/`, `dist/` and `release/`
paths remain in place for local dependencies and generated builds. Historical
files were moved without deletion; the archive guide records their locations
and how to run preserved experiments with `tools/run_archived.py`.

## Refactor Direction

The main application remains in `cga_v167.py`, with focused conversion and UI
modules beside it. Future refactors should be small, reversible commits that
move code into modules without changing behavior.

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
