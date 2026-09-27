# CGA beam timing and repeatable palette switching

## Decision

Stable beam-synchronized execution on an original IBM PC/CGA is physically possible and has published hardware evidence. That evidence is strong enough to justify a bounded synchronization experiment. It is not sufficient to certify CGA Image Studio's current eight-write export, or to promise an identical starting position after every power cycle.

The immediate engineering decision is **hold further palette-density and image-optimizer work until a small diagnostic passes acquisition, retention, and palette-position tests**. The existing hardware test in the supplied forum PDF failed to reproduce the intended image. A new emulator build is a useful instrument, but an emulator screenshot cannot close that failure. [^1]

Three claims need separate answers:

| Claim | Assessment |
| --- | --- |
| Can original CGA support repeatable execution synchronized to the beam? | Yes. Reenigne's experiments and a later physical bus capture provide direct evidence. |
| Does the current eight-write exporter have a validated hardware lock? | No. Its evidence is emulator calibration, while the supplied hardware test disagrees. |
| Is automatic acquisition with the same palette boundaries on every supported startup already demonstrated for this project? | No. The released Lake initializer now has a byte-matched successful hardware acquisition, but this project's palette edges and all startup phases remain unvalidated. |

The scope is a stock-clock Intel 8088 system with an original IBM CGA, initially on RGBI output. Record the motherboard, CGA revision and actual CRTC chip. Compatibility with V20 CPUs, turbo operation, EGA/VGA compatibility modes, or arbitrary CGA clones requires separate qualification. Review date: 2026-09-14.

**Released-binary follow-up:** We downloaded and unpacked the August 2022 Area 5150 party release, disassembled its actual `LAKE.COM`, and matched all 20,445 observed initializer fetches in the published physical capture. The released code has automatic status-conditioned PIT acquisition and the capture uses its default timing values. This corrects any inference that the older manually controlled `lake.asm` was the released implementation. See [released disassembly and revised next steps](research/area5150/README.md) and [hardware byte comparison](research/area5150/capture_match.md). Use that initializer as the next reference; a four-way correction table is not inherently necessary if its feedback proves phase-insensitive.

**Mode-4 prototype correction, 2026-09-14:** the original STARTLCK and IMAGELOCK harnesses omitted `CpuOption::EnableWaitStates(true)`. The CPU default disabled wait states and also bypassed refresh DMA stalls, even though refresh simulation was requested. Their marker positions, 304-cycle image rows, and passing startup matrices are **invalid for native timing validation**. Enabling the native option reproduced the user's garbled image. [The source audit and untouched archive](research/waitstates_disabled_archive/README.md) record the mistake; [corrected validation](research/imagelock_waitstates_validation.md) must establish replacement timing. The published physical Lake capture and external hardware research below are separate evidence and are unaffected.

## 1. What the hardware evidence actually establishes

### Reenigne's original experiments

In September 2012, Andrew Jenner (Reenigne) used palette changes as visible timing markers. He deliberately introduced 16 CPU/CGA entry phases, then demonstrated convergence modulo 48 master-clock dots in a photographed test. His separate CRTC experiment found that CPU/CGA alignment could still leave different first-line states. [^2][^3]

Those are useful existence experiments, not merely nominal instruction-cycle calculations. They also distinguish a stable pattern during one run from a repeatable absolute position between runs. In a May 2017 correction, Jenner documented four power-on PIT/CGA phases and a CGA memory-access race that can vary even within one run. The original photograph therefore does not establish universal startup coverage. [^2]

The repository contains a numerical record in `8088/cga/graphical_timer/results.txt`. Its experiment IDs `10` through `1F` have final wait-cycle values:

```text
7, 6, 5, 4, 3, 8, 7, 6, 5, 4, 8, 7, 6, 5, 4, 8
```

The corresponding distribution is:

| Added CPU cycles | Recorded experiments |
| ---: | ---: |
| 3 | 1 |
| 4 | 3 |
| 5 | 3 |
| 6 | 3 |
| 7 | 3 |
| 8 | 3 |

The mean is 5.8125 cycles. This agrees with the distribution in Jenner's wait-state article. Git history ties the record to November 7, 2011, with matching graphical and system-RAM baseline tests. The graphical test steps its delay from 78 through 93 CPU cycles; subtracting the recorded RAM baselines from 304 produces the listed waits. Its indices are relative injected delays, not calibrated absolute master-dot phases. The record supports phase-dependent memory timing; it is not a measured `OUT 3D9h` latency table or a four-boot-phase test matrix. [^4][^5]

### Independent analysis of an actual hardware capture

Daniel Balsom published a logic-analyzer capture of Reenigne's Area 5150 Lake effect. The capture includes PIT clock, interrupt request, refresh request, and CRTC horizontal sync, vertical sync and display enable. Its documented original acquisition was 50 MHz; the published stream is downsampled to twice the CPU clock. [^6]

The accompanying analysis of `area5150_lake_effect_final_02.sr` finds three final VSYNC rising edges at CPU-edge coordinates 604472, 684120 and 763768. They delimit two complete consecutive frames:

| Measurement | First frame | Second frame |
| --- | ---: | ---: |
| Frame duration, CPU cycles | 79,648 | 79,648 |
| HS rising edges | 262 | 262 |
| DEN rising edges | 400 | 400 |
| INTR rising edges | 1 | 1 |
| PIT CLK0 rising edges | 19,912 | 19,912 |
| DREQ0 rising edges | 1,048 | 1,048 |
| INTR offset after VS rising edge, CPU cycles | 11,161 | 11,161 |

After aligning those frames by VSYNC, **VS, HS, DEN, INTR, CLK0, DREQ0 and READY have zero differing samples**. These are measurements from the published physical capture, not results from running the current emulator. The 400 DEN pulses are specific to the Lake effect's unusual display organization; they do not imply a normal 400-line screen. [^6][^7]

The result establishes sustained synchronization in this captured run. Its limits are equally important: two complete frames, one captured startup, no complete cold-boot population, and no RGBI color channels establishing the visible edge of a `3D9h` palette change. Downsampling also prevents treating this file as a master-dot-resolution latch measurement. It is a strong reference for timing infrastructure, not certification of the application's palette schedule.

### The current application's hardware evidence

The supplied PDF records VileR's test on an IBM 5160 with original IBM CGA. The image was incorrect on three attempts, with palette boundaries estimated one character clock early. Balsom identified a missing character-clock rasterization delay in the then-current MartyPC; Jenner separately identified startup phase and refresh issues. These observations support several possible causes, not one proven diagnosis. [^1]

A fixed horizontal error can coexist with excellent frame-to-frame stability. The diagnostic must therefore measure both **variance** and **absolute registration**. Shifting the preview until one picture looks right would leave acquisition correctness unresolved.

## 2. The timing relationships and the four distinct problems

Use master-clock dots as the common unit. In standard 320-pixel CGA graphics, one logical pixel lasts two master dots, and one CPU cycle lasts three. PIT frequency is the master frequency divided by 12, or CPU frequency divided by four. The opening paragraph of the 2012 CGA-lockstep article has an inconsistent PIT divisor; its frame-count formula and the later explanation give the correct relationship. [^2][^8]

For the standard 262-line frame used here, the derived quantities are:

```text
one scanline = 912 master dots = 304 CPU cycles = 76 PIT ticks
one frame   = 262 scanlines   = 79,648 CPU cycles = 19,912 PIT ticks
one CPU cycle = 1.5 logical 320-mode pixels
```

These equalities explain why drift-free timing is possible: the clocks share a source and the frame periods are integral. They do not determine the initial phase or the completion time of an instruction stream.

| Problem | Required observation or control |
| --- | --- |
| CPU/CGA phase | Establish the phase of timed CPU activity relative to CGA memory arbitration. |
| CRTC position | Establish which row/column state the controller occupies after clock alignment. |
| PIT/refresh phase | Detect or tolerate the power-on phase, and control refresh requests and resulting bus interference. |
| Visible palette registration | Establish where a completed palette write affects RGBI output relative to the displayed pixels. |

The four CRTC states in the corrected small-frame routine are **not** the four power-on PIT phases. Clearing one ambiguity does not clear the other. Likewise, a PIT interrupt repeating every 19,912 ticks gives a frame-period heartbeat; it does not alone prove that every launch wakes at the desired pixel.

`HLT` removes variation caused by interrupting different foreground instructions. The interrupt path, prefetch state, refresh behavior and initial timer phase still have to be characterized. A loop's average duration of 304 cycles is insufficient: a repeating short/long pattern can average 304 while individual seams move.

## 3. What to reuse from Reenigne's code

### Source history resolves an apparent missing routine

The Kefrens source calls `lockstep2`, while the current common include defines `lockstep`. Git history explains the mismatch: `lockstep2` was added on 2014-04-29 and merged into the older macro on 2015-04-25. A subsequent 2017-09-26 commit, titled `Fixed lockstep`, changes the CRTC convergence section. This is a reason to pin source revisions and inspect expansions, rather than paste whichever snippet a search finds. [^9][^10][^11]

The current macro still has a nearby TODO about leaked CRTC row/column state. That comment predates the September 2017 change. It is not, by itself, proof that the later implementation has that defect. Conversely, the commit title is not proof of all-phase hardware correctness.

### CPU/CGA acquisition

The common macro uses controlled CGA memory reads separated by carefully arranged delays, including multiply instructions. That is qualitatively different from polling a status edge and then hoping that a fixed NOP count gives the same start. The memory wait behavior can collapse several possible entry phases into fewer exit phases. [^2][^11]

For a port of this method, preserve the full instruction sequence, register setup, segment addresses, data bytes read from CGA, branch paths and prefetch preparation. A nominally equivalent instruction substitution is a new timing experiment. Test the unstable wait-state case rather than modeling it as one deterministic value.

### The corrected CRTC acquisition

The 2017 change uses a temporary frame of two character clocks by two scanlines, with only one cell displayed. A status-sampling loop documented as 144 CPU cycles walks through the possible row/column states until display enable identifies the chosen state. [^11]

The following is an arithmetic interpretation of that source, not a new hardware measurement. With a 16-dot character period, 144 CPU cycles equal 432 dots, or 27 character periods. Modulo a four-character frame, each repeated observation advances by three states. It visits all four possibilities; meanwhile 144 is divisible by 16 CPU cycles, preserving the CPU/CGA phase class. At most three additional backedges are required after the first observation under that model.

Restore normal display geometry at a known point after acquisition. Monitor recovery from the temporary geometry is a separate issue; settling frames must be excluded from measurements by a declared acquisition boundary, not by discarding inconvenient early failures.

### A real PIT-phase detector exists

In `8088/cga/scanline_per_frame/lake.asm`, the code first enters lockstep, then programs PIT channel 2 and takes five latched 16-bit readings. It examines four adjacent differences and encodes the position of a difference of 20 as a one-hot phase signature, 1, 2, 4 or 8. The source stores ASCII `'0' + signature`, producing the displayed characters `'1'`, `'2'`, `'4'`, `'8'`; a new log format must distinguish the character from the numeric signature. The associated notes describe the read/store interval as 83 CPU cycles, or 20.75 PIT ticks. [^12][^13]

Under that timing assumption, the expected difference sequence has one 20 and three 21s. This gives a useful falsifiable detector contract: save all five raw values, compute differences modulo 65536, and require the expected signature repeatedly. Unexpected signatures must produce failure, not a plausible-looking phase number.

The examined **2017 experimental** `lake.asm` uses the phase value for display/logging. Its timing period, refresh phase and CGA/CRTC phase controls are adjusted manually. It does **not** supply an automatic four-way correction table for this application's palette kernel. [^12] This statement does not describe the 2022 released binary: the later [disassembly](research/area5150/README.md) recovers automatic feedback acquisition and ties it to a successful hardware run.

The 8088 MPH final-version write-up independently reports needing the correct power-on phase for the plasma effect. Its calibration screen adjusts display/CRTC behavior; it is not evidence that every effect automatically normalizes the PIT phase. [^8]

### The appropriate architecture

The recommended implementation separates `acquire`, `identify`, `run`, `verify`, and `restore`. Acquisition establishes CPU/CGA and CRTC state. Identification records the PIT signature for coverage during validation; it need not remain in production if the released feedback approach proves phase-insensitive. Running selects either a schedule proven insensitive to that signature or a separately measured schedule for that signature. Verification detects failed acquisition or lost registration. Restoration provides a bounded return to DOS.

A four-way dispatch is a plausible engineering route, not a completed solution. A delay of a few CPU cycles might correct the initial write while leaving different refresh collisions later in the line. Consequently, validate complete per-phase line kernels and frame transitions, rather than measuring only the first `OUT`.

## 4. Refresh is part of the lock

The legacy phase-7 eight-write path disables PIT channel 1 refresh and subsequently spends startup frames waiting in `HLT`. Its argument that unrolled instruction fetches refresh memory applies during the drawing stream; it does not justify long halted calibration intervals. The interrupt vector, handler, stack, DOS state and other RAM must survive as well as the code being executed. [^1][^14]

Jenner's older refresh article explains why sequential accesses can maintain DRAM under particular row-address and timing assumptions. The 2026 forum warning cautions against extending that argument to all RAM needed for a DOS return. The prudent interpretation is to validate row coverage and retention for the actual memory system, including expansion memory, instead of assuming one executing segment preserves everything. [^1][^14]

For the first experiment, keep refresh operating during setup, user interaction and long waits. Restrict any refresh-off window to a measured bounded interval with an adequate margin below the strictest supported retention requirement. The common source's `safeRefreshOff` performs an accelerated refresh sweep and documents only about 1.6 ms remaining; it does not justify a whole 200-line interval or a long halted wait. Preserve a recoverable exit path outside the timed interval. Restoring refresh after data has already decayed does not repair the data. [^11]

For sustained display, PIT channel 1 count 19 is an established candidate: it produces refresh every 76 CPU cycles, four requests per scanline. Jenner describes its successful use in Kefrens while explicitly noting that the slower rate can be outside the DRAM specification. It is evidence of practical operation on tested machines, not a universal retention guarantee. [^15]

Derived example: 128 rows refreshed every 76 CPU cycles take about 2.04 ms at 4.77 MHz. That slightly exceeds a 2 ms requirement. Count 18 is faster but does not divide the 304-cycle line, so its interference pattern varies across lines. A faster divisor that divides 76 PIT ticks, such as count 4, is an experimental alternative with substantial bus cost; it has not been validated here and should not be substituted into a tuned kernel.

Choose and document the retention contract before increasing write density. A long-lived picture that cannot exit safely is not sufficient for this project.

## 5. Specific gaps in the current exporter

The source audit below refers to the current working `cga_v167.py`; line numbers can move as the exporter changes. The recent NASM round-trip checks establish binary export fidelity only.

| Location | Observation | Consequence |
| --- | --- | --- |
| Around 10246-10270 | Comments describe a residual plus/minus one CPU cycle and moving eight-write seams away from character boundaries; four matching emulator cold boots are recorded. | This is a tolerance workaround and a small emulator sample, not an exact hardware-lock proof. |
| Around 10747-10759 | No refresh sweep is retained; the rationale describes unrolled fetching and short residual waits. | It does not cover the multi-frame startup `HLT` search or all required RAM. |
| Around 10773-10825 | Phase 7 installs IRQ0, uses a 19,912-tick timer, and searches for a VSYNC falling edge with coarse and fine delays. | It remains PIT-dependent despite refresh being off; it is not the memory-wait/CRTC acquisition sequence audited above. |
| Around 10812-10825 | Fine search can exhaust its candidates and fall through into drawing. | A failed search needs an explicit failed result, not the same entry as success. |
| Around 10829-10837 | Each frame reuses the same delay after `HLT`. | Long-term stability is plausible for a fixed phase, but there is no ongoing independent lock witness. |
| Around 10905-10925 | The program repeats indefinitely and does not restore the overwritten IRQ vector or PIC state. | It is unsuitable as the next hardware diagnostic without a safe bounded lifecycle. |

`tools/phaselock.asm` is also an unfinished design sketch: its computed delay dispatch is a placeholder. Its statement that one timer read removes all startup uncertainty should not be treated as a completed implementation.

The next production change should follow measurements, not precede them. Keep the existing binary and preview as a historical control. Build the synchronization diagnostic independently so an image optimizer, palette ownership error or old preview calibration cannot obscure its result.

### Palette timing and rasterization timing must be measured separately

The eight-write profile uses seven visible boundaries and one blanking write for the following line's leading palette. Its current expected boundaries are 33, 73, 113, 153, 193, 233 and 273 logical pixels. Those are emulator-derived coordinates. They must be remeasured against the physical displayed pixel stream.

A status read, CRTC DEN edge, completed I/O bus write, graphics shift-register output and monitor-visible transition are distinct observations. Record which one each timestamp describes. The current trace parser's instruction and bus events cannot directly certify the visible RGBI transition.

Use two diagnostics with an identical timed instruction stream. First use zero-valued VRAM so background changes form unambiguous vertical color edges. Then use a known repeating 2-bit pattern containing all four pixel indices. Compare background selection, foreground palette/intensity changes and the bitmap's physical registration. A disagreement between these tests can expose a pixel-pipeline or palette-model issue without confusing it with line drift.

The latest MartyPC source changes its CGA and monitor handling substantially. The audited build is pinned to `05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44`. Do not assume that the forum's particular latency issue is fixed solely from a version label or successful compilation. Validate it with the same diagnostic and a physical trace. [^16]

## 6. A bounded empirical validation program

### Stage A: establish one observable marker

Create a separate NASM diagnostic with no image conversion, no disk access during measurement and no palette optimization. Use a controlled BIOS/DOS baseline and record the actual hardware. Save readable state such as interrupt vectors, PIC mask and speaker controls; record the timer/video settings the diagnostic establishes and restore a documented BIOS-compatible baseline. Do not promise restoration of arbitrary unknown settings: CGA includes write-only registers. Account for elapsed BIOS time if the DOS-return contract requires it. Complete setup with refresh on. [^17]

First reproduce the [released Lake initializer](research/area5150/lake_initializer.asm) against its captured acquisition sequence. Then acquire using that pinned, reviewed reference and verify the handoff to mode-4 drawing. Emit one high-contrast background transition at a declared line and horizontal position. Begin with a short burst of measured lines, restore the machine, and report success or failure. The first objective is an observable reference event with a safe exit; it is not eight writes across 200 lines.

Record the acquisition result, raw PIT signature, selected schedule, reference sync edge, palette-write edge and visible color edge. Acquisition loops need timeouts. Their implementation must preserve or explicitly rederive critical loop timing; inserting a counter into the reference 144-cycle loop would invalidate its convergence arithmetic. A timeout or malformed signature must restore state and report failure. Do not call the DOS keyboard or file services inside the measured interval.

### Stage B: attack the starting phase

Inject the 16 controlled CPU/CGA entry offsets used by the reference method. Independently verify that the injection actually creates distinct pre-acquisition states; sixteen binaries containing different NOP counts do not automatically prove sixteen distinct states. Reacquire on each trial and compare the final marker to the same physical raster reference.

Repeat under each observed PIT signature. As a proposed acceptance minimum, use 100 warm reacquisitions per controlled offset per signature. The 16-by-4 matrix is a controlled coverage grid, not an exhaustive proof of every internal machine state. Standardize the prefetch and register preconditions and separately test perturbations that the normalization routine claims to absorb.

For cold-start validation, record actual power-on trials and their detected signatures. A software restart or emulator reset does not necessarily change the physical divider phase. Do not declare all-phase success based on a fixed number of boots if one or more signatures never appears. Avoid inventing a mapping between MartyPC's `pit_phase = 0..3` and the hardware detector's labels; establish that mapping from observed signatures.

In the emulator, run four separately configured startup phases and verify that they actually produce distinct relevant device timing. A configuration field being accepted is not proof that it exercises the intended path.

### Stage C: prove line cadence and a complete frame

Extend the passing marker to a 200-line pattern. Measure corresponding writes on adjacent lines and on adjacent frames. For the standard geometry, require 304 CPU cycles between equivalent line events and 79,648 between equivalent frame events, with no alternating or periodic exceptions.

As a proposed endurance screen, capture at least 10,000 consecutive frames for each supported signature and schedule. This is roughly 167 seconds per case. Record every outlier; do not average the error away. It is an engineering screening threshold, not a statistical guarantee for all future operation.

Measure the top visible line, the final visible line, the transition into blanking and the first line after the next frame's acquisition. Test the chosen refresh strategy through setup, drawing, waiting and exit. The frame boundary is part of the kernel.

### Stage D: prove palette placement

Progress from one transition to two, then to the intended eight writes. For each density, test the zero-VRAM pattern and the indexed bitmap pattern. Exercise background changes, intensity changes and palette-family changes, including values that previously looked correct in the preview.

Capture RGBI and sync if possible. A 640-dot digital capture can expose half-logical-pixel transitions that a resized 320-pixel screenshot conceals. For electrical measurements, use sufficient sampling resolution and record the uncertainty. The existing twice-CPU Lake capture is useful for bus cadence but cannot certify a one-master-dot color-edge tolerance.

Acceptance requires the same visible transition coordinate for the same case, both within a run and across qualified startups. A constant measured pipeline offset may be incorporated into the preview once independently established. A different unexplained offset for each launch is a failure. If a stable transition falls halfway through a 320-mode pixel, either move the schedule or explicitly model that output; do not silently round it away.

### Stage E: qualify the actual export

Only after the diagnostic passes should the application adopt its acquisition and frame machinery. Generate a fixed palette-map test before photographic artwork. Verify all seven visible boundaries, the preceding line's blanking write, leading-zone ownership and the final-line case. Then compare the exported indexed image against a raw capture using the measured palette schedule.

The final capability remains a 320x200, 2-bit-per-pixel bitmap whose four-color interpretation changes in horizontal regions. Multiple regions can use colors from the RGBI set of 16. It does not become an unrestricted four-bit framebuffer where every pixel independently selects any of 16 colors. [^17]

## 7. Go/no-go criteria and failure diagnosis

| Result | Interpretation | Decision |
| --- | --- | --- |
| One marker moves within one startup with IRQ/refresh controlled | Acquisition, instruction/bus timing, or a race is unresolved. | Stop density work; retain raw failing traces. |
| Marker is stable per startup but differs by PIT signature | Phase identification works, correction or phase-insensitive scheduling does not. | Develop and validate per-signature schedules; do not claim universal lock. |
| Bus writes repeat exactly but visible pixels are consistently displaced | Investigate graphics pipeline and output registration. | Calibrate only after the physical relationship is measured. |
| First marker matches, later lines drift | Line period or phase-dependent interference is wrong. | Repair the kernel before testing full images. |
| All image tests pass but RAM/exit fails | Retention or state restoration is inadequate. | Fail the implementation. |
| Diagnostic passes all measured phases on the first documented machine | The first hardware profile is supported by evidence. | Integrate, then qualify a second independent machine/card profile. |
| Operation requires power-cycling until a favorable phase appears | A restricted demonstration works, but automatic consistency is unmet. | No-go for the stated always-repeatable objective. |

There is no need for further open-ended image tuning to answer feasibility. The bounded next deliverable is a reference acquisition/phase diagnostic plus its raw measurement package. The published evidence makes success plausible and provides concrete mechanisms to test. Until that package demonstrates the project's own starting point and palette switch, the eight-write feature should remain experimental.

## 8. Reproducibility and evidence preservation

For every new trial, retain: machine/card/CRTC identifiers; CPU and clock setting; boot environment; executable and source hashes; acquisition revision; raw five-word PIT readings; decoded signature; selected kernel; refresh configuration; acquisition time/result; raw sync, bus and RGBI capture; measured first/last transition; frame count; retention/exit result; and measurement uncertainty. Logs written after restoring DOS should preserve failed cases as well as successful ones.

The Lake analysis includes a [reproducible script](research/lake_trace_analysis.py), [full results and capture hash](research/lake_trace_analysis.json), [frame timing table](research/lake_frame_timing.csv), and [evidence audit](research/evidence_audit.md). Its source archive belongs to `dbalsom/marty_tools`, pinned to `23d99544ebf8aaf009bf2a551f048bb4b68a39a7`. Reenigne's inspected checkout is pinned to `474aced6e6decd8149972fa517e0e732841f94f8`. Downloaded research repositories are local reference material under `external/research`; the report and small analysis outputs are the project artifacts.

Reproduce the comparison from the project root with:

```powershell
.\.venv\Scripts\python.exe docs\research\lake_trace_analysis.py
```

No new physical-machine run of CGA Image Studio was performed for this assessment. The newly computed hardware numbers come from Balsom's published recording. That distinction must remain attached to any future summary of these findings.

## Sources

[^1]: VileR, GloriousCow, reenigne and chjmartin2. *320x200x16 CGA Test on Hardware Request*, June 21-28, 2026. Supplied five-page PDF: `Extras/320x200x16 CGA Test on Hardware Request  Vintage Computer Federation Forums.pdf`, especially pp. 2-4. [Original thread](https://forum.vcfed.org/index.php?threads/320x200x16-cga-test-on-hardware-request.1257955/). The supplied PDF is the record used; the live thread was not independently retrieved.
[^2]: Andrew Jenner. [Adventures in CGA lockstep](https://www.reenigne.org/blog/adventures-in-cga-lockstep/), September 30, 2012, including author's May 28, 2017 correction.
[^3]: Andrew Jenner. [Adventures in CRTC lockstep](https://www.reenigne.org/blog/adventures-in-crtc-lockstep/), October 1, 2012.
[^4]: Andrew Jenner. [The CGA wait states](https://www.reenigne.org/blog/the-cga-wait-states/), September 29, 2012.
[^5]: Andrew Jenner. [Original graphical timer results](https://github.com/reenigne/reenigne/blob/8e0c527b4880424f2becb1ee28bf496d99144c38/8088/cga/graphical_timer/results.txt), [graphical experiment](https://github.com/reenigne/reenigne/blob/8e0c527b4880424f2becb1ee28bf496d99144c38/8088/cga/graphical_timer/graphical_timer.asm), and [RAM baseline timing code](https://github.com/reenigne/reenigne/blob/8e0c527b4880424f2becb1ee28bf496d99144c38/8088/memtimer/memtimer.asm), November 7, 2011, commit `8e0c527b`.
[^6]: Daniel Balsom. [Area5150 Lake capture documentation and files](https://github.com/dbalsom/marty_tools/tree/23d99544ebf8aaf009bf2a551f048bb4b68a39a7/bus_sniffer/captures/area5150). [Bus Sniffing the IBM 5150: Part 1](https://martypc.blogspot.com/2023/10/bus-sniffing-ibm-5150.html), October 2023, describes physical instrumentation.
[^7]: Local reproducible analysis of source 6, `docs/research/lake_*`, September 14, 2026. All counts identified as newly derived in this report come from the published physical capture.
[^8]: Scali, co-author of 8088 MPH. [8088 MPH: The final version](https://scalibq.wordpress.com/2015/08/02/8088-mph-the-final-version/), August 2, 2015, especially Overall tweaks and Calibration screen.
[^9]: Andrew Jenner. [Addition of lockstep2](https://github.com/reenigne/reenigne/commit/0fc90fe5f6d867e34892e6cb0ed22202abdf28d6), April 29, 2014.
[^10]: Andrew Jenner. [Common lockstep revision](https://github.com/reenigne/reenigne/commit/f4f6cf244e3c9cc5be2ebaddc62d487b70dbe41e), April 25, 2015.
[^11]: Andrew Jenner. [Fixed lockstep](https://github.com/reenigne/reenigne/commit/55d4e649da333fdb2abde512888e96726057c6db), September 26, 2017; [current common macro](https://github.com/reenigne/reenigne/blob/474aced6e6decd8149972fa517e0e732841f94f8/8088/defaults_common.asm).
[^12]: Andrew Jenner. [Lake experiment source](https://github.com/reenigne/reenigne/blob/474aced6e6decd8149972fa517e0e732841f94f8/8088/cga/scanline_per_frame/lake.asm), particularly lines 117-170 (detector), 301-443 (interrupt setup), 562-635 (manual controls), 822-825 (defaults).
[^13]: Andrew Jenner. [Scanline-per-frame experiment notes](https://github.com/reenigne/reenigne/blob/474aced6e6decd8149972fa517e0e732841f94f8/8088/cga/scanline_per_frame/1spf.txt), especially the 83-cycle read interval near line 137. These are laboratory notes, not a completed compatibility specification.
[^14]: Andrew Jenner. [How to get away with disabling DRAM refresh](https://www.reenigne.org/blog/how-to-get-away-with-disabling-dram-refresh/), October 29, 2012. Read together with the later warning in source 1.
[^15]: Andrew Jenner. [More 8088 MPH how it's done](https://www.reenigne.org/blog/more-8088-mph-how-its-done/), April 12, 2015, Kefrens bars section; [Kefrens source](https://github.com/reenigne/reenigne/blob/474aced6e6decd8149972fa517e0e732841f94f8/8088/demo/kefrens/kefrens.asm).
[^16]: Daniel Balsom and contributors. [MartyPC source at the audited build revision](https://github.com/dbalsom/martypc/tree/05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44), September 7, 2026. Relevant files: `crates/lib/marty_core/src/devices/cga/mod.rs`, `io.rs`, and `crates/bin/martypc_eframe/src/emulator/mod.rs`.
[^17]: IBM. [IBM Personal Computer Technical Reference, first edition](https://minuszerodegrees.net/manuals/IBM_5150_Technical_Reference_6025005_AUG81.pdf), August 1981, Color/Graphics adapter section, particularly printed pp. 2-51 to 2-59. Original IBM document hosted by Minus Zero Degrees.
