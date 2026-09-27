# AREA 5150: released binary disassembly and CGA acquisition

Analyzed 2026-09-14. **The released Lake effect contains automatic timing acquisition, and its observed initializer matches the published IBM 5150 hardware capture.** This is stronger evidence than the previously examined 2017 experimental `lake.asm`. We now have the released machine code, its loader contract, and a successful recorded acquisition using its default parameters.

This corrects the earlier implication that Lake only offered a manually tuned experiment. The 2017 source has manual controls; the 2022 released initializer is a separate, automatically advancing implementation. It is the appropriate reference for the next experiment. Its success on the recorded machine does not yet establish identical palette edges across every power-on phase in this project's mode-4 renderer.

## What was downloaded and recovered

The [author-submitted Pouet entry](https://www.pouet.net/prod.php?which=91938) points to the [Oldskool release archive](http://archives.oldskool.org/pub/misc/area5150.zip). The downloaded NFO identifies this as the **August 2022 party version**, with a final version intended later. No later final was identified in the release listings inspected.

- Local package: `external/research/area5150/area5150.zip`, 484,846 bytes, 64 files.
- ZIP SHA-256: `acc37410944e52a111ebb7028ebd9a3233daa9454e8761c3f4fa99ae613a2be5`.
- Main launcher: 4,674 packed bytes, 22,872 unpacked bytes.
- `LAKE.COM`: 21,631 packed bytes, **60,050 unpacked bytes**.
- All 29 executable modules use ZX0 v2 compression and were unpacked successfully.

An independent check executed only the release's original decompression routine in isolated Unicorn memory. Every module matched the Python decoder byte-for-byte, with identical output lengths and consumed input. That check validates unpacking, not CGA timing. See [unpacking method and hashes](UNPACKING.md).

The files with `.COM` extensions are not all standalone DOS applications. Lake depends on the launcher and its already loaded audio resources. The [loader analysis](LOADER.md) establishes entry at `CS:0100h` and identifies `INT F0h/AH=0Ch` as a resource lookup. Those calls do not calibrate the PIT or CGA. The released script does not patch Lake's timing constants.

## Disassembly artifacts

All addresses below are runtime offsets at COM origin `0100h`; subtract `0100h` for an unpacked-file offset. Analytical comments and labels are newly assigned, not the author's original source.

| Artifact | Purpose |
|---|---|
| [lake_initializer.asm](lake_initializer.asm) | Annotated 768-byte initializer, `0100h` through `03FFh`; begin here. |
| [Full LAKE assembly](../../../external/research/area5150/disassembly/LAKE.asm) | Complete 60,050-byte module, with decoded code comments and explicit data bytes. |
| [Readable LAKE code listing](../../../external/research/area5150/disassembly/LAKE.code.lst) | Addresses, bytes, instructions and explanatory annotations through `45BCh`. |
| [Loader listing](loader.linear.asm) | Launcher disassembly; its embedded script and registry are explained in [LOADER.md](LOADER.md). |
| [All-module disassembly directory](../../../external/research/area5150/disassembly/) | Linear listings for all 29 executables, with code/data warnings. |
| [disassemble.py](disassemble.py) | Reproduces the listings and optional NASM round-trip checks. |
| [Hardware comparison](capture_match.md) | Released bytes, acquisition sequence and parameters matched to physical capture. |

**The full Lake assembly and initializer both rebuild byte-for-byte with NASM.** The assembly intentionally uses `db` for exact encodings, with instruction mnemonics in comments. This preserves timing padding and self-modifying operand addresses. It is a faithful binary representation, not reconstructed editable author source. Generic linear listings decode embedded data as well as instructions; they are exploratory. Lake's reviewed code ends with the jump at `45BAh`, followed by data at `45BDh`.

## How the released initializer acquires timing

The important feature is feedback: the program repeatedly samples display status and advances only when the sample reaches the desired side of an edge. It does not merely wait for VSYNC and then run one fixed delay.

| Runtime offset | Recovered behavior | Timing significance |
|---|---|---|
| `01DDh` | Temporarily programs a two-character by two-scanline CRTC frame. | Reduces the CRTC states to resolve. |
| `0213h` | Accelerates refresh with PIT1 count 2, performs RAM reads, then writes mode 0/count 1. | Prepares a temporary interval without periodic refresh. |
| `0225h` | Writes `03h,03h,00h` into CGA RAM; performs controlled `MUL`/VRAM-read sequences. | Uses CGA wait states to constrain CPU/CGA alignment. |
| `0254h` | Repeats a timed `DIV`/NOP/status-read loop until port `3DAh` bit 0 is low. | Resolves the tiny CRTC-frame state. |
| `026Fh` | Establishes 114 eight-dot characters per line, then a temporary two-line frame. | One normal line is 912 master dots = 304 CPU cycles = 76 PIT ticks. |
| `032Ch` / `0340h` | Uses a 75-tick timer interval and tests display status on IRQ entry. Repeats until bit 0 is high. | Nominal interval is one PIT tick shorter than a line, so sampling walks relative to the edge. |
| `0354h` / `036Dh` / `037Ch` | Applies a 69-tick transitional interval, then restarts periodic refresh at count 19. | Places refresh before the next acquisition stage. |
| `03A2h` / `03B6h` | Uses a 4,863-tick timer with a 64-line CRTC frame, again testing display status. | One tick shorter than the 4,864-tick temporary frame; acquisition now includes refresh interference. |
| `03CAh` / `03E3h` | Applies a 5,117-tick transition, then a 19,912-tick steady period. | Enters the effect's `0400h` frame ISR at its scheduled phase. |

The timing constants reside at `45E4h=13FDh` (5,117), `45E6h=0045h` (69), and `45E8h=0000h`. The last controls an optional one-character horizontal stretch; the released default skips it. The captured reads confirm the two interval words and the zero stretch-control byte.

PIT reloads must be interpreted as a pipeline. A new count written while mode 2 is running is not simply an immediate new period. For example, the bridge handler at `036Dh` allows the transitional 69-count interval to elapse before the refresh restart. Likewise, `03E3h` installs 19,912 while the 5,117 transition is already counting. The raw counts are not interchangeable delays.

An explicit four-way phase detector is **not inherently required** if feedback acquisition removes the relevant phase dependence. Its absence cannot by itself establish that the method fails. Conversely, the existence of these feedback loops alone does not prove the final sub-tick timing is identical in all initial phase classes.

## What the physical capture proves

The [published capture](https://github.com/dbalsom/marty_tools/tree/23d99544ebf8aaf009bf2a551f048bb4b68a39a7/bus_sniffer/captures/area5150) calls the effect `CREDITS.COM`. The [publisher's account](https://martypc.blogspot.com/2023/10/bus-sniffing-ibm-5150.html) describes modifying the released launcher's execution script to reach the credits directly. We resolved the naming uncertainty by comparing actual fetched bytes, rather than trusting the labels.

The [reproducible comparison](capture_match.py) finds:

- **20,445 initializer fetch events**, covering 733 distinct bytes of the 768-byte initializer, all match the released binary.
- **53,054 observed effect fetches** match after replaying recorded self-modifications. Four initially different fetches occur at two operand bytes; the capture contains the writes that explain each one. There are no unexplained differences.
- The hardware interrupt-entry sequence is `032C -> 0340 -> 0340 -> 0354 -> 036D -> 037C -> 03B6 -> 03CA -> 03E3 -> 0400`.
- At the first `0340h` test, `3DAh` returns `F6h` (bit 0 clear). On the next entry it returns `F7h` (bit 0 set), and the chain advances. **This directly records a successful automatic acquisition decision.**
- Three observed main-effect entries occur at CPU cycles 536,065, 615,713 and 695,361: both intervals are exactly **79,648 CPU cycles**.
- Six shared signals match between this decoded CSV and the raw SR stream used in the earlier [two-frame comparison](../lake_trace_analysis.json), tying the byte evidence to the stable waveform evidence.

These are measurements from an existing physical-machine recording. We did not operate new hardware or run the full demo in Unicorn. Captured fetches include prefetch and do not prove every fetched instruction executed; interrupt acknowledgments and observed port reads independently establish the acquisition path above. Unobserved branches and the missing startup population remain outside this evidence.

## What transfers to CGA Image Studio

The acquisition machinery is a concrete reference worth testing. The drawing kernel is different: released Lake sets mode control `09h` and performs carefully timed CRTC/text operations, including scanline-address changes. It is not the application's mode-4 `OUT 3D9h` palette loop. Therefore this disassembly does not establish arbitrary 16-color-per-pixel graphics or the existing eight-write schedule.

The next work should be:

1. **Reproduce the released initialization in the updated MartyPC**, using the captured IRQ sequence, status decisions and steady period as a reference. Preserve exact instruction layout, register preconditions, VRAM bytes, timer sequencing and refresh behavior while establishing that baseline.
2. **Extract a bounded reference diagnostic**, preserving the timing-critical acquisition, then design and verify the handoff to mode-4 drawing. A graphics-mode change can affect the timing being preserved; it needs analysis and measurement rather than an assumed equivalent entry point. Timeout and cleanup changes also need timing review.
3. **Measure one palette transition against sync and the bitmap**, across deliberately varied entry states and every observed PIT/CGA power-on phase. Record both the bus write and the visible RGBI change. A phase signature can label test coverage without becoming a mandatory production correction table.
4. Only after that passes, extend to complete lines and frames, then two and eight writes. Keep the current exporter as a comparison artifact until the measured boundaries justify changing it.

The go/no-go criterion remains the user's: the same acquired starting point and predictable visible palette switch. This work removes the earlier missing-reference problem and establishes a successful hardware acquisition using released defaults. It leaves a specific, bounded portability and phase-coverage experiment.

## Reproduce the disassembly

After [unpacking](UNPACKING.md), from the repository root:

```powershell
.venv/Scripts/python.exe -m pip install --target external/research/python-tools capstone==5.0.9
.venv/Scripts/python.exe docs/research/area5150/disassemble.py --nasm "$env:LOCALAPPDATA/bin/NASM/nasm.exe"
.venv/Scripts/python.exe docs/research/area5150/capture_match.py
```

The installed Capstone distribution is 5.0.9; its Python module reports 5.0.7. The generated disassembly manifest records the reported decoder version and NASM comparison result. Downloaded binaries and large listings remain under ignored `external/research/`; the reviewed initializer, scripts, small results and notes are retained in this research directory.
