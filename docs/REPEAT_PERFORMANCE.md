# Repeat-mode search efficiency, October 19, 2026

## Finding

The major cost is repeatedly rendering and scoring candidate images with real
dithering. The existing search evaluates up to ten unrestricted color-union
images, then up to six legal cyclic images. It batches candidates, but diffusion
still visits every pixel sequentially within each raster.

A cProfile run of the 320x200 Picard six-row Forced No Repeats case took 19.64
seconds with profiling enabled. Candidate rendering accounted for 15.53 seconds
(79%); the phase/ring search functions accounted for approximately 2.26 seconds
(12%). The original perceptual-distance function was called 128,081 times and
accounted for 11.79 cumulative seconds. Image scoring added 1.45 seconds.
These figures describe one profiled case; profiler overhead differs from normal
conversion timing, and nested cumulative times must not be added together.

## Implemented reductions

- Prepare constant palette Lab component views and unadjusted chroma once per
  row, instead of repeating array-axis setup and palette chroma calculation for
  every pixel. G-adjusted palette hue/chroma still depend on the target pixel
  and are recomputed. The CIEDE2000 expression and arithmetic order are retained.
- Reuse nearest-color choices when the full ordered palette batch and corrected
  float64 RGB batch match exactly. Keys contain the original bytes, with no
  rounding or reduced precision. A per-render LRU cache holds at most 8,192
  entries. Only matching is cached: black protection and signed error transport
  still execute for every pixel. Repeated colors benefit most.
- Prepare the fixed source's Lab pyramid, edges and luminance statistics once
  per conversion. Reuse rendered pyramid data between score terms and omit
  smoothing whose result was discarded. Score arithmetic remains identical.
- In target-restricted phase searches, omit mask bits outside that target union.
  For example, a nine-color target needs 512 masks instead of 65,536 in a
  sixteen-color pool. Expansion preserves the original public result shape.
  The mapping preserves numerical order, including predecessor tie-breaking.
- Use set membership for shortlist deduplication while retaining the existing
  ordered selection. This removes repeated linear scans of the growing list.

Candidate counts, quality objectives, palette/background rules, diffusion
kernels, clipping, strength, serpentine traversal and final winner selection
remain the same. Changes are confined to the Repeat engine. The shared color
and ordinary scanline engines were not modified.

## Full-size before/after measurements

Each pair ran sequentially in one process on the same Windows 11 machine with
NumPy 2.4.6. These are one measured pair per case, not repeated-run medians or
portable performance guarantees. Timing covers engine conversion, excluding
file loading and COM construction. Sources are the existing 320x200 Picard and
Gadget scanline-validation inputs.

| Input/settings | Before | After | Less time |
|---|---:|---:|---:|
| Picard, 2 rows, Adjustable, Floyd-Steinberg | 14.74 s | 13.08 s | 11.3% |
| Picard, 6 rows, Forced No Repeats, Floyd-Steinberg | 17.80 s | 14.63 s | 17.8% |
| Gadget, 2 rows, Adjustable, Floyd-Steinberg | 14.57 s | 8.25 s | 43.4% |
| Picard, 6 rows, Forced No Repeats, Ordered | 6.83 s | 6.33 s | 7.3% |
| Picard, 6 rows, Forced No Repeats, None | 6.07 s | 5.64 s | 7.1% |
| Picard, 3 rows, forced Brown, Floyd-Steinberg | 14.85 s | 12.48 s | 15.9% |

All six cases produced exactly equal RGB bytes, complete palette schedules,
exported COM bytes and every non-timing search diagnostic, including scores.
Comparison used a frozen copy of the engine taken before this efficiency pass.

## Validation and reproduction

113 focused tests and 165 subtests passed across:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_repeat_performance_parity.py tests/test_repeat_engine.py tests/test_repeat_diffusion_bounds.py tests/test_repeat_background_cycle.py tests/test_repeat_palette_families.py tests/test_mode_switch_repeat_export.py -q
```

Coverage includes exact prepared-distance/scoring parity, duplicate palette
entries, achromatic targets, strided arrays, single-pixel dimensions, cache
hits/eviction/palette separation, every diffusion kernel and both traversal
directions, dense-vs-compressed DP costs and tied paths, constraints and exports.
The transport-observation test disables matching memoization while recording
every corrected pixel, so skipped duplicate Lab calls do not hide its probes.

Fifteen additional frozen-engine comparisons cover repeat lengths 2-6, all
three dither families, fixed Brown, Atkinson at 70%, both traversal directions,
ordered matrix 2 at 80%, random colors, black and white regions. Pixels,
palettes and all non-timing diagnostics matched exactly.

Local evidence is in the ignored `artifacts/repeat-performance/` directory:
`reference_repeat.py` preserves the original engine; `benchmark.py --engine
paired` runs the six full-size comparisons; `paired.json` contains timings,
hashes, palettes and diagnostics; `reference-picard-6-no-repeat-fs.txt` contains
the original profile; `randomized_parity.py` reproduces the additional cases.
These local inputs and artifacts are not publication assets.

## Remaining cost

The remaining dominant work is target-dependent perceptual color matching inside
diffusion. A compiled implementation could reduce small NumPy-call overhead
substantially, but it needs separate numerical-parity qualification: changing
floating-point operations or transcendental implementations can change close
ties and propagate into later pixels. Parallelism is available across independent
trials; adjacent diffusion rows have actual data dependencies. No GPU or new
worker execution path was introduced in this pass.

The search still has the same bounded dither shortlist and exact additive proxy
stages. These speedups do not turn it into a globally exhaustive dither search.
