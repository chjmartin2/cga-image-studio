# Refactor Plan

The first GitHub baseline preserves `cga_v165.py` as the known-good working application. Refactoring should happen after the baseline is committed and tagged.

## Goals

- Keep the current application behavior stable.
- Replace manual filename revisioning with Git commits and semantic version tags.
- Split the large single-file program into focused modules.
- Add tests around pure conversion, palette, packing, and export helpers.
- Keep the GUI runnable throughout the transition.

## Suggested Sequence

1. Preserve `cga_v165.py` as the baseline.
2. Add a package skeleton under `src/cga_converter/`.
3. Move palette constants and palette builders into `palettes.py`.
4. Move dithering and resize helpers into `dithering.py` and `resize.py`.
5. Move DOS `.COM` packing/building helpers into `dos_com.py`.
6. Move composite/NTSC simulation helpers into `composite.py`.
7. Move Mode Switch logic into `mode_switch.py`.
8. Move the Tkinter app into `app.py`.
9. Replace `cga_v165.py` with a thin launcher or compatibility wrapper.

Each step should be a separate commit. After every move, run:

```powershell
.\.venv\Scripts\python.exe -m py_compile cga_v165.py
```

