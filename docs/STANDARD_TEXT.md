# General-purpose CGA RGB text

Implemented in the source application on 2026-10-19. Run `run_cga_v167.cmd`,
choose **RGB Text**, then **40-column Text (RGB)** or **80-column Text (RGB)**.
Character height **8** gives standard **40x25** or **80x25** text.

Each cell searches all 256 characters in the bundled IBM CGA font and all
16 foreground x 16 background combinations. Blink is disabled so bright
backgrounds are available. Two colors per character remain a hardware limit.
The existing graphics and text-trick converters keep their own algorithms.

## Selectable conversion controls

| Character matching | What the distance measures |
| --- | --- |
| Pixel (linear RGB) | Squared color error at every pixel, in linear light |
| Average 2x2 | Squared difference between each 2x2 block's average colors |
| Average 4x4 | The same comparison at a coarser scale |
| Average whole character | Mean color/coverage of the entire cell; ignores spatial arrangement |
| DCT (structure), default | All DCT coefficients, with more weight on lower frequencies |
| Balanced (multiscale) | 40% pixel, 30% 2x2, 20% 4x4, 10% whole-cell error |

Averaging compares both the source and the rendered candidate. Partial blocks
at unusual character heights receive proportional area weights. Whole-cell
averaging can choose visually arbitrary patterns with similar coverage; it is
an explicit experimental option, not a recommended default.

An unweighted orthonormal DCT has exactly the same squared error as pixel
matching (Parseval's identity). This implementation deliberately weights each
coefficient by `1 / (1 + 8*((v/height)^2 + (u/8)^2))`. It emphasizes broad shapes
and color areas without discarding the higher frequencies. It is a different
objective, not a guarantee of better-looking art. Scores from different
matching methods are not directly comparable.

New text sessions default to **DCT (structure)** with stock weights (8, 1, 1, 1),
**Original** preprocessing and **Reduce to CGA colors before matching** unchecked.
Consequently no preconversion dithering runs. Switching modes preserves deliberate
user adjustments rather than resetting them.

### Live DCT Tweaker

**DCT Tweaker** selects standard DCT and opens four sliders:

- **Broad-shape weighting**, 0-32 (default 8): larger values discount fine detail.
- **Fine-detail falloff**, 0.25-3 (default 1): controls how steeply frequency
  weights decline.
- **Average-color importance**, 0.25-4 (default 1): multiplies the DC coefficient's
  squared-error weight, independently of the other frequencies.
- **Vertical / horizontal emphasis**, 0.25-4 (default 1): above 1 discounts rapid
  vertical changes more; below 1 discounts rapid horizontal changes more.

The generalized weight is
`(1 + structure*((v/height)^2*vertical + (u/8)^2/vertical))^(-falloff)`,
with `color` multiplying its DC entry. Every coefficient remains present. Setting
structure to zero and color to one in standard DCT gives the ordinary pixel squared-error
objective through an orthonormal transform.

Slider changes refresh the conversion after a 250 ms pause. Superseded work is
cancelled and cannot publish stale results. The exact prepared input is reused
while only matching weights change; resizing, simplification and dithering are
not repeated. Conversion itself still takes its normal processing time, so this
is an automatic interactive preview, not a guaranteed video frame rate.
Restore defaults returns to the original DCT weighting. The saved output uses
the latest completed settings; export is blocked while a new result is pending.

### Optimize text settings

The toolbar **Optimize** button appears for both 40- and 80-column RGB text.
It keeps the selected column count, character height, CGA-reduction checkbox,
image composition (Fit/Fill/Stretch), input adjustments and DCT Tweaker weights.
The checkbox is a fixed choice: unchecked candidates never prequantize; checked
candidates all reduce to CGA colors and search the dither settings.

Every matching method, preprocessing option and resize filter is evaluated:
6 x 4 x 9 = **216 combinations** with color reduction off. With it on, Optimize
also visits no dithering, all nine nontrivial diffusion kernels in both scan
directions, and every ordered matrix size from 2 through 16. Diffusion strength
uses 0, 0.25, 0.5, 0.75, 1; ordered strength uses 0 through 3 in 0.25 steps.
Both exact current strengths are also included. Zero strength and the None
diffusion kernel share the equivalent no-dither case. This gives **54,648**
combinations at default strengths; arbitrary current strengths can add cases.
The continuous sliders are sampled, not exhaustively optimized over real numbers.
This larger search can take much longer than a normal conversion.

The common score compares the **complete rendered image** with one fixed
reference: the adjusted original resized using Lanczos and the selected
composition, without simplification, dithering or CGA reduction. The hardware
margins are identical for reference and candidates. The existing CGA visual
score combines normalized squared CIEDE2000 at the pixel scale and two successive
2D smoothing scales (weights 0.2, 0.5, 0.3), horizontal and vertical luminance-edge
error, and a penalty for collapsed contrast. Windows cross character boundaries.
Each candidate is judged against this reference, never its own simplified input.
This is a visual heuristic, not a guarantee of the owner's artistic preference.

Exact duplicate prepared rasters share matching work; no low-scoring shortlist
discards unique candidates. Without CUDA, worker processes use available CPUs,
bounded by job count, free memory and the Windows process-pool limit. With CUDA,
CPU processes prepare/dither inputs and a small shared-GPU pipeline matches cells
and scores outputs. When no dithering is needed, preparation processes are
unnecessary. This avoids creating a competing CUDA context for every CPU worker.
CPU processes limit BLAS to one thread with threadpoolctl. Pending work and
caches are bounded. Completion order does not change tie-breaking. STOP, changed
inputs, a newer conversion or closing Studio cancels the search.

The winner's controls, prepared preview, output and encoded cells are installed
together. Its cached cells feed all exports; Convert with the selected settings
reproduces them. The status shows best and starting visual errors. A detailed
in-memory report is available as `standard_text_optimization_report`, including
all tested settings, scores, exact-equivalence groups and search timing.

In the initial CPU-only measurement, the complete unchecked search on Inspector Gadget
took 4.8 seconds for 40 columns (8 distinct preparation jobs) and 24.1 seconds
for 80 columns (24 jobs), using 8 and 24 CPU workers respectively. Both covered
all 216 combinations. Relative to Original + DCT + Nearest, the visual score
improved from 0.013339 to 0.012773 and 0.008792 to 0.008266. Both selected Pixel
matching + Cartoon simplify + Nearest. These are score improvements on one image,
not proof of a universally better-looking method. Reports and rendered samples
are under `artifacts/standard-text-validation/optimize/`.
The subsequent CUDA run chose the same winners and visual scores for both column
counts; its reports are under `artifacts/standard-text-validation/optimize-cuda/`.

### GPU acceleration

Normal text conversion, DCT Tweaker and Optimize automatically use a working
NVIDIA CUDA GPU through CuPy. The status bar and diagnostics identify CUDA or
CPU fallback. The optional dependencies are in `requirements-cuda.txt`; this
implementation does not provide an AMD/Intel GPU backend. Missing libraries,
driver failures or device/allocation errors fall back to the same full CPU
search. Explicit `backend='cuda'` in the Python API raises instead of falling
back, which supports GPU qualification tests.

GPU scoring retains all characters, color pairs and DCT coefficients and uses
float64, with no half-precision or shortlist shortcut. Device batches are bounded
by free VRAM. Averaging can give different rendered patterns exactly equal
feature scores; when GPU roundoff could affect their order, the original CPU
arithmetic resolves those ambiguous batches. This preserves the tested CPU
rendered output instead of allowing GPU tie choices to change the visual score.

Native checks passed on the development machine's **NVIDIA GeForce RTX 3090
(24 GB)**. After CUDA initialization, DCT encoding of Inspector Gadget took
about **23 ms at 40 columns** and **48 ms at 80 columns**, versus approximately
314 ms and 618 ms on CPU, excluding preprocessing and GUI updates. The first
CUDA call took about 610 ms including initialization. These are measurements
on one machine and image, not universal performance guarantees; Optimize also
performs preprocessing, other matching methods and whole-image scoring.

**Text preprocessing** offers Original, Downsample 2x, Downsample 4x, and
Cartoon simplify. Downsample uses area averaging and nearest-neighbor expansion;
Cartoon simplify uses a 3x3 median filter and four-bit-per-channel posterization.
The median filter removes small details/noise, while posterization keeps 16 levels
per RGB channel (up to 4,096 colors, not the sixteen CGA colors). It can simplify
flat areas but also erase useful fine detail. CGA palette reduction is a separate
checkbox. This is a basic filter, not semantic cartoon generation.

In the **Input** pane, select **Text input** and click **Preview text input** to
inspect the fully prepared raster without searching characters. **Source** shows
the original with input adjustments. Convert also publishes the exact raster it
passes to matching, after scaling, preprocessing, and optional color reduction
and dithering. The preview uses nearest-neighbor display scaling and output pixel
aspect; its caption reports the actual matching dimensions. Settings or source
changes hide a stale intermediate preview until Preview text input or Convert is
run again. Changing just the view does not invalidate a finished conversion.

**Reduce to CGA colors before matching** optionally converts the intermediate
image to the sixteen CGA colors. Turning it on reveals None, Ordered, and Error
diffusion, including the existing matrix, kernel, strength and serpentine
settings. Dithering runs on this intermediate raster before character matching.
There is no second diffusion pass between chosen character cells. Without this
checkbox, matching uses the full-color source after the normal input adjustments
and selected preprocessing. Original with this checkbox off is the baseline.

Preconversion diffusion bounds corrected linear RGB to [0,1] before both palette
matching and outgoing residual calculation. The previous implementation matched
the bounded color but propagated the unbounded residual, allowing saturated
regions to accumulate impossible channel error and bleed into later rows.
Diffusion strength is limited to 0-1 (the UI range); Optimize canonicalizes to
the same effective range. Each kernel weight is applied once, with no edge or
downward-weight renormalization; Atkinson retains its intentional 75% transport.
Useful signed error still crosses scanlines, and every conversion/preview/search
trial starts from fresh diffusion state. This fix affects optional text input
prequantization, shared by all text matching methods.

Pipeline: input adjustments -> resize/sampling -> optional simplification ->
optional CGA-color quantization/dithering -> character/attribute search ->
render the exact encoded cells. PNG/WebP, COM, ASM, disk and Open in MartyPC all
use that result. STOP cancels the worker; settings changes invalidate exports.

## Character height and hardware

The selector and encoder accept **2 through 8 scanlines per cell**. Eight shows
the full ROM glyph; smaller values show only its top rows. Heights above eight
were removed at the owner's request. No font stretching or custom font upload
is involved.

The horizontal grid stays 40 or 80 columns. The UI reports cell rows and video
memory use. A character and its attribute occupy two bytes. Standard layouts
use 2,000 and 4,000 bytes; the densest supported layout uses 16,000 of 16,384.
One-scanline cells are omitted: this static 262-line frame cannot fit the
6845's vertical-total and vertical-adjust register limits at that height.

For arbitrary heights, vertical sync is quantized to character rows. With
`h` scanlines/cell, the top margin is `224 % h`; the cell row count is
`floor((200 - margin)/h)`. Remaining space is black. The preview reproduces
these margins so the exported display fits the standard 200-line aperture.
The input is resized to the active image area, then placed into the preview.
40-column exports have twice-wide hardware dots; saved rasters are 320x200,
versus 640x200 for 80 columns. Studio applies display aspect correction.

Exports initialize BIOS mode 1 or 3, blank video while loading, program static
CRTC timing, disable blink and cursor, and use a black border. Press a key to
return to BIOS mode 3 and DOS. These exports target CGA; EGA/VGA-specific font
and timing support is future work.

Primary hardware/implementation references:
[MartyPC CGA notes](https://book.martypc.net/display-graphics/cga),
[MartyPC 6845 notes](https://book.martypc.net/display-graphics/6845), and
`external/martypc/crates/lib/marty_core/src/devices/cga/mod.rs`
(`get_hchar_glyph_row` / `get_lchar_glyph_rows`, raster address masked with 7).

## Exhaustive matching without redundant rendering

For linear feature transform T, glyph mask M, foreground f and background b,
the rendered features are `T(M)*f + T(1-M)*b`. Expanding squared error leaves
only precomputed mask norms, mask cross-products, source correlations, and
sixteen color vectors. Pixel matching has disjoint foreground/background
support, allowing independent exact color minimization for each glyph.
The other methods evaluate all 256 foreground/background pairs per glyph.

All six matching methods exhaustively minimize independent cell scores
(within floating-point arithmetic). No glyph shortlist is used. These objectives
do not optimize inter-cell relationships, semantic recognition or artistic composition.

CPU NumPy batches keep the largest candidate-score array around 8 MiB. CUDA uses
larger VRAM-bounded batches. Conversion runs in a background thread and selects
the available backend; Optimize additionally parallelizes candidate work. There
is no neural model. In the initial CPU baseline, a 40x25 conversion
of the 320x200 banded planet took about 0.08 seconds for pixel matching and
0.30 seconds for DCT or multiscale matching, excluding UI/export. Optional
Python error diffusion takes additional time; these are observations, not
hardware-independent performance promises.

## Validation

- Literal rendered-candidate exhaustive oracle: all six cell-only matching objectives,
  tested at both ordinary and cropped character heights.
- Exact recovery of generated legal CGA text images for Pixel, DCT and Balanced.
- Geometry/register/memory checks for all 14 supported column/height combinations.
- All 14 currently supported COM configurations were included in the original
  62-configuration run that matched the native MartyPC visible RGB
  framebuffer pixel for pixel, including margins and arbitrary bright
  backgrounds. Random character/attribute payloads; direct COM load after BIOS;
  2,000,000 execution cycles per case. This is emulator evidence, not physical
  card or every-monitor qualification. Keyboard exit/reentry was not part of
  this framebuffer comparison.
- Actual Tk conversions for both modes and every metric; preprocessing and
  prequantization routing; cancellation, failure, superseded workers and stale
  export rejection; exact PNG/WebP and COM/ASM round trips; bootable disk and
  shared MartyPC launch routing.

Run `python -m pytest tests/test_standard_text.py tests/test_standard_text_ui.py -q`.
The updated focused run passed 61 tests, including exact agreement between the
prepared preview and matching input, preparation without matching, stale-preview
hiding, and view changes preserving export validity. The existing all-mode
layout check passed another 64 subtests. Local emulator captures and JSON results are in
`artifacts/standard-text-validation/`.

Additional optimizer/tweaker validation: full unchecked option coverage, all
dither option families/matrix sizes/directions and exact current strengths,
fixed-reference scoring, serial/parallel winner equality, selected-setting
replay, real quantized candidates, cancellation, slider debounce/latest-value
behavior, prepared-input reuse, and UI export validity. Run
`python -m pytest tests/test_standard_text_optimize.py tests/test_standard_text_controls.py -q`.
GPU checks in `tests/test_standard_text_cuda.py` cover all six cell-only metrics at cropped
and full character heights, CPU/GPU score and rendered-image parity, missing or
failed devices, real hybrid CPU/CUDA optimization, replay and cancellation.
## TODO: human-artist conversion

Perceptual DCT and Boundary-aware DCT were evaluated and removed at the owner's
request. Standard DCT remains the preferred baseline. Semantic artist-style
conversion and broader joint optimization remain future research, not active options.

1. Investigate **larger viewing scales** and
   display-aware whole-image evaluation. Reward contour continuity and preserve negative
   space; avoid fragmented edges and distracting texture in flat regions.
2. Build source abstractions that preserve silhouettes, face landmarks, text and
   small salient features. Allow controlled exaggeration or detail removal rather
   than trying to reproduce every source pixel. Keep abstraction strength explicit.
3. Investigate **joint multi-cell moves** and larger regions, with visual
   comparisons against standard DCT before introducing another option. Compare local search,
   beam/graph methods and relax-and-project approaches under the same global score;
   do not assume Viterbi solves two-dimensional image dependencies.
4. Consider a learned perceptual/ranking model or artist examples only after a
   representative evaluation set exists. Enforce the fixed CGA font and two-color
   cell constraints on every final render. Use GPU batches if whole-image or
   patch scoring becomes the bottleneck.
5. Evaluate paired outputs at normal display size with the owner: faces, cartoons,
   photographs, logos, gradients and fine line art. Judge recognizability, palette
   choices, spacing and visual coherence as well as color error. Preserve the
   reproducible baseline and expose tradeoffs rather than declaring one metric
   universally best.
