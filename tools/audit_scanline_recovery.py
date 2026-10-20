"""Exhaustive exact-color feasibility audit; optional real encoder comparisons.

No resizing, tone matching, fixed background or adjacent-family exclusion.
Input remains private; reports and previews default to ignored artifacts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cga_v167 as cga


def audit(image,palettes):
    pool=np.asarray(list(dict.fromkeys(tuple(map(tuple,p)) for p in palettes)),np.uint8)
    rows=[]
    previous=None
    first_unique_failure=None
    for y,row in enumerate(image):
        hits=(row[None,:,None]==pool[:,None]).all(-1).any(-1).sum(-1)
        rows.append(dict(row=y,distinct_colors=len(np.unique(row,axis=0)),
            exact_palette_indices=np.flatnonzero(hits==len(row)).tolist(),
            maximum_exact_pixels=int(hits.max())))
        exact_groups={tuple(sorted(map(tuple,pool[i,1:])))
                      for i in rows[-1]['exact_palette_indices']}
        reachable=exact_groups if previous is None else {
            group for group in exact_groups if any(group!=p for p in previous)}
        if not reachable and first_unique_failure is None:
            first_unique_failure=y
        previous=reachable
    return dict(palette_count=len(pool),exact_rows=sum(bool(r['exact_palette_indices']) for r in rows),
        maximum_exact_pixels=sum(r['maximum_exact_pixels'] for r in rows),
        exact_with_forced_unique_foregrounds=bool(previous),
        first_row_without_unique_exact_path=first_unique_failure,rows=rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('--output',type=Path,default=Path('artifacts/planet-audit'))
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args()
    image=Image.open(args.image).convert('RGB')
    if image.size!=(320,200):
        parser.error('Exact source recovery audit requires a native 320x200 image')
    rgb=np.asarray(image)
    args.output.mkdir(parents=True,exist_ok=True)
    pools={name:list(dict.fromkeys(tuple(tuple(c) for c in p) for p in
        cga.filter_candidates_by_tweaked_mode(cga.CGA_4COLOR_PALETTES,mode)))
        for name,mode in [('standard','off'),('tweaked_only','on'),('combined','all')]}
    report=dict(source_name=args.image.name,source_sha256=hashlib.sha256(args.image.read_bytes()).hexdigest(),
        size=image.size,unique_rgb_colors=np.unique(rgb.reshape(-1,3),axis=0).tolist(),
        feasibility={name:audit(rgb,pool) for name,pool in pools.items()},renders=[])
    target=args.output/'recovery-report.json'
    def save(): target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    for name,result in report['feasibility'].items():
        print(name,result['exact_rows'],result['maximum_exact_pixels'],flush=True)
    if args.render:
        for mode,family in [('off','None'),('on','None'),('on','Ordered'),('on','Diffusion')]:
            start=time.perf_counter()
            print('Rendering',mode,family,flush=True)
            output,palettes=cga.quantize_320x200_mode_switch(image,
                tweaked_mode=mode,dither_family=family,dither_aware=True,
                return_palettes=True,debug=False)
            registers=cga.build_cga_reg_table(palettes)
            result=dict(tweaked=mode,dither=family,seconds=time.perf_counter()-start,
                matching_pixels=int(np.all(np.asarray(output)==rgb,axis=-1).sum()),
                standard_rows=sum(m==0x0A for m in registers[::2]),
                tweaked_rows=sum(m==0x0E for m in registers[::2]))
            report['renders'].append(result)
            output.save(args.output/f'after-{mode}-{family.lower()}.png')
            save()
            print(result,flush=True)


if __name__=='__main__':
    main()
