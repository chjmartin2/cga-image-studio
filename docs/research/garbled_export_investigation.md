# Converter export discrepancy, 2026-09-14

The user reported a garbled native MartyPC display from the converter while its
preview looked correct. The failure is now **reproduced**: the validation harness
never called `CpuOption::EnableWaitStates(true)`. The 8088 core defaults that
option to false. This also bypasses its DMA refresh simulation because
`tick_dma()` is gated by both wait states and the refresh flag. The native
frontend explicitly enables wait states from its configuration.

Changing only this missing option reproduces the user's smeared image. The old
kernel's corresponding writes on successive rows are 331-338 CPU cycles apart,
instead of 304, while the outer frame timer still repeats at 79,648 cycles.
The old COM differs from its intended picture at 78,398 dots per frame in phases
0-2 and 78,050 in phase 3. These results explain why a stationary screen and a
passing outer marker did not establish correct inner palette timing.

Earlier emulator tests below ran with wait states and effective DMA refresh
disabled. Their claims of validating the normal desktop configuration are
withdrawn. The conversion/packing comparisons remain useful, but do not prove
raster timing. Retiming with explicit, asserted CPU options is in progress.

The reported file is `C:\Users\chjmartin2\Desktop\CGAFUN\cga_320_startlock.dsk`.
Its `TEST.COM` contains the current acquired mode-4 backend, with exactly the
same instruction bytes as the delivered template. Only the permitted palette
operands and VRAM differ. The COM SHA256 is
`5ffd2e5ef829ae7d4b25d9aeced1b262ad8e21aa5db47d8b5078b1d53b264968`.

An independently reconstructed [intended image](../../files/EXPORT_TEST_preview.png)
from those operands and VRAM matches the [actual core capture](../../files/EXPORT_TEST_marty.png).
Testing included:

- The exact extracted COM across four PIT phases: 269 complete frames, no differing dots.
- Cold boots of the exact unchanged user disk, followed by Model F keyboard
  input of `TEST` and Enter: 626 complete frames across four PIT phases, no differing dots.
- Seventeen additional reentry, launch-delay and execution-batch cases: 4,843
  complete frames, no differing dots. These included up to five prior STARTLCK runs.
- Actual GUI conversion and disk-export methods through twelve combinations
  of dithering, dither-aware optimization and border settings. Decoded disk
  contents matched all 64,000 preview pixels in each case.

The selected ROM definition has no ROM patches; the title-hacks flag is stored
but unused in this core. Those two configuration differences do not explain the
failure. The running native executable's SHA256 matches the previously built
MartyPC executable. The saved baseline has turbo disabled and refresh and wait
states enabled; this does not reveal settings changed inside the running UI.

The export was rewritten at 21:44:30, after the observed MartyPC process started
at 21:44:15. A fresh disk/session was tested with the user and was still garbled;
the earlier mounted-image hypothesis did not resolve the failure.

`Test My CGA Export.lnk` now invokes `run_cga_disk.cmd` with the reported disk.
Each launch makes a fresh runtime copy, verifies the exact COM, changes only
AUTOEXEC to start TEST, and uses the documented IBM 5160/CGA settings. The
original Desktop export is unchanged. The user confirmed that this fresh launch
was still garbled. A corrected kernel must now pass the harness with actual
wait states and refresh enabled, then be retested in the native application.

The launcher can also be used with later exports:

```powershell
.\run_cga_disk.cmd "C:\path\to\export.dsk"
```

[Machine-readable findings](garbled_export_investigation.json) record hashes and
counts. Raw immutable inputs, independent previews and isolated harness results
are under the ignored `external/research/garbled-export/` and
`external/research/imagelock-reentry/` directories. The earlier validated kernel,
Picard disk and original validation tools remain unchanged.
