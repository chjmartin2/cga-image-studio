"""Compare complete NEW and legacy conversions against the same full-color target.

Example (run from the repository root):
  .venv/Scripts/python.exe tools/benchmark_text_new.py test_images/picard_input_copy.bmp --backend cuda

Outputs stay under ignored artifacts/ unless --outdir explicitly selects another
destination. The legacy baseline uses no dithering or chroma filtering, K=8,
and no polish by default; use --legacy-k 64 --legacy-polish 5 for that baseline.
Use --dither Diffusion to compare the NEW and legacy error-diffusion paths.
No conversion is stopped because of a time budget.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw, ImageOps

import cga_v167 as c
import cga_text_new as new


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def render_cells(cells, preset):
    """Independent scalar full-scanline reference; no RGB444 quantization."""
    ctx, _, _ = new.model(preset)
    decoded = []
    for y in range(100):
        rows = c._cells_to_row_pixels_640x200(cells, y, None)
        for row in rows:
            decoded.append(ctx.decode_scanline_rgba(0, row.reshape(-1).tolist()))
    return np.asarray(decoded, dtype=np.uint8)


def image_metrics(rgb, target_lab):
    # Convert exactly as the production NEW objective, then accumulate in f64.
    lab = c._rgb_array_to_lab_f32(rgb).astype(np.float64)
    squared = np.square(lab-target_lab.astype(np.float64)).sum(axis=2)
    objective = float(squared.sum())
    return dict(objective=objective, mean_squared_delta_e=objective/squared.size,
                rms_delta_e=float(np.sqrt(squared.mean())),
                mean_delta_e=float(np.sqrt(squared).mean()),
                rgb_color_count=int(len(np.unique(rgb.reshape(-1, 3), axis=0))),
                decoded_rgb_sha256=sha256(rgb.tobytes()))


def save_result(outdir, name, cells, target_lab, preset, seconds, **extra):
    rgb = render_cells(cells, preset)
    image = Image.fromarray(rgb)
    image.save(outdir/f'{name}.png')
    image.resize((640, 480), Image.Resampling.NEAREST).save(outdir/f'{name}-display.png')
    packed = c.pack_text_640x200_1024color(cells)
    (outdir/f'{name}-cells.bin').write_bytes(packed)
    return dict(seconds=seconds, **image_metrics(rgb, target_lab),
                cells_sha256=sha256(packed), **extra)


def display_comparison(outdir, results):
    names = ['source', 'new', 'legacy']
    canvas = Image.new('RGB', (640*len(names), 508), '#202020')
    draw = ImageDraw.Draw(canvas)
    for index, name in enumerate(names):
        canvas.paste(Image.open(outdir/f'{name}-display.png'), (640*index, 28))
        label = 'Source'
        if name in results:
            result = results[name]
            label = (f'{name.upper()} | {result["seconds"]:.2f}s | '
                     f'RMS Delta E {result["rms_delta_e"]:.3f} | '
                     f'{result["rgb_color_count"]:,} RGB colors')
        draw.text((640*index+8, 8), label, fill='white')
    canvas.save(outdir/'comparison-display.png')


def progress_report(label):
    previous = [-1]

    def report(percent):
        bucket = int(percent)//5
        if bucket != previous[0]:
            print(f'{label}: {int(percent)}%', flush=True)
            previous[0] = bucket
    return report


def run_legacy(source, args):
    started = time.perf_counter()
    result = c.encode_image_to_640x200_1024_viterbi(
        source, args.preset, k_candidates=args.legacy_k,
        dither_family=args.dither, dither_strength=args.dither_strength,
        diffusion_method=args.diffusion_method, chroma_lowpass=False,
        dct_shape_weight=1.0, serpentine=args.serpentine,
        return_intermediate=bool(args.legacy_polish),
        progress_cb=progress_report('Legacy Viterbi'))
    viterbi_seconds = time.perf_counter()-started
    polish_seconds = 0.0
    if args.legacy_polish:
        cells, target, error = result
        polish_started = time.perf_counter()
        ctx, ct, coeffs = new.model(args.preset)
        errors = c._compute_cell_errors_640x200(cells, target, error, ctx, ct, *coeffs)
        selected = c._select_cells_to_polish(errors, args.legacy_polish)
        c.polish_cells_640x200(cells, target, error, args.preset, ctx, ct, *coeffs,
                              selected_cells=selected, serpentine=args.serpentine,
                              progress_cb=progress_report('Legacy polish'))
        polish_seconds = time.perf_counter()-polish_started
    else:
        cells = result
    return cells, time.perf_counter()-started, dict(viterbi_seconds=viterbi_seconds,
                                                   polish_seconds=polish_seconds)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('image', type=Path)
    parser.add_argument('--outdir', type=Path, help='Default: ignored artifacts/text-new-benchmark/<source>-<UTC timestamp>')
    parser.add_argument('--backend', choices=('auto', 'cpu', 'cuda'), default='auto')
    parser.add_argument('--workers', type=int, help='CPU worker count; omitted uses automatic parallelism')
    parser.add_argument('--preset', choices=('Old CGA', 'New CGA'), default='Old CGA')
    parser.add_argument('--legacy-k', type=int, choices=(8, 16, 32, 64, 128, 256), default=8)
    parser.add_argument('--legacy-polish', type=int, default=0, metavar='PERCENT',
                        help='Legacy worst-error cell polish percentage, 0..100; default 0')
    parser.add_argument('--dither', choices=('None', 'Diffusion'), default='None',
                        help='Dithering for both encoders; legacy 640x200 does not implement Ordered')
    parser.add_argument('--diffusion-method', default='Floyd-Steinberg',
                        choices=('None', 'Floyd-Steinberg', 'Atkinson', 'Jarvis-Judice-Ninke',
                                 'Stucki', 'Burkes', 'Sierra', 'Sierra-2', 'Sierra Lite',
                                 'Horizontal Striped'))
    parser.add_argument('--dither-strength', type=float, default=1.0)
    parser.add_argument('--serpentine', action='store_true')
    parser.add_argument('--scale', choices=('stretch', 'fit', 'fill'), default='stretch')
    parser.add_argument('--order', choices=('new-first', 'legacy-first'), default='new-first',
                        help='Change execution order to assess shared cache/startup effects')
    args = parser.parse_args(argv)
    if args.workers is not None and args.workers < 1:
        parser.error('--workers must be positive')
    if not 0 <= args.legacy_polish <= 100:
        parser.error('--legacy-polish must be in 0..100')
    if not 0 <= args.dither_strength <= 1:
        parser.error('--dither-strength must be in 0..1')
    if not args.image.is_file():
        parser.error(f'Image does not exist: {args.image}')
    return args


def main(argv=None):
    args = parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    outdir = args.outdir or ROOT/'artifacts'/'text-new-benchmark'/f'{args.image.stem}-{stamp}'
    outdir = outdir.resolve()
    if outdir.exists() and any(outdir.iterdir()):
        raise ValueError(f'Output directory must be empty to preserve earlier results: {outdir}')
    outdir.mkdir(parents=True, exist_ok=True)
    with Image.open(args.image) as original:
        source = ImageOps.exif_transpose(original).convert('RGB')
    original_size = list(source.size)
    scale = {'stretch': 'Stretch', 'fit': 'Fit (letterbox)', 'fill': 'Fill (crop)'}[args.scale]
    source = c.resize_with_mode(source, 640, 200, scale, 'Lanczos').convert('RGB')
    source.save(outdir/'source.png')
    source.resize((640, 480), Image.Resampling.NEAREST).save(outdir/'source-display.png')
    target_lab = c._rgb_array_to_lab_f32(np.asarray(source))
    versions = {}
    for package in ('numpy', 'pillow', 'numba', 'cupy-cuda12x', 'cupy-cuda13x'):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            pass
    report = dict(
        status='running', timestamp_utc=stamp,
        source=dict(path=str(args.image.resolve()), file_sha256=sha256(args.image.read_bytes()),
                    original_size=original_size, target_size=[640, 200],
                    target_rgb_sha256=sha256(source.tobytes())),
        settings=dict(preset=args.preset, backend=args.backend, workers=args.workers,
                      scale=args.scale, resample='Lanczos', legacy_k=args.legacy_k,
                      legacy_polish_percent=args.legacy_polish, legacy_dither=args.dither,
                      new_dither=args.dither, diffusion_method=args.diffusion_method,
                      dither_strength=args.dither_strength, serpentine=args.serpentine,
                      legacy_chroma_lowpass=False, legacy_shape_weight=1.0, order=args.order),
        environment=dict(python=sys.version, platform=platform.platform(), cpu_count=os.cpu_count(),
                         packages=versions,
                         source_hashes={p.name: sha256(p.read_bytes()) for p in
                                        [ROOT/'cga_v167.py', *sorted(ROOT.glob('cga_text_new*.py'))]}),
        objective='Sum of squared CIE Lab distances to original target, full decoder RGB; f32 Lab conversion, f64 accumulation. This pixelwise score does not rank perceived dither quality.',
        timing_note='Encoding wall time includes lazy initialization/JIT; rendering/files excluded. Second encoder may reuse candidate caches. Alternate --order for startup comparisons.',
        display_note='Raw PNGs preserve full decoder RGB. Display PNGs use nearest-neighbor 640x480 CRT aspect. Legacy GUI RGB444 quantization is intentionally excluded from both scores.',
        results={})

    def write_report():
        (outdir/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')

    write_report()
    print(f'Results: {outdir}', flush=True)
    try:
        order = ('new', 'legacy') if args.order == 'new-first' else ('legacy', 'new')
        for name in order:
            if name == 'new':
                diagnostics = {}
                started = time.perf_counter()
                cells = new.encode_image_to_640x200_1024_new(
                    source, args.preset, backend=args.backend, workers=args.workers,
                    dither_family=args.dither, diffusion_method=args.diffusion_method,
                    dither_strength=args.dither_strength, serpentine=args.serpentine,
                    status_cb=lambda text: print('NEW: '+text, flush=True),
                    diagnostics_cb=diagnostics.update)
                seconds = time.perf_counter()-started
                extra = dict(diagnostics=diagnostics)
            else:
                cells, seconds, extra = run_legacy(source, args)
            report['results'][name] = save_result(outdir, name, cells, target_lab,
                                                  args.preset, seconds, **extra)
            write_report()
            print(f'{name.upper()}: {seconds:.2f}s, objective {report["results"][name]["objective"]:,.3f}', flush=True)
        old_error = report['results']['legacy']['objective']
        new_error = report['results']['new']['objective']
        report['new_objective_reduction_percent_vs_legacy'] = 100*(old_error-new_error)/old_error if old_error else None
        report['status'] = 'complete'
        display_comparison(outdir, report['results'])
    except KeyboardInterrupt:
        report['status'] = 'cancelled'
        return 130
    except Exception as error:
        report['status'] = 'error'
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        write_report()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
