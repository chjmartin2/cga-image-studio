"""Launch the separate MartyPC build with a fresh STARTLCK disk copy."""
from pathlib import Path
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_startlock import read_files


def set_boot_floppy(config: str, filename: str) -> str:
    """Replace drive A's mount without depending on its previous filename."""
    mounts=tomllib.loads(config).get('emulator',{}).get('media',{}).get('floppy',[])
    # This Marty revision mounts native floppies by table order. Do not quietly
    # configure a later table and leave a different image first in drive A.
    if not mounts or mounts[0].get('drive')!=0:
        raise ValueError('The first native floppy mount must be drive A')
    changed=0
    def replace_table(match):
        nonlocal changed
        table=tomllib.loads(match.group(0))['emulator']['media']['floppy'][0]
        if table.get('drive') != 0:
            return match.group(0)
        updated,count=re.subn(r'^filename\s*=.*$',f'filename = "{filename}"',match.group(0),flags=re.MULTILINE)
        if count!=1:
            raise ValueError('Drive A must have exactly one filename entry')
        changed+=1
        return updated
    result=re.sub(r'^\[\[emulator\.media\.floppy\]\][^\n]*\n.*?(?=^\[|\Z)',
                  replace_table,config,flags=re.MULTILINE|re.DOTALL)
    if changed!=1:
        raise ValueError('Expected exactly one configured drive A')
    tomllib.loads(result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',type=int,choices=range(4),nargs='?',default=0)
    parser.add_argument('--prepare-only',action='store_true',help='Prepare disk/config without opening MartyPC')
    args=parser.parse_args()
    install=ROOT/'external/martypc/install'
    exe=ROOT/'external/martypc/target/release/martypc.exe'
    image=ROOT/'files/STARTLCK.DSK'
    baseline=install/'martypc-cga.toml'
    for path in (exe,image,baseline):
        if not path.is_file(): raise SystemExit(f'Required file missing: {path}')
    image_bytes=image.read_bytes()
    files=read_files(bytearray(image_bytes))
    if files.get('STARTLCK.COM') != (ROOT/'files/STARTLCK.COM').read_bytes():
        raise SystemExit('The demo disk does not contain the current STARTLCK.COM; rebuild it first')
    runtime_name=f'startlock_phase{args.phase}_runtime.dsk'
    runtime=install/'media/floppies'/runtime_name
    runtime.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(image,runtime)
    config=baseline.read_text(encoding='utf-8')
    config,n=re.subn(r'^pit_phase\s*=\s*\d+\s*$',f'pit_phase = {args.phase}',config,flags=re.MULTILINE)
    if n!=1: raise SystemExit('Expected exactly one active PIT phase setting')
    config=set_boot_floppy(config,runtime.as_posix())
    config_path=install/f'martypc-startlock-phase{args.phase}.toml'
    config_path.write_text(config,encoding='utf-8')
    print(f'STARTLCK: phase {args.phase}; fresh runtime disk {runtime}',flush=True)
    print(f'Verified STARTLCK.COM on drive A; disk SHA256 {hashlib.sha256(image_bytes).hexdigest()}',flush=True)
    if not args.prepare_only:
        result=subprocess.run([str(exe),'--configfile',str(config_path)],cwd=install)
        raise SystemExit(result.returncode)


if __name__=='__main__': main()
