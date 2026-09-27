# STARTLCK: mode-4 start-line marker

**Timing validation withdrawn, 2026-09-14.** The original harness left CPU wait
states disabled and therefore also skipped simulated refresh DMA stalls.
Its `(9,8)` marker placement and phase-sweep results do not establish behavior
under the native frontend's settings. The program remains an experimental
artifact requiring corrected measurement. See the
[correction and original counts](research/startlock_validation.md).

The bootable disk is **`files/STARTLCK.DSK`** (360 KiB).
The standalone DOS program is **`files/STARTLCK.COM`**.

## Run in MartyPC

Double-click **`STARTLCK Demo.lnk`** or **`run_startlock.cmd`** in the project root to use the separately
built MartyPC 0.5.0 with the test disk already mounted in A:. Alternatively,
mount `files/STARTLCK.DSK` in MartyPC's drive A: and reset the emulated machine.
The disk boots DOS and runs STARTLCK automatically.

Use the dedicated STARTLCK launcher for this older diagnostic. Other project
shortcuts can select a different disk. Close an already running emulator and
launch again to load the selected disk; an existing window keeps its mounted
image in memory.

The launcher makes a fresh runtime disk copy, so emulator disk writes do not
change the test image. It uses the existing stock-clock IBM 5160/CGA baseline,
requesting refresh simulation and wait states, RGBI output and no turbo.
The original harness did not actually apply the CPU wait-state option.

For separate process starts with all four configured PIT phases:

```text
run_startlock.cmd 0
run_startlock.cmd 1
run_startlock.cmd 2
run_startlock.cmd 3
```

Close the previous MartyPC before each launch. Repeating STARTLCK at the DOS
prompt performs a warm reacquisition; that is different from changing the
emulated power-on phase.

## What to look for

After initialization, the screen has a black background and a white bitmap
ruler. A bright red palette pulse appears near the top. The short side ticks
are spaced eight image lines apart; longer left ticks are 32 lines apart.
Four white dashes identify bitmap row 8. These reference marks do not depend
on the changing background palette. The first 32 pixels of row 8 deliberately
have no white ruler marks, so they cannot conceal a change in the palette edge.

Compare the red pulse's first pixel and row against that same ruler:

- Within one run, it should remain still. Rolling, flickering or changing
  endpoints are evidence of a timing problem.
- After restarting, check both its vertical line and horizontal endpoints.
  A steady pulse in a different place is not repeatable acquisition.
- Bitmap row 8 is the intended reference. The actual marker position must be
  measured again with effective CPU wait states and refresh DMA stalls enabled.

Escape ends the display. It also returns to DOS after 3,600 displayed frames,
approximately 60 seconds. Type `STARTLCK` to repeat. The program restores the
interrupt vectors, PIC mask, speaker control, standard timer/refresh settings,
and text mode on this exit path. It does not account for elapsed DOS clock time.

## What the program tests

The original released Lake instructions from `0182h` through `03FFh` are kept
byte-for-byte at their original offsets. The earlier resource-loading and
artwork setup are replaced by independent DOS setup and the ruler bitmap.

At `0400h` the demo switches to standard 320x200 mode-4 timings and waits for
two fresh VSYNC edges. It then performs an additional mode-4 acquisition:

1. PIT0 count 19,911 advances the IRQ sampling position relative to the
   19,912-tick graphics frame.
2. The probe must observe VSYNC high and then low. It aborts after 256 unsuccessful
   probe entries, rather than claiming convergence.
3. A transitional count of 3,496 targets approximately line 8. A bridge IRQ
   queues the steady 19,912 count, respecting the PIT mode-2 reload pipeline.
4. The marker handler changes background color once per frame and returns it
   after a short fixed instruction sequence. No per-line palette kernel is used.

The code leaves PIT channel 1 programmed to divisor 19 during the mode-4
acquisition and display. This register setting did not make refresh DMA stalls
operate in the original harness: its disabled CPU wait-state option bypassed
that simulation. The steady frame and transitional interval are multiples of 19. The release's
earlier temporary refresh-off acquisition is retained; this is a MartyPC
experiment, not a qualified physical-hardware utility. Its unchanged Lake
polling stages can still stall if the emulated reference acquisition fails.

## Build and verification

```powershell
.venv/Scripts/python.exe tools/build_startlock.py
```

Source: `tools/startlock.asm`. The build requires NASM and the existing
`files/dos_boot_template.dsk`. It refuses to substitute a nonbootable blank disk.
The build verifies the pinned Lake byte range, embedded COM, DOS system files,
boot sector and both FAT copies. `files/STARTLCK.json` records binary/disk hashes.
`files/STARTLCK.lst` supplies instruction addresses for the debugger.

The original demo's compressed assets are not needed to rebuild this test.
The pinned reference comes from the reviewed `docs/research/area5150/lake_initializer.asm`.

## Original MartyPC results are not native timing validation

The original tests reported marker onset `(9,8)` and 79,648-cycle periods across
four PIT settings, with 1,225 matching completed visible frames. A separate disk
boot executed 3,600 marker pulses and returned to DOS. **These results were
measured with CPU wait states disabled and refresh DMA stalls bypassed.** They
must not be used to claim repeatable native timing, effective refresh, or
physical-hardware compatibility.

The [corrected status page](research/startlock_validation.md) retains the old
counts and links to the untouched reports, result JSON, and source audit. The
original report's statements that its harness preserved CGA wait states and
normal DRAM refresh are withdrawn. Successful disk packaging, exact binary
reassembly, and DOS return in that configuration are separate observations.

The [wait-state-enabled validation record](research/imagelock_waitstates_validation.md)
now includes a bounded corrected STARTLCK run: the marker appears at x=25 in PIT
phases 0-2 and x=17 in phase 3, on row 8. It is stationary within a run but fails
the identical-position startup criterion. Corrected full-image results must
not be transferred to this older marker binary.
