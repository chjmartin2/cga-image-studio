# Acquired mode-4 image kernel

The source is [`tools/imagelock.asm`](../../tools/imagelock.asm). It extends the
STARTLCK experiment into a 200-line raster with seven visible palette changes per
line and one blanking write that prepares the following line. The image remains
ordinary CGA mode 04h: 320 x 200, two stored bits per pixel. Colors come from the
palette active while each region is scanned. This does not provide an independent
choice among 16 colors for every pixel.

This kernel has passed the described tests in the current, unmodified MartyPC
core. These are emulator observations, not physical-hardware measurements or a
proof covering every IBM CGA revision, clone, processor, or startup state.

## Acquisition and handoff

1. DOS setup selects BIOS mode 04h, copies the supplied 16 KiB framebuffer, saves
   the interrupt vectors, PIC mask, and speaker-control value, and masks all PIC
   interrupts except the timer.
2. COM addresses `0182h..03FFh` contain the reviewed released Lake acquisition
   bytes unchanged. The required absolute data locations and stack arrangement
   are preserved. The Lake initializer ends with PIT channel 1 refreshing at a
   divisor of 19. Its temporary write near the end of CGA memory is outside the
   active mode-4 bitmap.
3. At `0400h`, the new handler programs standard mode-4 CRTC geometry and waits
   for two fresh VSYNC edges. PIT channel 0 then runs at 19,911 ticks, one tick
   shorter than the 19,912-tick graphics frame. A fixed-position timer-handler
   status read walks toward the end of VSYNC. Acquisition requires observing a
   high status before accepting a low status; a 256-probe limit returns to DOS
   on failure.
4. The two subsequent handlers account for PIT mode-2 reload timing. The acquired
   handler queues 2,888 ticks, corresponding to 38 scanlines. The bridge queues
   the steady 19,912-tick frame period and points IRQ0 at `1000h`. It installs the
   first line's leading palette before the first raster starts.
5. Each frame's interrupt executes 200 unrolled rows, services the keyboard and
   frame limit afterward, sends the PIC end-of-interrupt, resets the working
   stack, then enables interrupts and waits in HLT for the next frame.

The steady raster leaves PIT channel 1 at 19. It does not disable refresh or
reprogram the refresh phase in the bridge. An experimental bridge reprogram did
not resolve the observed inner-boundary differences and is absent from the
final source.

## Why the marker test was insufficient

STARTLCK established a repeatable first visible transition. An initial image
kernel reproduced that transition and had an exact 304-CPU-clock line period,
yet some inner palette changes differed by eight pixels between startup states.
The first marker alone did not establish a common position for every later OUT.

With two NOPs between all seven visible writes, the initial four-PIT-phase test
gave inner boundaries at `153,193,233` in three cases and `145,185,225` in the
fourth. Moving two NOPs from blanking into the middle corrected those four runs,
but broader entry-delay tests exposed another difference at the fourth boundary.
The final schedule delays only that fourth write by one additional NOP and
shortens the following gap by one NOP. Total row duration and all other final
boundaries stay unchanged.

The accepted NOP schedule is:

| Position | NOPs |
|---|---:|
| Before the first visible write | 4 |
| After visible writes 1 through 6 | 2, 2, 5, 1, 2, 2 |
| Between visible write 7 and the blanking write | 16 |
| After the blanking write | 6 |
| Total per row | 40 |

Each row also contains eight `MOV AL,imm8` / `OUT DX,AL` pairs, with DX held at
`03D9h`. A row occupies exactly 64 code bytes. Runtime image construction patches
only the immediate operands; it does not introduce data loads, branches, or
different instruction encodings into the raster.

Measured instruction-completion intervals between the eight writes and the next
row's first write are `26,26,38,22,26,26,82,58` CPU clocks, totaling 304. These
intervals come from execution, not a sum of nominal instruction-table costs.
Instruction completion is not asserted to be the exact electrical register-latch
instant. Independent checks of the actual rendered RGBI pixels establish the
visible boundaries below.

## Palette and pixel ownership

The measured boundaries in 320-pixel image coordinates are
`0,33,73,113,169,201,241,281,320`.

| Pixels on row y | Palette source |
|---|---|
| `[0,33)` | Previous row's blanking write; bridge value on the first frame |
| `[33,73)` | Row y, visible write 1 |
| `[73,113)` | Row y, visible write 2 |
| `[113,169)` | Row y, visible write 3 |
| `[169,201)` | Row y, visible write 4 |
| `[201,241)` | Row y, visible write 5 |
| `[241,281)` | Row y, visible write 6 |
| `[281,320)` | Row y, visible write 7 |

The eighth write occurs in blanking before the following active line. The
exporter must give row 199's eighth write the same value as row 0's leading
palette, or subsequent frames will start with a different palette from the first
frame. The converter, preview, framebuffer indices, and emitted immediate values
must all use this same region ownership.

The calibration observed the same transition positions for framebuffer indices
0, 1, 2, and 3. Foreground-index palette changes did not need a different preview
boundary from background-index changes in the tested emulator configuration.

## Binary layout and patch contract

All code addresses below include the DOS COM origin of `0100h`; subtract `0100h`
to obtain a file offset.

| COM address | Purpose |
|---|---|
| `0100h` | Jump to DOS setup |
| `0182h..03FFh` | Unchanged released Lake acquisition bytes |
| `0400h` | Mode-4 CRTC handoff |
| `0500h` | Mode-4 VSYNC-edge probe |
| `0600h` | Timer reload bridge; leading palette operand at `0618h` |
| `0900h` | DOS setup and framebuffer copy |
| `0C00h` | Cleanup and DOS return |
| `0E00h` | Saved state, counters, CRTC table, and messages |
| `0F00h` | `IMGLK001` template descriptor |
| `1000h..41FFh` | 200 raster rows; first OUT at `1006h` |
| `4200h` | Post-raster keyboard polling and frame completion |
| `45C6h` | Sample-segment compatibility word read by Lake's final handler |
| `45E4h..45E9h` | Preserved Lake timing defaults `13FDh,0045h,0000h` |
| `8000h..8C7Fh` | 1,600 little-endian palette-operand file offsets |
| `A000h..DFFFh` | Embedded 16 KiB CGA framebuffer |
| `EC94h` | Working stack top and acquisition scratch area |

The COM file is 57,088 bytes. It ends at `DFFFh`, below the working stack. The
descriptor starts at file offset `0E00h` with eight ASCII magic bytes, followed
by twelve little-endian 16-bit words:

1. Framebuffer file offset.
2. Palette-offset-table file offset.
3. Palette operand count, 1,600.
4. First-frame leading-palette operand file offset.
5. Runtime frame-counter variable file offset.
6. Raster entry file offset.
7. Raster end file offset, exclusive.
8. Total NOPs per row.
9. Leading NOP count.
10. Base inter-write NOP count.
11. NOP count after the blanking write.
12. Initial image delay in PIT ticks.

The descriptor does not encode every internal gap. The reviewed template hash
and emitted instruction bytes identify this schedule; changing the template
requires revalidation. Every palette-table entry points to the immediate byte
between opcodes `B0h` and `EEh`. The frame-counter field alone does not set the
test's duration: startup reloads the `DISPLAY_FRAMES` assembly constant.

## Validation and limitations

The final diagnostic exercised eight pre-acquisition entry delays—0, 1, 2, 3, 7,
13, 31, and 127 NOPs—at each of the four MartyPC PIT phase settings. Local timing
captures measured 154,421 adjacent-row intervals of exactly 304 CPU clocks and
754 frame intervals of exactly 79,648 CPU clocks. Their 754 completed diagnostic
frames had the same visible framebuffer hash. Raw results are in
`external/research/imagelock-kernel-entry2/`.

An independent image validator then exercised the same 32 configurations with
varying framebuffer indices and row palettes. All 2,162 completed frames
matched its expected RGBI image at every dot, including the first frame and
row-199-to-row-0 palette carry. It also checked that each pair of horizontal
master-clock dots represented one consistent 320-mode pixel. Raw calibration
results are in `external/research/imagelock-validation/index-final/`.

During display, IRQ1 is masked and the keyboard latch is polled and acknowledged
only after the 200-line raster. Escape returns to DOS; the default limit is 3,600
displayed frames. The routine resets its stack each frame rather than returning
through accumulated interrupt frames. Cleanup restores saved IRQ vectors, the
PIC mask and speaker control, the standard refresh divisor of 18, the BIOS timer
divisor of 65,536, and text mode. BIOS timekeeping does not advance normally
while its timer handler is replaced. The program does not preserve an arbitrary
preexisting graphics mode or another program's custom PIT programming.

Successful real-image comparison in MartyPC, repeated DOS launches, disk boot,
and the same tests on the intended physical machine remain distinct checks.
The results above establish the kernel's tested emulator behavior; they should
not be described as physical CGA certification.
