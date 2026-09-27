# STARTLCK: mode-4 start-line marker

The bootable disk is **`files/STARTLCK.DSK`** (360 KiB).
The standalone DOS program is **`files/STARTLCK.COM`**.

## Run in MartyPC

Double-click **`STARTLCK Demo.lnk`** or **`run_startlock.cmd`** in the project root to use the separately
built MartyPC 0.5.0 with the test disk already mounted in A:. Alternatively,
mount `files/STARTLCK.DSK` in MartyPC's drive A: and reset the emulated machine.
The disk boots DOS and runs STARTLCK automatically.

The general **`MartyPC Latest.lnk`** now boots this demo disk too. Its previous
plain-DOS configuration is saved as `install/martypc-cga-dos-only.toml`.
Close an already running emulator and launch again to load the changed disk;
an existing window keeps its currently mounted image in memory.

The launcher makes a fresh runtime disk copy, so emulator disk writes do not
change the test image. It uses the existing stock-clock IBM 5160/CGA baseline,
with refresh and wait states enabled, RGBI output and no turbo.

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
- The intended transition is near bitmap row 8. The exact measured coordinates
  are recorded below; the initial delay was not an assumption of exact pixel placement.

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

PIT1 refresh count 19 remains active during the mode-4 acquisition and display.
The steady frame and transitional interval are multiples of 19. The release's
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

## MartyPC results, 2026-09-14

The standalone validation harness executes the unchanged MartyPC core from
commit `05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44`, with an emulated IBM 5160,
640 KiB, GLaBIOS XT 0.2.6, CGA, CPU wait states and DRAM refresh simulation.
It exercises the same PIT-phase adjustment used by the desktop frontend.

| Configured PIT phase | Marker entries observed | Visible red onset | Interval between marker entries |
|---|---:|---|---:|
| 0 | 307 | x=9, y=8 | 79,648 CPU cycles |
| 1 | 307 | x=9, y=8 | 79,648 CPU cycles |
| 2 | 307 | x=9, y=8 | 79,648 CPU cycles |
| 3 | 304 | x=9, y=8 | 79,648 CPU cycles |

Coordinates are zero-based 320x200 image pixels. All marker observations,
including the first, are included. The nine black pixels before the red edge
are visible; a white bitmap mark is not masking the transition. Completed
visible frames match across these phases. The switch back to black occurs
in horizontal blanking and is 16 master dots earlier in phase 3, without
changing the active image. Thus the result establishes the measured marker,
not identical timing of every instruction in all four phases.

An actual BIOS/floppy/DOS boot also ran AUTOEXEC, displayed all 3,600 marker
pulses and returned to the DOS prompt. The interrupt-entry period remained
79,648 cycles throughout. The independent per-phase runs injected the COM
after BIOS initialization; they were not four full floppy boots.

This is a positive emulator result for one startup per configured phase and
one palette pulse. It does not certify all entry states, physical CGA hardware,
or the application's eight-write palette loop. Keyboard input ends or can
perturb a timing run; compare the display before pressing Escape.

Reproducible harness and measurements: `tools/validate_startlock.rs`,
`tools/validate_startlock.cmd`, `tools/validate_startlock.py`, and
`docs/research/startlock_validation.md`. The harness observes instruction
boundaries and rendered pixels; it does not claim an exact electrical latch time.
