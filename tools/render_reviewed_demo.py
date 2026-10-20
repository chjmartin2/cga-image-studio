"""Render the approved demo proposal through the current Studio callbacks."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.build_demo_disk import Example, convert_examples

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/demo-slideshow')
    parser.add_argument('--only',type=int,nargs='+')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    proposal=json.loads((args.output/'approved-proposal.json').read_text(encoding='utf-8'))
    rows=proposal['selections']
    items=[Example(r['number'],r['id'],r['mode'],r['title'].replace(chr(8212),'-'),r['display'],r['settings']) for r in rows]
    sources={r['id']:args.output/'sources'/('EX%02d'%r['number']+Path(r['path']).suffix.lower()) for r in rows}
    def prepare(item,image):
        if image.size==(320,192) and item.settings.get('scale_var')!='Stretch':
            from PIL import Image
            padded=Image.new('RGB',(320,200));padded.paste(image,(0,4));return padded
        return image
    convert_examples(args.output,sources,args.resume,set(args.only or []),items=items,prepare_source=prepare)
if __name__=='__main__':main()
