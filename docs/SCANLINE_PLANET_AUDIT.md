# Planet recovery and per-line tweaked palettes

Audited on 2026-10-19 using the owner's
`Desktop/TestImages/320x200/Landscapes-Nature/banded-planet-interleaved-320x200.png`.
The original remains untouched and is not added to the repository.

Source SHA-256:
`5e4d9c0e5babad55d5ce1b8de8b07d7de739ee84bf9137c9b9daf1d5051a27a4`.
It is a native 320x200 RGB PNG containing 12 exact CGA RGBI colors. No row
contains more than four distinct colors. Exhaustively comparing each source
pixel with every legal palette establishes these exact-color bounds:

| Allowed families | Fully recoverable rows | Maximum identical pixels |
| --- | ---: | ---: |
| Four standard families | 175 / 200 | 63,288 / 64,000 |
| Two tweaked families only | 91 / 200 | 56,603 / 64,000 |
| All six families | 200 / 200 | 64,000 / 64,000 |

These are exhaustive bounds on identical source pixels, not perceptual scores.
The image is **100% recoverable** using one palette per scanline, including with
a fixed black background. It requires both standard and tweaked families.

## Bug and correction

The independent-row palette builder interpreted Tweaked On as **tweaked only**,
discarding all four standard families before scoring. This restriction was left
over from an older exporter that preferred a constant mode register. Repeat
already included both families, and the N=1 exporter already supports mixed
per-row mode/color registers.

Tweaked On now adds the two tweaked families to the four standard families.
Tweaked Off retains the same four standard families. The candidate order keeps
standard palettes first for deterministic ties. Repeat uses the shared pool
without changing its candidate order or duplicating candidates. Multiwrite
profiles retain their existing standard-only UI restriction.

The controls now say **Off (standard)** and **On (standard + tweaked)**. Dither
projection, error transport, scoring and palette-uniqueness rules are unchanged.

## Actual encoder results

Native dimensions, background Per line, dither-aware search on, forced unique
foregrounds off, default dither strengths and serpentine setting:

| Conversion | Identical pixels |
| --- | ---: |
| Before: Tweaked Off, no dithering | 63,268 / 64,000 (98.85625%) |
| Before: Tweaked On, no dithering | 56,156 / 64,000 (87.74375%) |
| After: Tweaked On, no dithering | 64,000 / 64,000 (100%) |
| After: Tweaked On, ordered dithering | 64,000 / 64,000 (100%) |
| After: Tweaked On, Floyd–Steinberg diffusion | 64,000 / 64,000 (100%) |

Each corrected run chose 175 standard rows and 25 tweaked rows. The old
conversions fall below the exact-color bounds because their perceptual scoring
does not maximize identical-pixel counts. With an exact representation available,
the corrected renderer obtains zero error without changing that scoring rule.

**Force unique palette per scanline must be off for exact recovery.** An exact
reachability check over all legal foreground choices becomes impossible at
zero-based row 9 when adjacent identical foreground combinations are forbidden.
That setting deliberately excludes palettes this source needs on adjacent rows.
Use native dimensions and no tone/color adjustments to preserve the source.

Reproduce the feasibility audit and conversions with:

```powershell
.venv\Scripts\python.exe tools/audit_scanline_recovery.py <source.png> --render
```

Reports and comparison PNGs go into ignored `artifacts/planet-audit/`.
The tests in `tests/test_scanline_tweaked_inclusion.py` use generated legal
images with all six families and exercise None, Ordered and Diffusion, with
dither-aware search on/off, fixed/per-line backgrounds, and mixed-register COM
payloads with the border option checked/unchecked. Existing background,
foreground-uniqueness, Repeat and UI/export tests cover the surrounding paths.
COM payload equality is distinct from the existing border timing qualification;
this change makes no new emulator/hardware timing claim.

Validation: 154 encoder/export regression tests passed. All 12 UI tests passed
when run in separate processes. Combined UI runs intermittently failed during
Tcl/Tk initialization before application code, with library-read errors; those
failures are recorded as a test-runtime limitation, not successful combined runs.
Compilation and whitespace checks passed.
