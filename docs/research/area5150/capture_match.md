# Released LAKE.COM matched against the published hardware capture

The captured instruction-fetch stream matches the unpacked released `LAKE.COM`, including its complete observed initialization path. This closes the earlier evidentiary gap between the capture's `CREDITS.COM` label and the released effect's filename. It does not prove all possible startup phases succeed.

## Inputs and reproducibility

- Capture publisher: Daniel Balsom, [Area 5150 Lake bus capture](https://github.com/dbalsom/marty_tools/tree/23d99544ebf8aaf009bf2a551f048bb4b68a39a7/bus_sniffer/captures/area5150).
- Capture CSV SHA-256: `9a39cf60d8646dd8efa4fc23b795eb58a06cb12d6fec378b382ba518c33dfc63`.
- Capture SR SHA-256: `4c0a38b1a21969c3a54746c2ad5ccd0d7e9e0433b66f1e16de2955c8828f93f4`.
- Unpacked release `LAKE.COM`: 60,050 bytes, SHA-256 `1192f22cb6dd3fa668acf8cfc221347438f599e8d006621e3ead2dc6f7aae0fe`.
- Reproduction: `.venv/Scripts/python.exe docs/research/area5150/capture_match.py`.
- Machine-readable results: [capture_match.json](capture_match.json).

The script discovers the load address by locating observed contiguous 32-byte code blocks that occur only once in the released binary. Ninety independent windows agree on physical address `15990h` for the first file byte, corresponding to `CS=1589h` for a COM origin of `0100h`. No alternative address receives a vote.

The script then compares every captured `CODE` byte in that binary's address range. It also replays captured memory writes to account for self-modifying code. The comparison uses the recorded byte fields and addresses, not the capture's disassembly labels: the address visible in a disassembly row can belong to a later prefetch or another bus operation.

## Byte comparison

| Region | Captured fetch events | Distinct file offsets | Result |
|---|---:|---:|---|
| Initializer, COM `0100h–03FFh` | 20,445 | 733 | All match the static release |
| Entire observed effect | 53,054 | 11,766 | All match after applying observed self-modifications |

The only four fetches that differ from the original file occur at two self-modified operand bytes. Each changed value is preceded by a captured memory write of that exact value:

| COM offset | Initial byte | Subsequent fetched values | Captured writes |
|---|---|---|---|
| `0401h` | `00h` | `02h`, `04h` | `02h`, `04h`, `06h` |
| `25F0h` | `06h` | `0Ah`, `0Eh` | `0Ah`, `0Eh`, `12h` |

Thus there is no unexplained code mismatch in the observed initialization or effect fetches. The comparison covers observed fetches, not every byte or unexecuted path of the capture executable.

## Observed automatic acquisition

The interrupt entries below are identified by the first code fetch after an interrupt-acknowledge sequence. Unlike an arbitrary prefetch of a branch target, this ties each address to an observed hardware interrupt entry.

| Handler COM address | Entries | First code-fetch cycle(s) |
|---|---:|---|
| `032Ch` | 1 | 456,007 |
| `0340h` | 2 | 456,199; 456,358 |
| `0354h` | 1 | 456,555 |
| `036Dh` | 1 | 456,855 |
| `037Ch` | 1 | 457,131 |
| `03B6h` | 1 | 476,724 |
| `03CAh` | 1 | 496,142 |
| `03E3h` | 1 | 515,596 |
| Main effect `0400h` | 3 | 536,065; 615,713; 695,361 |

Both main-effect intervals are exactly **79,648 CPU cycles**.

At the first `0340h` entry, the recorded `IN` from port `3DAh` returns `F6h`, whose bit 0 is clear. At its second entry, that read returns `F7h`, whose bit 0 is set. The next hardware interrupt enters `0354h`; therefore the capture includes a successful repeat of the status-conditioned acquisition stage. The later `03B6h` status read returns `F7h` on its first observed entry, followed by entry to `03CAh`.

The captured parameter reads are also concrete:

- `CS:45E6h–45E7h` reads `45h,00h`, the word `0045h`.
- `CS:45E4h–45E5h` reads `FDh,13h`, the word `13FDh`.
- `CS:45E8h` reads `00h`, the low byte of the optional stretch control. Its high byte is not read in this captured decision and should not be described as independently measured.

These observed values agree with the released binary's defaults. The acquired hardware run therefore does not require assuming that someone manually patched those timing parameters before recording it.

## Relationship to the earlier SR frame analysis

The CSV contains 770,891 rows. The SR file contains 1,541,781 normalized samples. Comparing CSV row `n` with SR sample `2*n` gives zero differences for all six shared signals examined: VS, HS, DEN, INTR, DR0 and CLK0. This connects the byte-level analysis to the same signal sequence used in the earlier two-frame timing comparison despite the files' different `01`/`final_02` names.

## Limits

This is reanalysis of a published physical-machine capture; no new hardware was operated. It establishes that the released initializer's observed code and default parameters acquired the recorded stable effect. It does not measure a cold-boot population, expose every initial phase, prove unexecuted branches, or directly measure palette-latch/RGBI output edges. The publisher also states that A19 was not physically captured, so the physical addresses use the published decoder's reconstruction.

