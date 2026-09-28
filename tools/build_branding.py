"""Export approved artwork using the owner's identity.json crop rectangles."""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'assets/branding/raster-crt'


def main():
    identity = json.loads((DEST / 'identity.json').read_text())
    with Image.open(DEST / identity['source']) as source:
        def crop(key):
            x, y, w, h = identity[key]
            return source.crop((x, y, x+w, y+h)).convert('RGB')
        logo = crop('logoCrop')
        logo.save(DEST / 'logo.png')
        icon = crop('iconCrop')
        side = max(icon.size)
        square = Image.new('RGB', (side, side), identity['paletteTargets']['charcoal'])
        square.paste(icon, ((side-icon.width)//2, (side-icon.height)//2))
        square.save(DEST / 'app-icon.png')
        square.save(DEST / 'app.ico', sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == '__main__':
    main()
