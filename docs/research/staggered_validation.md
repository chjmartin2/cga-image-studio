# Fixed staggered eight-write profile — 2026-09-27

The **8 staggered** selection uses a separate calibrated template and row layout.
Its pattern is fixed at assembly time and identical across frames, exports and
images. There is no random number generation during conversion or display.

| Zero-based row | Visible region bounds |
| --- | --- |
| Even | 0, 25, 65, 113, 161, 209, 249, 289, 320 |
| Odd | 0, 49, 97, 137, 185, 233, 273, 313, 320 |

All seven visible palette transitions move on adjacent rows. This is not a
perfect rigid translation: two inner region widths exchange 40/48-pixel widths
to meet measured timing margins. The converter optimizes against the actual
row geometry, including clipped edge regions. The eighth write remains in
blanking and supplies the next row's leading palette, including row 199 → 0.

## Timing implementation

Acquisition, paired PREP/MAIN entry, refresh handling and frame cadence remain
the same as the [aligned profile](eight_write_validation.md). Even rows use the
original 33-NOP schedule. Odd rows use five leading NOPs, six inter-write gaps
of 2, 2, 3, 2, 2, 1 NOPs, ten NOPs before the blanking write, a short jump to the
next instruction, and three trailing NOPs. Total odd-row padding is 30 NOPs plus
the jump. The jump discards prefetched instructions and gives the following row
a repeatable instruction-fetch state.

First-write intervals alternate **320 and 288 CPU clocks**, totaling 608 clocks
per two scanlines. Frame spacing remains **79,648 CPU clocks**. The scanline grid
does not drift; the first write deliberately moves within that grid. The default
assembly without `STAGGERED` rebuilds the alpha.2 aligned template byte-for-byte.

Simple NOP redistribution failed at some startup phases. Those candidates were
not enabled. The accepted profile is identified by its template hash in
`assets/mode4_lock/staggered/profile.json`; preview and exporter select it together.

## Acceptance evidence

The unchanged MartyPC core at commit
`05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44` runs IBM 5160 / CGA, normal-speed 8088,
effective CPU waits and active raster refresh. Each activation asserts PIT1
mode 2, reload 19, counting and retrigger state. Preparation still briefly quiets
refresh; physical hardware behavior is unqualified.

The independent staggered suite passes **44 cases / 18,736 exact visible frames**:

- Eight entry-delay variants across four PIT phases, exercising all bitmap indices.
- Four photo runs with full RGBI comparison.
- Four full DOS boots, 3,599 captured complete frames per boot.
- Five successive DOS launches at each PIT phase, 55 captured frames per case.

Every captured frame matches the expected pixels, including the first and last
frames. Recorded first-write intervals contain only 288 and 320 clocks, and all
frame intervals are 79,648 clocks. The shipped `STAGGER.DSK` is the exact disk
used in the four full-boot cases.

Actual GUI callbacks pass None/Ordered/Error diffusion × dither-aware off/on ×
black-border off/on for both 8 and 8 staggered. Each of the 12 staggered COMs
matches its preview in the core (1,383 frames); each ASM rebuilds byte-for-byte,
and each disk's FAT12 TEST.COM matches the export. The aligned GUI checks also
pass separately. Software regression results: 31 tests / 59 subtests passed.

Curated per-case options, hashes and counts are in
[staggered_validation.json](staggered_validation.json). Raw experimental captures
remain under ignored `external/research`. Native visual confirmation of this new
profile remains pending; the user's alpha.2 confirmation applied to aligned 8.

## Reproduce

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe tools/validate_mode4_release.py --staggered
.venv/Scripts/python.exe tools/smoke_mode4_gui.py --staggered
.venv/Scripts/python.exe tools/validate_mode4_gui_exports.py --staggered
```

Build `tools/validate_imagelock.cmd` first if the local core validator is absent.
Its local MartyPC source and toolchain prerequisites match the aligned suite.
