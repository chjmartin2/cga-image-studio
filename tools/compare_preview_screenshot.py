from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image


def downsample_pick(img: Image.Image, ox: int, oy: int) -> Image.Image:
    width, height = img.width // 2, img.height // 2
    out = Image.new("RGB", (width, height))
    pix = out.load()
    src = img.load()
    for y in range(height):
        for x in range(width):
            pix[x, y] = src[x * 2 + ox, y * 2 + oy]
    return out


def mismatch_mask(a: Image.Image, b: Image.Image) -> list[list[bool]]:
    width, height = a.size
    ap = a.load()
    bp = b.load()
    return [[ap[x, y] != bp[x, y] for x in range(width)] for y in range(height)]


def connected_components(mask: list[list[bool]]) -> list[tuple[int, int, int, int, int]]:
    height = len(mask)
    width = len(mask[0])
    seen = [[False] * width for _ in range(height)]
    comps: list[tuple[int, int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or seen[y][x]:
                continue
            q: deque[tuple[int, int]] = deque([(x, y)])
            seen[y][x] = True
            xs: list[int] = []
            ys: list[int] = []
            while q:
                cx, cy = q.popleft()
                xs.append(cx)
                ys.append(cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            comps.append((len(xs), min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    comps.sort(reverse=True)
    return comps


def save_diff(mask: list[list[bool]], out_path: Path) -> None:
    height = len(mask)
    width = len(mask[0])
    out = Image.new("RGB", (width, height), (8, 8, 8))
    pix = out.load()
    for y in range(height):
        for x in range(width):
            if mask[y][x]:
                pix[x, y] = (255, 0, 255)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preview")
    parser.add_argument("screenshot")
    parser.add_argument("--diff", default="test_images/preview_vs_marty_diff.png")
    args = parser.parse_args()

    preview = Image.open(args.preview).convert("RGB")
    screenshot = Image.open(args.screenshot).convert("RGB")
    print(f"preview {preview.size} screenshot {screenshot.size}")
    if screenshot.size != (preview.width * 2, preview.height * 2):
        raise SystemExit("screenshot is not exactly 2x preview size")

    variants = []
    for oy in (0, 1):
        for ox in (0, 1):
            actual = downsample_pick(screenshot, ox, oy)
            mask = mismatch_mask(preview, actual)
            mismatches = sum(sum(row) for row in mask)
            variants.append((mismatches, ox, oy, actual, mask))
            print(f"offset {ox},{oy}: {mismatches} / {preview.width * preview.height}")
    mismatches, ox, oy, _actual, mask = min(variants, key=lambda item: item[0])
    print(f"best offset {ox},{oy}: {mismatches} / {preview.width * preview.height}")

    comps = connected_components(mask)
    print(f"components {len(comps)}")
    for count, x0, y0, x1, y1 in comps[:24]:
        print(f"component {count:5d}: x{x0:3d}-{x1:3d} y{y0:3d}-{y1:3d} size {x1 - x0}x{y1 - y0}")

    cols = [sum(mask[y][x] for y in range(preview.height)) for x in range(preview.width)]
    rows = [sum(mask[y][x] for x in range(preview.width)) for y in range(preview.height)]
    print("top columns:", " ".join(f"{x}:{v}" for v, x in sorted((v, x) for x, v in enumerate(cols))[-16:][::-1]))
    print("top rows:", " ".join(f"{y}:{v}" for v, y in sorted((v, y) for y, v in enumerate(rows))[-16:][::-1]))

    save_diff(mask, Path(args.diff))
    print(f"wrote {args.diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
