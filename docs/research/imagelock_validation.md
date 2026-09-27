# IMAGELOCK validation: original timing claim withdrawn

**Correction, 2026-09-14:** the original harness omitted
`CpuOption::EnableWaitStates(true)`. Its CPU had wait states disabled and did not
execute simulated refresh DMA stalls, despite the requested refresh setting.
The original claims of native-equivalent wait states and normal DRAM refresh
are invalid. Enabling the option reproduced the user's garbled output.

Use the [corrected wait-state-enabled validation](imagelock_waitstates_validation.md)
for new results. The [source audit and untouched archive](waitstates_disabled_archive/README.md)
explain the configuration mistake. Do not add the following counts to the new
validation totals.

## Historical counts, invalid for native timing validation

| Old test | Completed visible frames | Corrected interpretation |
|---|---:|---|
| Picard, four PIT settings | 1,225 | Wait states and refresh DMA stalls absent |
| REGLOCK, four PIT settings | 269 | Wait states and refresh DMA stalls absent |
| Independent indices/startup matrix, 32 configurations | 2,162 | Wait states and refresh DMA stalls absent |
| Four cold disk boots, including DOS return | 14,396 | Wait states and refresh DMA stalls absent |

The old kernel's reported 304-cycle rows, 79,648-cycle frames, and boundaries
`0,33,73,113,169,201,241,281,320` were measured under that invalid configuration.
They must not be treated as the geometry of a corrected native-compatible
kernel. The old disk and COM hashes remain recorded in the archive.

The [original report](waitstates_disabled_archive/imagelock_validation.md),
[original JSON](waitstates_disabled_archive/imagelock_validation.json), and
[archive manifest](waitstates_disabled_archive/archive_manifest.json) retain
the old evidence without modification. The similarly named JSON and SHA file
beside this page are also historical, not corrected validation records.

The converter's byte-exact ASM tests, bitmap packing checks, and successful
preview-to-export consistency checks remain useful software tests. They do
not validate palette timing on the native emulator or physical hardware.
