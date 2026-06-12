# CGA Lockstep Milestone

## Goal

Place more than one CGA color-select write (`OUT 03D9h,AL`) on each scanline
with repeatable horizontal positions. The immediate lab case is two writes per
line in BIOS mode `04h`.

## Proven Structure

The stable test is preserved in `cgalk5.asm` and reproduced without NASM by
`generate_cgalk5_test.py`.

The timing-critical region:

1. Synchronizes once per frame using CGA status port `03DAh`.
2. Programs PIT channel 1 refresh count from BIOS default `18` to `19`.
3. Disables interrupts with `CLI`.
4. Emits 200 fully unrolled scanline blocks with no per-line polling.
5. Restores interrupts and checks for an `ESC` keypress between frames.
6. Restores PIT channel 1 to `18` before returning to DOS.

Each line block is:

```asm
times LEAD nop
mov al,B1
out dx,al
times MID nop
mov al,B2
out dx,al
times TAIL nop
```

The empirically stable baseline is:

```text
LEAD = 36
MID  = 15
TAIL = 10
SUM  = 61 NOPs
```

## Measured Facts

- Standard mode-04h CGA scanline: `912` dots = `304` CPU cycles.
- PIT refresh clock: `76` PIT ticks per scanline.
- BIOS refresh count `18` precesses relative to the raster.
- PIT refresh count `19` gives `76 / 19 = 4` refreshes per scanline at a
  repeating phase.
- Per-line status polling did not produce stable mid-line seams.
- Frame-level lockstep plus PIT count `19` produced stable seams.
- Empirical drift tuning:

| Total NOPs | Observed drift |
| --- | --- |
| 88 | approximately `+336` beam dots per line |
| 51 | approximately `-128` beam dots per line |
| 61 | approximately zero steady-state drift |

At `LEAD=36`, the first several `03D9h` breakpoints clustered around two seam
positions near beam-x `480` and `745`, with a small startup transient and
approximately `16`-dot residual shifts.

At constant `LEAD=42`, `MID=15`, `TAIL=4`, the breakpoint sequence settled to
stable positions after a short transient:

```text
674, 18, 674, 2, 658, 2, 658, 2, 658, 2, 658
```

The sequence alternates `OUT#1`, `OUT#2`; the second write wraps near the next
line origin.

## Placement Test Result

The same `61`-NOP total remains locked when the write position moves much
earlier in the line. The decisive constant-position probe used:

```text
LEAD = 6
MID  = 15
TAIL = 40
SUM  = 61 NOPs
```

MartyPC IO breakpoint `3D9` produced:

```text
scanline 25: OUT#1 162, OUT#2 418
scanline 26: OUT#1 162, OUT#2 418
scanline 27: OUT#1 162, OUT#2 418
scanline 28: OUT#1 162, OUT#2 402
scanline 29: OUT#1 146, OUT#2 402
```

An initial short sample looked stable, but a longer sample showed repeated
leftward phase steps:

```text
scanline 30: OUT#1 146, OUT#2 402
scanline 32: OUT#1 130, OUT#2 386
scanline 37: OUT#1 114, OUT#2 370
scanline 41: OUT#1  98, OUT#2 354
```

Conclusion: `LEAD=6`, `MID=15`, `TAIL=40` is close to lock but not locked. The
seams step left by `16` dots every few lines. Across the longer sample, `OUT#1`
moved from beam-x `162` on scanline 25 to beam-x `98` on scanline 41:
approximately `-4` dots per line on average. `OUT#2` follows the same trend.

This revives the placement-sensitive timing hypothesis. Moving NOPs between
`LEAD` and `TAIL` can move seams horizontally, but the exact lock point may
also depend on where the writes land relative to refresh, prefetch, or CGA
I/O wait-state phases.

## Next Refinement

Investigate the residual repeated `16`-dot notches. Since both writes trend
together, the remaining effect is primarily a line-level phase drift rather
than unstable spacing between the palette writes.

1. Repeat with `LEAD=5`, `TAIL=41` and `LEAD=7`, `TAIL=39`, preserving the
   `61`-NOP total, to test whether moving `OUT#1` off the current phase
   boundary changes the average drift.
2. If neither placement locks, test a `62`-NOP total. The measured `LEAD=6`
   drift is negative, so the line cadence is slightly short on average.
3. If a whole extra NOP overcorrects, replace padding with a finer-grained
   deterministic instruction sequence and tune by fewer than three cycles.

## Entry-Phase Issue

The current `cgalk5` acquisition sequence has an important top-of-screen
limitation:

```asm
.act:   in      al,dx
        test    al,01h
        jnz     .act
.blk:   in      al,dx
        test    al,01h
        jz      .blk
        cli
        mov     dx,COLSEL
```

After VSYNC begins, `.act` waits for the first active scanline and `.blk` waits
for that same scanline to end. The first unrolled palette-write block therefore
starts in the horizontal blank *after* visible line 0. Visible line 0 is drawn
using an inherited `03D9h` value from the prior frame and cannot contain the
expected two timed palette changes.

The first generated block also follows a one-off polling/prologue path
(`IN`/`TEST`/branch loops, `CLI`, `MOV DX`) instead of another identical
scanline block. Its prefetch and refresh phase differs from the eventual
steady-state body. Screenshots show a top-of-screen staircase that converges
into a vertical seam, consistent with this entry transient.

Do not treat those early-line notches as proof of a globally short line cadence
until entry management is fixed. A proper next architecture should:

1. Acquire vertical phase early enough to operate during top blanking.
2. Run throwaway blocks with the same cadence as real lines to settle refresh
   and prefetch phase.
3. Enter visible line 0 directly from an identical preceding cadence block,
   without a poll-loop or prologue discontinuity at the boundary.
4. Include an explicit full-frame schedule so the next frame does not recreate
   the entry transient.

## CGALK6 Pre-Roll Result

`cgalk6_preroll.asm` implements the vertical-blank pre-roll architecture:

```text
VSYNC rising edge
-> 38 invisible same-cadence blocks
-> 200 visible same-cadence blocks
```

The 38-line count comes from the standard mode-04h frame geometry:

```text
262 total scanlines - VSYNC start at line 224 = 38 scanlines
```

The test body uses:

```text
LEAD = 6
MID  = 15
TAIL = 40
SUM  = 61 NOPs
```

Visual result in MartyPC: the complete active 320x200 image is stable from its
first visible row, with two clean vertical seams (`gray / brown / gray`). The
startup staircase remains visible only in overscan before the active image.
This confirms that the old top-of-image staircase was caused by entry-phase
settling after the polling/prologue path, not by an inherent inability to
place stable mid-line `03D9h` writes.

Preserved files:

```text
cgalk6_preroll.asm
generate_cgalk6_preroll_test.py
files/CGALK6.COM
files/CGALK6.map.csv
files/marty_work_cgalk6.dsk
```

## CGALK7 And CGALK8 Degrees Of Freedom

Two follow-up probes established which in-line timing controls remain usable
while preserving the lockstep cadence.

### CGALK7: Alternating Offset

`cgalk7_alternating.asm` alternates the NOP distribution:

```text
phase A: LEAD=4, MID=15, TAIL=42
phase B: LEAD=8, MID=15, TAIL=38
```

Both phases preserve `61` total NOPs and the same two `MOV`/`OUT` pairs. The
MartyPC result is stable and produces a deterministic horizontal walk/wrap
pattern. This proves that moving NOPs between `LEAD` and `TAIL` can translate a
fixed-width palette band while keeping the line cadence locked.

### CGALK8: Alternating Width

`cgalk8_width.asm` keeps the first seam timing constant and alternates the
second seam timing:

```text
phase A: LEAD=6, MID=11, TAIL=44
phase B: LEAD=6, MID=19, TAIL=36
```

Both phases again preserve `61` total NOPs and the same two `MOV`/`OUT` pairs.
The MartyPC result shows a fixed left edge and an alternating right edge on
adjacent rows. This proves that band width is independently controllable by
moving NOPs between `MID` and `TAIL`.

Together, the probes establish two useful controls for the two-write profile:

```text
offset = LEAD
width  = MID
TAIL   = 61 - LEAD - MID
```

Constraints:

```text
LEAD >= 0
MID  >= 0
TAIL >= 0
```

The pattern must also be emitted during the 38-line pre-roll with matching
phase so visible line 0 enters from the intended preceding cadence block.

## CGALK9 Palette-Value Stress Test

`generate_cgalk9_palette_random_test.py` isolates whether changing palette
register values affects lockstep stability:

1. It embeds a deterministic 16 KB pseudo-random bitmap in the COM file.
2. It copies that bitmap to CGA VRAM before the timing-critical loop begins.
3. It retains the proven fixed geometry:

```text
LEAD = 6
MID  = 15
TAIL = 40
SUM  = 61 NOPs
```

4. It bakes varying `MOV AL,imm8` values into every pre-roll and visible line.
5. It exercises all 64 standard mode-04h `03D9h` combinations across visible
   lines: background bits `0..3`, intensity bit `4`, and palette-family bit `5`.
6. It does not write `03D8h` inside the raster loop and does not use tweaked
   mode `05h`.

Preserved files:

```text
generate_cgalk9_palette_random_test.py
files/CGALK9.COM
files/CGALK9.map.csv
files/marty_work_cgalk9.dsk
```

MartyPC visual result: the random bitmap renders with heavy palette variation,
but the two active-area seam columns remain stable and vertical. Palette byte
values are therefore timing-neutral when baked into the same immediate
`MOV AL,imm8` / `OUT DX,AL` skeleton. Standard mode-04h palette/background
changes may be selected independently per generated line without disturbing
lockstep timing.

## CGA Studio v166 Integration

`cga_v166.py` integrates the proven profile as the production two-write
320x200 Mode Switch exporter:

1. Mode Switch writes per scanline are restricted to `1` or `2`.
2. The `2`-write profile uses PIT channel 1 count `19`, VSYNC rising-edge
   acquisition, `38` invisible pre-roll blocks, and `200` visible unrolled
   blocks with no per-line polling.
3. Quantization models the actual three visible zones:

```text
left   = prior line's final palette
middle = OUT #1 palette
right  = OUT #2 palette
```

4. `OUT #2` is selected by scoring both the current line's right zone and the
   next line's inherited left zone.
5. The optional `Keep border black after final Mode Switch write` control
   restricts `OUT #2` background bits to zero. This keeps overscan black at the
   cost of constraining both the right zone and the next line's left zone.
6. Tweaked mode-05h palettes are disabled for the two-write profile because
   their additional `03D8h` write would alter the tested cadence.
7. The former stagger selector is now a set of deterministic lockstep patterns:

```text
Horizontal Striped
Staircase
Alternating
Dispersed
```

## Final Preview Calibration

The stable lockstep COM cadence and the preview model were validated separately.
The initial preview geometry was provisional; a diagnostic image and MartyPC
capture established the physical active-area boundaries for the baseline:

```text
LEAD = 6
MID  = 15
TAIL = 40

left zone   = x 0..144
middle zone = x 145..272
right zone  = x 273..319
```

The v166 preview quantizer and COM exporter now share those calibrated
boundaries. A second MartyPC capture of the bootable diagnostic DSK matched the
regenerated 320x200 source image exactly: `64,000 / 64,000` pixels.

## Experimental N=3 Profile

The next fixed selector extends the same frame-level lockstep structure to
three `03D9h` writes per scanline. Its first calibration pass used this
provisional profile:

Initial profile:

```text
LEAD = 0
GAP1 = 0
GAP2 = 0
TAIL = 48
SUM  = 48 NOPs

estimated seams = x 121, 189, 257
```

The initial COM uses PIT channel 1 count `19`, VSYNC rising-edge
acquisition, `38` same-cadence pre-roll lines, and `200` visible unrolled
blocks. Three writes create four visible zones because the final write on the
prior line remains active at the left edge of the next line.

Generate the calibration disk:

```powershell
.\.venv\Scripts\python.exe generate_cgalk10_n3_test.py
```

The first `TEST.COM` capture showed stable but incorrect seven-line phase
precession: the three seams walked left by approximately `56` logical pixels
per scanline. The `48`-NOP baseline is therefore too short. The next generated
bootable disk retains `TEST.COM` for reference and contains `N3T56.COM` through
`N3T64.COM`; test `N3T60.COM` first. N=3 remains restricted to
`Horizontal Striped` until the stable cadence and physical seams are measured.

Final CGALK10 calibration:

```text
N3T57.COM

LEAD = 0
GAP1 = 0
GAP2 = 0
TAIL = 57
SUM  = 57 NOPs

left zone = x 0..112
zone 1    = x 113..136
zone 2    = x 137..168
right zone = x 169..319
```

The MartyPC capture showed seams at `x=113`, `x=137`, and `x=169` on all
`200` visible scanlines. The production v166 N=3 encoder now uses this cadence
and these measured preview boundaries.

## Workflow

Generate a probe:

```powershell
.\.venv\Scripts\python.exe generate_cgalk5_test.py `
  --lead 6 --mid 15 --tail 40 `
  --out files\CGAL06.COM `
  --map-out files\CGAL06.map.csv
```

Create a bootable DOS floppy image containing it as `TEST.COM`:

```powershell
.\.venv\Scripts\python.exe tools\make_marty_disk.py `
  --source files\CGAL06.COM `
  --output files\marty_work_cgal06.dsk `
  --name TEST.COM
```
## CGALK11 dense standard-palette boundary test

The calibrated N=2 and N=3 profiles measure the cost of one additional
standard mode-04h `mov al,imm8 / out dx,al` palette write as four NOPs while
preserving the scanline lock:

```
N=2: 61 total NOPs
N=3: 57 total NOPs
```

The resulting low-density extrapolation is `total_nops = 69 - 4*N`. Its last
non-negative candidate is N=17 with one tail NOP. N=18 would need negative
padding. This is a search bound, not a claim that dense CGA I/O remains
cycle-equivalent: wait-state and prefetch behavior may consume additional
frame time as writes are packed closer together.

`generate_cgalk11_dense_test.py` emits `TEST.COM` for the N=17/T=1 candidate
and includes N=3 through N=17 predicted-cadence variants on one bootable disk,
plus nearby N=17 controls and an intentionally over-budget N=18 probe.

## CGALK12 N=11 dense-write tuning

The CGALK11 bracket disk showed that `N10T29.COM` is frame-stable while
`N11T25.COM` blinks and its seam positions wobble. Eleven writes are not yet
ruled out: the low-density NOP extrapolation can overestimate the remaining
padding once CGA I/O writes are densely packed.

`generate_cgalk12_n11_tuning_test.py` holds N=11 constant and sweeps tail
padding downward. The generated boot disk includes even tail values from 0
through 24 plus the known-overlong T=25 control.

MartyPC testing found `N11T18.COM` stable with vertically aligned seams.

## CGALK13 N=12 dense-write tuning

With eleven writes proven, `generate_cgalk13_n12_tuning_test.py` holds N=12
constant and sweeps every tail-NOP value from 0 through 21. `TEST.COM` starts
at T=15, which preserves the 51-byte per-line instruction-stream size of the
stable N11T18 profile.

MartyPC testing found `N12T14.COM` stable with vertically aligned seams. Its
twelve scheduled writes produce about eight visible active-picture regions;
the remaining writes land in horizontal blanking or border time.

## CGALK14 N=13 dense-write tuning

With twelve writes proven, `generate_cgalk14_n13_tuning_test.py` holds N=13
constant and sweeps every tail-NOP value from 0 through 14. `TEST.COM` starts
at T=11, preserving the 50-byte per-line instruction-stream size of stable
N12T14.

MartyPC testing found `N13T10.COM` stable with vertically aligned seams. Its
diagnostic image exposed two visual-quality issues rather than timing issues:
all ten spare NOPs followed the last write, and the four-selector repeating
test sequence made OUT #13 equal OUT #1 on the next line.

## CGALK15 N=13 equal-band phase sweep

`generate_cgalk15_n13_equalbands_test.py` preserves the proven N13T10 line
budget while distributing the ten NOPs across the thirteen circular write
intervals. It also uses a wrap-safe selector sequence where every adjacent
write changes color. A one-time pre-roll delay sweeps the locked horizontal
phase without changing any per-line cadence.

MartyPC testing found phase `E13P06.COM` removes the leading carry-over sliver,
but its final visible band remains clipped. The globally balanced interval
distribution still spends the three unavoidable zero-NOP intervals inside the
active picture.

## CGALK16 N=13 equal visible bands

`generate_cgalk16_n13_visiblebands_test.py` keeps the proven P06 phase and
groups the three zero-NOP intervals into one circular block. Thirteen variants
rotate that block around the scanline. The preferred rotation should place the
short block in horizontal blanking, leaving the ten one-NOP intervals in the
active picture.

MartyPC testing showed that the grouped-gap rotations remove edge slivers but
make several interior column widths worse. The best base remains the dispersed
gap `E13P06.COM` profile from CGALK15.

## CGALK17 N=13 fine phase sweep

`generate_cgalk17_n13_finephase_test.py` restores the dispersed-gap N13T10
profile and sweeps its one-time pre-roll delay from P02 through P08 at
single-NOP resolution. This tunes the active-picture edge clipping without
changing the proven per-line cadence or its interior gap distribution.

MartyPC testing found `F13P07.COM` the closest N=13 result, but its visible
widths remain imperfect because three of the thirteen circular intervals must
omit a NOP. Moving to nine visible bands allows a more uniform layout.

## CGALK18 N=12 nine equal visible bands

`generate_cgalk18_n12_ninebands_test.py` returns to the proven N12T14 cadence.
Twelve circular intervals receive one NOP each, and the two remaining NOPs are
grouped into a longer two-interval block. Variants rotate that block near the
scanline wrap and sweep the horizontal phase. The preferred profile should
hide both longer intervals in blanking and leave nine active-picture intervals
with identical instruction spacing.

## CGALK19 measured trace anchor

A MartyPC `CycleText` capture of stable `F13P07.COM` confirms that the dense
emitter repeats every 304 CPU cycles exactly. Its thirteen measured write-to-
write intervals are:

`23, 27, 19, 23, 28, 23, 23, 24, 23, 23, 26, 19, 23`

This explains why distributing NOPs evenly does not produce evenly spaced
visible bars: CGA I/O waits, DRAM refresh, DMA, and prefetch effects alter the
real instruction timing. Nominal opcode-cycle arithmetic is a useful starting
bound, but final placement must use measured write-completion timestamps.

`generate_cgalk19_trace_anchor_test.py` builds a trace-specific boot disk.
`TEST.COM` and `TRACE.COM` retain the proven F13P07 emitter, then sample the
CGA status register after vertical retrace and after the first active-display
interval begins. Waiting for VSYNC clear alone is insufficient because VSYNC
ends several scanlines before vertical blanking does. `STABLE.COM` is the
unmodified F13P07 reference. The added status samples expose the horizontal
display-enable edge in a MartyPC trace so each palette write can be classified
as a visible seam, a left-edge setup write, an invisible blanking write, or a
black-border reset candidate.

## CGALK20 measured black-border schedule

The corrected CGALK19 trace classifies the stable F13 cadence precisely. At
`P07`, slots `#9` through `#4` complete during active display and slots `#5`
through `#8` complete during horizontal blanking. The circular schedule
therefore provides nine visible seams and ten visible regions per scanline,
plus four blanking writes that must remain in place to preserve the proven
304-cycle cadence.

`generate_cgalk20_border_schedule_test.py` reassigns those four blanking slots
to black-background selectors. Slot `#5` resets the right border and slots
`#6` through `#8` preserve black during blanking while preparing the inherited
left-edge selector for the next scanline. The test sweeps `P04` through `P07`;
visual testing selected `B13P07.COM` as `TEST.COM`. At `P07`, slot `#5` is
hidden in right-side blanking while the visible regions make better use of
the active width. Slot `#9` keeps the same upper selector bits but clears its
background nibble from `04h` to `00h`, preventing a narrow red strip in the
left border without changing its active-pixel palette or instruction timing.

The border schedule also emits one untimed `00h` selector immediately after
the 200-line locked region. Without that post-frame reset, the final active
selector remains latched during the vertical border and produces a colored
band below the image until the next frame begins.

The 38 warm-up scanlines use the same upper selector bits and identical
instruction cadence, but clear each background nibble to zero. This preserves
the preroll timing while keeping the top vertical border black.

The physical raster schedule is circular: source-block slots `#9` through
`#13` paint the beginning of a scanline and the next block's slots `#1`
through `#4` paint its end. Stopping immediately after a complete source block
therefore truncates the final physical scanline. A five-write drain tail emits
the next block's slots `#1` through `#5`, finishing the picture and performing
the normal black reset in horizontal blanking.

## CGALK21 dispersed seams

`generate_cgalk21_disperse_test.py` keeps the CGALK20 role assignment, P07
phase, black preroll, post-frame reset, and five-write drain tail. Each line
still emits exactly thirteen selectors and ten NOPs. Its variants rotate the
three omitted NOP positions around the circular interval schedule:

- `FIXED.COM`: the CGALK20 reference with the last-line drain fix
- `ALTER.COM`: alternate two interval layouts each scanline
- `STAIR.COM`: advance the interval layout every two scanlines
- `DISP.COM`: use a deterministic thirteen-line dispersed sequence

These variants test whether repeatable per-line seam movement reduces visible
vertical striping while retaining stable frame lock and black borders.

## CGALK22 constrained dispersion and vertical-end sweep

CGALK21 established that arbitrary circular interval rotation is too broad:
it can move non-black active selectors into horizontal blanking and color the
side borders. Its five-write drain-tail experiment also failed to remove the
single-line bottom artifact.

`generate_cgalk22_safe_disperse_test.py` separates the two questions. Four
fixed-layout variants sweep 199 or 200 repeated blocks with or without the
five-write drain tail: `V199N.COM`, `V199D.COM`, `V200N.COM`, and `V200D.COM`.
MartyPC testing selected `V199D.COM`: 199 complete blocks followed by a
five-write drain tail. The drain replaces block 200 rather than following it.
It finishes the final physical raster line cleanly without painting a border
scanline.

The final constrained pattern variants keep the blanking interval group
byte-for-byte unchanged. They redistribute omitted NOPs only within the two
active interval groups on either side of the source-block boundary, preserving
the nominal phases of slot `#5` right-border reset and slot `#9` left-edge
setup. `ALTER.COM`, `STAIR.COM`, and `DISP.COM` all use the selected
199-block-plus-drain ending.

`BDISP.COM` tests the broader dispersion pattern again, but with every
selector's background nibble cleared. This sacrifices non-black color-0 use in
exchange for allowing much larger seam movement without coloring the borders.
