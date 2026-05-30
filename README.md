# CGA Converter

CGA Converter is a Python/Tkinter desktop tool for converting modern images into IBM CGA-style graphics outputs. It can preview classic CGA modes, composite artifact color modes, text-mode color tricks, mode-switch palette experiments, and export many results as DOS `.COM` programs.

This repository starts from the historical manually versioned source file `cga_v165.py`. The first GitHub baseline is version `0.1.0`, corresponding to the working `v165` application.

## Quick Start

From this folder:

```powershell
.\.venv\Scripts\python.exe cga_v165.py
```

Or double-click:

```text
run_cga_v165.cmd
```

The application window title should show `CGA Converter v165`.

## Requirements

- Python 3.12
- Pillow
- NumPy
- Tkinter, included with standard Windows Python installs

Install dependencies into a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

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

## Visual Studio Setup

Open this folder in Visual Studio and select this interpreter:

```text
C:\Users\chjmartin2\Desktop\CGAFun\.venv\Scripts\python.exe
```

Use this startup file:

```text
C:\Users\chjmartin2\Desktop\CGAFun\cga_v165.py
```

## Versioning

This project is moving from manual filename revisioning, such as `cga_v165.py`, to semantic versioning.

- `0.1.0`: first GitHub baseline, historical app version `v165`
- `0.x`: active development and refactoring
- `1.0.0`: future stable release milestone

Git tags should mark release points, for example:

```powershell
git tag v0.1.0
```

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

