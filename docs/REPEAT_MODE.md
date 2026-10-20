# Repeat-mode diffusion and palette constraints

The 2026-10-19 correction fixes downward color bleeding and requires every
slot in a repeating cycle to have a different foreground three-color combination.
A different background never makes a repeated foreground combination eligible.
The entire cycle then repeats down the 200-row image.

Repeat's standard pool has four foreground combinations. Enabling Tweaked adds
the two tweaked combinations, rather than replacing the standard pool. Adjustable
backgrounds offer 2–6 rows; choosing 5 or 6 automatically enables the tweaked
combinations. A named fixed background offers up to four rows with Tweaked off
or six with it on. Explicitly turning Tweaked off reduces a longer cycle to four rows, with an
explanation beside the control. Independent-row mode now uses the same additive
family selection; see [the planet recovery audit](SCANLINE_PLANET_AUDIT.md).

Background choices default to **Adjustable**, followed by **Forced No Repeats**
and all 16 CGA color names. A color name forces that background for the whole
image. Forced No Repeats optimizes the backgrounds with an inequality constraint
on every adjacent pair, including the cycle wrap; nonadjacent reuse remains
legal. Three-row cycles therefore require three backgrounds, while four-row
cycles can alternate two. This constraint never relaxes foreground uniqueness.

## Excess error at color boundaries

The old Repeat renderer bounded corrected linear RGB for palette matching, but
subtracted the chosen color from the unbounded value when calculating error.
Unavailable colors could therefore accumulate a large residual and transport it
into later image regions. The correction uses the same value, bounded to `[0,1]`,
for matching and residual calculation. Signed error still crosses rows with the
selected kernel and strength; the renderer does not reset error at each row or
project away colors that a following palette can supply.

In a fixed legal two-palette Floyd–Steinberg test, the old maximum transmitted
residual was 61.616 linear units; the corrected maximum was 1.0. The first 16
gray rows below a bright patch had 83.5% less mean-color error. A separate Picard
comparison retains the exact previous source and palette schedule, and its
legacy oracle reproduces the previous output byte-for-byte. Bounding the
residual alone reduces the image score from 0.03326 to 0.02430 and visibly clears
much of the downward cyan/magenta bleeding. These measurements isolate the
renderer change from palette selection; they do not claim all dithering artifacts
are eliminated. Reports and images are under `artifacts/repeat-diffusion-fix/`.

The mechanism is consistent with the color-boundary smear caused by accumulated
out-of-gamut quantizer inputs discussed by Monga, Damera-Venkata and Evans in
[Image Halftoning by Error Diffusion: A Survey of Methods for Artifact Reduction](https://users.ece.utexas.edu/~bevans/papers/2004/artifactReduction/jeiErrorDiffArtifactReduction.pdf).
The code change and numerical evidence above are specific to this implementation.

## Search and export

The October 19 efficiency pass retains the same candidates, search objectives,
tie-breaking and diffusion arithmetic. It prepares fixed-palette CIEDE2000
components outside the pixel loop, caches nearest-color choices only for exact
float64 corrected-RGB/palette matches (8,192-entry bound), and prepares the
reference-image scoring pyramid once per conversion. Output-pyramid smoothing
and Lab conversions are reused between score terms. Restricted phase searches
omit color-mask bits outside their target union, preserving numeric mask order;
shortlist deduplication uses a set while retaining the original selection order.
See [performance evaluation](REPEAT_PERFORMANCE.md) for measured timings and
exact before/after validation.

The exact additive phase search now processes one foreground group at a time.
Its state records assigned cycle phases and the combined color mask. All legal
background variants compete for one free phase; descending phase-count updates
prevent that foreground group from occupying a second phase. This retains all
legal orders and background choices under the proxy objective. Both the initial
screening and the post-dither phase search use the same constraint.

Actual dithered search still evaluates a bounded set of unions and cycles; it
does not certify a global dither optimum. Tiny independent exhaustive searches
check the exact proxy stages, including repeated color masks, tied costs and
multiple background variants in a foreground group.

With Forced No Repeats, broad union screening uses the unconstrained phase
cost as a lower bound. Shortlisted unions are solved with an exact additive ring
DP before free-union dithering and again during final cycle selection. For each
foreground subset it considers all phase orders, retaining the starting and
latest background plus coverage of colors missing from the foreground union.
Closing the ring excludes a repeated first/last background. Background-register
variants remain separate even when they produce identical visible color sets.
This avoids rejecting good alternate backgrounds just because the unconstrained
optimum happened to repeat one. The final dithered shortlist remains bounded.

Exports reject repeated foreground combinations, a mismatch with a selected
fixed background, or any adjacent background repetition under Forced No Repeats.
Mixed
cycles use the existing N=1 COM path containing 200 interleaved mode/color-register
pairs. Constant-mode cycles retain the existing compact color-register table.
Independent decoders verify both table layouts and all 64,000 preview pixels;
ASM round trips and boot-disk/Marty routing are also checked. This is data-path
validation, not new physical-hardware timing qualification.
