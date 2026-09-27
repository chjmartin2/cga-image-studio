# Withdrawn wait-states-disabled validation

These are byte-for-byte copies of the reports and result records before the
2026-09-14 correction. **Their native MartyPC timing claims are invalid.**
Historical measurements and hashes are retained for audit; they are not passing
results for the corrected configuration. Links inside copied reports preserve
their original text and may require the original directory context.

Both original harnesses omitted `CpuOption::EnableWaitStates(true)`. The CPU
therefore used its default `false`, even though the harness requested DRAM
refresh simulation. This disabled memory/I/O wait states and the CPU's simulated
refresh DMA stalls. Programming PIT channel 1 to 19 did not make the missing
stall simulation operate. The native frontend explicitly enables wait states.
Enabling the same option in the harness reproduced the user's garbled image.

Verified source at MartyPC commit
`05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44`:

- [Intel808x derives Default; enable_wait_states is a bool](https://github.com/dbalsom/martypc/blob/05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44/crates/lib/marty_core/src/cpu_808x/mod.rs#L462).
  The constructor starts from `Default::default()` at line 807.
- [The native frontend explicitly sets EnableWaitStates](https://github.com/dbalsom/martypc/blob/05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44/crates/bin/martypc_eframe/src/emulator/mod.rs#L267).
- [Disabled wait states suppress both memory and I/O waits](https://github.com/dbalsom/martypc/blob/05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44/crates/lib/marty_core/src/cpu_808x/cycle.rs#L172).
- [tick_dma requires both enable_wait_states and dram_refresh_simulation](https://github.com/dbalsom/martypc/blob/05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44/crates/lib/marty_core/src/cpu_808x/cycle.rs#L235).

The [archive manifest](archive_manifest.json) records hashes and the effective
CPU options. Original JSON contents and their SHA files were not rewritten.
Published physical Area 5150 captures are separate evidence and are unaffected.
See [the corrected validation record](../imagelock_waitstates_validation.md) for
new measurements; do not combine old and corrected frame counts.
