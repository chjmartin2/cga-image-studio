"""
CGA Converter GUI
-----------------
Python 3.13-compatible Tkinter app that:

- Loads an image (left preview)
- Converts to CGA:
    * 320x200 4-color mode (multiple CGA palettes, including tweaked Red/White/Cyan)
    * 640x200 2-color mode (black background + 1 selectable CGA color)
- Supports dithering:
    * None
    * Floyd–Steinberg
    * Atkinson
    * Bayer 2x2, 4x4, 8x8 ordered dithering
- Scaling modes: Fit (letterbox), Fill (crop), Stretch
- Scaling filters: Lanczos, Nearest
- Optimize button:
    * In 320x200 mode: tries all 4-color palettes & backgrounds, picks best
    * In 640x200 mode: tries all CGA colors as foreground with black background, picks best
      (background is always black in 640x200)
- Palette optimization cost:
    * Color error (as before)
    * PLUS a penalty if large areas are assigned to background where the source image
      has high local texture/gradient. This discourages "washed out" mid-gray backgrounds.
- Output preview on the right; 640x200 preview is aspect-corrected for a 4:3 display
- Save as GIF (palette preserved)

Requires:
    pip install pillow
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk


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
    (0, 170, 0),        # 2 Green
    (0, 170, 170),      # 3 Cyan
    (170, 0, 0),        # 4 Red
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
      - Cyan / Magenta / White with all 16 backgrounds
      - Red / Green / Yellow with all 16 backgrounds
      - Tweaked Red / White / Cyan with all 16 backgrounds
    Returns dict: palette_name -> [RGB, RGB, RGB, RGB]
    The first color is always the background color.
    """
    palettes = {}
    base_sets = [
        ("Cyan/Magenta/White", [3, 5, 15]),       # cyan, magenta, white
        ("Red/Green/Yellow", [4, 2, 14]),         # red, green, yellow
        ("Tweaked Red/White/Cyan", [4, 15, 3]),   # red, white, cyan
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
    Build 640x200 2-color palettes:
    - Always black background (index 0)
    - Foreground is any CGA color except black
    Returns dict: foreground_name -> [RGB_black, RGB_foreground]
    """
    palettes = {}
    black = CGA_COLORS[0]
    for idx, name in enumerate(CGA_COLOR_NAMES):
        if idx == 0:
            # Skip Black as foreground (would be all black)
            continue
        palettes[name] = [black, CGA_COLORS[idx]]
    return palettes


CGA_4COLOR_PALETTES = build_cga_4color_palettes()
CGA_MONO_PALETTES = build_cga_mono_palettes()


# --- Dithering and quantization helpers --------------------------------------


def clamp(value, lo=0.0, hi=255.0):
    return lo if value < lo else hi if value > hi else value


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
    """Error-diffusion dithering with Atkinson pattern."""
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

            # Atkinson kernel
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
    """
    Generic ordered (Bayer-style) dithering using a supplied threshold matrix.
    'strength' controls visibility of the pattern.
    """
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
    # Build a 256-color palette list
    flat_palette = []
    for (r, g, b) in palette:
        flat_palette.extend([int(r), int(g), int(b)])
    # Pad to 256 * 3
    while len(flat_palette) < 256 * 3:
        flat_palette.extend([0, 0, 0])
    pimg.putpalette(flat_palette)
    return pimg


def apply_dithering(image, palette, mode_name):
    """
    image: PIL RGB, already scaled to target size.
    palette: list of RGB tuples (len 2 or 4).
    mode_name: str ('None', 'Floyd-Steinberg', 'Atkinson',
                    'Bayer 2x2', 'Bayer 4x4', 'Bayer 8x8')
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

    # Grayscale
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
    Compute a score for a palette on a resized image.

    Score = color_error + lambda * (background_coverage * background_texture)

    where:
      - color_error is sum of squared RGB error (as before)
      - background_coverage is the fraction of sampled pixels mapped to background
      - background_texture is average gradient magnitude over background pixels

    This penalizes palettes that map large, high-texture regions to background
    (which tends to create washed-out flat areas).
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

    # Lambda factor controls how strongly we penalize "busy background".
    # Tuned experimentally; increase if you still see too many flat backgrounds.
    LAMBDA = 4.0
    penalty = LAMBDA * bg_fraction * bg_texture

    return total_error + penalty


# --- Image resizing helpers --------------------------------------------------


def get_resample_filter(name: str):
    # Pillow 9+ uses Image.Resampling
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
        # Fit inside
        if src_aspect > dst_aspect:
            new_w = target_w
            new_h = int(round(target_w / src_aspect))
        else:
            new_h = target_h
            new_w = int(round(target_h * src_aspect))
        resized = image.resize((new_w, new_h), resample=resample)
        # Paste centered on black background
        bg = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        x0 = (target_w - new_w) // 2
        y0 = (target_h - new_h) // 2
        bg.paste(resized, (x0, y0))
        return bg

    elif scale_mode == "Fill (crop)":
        # Fill entire area, crop excess
        if src_aspect > dst_aspect:
            new_h = target_h
            new_w = int(round(target_h * src_aspect))
        else:
            new_w = target_w
            new_h = int(round(target_w / src_aspect))
        resized = image.resize((new_w, new_h), resample=resample)
        x0 = (new_w - target_w) // 2
        y0 = (new_h - target_h) // 2
        # Crop box order: (left, upper, right, lower)
        return resized.crop((x0, y0, x0 + target_w, y0 + target_h))

    # Fallback to stretch if unknown
    return image.resize((target_w, target_h), resample=resample)


# --- GUI Application ---------------------------------------------------------


class CgaConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CGA Converter")
        self.geometry("980x540")

        self.src_image = None          # original loaded image (RGB)
        self.output_pimage = None      # dithered P-mode image for saving
        self.src_tk_image = None       # Tkinter previews
        self.out_tk_image = None

        self._build_ui()

    # --- UI setup ---

    def _build_ui(self):
        # Top control frame
        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)

        open_btn = ttk.Button(controls, text="Open Image...", command=self.on_open)
        open_btn.pack(side=tk.LEFT, padx=4)

        convert_btn = ttk.Button(controls, text="Convert", command=self.on_convert)
        convert_btn.pack(side=tk.LEFT, padx=4)

        optimize_btn = ttk.Button(controls, text="Optimize Palette", command=self.on_optimize)
        optimize_btn.pack(side=tk.LEFT, padx=4)

        save_btn = ttk.Button(controls, text="Save GIF...", command=self.on_save)
        save_btn.pack(side=tk.LEFT, padx=4)

        # Options frame
        options = ttk.LabelFrame(self, text="Options")
        options.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)

        # Output mode
        ttk.Label(options, text="Output mode:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.mode_var = tk.StringVar(value="320x200 (4-color)")
        mode_cb = ttk.Combobox(
            options,
            textvariable=self.mode_var,
            state="readonly",
            values=["320x200 (4-color)", "640x200 (2-color)"],
            width=20,
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
        ttk.Label(options, text="Dither:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
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

        # Resample filter
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

        # Image display frame
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

        # Initialize palette dropdown
        self._refresh_palette_choices()

    # --- Helpers for mode / palette ---

    def is_4color_mode(self):
        return "320x200" in self.mode_var.get()

    def get_target_size(self):
        if self.is_4color_mode():
            return 320, 200
        else:
            return 640, 200

    def _refresh_palette_choices(self):
        if self.is_4color_mode():
            names = sorted(CGA_4COLOR_PALETTES.keys())
        else:
            # mono: just choose the foreground color name
            names = sorted(CGA_MONO_PALETTES.keys())
        self.palette_cb["values"] = names
        # select first palette if none selected or not in new list
        if not names:
            self.palette_var.set("")
        else:
            current = self.palette_var.get()
            if current not in names:
                self.palette_var.set(names[0])

    def on_mode_changed(self, event=None):
        self._refresh_palette_choices()
        self._update_right_preview()

    def get_current_palette(self):
        name = self.palette_var.get()
        if self.is_4color_mode():
            return CGA_4COLOR_PALETTES.get(name)
        else:
            return CGA_MONO_PALETTES.get(name)

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
        """
        Create an RGB image suitable for preview from self.output_pimage.
        In 640x200 mode, correct aspect to 4:3 by scaling to 640x480
        before downscaling to the preview box.
        """
        if not self.output_pimage:
            return None
        img = self.output_pimage.convert("RGB")
        w, h = img.size

        if not self.is_4color_mode() and (w, h) == (640, 200):
            # Aspect correction for 640x200 to 4:3 => 640x480
            img = img.resize((640, 480), resample=get_resample_filter("Nearest"))

        # Now downscale to fit preview region while preserving aspect
        max_w, max_h = 400, 400
        img.thumbnail((max_w, max_h), resample=get_resample_filter("Nearest"))
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

        # Resize
        resized = resize_with_mode(self.src_image, target_w, target_h, scale_mode, resample_name)
        # Dither / quantize
        pimg = apply_dithering(resized, palette, dither_mode)

        self.output_pimage = pimg
        self._update_right_preview()

    def on_optimize(self):
        if self.src_image is None:
            messagebox.showinfo("No image", "Please open an image first.")
            return

        target_w, target_h = self.get_target_size()
        scale_mode = self.scale_var.get()
        resample_name = self.resample_var.get()

        # Resize once for optimization
        resized = resize_with_mode(self.src_image, target_w, target_h, scale_mode, resample_name)
        _, grad_map = compute_gray_and_gradient(resized)

        if self.is_4color_mode():
            palettes = CGA_4COLOR_PALETTES
            step = 2  # small resolution => can check more thoroughly
            bg_index = 0  # first color is background
        else:
            palettes = CGA_MONO_PALETTES
            step = 2  # still manageable
            bg_index = 0  # black is background

        best_name = None
        best_score = float("inf")

        for name, pal in palettes.items():
            score = compute_palette_score(resized, pal, grad_map, bg_index=bg_index, step=step)
            if score < best_score:
                best_score = score
                best_name = name

        if best_name is None:
            messagebox.showinfo("No palette", "No palettes available to optimize.")
            return

        self.palette_var.set(best_name)
        # After selecting the best palette, perform conversion with current dither
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
            # Save original CGA-sized image (320x200 or 640x200),
            # not the aspect-corrected preview
            self.output_pimage.save(path, format="GIF")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save GIF:\n{e}")


def main():
    app = CgaConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
