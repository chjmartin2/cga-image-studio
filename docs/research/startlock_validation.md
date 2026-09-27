# STARTLCK validation: original timing claim withdrawn

**Correction, 2026-09-14:** the original STARTLCK harness omitted
`CpuOption::EnableWaitStates(true)`. Its native-equivalence claim is invalid.
The CPU used wait states disabled, which also bypassed simulated refresh DMA
stalls despite `get_cpu_dram_refresh_simulation()` returning true. The original
report's statements that CGA wait states and normal DRAM refresh were preserved
are withdrawn. See the [source audit and untouched archive](waitstates_disabled_archive/README.md).

## Historical observations, invalid for native timing validation

The old runs reported 1,225 matching visible frames across four injected-COM
starts, marker onset at image pixel `(9,8)`, and a 79,648-cycle frame period.
A separate disk boot executed 3,600 marker pulses and yielded 3,599 completed
visible frames before DOS return. These counts describe only the incorrectly
configured harness. They do not establish STARTLCK acquisition, marker position,
or retention with the native frontend's wait-state and refresh settings.

The old COM SHA-256 was
`3e0e514005cb41809a209ad1311e63bd1426d6a9f820411a8a0af9fdc2417537`.
The [original report](waitstates_disabled_archive/startlock_validation.md),
[original JSON](waitstates_disabled_archive/startlock_validation.json), and
[archive manifest](waitstates_disabled_archive/archive_manifest.json) preserve
all original observations and hashes. The similarly named JSON beside this
page is also historical and must not be read as corrected validation.

## Current status

A bounded corrected STARTLCK run now shows stationary markers at x=25 for PIT
phases 0-2 and x=17 for phase 3, all on row 8. That is an eight-pixel startup
variation and fails the same-position criterion. The [corrected measurement
record](imagelock_waitstates_validation.md) reports effective CPU wait states
and refresh scheduling assertions. This is a separate observation from the
replacement full-image kernel; do not transfer its later results to STARTLCK.

The old marker disk's packaging and byte-preserving Lake reference can be
checked independently of timing. No physical-hardware qualification follows
from either emulator harness.
