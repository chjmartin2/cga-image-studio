"""
CGA Converter GUI

Modes:
  * 320x200 (4-color)         : classic CGA 4-color palettes (multiple sets, all 16 backgrounds)
  * 640x200 (2-color)         : black background + one CGA foreground color
  * 160x100 (16-color)        : full 16-color CGA palette, low resolution
  * 640x200 (char 16-color)   : TRUE text-style mode:
                                 - Screen is 80x25 character cells
                                 - Each cell is 8x8 pixels
                                 - Each cell uses exactly TWO CGA colours (FG/BG)
                                 - Pixels within the cell follow a ROM-style 1-bit glyph
                                   from a bitmap font (here we use Pillow's default
                                   monospaced bitmap font as our "ROM").

Dithers (for non-char modes):
  * None
  * Floyd–Steinberg
  * Atkinson
  * Bayer 2x2, 4x4, 8x8

Features:
  * Scaling: Fit (letterbox) / Fill (crop) / Stretch
  * Scale filter: Lanczos / Nearest
  * Optional "Match contrast / tone to palette" pre-toning
  * Palette optimization (for 320x200 and 640x200 2-color) with background-coverage penalty
  * 640x200 previews (both mono and char-16) aspect-corrected to 4:3 for display
  * Preview scale dropdown: 1x / 2x / 3x / 4x
  * Save result as GIF (palette preserved)

NOTE about 640x200 (char 16-color):
  - This uses an actual bitmap font (Pillow's built-in default) as a stand-in
    for a CGA ROM font.
  - It enforces the true text restriction:
      * 80x25 cells, each 8x8 pixels
      * Per-cell FG and BG chosen from 16 CGA colours
      * Per-pixel 1-bit pattern from that glyph
  - If you want to swap in a real CGA ROM font later, you can replace
    the glyph-generation routine with a static byte table.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont


# --- CGA palette definitions -------------------------------------------------

CGA_COLOR_NAMES = [
    "Black", "Blue", "Green", "Cyan",
    "Red", "Magenta", "Brown", "Light Gray",
    "Dark Gray", "Light Blue", "Light Green", "Light Cyan",
    "Light Red", "Light Magenta", "Yellow", "White",
]

CGA_COLORS = [
    (0, 0, 0),          # 0 Black
    (0, 0, 170),        # 1 Blue
    (0, 170, 0),        # 2 Green (dark green)
    (0, 170, 170),      # 3 Cyan
    (170, 0, 0),        # 4 Red (dark red)
    (170, 0, 170),      # 5 Magenta
    (170, 85, 0),       # 6 Brown
    (170, 170, 170),    # 7 Light Gray
    (85, 85, 85),       # 8 Dark Gray
    (85, 85, 255),      # 9 Light Blue
    (85, 255, 85),      # 10 Light Green
    (85, 255, 255),     # 11 Light Cyan
    (255, 85, 85),      # 12 Light Red
    (255, 85, 255),     # 13 Light Magenta
    (255, 255, 85),     # 14 Yellow
    (255, 255, 255),    # 15 White
]


def build_cga_4color_palettes():
    """
    Build CGA 320x200 (4-color) palettes as:
      - Cyan / Magenta / White
      - Red / Green / Yellow
      - Tweaked Red / White / Cyan
      - Dark Red / Dark Green / Brown
    each with all 16 possible background colors.

    Returns dict: palette_name -> [RGB, RGB, RGB, RGB]
    (first color is background).
    """
    palettes = {}
    base_sets = [
        ("Cyan/Magenta/White", [3, 5, 15]),       # cyan, magenta, white
        ("Red/Green/Yellow", [4, 2, 14]),         # red, green, yellow
        ("Tweaked Red/White/Cyan", [4, 15, 3]),   # red, white, cyan
        ("Dark Red/Green/Brown", [4, 2, 6]),      # dark red, dark green, brown
    ]
    for bg_idx in range(16):
        bg_color = CGA_COLORS[bg_idx]
        bg_name = CGA_COLOR_NAMES[bg_idx]
        for base_name, fg_indices in base_sets:
            name = f"{base_name} (bg={bg_name})"
            colors = [bg_color] + [CGA_COLORS[i] for i in fg_indices]
            palettes[name] = colors
    return palettes


def build_cga_mono_palettes():
    """
    640x200 2-color: black background (index 0) + one CGA foreground color.
    Returns dict: name -> [RGB_black, RGB_foreground].
    """
    palettes = {}
    black = CGA_COLORS[0]
    for idx, name in enumerate(CGA_COLOR_NAMES):
        if idx == 0:
            continue
        palettes[name] = [black, CGA_COLORS[idx]]
    return palettes


CGA_4COLOR_PALETTES = build_cga_4color_palettes()
CGA_MONO_PALETTES = build_cga_mono_palettes()
CGA_16COLOR_PALETTE = list(CGA_COLORS)  # for 16-color modes


# --- Basic helpers -----------------------------------------------------------


def clamp(value, lo=0.0, hi=255.0):
    return lo if value < lo else hi if value > hi else value


# --- Dithering and quantization helpers --------------------------------------


def nearest_palette_index(rgb, palette):
    """Return index of nearest color in palette (Euclidean distance)."""
    r, g, b = rgb
    best_idx = 0
    best_dist = float("inf")
    for i, (pr, pg, pb) in enumerate(palette):
        dr = r - pr
        dg = g - pg
        db = b - pb
        dist = dr * dr + dg * dg + db * db
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def floyd_steinberg_dither(image, palette):
    """Error-diffusion dithering with Floyd-Steinberg."""
    w, h = image.size
    pixels = [[[float(c) for c in image.getpixel((x, y))]
               for x in range(w)] for y in range(h)]
    indices = [0] * (w * h)

    for y in range(h):
        for x in range(w):
            old = pixels[y][x]
            idx = nearest_palette_index(old, palette)
            new = palette[idx]
            indices[y * w + x] = idx
            err = [old[i] - new[i] for i in range(3)]

            def add_error(xx, yy, factor):
                if 0 <= xx < w and 0 <= yy < h:
                    p = pixels[yy][xx]
                    for c in range(3):
                        p[c] = clamp(p[c] + err[c] * factor)

            add_error(x + 1, y, 7 / 16)
            add_error(x - 1, y + 1, 3 / 16)
            add_error(x, y + 1, 5 / 16)
            add_error(x + 1, y + 1, 1 / 16)

    return indices


def atkinson_dither(image, palette):
    """Error-diffusion dithering with Atkinson kernel."""
    w, h = image.size
    pixels = [[[float(c) for c in image.getpixel((x, y))]
               for x in range(w)] for y in range(h)]
    indices = [0] * (w * h)

    for y in range(h):
        for x in range(w):
            old = pixels[y][x]
            idx = nearest_palette_index(old, palette)
            new = palette[idx]
            indices[y * w + x] = idx
            err = [(old[i] - new[i]) / 8.0 for i in range(3)]

            def add_error(xx, yy):
                if 0 <= xx < w and 0 <= yy < h:
                    p = pixels[yy][xx]
                    for c in range(3):
                        p[c] = clamp(p[c] + err[c])

            # Atkinson pattern
            add_error(x + 1, y)
            add_error(x + 2, y)
            add_error(x - 1, y + 1)
            add_error(x, y + 1)
            add_error(x + 1, y + 1)
            add_error(x, y + 2)

    return indices


# Bayer / ordered matrices
BAYER_2x2 = [
    [0, 2],
    [3, 1],
]

BAYER_4x4 = [
    [0,  8,  2, 10],
    [12, 4, 14,  6],
    [3, 11,  1,  9],
    [15, 7, 13,  5],
]

BAYER_8x8 = [
    [ 0, 32,  8, 40,  2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44,  4, 36, 14, 46,  6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [ 3, 35, 11, 43,  1, 33,  9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47,  7, 39, 13, 45,  5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
]


def ordered_dither(image, palette, matrix, strength=24.0):
    """Generic ordered (Bayer-style) dithering using a supplied threshold matrix."""
    w, h = image.size
    mh = len(matrix)
    mw = len(matrix[0])
    max_val = max(max(row) for row in matrix) or 1

    indices = [0] * (w * h)
    pixels = image.load()

    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            t = matrix[y % mh][x % mw]
            offset = ((t / max_val) - 0.5) * strength
            r = clamp(r + offset)
            g = clamp(g + offset)
            b = clamp(b + offset)
            idx = nearest_palette_index((r, g, b), palette)
            indices[y * w + x] = idx
    return indices


def no_dither(image, palette):
    """Plain nearest-color quantization without dithering."""
    w, h = image.size
    indices = [0] * (w * h)
    pixels = image.load()
    for y in range(h):
        for x in range(w):
            indices[y * w + x] = nearest_palette_index(pixels[x, y], palette)
    return indices


def indices_to_pimage(indices, palette, size):
    """Create a 'P' image from palette indices and an RGB palette."""
    w, h = size
    pimg = Image.new("P", (w, h))
    pimg.putdata(indices)
    flat_palette = []
    for (r, g, b) in palette:
        flat_palette.extend([int(r), int(g), int(b)])
    while len(flat_palette) < 256 * 3:
        flat_palette.extend([0, 0, 0])
    pimg.putpalette(flat_palette)
    return pimg


def apply_dithering(image, palette, mode_name):
    """
    image: PIL RGB, already scaled (and optionally toned) to target size.
    palette: list of RGB tuples.
    mode_name: 'None', 'Floyd-Steinberg', 'Atkinson',
               'Bayer 2x2', 'Bayer 4x4', 'Bayer 8x8'.
    """
    if mode_name == "Floyd-Steinberg":
        indices = floyd_steinberg_dither(image, palette)
    elif mode_name == "Atkinson":
        indices = atkinson_dither(image, palette)
    elif mode_name == "Bayer 2x2":
        indices = ordered_dither(image, palette, BAYER_2x2, strength=32.0)
    elif mode_name == "Bayer 4x4":
        indices = ordered_dither(image, palette, BAYER_4x4, strength=24.0)
    elif mode_name == "Bayer 8x8":
        indices = ordered_dither(image, palette, BAYER_8x8, strength=16.0)
    else:
        indices = no_dither(image, palette)
    return indices_to_pimage(indices, palette, image.size)


# --- Palette scoring with background-coverage penalty ------------------------


def compute_gray_and_gradient(image):
    """
    Compute grayscale and simple gradient magnitude for each pixel.

    Gradient is |dI/dx| + |dI/dy| on a 4-neighbour grid.
    Returns:
        gray: list of len W*H with grayscale intensities
        grad: list of len W*H with gradient magnitudes
    """
    w, h = image.size
    pixels = image.load()
    gray = [0.0] * (w * h)

    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            gval = 0.299 * r + 0.587 * g + 0.114 * b
            gray[y * w + x] = gval

    grad = [0.0] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            g0 = gray[i]
            gx = 0.0
            gy = 0.0
            if x < w - 1:
                gx = abs(gray[y * w + (x + 1)] - g0)
            if y < h - 1:
                gy = abs(gray[(y + 1) * w + x] - g0)
            grad[i] = gx + gy
    return gray, grad


def compute_palette_score(resized_image, palette, grad_map, bg_index=0, step=2):
    """
    Compute a score for a palette on a resized (optionally toned) image.

    Score = color_error + lambda * (background_coverage * background_texture)
    """
    w, h = resized_image.size
    pixels = resized_image.load()

    total_error = 0.0
    bg_grad_sum = 0.0
    bg_count = 0
    sample_count = 0

    for y in range(0, h, step):
        for x in range(0, w, step):
            sample_count += 1
            i = y * w + x
            r, g, b = pixels[x, y]
            idx = nearest_palette_index((r, g, b), palette)
            pr, pg, pb = palette[idx]
            dr = r - pr
            dg = g - pg
            db = b - pb
            total_error += dr * dr + dg * dg + db * db

            if idx == bg_index:
                bg_count += 1
                bg_grad_sum += grad_map[i]

    if sample_count == 0:
        return total_error

    bg_fraction = bg_count / sample_count
    bg_texture = (bg_grad_sum / bg_count) if bg_count > 0 else 0.0

    LAMBDA = 4.0
    penalty = LAMBDA * bg_fraction * bg_texture

    return total_error + penalty


# --- Palette-dependent pre-toning --------------------------------------------


def tone_image_to_palette(image, palette):
    """
    Linearly remap the image's RGB range to the palette's RGB bounding box.
    """
    w, h = image.size
    src = image.load()

    src_min = [255.0, 255.0, 255.0]
    src_max = [0.0, 0.0, 0.0]
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            vals = (r, g, b)
            for c in range(3):
                v = vals[c]
                if v < src_min[c]:
                    src_min[c] = v
                if v > src_max[c]:
                    src_max[c] = v

    pal_min = [255.0, 255.0, 255.0]
    pal_max = [0.0, 0.0, 0.0]
    for (pr, pg, pb) in palette:
        vals = (pr, pg, pb)
        for c in range(3):
            v = vals[c]
            if v < pal_min[c]:
                pal_min[c] = v
            if v > pal_max[c]:
                pal_max[c] = v

    for c in range(3):
        if src_max[c] <= src_min[c]:
            src_max[c] = src_min[c] + 1.0

    out = Image.new("RGB", (w, h))
    dst = out.load()

    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            vals_in = (r, g, b)
            vals_out = [0, 0, 0]
            for c in range(3):
                t = (vals_in[c] - src_min[c]) / (src_max[c] - src_min[c])
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                v = pal_min[c] + t * (pal_max[c] - pal_min[c])
                vals_out[c] = int(clamp(v))
            dst[x, y] = tuple(vals_out)

    return out


# --- 640x200 "char 16-color" true text-style quantisation --------------------

_CHAR_GLYPHS = None  # lazily built


def build_char_glyphs():
    """
    Build an 8x8 bitmap glyph for each character 0..255 using Pillow's
    default bitmap font. This serves as our "ROM font".
    Returns: dict code -> 8x8 list of booleans (True=foreground).
    """
    font = ImageFont.load_default()
    glyphs = {}
    for code in range(256):
        ch = chr(code)
        img = Image.new("L", (8, 8), 0)
        draw = ImageDraw.Draw(img)
        # Draw character; offset a bit to keep it mostly inside 8x8
        draw.text((0, -1), ch, fill=255, font=font)
        bits = []
        px = img.load()
        for y in range(8):
            row = []
            for x in range(8):
                row.append(px[x, y] > 128)
            bits.append(row)
        glyphs[code] = bits
    return glyphs


def ensure_char_glyphs():
    global _CHAR_GLYPHS
    if _CHAR_GLYPHS is None:
        _CHAR_GLYPHS = build_char_glyphs()
    return _CHAR_GLYPHS


def quantize_char16_true_text(image):
    """
    Enforce CGA text-style restriction on a 640x200 RGB image using a
    ROM-style font:

      - Screen is 80x25 cells, each 8x8 pixels.
      - Each cell chooses FG/BG from 16 CGA colours.
      - Within a cell, pixels follow a 1-bit glyph from a fixed bitmap font.
      - For each cell we:
          1) Choose FG/BG based on nearest CGA colour frequencies.
          2) Search a subset of glyphs (ASCII 32..126) to minimise colour error.

    Returns a paletted PIL image (P mode) of size 640x200.
    """
    w, h = image.size
    if (w, h) != (640, 200):
        raise ValueError("quantize_char16_true_text expects a 640x200 image")

    palette = CGA_16COLOR_PALETTE
    glyphs = ensure_char_glyphs()

    num_cols = 80
    num_rows = 25
    cell_w = 8
    cell_h = 8

    pixels = image.load()
    indices = [0] * (w * h)

    # Pre-allocated structures
    counts = [0] * 16

    # Restrict glyphs to printable ASCII for now
    glyph_codes = list(range(32, 127))

    for row in range(num_rows):
        y0 = row * cell_h
        for col in range(num_cols):
            x0 = col * cell_w

            # 1) Decide FG/BG from nearest CGA colours across the cell
            for i in range(16):
                counts[i] = 0

            for dy in range(cell_h):
                for dx in range(cell_w):
                    x = x0 + dx
                    y = y0 + dy
                    r, g, b = pixels[x, y]

                    best_idx = 0
                    best_dist = float("inf")
                    for pi, (pr, pg, pb) in enumerate(palette):
                        dr = r - pr
                        dg = g - pg
                        db = b - pb
                        dist = dr * dr + dg * dg + db * db
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = pi
                    counts[best_idx] += 1

            sorted_indices = sorted(range(16), key=lambda i: counts[i], reverse=True)
            fg_idx = sorted_indices[0]
            bg_idx = sorted_indices[1] if counts[sorted_indices[1]] > 0 else fg_idx

            if fg_idx == bg_idx:
                # Fallback: ensure two distinct colours
                bg_idx = 0 if fg_idx != 0 else 7

            fg_rgb = palette[fg_idx]
            bg_rgb = palette[bg_idx]

            # 2) Search glyphs to minimise error
            best_glyph_code = glyph_codes[0]
            best_error = float("inf")

            for code in glyph_codes:
                glyph = glyphs[code]
                err = 0.0
                for dy in range(cell_h):
                    for dx in range(cell_w):
                        x = x0 + dx
                        y = y0 + dy
                        r, g, b = pixels[x, y]
                        if glyph[dy][dx]:
                            pr, pg, pb = fg_rgb
                        else:
                            pr, pg, pb = bg_rgb
                        dr = r - pr
                        dg = g - pg
                        db = b - pb
                        err += dr * dr + dg * dg + db * db
                if err < best_error:
                    best_error = err
                    best_glyph_code = code

            chosen_glyph = glyphs[best_glyph_code]

            # 3) Write out pixels according to chosen glyph and FG/BG
            for dy in range(cell_h):
                for dx in range(cell_w):
                    x = x0 + dx
                    y = y0 + dy
                    idx = fg_idx if chosen_glyph[dy][dx] else bg_idx
                    indices[y * w + x] = idx

    return indices_to_pimage(indices, palette, (w, h))


# --- Image resizing helpers --------------------------------------------------


def get_resample_filter(name: str):
    if name == "Lanczos":
        return getattr(Image, "Resampling", Image).LANCZOS
    else:
        return getattr(Image, "Resampling", Image).NEAREST


def resize_with_mode(image, target_w, target_h, scale_mode, resample_name):
    """
    scale_mode:
      - "Fit (letterbox)" => preserve aspect, black bars
      - "Fill (crop)"     => preserve aspect, crop overflows
      - "Stretch"         => ignore aspect
    """
    resample = get_resample_filter(resample_name)
    src_w, src_h = image.size

    if scale_mode == "Stretch":
        return image.resize((target_w, target_h), resample=resample)

    src_aspect = src_w / src_h
    dst_aspect = target_w / target_h

    if scale_mode == "Fit (letterbox)":
        if src_aspect > dst_aspect:
            new_w = target_w
            new_h = int(round(target_w / src_aspect))
        else:
            new_h = target_h
            new_w = int(round(target_h * src_aspect))
        resized = image.resize((new_w, new_h), resample=resample)
        bg = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        x0 = (target_w - new_w) // 2
        y0 = (target_h - new_h) // 2
        bg.paste(resized, (x0, y0))
        return bg

    if scale_mode == "Fill (crop)":
        if src_aspect > dst_aspect:
            new_h = target_h
            new_w = int(round(target_h * src_aspect))
        else:
            new_w = target_w
            new_h = int(round(target_w / src_aspect))
        resized = image.resize((new_w, new_h), resample=resample)
        x0 = (new_w - target_w) // 2
        y0 = (new_h - target_h) // 2
        return resized.crop((x0, y0, x0 + target_w, y0 + target_h))

    return image.resize((target_w, target_h), resample=resample)


# --- GUI Application ---------------------------------------------------------


class CgaConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CGA Converter")
        self.geometry("1040x640")

        self.src_image = None
        self.output_pimage = None
        self.src_tk_image = None
        self.out_tk_image = None

        self._build_ui()

    # --- UI setup ---

    def _build_ui(self):
        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)

        ttk.Button(controls, text="Open Image...", command=self.on_open).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Convert", command=self.on_convert).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Optimize Palette", command=self.on_optimize).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Save GIF...", command=self.on_save).pack(side=tk.LEFT, padx=4)

        options = ttk.LabelFrame(self, text="Options")
        options.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)

        # Mode
        ttk.Label(options, text="Output mode:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.mode_var = tk.StringVar(value="320x200 (4-color)")
        mode_cb = ttk.Combobox(
            options,
            textvariable=self.mode_var,
            state="readonly",
            values=[
                "320x200 (4-color)",
                "640x200 (2-color)",
                "160x100 (16-color)",
                "640x200 (char 16-color)",
            ],
            width=22,
        )
        mode_cb.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        mode_cb.bind("<<ComboboxSelected>>", self.on_mode_changed)

        # Palette
        ttk.Label(options, text="CGA palette / color:").grid(row=0, column=2, sticky="w", padx=4, pady=2)
        self.palette_var = tk.StringVar()
        self.palette_cb = ttk.Combobox(
            options,
            textvariable=self.palette_var,
            state="readonly",
            width=40,
        )
        self.palette_cb.grid(row=0, column=3, sticky="w", padx=4, pady=2)

        # Dither
        ttk.Label(options, text="Dither (non-char modes):").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        self.dither_var = tk.StringVar(value="Floyd-Steinberg")
        dither_cb = ttk.Combobox(
            options,
            textvariable=self.dither_var,
            state="readonly",
            values=[
                "None",
                "Floyd-Steinberg",
                "Atkinson",
                "Bayer 2x2",
                "Bayer 4x4",
                "Bayer 8x8",
            ],
            width=20,
        )
        dither_cb.grid(row=1, column=1, sticky="w", padx=4, pady=2)

        # Scaling
        ttk.Label(options, text="Scaling:").grid(row=1, column=2, sticky="w", padx=4, pady=2)
        self.scale_var = tk.StringVar(value="Fit (letterbox)")
        scale_cb = ttk.Combobox(
            options,
            textvariable=self.scale_var,
            state="readonly",
            values=["Fit (letterbox)", "Fill (crop)", "Stretch"],
            width=20,
        )
        scale_cb.grid(row=1, column=3, sticky="w", padx=4, pady=2)

        # Resample
        ttk.Label(options, text="Scale filter:").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        self.resample_var = tk.StringVar(value="Lanczos")
        resample_cb = ttk.Combobox(
            options,
            textvariable=self.resample_var,
            state="readonly",
            values=["Lanczos", "Nearest"],
            width=20,
        )
        resample_cb.grid(row=2, column=1, sticky="w", padx=4, pady=2)

        # Pre-toning
        self.tone_var = tk.BooleanVar(value=False)
        tone_cb = ttk.Checkbutton(
            options,
            text="Match contrast / tone to palette",
            variable=self.tone_var,
        )
        tone_cb.grid(row=2, column=2, sticky="w", padx=4, pady=2)

        # Preview scale
        ttk.Label(options, text="Preview scale:").grid(row=2, column=3, sticky="e", padx=4, pady=2)
        self.preview_scale_var = tk.StringVar(value="2x")
        preview_cb = ttk.Combobox(
            options,
            textvariable=self.preview_scale_var,
            state="readonly",
            values=["1x", "2x", "3x", "4x"],
            width=5,
        )
        preview_cb.grid(row=2, column=4, sticky="w", padx=4, pady=2)

        # Image frames
        img_frame = ttk.Frame(self)
        img_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=4)

        left_frame = ttk.LabelFrame(img_frame, text="Input")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        right_frame = ttk.LabelFrame(img_frame, text="Output")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.left_label = ttk.Label(left_frame, text="No image loaded")
        self.left_label.pack(fill=tk.BOTH, expand=True)

        self.right_label = ttk.Label(right_frame, text="No output yet")
        self.right_label.pack(fill=tk.BOTH, expand=True)

        self._refresh_palette_choices()

    # --- Mode helpers ---

    def is_4color_mode(self):
        return "320x200 (4-color)" in self.mode_var.get()

    def is_mono_mode(self):
        return "640x200 (2-color)" in self.mode_var.get()

    def is_16color_low_mode(self):
        return "160x100 (16-color)" in self.mode_var.get()

    def is_16color_char_mode(self):
        return "640x200 (char 16-color)" in self.mode_var.get()

    def get_target_size(self):
        if self.is_4color_mode():
            return 320, 200
        if self.is_mono_mode():
            return 640, 200
        if self.is_16color_low_mode():
            return 160, 100
        # char 16-color
        return 640, 200

    def _refresh_palette_choices(self):
        if self.is_4color_mode():
            names = sorted(CGA_4COLOR_PALETTES.keys())
            self.palette_cb["values"] = names
            self.palette_cb.state(["!disabled"])
            if names:
                current = self.palette_var.get()
                if current not in names:
                    self.palette_var.set(names[0])
            else:
                self.palette_var.set("")
        elif self.is_mono_mode():
            names = sorted(CGA_MONO_PALETTES.keys())
            self.palette_cb["values"] = names
            self.palette_cb.state(["!disabled"])
            if names:
                current = self.palette_var.get()
                if current not in names:
                    self.palette_var.set(names[0])
            else:
                self.palette_var.set("")
        else:
            # 16-color modes: fixed palette
            names = ["CGA 16-color"]
            self.palette_cb["values"] = names
            self.palette_cb.state(["disabled"])
            self.palette_var.set("CGA 16-color")

    def on_mode_changed(self, event=None):
        self._refresh_palette_choices()
        self._update_right_preview()

    def get_current_palette(self):
        if self.is_4color_mode():
            name = self.palette_var.get()
            return CGA_4COLOR_PALETTES.get(name)
        if self.is_mono_mode():
            name = self.palette_var.get()
            return CGA_MONO_PALETTES.get(name)
        # Both 16-color modes share the same palette
        return CGA_16COLOR_PALETTE

    # --- UI callbacks ---

    def on_open(self):
        path = filedialog.askopenfilename(
            title="Open image",
            filetypes=[
                ("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image:\n{e}")
            return

        self.src_image = img
        self._update_left_preview()

    def _update_left_preview(self):
        if not self.src_image:
            return
        preview = self.src_image.copy()
        max_w, max_h = 400, 400
        preview.thumbnail((max_w, max_h), resample=get_resample_filter("Lanczos"))
        self.src_tk_image = ImageTk.PhotoImage(preview)
        self.left_label.configure(image=self.src_tk_image, text="")

    def _make_output_preview_image(self):
        if not self.output_pimage:
            return None
        img = self.output_pimage.convert("RGB")
        w, h = img.size

        # Aspect-correct 640x200 modes for 4:3 (approx 640x480)
        if (self.is_mono_mode() or self.is_16color_char_mode()) and (w, h) == (640, 200):
            img = img.resize((640, 480), resample=get_resample_filter("Nearest"))
            w, h = img.size

        # Preview scale factor
        scale_str = self.preview_scale_var.get().lower().rstrip("x")
        try:
            factor = int(scale_str)
        except ValueError:
            factor = 2
        factor = max(1, min(4, factor))

        new_w = w * factor
        new_h = h * factor

        # Hard cap
        max_w, max_h = 1600, 1200
        if new_w > max_w or new_h > max_h:
            ratio = min(max_w / new_w, max_h / new_h)
            new_w = int(new_w * ratio)
            new_h = int(new_h * ratio)

        img = img.resize((new_w, new_h), resample=get_resample_filter("Nearest"))
        return img

    def _update_right_preview(self):
        if not self.output_pimage:
            return
        preview = self._make_output_preview_image()
        if preview is None:
            return
        self.out_tk_image = ImageTk.PhotoImage(preview)
        self.right_label.configure(image=self.out_tk_image, text="")

    def on_convert(self):
        if self.src_image is None:
            messagebox.showinfo("No image", "Please open an image first.")
            return

        palette = self.get_current_palette()
        if not palette:
            messagebox.showinfo("No palette", "No CGA palette / color selected.")
            return

        target_w, target_h = self.get_target_size()
        scale_mode = self.scale_var.get()
        resample_name = self.resample_var.get()
        dither_mode = self.dither_var.get()

        resized = resize_with_mode(self.src_image, target_w, target_h, scale_mode, resample_name)

        if self.tone_var.get():
            toned = tone_image_to_palette(resized, palette)
        else:
            toned = resized

        if self.is_16color_char_mode():
            # TRUE restricted char-style mode: per 8x8 cell, glyph + FG/BG.
            pimg = quantize_char16_true_text(toned)
        else:
            # Normal modes: honour dithering choice
            pimg = apply_dithering(toned, palette, dither_mode)

        self.output_pimage = pimg
        self._update_right_preview()

    def on_optimize(self):
        if self.src_image is None:
            messagebox.showinfo("No image", "Please open an image first.")
            return

        # Both 16-color modes have fixed palette; nothing to optimize
        if self.is_16color_low_mode() or self.is_16color_char_mode():
            messagebox.showinfo(
                "Fixed palette",
                "This mode uses the full CGA 16-color palette; "
                "there is nothing to optimize. Running a normal convert instead.",
            )
            self.on_convert()
            return

        target_w, target_h = self.get_target_size()
        scale_mode = self.scale_var.get()
        resample_name = self.resample_var.get()

        base_resized = resize_with_mode(self.src_image, target_w, target_h, scale_mode, resample_name)
        _, grad_map = compute_gray_and_gradient(base_resized)

        if self.is_4color_mode():
            palettes = CGA_4COLOR_PALETTES
            bg_index = 0  # first color in each palette
        else:
            palettes = CGA_MONO_PALETTES
            bg_index = 0  # black background

        step = 2

        best_name = None
        best_score = float("inf")

        for name, pal in palettes.items():
            if self.tone_var.get():
                img_for_score = tone_image_to_palette(base_resized, pal)
            else:
                img_for_score = base_resized

            score = compute_palette_score(img_for_score, pal, grad_map, bg_index=bg_index, step=step)
            if score < best_score:
                best_score = score
                best_name = name

        if best_name is None:
            messagebox.showinfo("No palette", "No palettes available to optimize.")
            return

        self.palette_var.set(best_name)
        self.on_convert()

    def on_save(self):
        if self.output_pimage is None:
            messagebox.showinfo("No output", "There is no converted image to save yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Save GIF",
            defaultextension=".gif",
            filetypes=[("GIF image", "*.gif")],
        )
        if not path:
            return
        try:
            self.output_pimage.save(path, format="GIF")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save GIF:\n{e}")


def main():
    app = CgaConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
