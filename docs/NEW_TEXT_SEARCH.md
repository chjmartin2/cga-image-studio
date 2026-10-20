# 640x200 (1024 Colors): CPU/GPU text search

Choose **Composite → 640x200 (1024 Colors)**, select the composite model that
matches the target CGA card, open an image, and click **Convert**. This is the
CPU/GPU encoder previously named **640x200x1024 NEW**. It replaces the old
640×200 encoder in the application; there is one full-screen 1024-color entry.
The legacy encoder remains available to the developer comparison tool.

The mode uses an 80×100 character/attribute layout and full-screen 640×200
display program. “1024” is a historical label:
the NTSC simulation can produce many more apparent colors because a pixel's
color depends on nearby character patterns.

## Composite and RGB text previews

Use **Display: Composite / RGB text** beneath the output image to switch views
without converting again. Composite shows the simulated NTSC output. RGB text
shows the same encoded characters and attributes through the 16-color CGA RGBI
palette, including both glyph scanlines and bright backgrounds with blink off.
It previews how that text data would appear on an RGB monitor; it does not
optimize a separate RGB image. Zoom applies to either view.

PNG, lossless WebP, and GIF export save the selected view at native 640×200
resolution. COM, ASM, and DSK exports use the same character/attribute buffer
regardless of the selected display. During conversion, unencoded RGB text rows
remain black until their character data is ready.

## Conversion controls and progress

Image sizing, resize filter, input brightness/contrast/channel gains, and the
Old/New CGA composite preset still apply. Dithering offers **Error diffusion**
(the application's default), **Ordered**, and **None**.

- **Error diffusion:** finish each two-scanline character row, decode its actual
  NTSC output, and carry its Lab residual into future character rows. The next
  row is searched against its source plus accumulated error. Each row finishes
  all search/refinement stages before sending its residual onward.
- **Ordered:** apply the selected repeating threshold matrix to the RGB target
  once, then run the parallel search. Matrix sizes 2–16 and strength 0–3 use the
  existing application's conventions. Zero strength disables the perturbation.
- **None:** search the unchanged source target with independent character rows.

Diffusion method, strength, and serpentine direction are available. The diffusion
matches the existing .167a 640×200 encoder's **vertical/block** convention: retain
future-row kernel taps with their original weights, mirror horizontal offsets on
odd character rows when serpentine is enabled, and send top-scanline residuals to
future top scanlines and bottom residuals to future bottom scanlines. Same-row
taps are omitted because a complete character row is solved jointly. This is not
ordinary sequential pixel-by-pixel Floyd–Steinberg. Kernel **None** or zero
strength disables diffusion. In particular, retained Floyd–Steinberg weights sum
to 9/16; they are not renormalized. Atkinson retains the legacy divisor of 6.

Search depth, Shape versus color, and Polish remain hidden. Their values from
other modes do not affect the new conversion. Refinement runs automatically
until its search stages converge; there is no one-minute cutoff that silently
skips unfinished quality work. A final undiffused polish is not applied because
it could undo the intended error distribution.

The progress text identifies the selected backend, current search stage, and
objective improvements. **STOP** requests cancellation. A canceled or failed
conversion cannot be exported as a completed result. Changing the image, mode,
or conversion settings cancels the active new search; click Convert again to
use the new settings. Preview zoom and controls unused by this mode do not
cancel it.

On completion the status reports backend, search time, pass count, and the
achieved local convergence guarantee. Time in that message includes encoder
preparation and search; it excludes GUI rendering and export. First use can include device/kernel initialization
and compiled-code cache creation, so it can take longer than later conversions.
Actual runtime depends on the image, available hardware, and search convergence.

## What the search guarantees

With a fixed target, the decoder's finite horizontal support makes each
two-scanline character row an independent second-order chain. Error diffusion
fixes the current row's target after receiving preceding rows' residuals, then
optimizes that row. The new algorithm evaluates complete
candidate patterns in their actual context, then solves coupled row changes
with exact dynamic programming over progressively expanded proposal sets.
The incumbent is always available, and independent full-row rescoring rejects
changes that worsen the objective.

The default proposal widths are 8, 16, 32, and 64. Before the final 64-choice
refinement, two passes use different neighboring contexts to discover further
alternatives, then fuse 32 choices per cell. These passes broaden exploration;
they do not add a global certificate.

Exact row optimization applies to the supplied proposal sets. Full-domain
conditional scans support a single-cell local optimum against each row's fixed
search target: no one-cell replacement improves that target's objective within
the numerical tolerance. For error diffusion this is a causal per-row guarantee,
not an optimum of the complete image against its original source; changing an
earlier row would also change the targets received by later rows.
Coordinated choices omitted from the final proposal sets may still improve the
image. **There is no general global-optimality certificate or claimed percentage
of the exhaustive optimum.**

The search objective is the sum of squared CIE Lab distances to its fixed target
(original, ordered, or current diffused row). Reports distinguish the search
target from error measured against the original source. It uses all RGB channel
values produced by the simulator, with no
RGB444 palette reduction. The new preview preserves those full decoder colors;
the legacy preview's RGB444 quantization is unchanged. Better Lab error is a
measured property of this simulator and target, rather than a guarantee of
subjective preference or perfect reproduction on every physical CRT.

See [the research and algorithm analysis](research/640x200_new_search_research.md)
for decoder dependencies, the previous search's approximations, primary
references, and the distinction between exact restricted search and a global
solution.

## Optional acceleration for source installations

The base NumPy/Pillow installation remains usable. For compiled CPU scoring,
run from the Source folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-acceleration.txt
```

For an NVIDIA CUDA GPU, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cuda.txt
```

The CUDA requirements include the CPU acceleration package and CuPy's CUDA
runtime extra. A compatible NVIDIA driver is also needed. This development
environment has Numba 0.68.0 and `cupy-cuda12x` 14.2.0 installed. These packages
are optional; they do not change the old mode's algorithm.

The application probes CUDA at runtime and uses it when available. If the GPU
backend cannot initialize, it reports the reason and selects parallel CPU
scoring. Numba accelerates the CPU path when installed; NumPy remains the
fallback otherwise. CPU work is divided across independent tasks using the
available worker count (32 on the development workstation). On CUDA, both
candidate scoring and exact row dynamic programming run on the GPU; the row
fusion returns selected labels instead of transferring its full cost arrays
back to the CPU. Initialization failures are informational during a
successful fallback, and do not invalidate the eventual conversion.

Error diffusion serializes the 100 character rows, while candidate scoring and
the dynamic-programming transitions within each row retain GPU/CPU parallelism.
The dictionary, full-color lookup table, and candidate features are reused across
rows. Serial dependencies can increase runtime, while batching all columns of
the current row keeps GPU occupancy high. Quality and convergence are not reduced
to meet a time limit.

## Reproducible comparisons

See the [corrected error-diffusion validation](research/640x200_new_dither_validation_2026-10-19.md)
for matching-settings image comparisons and the GPU memory-layout regression.

Run the benchmark against an image you may use locally:

```powershell
.\.venv\Scripts\python.exe tools\benchmark_text_new.py path\to\image.png --backend auto
```

For the former K=64 search with a 5% polish comparison:

```powershell
.\.venv\Scripts\python.exe tools\benchmark_text_new.py path\to\image.png --backend cuda --legacy-k 64 --legacy-polish 5
```

The default legacy comparison is K=8 with no polish and no dithering. To compare
error diffusion in both encoders:

```powershell
.\.venv\Scripts\python.exe tools\benchmark_text_new.py path\to\image.png --backend cuda --dither Diffusion --legacy-k 64 --legacy-polish 5
```

Use `--diffusion-method`, `--dither-strength`, and `--serpentine` to match settings.
Chroma filtering is disabled for the legacy comparison. Both rendered results
are scored against the same original source in full RGB. The pixelwise Lab score
does not measure the full visual benefit of dithering: inspect the saved display
comparisons, especially gradients and large areas of similar color. The legacy
640×200 encoder does not implement Ordered, so the shared benchmark does not
offer that as a comparable setting.

Results go to ignored `artifacts/text-new-benchmark/` by default. Each run saves:

- Raw source, NEW, and legacy PNGs at 640×200.
- Nearest-neighbor 640×480 display images and a labeled comparison.
- The 16,000-byte character/attribute buffers.
- JSON with wall time, objective, RMS/mean Delta E, distinct decoded RGB color
  count, NEW diagnostics, source/code hashes, package versions, and settings.

Use `--backend cpu` to benchmark CPU operation, `--workers N` to select its
worker count, and `--order legacy-first` to examine startup/cache effects.
`--outdir` selects an empty output folder. `--help` lists all options. A run
keeps each completed encoder's report even if the later conversion fails or
is interrupted; incomplete results are explicitly marked.

## Export

After completion, COM, NASM source, and bootable DOS disk export use the actual
new character/attribute buffer and the existing full-screen display builder.
The default filename is `cga_640x200_1024c` with the chosen export extension.
Preview images and conversion timings
do not certify physical hardware behavior; hardware validation remains a
separate check. Use **Export > Image (PNG, WebP, GIF)** to save the full simulated
RGB output as PNG (the default) or lossless WebP. Both preserve more than 256
colors without palette reduction. GIF remains available with its 256-color limit.
