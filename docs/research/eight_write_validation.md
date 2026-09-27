# Eight-write release validation — 2026-09-27

The replacement mode-4 profile is enabled for conversion and COM/ASM/DSK export.
The user confirmed the native MartyPC visualization was perfect. The independent
core checks below use effective CPU wait states and active raster refresh.
Physical hardware validation remains outstanding.

## Timing repair

The former harness omitted CPU wait states, which also bypassed refresh DMA
stalls. Enabling the option reproduced the garbled export. The replacement
preserves Lake reference bytes but introduces paired PREP/MAIN acquisition and
raster entry. PIT0 intervals of 19,760 and 152 ticks sum to one 79,648-clock frame.
Brief PIT1 mode-0 quiet windows drain pending DMA; MAIN restores mode 2/count 19
before visible writes. Refresh is active during the raster, not continuously
through preparation. Each row uses 33 NOPs and eight MOV/OUT pairs in 304 clocks.

Measured bounds: **0, 25, 65, 113, 161, 209, 249, 289, 320**. The eighth write is
in horizontal blanking and supplies the next row's leading palette. First-frame
and last-row/row-zero palette ownership are included in pixel comparisons.

## Evidence

The core is unchanged MartyPC commit `05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44`,
using IBM 5160, normal-speed 8088, CGA and GLaBIOS 0.2.6 XT. Every activation
asserts CPU waits, refresh scheduling and PIT1 mode 2/reload 19/counting/retrigger.
The harness checks full visible RGBI pixels, unequal pixel pairs, every row's
304-clock period and the 79,648-clock frame interval.

| Gate | Cases | Exact visible frames |
| --- | ---: | ---: |
| All-index registration: eight entry paddings × four PIT phases | 32 | 3,659 |
| Final photo COM: four PIT phases | 4 | 461 |
| Full DOS boot: four PIT phases | 4 | 14,396 |
| Five successive DOS launches: four PIT phases | 4 | 220 |
| **Core acceptance total** | **44** | **18,736** |
| Actual GUI exports: dithering × palette optimization × border | 12 | 1,383 |
| Final shipped demo disk: four PIT phases | 4 | 1,803 |

The final frame of a DOS display ends before a completed buffer flip, so a
3,600-frame run contributes 3,599 captured visible frames. Every captured frame
matches; first and last buffers are also checked independently. Raw logs stay
under ignored `external/research`; curated per-case options, hashes and totals
are in [the JSON evidence](eight_write_validation.json).

GUI callbacks exercised all three dithering families, both dither-aware settings
and both black-border settings. Each COM matches its expected preview in the
core, each ASM rebuilds byte-for-byte, and each DSK's FAT12 TEST.COM matches the
export. The packaged executable additionally passes its independent runtime
smoke test. Software regression results: 26 tests / 59 subtests passed.

Native confirmation was provided by the user on 2026-09-27 for candidate COM
`67c94210dbe7177c0a57b7b19741debb766ab1f551a7112f2fc8e536a2bee65f`.
The final template uses the same executed timing instructions; its descriptor
corrects the recorded inter-write NOP parameter. Photo pixels/palettes differ
with conversion options. Native visual confirmation is distinct from automated
core comparison; neither establishes physical CGA hardware reliability.

Template SHA-256:
`3866d092a169a128ed7d7ab8fbe9038d8991c770ebed9476bb056633e8e9ed89`.
Final Picard COM SHA-256:
`295e7b5416df3d70776f9e704bc9160bead495f840a574a7a5a9a6efcc0a11c0`.
The profile records the assembly source hash; default assembly rebuild is tested
against the entire template. Reports of the former withdrawn kernel are retained
as historical evidence and contribute no counts above.

Reproduction commands are in [project status](../PROJECT_STATUS.md). For GUI
exports, run `tools/smoke_mode4_gui.py`, then `tools/validate_mode4_gui_exports.py`.
