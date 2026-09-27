# CGA timing evidence audit

Prepared 2026-09-14. Scope: published measurements relevant to an original
4.77 MHz 8088 system with IBM CGA. These findings do not certify the CGA Image
Studio palette loop on physical hardware.

## Direct analysis of a real hardware capture

Daniel Balsom publishes a logic-analyzer capture of Reenigne's Area 5150 Lake
effect, including its setup and several effect frames. The capture README
identifies the signal probes and says the original 50 MHz recording was
downsampled to twice the CPU frequency. HS, VS and DEN are CRTC pins; RGBI and
the palette latch are not among the recorded signals. [1]

The two final complete VS-to-VS intervals were analyzed independently using
[lake_trace_analysis.py](lake_trace_analysis.py). The source file SHA-256 is
`4c0a38b1a21969c3a54746c2ad5ccd0d7e9e0433b66f1e16de2955c8828f93f4`.
The original file was read without alteration. Results are saved in
[JSON](lake_trace_analysis.json) and [CSV](lake_frame_timing.csv).

| Measurement | Frame 1 | Frame 2 |
|---|---:|---:|
| Frame duration, CPU cycles | 79,648 | 79,648 |
| IRQ rising edge after VS rising edge, CPU cycles | 11,161 | 11,161 |
| IRQ rising edge after VS falling edge, CPU cycles | 6,297 | 6,297 |
| IRQ after preceding HS rising edge, CPU cycles | 281 | 281 |
| Next DEN rising edge after IRQ, CPU cycles | 626 | 626 |
| HS rising edges | 262 | 262 |
| DEN rising edges | 400 | 400 |
| PIT clock rising edges | 19,912 | 19,912 |
| DRAM refresh request rising edges | 1,048 | 1,048 |
| I/O-write bus-status entries | 3,669 | 3,669 |

Every retained sample of VS, HS, DEN, INTR, CLK0, DREQ0 and READY is identical
between these two frames after alignment. Every I/O-write bus-status entry also
occurs at the same relative sample position. The comparison covers 159,296
samples per signal per frame, at two normalized samples per CPU cycle.

**What this establishes:** actual hardware executing Reenigne's effect exhibits
repeatable raster, interrupt, refresh and I/O-write timing in the two examined
frames. It is stronger evidence than an emulator screenshot or a frame-period
calculation alone.

**What this does not establish:** all-power-on-phase acquisition, a long-run
failure rate, electrical palette-latch delay, dot-resolution RGBI behavior, or
the correctness of this project's code. The selected intervals follow setup;
they do not measure whether setup converges from every possible starting state.
The effect has two DEN pulses per physical visible line, so the next DEN edge
must not be mistaken for an ordinary mode-4 screen origin. The normalized sample
rate is suitable for relative CPU-cycle counts, not precision measurements of
absolute oscillator frequency. Sub-sample analog behavior is not resolved.

## Evidence matrix

| Source | Empirical content | Supports | Limitation |
|---|---|---|---|
| Reenigne, CGA lockstep, 2012 [2] | Monitor photographs of injected entry phases and final aligned palette transitions | CPU/CGA phase convergence can be observed using palette writes as timing markers | Selected experiment; later author correction identifies missing power-on phases and an unstable wait-state race |
| Reenigne, CRTC lockstep, 2012 [3] | Palette-cycling image and account of a random first-line error followed by a status-dependent correction | CPU/CGA alignment and raster-origin alignment are distinct problems | Does not supply a large cold-start trial log |
| Reenigne source, original wait-state experiment, 2011 [4] | Numeric timing records plus matching RAM-baseline and CGA graphical programs | Phase-dependent extra wait times of 3–8 CPU cycles, with 16 deliberately stepped phases | Experiment indices are relative delay phases; no calibrated absolute master-clock origin or four-boot-phase matrix is recorded |
| Scali, 8088 MPH final, 2015 [5] | Reports plasma changes across power cycles and use of a phase-detection tool | Fixed frame period alone does not remove startup-phase dependence | Their stated workaround still requires power cycling for the favorable plasma phase; other effects are reported unaffected |
| Reenigne's 2017 correction [2] | Author reports four PIT/CGA boot phases and one inconsistent CGA wait-state phase | A robust acquisition design must account for phase classes and avoid the race | The comment proposes approaches; it is not a completed all-phase proof |
| Balsom, Lake trace [1] | Public binary trace, signal descriptions, timing images, decoder | Reproducible independent inspection of sophisticated real-hardware synchronization | One captured run and limited retained resolution |

## Original numeric wait-state data

The first and only change to `8088/cga/graphical_timer/results.txt` is commit
`8e0c527b4880424f2becb1ee28bf496d99144c38`, dated 2011-11-07, titled
`CGA wait states`. In that revision the graphical program tests phase delays
78 through 93 with a `STOSB`, first to system RAM and then to CGA RAM. A matching
`memtimer` program measures the system-RAM instruction sequences. [4]

For experiments 10–1F the recorded baseline cycles are:

```text
297 298 299 300 301 296 297 298 299 300 296 297 298 299 300 296
```

The file's recorded differences from the 304-cycle reference are:

```text
  7   6   5   4   3   8   7   6   5   4   8   7   6   5   4   8
```

The histogram is one phase with 3 extra cycles and three phases each with
4, 5, 6, 7 and 8 cycles. This agrees with Reenigne's published wait-state
description. [6] The experiment index advances one CPU cycle, hence three master
clock dots, at a time. An absolute phase origin or the later unstable phase
cannot be inferred merely by assigning array index zero to a hardware dot.
Any state-transition calculation from this record must declare its phase
convention and treat the later race separately.

## Validation gate suggested by the evidence

1. Reproduce one simple palette transition on a static, high-contrast pattern.
   Measure the RGBI edge against HSYNC and a fixed video-data boundary. Keep a
   separate record of I/O-write completion and visible output; their relationship
   is part of the measurement.
2. Deliberately sweep all 16 CPU/CGA entry delays. A successful acquisition must
   produce the same raster-relative transition after each sweep, not merely a
   stable but differently placed screen for each starting condition.
3. Detect and log the four PIT/CGA power-on phase classes, then repeat the sweep
   and marker test in every observed class. A count of reboots without phase
   classification is not proof of coverage. Include genuine power cycles.
4. Repeat with the intended refresh schedule enabled. Test the complete
   startup, drawing, blanking and exit paths; an active-display timing success
   does not establish RAM retention while halted or waiting during startup.
5. Only after one marker passes should the test expand to two, then the desired
   eight writes per line. Compare every output boundary over sustained runs and
   across cold starts. Preserve source, binary hashes, machine/card details,
   phase labels, capture files and explicit failures.

Published evidence supports undertaking this bounded experiment. It does not
justify expanding image-conversion features before the project's marker test
passes. A stable selected boot that needs a hand-adjusted delay remains an
experimental profile, not consistent automatic acquisition.

## Sources

1. Daniel Balsom, [Area 5150 Lake hardware capture and README](https://github.com/dbalsom/marty_tools/tree/23d99544ebf8aaf009bf2a551f048bb4b68a39a7/bus_sniffer/captures/area5150), repository revision 2023-10-17. See also his [2025-05-17 Lake debugging account](https://martypc.blogspot.com/2025/05/emulator-debugging-area-5150s-lake.html). The numerical comparison above is a new analysis of his published capture, not a quotation of his conclusions.
2. Andrew Jenner, [Adventures in CGA lockstep](https://www.reenigne.org/blog/adventures-in-cga-lockstep/), 2012-09-30, with author's correction 2017-05-28. Photographs: [wait states](https://www.reenigne.org/misc/cga_wait_states.png), [phase convergence](https://www.reenigne.org/misc/cga_lockstep.png).
3. Andrew Jenner, [Adventures in CRTC lockstep](https://www.reenigne.org/blog/adventures-in-crtc-lockstep/), 2012-10-01; [palette-cycling image](https://www.reenigne.org/misc/lockstep_test.png).
4. Andrew Jenner, [original wait-state results](https://github.com/reenigne/reenigne/blob/8e0c527b4880424f2becb1ee28bf496d99144c38/8088/cga/graphical_timer/results.txt), [graphical experiment](https://github.com/reenigne/reenigne/blob/8e0c527b4880424f2becb1ee28bf496d99144c38/8088/cga/graphical_timer/graphical_timer.asm), and [matching baseline timing code](https://github.com/reenigne/reenigne/blob/8e0c527b4880424f2becb1ee28bf496d99144c38/8088/memtimer/memtimer.asm), 2011-11-07.
5. Scali, [8088 MPH: The final version](https://scalibq.wordpress.com/2015/08/02/8088-mph-the-final-version/), 2015-08-02. The monitor calibration screen and the PIT/CGA phase issue are described separately.
6. Andrew Jenner, [The CGA wait states](https://www.reenigne.org/blog/the-cga-wait-states/), 2012-09-29.
