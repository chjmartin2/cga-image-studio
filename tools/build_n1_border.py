"""Build the N=1 border template; normal exports use the packaged binary."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cga_n1_border import descriptor
from tools.build_startlock import reference_include


def build():
    work = ROOT/'artifacts/border-validation/build'
    work.mkdir(parents=True, exist_ok=True)
    reference_work = ROOT/'external/research/startlock-build'
    reference_work.mkdir(parents=True, exist_ok=True)
    reference = reference_include(reference_work)
    (work/'blank.bin').write_bytes(bytes(16384))
    assembler = Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe'
    output = work/'template.bin'
    subprocess.run([str(assembler), '-f', 'bin', '-DN1_BORDER',
        '-DBITMAP_PATH="artifacts/border-validation/build/blank.bin"',
        '-o', str(output), '-l', str(work/'template.lst'), 'tools/imagelock.asm'], cwd=ROOT, check=True)
    payload = output.read_bytes()
    assert payload[0x82:0x300] == reference
    descriptor(payload)
    profile = dict(template_sha256=hashlib.sha256(payload).hexdigest(),
        source='tools/imagelock.asm with N1_BORDER; tools/n1_border_kernel.inc',
        image_ticks=2227, line_cpu_cycles=304, frame_cpu_cycles=79648,
        preroll_lines=8, visible_lines=200, image_palette_writes_per_row=1,
        black_border_writes_per_row=1, physical_hardware_validated=False,
        status='Experimental edge timing: see the recorded renderer/phase limitations',
        direct_load_exact_pixel_clock_phases=[0,1,2], exact_default_renderer=False,
        exact_dos_reentry=False,
        validation='docs/N1_BORDER.md')
    (work/'profile.json').write_text(json.dumps(profile, indent=2)+'\n')
    if '--install' in sys.argv:
        assets=ROOT/'assets/mode4_lock/n1_border'
        assets.mkdir(parents=True, exist_ok=True)
        (assets/'template.bin').write_bytes(payload)
        (assets/'profile.json').write_text(json.dumps(profile, indent=2)+'\n')
    print(output, profile['template_sha256'])


if __name__ == '__main__':
    build()
