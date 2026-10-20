"""Measure the exported N=1 border program in the unchanged MartyPC core."""
from pathlib import Path
import csv
import json
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_n1_border as border
import cga_v167 as cga


def run():
    output = ROOT/'artifacts/border-validation/acceptance'
    output.mkdir(parents=True, exist_ok=True)
    harness=ROOT/'external/research/imagelock-validation/target/release/validate_imagelock.exe'
    records=[]
    for kind in ('standard', 'tweaked', 'mixed'):
        registers=bytes(value for y in range(200) for value in (
            0x0E if kind=='tweaked' or (kind=='mixed' and y%3==1) else 0x0A,
            (y%16)|((y%4)<<4)))
        indices=((np.arange(320)[None]//13+np.arange(200)[:,None])%4).astype(np.uint8)
        # Explicit background and each foreground at both edges, cycling by row.
        indices[:,0]=np.arange(200)%4
        indices[:,-1]=(np.arange(200)//4)%4
        expected=np.empty((200,320),np.uint8)
        for y in range(200):
            mode,color=registers[2*y:2*y+2]
            foreground=(3,4,7) if mode&4 else ((3,5,7) if color&32 else (2,4,6))
            palette=np.array([color&15]+[c+(8 if color&16 else 0) for c in foreground],np.uint8)
            expected[y]=palette[indices[y]]
        com=cga.build_com_320_mode_switch_n1(cga.pack_cga_320_vram_from_indices(indices),registers,
            display_frames=1000, exit_on_keypress=True, keep_border_black=True)
        path=output/f'{kind}.com';path.write_bytes(com)
        expected_path=output/f'{kind}-expected.bin';expected_path.write_bytes(expected.tobytes())
        meta=border.descriptor(com)
        for pixel_clock in (True,False):
            for phase in range(4) if pixel_clock else (0,):
                folder=output/f'{kind}-{"pixel" if pixel_clock else "character"}-{phase}'
                args=[str(harness),str(ROOT),str(path),str(phase),'12000000',str(folder),
                    f"{meta['first_color_out_offset']+0x100:X}",str(expected_path),'--no-debug-video']
                if pixel_clock:args.append('--pixel-clock')
                subprocess.run(args,cwd=ROOT,check=True,capture_output=True)
                frames=list(csv.DictReader((folder/f'phase{phase}-frames.csv').open()))
                field=np.frombuffer((folder/f'phase{phase}-frame.bin').read_bytes(),np.uint8).reshape(-1,912)[:262]&15
                outside=np.ones((245,768),bool)
                outside[21:221,64:704]=False # x=192..831,y=38..237 in the full field
                border_pixels=field[17:262,128:896][outside]
                bad_border=int(np.count_nonzero(border_pixels))
                mismatches=[int(frame['mismatching_dots']) for frame in frames]
                record=dict(kind=kind,pixel_clock=pixel_clock,phase=phase,frames=len(frames),
                    image_mismatches=sorted(set(mismatches)),last_frame_nonblack_border_dots=bad_border)
                records.append(record)
                (output/'report.json').write_text(json.dumps(records,indent=2)+'\n')
                print(record,flush=True)
                if phase==0:
                    rgb=np.asarray(cga.CGA_COLORS,np.uint8)[field[17:262,128:896]]
                    Image.fromarray(rgb).save(folder/'border.png')
    failures=[r for r in records if not r['frames'] or r['image_mismatches']!=[0]
              or r['last_frame_nonblack_border_dots']]
    if failures and '--record-known-failures' not in sys.argv:
        raise SystemExit(f'{len(failures)} of {len(records)} border cases failed exact qualification; see report.json')
    return records


if __name__=='__main__':
    run()
