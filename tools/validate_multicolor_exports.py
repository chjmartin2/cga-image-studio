"""Run generated static mode-6 exports in Marty core and verify bitmap pixels.

Checks RGBI signal bits, not frontend NTSC color rendering or human visual QA.
Run smoke_multicolor_gui.py first and build validate_imagelock with its CMD file.
"""
from pathlib import Path
import csv
import hashlib
import json
import argparse
import subprocess
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--during-search', action='store_true')
    args = parser.parse_args()
    source = ROOT / 'external/research' / ('multicolor-search-gui' if args.during_search else 'multicolor-gui')
    exe = ROOT / 'external/research/imagelock-validation/target/release/validate_imagelock.exe'
    cases = sorted(source.glob('*.com'))
    cases = [p for p in cases if '.rebuilt.' not in p.name]
    assert len(cases) == (2 if args.during_search else 6)
    family = 'error-diffusion' if args.during_search else 'none'
    cases += [source / f'{preset}-{family}.dsk' for preset in ('old', 'new')]
    results = []
    for path in cases:
        out = ROOT / 'external/research' / ('multicolor-search-core' if args.during_search else 'multicolor-core') / (path.stem + '-' + path.suffix[1:])
        subprocess.run([str(exe), str(ROOT), str(path), '0',
                        '100000000' if path.suffix == '.dsk' else '4000000',
                        str(out), '10C', '--static-mode6'], check=True, capture_output=True)
        com = path.with_suffix('.com').read_bytes()
        vram = com[-16384:]
        expected = b''.join((np.unpackbits(np.frombuffer(
            vram[(y%2)*8192+(y//2)*80:(y%2)*8192+(y//2)*80+80], dtype=np.uint8))*15).tobytes()
            for y in range(200))
        observed = (out / 'phase0-last-visible.bin').read_bytes()
        assert observed == expected, path
        rows = list(csv.DictReader((out/'phase0-frames.csv').open()))
        assert len(rows) >= 10
        fnv = 0xcbf29ce484222325
        for b in expected:
            fnv = ((fnv ^ b) * 0x100000001b3) & ((1 << 64)-1)
        assert all(r['cropped_fnv64'] == f'{fnv:016X}' for r in rows[-10:])
        result = {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'captured_frames': len(rows), 'last_10_frames_exact': True,
                  'bitmap_pixels': '128000 exact', 'frontend_composite_visual': 'pending user'}
        results.append(result)
        print(result, flush=True)
    (source/'marty-results.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()
