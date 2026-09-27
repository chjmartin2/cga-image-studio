# Mode-4 image lock validation — 2026-09-14

The exported Picard image and registration pattern reproduce their expected RGBI pixels exactly in the unchanged MartyPC core. Across **44 tested startups, all 18,052 completed visible graphics frames matched their expected image at every one of the 128,000 displayed CGA clock dots**. The first completed frame is included in every run; no completed graphics frames were discarded.

The test uses MartyPC commit `05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44`, IBM 5160, non-turbo 8088, CGA, GLaBIOS 0.2.6 XT, and normal DRAM refresh simulation. Monitor emulation is enabled; ROM patches and title hacks are disabled. The Marty checkout has no modified core source; its only untracked item at validation was the project's machine configuration.

This is emulator evidence. It does not certify a physical CGA card, every possible hardware startup phase, different CPU speeds, or clone adapters.

## Results

| Test | Startups | Completed visible frames | Result |
|---|---:|---:|---|
| Exported Picard COM | Four PIT settings | 1,225 | Exact expected image in every frame |
| Exported REGLOCK COM | Four PIT settings | 269 | Exact expected registration pattern |
| Independent diagnostic, all four VRAM indices and row-varying palettes | Eight entry delays × four PIT settings | 2,162 | Exact independently calculated image |
| Final boot disk, including automatic DOS return | Four cold boots, one per PIT setting | 14,396 | 3,599 exact frames per boot; all 3,600 raster passes executed |

The independent diagnostic uses entry NOP counts `0, 1, 2, 3, 7, 13, 31, 127`. It exercises VRAM indices 0, 1, 2 and 3 on successive rows, changes background colors by row, and explicitly checks the leading-palette carry from row 199 back to row 0. This catches a shifted internal palette boundary even when the left edge and frame timing remain steady.

Every measured corresponding write on successive raster lines is **304 CPU cycles apart**. Every successive kernel entry is **79,648 CPU cycles apart**. All four disk runs contain exactly **5,760,000 timed palette writes**: 1,600 writes per pass × 3,600 passes. The expected-image comparisons report zero unequal two-dot pixel pairs.

The measured visible palette boundaries are:

```text
0, 33, 73, 113, 169, 201, 241, 281, 320
```

There are seven visible writes per line. The eighth occurs during blanking before the next active row and supplies that row's leading palette. These boundaries apply to all four VRAM indices in the tested configurations; no separate foreground displacement was observed. The final padding arrangement matters: earlier candidates kept a 304-cycle line but moved internal boundaries in some startup configurations. Those candidates are not the delivered kernel.

## What was measured

[validate_imagelock.rs](../../tools/validate_imagelock.rs) links the existing `marty_core` crate without changing it. It records port `3D9h`/`3D8h` OUT instructions and CPU cycles, activates graphics-frame collection at the kernel's first OUT (`CS:1006h`), and compares every completed active image with a separately supplied 320×200 RGBI index buffer. Each expected pixel is compared with both corresponding clock dots in the emulator's 640×200 active aperture.

OUT beam coordinates are sampled at instruction boundaries. They are **not** separately instrumented I/O register-latch timestamps. The visible image and transition positions are independently checked in the completed framebuffer. The active aperture is at master-dot x=192, physical row 38; the seven visible instruction-end x positions are 258, 338, 418, 530, 594, 674 and 754 in these captures.

COM tests run the ROM for 20 million CPU cycles, inject the COM at `1000:0100`, and execute another 30 million cycles for Picard or 11 million for the diagnostics. Each starts a fresh emulated machine. The entry-delay matrix adds NOPs before acquisition; it does not change the timed raster.

Disk tests cold-boot the actual final image and run for 400 million CPU cycles. DOS and AUTOEXEC load the program normally at `0C60:0100`. After the 3,600th raster pass, cleanup switches to text mode before another completed graphics frame is presented; therefore 3,599 completed visible frames per boot are available for comparison. This accounts for the count without discarding a graphics frame.

The phase-0 and phase-3 final screenshots were visually checked: the completion message, instructions to run `IMGLCK` or `REGLOCK`, and the `A:\>` prompt are present. All four runs end in text mode without an emulator error. Keyboard Escape was not exercised by this harness.

## Artifacts and reproduction

- [Actual captured Picard image](../../files/IMGLCK_marty.png)
- [Observed DOS return](imagelock_dos_return.png)
- [Durable result record](imagelock_validation.json), including per-run counts, first-frame records, timing distributions, and file hashes
- [SHA-256 manifest](imagelock_validation.sha256)

Validated final disk SHA-256: `de459c71bb87103cb187a62bdd5915452378169b7b6ef1f5494e2b4c965fbae6`.

Validated Picard COM SHA-256: `e70dd7e75f376b87ae450ca3a29820b5d7e4efad1744eb3d4d9d575ebf51281e`.

Every Picard visible frame has FNV-1a-64 `A1D9A0BF2A4A5D93`. The first and last captured visible images across all Picard COM and disk tests have SHA-256 `9849eea387ea43c9d205ccd933c6e92cf91fe0630c501fbfcfd2896ab507e53d`. This hash is for the 640×200 dot-index buffer, not the expected 320×200 pixel-index file.

From the project directory:

```powershell
0..3 | ForEach-Object {
    cmd /c tools\validate_imagelock.cmd files/IMGLCK.COM $_ 30000000 external/research/imagelock-validation/imglck 1006 files/IMGLCK_expected.bin
    cmd /c tools\validate_imagelock.cmd files/REGLOCK.COM $_ 11000000 external/research/imagelock-validation/reglock 1006 files/REGLOCK_expected.bin
    cmd /c tools\validate_imagelock.cmd files/IMGLCK.DSK $_ 400000000 external/research/imagelock-validation/disk 1006 files/IMGLCK_expected.bin
}
.\.venv\Scripts\python.exe tools/validate_imagelock.py --directory external/research/imagelock-validation/imglck --expected files/IMGLCK_expected.bin
.\.venv\Scripts\python.exe tools/validate_imagelock.py --directory external/research/imagelock-validation/reglock --expected files/REGLOCK_expected.bin
.\.venv\Scripts\python.exe tools/validate_imagelock.py --directory external/research/imagelock-validation/disk --expected files/IMGLCK_expected.bin
```

The [independent calibration generator](../../tools/make_imagelock_calibration.py) accepts a compiled template, an output directory, and the nine measured `--bounds`. It changes palette immediate operands and bitmap data only. The original entry-delay templates and resulting independent expected images are recorded under `external/research/imagelock-validation/index-final/entry*/`.

Large raw CSVs and detailed per-instruction summaries remain under the git-ignored `external/research/imagelock-validation/` directory. The summarizer streams these traces in bounded memory. The durable JSON above keeps the evidence needed to assess the result without adding those large files to the repository.
