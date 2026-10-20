# Research and design: 640x200x1024 NEW

Research date: October 19, 2026. This document distinguishes mathematical
guarantees from practical search heuristics. Runtime and visual quality require
measurements on real images; neither a sub-minute conversion nor a small global
optimality gap follows from the algorithm alone.

Current implementation measurements are in
[the corrected diffusion validation](640x200_new_dither_validation_2026-10-19.md).
The [initial benchmark report](640x200_new_benchmarks_2026-10-19.md) preserves
earlier no-dither results, superseded after a GPU memory-layout correction.
Prototype timings below remain historical development measurements.

## What the existing converter actually optimizes

The full-screen text mode has 80 by 100 character cells. A character and its
foreground/background attribute determine two rows of eight RGBI samples.
The NTSC simulator then converts each complete scanline to RGB. “1024 colors”
is a historical mode label, not a limit on the neighboring-pattern-dependent
colors the simulator can produce.

Inspection of `cga_v167.py` found these consequential details:

1. `_build_all_candidates_array_640x200` enumerates 24,496 character/attribute
   representatives. Comparing their actual two-row RGBI patterns gives 23,536
   distinct patterns; exact pixel deduplication can remove the remainder.
2. `encode_image_to_640x200_1024_viterbi` first retains K candidates using DCT
   features of each candidate decoded against black surroundings. Candidates
   rejected here never enter the row search, even if real neighboring colors
   would make them better.
3. Its transition cost combines a previous candidate and current candidate
   with a **source-quantized RGBI right neighbor**. That right neighbor is not
   the candidate eventually selected for the next cell. The dynamic program
   is exact for its restricted proxy costs, not for the final rendered row.
4. The decoder's output at pixel x depends on RGBI samples x-5 through x+6.
   Therefore some pixels depend on three adjacent character cells. A state
   containing only the current candidate loses relevant history.
5. Existing polish searches all candidates for selected individual cells, but
   its 24-pixel local decode inserts black beyond the immediate neighbors.
   Replacing a cell beginning at s affects output pixels s-6 through s+12.
   Correctly decoding that entire changed area needs input s-11 through s+18,
   including portions of the second neighbors. The artificial local borders
   can change the polish score. This finding does not alter the legacy mode.
6. Error diffusion changes later rows' targets and introduces a serial
   dependency. Independently optimizing rows requires a fixed target, or
   explicitly freezing a target between separate passes.

The cost is also substantial: old candidate pruning materializes large feature
distance arrays, and each transition repeatedly constructs and decodes two
24-pixel windows. The legacy polish repeats broad integer-array operations and
Lab conversion for every candidate, even though most signal context is shared.

## Mathematical structure: difficult does not imply NP-hard here

For a fixed target, each of the 100 cell-rows is independent. Define
`F[x,a,b,c]` as the squared Lab error of the **central cell's actual decoded
16 pixels**, with neighboring labels a and c and central label b. The row
energy is:

```
E(z) = sum_x F[x, z[x-1], z[x], z[x+1]]
```

Absent screen-edge neighbors are the true black border. This is a second-order
chain. Exact dynamic programming retains the last two labels and costs
O(W*N^3) time and O(W*N^2) traceback memory for W cells and N labels.
The domain is large enough to make that naive full-domain calculation
impractical, but the bounded chain is not evidence of NP-hardness. Variable
elimination complexity depends on the induced width, rather than merely the
number of possible whole images. This is the relevant structural lesson from
[Dechter and Rish, Mini-Buckets: A General Scheme for Bounded Inference](https://ics.uci.edu/~csp/r62.pdf).

The RGB clipping and nonlinear RGB-to-Lab conversion do not invalidate this
factorization: they act inside each bounded-support pixel factor. They do
prevent treating the rendered error as an ordinary linear least-squares
problem over independent characters.

## Recommended algorithm: full-domain proposals and exact row fusion

The new design separates broad candidate discovery from a mathematically
correct coupled search. It does not use a beam of incomplete paths.

1. **Initialize across the complete candidate domain.** Compare all distinct
   patterns with isolated target cells to build an initial collection of
   proposals. This is an initialization heuristic, not a certificate; no
   candidate is permanently removed from subsequent full-domain scans.
2. **Solve the real row objective over those proposals.** Include the current
   solution at candidate index zero for every cell. Decode real triples to
   build the central-cell factors, then use exact second-order dynamic
   programming. Start with a proposal domain of K=8.
3. **Refresh proposals from actual context.** For every cell, score every one
   of the 23,536 patterns against its entire affected output area while its
   actual neighbors are fixed. Use five-cell input windows and the central
   19 affected output pixels per scanline. Keep good alternatives as well as
   the incumbent, then repeat exact row fusion. Increase the proposal width
   through K=16, K=32 and K=64. Two alternate-context proposal passes after
   K=32 improve proposal diversity before final K=64 convergence. Continue to stable search results
   rather than stopping solely because one minute has elapsed.

A two-proposal fusion can select the best of 2^80 possible combinations in a
row using only four pair states and eight triple transitions per position.
K proposals generalize this to K^80 combinations with O(80*K^3) work. This
allows coordinated changes across distant or adjacent cells that a sequence
of single-cell improvements can miss. The count describes combinations of
the supplied proposals, not all possible CGA encodings.

### Neighbor-context proposal diversity

Top conditional candidates can omit two alternatives that are individually
unhelpful but work well together. An additional proposal family addresses
this without accepting a worse image:

1. Starting from the incumbent, find each cell's best distinct alternative
   by a complete conditional scan.
2. In a temporary context only, replace alternating cells with their
   alternatives. Use both alternating offsets in separate passes.
3. Rank the complete dictionary against that temporary context, then perform
   exact fusion of those proposals with the actual incumbent. The temporary
   context is never directly committed.
4. Accept only actual complete-row improvements. Finish with ordinary
   actual-context full-domain scans and fusion convergence so that the final
   single-cell optimality claim remains valid.

This is a problem-specific proposal strategy inferred from the fusion
framework, not a new global guarantee. The prototype in
`artifacts/text-new-development/alternate_context_probe.py` used K=32 and
two offsets on the Raiders development image with the Old CGA simulator and
an NVIDIA GeForce RTX 3090. On the saved K=32 result it reduced the fixed Lab
objective from 8,921,287.53 to 8,827,273.98 in 6.13 seconds. On the separately
saved K=64 result it reduced 8,732,891.84 to 8,702,108.32 in 6.20 seconds.
These are additional-pass measurements on one existing result, not total
conversion runtimes or a quality comparison with the legacy mode. The
corresponding JSON records the individual pass changes.

The saved ordinary stage-8/16/32 run took 10.89 seconds; adding ordinary
stage-64 convergence took 64.48 seconds total on that development run and
lowered its objective by about 2.11%. Thus the one-minute performance goal
must remain separate from quality convergence. A K=64 factor row occupies
160 MiB; K=128 would require 1,280 MiB per row and eight times the triple
evaluations of K=64. Streaming factors would be advisable before making
K=128 routine. These timings are development observations before subsequent
GPU kernel optimization, not guarantees for other hardware or images.

The proposal-and-fusion principle comes from
[Lempitsky, Rother, Roth and Blake, Fusion Moves for Markov Random Field Optimization](https://www.microsoft.com/en-us/research/wp-content/uploads/2009/05/fusion.pdf).
Their general image models use graph-cut machinery and sometimes partial
solutions. Our adaptation instead exploits this encoder's second-order chain
and solves each fusion completely with dynamic programming. That adaptation
is a deduction from the inspected decoder structure, not a claim made by the
paper about CGA.

`cga_text_new_search.solve_chain` implements the exact restricted-domain
recurrence. It handles one- and two-cell rows, deterministic ties, and true
three-label factors. Its independent tests enumerate all K^W assignments for
small random chains, and include a case where only changing three cells
together escapes a single-cell minimum.

## Error diffusion and ordered dithering

The initial NEW mode omitted dithering to use a fixed source target across
independent rows. The updated implementation supports the existing GUI's None,
Error diffusion, and Ordered choices. Error diffusion follows the .167a text
encoder's block convention: complete one two-scanline character row, decode its
actual output, subtract it from the source plus incoming Lab error, then scatter
that residual into future character rows. All refinement finishes before the
residual is sent. Top and bottom scanlines remain distinct, and serpentine mirrors
the horizontal kernel offsets on odd character rows.

Only future-row taps are retained, divided by the sum of the complete original
kernel. Thus Floyd–Steinberg sends 9/16 of the residual onward; the retained taps
are not renormalized. Atkinson preserves the legacy divisor of six. This is
legacy-compatible block diffusion, not an assertion of equivalence to ordinary
pixelwise Floyd–Steinberg or Atkinson halftoning. Ordered dithering instead
perturbs the RGB target once and keeps independent-row processing.

The GPU/CPU scorer, color table, and candidate features persist across causal
rows. For a single row, the CUDA path scores all columns' triple factors in one
batch when memory permits, then runs the same exact dependent DP transitions.
The streaming path remains available on devices with insufficient memory. No
proposal width, precision, or convergence condition is reduced for speed.

This change also separates visual assessment from the raw pixel-error metric.
[Kite, Evans and Bovik's error-diffusion analysis](https://users.ece.utexas.edu/~bevans/papers/2000/errorDiffusion/index.html)
describes edge sharpening and noise shaping; its perceptual analysis helps
explain why a lower unfiltered pixelwise error need not yield a preferred image.
[Deshpande, Misra and Narayanan's parallel error-diffusion work](https://www.cs.cmu.edu/~imisra/projects/dithering/HybridDithering.pdf)
addresses dependency-aware scheduling and GPU overhead. Their pixel-level
wavefront algorithm is not directly interchangeable with this coupled whole-row
search; reusing state and batching independent candidate evaluations is our
application-specific adaptation.

Diagnostics distinguish original-source error from the adjusted search target.
Diffusion convergence describes each row against the target it received, not
whole-image optimality against the original source. Changing an earlier row
would change subsequent targets. Visual comparisons use matching kernel,
strength, and serpentine settings, and preserve full simulated RGB output.

## What is guaranteed, and what is not

- Each row fusion finds the minimum over its supplied candidate domains.
- Including the incumbent means an accepted fusion need not worsen the fixed
  objective. Equal-score results retain the incumbent. A complete-row decode
  should independently verify accepted changes and screen-edge handling.
- If a full-domain conditional scan includes each cell's best alternative
  and the exact fusion cannot improve, no single-cell replacement improves
  that fixed objective. This is a useful local optimality statement.
- Coordinated changes involving omitted alternatives can still improve it.
  Consequently convergence is not a proof of the global optimum, nor a
  numerical “99% optimal” certificate. Multiple diverse proposals and wider
  fusion domains improve exploration without supplying such a certificate.
- The optimization objective is the specified Lab error against the fixed
  target. An improvement under that metric is not proof of better subjective
  appearance or of a better match to unmodeled physical CRT behavior.
- Changing a diffusion target changes the optimization problem. Scores from
  different target definitions should not be presented as directly comparable
  guarantees of improvement.

In particular, the minimum found after restricting a label domain is a
**feasible upper bound** on the full-domain minimum, not a lower bound.

## GPU and CPU organization

The implemented CUDA path keeps candidate patterns, simulator constants, the
target and the complete 16,777,216-entry float32 RGB-to-Lab table resident on
the GPU. Candidate scoring runs in bounded batches. The exact pair-state
fusion dynamic program, all active rows, and traceback also run on the GPU;
one column of triple factors is live at a time. Only selected ranks and final
label choices return to the CPU. This avoids transferring complete row-factor
tables repeatedly. The
[NVIDIA CUDA C++ Best Practices Guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html)
specifically emphasizes exposing parallelism, minimizing host/device transfers,
and arranging memory access for throughput. These are general GPU principles;
the linked benchmark report supplies this application's measured evidence.

Both backends now precompute each candidate's internal signal contribution
before RGB clipping. The FIR decoder is additive in its composite waveform
samples. Actual external context and the two candidate-dependent boundary
transitions are added before clipping and Lab lookup. This removes repeated
decoder work without reducing the candidate domain, approximating the signal,
or quantizing RGB below the reference decoder's eight bits per channel.
The stencil and candidate/triple scores are checked against complete
reference-decoder results, including physical borders and second neighbors.

CPU candidate and triple scoring use Numba parallel loops when available.
The NumPy-only fallback uses a thread pool over disjoint positions or cells;
its array arithmetic can release the GIL, though Python loop overhead means
scaling still requires measurement. Worker counts respect requested workers,
available CPUs, useful tasks, the Numba limit, and bounded NumPy scratch
memory. The normal `auto` backend checks CUDA availability and falls back to
the same search on CPU after initialization or execution failure. Explicit
`cuda` requests expose errors instead of silently changing the backend.

The numerical objective uses the reference float32 Lab values and float64
differences/accumulation. GPU kernels do not enable fast-math or fused
multiply-add contraction. CPU/CUDA parity and device-resident fusion are
tested against the CPU exact chain and independent tiny exhaustive problems;
full-row reference decoding still verifies every accepted production move.
These numerical safeguards and exact restricted-domain fusion do not convert
the overall proposal search into a global-optimum certificate.

## Why the alternatives are not the first implementation

| Method | Useful property | Limitation for this encoder |
| --- | --- | --- |
| Wider beam or the old one-label Viterbi | Familiar and easy to extend | Width does not repair a wrong right-context cost or insufficient state. |
| Full-domain second-order DP | Exact global optimum for the fixed row objective | The large label domain makes naive cubic transitions prohibitive. |
| Coordinate descent alone | Full-domain conditional optimum, cheap parallel rows | Can stop at a minimum requiring several coordinated changes to escape. |
| Simulated annealing or evolutionary search | Can leave local minima | More tuning and variable convergence; no useful finite-time optimality certificate by themselves. |
| Generic graph-cut moves | Very effective for suitable image energies | This decoder's arbitrary ternary factors do not automatically satisfy graph-cut assumptions; the chain admits a simpler exact fusion solver. |
| Mini-bucket or dual bounds plus branch-and-bound | A route to certified gaps and eventual exactness | Computing strong bounds over the complete large domain may itself dominate the budget. |

For a future certification path, maintain feasible score U and a mathematically
valid lower bound L, and report the gap U-L. Relaxed variable elimination can
provide bounds to guide branch-and-bound. This tradeoff is developed in
[Kask and Dechter, Branch and Bound with Mini-Bucket Heuristics](https://ics.uci.edu/~csp/r77.pdf)
and
[Kask and Dechter, Mini-Bucket Heuristics for Improved Search](https://ics.uci.edu/~dechter/publications/r79.html).
Bounds must cover omitted candidates too; applying them only to the proposal
domains cannot certify the full problem. The search can return the best
feasible image at any point, with a certificate only if its bound justifies
one.

Another candidate is dual decomposition: separate overlapping tractable
subproblems and improve a shared lower bound. The monotone-bound motivation is
illustrated by
[Kolmogorov, Convergent Tree-Reweighted Message Passing for Energy Minimization](https://www.microsoft.com/en-us/research/publication/convergent-tree-reweighted-message-passing-for-energy-minimization/).
The original algorithm does not directly solve this ternary CGA model, and
convergence of a bound is not in itself equality with the feasible optimum.
Neither this nor mini-bucket certification is supplied by the current fusion
solver.

## Required empirical assessment

Compare both modes on identical source preparation, simulator preset and
fixed objective. Include photographs, sharp text/graphics, smooth gradients,
noise, and synthetic images generated from known legal CGA encodings. Record
warm and cold runtimes, CPU/GPU backend and worker count, objective value
after every accepted pass, convergence status, and full-decode parity. Test
screen edges and changes to second neighbors explicitly. Visual inspection
remains necessary because numerical error is only the chosen quality model.

The under-one-minute target is a performance goal. It must not become an
unreported early termination rule or be claimed from small-chain tests.
