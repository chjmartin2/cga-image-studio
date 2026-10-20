# NEW encoder dithering validation — October 19, 2026

The NEW mode now supports error diffusion, ordered dithering, and None. Error
diffusion follows the existing .167a text encoder's row-pair feedback convention,
while retaining full candidate scoring and all refinement widths. Existing modes
keep their encoder behavior. The application defaults to Error diffusion,
Floyd–Steinberg, strength 1, and serpentine; NEW now honors these controls.

## Corrected, matching-settings photograph comparison

Hardware: NVIDIA GeForce RTX 3090, 32 CPU threads. Both encoders used Old CGA,
640×200 Lanczos stretch, Floyd–Steinberg at strength 1, serpentine enabled, and
the same original RGB source. Legacy used K=64, shape weight 1, 5% polish, and no
chroma low-pass. NEW retained widths 8/16/32/64, both alternate-context passes,
and refinement to convergence for every character row.

| Image | NEW encoding | Legacy encoding | NEW RMS Delta E76 | Legacy RMS Delta E76 |
| --- | ---: | ---: | ---: | ---: |
| Raiders | 15.90 s | 174.94 s | 9.311 | 11.531 |
| Picard | 13.56 s | 180.73 s | 12.250 | 14.582 |

These are individual measurements, not runtime guarantees. Encoding includes
preparation and excludes saved-image rendering. The corrected NEW results were
measured sequentially in one process; Picard can reuse startup caches. Completed
legacy results were reused after fixing the NEW GPU path, since the legacy
implementation and its inputs were unchanged. Reports record both builds' source
hashes and the reused report provenance. Machine-readable summary:
[validation JSON](640x200_new_dither_validation_2026-10-19.json).

Both scores use the full NTSC decoder RGB and the original source, not the
diffusion-adjusted target. The raw per-pixel score is a diagnostic, not a rating
of dithering's visual quality. Inspect the actual comparisons:

- [Raiders: source, NEW, legacy](../../artifacts/text-new-diffusion-raiders-verified/comparison-display.png)
  and [full report](../../artifacts/text-new-diffusion-raiders-verified/report.json).
- [Picard: source, NEW, legacy](../../artifacts/text-new-diffusion-picard-verified/comparison-display.png)
  and [full report](../../artifacts/text-new-diffusion-picard-verified/report.json).
- [Smooth gradients: source, None, diffusion, ordered](../../artifacts/text-new-dither-gradients/comparison.png).
  All three full-size searches converged and produced different encoded buffers.
  Diffusion distributes transitions across rows; the fixed ordered pattern leaves
  more visible vertical bands in this test. This visual observation is specific
  to the tested settings and source.

## GUI and export verification

An actual Tk conversion of Picard completed in **21.73 seconds**, including GUI
processing. Its complete 16,000-byte character buffer and every RGB preview pixel
matched the corrected command-line conversion. The 16,777 distinct colors
survived PNG and lossless WebP export exactly. Changing diffusion strength then
invalidated the output for export. [GUI report](../../artifacts/text-new-dither-gui-verified/report.json).

The focused final run passed **73 tests and 210 subtests**. Automated checks
cover all nine kernels, source-pixel offsets, row-pair routing,
serpentine, strength, zero/None behavior, ordered matrices, cancellation, stale
output rejection, resource reuse, and exact CPU/GPU comparisons on tractable
problems. Source and full-color export tests are included in the focused suite.

## GPU layout correction discovered during validation

An early GUI/CLI comparison disagreed despite identical source bytes and settings.
`numpy.argwhere` produces Fortran-order position arrays. CuPy could preserve this
layout for short batches, while raw CUDA kernels read interleaved row/cell pairs.
Late refinement passes therefore read incorrect positions and could access
unrelated memory. All raw CUDA inputs now explicitly use contiguous row-major
layout. Regression tests cover short and split batches, non-C-contiguous source
arrays, every candidate score, restricted candidate domains, repeated runs, and
background-thread execution.

The first implementation's GPU numbers, including the early 13.36-second
diffusion result, are superseded. They remain preserved in their original local
artifacts. The corrected table above and GUI/CLI byte comparison are the accepted
validation. The initial no-dither benchmark report is also marked superseded;
its GPU results do not establish current convergence or quality.

## Reproduce

```powershell
.\.venv\Scripts\python.exe tools\benchmark_text_new.py test_images\raiders-of-the-lost-ark.webp --backend cuda --dither Diffusion --serpentine --legacy-k 64 --legacy-polish 5
.\.venv\Scripts\python.exe tools\benchmark_text_new.py test_images\picard_input_copy.bmp --backend cuda --dither Diffusion --serpentine --legacy-k 64 --legacy-polish 5
```

Use an available local input image if these unreviewed samples are absent. The
benchmark preserves full RGB PNGs and cell buffers. CPU fallback remains
available; full-image CPU timings were not measured in this validation.
