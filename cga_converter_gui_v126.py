
# Debug: set True to write a per-scanline log for 320x200 Mode Switch
DEBUG_MODE_SWITCH = False

DEBUG_PROPAGATION_SUMMARY = False  # set True to log per-scanline error propagation metrics for Mode Switch
DEBUG_PROPAGATION_DETAILS = False  # set True to log a small per-pixel trace (slow) for first few scanlines
DEBUG_ZERO_ERROR_CHECK = True   # logs ZEROERR and SAMPLE lines into diffusion debug file
DEBUG_DIFFUSION = False  # set True to log error propagation stats for Mode Switch
"""
CGA Converter GUI

Modes:
  * 320x200 (4-color)         : classic CGA 4-color palettes (multiple sets, all 16 backgrounds)
  * 640x200 (2-color)         : black background + one CGA foreground color
  * 160x100 (16-color)        : full 16-color CGA palette, low resolution
  * 640x200 (char 16-color)   : "text-block" mode (character-slice graphics):
                                 - Screen is 80x100 cells
                                 - Each cell is 8x2 pixels
                                 - Each cell uses exactly TWO CGA colours (FG/BG)
                                 - Each cell chooses one of 256 ROM characters, but only the
                                   FIRST TWO scanlines (row 0 and row 1) of that glyph are used,
                                   forming a 2x8 bit pattern (16 bits total).
                                 - IMPORTANT: dithering happens BEFORE this restriction:
                                   we first convert to a normal 640x200 16-color bitmap (with
                                   your chosen dither), then map that result into the
                                   character-limited 8x2 blocks.

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
  * 640x200 previews shown at native 640x200 geometry (no aspect correction)
  * Preview scale dropdown: 1x / 2x / 3x / 4x
  * Save result as GIF (palette preserved)

NOTE about 640x200 (char 16-color):
  - This is NOT normal text mode rendering.
  - It models the common trick where only the FIRST scanline row of each
    character is displayed/used, giving you 8x1 "cells" across 200 rows.
  - Each 8x1 cell can pick ANY two CGA colours and ANY 8-bit pattern (0..255).
"""

import tkinter as tk
import datetime
import os
import re
from typing import List, Tuple, Optional, Dict
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter
import numpy as np
import math



def popcount(x: int) -> int:
    """Return number of set bits in x (Python 3.8 compatible)."""
    return bin(int(x) & 0xFFFFFFFF).count('1')

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


# --- 640x200 (2-color) palettes ---------------------------------------------
# For the 640x200 2-color mode, we treat the source as *black/white only* (luminance).
# The selected foreground color is applied *after* thresholding/dithering by substituting
# the "white" pixels with the chosen CGA foreground color.
def build_cga_mono_palettes():
    palettes = {}
    for idx, rgb in enumerate(CGA_COLORS):
        name = f"Black / {CGA_COLOR_NAMES[idx]}"
        palettes[name] = [(0, 0, 0), rgb]
    return palettes

CGA_MONO_PALETTES = build_cga_mono_palettes()


def build_cga_4color_palettes():
    """
    Build CGA 320x200 (4-color) palettes for *RGBI* output.

    We expose both LOW and HIGH intensity variants where the CGA intensity bit (3D9h bit 4)
    changes the three foreground colors.

    Notes:
      * Standard CGA mode 4 palettes:
          - Cyan/Magenta/White family (palette bit 5 = 1)
          - Red/Green/(Brown|Yellow) family (palette bit 5 = 0)
      * "Tweaked" (cyan/red/white) corresponds to BIOS mode 05h on RGB monitors.
        (We still build the preview palette here; the COM exporter chooses mode 05h.)
    """
    palettes = {}

    base_sets = [
        # Standard mode 4 palettes
        ("Cyan/Magenta/White LOW",  [3, 5, 7]),      # cyan, magenta, light gray
        ("Cyan/Magenta/White",      [11, 13, 15]),   # light cyan, light magenta, white (HIGH)

        ("Red/Green/Yellow LOW",    [2, 4, 6]),      # green, red, brown (LOW)
        ("Red/Green/Yellow",        [10, 12, 14]),   # light green, light red, yellow (HIGH)

        # "Tweaked" (mode 05h on real CGA RGB) palette
        ("Tweaked Cyan/Red/White LOW", [3, 4, 7]),    # cyan, red, light gray
        ("Tweaked Cyan/Red/White",     [11, 12, 15]), # light cyan, light red, white (HIGH)

        # Back-compat name that users like (same as Red/Green/Yellow LOW)
        ("Dark Red/Green/Brown",    [2, 4, 6]),
    ]

    for bg_idx in range(16):
        bg_color = CGA_COLORS[bg_idx]
        bg_name = CGA_COLOR_NAMES[bg_idx]
        for base_name, fg_indices in base_sets:
            name = f"{base_name} (bg={bg_name})"
            palettes[name] = [bg_color, CGA_COLORS[fg_indices[0]], CGA_COLORS[fg_indices[1]], CGA_COLORS[fg_indices[2]]]
    return palettes



CGA_4COLOR_PALETTES = build_cga_4color_palettes()
CGA_16COLOR_PALETTE = list(CGA_COLORS)  # for 16-color modes






# --- Composite (NTSC artifact) palettes & simulation (Reenigne/Jenner algorithm) ---
#
# We model "160x200 Composite (16-color)" as **CGA 640x200 2-color graphics (BIOS mode 06h)**
# viewed through an NTSC composite decoder. Each *logical* composite pixel corresponds to a
# 4-bit pattern across 4 adjacent hi-res pixels (640/4 = 160).
#
# For each selectable "Composite Palette/Color" preset, we:
#   1) Run a port of Reenigne's sampled chroma multiplexer decoder to compute the *actual*
#      RGB output for each of the 16 possible 4-bit patterns.
#   2) Use those 16 decoded RGB colors as the palette for dithering/quantization in 160x200 space.
#   3) Encode each 160x200 palette index back into its 4-bit hi-res pattern, producing a
#      640x200 1bpp image for packing/export (mode 06h).

_RE_CHROMA_MULTIPLEXER = [
      2,   2,   2,   2, 114, 174,   4,   3,   2,   1, 133, 135,   2, 113, 150,   4,
    133,   2,   1,  99, 151, 152,   2,   1,   3,   2,  96, 136, 151, 152, 151, 152,
      2,  56,  62,   4, 111, 250, 118,   4,   0,  51, 207, 137,   1, 171, 209,   5,
    140,  50,  54, 100, 133, 202,  57,   4,   2,  50, 153, 149, 128, 198, 198, 135,
     32,   1,  36,  81, 147, 158,   1,  42,  33,   1, 210, 254,  34, 109, 169,  77,
    177,   2,   0, 165, 189, 154,   3,  44,  33,   0,  91, 197, 178, 142, 144, 192,
      4,   2,  61,  67, 117, 151, 112,  83,   4,   0, 249, 255,   3, 107, 249, 117,
    147,   1,  50, 162, 143, 141,  52,  54,   3,   0, 145, 206, 124, 123, 192, 193,
     72,  78,   2,   0, 159, 208,   4,   0,  53,  58, 164, 159,  37, 159, 171,   1,
    248, 117,   4,  98, 212, 218,   5,   2,  54,  59,  93, 121, 176, 181, 134, 130,
      1,  61,  31,   0, 160, 255,  34,   1,   1,  58, 197, 166,   0, 177, 194,   2,
    162, 111,  34,  96, 205, 253,  32,   1,   1,  57, 123, 125, 119, 188, 150, 112,
     78,   4,   0,  75, 166, 180,  20,  38,  78,   1, 143, 246,  42, 113, 156,  37,
    252,   4,   1, 188, 175, 129,   1,  37, 118,   4,  88, 249, 202, 150, 145, 200,
     61,  59,  60,  60, 228, 252, 117,  77,  60,  58, 248, 251,  81, 212, 254, 107,
    198,  59,  58, 169, 250, 251,  81,  80, 100,  58, 154, 250, 251, 252, 252, 252
]
_RE_INTENSITY = [77.175381, 88.654656, 166.564623, 174.228438]
_RE_TAU = 6.28318531

def _re_byte_clamp(v: int) -> int:
    # Matches reenigne_composite.rs: (v >> 13).clamp(0,255)
    vv = v >> 13
    if vv < 0: return 0
    if vv > 255: return 255
    return vv

class _ReCompositeContextPy:
    """Minimal port of reenigne's composite decoder for our palette derivation + preview."""
    def __init__(self):
        self.brightness = 0.0
        self.contrast = 100.0
        self.saturation = 100.0
        self.sharpness = 0.0
        self.hue_offset = 0.0
        self.composite_table = [0] * 1024

        self.mode_brightness = 0.0
        self.mode_contrast = 0.0
        self.mode_saturation = 0.0
        self.mode_hue = 0.0
        self.min_v = 0.0
        self.max_v = 0.0

        self.video_ri = 0
        self.video_rq = 0
        self.video_gi = 0
        self.video_gq = 0
        self.video_bi = 0
        self.video_bq = 0
        self.video_sharpness = 0

        self.cgamode = 0
        self.new_cga = False

    def _new_cga_mix(self, c: float, i: float, r: float, g: float, b: float) -> float:
        return (c / 0.72) * 0.29 + (i / 0.28) * 0.32 + (r / 0.28) * 0.10 + (g / 0.28) * 0.22 + (b / 0.28) * 0.07

    def adjust(self, hue_offset_deg: float, saturation: float, brightness: float, contrast: float = 100.0, sharpness: float = 0.0, new_cga: bool = False):
        self.hue_offset = float(hue_offset_deg)
        self.saturation = float(saturation)
        self.brightness = float(brightness)
        self.contrast = float(contrast)
        self.sharpness = float(sharpness)
        self.new_cga = bool(new_cga)

    def update_cga16_color(self, cgamode: int):
        # Port of update_cga16_color() from reenigne_composite.rs
        RI, RQ = 0.9563, 0.6210
        GI, GQ = -0.2721, -0.6474
        BI, BQ = -1.1069, 1.7046

        if not self.new_cga:
            self.min_v = float(_RE_CHROMA_MULTIPLEXER[0]) + _RE_INTENSITY[0]
            self.max_v = float(_RE_CHROMA_MULTIPLEXER[255]) + _RE_INTENSITY[3]
        else:
            i0 = _RE_INTENSITY[0]; i3 = _RE_INTENSITY[3]
            self.min_v = self._new_cga_mix(float(_RE_CHROMA_MULTIPLEXER[0]), i0, i0, i0, i0)
            self.max_v = self._new_cga_mix(float(_RE_CHROMA_MULTIPLEXER[255]), i3, i3, i3, i3)

        self.mode_contrast = 256.0 / (self.max_v - self.min_v)
        self.mode_brightness = -self.min_v * self.mode_contrast

        self.mode_hue = 14.0 if ((cgamode & 3) == 1) else 4.0

        self.mode_contrast *= (self.contrast * (1.2 if self.new_cga else 1.0) / 100.0)
        self.mode_brightness += ((self.brightness - 10.0) if self.new_cga else self.brightness) * 5.0
        self.mode_saturation = (4.35 if self.new_cga else 2.9) * self.saturation / 100.0

        for x in range(1024):
            phase = x & 3
            right = (x >> 2) & 15
            left = (x >> 6) & 15
            rc, lc = right, left

            if (cgamode & 4) != 0:
                # hi-res mono adjustment
                rc = (right & 8) | (7 if (right & 7) != 0 else 0)
                lc = (left & 8)  | (7 if (left & 7)  != 0 else 0)

            c = float(_RE_CHROMA_MULTIPLEXER[((lc & 7) << 5) | ((rc & 7) << 2) | phase])
            i = _RE_INTENSITY[(left >> 3) | ((right >> 2) & 2)]
            if not self.new_cga:
                v = c + i
            else:
                r = _RE_INTENSITY[((left >> 2) & 1) | ((right >> 1) & 2)]
                g = _RE_INTENSITY[((left >> 1) & 1) | (right & 2)]
                b = _RE_INTENSITY[(left & 1) | ((right << 1) & 2)]
                v = self._new_cga_mix(c, i, r, g, b)

            self.composite_table[x] = int(v * self.mode_contrast + self.mode_brightness)

        # derive IQ adjustment
        i = float(self.composite_table[6 * 68] - self.composite_table[6 * 68 + 2])
        q = float(self.composite_table[6 * 68 + 1] - self.composite_table[6 * 68 + 3])

        a = _RE_TAU * (33.0 + 90.0 + self.hue_offset + self.mode_hue) / 360.0
        c = math.cos(a); s = math.sin(a)
        denom = math.sqrt(i * i + q * q)
        # In some parameter combinations (notably New CGA), i and q can both be 0 for the chosen reference pattern.
        # Avoid division-by-zero; if there is no chroma reference, disable IQ scaling (results in grayscale, which is safer).
        r = 0.0 if denom == 0.0 else (256.0 * self.mode_saturation / denom)

        iq_adjust_i = -(i * c + q * s) * r
        iq_adjust_q =  (q * c - i * s) * r

        self.video_ri = int(RI * iq_adjust_i + RQ * iq_adjust_q)
        self.video_rq = int(-RI * iq_adjust_q + RQ * iq_adjust_i)
        self.video_gi = int(GI * iq_adjust_i + GQ * iq_adjust_q)
        self.video_gq = int(-GI * iq_adjust_q + GQ * iq_adjust_i)
        self.video_bi = int(BI * iq_adjust_i + BQ * iq_adjust_q)
        self.video_bq = int(-BI * iq_adjust_q + BQ * iq_adjust_i)

        self.video_sharpness = int(self.sharpness * 256.0 / 100.0)
        self.cgamode = int(cgamode)

    def decode_scanline_rgba(self, border: int, in_rgbi: List[int]) -> List[Tuple[int,int,int]]:
        """Decode one scanline of RGBI nibbles into RGB tuples. Output width == len(in_rgbi)."""
        w = len(in_rgbi)
        if w < 4:
            return [(0,0,0)] * w

        blocks = w // 4

        # temp holds samples; we follow reenigne code closely
        temp = [0] * (w + 10)
        atemp = [0] * (w + 2)
        btemp = [0] * (w + 2)

        o_index = 0
        btab = self.composite_table[(border & 0x0F) * 68 : (border & 0x0F) * 68 + 68]

        for x in range(4):
            temp[o_index] = btab[(x + 3) & 3]
            o_index += 1

        temp[o_index] = int(self.composite_table[((border & 0x0F) << 6) | ((in_rgbi[0] & 0x0F) << 2) | 3])
        o_index += 1

        rgbi_index = 0
        for x in range(w - 1):
            a = in_rgbi[rgbi_index] & 0x0F
            b = in_rgbi[rgbi_index + 1] & 0x0F
            temp[o_index] = int(self.composite_table[(a << 6) | (b << 2) | (x & 3)])
            o_index += 1
            rgbi_index += 1

        temp[o_index] = int(self.composite_table[((in_rgbi[rgbi_index] & 0x0F) << 6) | ((border & 0x0F) << 2) | 3])
        o_index += 1

        for x in range(5):
            temp[o_index] = btab[x & 3]
            o_index += 1

        # build a/b temps
        i_index = 4
        ap_index = 1
        bp_index = 1
        for x in range(w + 2):
            atemp[ap_index + x - 1] = temp[i_index - 4] - ((temp[i_index - 2] - temp[i_index] + temp[i_index + 2]) << 1) + temp[i_index + 4]
            btemp[bp_index + x - 1] = (temp[i_index - 3] - temp[i_index - 1] + temp[i_index + 1] - temp[i_index + 3]) << 1
            i_index += 1

        # decode pixels
        i_index = 5
        temp[i_index - 1] = (temp[i_index - 1] << 3) - atemp[ap_index - 1]
        temp[i_index]     = (temp[i_index]     << 3) - atemp[ap_index]

        out = []
        for _ in range(blocks):
            for rot in range(4):
                temp[i_index + 1] = (temp[i_index + 1] << 3) - atemp[ap_index + 1]
                a = atemp[ap_index]
                b = btemp[bp_index]
                c = temp[i_index] + temp[i_index]
                d = temp[i_index - 1] + temp[i_index + 1]
                y = ((c + d) << 8) + self.video_sharpness * (c - d)

                if rot == 0:
                    rr = y + self.video_ri * a + self.video_rq * b
                    gg = y + self.video_gi * a + self.video_gq * b
                    bb = y + self.video_bi * a + self.video_bq * b
                elif rot == 1:
                    rr = y + self.video_ri * (-b) + self.video_rq * a
                    gg = y + self.video_gi * (-b) + self.video_gq * a
                    bb = y + self.video_bi * (-b) + self.video_bq * a
                elif rot == 2:
                    rr = y + self.video_ri * (-a) + self.video_rq * (-b)
                    gg = y + self.video_gi * (-a) + self.video_gq * (-b)
                    bb = y + self.video_bi * (-a) + self.video_bq * (-b)
                else:
                    rr = y + self.video_ri * b + self.video_rq * (-a)
                    gg = y + self.video_gi * b + self.video_gq * (-a)
                    bb = y + self.video_bi * b + self.video_bq * (-a)

                out.append((_re_byte_clamp(rr), _re_byte_clamp(gg), _re_byte_clamp(bb)))

                i_index += 1
                ap_index += 1
                bp_index += 1

        # if width wasn't divisible by 4, pad (shouldn't happen for our use)
        if len(out) < w:
            out.extend([out[-1]] * (w - len(out)))
        return out[:w]

# 16 possible 4-bit patterns across 4 hi-res pixels (LSB = first pixel).
# We use idx 0..15 mapped to bits of idx: [b0,b1,b2,b3] where b0 is leftmost.
_COMPOSITE_HIRES_PATTERNS = [[(i >> k) & 1 for k in range(4)] for i in range(16)]

# NTSC text-hack patterns (8 pixels wide) used by the 1024-color / "4K" CGA text composite trick.
# These are the two canonical phase patterns and their FG/BG inverted forms.
_TEXT_NTSC_PATTERNS_8 = [
    [1, 1, 0, 0, 1, 1, 0, 0],  # 0xCC
    [0, 1, 1, 0, 0, 1, 1, 0],  # 0x66
]


# Composite presets -> (hue_offset_deg, saturation, brightness, contrast, sharpness, new_cga, cgamode)
# cgamode is the timing/mode selector used by Reenigne's decoder.
#
# We intentionally expose ONLY the historically common "Old CGA" vs "New CGA" composite decodes.
# - Old CGA: Reenigne/Jenner baseline (no additional phase rotation)
# - New CGA: later IBM CGA revision look (different chroma mixing model; no extra rotation applied)
_COMPOSITE_PRESETS = {
    # NOTE:
    # For our *palette derivation* we drive Reenigne's decoder the same way his reference
    # harness does for the common "artifact color" workflow: 80-column text timing
    # (cgamode = 0b0_0001). Using the hi-res graphics flag (0b1_0110) enables the "hi-res
    # mono adjustment" path in update_cga16_color(), which can collapse the chroma reference
    # for New CGA and yields an effectively grayscale palette.
    "Old CGA": (0.0, 100.0, 0.0, 100.0, 0.0, False, 0b0_0001),
    "New CGA": (0.0, 100.0, 0.0, 100.0, 0.0, True,  0b0_0001),
}

_COMPOSITE_PALETTE_CACHE: Dict[str, List[Tuple[int,int,int]]] = {}

def _build_reenigne_composite_palette(preset_name: str) -> List[Tuple[int,int,int]]:
    """Return 16 RGB colors for the 16 4-bit hi-res patterns under the given preset."""
    if preset_name in _COMPOSITE_PALETTE_CACHE:
        return _COMPOSITE_PALETTE_CACHE[preset_name]

    params = _COMPOSITE_PRESETS.get(preset_name, _COMPOSITE_PRESETS["Old CGA"])
    hue, sat, bri, con, shp, new_cga, cgamode = params

    ctx = _ReCompositeContextPy()
    ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri, contrast=con, sharpness=shp, new_cga=new_cga)
    ctx.update_cga16_color(int(cgamode))

    # Build a long synthetic scanline to stabilize averaging.
    w = 640  # hi-res width
    cycles = w // 4

    palette = []
    for idx in range(16):
        bits = _COMPOSITE_HIRES_PATTERNS[idx]
        # Build RGBI nibbles: bit0->black/white in hires mode (0 or 15)
        in_line = []
        for c in range(cycles):
            for k in range(4):
                in_line.append(15 if bits[k] else 0)

        rgb = ctx.decode_scanline_rgba(border=0, in_rgbi=in_line)

        # Average each 4-pixel group down to 160 "logical" pixels, then average across line.
        rs = gs = bs = 0
        for c in range(cycles):
            base = c * 4
            r = (rgb[base][0] + rgb[base+1][0] + rgb[base+2][0] + rgb[base+3][0]) / 4.0
            g = (rgb[base][1] + rgb[base+1][1] + rgb[base+2][1] + rgb[base+3][1]) / 4.0
            b = (rgb[base][2] + rgb[base+1][2] + rgb[base+2][2] + rgb[base+3][2]) / 4.0
            rs += r; gs += g; bs += b
        rs /= cycles; gs /= cycles; bs /= cycles
        palette.append((int(round(rs)), int(round(gs)), int(round(bs))))

    _COMPOSITE_PALETTE_CACHE[preset_name] = palette
    return palette

# Public dict used by the GUI drop-down (computed lazily; values filled on demand)
COMPOSITE_PALETTES = {name: None for name in _COMPOSITE_PRESETS.keys()}


# --- NTSC Text 4K ("1024-color" text hack) helpers ---------------------------

_TEXT_NTSC_4K_LUT_CACHE = {}  # preset_name -> list of entries (avg_rgb, fg, bg, pattern_bits)


def _quantize_rgb444(rgb):
    """Quantize an (r,g,b) tuple to RGB444 (4096-color)."""
    r, g, b = rgb
    r4 = int(round(r / 255.0 * 15.0))
    g4 = int(round(g / 255.0 * 15.0))
    b4 = int(round(b / 255.0 * 15.0))
    r8 = int(round(r4 * 255.0 / 15.0))
    g8 = int(round(g4 * 255.0 / 15.0))
    b8 = int(round(b4 * 255.0 / 15.0))
    return (r8, g8, b8)


def _build_text_ntsc_4k_lut(preset_name):
    """Build a lookup table of the 1024 (fg,bg,pattern) combinations.

    Each entry is (avg_rgb444, fg_idx, bg_idx, pattern_bits_8).
    We compute the apparent color by running the Reenigne/Jenner decoder
    over an 8-pixel pattern repeated across 640 pixels, then averaging.
    """
    if preset_name in _TEXT_NTSC_4K_LUT_CACHE:
        return _TEXT_NTSC_4K_LUT_CACHE[preset_name]

    params = _COMPOSITE_PRESETS.get(preset_name, _COMPOSITE_PRESETS["Old CGA"])
    hue, sat, bri, con, shp, new_cga, cgamode = params
    ctx = _ReCompositeContextPy()
    ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri, contrast=con, sharpness=shp, new_cga=new_cga)
    ctx.update_cga16_color(int(cgamode))

    w = 640
    reps = w // 8

    entries = []
    # Two base patterns, plus fg/bg swapped.
    for pat in _TEXT_NTSC_PATTERNS_8:
        for swap in (False, True):
            for fg in range(16):
                for bg in range(16):
                    # Build a full scanline of RGBI nibbles
                    line = []
                    for _ in range(reps):
                        for bit in pat:
                            use_fg = (bit == 1)
                            if swap:
                                use_fg = not use_fg
                            line.append(fg if use_fg else bg)

                    rgb = ctx.decode_scanline_rgba(border=0, in_rgbi=line)

                    # Average the full scanline (this is a "cell color" LUT)
                    rs = gs = bs = 0.0
                    for (r, g, b) in rgb:
                        rs += r; gs += g; bs += b
                    rs /= float(len(rgb)); gs /= float(len(rgb)); bs /= float(len(rgb))
                    avg = _quantize_rgb444((int(round(rs)), int(round(gs)), int(round(bs))))
                    entries.append((avg, fg, bg, pat, swap))

    _TEXT_NTSC_4K_LUT_CACHE[preset_name] = entries
    return entries



# 16 possible 2-pixel pairs in 2bpp (values 0..3). We map composite "color index" 0..15 to these pairs.
COMPOSITE_PAIR_TABLE = [(a, b) for a in range(4) for b in range(4)]
# --- CGA ROM font data (256 chars x 8 bytes) --------------------------------
# Parsed from the user's provided DATA dump (each line = 64 bits = 8 rows).
# We use ONLY row 0 (the first scanline of each 8x8 glyph) for the "text-row"
# graphics trick.
_CGA_FONT_DATA_BLOB = """
DATA "0000000000000000000000000000000000000000000000000000000000000000"
DATA "0111111010000001101001011000000110111101100110011000000101111110"
DATA "0111111011111111110110111111111111000011111001111111111101111110"
DATA "0110110011111110111111101111111001111100001110000001000000000000"
DATA "0001000000111000011111001111111001111100001110000001000000000000"
DATA "0011100001111100001110001111111011111110110101100001000000111000"
DATA "0001000000010000001110000111110011111110011111000001000000111000"
DATA "0000000000000000000110000011110000111100000110000000000000000000"
DATA "1111111111111111111001111100001111000011111001111111111111111111"
DATA "0000000000111100011001100100001001000010011001100011110000000000"
DATA "1111111111000011100110011011110110111101100110011100001111111111"
DATA "0000111100000111000011110111110111001100110011001100110001111000"
DATA "0011110001100110011001100110011000111100000110000111111000011000"
DATA "0011111100110011001111110011000000110000011100001111000011100000"
DATA "0111111101100011011111110110001101100011011001111110011011000000"
DATA "0001100011011011001111001110011111100111001111001101101100011000"
DATA "1000000011100000111110001111111011111000111000001000000000000000"
DATA "0000001000001110001111101111111000111110000011100000001000000000"
DATA "0001100000111100011111100001100000011000011111100011110000011000"
DATA "0110011001100110011001100110011001100110000000000110011000000000"
DATA "0111111111011011110110110111101100011011000110110001101100000000"
DATA "0011111001100011001110000110110001101100001110001100110001111000"
DATA "0000000000000000000000000000000001111110011111100111111000000000"
DATA "0001100000111100011111100001100001111110001111000001100011111111"
DATA "0001100000111100011111100001100000011000000110000001100000000000"
DATA "0001100000011000000110000001100001111110001111000001100000000000"
DATA "0000000000011000000011001111111000001100000110000000000000000000"
DATA "0000000000110000011000001111111001100000001100000000000000000000"
DATA "0000000000000000110000001100000011000000111111100000000000000000"
DATA "0000000000100100011001101111111101100110001001000000000000000000"
DATA "0000000000011000001111000111111011111111111111110000000000000000"
DATA "0000000011111111111111110111111000111100000110000000000000000000"
DATA "0000000000000000000000000000000000000000000000000000000000000000"
DATA "0011000001111000011110000011000000110000000000000011000000000000"
DATA "0110110001101100011011000000000000000000000000000000000000000000"
DATA "0110110001101100111111100110110011111110011011000110110000000000"
DATA "0011000001111100110000000111100000001100111110000011000000000000"
DATA "0000000011000110110011000001100000110000011001101100011000000000"
DATA "0011100001101100001110000111011011011100110011000111011000000000"
DATA "0110000001100000110000000000000000000000000000000000000000000000"
DATA "0001100000110000011000000110000001100000001100000001100000000000"
DATA "0110000000110000000110000001100000011000001100000110000000000000"
DATA "0000000001100110001111001111111100111100011001100000000000000000"
DATA "0000000000110000001100001111110000110000001100000000000000000000"
DATA "0000000000000000000000000000000000000000001100000011000001100000"
DATA "0000000000000000000000001111110000000000000000000000000000000000"
DATA "0000000000000000000000000000000000000000001100000011000000000000"
DATA "0000011000001100000110000011000001100000110000001000000000000000"
DATA "0111110011000110110011101101111011110110111001100111110000000000"
DATA "0011000001110000001100000011000000110000001100001111110000000000"
DATA "0111100011001100000011000011100001100000110011001111110000000000"
DATA "0111100011001100000011000011100000001100110011000111100000000000"
DATA "0001110000111100011011001100110011111110000011000001111000000000"
DATA "1111110011000000111110000000110000001100110011000111100000000000"
DATA "0011100001100000110000001111100011001100110011000111100000000000"
DATA "1111110011001100000011000001100000110000001100000011000000000000"
DATA "0111100011001100110011000111100011001100110011000111100000000000"
DATA "0111100011001100110011000111110000001100000110000111000000000000"
DATA "0000000000110000001100000000000000000000001100000011000000000000"
DATA "0000000000110000001100000000000000000000001100000011000001100000"
DATA "0001100000110000011000001100000001100000001100000001100000000000"
DATA "0000000000000000111111000000000000000000111111000000000000000000"
DATA "0110000000110000000110000000110000011000001100000110000000000000"
DATA "0111100011001100000011000001100000110000000000000011000000000000"
DATA "0111110011000110110111101101111011011110110000000111100000000000"
DATA "0011000001111000110011001100110011111100110011001100110000000000"
DATA "1111110001100110011001100111110001100110011001101111110000000000"
DATA "0011110001100110110000001100000011000000011001100011110000000000"
DATA "1111100001101100011001100110011001100110011011001111100000000000"
DATA "1111111001100010011010000111100001101000011000101111111000000000"
DATA "1111111001100010011010000111100001101000011000001111000000000000"
DATA "0011110001100110110000001100000011001110011001100011111000000000"
DATA "1100110011001100110011001111110011001100110011001100110000000000"
DATA "0111100000110000001100000011000000110000001100000111100000000000"
DATA "0001111000001100000011000000110011001100110011000111100000000000"
DATA "1110011001100110011011000111100001101100011001101110011000000000"
DATA "1111000001100000011000000110000001100010011001101111111000000000"
DATA "1100011011101110111111101111111011010110110001101100011000000000"
DATA "1100011011100110111101101101111011001110110001101100011000000000"
DATA "0011100001101100110001101100011011000110011011000011100000000000"
DATA "1111110001100110011001100111110001100000011000001111000000000000"
DATA "0111100011001100110011001100110011011100011110000001110000000000"
DATA "1111110001100110011001100111110001101100011001101110011000000000"
DATA "0111100011001100011000000011000000011000110011000111100000000000"
DATA "1111110010110100001100000011000000110000001100000111100000000000"
DATA "1100110011001100110011001100110011001100110011001111110000000000"
DATA "1100110011001100110011001100110011001100011110000011000000000000"
DATA "1100011011000110110001101101011011111110111011101100011000000000"
DATA "1100011011000110011011000011100000111000011011001100011000000000"
DATA "1100110011001100110011000111100000110000001100000111100000000000"
DATA "1111111011000110100011000001100000110010011001101111111000000000"
DATA "0111100001100000011000000110000001100000011000000111100000000000"
DATA "1100000001100000001100000001100000001100000001100000001000000000"
DATA "0111100000011000000110000001100000011000000110000111100000000000"
DATA "0001000000111000011011001100011000000000000000000000000000000000"
DATA "0000000000000000000000000000000000000000000000000000000011111111"
DATA "0011000000110000000110000000000000000000000000000000000000000000"
DATA "0000000000000000011110000000110001111100110011000111011000000000"
DATA "1110000001100000011000000111110001100110011001101101110000000000"
DATA "0000000000000000011110001100110011000000110011000111100000000000"
DATA "0001110000001100000011000111110011001100110011000111011000000000"
DATA "0000000000000000011110001100110011111100110000000111100000000000"
DATA "0011100001101100011000001111000001100000011000001111000000000000"
DATA "0000000000000000011101101100110011001100011111000000110011111000"
DATA "1110000001100000011011000111011001100110011001101110011000000000"
DATA "0011000000000000011100000011000000110000001100000111100000000000"
DATA "0000110000000000000011000000110000001100110011001100110001111000"
DATA "1110000001100000011001100110110001111000011011001110011000000000"
DATA "0111000000110000001100000011000000110000001100000111100000000000"
DATA "0000000000000000110011001111111011111110110101101100011000000000"
DATA "0000000000000000111110001100110011001100110011001100110000000000"
DATA "0000000000000000011110001100110011001100110011000111100000000000"
DATA "0000000000000000110111000110011001100110011111000110000011110000"
DATA "0000000000000000011101101100110011001100011111000000110000011110"
DATA "0000000000000000110111000111011001100110011000001111000000000000"
DATA "0000000000000000011111001100000001111000000011001111100000000000"
DATA "0001000000110000011111000011000000110000001101000001100000000000"
DATA "0000000000000000110011001100110011001100110011000111011000000000"
DATA "0000000000000000110011001100110011001100011110000011000000000000"
DATA "0000000000000000110001101101011011111110111111100110110000000000"
DATA "0000000000000000110001100110110000111000011011001100011000000000"
DATA "0000000000000000110011001100110011001100011111000000110011111000"
DATA "0000000000000000111111001001100000110000011001001111110000000000"
DATA "0001110000110000001100001110000000110000001100000001110000000000"
DATA "0001100000011000000110000000000000011000000110000001100000000000"
DATA "1110000000110000001100000001110000110000001100001110000000000000"
DATA "0111011011011100000000000000000000000000000000000000000000000000"
DATA "0000000000010000001110000110110011000110110001101111111000000000"
DATA "0111100011001100110000001100110001111000000110000000110001111000"
DATA "0000000011001100000000001100110011001100110011000111111000000000"
DATA "0001110000000000011110001100110011111100110000000111100000000000"
DATA "0111111011000011001111000000011000111110011001100011111100000000"
DATA "1100110000000000011110000000110001111100110011000111111000000000"
DATA "1110000000000000011110000000110001111100110011000111111000000000"
DATA "0011000000110000011110000000110001111100110011000111111000000000"
DATA "0000000000000000011110001100000011000000011110000000110000111000"
DATA "0111111011000011001111000110011001111110011000000011110000000000"
DATA "1100110000000000011110001100110011111100110000000111100000000000"
DATA "1110000000000000011110001100110011111100110000000111100000000000"
DATA "1100110000000000011100000011000000110000001100000111100000000000"
DATA "0111110011000110001110000001100000011000000110000011110000000000"
DATA "1110000000000000011100000011000000110000001100000111100000000000"
DATA "1100011000111000011011001100011011111110110001101100011000000000"
DATA "0011000000110000000000000111100011001100111111001100110000000000"
DATA "0001110000000000111111000110000001111000011000001111110000000000"
DATA "0000000000000000011111110000110001111111110011000111111100000000"
DATA "0011111001101100110011001111111011001100110011001100111000000000"
DATA "0111100011001100000000000111100011001100110011000111100000000000"
DATA "0000000011001100000000000111100011001100110011000111100000000000"
DATA "0000000011100000000000000111100011001100110011000111100000000000"
DATA "0111100011001100000000001100110011001100110011000111111000000000"
DATA "0000000011100000000000001100110011001100110011000111111000000000"
DATA "0000000011001100000000001100110011001100011111000000110011111000"
DATA "1100001100011000001111000110011001100110001111000001100000000000"
DATA "1100110000000000110011001100110011001100110011000111100000000000"
DATA "0001100000011000011111101100000011000000011111100001100000011000"
DATA "0011100001101100011001001111000001100000111001101111110000000000"
DATA "1100110011001100011110001111110000110000111111000011000000110000"
DATA "1111100011001100110011001111101011000110110011111100011011000111"
DATA "0000111000011011000110000011110000011000000110001101100001110000"
DATA "0001110000000000011110000000110001111100110011000111111000000000"
DATA "0011100000000000011100000011000000110000001100000111100000000000"
DATA "0000000000011100000000000111100011001100110011000111100000000000"
DATA "0000000000011100000000001100110011001100110011000111111000000000"
DATA "0000000011111000000000001111100011001100110011001100110000000000"
DATA "1111110000000000110011001110110011111100110111001100110000000000"
DATA "0011110001101100011011000011111000000000011111100000000000000000"
DATA "0011100001101100011011000011100000000000011111000000000000000000"
DATA "0011000000000000001100000110000011000000110011000111100000000000"
DATA "0000000000000000000000001111110011000000110000000000000000000000"
DATA "0000000000000000000000001111110000001100000011000000000000000000"
DATA "1100001111000110110011001101111000110011011001101100110000001111"
DATA "1100001111000110110011001101101100110111011011111100111100000011"
DATA "0001100000011000000000000001100000011000000110000001100000000000"
DATA "0000000000110011011001101100110001100110001100110000000000000000"
DATA "0000000011001100011001100011001101100110110011000000000000000000"
DATA "0010001010001000001000101000100000100010100010000010001010001000"
DATA "0101010110101010010101011010101001010101101010100101010110101010"
DATA "1101101101110111110110111110111011011011011101111101101111101110"
DATA "0001100000011000000110000001100000011000000110000001100000011000"
DATA "0001100000011000000110000001100011111000000110000001100000011000"
DATA "0001100000011000111110000001100011111000000110000001100000011000"
DATA "0011011000110110001101100011011011110110001101100011011000110110"
DATA "0000000000000000000000000000000011111110001101100011011000110110"
DATA "0000000000000000111110000001100011111000000110000001100000011000"
DATA "0011011000110110111101100000011011110110001101100011011000110110"
DATA "0011011000110110001101100011011000110110001101100011011000110110"
DATA "0000000000000000111111100000011011110110001101100011011000110110"
DATA "0011011000110110111101100000011011111110000000000000000000000000"
DATA "0011011000110110001101100011011011111110000000000000000000000000"
DATA "0001100000011000111110000001100011111000000000000000000000000000"
DATA "0000000000000000000000000000000011111000000110000001100000011000"
DATA "0001100000011000000110000001100000011111000000000000000000000000"
DATA "0001100000011000000110000001100011111111000000000000000000000000"
DATA "0000000000000000000000000000000011111111000110000001100000011000"
DATA "0001100000011000000110000001100000011111000110000001100000011000"
DATA "0000000000000000000000000000000011111111000000000000000000000000"
DATA "0001100000011000000110000001100011111111000110000001100000011000"
DATA "0001100000011000000111110001100000011111000110000001100000011000"
DATA "0011011000110110001101100011011000110111001101100011011000110110"
DATA "0011011000110110001101110011000000111111000000000000000000000000"
DATA "0000000000000000001111110011000000110111001101100011011000110110"
DATA "0011011000110110111101110000000011111111000000000000000000000000"
DATA "0000000000000000111111110000000011110111001101100011011000110110"
DATA "0011011000110110001101110011000000110111001101100011011000110110"
DATA "0000000000000000111111110000000011111111000000000000000000000000"
DATA "0011011000110110111101110000000011110111001101100011011000110110"
DATA "0001100000011000111111110000000011111111000000000000000000000000"
DATA "0011011000110110001101100011011011111111000000000000000000000000"
DATA "0000000000000000111111110000000011111111000110000001100000011000"
DATA "0000000000000000000000000000000011111111001101100011011000110110"
DATA "0011011000110110001101100011011000111111000000000000000000000000"
DATA "0001100000011000000111110001100000011111000000000000000000000000"
DATA "0000000000000000000111110001100000011111000110000001100000011000"
DATA "0000000000000000000000000000000000111111001101100011011000110110"
DATA "0011011000110110001101100011011011111111001101100011011000110110"
DATA "0001100000011000111111110001100011111111000110000001100000011000"
DATA "0001100000011000000110000001100011111000000000000000000000000000"
DATA "0000000000000000000000000000000000011111000110000001100000011000"
DATA "1111111111111111111111111111111111111111111111111111111111111111"
DATA "0000000000000000000000000000000011111111111111111111111111111111"
DATA "1111000011110000111100001111000011110000111100001111000011110000"
DATA "0000111100001111000011110000111100001111000011110000111100001111"
DATA "1111111111111111111111111111111100000000000000000000000000000000"
DATA "0000000000000000011101101101110011001000110111000111011000000000"
DATA "0000000001111000110011001111100011001100111110001100000011000000"
DATA "0000000011111100110011001100000011000000110000001100000000000000"
DATA "0000000011111110011011000110110001101100011011000110110000000000"
DATA "1111110011001100011000000011000001100000110011001111110000000000"
DATA "0000000000000000011111101101100011011000110110000111000000000000"
DATA "0000000001100110011001100110011001100110011111000110000011000000"
DATA "0000000001110110110111000001100000011000000110000001100000000000"
DATA "1111110000110000011110001100110011001100011110000011000011111100"
DATA "0011100001101100110001101111111011000110011011000011100000000000"
DATA "0011100001101100110001101100011001101100011011001110111000000000"
DATA "0001110000110000000110000111110011001100110011000111100000000000"
DATA "0000000000000000011111101101101111011011011111100000000000000000"
DATA "0000011000001100011111101101101111011011011111100110000011000000"
DATA "0011100001100000110000001111100011000000011000000011100000000000"
DATA "0111100011001100110011001100110011001100110011001100110000000000"
DATA "0000000011111100000000001111110000000000111111000000000000000000"
DATA "0011000000110000111111000011000000110000000000001111110000000000"
DATA "0110000000110000000110000011000001100000000000001111110000000000"
DATA "0001100000110000011000000011000000011000000000001111110000000000"
DATA "0000111000011011000110110001100000011000000110000001100000011000"
DATA "0001100000011000000110000001100000011000110110001101100001110000"
DATA "0011000000110000000000001111110000000000001100000011000000000000"
DATA "0000000001110110110111000000000001110110110111000000000000000000"
DATA "0011100001101100011011000011100000000000000000000000000000000000"
DATA "0000000000000000000000000001100000011000000000000000000000000000"
DATA "0000000000000000000000000000000000011000000000000000000000000000"
DATA "0000111100001100000011000000110011101100011011000011110000011100"
DATA "0111100001101100011011000110110001101100000000000000000000000000"
DATA "0111000000011000001100000110000001111000000000000000000000000000"
DATA "0000000000000000001111000011110000111100001111000000000000000000"
DATA "0000000000000000000000000000000000000000000000000000000000000000"
"""

def _parse_cga_font_data_blob(data_blob: str):
    lines = re.findall(r'DATA\s+"([01]{64})"', data_blob)
    if len(lines) != 256:
        raise ValueError(f"Expected 256 DATA lines, got {len(lines)}")
    font = []
    for s in lines:
        rows = [s[i*8:(i+1)*8] for i in range(8)]
        font.append([int(r, 2) for r in rows])
    return font

# FONT[char_code][row] => 8-bit mask (bit7=leftmost pixel)
_CGA_FONT = _parse_cga_font_data_blob(_CGA_FONT_DATA_BLOB)
# Convenience: first two scanline masks (row 0 and row 1) for each character.
# Each mask is an 8-bit value; bit 7 is the leftmost pixel.
_CGA_FONT_ROW01 = [(rows[0], rows[1]) for rows in _CGA_FONT]

# Reverse lookup: (row0,row1) -> first character code that matches those two scanlines
_CGA_ROW01_TO_CHAR = {}
for _i, (_r0, _r1) in enumerate(_CGA_FONT_ROW01):
    _CGA_ROW01_TO_CHAR.setdefault((_r0, _r1), _i)


def _hamming16(a0: int, a1: int, b0: int, b1: int) -> int:
    """Hamming distance between two 16-bit masks represented as two bytes."""
    return (popcount(a0 ^ b0) + popcount(a1 ^ b1))

# --- Basic helpers -----------------------------------------------------------


def clamp(value, lo=0.0, hi=255.0):
    return lo if value < lo else hi if value > hi else value


# --- Dithering and quantization helpers --------------------------------------




def clamp255(v):
    """Clamp numeric value into [0,255] as float."""
    return 0.0 if v < 0.0 else 255.0 if v > 255.0 else float(v)
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


# --- Error diffusion (variable intensity) ------------------------------------


def _error_diffusion_dither(image, palette, kernel, divisor, intensity=1.0, serpentine=True):
    """
    Generic error diffusion dithering.

    intensity: 0.0..1.0 controls how much quantization error is diffused.
               1.0 = classic algorithm; 0.0 = no diffusion (nearest color).
    serpentine: alternate scan direction each row (often reduces artifacts).
    kernel: list of (dx, dy, weight) offsets for forward scan direction.
            For reverse scan, dx is mirrored.
    """
    intensity = 0.0 if intensity < 0.0 else 1.0 if intensity > 1.0 else float(intensity)

    w, h = image.size
    buf = [[[float(c) for c in image.getpixel((x, y))]
            for x in range(w)] for y in range(h)]
    indices = [0] * (w * h)

    def clamp255(v):
        return 0.0 if v < 0.0 else 255.0 if v > 255.0 else v

    for y in range(h):
        sum_abs_err = 0.0
        sum_abs_to_next = 0.0
        max_abs_to_next = 0.0
        zero_err_count = 0
        sample_lines = []
        sample_lines = []
        sample_limit = 16  # pixels
        rev = serpentine and (y % 2 == 1)
        x_range = range(w - 1, -1, -1) if rev else range(w)

        for x in x_range:
            old = buf[y][x]
            idx = nearest_palette_index(old, palette)
            new = palette[idx]
            indices[y * w + x] = idx

            if intensity <= 0.0:
                continue

            err = [(old[i] - new[i]) * intensity for i in range(3)]

            for dx, dy, wgt in kernel:
                ddx = -dx if rev else dx
                xx = x + ddx
                yy = y + dy
                if 0 <= xx < w and 0 <= yy < h:
                    p = buf[yy][xx]
                    f = wgt / divisor
                    p[0] = clamp255(p[0] + err[0] * f)
                    p[1] = clamp255(p[1] + err[1] * f)
                    p[2] = clamp255(p[2] + err[2] * f)

    return indices


# Kernels are defined for left-to-right scan.
_FS_KERNEL = [(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)]  # /16
_ATKINSON_KERNEL = [(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1)]  # /8


# Horizontal Striped (all error goes straight down)
_HSTRIPE_KERNEL = [(0, 1, 1)]  # /1
# Larger diffusion kernels (classic)
_JJN_KERNEL = [
    (1, 0, 7), (2, 0, 5),
    (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
    (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1),
]  # /48

_STUCKI_KERNEL = [
    (1, 0, 8), (2, 0, 4),
    (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2),
    (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1),
]  # /42

_BURKES_KERNEL = [
    (1, 0, 8), (2, 0, 4),
    (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2),
]  # /32

_SIERRA_KERNEL = [
    (1, 0, 5), (2, 0, 3),
    (-2, 1, 2), (-1, 1, 4), (0, 1, 5), (1, 1, 4), (2, 1, 2),
    (-1, 2, 2), (0, 2, 3), (1, 2, 2),
]  # /32

_SIERRA2_KERNEL = [
    (1, 0, 4), (2, 0, 3),
    (-2, 1, 1), (-1, 1, 2), (0, 1, 3), (1, 1, 2), (2, 1, 1),
]  # /16

_SIERRALITE_KERNEL = [
    (1, 0, 2),
    (-1, 1, 1), (0, 1, 1),
]  # /4


def floyd_steinberg_dither(image, palette, intensity=1.0):
    """Floyd–Steinberg error diffusion, with variable intensity."""
    return _error_diffusion_dither(image, palette, _FS_KERNEL, 16, intensity=intensity, serpentine=True)


def atkinson_dither(image, palette, intensity=1.0):
    """Atkinson error diffusion, with variable intensity."""
    return _error_diffusion_dither(image, palette, _ATKINSON_KERNEL, 8, intensity=intensity, serpentine=True)


def jarvis_judice_ninke_dither(image, palette, intensity=1.0):
    """Jarvis–Judice–Ninke error diffusion."""
    return _error_diffusion_dither(image, palette, _JJN_KERNEL, 48, intensity=intensity, serpentine=True)


def stucki_dither(image, palette, intensity=1.0):
    """Stucki error diffusion."""
    return _error_diffusion_dither(image, palette, _STUCKI_KERNEL, 42, intensity=intensity, serpentine=True)


def burkes_dither(image, palette, intensity=1.0):
    """Burkes error diffusion."""
    return _error_diffusion_dither(image, palette, _BURKES_KERNEL, 32, intensity=intensity, serpentine=True)


def sierra_dither(image, palette, intensity=1.0):
    """Sierra (3-row) error diffusion."""
    return _error_diffusion_dither(image, palette, _SIERRA_KERNEL, 32, intensity=intensity, serpentine=True)


def sierra2_dither(image, palette, intensity=1.0):
    """Two-row Sierra error diffusion."""
    return _error_diffusion_dither(image, palette, _SIERRA2_KERNEL, 16, intensity=intensity, serpentine=True)


def sierra_lite_dither(image, palette, intensity=1.0):
    """Sierra Lite error diffusion."""
    return _error_diffusion_dither(image, palette, _SIERRALITE_KERNEL, 4, intensity=intensity, serpentine=True)





# Ordered (Bayer-style) matrices ------------------------------------------------
#
# v13 change:
#   - Ordered dithering is now its own "family" (separate from error diffusion).
#   - Matrix size is user-selectable (2..16).
#   - We generate threshold matrices on demand and cache them.
#
# We generate a classic Bayer matrix for power-of-two sizes (2,4,8,16) via recursion.
# For non power-of-two sizes (e.g., 3,5,6,...,15), we derive a usable matrix by
# cropping the next power-of-two Bayer matrix and then re-ranking values to 0..N^2-1.
# This isn't "perfect blue-noise", but it produces a stable, visible ordered dither
# and is fast / deterministic.

_ORDERED_MATRIX_CACHE = {}

def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0

def _next_power_of_two(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return p

def _bayer_matrix_pow2(n: int):
    """Generate an n×n Bayer threshold matrix for n in {2,4,8,16,...}."""
    if n == 2:
        return [
            [0, 2],
            [3, 1],
        ]
    half = n // 2
    prev = _bayer_matrix_pow2(half)
    out = [[0] * n for _ in range(n)]
    for y in range(half):
        for x in range(half):
            v = prev[y][x]
            out[y][x] = 4 * v + 0
            out[y][x + half] = 4 * v + 2
            out[y + half][x] = 4 * v + 3
            out[y + half][x + half] = 4 * v + 1
    return out

def get_ordered_matrix(n: int):
    """
    Return an n×n ordered-dither threshold matrix with values 0..(n*n-1).

    - Power-of-two n: classic Bayer matrix.
    - Non power-of-two n: crop next power-of-two Bayer and re-rank to 0..n^2-1.
    """
    n = int(n)
    if n < 2:
        n = 2
    if n > 16:
        n = 16

    cached = _ORDERED_MATRIX_CACHE.get(n)
    if cached is not None:
        return cached

    if _is_power_of_two(n):
        mat = _bayer_matrix_pow2(n)
        _ORDERED_MATRIX_CACHE[n] = mat
        return mat

    p2 = _next_power_of_two(n)
    base = _bayer_matrix_pow2(p2)
    cropped = [row[:n] for row in base[:n]]

    # Re-rank to ensure we span 0..n^2-1 with strictly increasing thresholds.
    flat = [cropped[y][x] for y in range(n) for x in range(n)]
    order = sorted(range(n * n), key=lambda i: flat[i])
    ranked = [0] * (n * n)
    for rank, idx in enumerate(order):
        ranked[idx] = rank
    mat = [[ranked[y * n + x] for x in range(n)] for y in range(n)]

    _ORDERED_MATRIX_CACHE[n] = mat
    return mat


def ordered_dither(image, palette, matrix_size=4, strength=1.0):
    """
    Ordered dithering using an N×N threshold matrix (2..16).

    Behavior:
      - 2-color palettes: true ordered thresholding by luminance coverage:
            f = (lum - lum_dark) / (lum_light - lum_dark)
            choose light if f > t else dark
        This makes the pattern *very* obvious in mono modes.
      - 3+ colors: apply a luminance-style offset before nearest-color quantization.
        (This is not mathematically perfect, but gives a controllable ordered texture.)

    strength:
      - 0.0..3.0 (GUI enforces)
      - For 2-color palettes, strength scales how aggressively we push toward dark/light
        (implemented as a slight contrast expansion around the palette midpoint).
      - For 3+ colors, strength scales the RGB offset amplitude.
    """
    w, h = image.size
    n = int(matrix_size)
    if n < 2:
        n = 2
    if n > 16:
        n = 16

    matrix = get_ordered_matrix(n)
    denom = float(n * n)  # matrix values are 0..n^2-1
    strength = 0.0 if strength < 0.0 else 3.0 if strength > 3.0 else float(strength)

    pixels = image.load()
    indices = [0] * (w * h)

    def luma(rgb):
        r, g, b = rgb
        return 0.299 * r + 0.587 * g + 0.114 * b

    if len(palette) == 2:
        # 2-color ordered dithering: always dither as if it were pure black/white,
        # then map "white" to palette[1] (foreground) regardless of its luminance.
        # This makes the ordered pattern behave predictably in 640x200 mono mode.
        dark_i, light_i = 0, 1
        ld, ll = 0.0, 255.0

        # Optional mild contrast expansion so low-contrast pairs still show pattern
        mid = (ld + ll) * 0.5
        span = (ll - ld) * 0.5
        span = span if span > 1e-6 else 1.0
        # strength=1 => no extra expansion; strength=0 => more expansion
        # (keep it subtle; expansion max 25%)
        expand = 1.0 + (1.0 - strength) * 0.25

        for y in range(h):
            sum_abs_err = 0.0
            sum_abs_to_next = 0.0
            max_abs_to_next = 0.0
            for x in range(w):
                r, g, b = pixels[x, y]
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                # Expand around midpoint
                lum = mid + (lum - mid) * expand
                # Coverage fraction of "light"
                f = (lum - ld) / (ll - ld)
                if f < 0.0:
                    f = 0.0
                elif f > 1.0:
                    f = 1.0

                t = matrix[y % n][x % n] / denom  # 0..1
                indices[y * w + x] = light_i if f > t else dark_i
        return indices

    # 3+ color palettes: offset then quantize
    # amplitude chosen so ordered is visible in 2-bit / 4-color palettes
    amplitude = 64.0 * strength

    for y in range(h):
        sum_abs_err = 0.0
        sum_abs_to_next = 0.0
        max_abs_to_next = 0.0
        for x in range(w):
            r, g, b = pixels[x, y]
            t = matrix[y % n][x % n] / denom  # 0..1
            offset = (t - 0.5) * amplitude
            rr = clamp(r + offset)
            gg = clamp(g + offset)
            bb = clamp(b + offset)
            indices[y * w + x] = nearest_palette_index((rr, gg, bb), palette)

    return indices


def no_dither(image, palette):
    """Plain nearest-color quantization without dithering."""
    w, h = image.size
    indices = [0] * (w * h)
    pixels = image.load()
    for y in range(h):
        sum_abs_err = 0.0
        sum_abs_to_next = 0.0
        max_abs_to_next = 0.0
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


# --- DOS .COM export (static CGA) --------------------------------------------

def _pack_cga_16k_interleaved(bytes_per_scanline: int, rows: int, row_bytes_func):
    """
    Pack CGA memory as 2 banks of 8KB:
      even scanlines 0,2,4.. go to bank0 at offsets (y//2)*bytes_per_scanline
      odd  scanlines 1,3,5.. go to bank1 at offsets 0x2000 + (y//2)*bytes_per_scanline
    Total returned size is 16384 bytes (16KB), with unused padding at end of each bank.
    """
    out = bytearray(16384)
    for y in range(rows):
        bank_base = 0x0000 if (y % 2 == 0) else 0x2000
        off = bank_base + (y // 2) * bytes_per_scanline
        rb = row_bytes_func(y)
        out[off:off + bytes_per_scanline] = rb
    return bytes(out)


def pack_cga_320x200_4color_vram(pimg: Image.Image) -> bytes:
    """Pack a 320x200 'P' image with indices 0..3 into CGA 2bpp VRAM (16KB)."""
    if pimg.mode != "P":
        raise ValueError("Expected palettized 'P' image for CGA packer.")
    w, h = pimg.size
    if (w, h) != (320, 200):
        raise ValueError(f"Expected 320x200, got {w}x{h}.")
    data = list(pimg.getdata())

    def row_bytes(y: int) -> bytes:
        base = y * 320
        rb = bytearray(80)
        for bx in range(80):
            x = bx * 4
            p0 = data[base + x + 0] & 3
            p1 = data[base + x + 1] & 3
            p2 = data[base + x + 2] & 3
            p3 = data[base + x + 3] & 3
            rb[bx] = (p0 << 6) | (p1 << 4) | (p2 << 2) | (p3 << 0)
        return bytes(rb)

    return _pack_cga_16k_interleaved(80, 200, row_bytes)


def pack_cga_640x200_2color_vram(pimg: Image.Image) -> bytes:
    """Pack a 640x200 'P' image with indices 0..1 into CGA 1bpp VRAM (16KB)."""
    if pimg.mode != "P":
        raise ValueError("Expected palettized 'P' image for CGA packer.")
    w, h = pimg.size
    if (w, h) != (640, 200):
        raise ValueError(f"Expected 640x200, got {w}x{h}.")
    data = list(pimg.getdata())

    def row_bytes(y: int) -> bytes:
        base = y * 640
        rb = bytearray(80)
        for bx in range(80):
            x = bx * 8
            b = 0
            for i in range(8):
                b = (b << 1) | (data[base + x + i] & 1)
            rb[bx] = b
        return bytes(rb)

    return _pack_cga_16k_interleaved(80, 200, row_bytes)



def pack_cga_160x100_16color_text_vram(pimage) -> bytes:
    """Pack a 160x100 image into CGA 160x100x16 pseudo-graphics text buffer (80x100 cells)."""
    w, h = pimage.size
    if (w, h) != (160, 100):
        raise ValueError(f"pack_cga_160x100_16color_text_vram expects 160x100 image, got {w}x{h}")

    # Ensure we have RGB tuples even if the source is paletted ('P') or grayscale ('L')
    if getattr(pimage, 'mode', None) != 'RGB':
        pimage = pimage.convert('RGB')
    px = pimage.load()
    out = bytearray(80 * 100 * 2)
    di = 0
    for y in range(100):
        for cx in range(80):
            bg_rgb = px[cx * 2 + 0, y][:3]
            fg_rgb = px[cx * 2 + 1, y][:3]
            bg_idx = nearest_palette_index(bg_rgb, CGA_COLORS) & 0x0F
            fg_idx = nearest_palette_index(fg_rgb, CGA_COLORS) & 0x0F
            out[di + 0] = 0xDE
            out[di + 1] = ((bg_idx & 0x0F) << 4) | (fg_idx & 0x0F)
            di += 2
    return bytes(out)



def pack_text_80x100_char16(pimg: Image.Image) -> bytes:
    """Pack a 640x200 'P' image (indices 0..15) into 80x100 text cells (ch,attr) pairs (16000 bytes)."""
    if pimg.mode != "P":
        # allow RGB that matches CGA palette by quantizing quickly
        pimg = pimg.convert("P", palette=Image.ADAPTIVE, colors=16)
    w, h = pimg.size
    if (w, h) != (640, 200):
        raise ValueError("pack_text_80x100_char16 expects a 640x200 image")

    idx = list(pimg.getdata())
    out = bytearray(16000)

    # Iterate 80x100 cells (8x2 pixels each)
    k = 0
    for cy in range(100):
        y0 = cy * 2
        row0 = y0 * 640
        row1 = (y0 + 1) * 640
        for cx in range(80):
            x0 = cx * 8
            # gather 16 indices
            block = [
                idx[row0 + x0 + 0], idx[row0 + x0 + 1], idx[row0 + x0 + 2], idx[row0 + x0 + 3],
                idx[row0 + x0 + 4], idx[row0 + x0 + 5], idx[row0 + x0 + 6], idx[row0 + x0 + 7],
                idx[row1 + x0 + 0], idx[row1 + x0 + 1], idx[row1 + x0 + 2], idx[row1 + x0 + 3],
                idx[row1 + x0 + 4], idx[row1 + x0 + 5], idx[row1 + x0 + 6], idx[row1 + x0 + 7],
            ]

            # Determine bg/fg (most common = bg, next = fg)
            counts = {}
            for v in block:
                counts[v] = counts.get(v, 0) + 1
            items = sorted(counts.items(), key=lambda t: t[1], reverse=True)
            bg = items[0][0] & 0x0F
            fg = bg
            if len(items) > 1:
                fg = items[1][0] & 0x0F

            # Build 8-bit masks for the two scanlines (1=fg, 0=bg)
            m0 = 0
            m1 = 0
            if fg != bg:
                for dx in range(8):
                    if block[dx] == fg:
                        m0 |= (1 << (7 - dx))
                for dx in range(8):
                    if block[8 + dx] == fg:
                        m1 |= (1 << (7 - dx))

            # Find a character whose row0/row1 match these masks
            ch = _CGA_ROW01_TO_CHAR.get((m0, m1))
            if ch is None:
                # Best-effort: pick closest in Hamming space
                best = 0
                best_d = 1_000_000
                for cand, (r0, r1) in enumerate(_CGA_FONT_ROW01):
                    d = _hamming16(m0, m1, r0, r1)
                    if d < best_d:
                        best_d = d
                        best = cand
                        if d == 0:
                            break
                ch = best

            # Attribute: fg in low nibble, bg in high nibble with bright-bg in bit 7 (requires blink disabled)
            attr = (fg & 0x0F) | ((bg & 0x07) << 4) | ((bg & 0x08) << 4)

            out[k] = ch & 0xFF
            out[k + 1] = attr & 0xFF
            k += 2

    return bytes(out)

def build_com_cga_160x100x16(vram_text_16000: bytes) -> bytes:
    """Build a DOS .COM that enters CGA 160x100x16 mode and blits 16000 bytes to B800:0000."""
    if len(vram_text_16000) != 16000:
        raise ValueError("vram_text_16000 must be exactly 16000 bytes (80*100*2)")

    code = bytearray()

    # push cs ; pop ds
    code += bytes([0x0E, 0x1F])

    # BIOS mode 03h
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])

    # OUT 3D8h, AL=01h (video off, blink disabled, 80 col)
    code += bytes([0xBA, 0xD8, 0x03, 0xB0, 0x01, 0xEE])

    def out_crtc(idx: int, val: int):
        nonlocal code
        code += bytes([0xBA, 0xD4, 0x03])  # mov dx,3D4h
        code += bytes([0xB0, idx & 0xFF])  # mov al,idx
        code += bytes([0xEE])              # out dx,al
        code += bytes([0x42])              # inc dx ->3D5h
        code += bytes([0xB0, val & 0xFF])  # mov al,val
        code += bytes([0xEE])              # out dx,al

    # CRTC tweaks for 80x100 text with 2 scanlines/char
    out_crtc(0x04, 0x7F)  # Vertical total = 127
    out_crtc(0x06, 0x64)  # Vertical displayed = 100
    out_crtc(0x07, 0x70)  # Vertical sync position = 112
    out_crtc(0x09, 0x01)  # Max scanline = 1 (2 scanlines/char)

    # OUT 3D8h, AL=09h (video on, blink disabled, 80 col)
    code += bytes([0xBA, 0xD8, 0x03, 0xB0, 0x09, 0xEE])

    # mov ax,B800h ; mov es,ax
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])
    # xor di,di
    code += bytes([0x31, 0xFF])
    # mov si, imm16 (patched)
    si_patch_at = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])
    # mov cx,8000 ; rep movsw
    code += bytes([0xB9, 0x40, 0x1F, 0xF3, 0xA5])

    # wait for key (int16 ah=01)
    code += bytes([0xB4, 0x01, 0xCD, 0x16, 0x74, 0xFA])
    # consume key
    code += bytes([0xB4, 0x00, 0xCD, 0x16])

    # restore mode 03h
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    code += bytes([0xC3])

    data_off = 0x100 + len(code)
    code[si_patch_at] = data_off & 0xFF
    code[si_patch_at + 1] = (data_off >> 8) & 0xFF

    return bytes(code) + vram_text_16000




def build_com_text_80x100_char16(char_attr_16000: bytes) -> bytes:
    """Build a DOS .COM that displays an 80x100 text screen (16000 bytes: [ch,attr] pairs) using VGA text tweaks.

    Notes:
      - Sets video mode 03h (80x25 color), disables blink (enables bright background bit),
        then tweaks VGA CRTC to 2 scanlines/row and 100 rows.
      - Writes the 16000 bytes to B800:0000 (2 bytes per cell).
    """
    if len(char_attr_16000) != 16000:
        raise ValueError("build_com_text_80x100_char16 expects exactly 16000 bytes")

    code = bytearray()

    # Set text mode 03h
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])  # mov ax,0003 ; int 10h

    # Disable blink: INT 10h AX=1003h, BX=0000h
    code += bytes([0xB8, 0x03, 0x10, 0xBB, 0x00, 0x00, 0xCD, 0x10])

    # VGA CRTC tweaks for 80x100 (best-effort, works on VGA-class adapters / DOSBox-X with VGA):
    # Program 3D4/3D5: (index,value) pairs
    # - 09h: Maximum scan line = 1 (2 scanlines/row)
    # - 12h: Vertical display end = 63h (99 decimal => 100 rows)
    # - 15h: Vertical blank start (a little after display end)
    # - 16h: Vertical blank end
    # - 10h/11h: Vertical retrace start/end
    # - 06h: Vertical total
    # These values are intentionally conservative; different VGA BIOSes may vary.
    crtc_pairs = [
        (0x09, 0x01),
        (0x12, 0x63),
        (0x15, 0x66),
        (0x16, 0x70),
        (0x10, 0x67),
        (0x11, 0x8C),
        (0x06, 0xBF),
    ]

    # mov dx,3D4h
    code += bytes([0xBA, 0xD4, 0x03])
    for reg, val in crtc_pairs:
        code += bytes([0xB0, reg, 0xEE, 0x42, 0xB0, val, 0xEE, 0x4A])

    # Copy 16000 bytes to B800:0000
    # push cs; pop ds
    code += bytes([0x0E, 0x1F])
    # mov ax,0B800h; mov es,ax
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])
    # xor di,di
    code += bytes([0x31, 0xFF])
    # mov si, imm16 (patched)
    si_patch_at = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])
    # mov cx,8000 ; rep movsw
    code += bytes([0xB9, 0x40, 0x1F, 0xF3, 0xA5])

    # Wait for key (int16 ah=01)
    code += bytes([0xB4, 0x01, 0xCD, 0x16, 0x74, 0xFA])
    # Consume key
    code += bytes([0xB4, 0x00, 0xCD, 0x16])

    # Restore mode 03h (safe even if already)
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    code += bytes([0xC3])  # ret

    data_off = 0x100 + len(code)
    if data_off > 0x1FF0:
        raise ValueError("Program stub too large")
    code[si_patch_at] = data_off & 0xFF
    code[si_patch_at + 1] = (data_off >> 8) & 0xFF
    code += char_attr_16000
    return bytes(code)

def build_com_static_cga(mode_bios: int, vram16k: bytes, color_select_3d9: int = None, mode_control_3d8: int = None) -> bytes:
    """
    Build a DOS .COM that:
      - sets BIOS video mode (int 10h)
      - optionally OUT 3D9h,AL with color_select_3d9
      - optionally OUT 3D8h,AL with mode_control_3d8 (CGA mode control; e.g., enable composite colorburst)
      - copies 16KB to B800:0000
      - waits for keypress
      - restores text mode 03h and exits
    """
    if len(vram16k) != 16384:
        raise ValueError("vram16k must be exactly 16384 bytes.")

    code = bytearray()

    # push cs ; pop ds  (DS=CS so we can read appended data)
    code += bytes([0x0E, 0x1F])

    # mov ax, mode_bios ; int 10h
    code += bytes([0xB8, mode_bios & 0xFF, (mode_bios >> 8) & 0xFF, 0xCD, 0x10])

    if color_select_3d9 is not None:
        # mov dx, 03D9h
        code += bytes([0xBA, 0xD9, 0x03])
        # mov al, imm8
        code += bytes([0xB0, color_select_3d9 & 0xFF])
        # out dx, al
        code += bytes([0xEE])

    if mode_control_3d8 is not None:
        # mov dx, 03D8h
        code += bytes([0xBA, 0xD8, 0x03])
        # mov al, imm8
        code += bytes([0xB0, mode_control_3d8 & 0xFF])
        # out dx, al
        code += bytes([0xEE])

    # mov ax, B800h ; mov es, ax
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])
    # xor di, di
    code += bytes([0x31, 0xFF])
    # mov si, imm16  (patched later)
    si_patch_at = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])
    # mov cx, 8192 (words) ; rep movsw
    code += bytes([0xB9, 0x00, 0x20, 0xF3, 0xA5])

    # wait loop: ah=01 int16; jz wait
    code += bytes([0xB4, 0x01, 0xCD, 0x16, 0x74, 0xFA])  # jz -6 bytes back to mov ah,01

    # consume key: ah=00 int16
    code += bytes([0xB4, 0x00, 0xCD, 0x16])

    # restore text mode 03h: mov ax,0003 ; int 10h
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])

    # ret
    code += bytes([0xC3])

    # data offset in COM is 0x100 + len(code)
    data_off = 0x100 + len(code)
    code[si_patch_at] = data_off & 0xFF
    code[si_patch_at + 1] = (data_off >> 8) & 0xFF

    return bytes(code + vram16k)


def cga_color_select_for_320_palette_name(palette_name: str) -> int:
    """
    Map our palette dropdown name to the IBM CGA Color Select register (port 3D9h).

    Bits:
      - 0..3 : background color (0-15)
      - 4    : intensity (0 = low, 1 = high)
      - 5    : palette select (0 = R/G/Y family, 1 = C/M/W family)

    For "Tweaked" palettes (BIOS mode 05h), bit 5 is not meaningful; we leave it at 0.
    """
    # Palette family bit (bit 5)
    pal_sel_bit5 = 0  # default to R/G/Y family
    if palette_name.startswith("Cyan/Magenta/White"):
        pal_sel_bit5 = 1
    elif palette_name.startswith("Red/Green/Yellow"):
        pal_sel_bit5 = 0
    elif palette_name.startswith("Dark Red/Green/Brown"):
        pal_sel_bit5 = 0
    elif palette_name.startswith("Tweaked"):
        pal_sel_bit5 = 0
    else:
        pal_sel_bit5 = 0

    # Background nibble from '(bg=NAME)'
    bg_idx = 0
    m = re.search(r"\(bg=([^)]+)\)", palette_name)
    if m:
        bg_name = m.group(1).strip()
        if bg_name in CGA_COLOR_NAMES:
            bg_idx = CGA_COLOR_NAMES.index(bg_name)

    # Intensity bit (bit 4)
    pname_upper = palette_name.upper()
    if " LOW" in pname_upper:
        intensity_bit4 = 0
    elif " HIGH" in pname_upper:
        intensity_bit4 = 1
    elif palette_name.startswith("Dark Red/Green/Brown"):
        # Back-compat: this name implies low intensity.
        intensity_bit4 = 0
    else:
        # Default to high intensity (matches prior behavior for most palettes)
        intensity_bit4 = 1

    return (bg_idx & 0x0F) | ((intensity_bit4 & 1) << 4) | ((pal_sel_bit5 & 1) << 5)
def apply_diffusion_dither(image, palette, method_name, intensity=1.0, serpentine=True):
    """
    Diffusion dithering family.

    intensity: 0.0..1.0 scales the diffused error (0 => no diffusion, 1 => full diffusion).
    serpentine: if True, alternate scan direction each row and mirror the kernel.
    """
    intensity = 0.0 if intensity < 0.0 else 1.0 if intensity > 1.0 else float(intensity)

    # Kernels are defined for left-to-right scan.
    if method_name == "Horizontal Striped":
        kernel, divisor = _HSTRIPE_KERNEL, 1
    elif method_name == "Floyd-Steinberg":
        kernel, divisor = _FS_KERNEL, 16
    elif method_name == "Atkinson":
        kernel, divisor = _ATKINSON_KERNEL, 8
    elif method_name == "Jarvis-Judice-Ninke":
        kernel, divisor = _JJN_KERNEL, 48
    elif method_name == "Stucki":
        kernel, divisor = _STUCKI_KERNEL, 42
    elif method_name == "Burkes":
        kernel, divisor = _BURKES_KERNEL, 32
    elif method_name == "Sierra":
        kernel, divisor = _SIERRA_KERNEL, 32
    elif method_name == "Sierra-2":
        kernel, divisor = _SIERRA2_KERNEL, 16
    elif method_name == "Sierra Lite":
        kernel, divisor = _SIERRA_LITE_KERNEL, 4
    else:
        indices = no_dither(image, palette)
        return indices_to_pimage(indices, palette, image.size)

    indices = _error_diffusion_dither(image, palette, kernel, divisor, intensity=intensity, serpentine=serpentine)
    return indices_to_pimage(indices, palette, image.size)


def apply_ordered_dither(image, palette, matrix_size=4, strength=1.0):
    """
    Ordered dithering family (Bayer-style threshold matrices).

    matrix_size: 2..16
    strength: 0.0..1.0
    """
    strength = 0.0 if strength < 0.0 else 3.0 if strength > 3.0 else float(strength)
    indices = ordered_dither(image, palette, matrix_size=matrix_size, strength=strength)
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
        sum_abs_err = 0.0
        sum_abs_to_next = 0.0
        max_abs_to_next = 0.0
        for x in range(w):
            r, g, b = pixels[x, y]
            gval = 0.299 * r + 0.587 * g + 0.114 * b
            gray[y * w + x] = gval

    grad = [0.0] * (w * h)
    for y in range(h):
        sum_abs_err = 0.0
        sum_abs_to_next = 0.0
        max_abs_to_next = 0.0
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


def tone_image_to_palette_debug(image, palette):
    """
    Match contrast/tone of the *input* image to the *target 4-color palette*.

    v76+: channel-wise matching (per RGB channel), as requested.
      - Compute source black/white per channel from robust percentiles (1% / 99%).
      - Compute target black/white per channel from palette min/max (per channel).
      - Apply an affine remap per channel:
            out = (in - src_black) * (pal_white - pal_black) / (src_white - src_black) + pal_black
        with clipping to [0, 255].

    Returns: (toned_image_rgb, debug_dict)
    """
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)

    pal = np.asarray([tuple(rgb) for rgb in palette], dtype=np.float32)
    pal_min = pal.min(axis=0)  # (3,)
    pal_max = pal.max(axis=0)  # (3,)

    src_black = np.percentile(arr, 1.0, axis=(0, 1)).astype(np.float32)
    src_white = np.percentile(arr, 99.0, axis=(0, 1)).astype(np.float32)

    # Avoid divide-by-zero if the input channel is nearly flat
    denom = np.maximum(src_white - src_black, 1e-6)
    contrast_scale = (pal_max - pal_min) / denom
    brightness_offset = pal_min - (src_black * contrast_scale)

    out = arr * contrast_scale[None, None, :] + brightness_offset[None, None, :]
    out = np.clip(out, 0.0, 255.0).astype(np.uint8)
    img_out = Image.fromarray(out, mode="RGB")

    dbg = {
        "src_black_rgb": tuple(float(x) for x in src_black),
        "src_white_rgb": tuple(float(x) for x in src_white),
        "pal_black_rgb": tuple(float(x) for x in pal_min),
        "pal_white_rgb": tuple(float(x) for x in pal_max),
        "contrast_scale_rgb": tuple(float(x) for x in contrast_scale),
        "brightness_offset_rgb": tuple(float(x) for x in brightness_offset),
    }
    return img_out, dbg


def tone_image_to_palette(image, palette):
    """Back-compat wrapper (returns only the toned image)."""
    out, _dbg = tone_image_to_palette_debug(image, palette)
    return out




# --- 640x200 "text-row" (char 16-color) quantisation -------------------------

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
    """Return the parsed 256x8 CGA ROM font masks."""
    return _CGA_FONT

def quantize_char16_textblock_from_indices(pre_indices, subsample=False):
    """
    Map a 640x200 *already CGA-16-quantized* image (given as palette indices 0..15)
    into the constrained "text-block" mode:

      - Output is 640x200
      - Screen is 80x100 cells, each 8x2 pixels
      - Per cell choose:
          * FG color index 0..15
          * BG color index 0..15
          * Character code 0..255
        but the bit patterns are constrained to the FIRST TWO scanlines of that
        character in the CGA ROM font (row 0 and row 1).

    When subsample=True, the match is scored using 2x2 sub-samples inside each 8x2 cell:
      - Each 8x2 cell becomes four 2x2 groups: x=[0..1],[2..3],[4..5],[6..7] across both rows.
      - We compare average RGB of each 2x2 group against the candidate output's 2x2 group averages.
      - This effectively scores the block as if the input were 320x100, balancing color match vs detail.

    Returns a 'P' image with the CGA 16-colour palette.
    """
    w, h = 640, 200
    if len(pre_indices) != w * h:
        raise ValueError("quantize_char16_textblock_from_indices expects 640x200 indices")

    num_cols = 80
    num_rows = 100
    cell_w = 8
    cell_h = 2

    out = [0] * (w * h)

    # local refs for speed
    row01 = _CGA_FONT_ROW01

    # small reusable counts
    counts = [0] * 16

    # --- Optional: precompute FG counts per 2x2 group for each character code ---
    # fgcount[code][g] where g in 0..3 corresponds to x=[2g,2g+1] across both rows (4 pixels total)
    global _CHAR16_FGCOUNT_2X2
    try:
        _CHAR16_FGCOUNT_2X2  # type: ignore[name-defined]
    except Exception:
        _CHAR16_FGCOUNT_2X2 = None

    if subsample and _CHAR16_FGCOUNT_2X2 is None:
        fgcount = [[0, 0, 0, 0] for _ in range(256)]
        for code in range(256):
            m0, m1 = row01[code]
            for g in range(4):
                dx0 = 2 * g
                # count set bits at dx0 and dx0+1 for both rows
                c = 0
                c += (m0 >> (7 - dx0)) & 1
                c += (m0 >> (7 - (dx0 + 1))) & 1
                c += (m1 >> (7 - dx0)) & 1
                c += (m1 >> (7 - (dx0 + 1))) & 1
                fgcount[code][g] = c
        _CHAR16_FGCOUNT_2X2 = fgcount

    # Precompute 16x16 squared-distance matrix between CGA palette colours (index space)
    # Used by the non-subsample matcher.
    dist = None
    if not subsample:
        dist = [[0] * 16 for _ in range(16)]
        for a in range(16):
            ar, ag, ab = CGA_16COLOR_PALETTE[a]
            for b in range(16):
                br, bg, bb = CGA_16COLOR_PALETTE[b]
                dr = ar - br
                dg = ag - bg
                db = ab - bb
                dist[a][b] = dr * dr + dg * dg + db * db

    # Pre-bake palette RGB arrays for subsample scoring
    pal_r = [c[0] for c in CGA_16COLOR_PALETTE]
    pal_g = [c[1] for c in CGA_16COLOR_PALETTE]
    pal_b = [c[2] for c in CGA_16COLOR_PALETTE]

    for row in range(num_rows):
        y0 = row * cell_h
        for col in range(num_cols):
            x0 = col * cell_w

            # Gather the 16 target indices for this 8x2 block
            # and find two most frequent colours as FG/BG candidates.
            for i in range(16):
                counts[i] = 0

            block = [0] * 16
            k = 0
            for dy in range(cell_h):
                base = (y0 + dy) * w + x0
                for dx in range(cell_w):
                    idx = pre_indices[base + dx]
                    block[k] = idx
                    k += 1
                    counts[idx] += 1

            # Choose top-2 colours by frequency
            order = sorted(range(16), key=lambda i: counts[i], reverse=True)
            fg_idx = order[0]
            bg_idx = order[1] if counts[order[1]] > 0 else fg_idx
            if fg_idx == bg_idx:
                bg_idx = 0 if fg_idx != 0 else 7

            best_code = 0
            best_err = float("inf")

            if not subsample:
                # --- Original pixel-level scoring ---
                for code in range(256):
                    m0, m1 = row01[code]
                    err = 0

                    # Row 0 (dy=0): block[0..7]
                    for dx in range(8):
                        bit = (m0 >> (7 - dx)) & 1
                        chosen = fg_idx if bit else bg_idx
                        err += dist[block[dx]][chosen]

                    # Row 1 (dy=1): block[8..15]
                    for dx in range(8):
                        bit = (m1 >> (7 - dx)) & 1
                        chosen = fg_idx if bit else bg_idx
                        err += dist[block[8 + dx]][chosen]

                    if err < best_err:
                        best_err = err
                        best_code = code
                        if best_err == 0:
                            break
            else:
                # --- Sub-sampled (2x2 group average) scoring ---
                # Input group averages (4 groups, each averages 4 pixels)
                # groups: g0 uses block dx=[0,1] from both rows, etc.
                in_r = [0.0, 0.0, 0.0, 0.0]
                in_g = [0.0, 0.0, 0.0, 0.0]
                in_b = [0.0, 0.0, 0.0, 0.0]
                for g in range(4):
                    dx0 = 2 * g
                    # indices in block: row0 at dx0,dx0+1 => block[dx0], block[dx0+1]
                    # row1 at dx0,dx0+1 => block[8+dx0], block[8+dx0+1]
                    i0 = block[dx0]
                    i1 = block[dx0 + 1]
                    i2 = block[8 + dx0]
                    i3 = block[8 + dx0 + 1]
                    sr = pal_r[i0] + pal_r[i1] + pal_r[i2] + pal_r[i3]
                    sg = pal_g[i0] + pal_g[i1] + pal_g[i2] + pal_g[i3]
                    sb = pal_b[i0] + pal_b[i1] + pal_b[i2] + pal_b[i3]
                    in_r[g] = sr * 0.25
                    in_g[g] = sg * 0.25
                    in_b[g] = sb * 0.25

                fr, fg, fb = pal_r[fg_idx], pal_g[fg_idx], pal_b[fg_idx]
                br, bg, bb = pal_r[bg_idx], pal_g[bg_idx], pal_b[bg_idx]
                fgcount = _CHAR16_FGCOUNT_2X2

                for code in range(256):
                    err = 0.0
                    gc = fgcount[code]
                    # Each group average is linear mix of fg/bg based on fg pixel count (0..4)
                    for g in range(4):
                        c = gc[g]
                        inv = 4 - c
                        cr = (c * fr + inv * br) * 0.25
                        cg = (c * fg + inv * bg) * 0.25
                        cb = (c * fb + inv * bb) * 0.25
                        dr = in_r[g] - cr
                        dg = in_g[g] - cg
                        db = in_b[g] - cb
                        err += dr * dr + dg * dg + db * db
                    if err < best_err:
                        best_err = err
                        best_code = code
                        if best_err == 0.0:
                            break

            # Emit pixels for chosen glyph slice
            m0, m1 = row01[best_code]

            base0 = y0 * w + x0
            base1 = (y0 + 1) * w + x0
            for dx in range(8):
                out[base0 + dx] = fg_idx if ((m0 >> (7 - dx)) & 1) else bg_idx
            for dx in range(8):
                out[base1 + dx] = fg_idx if ((m1 >> (7 - dx)) & 1) else bg_idx

    return indices_to_pimage(out, CGA_16COLOR_PALETTE, (w, h))



# --- 80x100 HiColor (8x2 block) mode -----------------------------------------

def _build_representative_2x8_masks():
    """
    From the CGA font, pick a representative 2x8 (two scanlines) mask for each
    fill level k=0..16, based on rows 0 and 1 of each character.

    Returns dict: k -> (row0_byte, row1_byte, bits16_list[16], ones_count)
    """
    # CGA_FONT: [256][8] bytes
    masks_by_k = {k: [] for k in range(17)}

    def clumpiness(bits16):
        # Lower is better (more even). Simple adjacency sum.
        s = 0
        for i in range(15):
            s += 1 if bits16[i] == bits16[i+1] else 0
        # Also weight vertical adjacency between the two rows
        for x in range(8):
            s += 1 if bits16[x] == bits16[8+x] else 0
        return s

    for code in range(256):
        r0 = _CGA_FONT[code][0]
        r1 = _CGA_FONT[code][1]
        bits = []
        ones = 0
        for x in range(8):
            b = (r0 >> (7 - x)) & 1
            bits.append(bool(b))
            ones += b
        for x in range(8):
            b = (r1 >> (7 - x)) & 1
            bits.append(bool(b))
            ones += b
        masks_by_k[ones].append((clumpiness(bits), r0, r1, bits))

    rep = {}
    for k in range(17):
        if not masks_by_k[k]:
            # Fallback: all 0 or all 1
            if k == 0:
                r0 = r1 = 0x00
            elif k == 16:
                r0 = r1 = 0xFF
            else:
                # simple left-filled
                fill = (1 << k) - 1
                r0 = ((fill & 0xFF) << max(0, 8 - min(8, k))) & 0xFF
                r1 = r0
            bits = []
            for x in range(8):
                bits.append(bool((r0 >> (7 - x)) & 1))
            for x in range(8):
                bits.append(bool((r1 >> (7 - x)) & 1))
            rep[k] = (r0, r1, bits, k)
            continue

        masks_by_k[k].sort(key=lambda t: t[0])
        _, r0, r1, bits = masks_by_k[k][0]
        rep[k] = (r0, r1, bits, k)
    return rep


_REP_2X8_MASKS = None


def _ensure_rep_2x8_masks():
    global _REP_2X8_MASKS
    if _REP_2X8_MASKS is None:
        _REP_2X8_MASKS = _build_representative_2x8_masks()
    return _REP_2X8_MASKS


def _compute_block_averages_80x100(image_640x200_rgb):
    """Return an 80x100 RGB image where each pixel is the average of the corresponding 8x2 block."""
    w, h = image_640x200_rgb.size
    if (w, h) != (640, 200):
        raise ValueError("Expected 640x200 image")

    src = image_640x200_rgb.load()
    eff = Image.new("RGB", (80, 100))
    dst = eff.load()

    for by in range(100):
        y0 = by * 2
        for bx in range(80):
            x0 = bx * 8
            rs = gs = bs = 0
            for dy in range(2):
                for dx in range(8):
                    r, g, b = src[x0 + dx, y0 + dy]
                    rs += r; gs += g; bs += b
            dst[bx, by] = (rs // 16, gs // 16, bs // 16)
    return eff


def _precompute_mix_palette():
    """
    Precompute all (fg,bg,k) average RGB colors, for fast nearest search.
    Returns:
      avg_rgb: float32 array (N,3)
      meta: int16 array (N,3) -> fg_idx, bg_idx, k
    """
    entries = []
    meta = []
    for fg in range(16):
        fr, fg_g, fb = CGA_COLORS[fg]
        for bg in range(16):
            br, bg_g, bb = CGA_COLORS[bg]
            for k in range(17):
                a = k / 16.0
                r = br + (fr - br) * a
                g = bg_g + (fg_g - bg_g) * a
                b = bb + (fb - bb) * a
                entries.append((r, g, b))
                meta.append((fg, bg, k))
    avg_rgb = np.array(entries, dtype=np.float32)
    meta = np.array(meta, dtype=np.int16)
    return avg_rgb, meta


_MIX_AVG_RGB = None
_MIX_META = None


def _ensure_mix_palette():
    global _MIX_AVG_RGB, _MIX_META
    if _MIX_AVG_RGB is None or _MIX_META is None:
        _MIX_AVG_RGB, _MIX_META = _precompute_mix_palette()
    return _MIX_AVG_RGB, _MIX_META


def quantize_80x100_hicolor(image_80x100_rgb, dither_family="Error diffusion", diffusion_name="Floyd-Steinberg", intensity=1.0, ordered_size=4, ordered_strength=24.0, limit_chars=False):
    """
    HiColor mode:
      1) Input is already scaled to 80x100 (effective cell image).
      2) Dither in 80x100 space by selecting (fg,bg,fill-level k) whose AVERAGE best matches.
      3) Expand to 640x200 using a representative 2x8 mask for that fill level.

    Returns:
      (output_pimg_640x200, effective_img_80x100)
    """
    intensity = float(intensity)
    if intensity < 0.0: intensity = 0.0
    if intensity > 1.0: intensity = 1.0

    effective = image_80x100_rgb.copy()  # already scaled to 80x100
    eff_px = effective.load()
    W, H = 80, 100

    # Choose diffusion kernel
    kernels = {
        "Floyd-Steinberg": [ (1,0,7/16), (-1,1,3/16), (0,1,5/16), (1,1,1/16) ],
        "Atkinson": [ (1,0,1/8), (2,0,1/8), (-1,1,1/8), (0,1,1/8), (1,1,1/8), (0,2,1/8) ],
        "Jarvis-Judice-Ninke": [ (1,0,7/48), (2,0,5/48),
                                 (-2,1,3/48), (-1,1,5/48), (0,1,7/48), (1,1,5/48), (2,1,3/48),
                                 (-2,2,1/48), (-1,2,3/48), (0,2,5/48), (1,2,3/48), (2,2,1/48) ],
        "Stucki": [ (1,0,8/42), (2,0,4/42),
                    (-2,1,2/42), (-1,1,4/42), (0,1,8/42), (1,1,4/42), (2,1,2/42),
                    (-2,2,1/42), (-1,2,2/42), (0,2,4/42), (1,2,2/42), (2,2,1/42) ],
        "Burkes": [ (1,0,8/32), (2,0,4/32),
                    (-2,1,2/32), (-1,1,4/32), (0,1,8/32), (1,1,4/32), (2,1,2/32) ],
        "Sierra": [ (1,0,5/32), (2,0,3/32),
                    (-2,1,2/32), (-1,1,4/32), (0,1,5/32), (1,1,4/32), (2,1,2/32),
                    (-1,2,2/32), (0,2,3/32), (1,2,2/32) ],
        "Sierra-2": [ (1,0,4/16), (2,0,3/16),
                      (-2,1,1/16), (-1,1,2/16), (0,1,3/16), (1,1,2/16), (2,1,1/16) ],
        "Sierra Lite": [ (1,0,2/4), (-1,1,1/4), (0,1,1/4) ],
    }
    kernel = kernels.get(diffusion_name, kernels["Floyd-Steinberg"])

    # Working buffer of floats
    buf = np.zeros((H, W, 3), dtype=np.float32)
    for y in range(H):
        for x in range(W):
            buf[y, x] = eff_px[x, y]

    mix_avg, mix_meta = _ensure_mix_palette()
    reps = _ensure_rep_2x8_masks()

    # Ordered dithering setup (for HiColor): apply ordered RGB nudge in 80x100 cell space.
    ord_n = int(ordered_size) if ordered_size else 4
    if ord_n < 2: ord_n = 2
    if ord_n > 16: ord_n = 16
    ord_strength = float(ordered_strength)
    if ord_strength < 0.0: ord_strength = 0.0
    if ord_strength > 3.0: ord_strength = 3.0

    if dither_family == "Ordered" and ord_strength > 0.0:
        ord_matrix = get_ordered_matrix(ord_n)
        ord_den = float(ord_n * ord_n)
        base = 32.0  # matches the scale used in other ordered modes
        for yy in range(H):
            for xx in range(W):
                t = ord_matrix[yy % ord_n][xx % ord_n] / ord_den  # 0..1
                off = (t - 0.5) * base * ord_strength
                buf[yy, xx, 0] = min(255.0, max(0.0, buf[yy, xx, 0] + off))
                buf[yy, xx, 1] = min(255.0, max(0.0, buf[yy, xx, 1] + off))
                buf[yy, xx, 2] = min(255.0, max(0.0, buf[yy, xx, 2] + off))
        # After pre-nudging, proceed with normal nearest-choice selection.

    if limit_chars:
        # Restrict to a small, uniform-looking subset of fill levels.
        # This corresponds to empty, light shade (~25%), medium (~50%), dark (~75%), and solid.
        allowed_ks = np.array([0, 4, 8, 12, 16], dtype=np.int16)
        keep = np.isin(mix_meta[:, 2], allowed_ks)
        mix_avg = mix_avg[keep]
        mix_meta = mix_meta[keep]

    # Post-decision 80x100 effective preview (shows chosen average colour per cell)
    effective_after = Image.new("RGB", (W, H))
    eff_after_px = effective_after.load()


    # Output indices for 640x200
    out_indices = [0] * (640 * 200)

    for y in range(H):
        for x in range(W):
            desired = buf[y, x]  # float RGB
            # nearest in average-mix space
            d = mix_avg - desired
            dist = (d * d).sum(axis=1)
            j = int(dist.argmin())

            fg_idx, bg_idx, k = map(int, mix_meta[j])
            r0, r1, bits16, _ = reps[k]

            # Compute chosen average (in mix palette space)
            chosen_avg = mix_avg[j]

            # record the chosen average for the effective 80x100 preview
            eff_after_px[x, y] = (
                int(clamp(float(chosen_avg[0]))),
                int(clamp(float(chosen_avg[1]))),
                int(clamp(float(chosen_avg[2]))),
            )

            # Error diffusion: push residual to neighbors (scaled by intensity)
            if dither_family in ("Error diffusion", "Diffusion"):
                err = (desired - chosen_avg) * intensity

                # diffuse to neighbors
                if intensity > 0.0:
                    for dx, dy, wgt in kernel:
                        xx = x + dx
                        yy = y + dy
                        if 0 <= xx < W and 0 <= yy < H:
                            buf[yy, xx] += err * wgt

            # write 8x2 pixels
            x0 = x * 8
            y0 = y * 2
            # row0
            for px in range(8):
                idx = fg_idx if bits16[px] else bg_idx
                out_indices[(y0) * 640 + (x0 + px)] = idx
            # row1
            for px in range(8):
                idx = fg_idx if bits16[8 + px] else bg_idx
                out_indices[(y0 + 1) * 640 + (x0 + px)] = idx

    out_p = indices_to_pimage(out_indices, CGA_16COLOR_PALETTE, (640, 200))
    return out_p, effective_after


# --- Image resizing helpers --------------------------------------------------


def get_resample_filter(name: str):
    """Return a Pillow resampling enum for simple filters.

    NOTE: Some entries in the UI are *pipelines* (eg. Gaussian prefilter) and are
    handled inside resize_with_mode().
    """
    R = getattr(Image, "Resampling", Image)

    name = (name or "").strip()

    if name in ("Nearest", "Nearest neighbor"):
        return R.NEAREST
    if name == "Bilinear":
        return R.BILINEAR
    if name == "Bicubic":
        return R.BICUBIC
    if name == "Lanczos":
        return R.LANCZOS
    if name in ("Box", "Box (Area)", "Area"):
        return R.BOX
    if name == "Hamming":
        return R.HAMMING

    # Back-compat with older saved settings
    if name == "Nearest":
        return R.NEAREST

    # Default
    return R.LANCZOS



def resize_with_mode(image, target_w, target_h, scale_mode, resample_name):
    """
    scale_mode:
      - "Fit (letterbox)" => preserve aspect, black bars
      - "Fill (crop)"     => preserve aspect, crop overflows
      - "Stretch"         => ignore aspect
    """
    resample = get_resample_filter(filter_name if filter_name else resample_name)
    src_w, src_h = image.size

    # Extended scaling filters / pipelines
    filter_name = (resample_name or "").strip()

    def _do_resize(img, size, base_resample):
        """Resize helper that supports pipeline filters beyond a single resampler."""
        tw, th = size
        # --- xBRZ (pixel-art upscaler) ---
        # Only meaningful for *upscaling* by an integer factor. If unavailable or not applicable,
        # we fall back to the base resampler.
        if filter_name.startswith("xBRZ"):
            try:
                import xbrz  # external; user must install (see notes in README / docs)
            except Exception:
                return img.resize((tw, th), resample=base_resample)

            # Attempt to compute a clean integer upscale factor
            sx = tw / max(1, img.size[0])
            sy = th / max(1, img.size[1])
            s = int(round(min(sx, sy)))
            if s < 2:
                return img.resize((tw, th), resample=base_resample)

            # xbrz expects RGBA bytes typically; keep it simple
            rgba = img.convert("RGBA")
            out_rgba = xbrz.scale(rgba, s)  # library-specific API; may vary
            out = out_rgba.convert("RGB")
            if out.size != (tw, th):
                out = out.resize((tw, th), resample=base_resample)
            return out

        # --- Multi-pass downscale (Box) ---
        if filter_name == "Multi-pass Box (downscale)":
            # Progressively halve using BOX to reduce aliasing, then final resize.
            cur = img
            cw, ch = cur.size
            # only helps when downscaling
            while cw // 2 >= tw and ch // 2 >= th and cw > 1 and ch > 1:
                cw = max(tw, cw // 2)
                ch = max(th, ch // 2)
                cur = cur.resize((cw, ch), resample=getattr(Image, "Resampling", Image).BOX)
            return cur.resize((tw, th), resample=base_resample)

        # --- Gaussian prefilter for downscale ---
        if filter_name == "Gaussian (prefilter) + Lanczos":
            cur = img
            cw, ch = cur.size
            if tw < cw or th < ch:
                # radius proportional to reduction
                rx = max(0.0, (cw / max(1, tw) - 1.0) * 0.6)
                ry = max(0.0, (ch / max(1, th) - 1.0) * 0.6)
                radius = max(rx, ry)
                if radius > 0.01:
                    cur = cur.filter(ImageFilter.GaussianBlur(radius))
            return cur.resize((tw, th), resample=base_resample)

        # --- Unsharp after resize ---
        if filter_name == "Lanczos + Unsharp":
            out = img.resize((tw, th), resample=base_resample)
            return out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3))

        # Default: single-step resize
        return img.resize((tw, th), resample=base_resample)


    if scale_mode == "Stretch":
        return _do_resize(image, (target_w, target_h), resample)

    src_aspect = src_w / src_h
    dst_aspect = target_w / target_h

    if scale_mode == "Fit (letterbox)":
        if src_aspect > dst_aspect:
            new_w = target_w
            new_h = int(round(target_w / src_aspect))
        else:
            new_h = target_h
            new_w = int(round(target_h * src_aspect))
        resized = _do_resize(image, (new_w, new_h), resample)
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
        resized = _do_resize(image, (new_w, new_h), resample)
        x0 = (new_w - target_w) // 2
        y0 = (new_h - target_h) // 2
        return resized.crop((x0, y0, x0 + target_w, y0 + target_h))

    return _do_resize(image, (target_w, target_h), resample)


# --- GUI Application ---------------------------------------------------------




def quantize_320x200_mode_switch(
    image_rgb_320x200,
    forced_bg_idx=None,
    dither_family="Diffusion",
    diffusion_name="Floyd-Steinberg",
    diffusion_intensity=1.0,
    serpentine=True,
    ordered_matrix_size=4,
    ordered_strength=1.0,
    segments_per_line=1,
    progress_cb=None,
    debug=DEBUG_MODE_SWITCH,
    return_palettes=False,
):
    """
    320x200 Mode Switch:
      - Choose a 4-color CGA palette PER SCANLINE.
      - Render the scanline left-to-right (optionally serpentine) using that palette.
      - Error diffusion propagates from the *working/original* pixel value (work[y][x]) into future pixels,
        including the pixel(s) below, so palette choice for the next scanline can be influenced.
    """

    # --- Debug files ---
    dbg_f = None
    dbg_path = None
    if debug:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dbg_path = os.path.join(os.path.dirname(__file__), f'mode_switch_debug_{ts}.txt')
        dbg_f = open(dbg_path, 'w', encoding='utf-8')
        dbg_f.write('y\tpal_idx\tbest_err\trow_mean_rgb\trow_mean_luma\n')
        dbg_f.flush()

    diff_f = None
    diff_path = None
    if DEBUG_PROPAGATION_SUMMARY or DEBUG_PROPAGATION_DETAILS:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        diff_path = os.path.join(os.path.dirname(__file__), f'mode_switch_diffusion_{ts}.txt')
        diff_f = open(diff_path, 'w', encoding='utf-8')
        diff_f.write('y\tsum_abs_err\tsum_abs_to_next\tmax_abs_to_next\n')
        diff_f.write(f"params\tdither_family={dither_family}\tdiffusion_name={diffusion_name}\tdiffusion_intensity={diffusion_intensity}\tserpentine={serpentine}\tordered_n={ordered_matrix_size}\tordered_strength={ordered_strength}\n")
        diff_f.flush()

    # --- Prepare working buffer ---
    img = image_rgb_320x200.convert("RGB")
    W, H = img.size
    if W != 320 or H != 200:
        img = img.resize((320, 200), Image.LANCZOS)
        W, H = img.size

    # work[y][x] = [r,g,b] floats (mutable)
    pix = img.load()
    work = [[[float(pix[x, y][0]), float(pix[x, y][1]), float(pix[x, y][2])] for x in range(W)] for y in range(H)]

    # candidates: list of palettes, each palette is list of 4 (r,g,b)
    candidates = list(CGA_4COLOR_PALETTES.values()) if isinstance(CGA_4COLOR_PALETTES, dict) else list(CGA_4COLOR_PALETTES)
    if not candidates:
        candidates = [ [(0,0,0),(85,85,85),(170,170,170),(255,255,255)] ]

    chosen_palettes = [None] * H  # store 4-color palette per scanline (for diagnostics)

    # Optional: force background color (palette[0]) for all scanlines
    if forced_bg_idx is not None:
        try:
            bg_rgb = CGA_COLORS[int(forced_bg_idx)]
            filtered = [p for p in candidates if tuple(p[0]) == tuple(bg_rgb)]
            if filtered:
                candidates = filtered
        except Exception:
            pass


    # Ordered dithering: pre-apply offsets to the WORK buffer (so palette selection sees it)
    ord_n = int(ordered_matrix_size)
    if ord_n < 2: ord_n = 2
    if ord_n > 16: ord_n = 16
    ord_strength = float(ordered_strength)
    if ord_strength < 0.0: ord_strength = 0.0
    if ord_strength > 3.0: ord_strength = 3.0

    if dither_family == "Ordered" and ord_strength > 0.0:
        ord_matrix = get_ordered_matrix(ord_n)
        ord_den = float(ord_n * ord_n)
        base = 32.0  # consistent with other ordered modes in this tool
        for yy in range(H):
            row = work[yy]
            for xx in range(W):
                t = ord_matrix[yy % ord_n][xx % ord_n] / ord_den  # 0..1
                off = (t - 0.5) * base * ord_strength
                r, g, b = row[xx]
                row[xx][0] = min(255.0, max(0.0, r + off))
                row[xx][1] = min(255.0, max(0.0, g + off))
                row[xx][2] = min(255.0, max(0.0, b + off))

    # Diffusion kernels (dx, dy, weight). dy>=0 only; serpentine will mirror dx for odd rows.
    KERNELS = {
        "Horizontal Striped": [(0, 1, 1.0)],
        "Floyd-Steinberg": [(1, 0, 7/16), (-1, 1, 3/16), (0, 1, 5/16), (1, 1, 1/16)],
        "Jarvis-Judice-Ninke": [(1,0,7/48),(2,0,5/48),
                               (-2,1,3/48),(-1,1,5/48),(0,1,7/48),(1,1,5/48),(2,1,3/48),
                               (-2,2,1/48),(-1,2,3/48),(0,2,5/48),(1,2,3/48),(2,2,1/48)],
        "Stucki": [(1,0,8/42),(2,0,4/42),
                   (-2,1,2/42),(-1,1,4/42),(0,1,8/42),(1,1,4/42),(2,1,2/42),
                   (-2,2,1/42),(-1,2,2/42),(0,2,4/42),(1,2,2/42),(2,2,1/42)],
        "Burkes": [(1,0,8/32),(2,0,4/32),
                   (-2,1,2/32),(-1,1,4/32),(0,1,8/32),(1,1,4/32),(2,1,2/32)],
        "Sierra": [(1,0,5/32),(2,0,3/32),
                   (-2,1,2/32),(-1,1,4/32),(0,1,5/32),(1,1,4/32),(2,1,2/32),
                   (-1,2,2/32),(0,2,3/32),(1,2,2/32)],
        "Two-Row Sierra": [(1,0,4/16),(2,0,3/16),
                           (-2,1,1/16),(-1,1,2/16),(0,1,3/16),(1,1,2/16),(2,1,1/16)],
        "Sierra Lite": [(1,0,2/4), (-1,1,1/4), (0,1,1/4)],
        "Atkinson": [(1,0,1/8),(2,0,1/8),(-1,1,1/8),(0,1,1/8),(1,1,1/8),(0,2,1/8)],
    }

    # intensity
    intensity = float(diffusion_intensity)
    if intensity < 0.0: intensity = 0.0
    # allow higher? but mode switch uses 0..1 generally; keep unclamped if user wants, but protect extreme
    if intensity > 3.0: intensity = 3.0

    kernel = KERNELS.get(diffusion_name, KERNELS["Floyd-Steinberg"])

    # Output pixels
    out_pixels = [(0, 0, 0)] * (W * H)

    def nearest_index(old_rgb, pal4):
        # old_rgb: [r,g,b] floats
        r, g, b = old_rgb
        best_i = 0
        br = r - pal4[0][0]; bg = g - pal4[0][1]; bb = b - pal4[0][2]
        best = br*br + bg*bg + bb*bb
        for i in (1, 2, 3):
            pr, pg, pb = pal4[i]
            dr = r - pr; dg = g - pg; db = b - pb
            d = dr*dr + dg*dg + db*db
            if d < best:
                best = d
                best_i = i
        return best_i, best

    for y in range(H):
        zero_err_count = 0
        sample_lines = []
        sample_limit = 16  # pixels
        if progress_cb is not None and (y % 8) == 0:
            try:
                progress_cb(y / float(H))
            except Exception:
                pass

        # --- PASS 1: choose palette(s) for this scanline based on CURRENT work[y] ---
        # We allow up to 6 mode switches per scanline => up to 7 palette segments.
        seg_n = int(max(1, min(6, int(segments_per_line))))
        seg_w = W // seg_n if seg_n > 0 else W
        seg_pals = [candidates[0]] * seg_n
        seg_idxs = [0] * seg_n
        seg_errs = [0.0] * seg_n

        row = work[y]

        for si in range(seg_n):
            x0 = si * seg_w
            x1 = (si + 1) * seg_w if si < (seg_n - 1) else W

            best_err = float("inf")
            best_pal = candidates[0]
            best_pal_idx = 0

            for p_i, pal in enumerate(candidates):
                err = 0.0
                for x in range(x0, x1):
                    _, d = nearest_index(row[x], pal)
                    err += d
                    if err >= best_err:
                        break
                if err < best_err:
                    best_err = err
                    best_pal = pal
                    best_pal_idx = p_i

            seg_pals[si] = best_pal
            seg_idxs[si] = best_pal_idx
            seg_errs[si] = best_err

        chosen_palettes[y] = (seg_pals[0] if seg_n == 1 else seg_pals)


        # debug palette stats for this scanline
        if dbg_f is not None:
            rr = gg = bb = 0.0
            for x in range(W):
                r, g, b = row[x]
                rr += r; gg += g; bb += b
            rr /= W; gg /= W; bb /= W
            luma = 0.2126 * rr + 0.7152 * gg + 0.0722 * bb
            dbg_f.write(f"{y}\t" + ",".join(str(i) for i in seg_idxs) + f"\t{sum(seg_errs):.2f}\t{rr:.1f},{gg:.1f},{bb:.1f}\t{luma:.1f}\n")
            if (y % 8) == 0:
                dbg_f.flush()

        # --- PASS 2: render scanline and diffuse error forward (only if Diffusion family & intensity>0) ---
        sum_abs_err = 0.0
        sum_abs_to_next = 0.0
        max_abs_to_next = 0.0

        if serpentine and (y % 2 == 1):
            xs = range(W - 1, -1, -1)
            k_use = [(-dx, dy, w) for (dx, dy, w) in kernel]  # mirror horizontal terms
        else:
            xs = range(W)
            k_use = kernel

        for x in xs:
            old = row[x]  # [r,g,b] float, includes propagated error
            si = min(seg_n - 1, (x // seg_w) if seg_w > 0 else 0)
            pal_use = seg_pals[si]
            idx, _ = nearest_index(old, pal_use)
            new = pal_use[idx]
            out_pixels[y * W + x] = new

            if dither_family == "Diffusion" and intensity > 0.0:
                er = old[0] - new[0]
                eg = old[1] - new[1]
                eb = old[2] - new[2]
                if DEBUG_ZERO_ERROR_CHECK:
                    if abs(er) < 1e-9 and abs(eg) < 1e-9 and abs(eb) < 1e-9:
                        zero_err_count += 1
                    if y < 6 and len(sample_lines) < sample_limit:
                        sample_lines.append((y, x, old[0], old[1], old[2], new[0], new[1], new[2], er, eg, eb))
                sum_abs_err += abs(er) + abs(eg) + abs(eb)

                # overwrite current for clarity (not required)
                row[x][0] = float(new[0]); row[x][1] = float(new[1]); row[x][2] = float(new[2])

                # propagate
                for dx, dy, w in k_use:
                    xx = x + dx
                    yy = y + dy
                    if 0 <= xx < W and 0 <= yy < H:
                        f = w * intensity
                        dr = er * f
                        dg = eg * f
                        db = eb * f

                        # track vertical propagation magnitude
                        if diff_f is not None and dy == 1:
                            mag = abs(dr) + abs(dg) + abs(db)
                            sum_abs_to_next += mag
                            if mag > max_abs_to_next:
                                max_abs_to_next = mag

                        work[yy][xx][0] = min(255.0, max(0.0, work[yy][xx][0] + dr))
                        work[yy][xx][1] = min(255.0, max(0.0, work[yy][xx][1] + dg))
                        work[yy][xx][2] = min(255.0, max(0.0, work[yy][xx][2] + db))

                        if (DEBUG_PROPAGATION_DETAILS and diff_f is not None and y < 6 and x < 16):
                            diff_f.write(
                                f"PIX\ty={y}\tx={x}\tdx={dx}\tdy={dy}\told={old[0]:.1f},{old[1]:.1f},{old[2]:.1f}\t"
                                f"new={new[0]},{new[1]},{new[2]}\terr={er:.1f},{eg:.1f},{eb:.1f}\tf={f:.4f}\t"
                                f"applied={dr:.2f},{dg:.2f},{db:.2f}\n"
                            )

        if diff_f is not None and DEBUG_PROPAGATION_SUMMARY:
            diff_f.write(f"{y}\t{sum_abs_err:.2f}\t{sum_abs_to_next:.2f}\t{max_abs_to_next:.2f}\n")
            if DEBUG_ZERO_ERROR_CHECK:
                ratio = zero_err_count / float(W)
                diff_f.write(f"ZEROERR\t{y}\t{zero_err_count}\t{ratio:.4f}\n")
                if y < 6:
                    for (_yy,_xx,or0,og0,ob0,nr,ng,nb,er0,eg0,eb0) in sample_lines:
                        diff_f.write(f"SAMPLE\t{_yy}\t{_xx}\t{or0:.2f},{og0:.2f},{ob0:.2f}\t{nr},{ng},{nb}\t{er0:.2f},{eg0:.2f},{eb0:.2f}\n")
            if (y % 8) == 0:
                diff_f.flush()

    # Build output PIL image
    pimg = Image.new("RGB", (W, H))
    pimg.putdata(out_pixels)

    if dbg_f is not None:
        dbg_f.flush()
        dbg_f.close()
        print(f"[Mode Switch Debug] Wrote log: {dbg_path}")

    if diff_f is not None:
        diff_f.flush()
        diff_f.close()
        print(f"[Mode Switch Diffusion] Wrote log: {diff_path}")

    if return_palettes:
        return pimg, chosen_palettes
    return pimg

class CgaConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CGA Converter v124")
        self.geometry("1040x640")

        self.src_image = None
        self.output_pimage = None
        self.effective_80x100_image = None
        self.mid_tk_image = None
        self.src_tk_image = None
        self.out_tk_image = None

        self.status_var = tk.StringVar(value="Ready.")

        self._build_ui()

    # --- UI setup ---

    def _build_ui(self):
        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)

        ttk.Button(controls, text="Open Image...", command=self.on_open).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Convert", command=self.on_convert).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Optimize Palette", command=self.on_optimize).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Save GIF...", command=self.on_save).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Export COM...", command=self.on_export_com).pack(side=tk.LEFT, padx=4)

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
                "160x200 Composite (16-color)",
                "1K Color Mode",
                "160x100 (16-color)",
                "640x200 (char 16-color)",
                "80x100 HiColor",
                "320x200 Mode Switch",
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


        # Composite palette (Composite mode only)
        ttk.Label(options, text="Composite Palette/Color:").grid(row=9, column=0, sticky="w", padx=4, pady=2)
        self.composite_palette_var = tk.StringVar(value="Old CGA")
        self.composite_palette_cb = ttk.Combobox(
            options,
            textvariable=self.composite_palette_var,
            state="readonly",
            width=30,
            values=["Old CGA", "New CGA"],
        )
        self.composite_palette_cb.grid(row=9, column=1, sticky="w", padx=4, pady=2)
        self.composite_palette_cb.state(["disabled"])
        self.composite_palette_cb.bind("<<ComboboxSelected>>", self.on_composite_palette_changed)

        # Palette preview swatches (16 colors) for composite palette
        self.composite_palette_canvas = tk.Canvas(options, width=16 * 14, height=14, highlightthickness=1, highlightbackground="#888")
        self.composite_palette_canvas.grid(row=9, column=2, columnspan=4, sticky="w", padx=4, pady=2)
        self._draw_composite_palette_swatch()


        # Dithering (non-char modes) - v13: separate families
        ttk.Label(options, text="Dither family:").grid(row=1, column=0, sticky="w", padx=4, pady=2)

        self.dither_family_var = tk.StringVar(value="Error diffusion")
        family_cb = ttk.Combobox(
            options,
            textvariable=self.dither_family_var,
            state="readonly",
            values=["None", "Error diffusion", "Ordered"],
            width=18,
        )
        family_cb.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        family_cb.bind("<<ComboboxSelected>>", self.on_dither_family_changed)

        # Diffusion method
        ttk.Label(options, text="Diffusion method:").grid(row=1, column=2, sticky="w", padx=4, pady=2)
        self.diffusion_var = tk.StringVar(value="Floyd-Steinberg")
        self.diffusion_cb = ttk.Combobox(
            options,
            textvariable=self.diffusion_var,
            state="readonly",
            values=[
                "None",
                "Horizontal Striped",
                "Floyd-Steinberg",
                "Atkinson",
                "Jarvis-Judice-Ninke",
                "Stucki",
                "Burkes",
                "Sierra",
                "Sierra-2",
                "Sierra Lite",
            ],
            width=20,
        )
        self.diffusion_cb.grid(row=1, column=3, sticky="w", padx=4, pady=2)

        # Ordered matrix size
        ttk.Label(options, text="Ordered matrix:").grid(row=1, column=4, sticky="w", padx=4, pady=2)
        self.ordered_size_var = tk.IntVar(value=4)
        self.ordered_size_cb = ttk.Combobox(
            options,
            textvariable=self.ordered_size_var,
            state="readonly",
            values=[str(i) for i in range(2, 17)],
            width=5,
        )
        self.ordered_size_cb.grid(row=1, column=5, sticky="w", padx=4, pady=2)

        # Row 3: intensity controls
        ttk.Label(options, text="Diffusion intensity:").grid(row=3, column=0, sticky="w", padx=4, pady=2)
        self.dither_intensity_var = tk.DoubleVar(value=1.0)
        self.diffusion_intensity_scale = ttk.Scale(
            options,
            from_=0.0,
            to=1.0,
            variable=self.dither_intensity_var,
            orient=tk.HORIZONTAL,
            command=lambda _=None: self._update_dither_labels(),
        )
        self.diffusion_intensity_scale.grid(row=3, column=1, sticky="we", padx=4, pady=2)

        self.diffusion_intensity_label = ttk.Label(options, text="1.00")
        self.diffusion_intensity_label.grid(row=3, column=2, sticky="w", padx=4, pady=2)

        ttk.Label(options, text="Ordered strength:").grid(row=3, column=3, sticky="w", padx=4, pady=2)
        self.ordered_strength_var = tk.DoubleVar(value=1.0)
        self.ordered_strength_scale = ttk.Scale(
            options,
            from_=0.0,
            to=3.0,
            variable=self.ordered_strength_var,
            orient=tk.HORIZONTAL,
            command=lambda _=None: self._update_dither_labels(),
        )
        self.ordered_strength_scale.grid(row=3, column=4, sticky="we", padx=4, pady=2)

        self.ordered_strength_label = ttk.Label(options, text="1.00")
        self.ordered_strength_label.grid(row=3, column=5, sticky="w", padx=4, pady=2)

        # make the row stretch nicely
        options.grid_columnconfigure(1, weight=1)
        options.grid_columnconfigure(4, weight=1)


        # Scaling
        ttk.Label(options, text="Scaling:").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        self.scale_var = tk.StringVar(value="Fit (letterbox)")
        scale_cb = ttk.Combobox(
            options,
            textvariable=self.scale_var,
            state="readonly",
            values=["Fit (letterbox)", "Fill (crop)", "Stretch"],
            width=20,
        )
        scale_cb.grid(row=2, column=1, sticky="w", padx=4, pady=2)

        # Resample
        ttk.Label(options, text="Scale filter:").grid(row=2, column=2, sticky="w", padx=4, pady=2)
        self.resample_var = tk.StringVar(value="Lanczos")
        resample_cb = ttk.Combobox(
            options,
            textvariable=self.resample_var,
            state="readonly",
            values=["Lanczos", "Lanczos + Unsharp", "Gaussian (prefilter) + Lanczos", "Multi-pass Box (downscale)", "Bicubic", "Bilinear", "Box (Area)", "Hamming", "Nearest"],
            width=20,
        )
        resample_cb.grid(row=2, column=3, sticky="w", padx=4, pady=2)

        # Pre-toning
        self.tone_var = tk.BooleanVar(value=False)
        tone_cb = ttk.Checkbutton(
            options,
            text="Match contrast / tone to palette",
            variable=self.tone_var,
        )
        tone_cb.grid(row=4, column=0, columnspan=3, sticky="w", padx=4, pady=2)

        # Diffusion direction
        self.serpentine_var = tk.BooleanVar(value=True)
        serp_cb = ttk.Checkbutton(
            options,
            text="Serpentine diffusion",
            variable=self.serpentine_var,
        )
        serp_cb.grid(row=4, column=3, columnspan=3, sticky="w", padx=4, pady=2)

        # Mode Switch background control
        ttk.Label(options, text="Mode Switch Background Color:").grid(row=6, column=0, sticky="w", padx=4, pady=2)
        self.ms_bg_color_var = tk.StringVar(value="Multiple")
        self.ms_bg_color_cb = ttk.Combobox(
            options,
            textvariable=self.ms_bg_color_var,
            state="readonly",
            values=["Multiple"] + list(CGA_COLOR_NAMES),
            width=18,
        )
        self.ms_bg_color_cb.grid(row=6, column=1, columnspan=2, sticky="w", padx=4, pady=2)

        # Mode Switch: number of palette segments per scanline (1..6). 1 means one palette for the whole line.
        ttk.Label(options, text="Mode Switch segments per line:").grid(row=6, column=3, sticky="e", padx=4, pady=2)
        self.ms_switches_var = tk.IntVar(value=1)
        self.ms_switches_spin = ttk.Spinbox(
            options,
            from_=1,
            to=6,
            textvariable=self.ms_switches_var,
            width=5,
        )
        self.ms_switches_spin.grid(row=6, column=4, sticky="w", padx=4, pady=2)
        

        # Mode Switch palette strip diagnostic
        self.ms_show_palette_var = tk.BooleanVar(value=False)
        self.ms_show_palette_cb = ttk.Checkbutton(
            options,
            text="Show Mode Switch palette strip (diagnostic)",
            variable=self.ms_show_palette_var,
        )
        self.ms_show_palette_cb.grid(row=7, column=0, columnspan=6, sticky="w", padx=4, pady=2)

        # HiColor character limiting
        self.hicolor_limit_var = tk.BooleanVar(value=True)
        self.hicolor_limit_cb = ttk.Checkbutton(
            options,
            text="Limit HiColor characters (solids + shades + stripes)",
            variable=self.hicolor_limit_var,
        )
        self.hicolor_limit_cb.grid(row=5, column=0, columnspan=6, sticky="w", padx=4, pady=2)


        # Char 16-color: optional sub-sampled matcher (balances color match vs detail)
        self.char16_subsample_var = tk.BooleanVar(value=False)
        self.char16_subsample_cb = ttk.Checkbutton(
            options,
            text="Enable Sub-sampling for Char 16-color",
            variable=self.char16_subsample_var,
        )
        # start disabled; only enabled for 640x200 (char 16-color) mode
        self.char16_subsample_cb.grid(row=8, column=0, columnspan=6, sticky="w", padx=4, pady=2)

        # Preview scale
        ttk.Label(options, text="Preview scale:").grid(row=2, column=4, sticky="e", padx=4, pady=2)
        self.preview_scale_var = tk.StringVar(value="2x")
        preview_cb = ttk.Combobox(
            options,
            textvariable=self.preview_scale_var,
            state="readonly",
            values=["1x", "2x", "3x", "4x"],
            width=5,
        )
        preview_cb.grid(row=2, column=5, sticky="w", padx=4, pady=2)

        # Image frames
        img_frame = ttk.Frame(self)
        img_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=4)

        left_frame = ttk.LabelFrame(img_frame, text="Input")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.mid_frame = ttk.LabelFrame(img_frame, text="80x100 Effective")
        # start hidden; only show for 80x100 HiColor mode
        self.mid_label = ttk.Label(self.mid_frame, text="(HiColor mode only)")
        self.mid_label.pack(fill=tk.BOTH, expand=True)
        right_frame = ttk.LabelFrame(img_frame, text="Output")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.left_label = ttk.Label(left_frame, text="No image loaded")
        self.left_label.pack(fill=tk.BOTH, expand=True)

        # Tone-match preview (only shown for 320x200 4-color + "Match contrast / tone" enabled)
        self.tone_preview_frame = ttk.LabelFrame(left_frame, text="Tone-match (4-color only)")
        # start hidden
        self.tone_preview_img_label = ttk.Label(self.tone_preview_frame, text="(Enable 'Match contrast / tone' in 320x200 4-color)")
        self.tone_preview_img_label.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4,2))
        self.tone_preview_stats = ttk.Label(self.tone_preview_frame, text="", justify="left")
        self.tone_preview_stats.pack(fill=tk.X, padx=4, pady=(0,4))

        out_inner = ttk.Frame(right_frame)
        out_inner.pack(fill=tk.BOTH, expand=True)

        self.right_label = ttk.Label(out_inner, text="No output yet")
        self.right_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.ms_pal_label = ttk.Label(out_inner, text="")
        self.ms_pal_label.pack(side=tk.LEFT, fill=tk.Y, padx=(6, 0))
        self.ms_pal_tk = None
        self.ms_pal_pimage = None
        self.composite_encoded_pimage = None

        self._refresh_palette_choices()
        # Status bar
        status_frame = ttk.Frame(self)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 6))
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor='w')
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.on_dither_family_changed()
        self._update_dither_labels()

    def set_status(self, text: str):
        """Update the status bar and keep UI responsive."""
        try:
            self.status_var.set(text)
            self.update_idletasks()
        except Exception:
            pass



    # --- Mode helpers ---


    def is_4color_mode(self):
        return "320x200 (4-color)" in self.mode_var.get()

    def is_mono_mode(self):
        return "640x200 (2-color)" in self.mode_var.get()

    def is_16color_low_mode(self):
        return "160x100 (16-color)" in self.mode_var.get()

    def is_16color_char_mode(self):
        return "640x200 (char 16-color)" in self.mode_var.get()

    def is_hicolor_mode(self):
        return "80x100 HiColor" in self.mode_var.get()

    
    def is_composite_mode(self):
        m = self.mode_var.get()
        return ("Composite" in m) and ("160x200" in m)

    def is_text_ntsc_4k_mode(self):
        return "1K Color Mode" in self.mode_var.get()


    def is_mode_switch_mode(self):
        return "320x200 Mode Switch" in self.mode_var.get()

    def get_target_size(self):
        if self.is_4color_mode() or self.is_mode_switch_mode():
            return 320, 200
        if self.is_mono_mode():
            return 640, 200
        if self.is_text_ntsc_4k_mode():
            # Effective logical resolution of the 1024-color text hack.
            return 80, 100
        if self.is_composite_mode():
            return 160, 200
        if self.is_16color_low_mode():
            return 160, 100
        # char 16-color
        if self.is_16color_char_mode():
            return 640, 200
        # 80x100 HiColor (internally uses 640x200 blocks)
        if self.is_hicolor_mode():
            return 640, 200
        return 640, 200

        # 80x100 HiColor (internally uses 640x200 blocks)
        if self.is_hicolor_mode():
            return 640, 200
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
        elif self.is_composite_mode():
            names = ["(Composite mode)"]
            self.palette_cb["values"] = names
            self.palette_cb.state(["disabled"])
            self.palette_var.set("(Composite mode)")
        else:
            # 16-color modes: fixed palette
            names = ["CGA 16-color"]
            self.palette_cb["values"] = names
            self.palette_cb.state(["disabled"])
            self.palette_var.set("CGA 16-color")

    

    def get_current_composite_palette(self):
        name = getattr(self, "composite_palette_var", None).get() if getattr(self, "composite_palette_var", None) is not None else ""
        name = (name or "").strip()
        if not name:
            name = "Old CGA"

        pal = COMPOSITE_PALETTES.get(name)
        if pal is None:
            # Lazily build the palette via the Reenigne/Jenner decoder.
            pal = _build_reenigne_composite_palette(name)
            COMPOSITE_PALETTES[name] = pal

        # Safety: always return 16 RGB tuples
        if not pal or len(pal) < 16:
            pal = _build_reenigne_composite_palette("Old CGA")
            COMPOSITE_PALETTES["Old CGA"] = pal
        return pal

    def _draw_composite_palette_swatch(self):
        try:
            c = getattr(self, "composite_palette_canvas", None)
            if c is None:
                return
            c.delete("all")
            pal = self.get_current_composite_palette()
            sw = 14
            for i, (r, g, b) in enumerate(pal[:16]):
                x0 = i * sw
                c.create_rectangle(x0, 0, x0 + sw, sw, outline="", fill=f"#{r:02x}{g:02x}{b:02x}")
        except Exception:
            pass

    def on_composite_palette_changed(self, event=None):
        self._draw_composite_palette_swatch()
        # If we're currently in composite mode and already have an output, reconvert so the preview updates.
        if self.is_composite_mode() and self.src_image is not None:
            # Keep behavior consistent with other option changes: user must click Convert.
            # We only update the mid/right previews if there's an existing output.
            if getattr(self, "output_pimage", None) is not None:
                self._update_right_preview()
                self._update_mid_preview()

    def on_mode_changed(self, event=None):
        self._refresh_palette_choices()


        # Default diffusion method for Mode Switch (strong vertical propagation)
        if self.mode_var.get() == "320x200 Mode Switch":
            # Only override if blank or None; don't stomp user choice
            if getattr(self, "diffusion_method_var", None) is not None:
                if self.diffusion_method_var.get() in ("", "None"):
                    self.diffusion_method_var.set("Horizontal Striped")

        # Show/hide the 80x100 effective preview panel
        if getattr(self, "mid_frame", None) is not None:
            if self.is_hicolor_mode():
                if not self.mid_frame.winfo_ismapped():
                    self.mid_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=4, pady=4)
            else:
                if self.mid_frame.winfo_ismapped():
                    self.mid_frame.pack_forget()

        # Enable HiColor limit checkbox only in HiColor mode
        if getattr(self, "hicolor_limit_cb", None) is not None:
            if self.is_hicolor_mode():
                self.hicolor_limit_cb.state(["!disabled"])
            else:
                self.hicolor_limit_cb.state(["disabled"])

        # Enable Char16 subsampling checkbox only in char 16-color mode
        if getattr(self, "char16_subsample_cb", None) is not None:
            if self.is_16color_char_mode():
                self.char16_subsample_cb.state(["!disabled"])
            else:
                self.char16_subsample_cb.state(["disabled"])


        # Enable Composite palette controls in Composite and NTSC Text 4K modes
        if getattr(self, "composite_palette_cb", None) is not None:
            if self.is_composite_mode() or self.is_text_ntsc_4k_mode():
                self.composite_palette_cb.state(["!disabled"])
            else:
                self.composite_palette_cb.state(["disabled"])
        if getattr(self, "composite_palette_canvas", None) is not None:
            # Hide visual emphasis when disabled by clearing border
            if self.is_composite_mode() or self.is_text_ntsc_4k_mode():
                self.composite_palette_canvas.configure(highlightbackground="#888")
            else:
                self.composite_palette_canvas.configure(highlightbackground="#bbb")


        self._update_mid_preview()
        self._update_right_preview()
        self.set_status("Ready.")

    
    def _update_dither_labels(self):
        # Keep the numeric labels in sync with sliders
        try:
            self.diffusion_intensity_label.configure(text=f"{float(self.dither_intensity_var.get()):.2f}")
        except Exception:
            pass
        try:
            self.ordered_strength_label.configure(text=f"{float(self.ordered_strength_var.get()):.2f}")
        except Exception:
            pass

    def on_dither_family_changed(self, event=None):
        """
        v13: Dither family selector toggles the relevant controls.
        """
        family = self.dither_family_var.get()

        is_diff = (family == "Error diffusion")
        is_ord = (family == "Ordered")

        # Diffusion controls
        try:
            self.diffusion_cb.state(["!disabled"] if is_diff else ["disabled"])
            self.diffusion_intensity_scale.state(["!disabled"] if is_diff else ["disabled"])
            self.diffusion_intensity_label.state(["!disabled"] if is_diff else ["disabled"])
        except Exception:
            pass

        # Ordered controls
        try:
            self.ordered_size_cb.state(["!disabled"] if is_ord else ["disabled"])
            self.ordered_strength_scale.state(["!disabled"] if is_ord else ["disabled"])
            self.ordered_strength_label.state(["!disabled"] if is_ord else ["disabled"])
        except Exception:
            pass

        # If family is None, disable both sets
        if family == "None":
            try:
                self.diffusion_cb.state(["disabled"])
                self.diffusion_intensity_scale.state(["disabled"])
                self.diffusion_intensity_label.state(["disabled"])
                self.ordered_size_cb.state(["disabled"])
                self.ordered_strength_scale.state(["disabled"])
                self.ordered_strength_label.state(["disabled"])
            except Exception:
                pass

        self._update_dither_labels()

    def get_current_palette(self):
        if self.is_mode_switch_mode():
            return CGA_16COLOR_PALETTE
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

    

    
    def _update_tone_preview(self):
        """Show the tone-matched input preview and the computed adjustment stats."""
        show = self.is_4color_mode() and self.tone_var.get() and (getattr(self, "toned_input_image", None) is not None)
        if not hasattr(self, "tone_preview_frame"):
            return
        if show:
            if not self.tone_preview_frame.winfo_ismapped():
                self.tone_preview_frame.pack(fill=tk.BOTH, expand=False, padx=4, pady=4)
            preview = self.toned_input_image.copy()
            preview.thumbnail((400, 400), resample=get_resample_filter("Lanczos"))
            self.toned_tk_image = ImageTk.PhotoImage(preview)
            self.tone_preview_img_label.configure(image=self.toned_tk_image, text="")
            dbg = getattr(self, "tone_debug", None) or {}
            stats = []
            if dbg:
                sb = dbg.get("src_black_rgb")
                sw = dbg.get("src_white_rgb")
                pb = dbg.get("pal_black_rgb")
                pw = dbg.get("pal_white_rgb")
                cs = dbg.get("contrast_scale_rgb")
                bo = dbg.get("brightness_offset_rgb")
                if sb and sw and pb and pw:
                    stats.append(f"Src black (R,G,B): ({sb[0]:.1f}, {sb[1]:.1f}, {sb[2]:.1f})")
                    stats.append(f"Src white (R,G,B): ({sw[0]:.1f}, {sw[1]:.1f}, {sw[2]:.1f})")
                    stats.append(f"Pal black (R,G,B): ({pb[0]:.1f}, {pb[1]:.1f}, {pb[2]:.1f})")
                    stats.append(f"Pal white (R,G,B): ({pw[0]:.1f}, {pw[1]:.1f}, {pw[2]:.1f})")
                if cs:
                    stats.append(f"Contrast scale (R,G,B): ({cs[0]:.3f}, {cs[1]:.3f}, {cs[2]:.3f})")
                if bo:
                    stats.append(f"Offset (R,G,B): ({bo[0]:.1f}, {bo[1]:.1f}, {bo[2]:.1f})")
            self.tone_preview_stats.configure(text="\n".join(stats))
        else:
            # hide
            if self.tone_preview_frame.winfo_ismapped():
                self.tone_preview_frame.pack_forget()

    def _update_mid_preview(self):
        """Show the 80x100 effective image preview (HiColor mode only)."""
        if not getattr(self, "effective_80x100_image", None):
            return
        if not getattr(self, "mid_frame", None):
            return
        # Render small image scaled up for visibility
        preview = self.effective_80x100_image.copy()
        # scale up to a reasonable display size
        scale = 4
        preview = preview.resize((80*scale, 100*scale), resample=get_resample_filter("Nearest"))
        self.mid_tk_image = ImageTk.PhotoImage(preview)
        self.mid_label.configure(image=self.mid_tk_image, text="")
    def _make_output_preview_image(self):
        if not self.output_pimage:
            return None
        img = self.output_pimage.convert("RGB")
        w, h = img.size

        # Composite (NTSC) output has a different effective pixel aspect on real CRTs.
        # On modern square-pixel displays, 640x200 composite previews can look "wide".
        # Fix B: apply a simple horizontal pixel-aspect correction for Composite mode.
        last_mode = getattr(self, "last_output_mode", "") or ""
        if (("Composite" in last_mode) or ("1K Color Mode" in last_mode)) and (w >= 320):
            aspect_x = 0.83  # ~4:3 correction for CGA composite on square-pixel displays
            corr_w = max(1, int(round(w * aspect_x)))
            img = img.resize((corr_w, h), resample=get_resample_filter("Nearest"))
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
        self._update_tone_preview()

        # Optional: Mode Switch palette strip (diagnostic)
        if getattr(self, 'ms_pal_pimage', None) is not None:
            strip = self.ms_pal_pimage
            # match the preview height
            try:
                sh = preview.size[1]
                sw = max(24, int(strip.size[0] * (sh / strip.size[1])))
                strip_r = strip.resize((sw, sh), resample=get_resample_filter('Nearest'))
                self.ms_pal_tk = ImageTk.PhotoImage(strip_r)
                self.ms_pal_label.configure(image=self.ms_pal_tk, text='')
            except Exception:
                self.ms_pal_label.configure(image='', text='')
        else:
            self.ms_pal_label.configure(image='', text='')

    def on_convert(self):
        if self.src_image is None:
            messagebox.showinfo("No image", "Please open an image first.")
            return

        self.set_status("Converting...")
        # Clear Mode Switch diagnostic strip unless a Mode Switch conversion sets it
        self.ms_pal_pimage = None

        mode = self.mode_var.get()
        # Remember the mode used to generate the current output so the preview can
        # apply mode-specific display adjustments (e.g., composite aspect correction)
        # even if the user changes the dropdown after converting.
        self.last_output_mode = mode

        palette = None
        composite_palette = None
        if self.is_composite_mode() or self.is_text_ntsc_4k_mode():
            # NTSC-based modes use the Composite preset selector (Old/New CGA).
            if self.is_composite_mode():
                composite_palette = self.get_current_composite_palette()
                if not composite_palette or len(composite_palette) < 16:
                    messagebox.showinfo("No composite palette", "No Composite palette selected.")
                    return
        else:
            palette = self.get_current_palette()
            if not palette:
                messagebox.showinfo("No palette", "No CGA palette / color selected.")
                return


        target_w, target_h = self.get_target_size()
        scale_mode = self.scale_var.get()
        resample_name = self.resample_var.get()
        dither_family = self.dither_family_var.get()
        # Normalize UI labels to internal names
        if dither_family in ("Error diffusion", "Diffusion"):
            dither_family = "Diffusion"
        diffusion_method = self.diffusion_var.get()
        intensity= float(self.dither_intensity_var.get())
        serpentine = bool(self.serpentine_var.get())
        dither_intensity = float(self.dither_intensity_var.get())
        ordered_size = int(self.ordered_size_var.get())
        ordered_strength = float(self.ordered_strength_var.get())

        resized = resize_with_mode(self.src_image, target_w, target_h, scale_mode, resample_name)

        # Safety: never mutate or reuse the original PIL object; always work on a fresh RGB copy.
        # Some code paths (especially composite / palette workflows) may create palettized images; error diffusion expects RGB triples.
        resized = resized.copy()
        if resized.mode != 'RGB':
            resized = resized.convert('RGB')

        # Match contrast/tone to palette (ONLY for standard 320x200 4-color mode).
        # This is a luminance remap (not a quantization), so it is safe to apply even when dithering.
        self.toned_input_image = None
        self.tone_debug = None
        if self.is_4color_mode() and (not self.is_mode_switch_mode()) and self.tone_var.get():
            toned, dbg = tone_image_to_palette_debug(resized, palette)
            self.toned_input_image = toned
            self.tone_debug = dbg
        else:
            toned = resized

        if self.is_mode_switch_mode():
            # Mode-switch raster palette per scanline (CGA 320x200 4-color with per-scanline palette/background changes)
            # Work on a 320x200 image regardless of other target sizes.
            scaled = resize_with_mode(self.src_image, 320, 200, scale_mode, resample_name)
            toned_ms = scaled  # keep full RGB so dithering influences per-scanline palette selection
            # Mode Switch background behavior:
            #   - 'Multiple' => allow background/palette to vary per scanline (current behavior)
            #   - any color  => force that CGA background color for all scanlines
            forced_bg_idx = None
            bg_sel = getattr(self, 'ms_bg_color_var', tk.StringVar(value='Multiple')).get()
            if bg_sel and bg_sel != 'Multiple' and bg_sel in CGA_COLOR_NAMES:
                forced_bg_idx = CGA_COLOR_NAMES.index(bg_sel)

            want_pal_strip = bool(getattr(self, 'ms_show_palette_var', tk.BooleanVar(value=False)).get())


            if dither_family == "Ordered":
                pimg = quantize_320x200_mode_switch(
                    toned_ms,
                    forced_bg_idx=forced_bg_idx,
                    dither_family="Ordered",
                    ordered_matrix_size=ordered_size,
                    ordered_strength=ordered_strength,
                    serpentine=serpentine,
                    segments_per_line=int(getattr(self, "ms_switches_var", tk.IntVar(value=1)).get()),
                    return_palettes=want_pal_strip,
                )
            elif dither_family in ("Diffusion", "Error diffusion"):
                # Diffusion must be applied during per-scanline palette selection so vertical propagation can influence the next scanline.
                pimg = quantize_320x200_mode_switch(
                    toned_ms,
                    forced_bg_idx=forced_bg_idx,
                    dither_family="Diffusion",
                    diffusion_name=diffusion_method,
                    diffusion_intensity=dither_intensity,
                    serpentine=serpentine,
                    segments_per_line=int(getattr(self, "ms_switches_var", tk.IntVar(value=1)).get()),
                    return_palettes=want_pal_strip,
                )
            else:
                pimg = quantize_320x200_mode_switch(
                    toned_ms,
                    forced_bg_idx=forced_bg_idx,
                    dither_family="None",
                    serpentine=serpentine,
                    segments_per_line=int(getattr(self, "ms_switches_var", tk.IntVar(value=1)).get()),
                    return_palettes=want_pal_strip,
                )

            # If requested, Mode Switch can return (image, palettes_by_scanline)
            pals_by_y = None
            if want_pal_strip and isinstance(pimg, tuple) and len(pimg) == 2:
                pimg, pals_by_y = pimg

            # Build diagnostic palette strip (4 colors per scanline)
            if want_pal_strip and pals_by_y is not None:
                try:
                    # pals_by_y entries may be either:
                    #   - a single 4-color palette: [(r,g,b),...]
                    #   - a list of segment palettes: [pal4_seg0, pal4_seg1, ...]
                    first = pals_by_y[0] if pals_by_y else None
                    # pals_by_y entries may be either:
                    #   - a single 4-color palette: [(r,g,b),...]
                    #   - a list of segment palettes: [pal4_seg0, pal4_seg1, ...]
                    if first and isinstance(first, (list, tuple)) and len(first) == 4 and isinstance(first[0], (list, tuple)) and len(first[0]) == 3:
                        seg_n = 1
                    elif first and isinstance(first, list) and len(first) > 0 and isinstance(first[0], (list, tuple)) and len(first[0]) == 4:
                        seg_n = len(first)
                    else:
                        seg_n = 1
                    strip_w = max(64, int(seg_n) * 16)  # 16 px per segment (4 colors x 4px)
                    strip = Image.new("RGB", (strip_w, 200), (0, 0, 0))
                    block_w = max(1, strip_w // (seg_n * 4))

                    for yy in range(200):
                        entry = pals_by_y[yy]
                        if entry is None:
                            entry = [(0, 0, 0)] * 4

                        if seg_n == 1:
                            pal4 = entry
                            if pal4 is None or len(pal4) != 4:
                                pal4 = [(0, 0, 0)] * 4
                            for i in range(4):
                                x0 = i * block_w
                                x1 = strip_w if i == 3 else (i + 1) * block_w
                                color = tuple(int(v) for v in pal4[i])
                                for xx in range(x0, x1):
                                    strip.putpixel((xx, yy), color)
                        else:
                            # Segment palettes across the line
                            for si in range(seg_n):
                                pal4 = entry[si] if (isinstance(entry, list) and si < len(entry)) else [(0, 0, 0)] * 4
                                if pal4 is None or len(pal4) != 4:
                                    pal4 = [(0, 0, 0)] * 4
                                for i in range(4):
                                    x0 = (si * 4 + i) * block_w
                                    x1 = strip_w if (si == seg_n - 1 and i == 3) else (si * 4 + i + 1) * block_w
                                    color = tuple(int(v) for v in pal4[i])
                                    for xx in range(x0, x1):
                                        strip.putpixel((xx, yy), color)

                    self.ms_pal_pimage = strip
                except Exception:
                    self.ms_pal_pimage = None
            else:
                self.ms_pal_pimage = None

            self.output_pimage = pimg
            self._update_right_preview(); self._update_mid_preview()
            self.set_status("Ready.")
            return
        if self.is_16color_char_mode():
            # Text-block mode constraint is too strong to dither "during" mapping.
            # Instead:
            #   1) Convert to a normal 640x200 CGA 16-colour bitmap using the selected dither.
            #   2) Map that 16-colour result into the 8x2 character-slice constraints.
            if dither_family == "Ordered":
                pre_p = apply_ordered_dither(toned, CGA_16COLOR_PALETTE, matrix_size=ordered_size, strength=ordered_strength)
            elif dither_family in ("Error diffusion", "Diffusion"):
                pre_p = apply_diffusion_dither(toned, CGA_16COLOR_PALETTE, diffusion_method, intensity=dither_intensity, serpentine=serpentine)
            else:
                pre_p = apply_diffusion_dither(toned, CGA_16COLOR_PALETTE, "None", intensity=0.0)

            pre_indices = list(pre_p.getdata())
            pimg = quantize_char16_textblock_from_indices(pre_indices, subsample=bool(self.char16_subsample_var.get()))

        elif self.is_hicolor_mode():
            # 80x100 HiColor: scale the source into 80x100 using the selected scaling mode,
            # apply dithering in 80x100 cell space, then expand to 640x200 using 2x8 patterns.
            resized80 = resize_with_mode(self.src_image, 80, 100, scale_mode, resample_name)
            toned80 = resized80

            pimg, effective = quantize_80x100_hicolor(
                toned80.convert("RGB"),
                dither_family=dither_family,
                diffusion_name=diffusion_method,
                intensity=dither_intensity,
                ordered_size=int(self.ordered_size_var.get()),
                ordered_strength=float(self.ordered_strength_var.get()),
                limit_chars=bool(self.hicolor_limit_var.get()),
            )

            self.effective_80x100_image = effective
            self._update_mid_preview()

        elif self.is_text_ntsc_4k_mode():
            # "CGA in 1024 colors" text/composite trick (int10h.org article).
            # Logical resolution: 80x100 cells (each cell is 8x2 CGA pixels).
            # We dither in 80x100 space against the 1024 achievable (fg,bg,pattern) combos,
            # then render a 640x200 RGBI stream and decode via the Reenigne/Jenner NTSC simulator.
            preset = (self.composite_palette_var.get() or "Old CGA").strip()
            lut = _build_text_ntsc_4k_lut(preset)  # [(avg_rgb, fg, bg, pat, swap), ...] length=1024
            palette1024 = [avg for (avg, _fg, _bg, _pat, _swap) in lut]

            # 1) Scale source into 80x100 logical cells.
            src80 = resize_with_mode(self.src_image, 80, 100, scale_mode, resample_name).convert("RGB")

            # 2) Dither in 80x100 space to indices 0..1023 (IMPORTANT: do NOT build a 'P' image; PIL palettes are 256 max).
            if dither_family == "Ordered":
                indices80 = ordered_dither(src80, palette1024, matrix_size=ordered_size, strength=ordered_strength)
            elif dither_family == "Diffusion":
                method_name = diffusion_method
                if dither_intensity <= 0.0:
                    indices80 = no_dither(src80, palette1024)
                else:
                    # Match apply_diffusion_dither() kernel selection, but return indices directly.
                    if method_name == "Horizontal Striped":
                        kernel, divisor = _HSTRIPE_KERNEL, 1
                    elif method_name == "Floyd-Steinberg":
                        kernel, divisor = _FS_KERNEL, 16
                    elif method_name == "Atkinson":
                        kernel, divisor = _ATKINSON_KERNEL, 8
                    elif method_name == "Jarvis-Judice-Ninke":
                        kernel, divisor = _JJN_KERNEL, 48
                    elif method_name == "Stucki":
                        kernel, divisor = _STUCKI_KERNEL, 42
                    elif method_name == "Burkes":
                        kernel, divisor = _BURKES_KERNEL, 32
                    elif method_name == "Sierra":
                        kernel, divisor = _SIERRA_KERNEL, 32
                    elif method_name == "Sierra-2":
                        kernel, divisor = _SIERRA2_KERNEL, 16
                    elif method_name == "Sierra Lite":
                        kernel, divisor = _SIERRA_LITE_KERNEL, 4
                    else:
                        kernel, divisor = None, None

                    if kernel is None:
                        indices80 = no_dither(src80, palette1024)
                    else:
                        indices80 = _error_diffusion_dither(
                            src80, palette1024, kernel, divisor,
                            intensity=float(dither_intensity), serpentine=bool(serpentine)
                        )
            else:
                indices80 = no_dither(src80, palette1024)

            # 3) Resolve per-cell parameters from LUT.
            chosen = []
            for idx in indices80:
                _avg, fg, bg, pat, swap = lut[int(idx)]
                chosen.append((fg, bg, pat, swap))

            # 4) Render RGBI stream for a 640x200 raster (each cell expands to 8x2 pixels), then decode.
            params = _COMPOSITE_PRESETS.get(preset, _COMPOSITE_PRESETS["Old CGA"])
            hue, sat, bri, con, shp, new_cga, cgamode = params
            ctx = _ReCompositeContextPy()
            ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri, contrast=con, sharpness=shp, new_cga=new_cga)
            ctx.update_cga16_color(int(cgamode))

            rgb_out = []
            for ycell in range(100):
                for dy in range(2):
                    in_rgbi = [0] * 640
                    base_cell = ycell * 80
                    for xcell in range(80):
                        fg, bg, pat, swap = chosen[base_cell + xcell]
                        x0 = xcell * 8
                        for k, bit in enumerate(pat):
                            use_fg = (bit == 1)
                            if swap:
                                use_fg = not use_fg
                            in_rgbi[x0 + k] = fg if use_fg else bg
                    rgb_out.extend(ctx.decode_scanline_rgba(0, in_rgbi))

            rgb_img = Image.new("RGB", (640, 200))
            # Quantize to RGB444 (4096 colors) for the "1K Color Mode" output.
            rgb_img.putdata([_quantize_rgb444(px) for px in rgb_out])

            pimg = rgb_img


        elif self.is_composite_mode():
            # 160x200 Composite (16-color) via 640x200 1bpp + Reenigne/Jenner NTSC decode.
            #
            # A) Quantize/dither the *logical* 160x200 image into the selected 16-color composite palette.
            if dither_family == "Ordered":
                p160 = apply_ordered_dither(toned, composite_palette, matrix_size=ordered_size, strength=ordered_strength)
            elif dither_family == "Diffusion":
                p160 = apply_diffusion_dither(toned, composite_palette, diffusion_method, intensity=dither_intensity, serpentine=serpentine)
            else:
                indices160 = no_dither(toned, composite_palette)
                p160 = indices_to_pimage(indices160, composite_palette, toned.size)

            idx160 = list(p160.getdata())
            w160, h160 = toned.size  # expected 160x200

            # B) Encode each 160-wide pixel into 4 hi-res pixels (640-wide) using the 16 4-bit patterns.
            bits = []
            for y in range(h160):
                row_base = y * w160
                for x in range(w160):
                    ci = int(idx160[row_base + x]) & 0x0F
                    pat = _COMPOSITE_HIRES_PATTERNS[ci]
                    bits.extend(pat)

            # Store a 640x200 1bpp pimage for packing/export (mode 06h).
            bw_palette = [(0, 0, 0), (255, 255, 255)]
            self.composite_bits_pimage = indices_to_pimage(bits, bw_palette, (w160 * 4, h160))

            # C) Build a simulated composite preview by decoding the hi-res pixels through Reenigne.
            preset = (self.composite_palette_var.get() or "Old CGA").strip()
            params = _COMPOSITE_PRESETS.get(preset, _COMPOSITE_PRESETS["Old CGA"])
            hue, sat, bri, con, shp, new_cga, cgamode = params
            ctx = _ReCompositeContextPy()
            ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri, contrast=con, sharpness=shp, new_cga=new_cga)
            ctx.update_cga16_color(int(cgamode))

            rgb_out = []
            w640 = w160 * 4
            for y in range(h160):
                yo = y * w640
                # decoder expects RGBI nibbles; use 0/15 for black/white pixels
                in_rgbi = [15 if (bits[yo + x] & 1) else 0 for x in range(w640)]
                rgb_out.extend(ctx.decode_scanline_rgba(0, in_rgbi))

            rgb_img = Image.new("RGB", (w640, h160))
            rgb_img.putdata(rgb_out)

            # For the main output preview, keep it at 640x200 (your preview scaler will handle fit).
            pimg = rgb_img


        else:
            # Normal modes: honour dithering choice

            # MONO (640x200 2-color): threshold/dither purely on luminance, then substitute the chosen foreground for white.
            if self.is_mono_mode():
                fg_rgb = palette[1] if palette and len(palette) > 1 else (255, 255, 255)
                # Convert input to grayscale RGB so existing dither code ignores original chroma.
                gray = toned.convert("L")
                gray_rgb = Image.merge("RGB", (gray, gray, gray))
                bw_palette = [(0, 0, 0), (255, 255, 255)]
                if dither_family == "Ordered":
                    bw_pimg = apply_ordered_dither(gray_rgb, bw_palette, matrix_size=ordered_size, strength=ordered_strength)
                    indices = list(bw_pimg.getdata())
                elif dither_family == "Diffusion":
                    bw_pimg = apply_diffusion_dither(gray_rgb, bw_palette, diffusion_method, intensity=dither_intensity, serpentine=serpentine)
                    indices = list(bw_pimg.getdata())
                else:
                    # Simple threshold at mid gray
                    arrg = np.asarray(gray, dtype=np.uint8)
                    indices = [1 if v >= 128 else 0 for v in arrg.flatten()]
                # Now build final 2-color image with selected foreground color
                pimg = indices_to_pimage(indices, [(0, 0, 0), fg_rgb], toned.size)
            else:
                if dither_family == "Ordered":
                    pimg = apply_ordered_dither(toned, palette, matrix_size=ordered_size, strength=ordered_strength)
                elif dither_family == "Diffusion":
                    # Use full-color source so diffusion/ordered can generate real quantization error.
                    pimg = apply_diffusion_dither(toned, palette, diffusion_method, intensity=dither_intensity, serpentine=serpentine)
                else:
                    # No dithering: direct palette mapping.
                    indices = no_dither(toned, palette)
                    pimg = indices_to_pimage(indices, palette, toned.size)

        self.output_pimage = pimg
        if not self.is_hicolor_mode():
            self.effective_80x100_image = None
            if getattr(self, "mid_label", None) is not None:
                self.mid_label.configure(image="", text="(HiColor mode only)")
        self._update_right_preview()
        self.set_status("Ready.")

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

        self.set_status("Optimizing palette...")

        total = len(palettes)
        for i, (name, pal) in enumerate(palettes.items(), start=1):
            if i == 1 or i % 2 == 0:
                self.set_status(f"Optimizing palette... {i}/{total}")
            if self.is_4color_mode() and self.tone_var.get():
                img_for_score, _dbg = tone_image_to_palette_debug(base_resized, pal)
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
        self.set_status("Ready.")

    def on_export_com(self):
        """Export the current converted image as a DOS .COM (static CGA) for 320x200 or 640x200."""
        mode = self.mode_var.get()
        if mode not in ("320x200 (4-color)", "640x200 (2-color)", "160x200 Composite (16-color)", "160x100 (16-color)", "640x200 (char 16-color)", "80x100 HiColor"):
            messagebox.showinfo(
                "Export COM",
                "COM export is supported only for:\n"
                "- 320x200 (4-color)\n"
                "- 640x200 (2-color)\n"
                "- 160x200 Composite (16-color)\n"
                "- 160x100 (16-color)\n"
                "- 640x200 (char 16-color)\n"
                "- 80x100 HiColor",
            )
            return


        if self.output_pimage is None:
            messagebox.showinfo("Export COM", "Please click Convert first so there is an output image to export.")
            return

        try:
            if mode == "320x200 (4-color)":
                vram = pack_cga_320x200_4color_vram(self.output_pimage)
                pal_name = (self.palette_var.get() or "").strip()
                palbyte = cga_color_select_for_320_palette_name(pal_name)
                mode_bios = 0x0004
                com = build_com_static_cga(mode_bios, vram, color_select_3d9=palbyte)
                default_name = "cga_320.com"
            elif mode == "160x200 Composite (16-color)":
                # Export as CGA 640x200 2-color (BIOS mode 06h). The *apparent* 16 colors
                # come from composite artifacting on a real NTSC composite display.
                if getattr(self, "composite_bits_pimage", None) is None:
                    raise ValueError("No composite hi-res image available. Please Convert first.")
                vram = pack_cga_640x200_2color_vram(self.composite_bits_pimage)

                # Foreground nibble for mode 06h: use White (15). (Composite decoding ignores RGBI fg color,
                # but we keep it sane for RGB displays.)
                palbyte = 0x0F
                # BIOS mode 06h enables 640x200 but leaves composite colorburst disabled (B/W).
                # Clear bit 2 of the CGA mode-control register (port 3D8h) to enable NTSC colorburst
                # for composite artifact color.
                com = build_com_static_cga(0x0006, vram, color_select_3d9=palbyte, mode_control_3d8=0x1A)
                default_name = "cga_composite_160x200.com"
            elif mode == "640x200 (2-color)":
                vram = pack_cga_640x200_2color_vram(self.output_pimage)

                # 640x200 (BIOS mode 06h) uses port 3D9h bits 0..3 as the FOREGROUND color nibble.
                # Our 2-color palette dropdown entries are named like "Black / <ColorName>".
                sel = (self.palette_var.get() or "").strip()

                fg_name = sel
                if sel.startswith("Black / "):
                    fg_name = sel.split("Black / ", 1)[1].strip()

                fg_idx = 15  # default = White
                if fg_name in CGA_COLOR_NAMES:
                    fg_idx = CGA_COLOR_NAMES.index(fg_name)

                palbyte = fg_idx & 0x0F
                com = build_com_static_cga(0x0006, vram, color_select_3d9=palbyte)
                default_name = "cga_640.com"
            elif mode == "160x100 (16-color)":
                vram_text = pack_cga_160x100_16color_text_vram(self.output_pimage)
                com = build_com_cga_160x100x16(vram_text)
                default_name = "cga_160x100.com"
            elif mode == "640x200 (char 16-color)":
                char_attr = pack_text_80x100_char16(self.output_pimage)
                com = build_com_cga_160x100x16(char_attr)  # reuse known-good 80x100 CRTC+3D8 sequence
                default_name = "cga_char16_80x100.com"


            elif mode == "80x100 HiColor":
                # HiColor uses the same 80x100 text tweak as the char16 mode; the only difference
                # is how the 640x200 output was produced. We repack the 8x2 blocks into (ch,attr).
                char_attr = pack_text_80x100_char16(self.output_pimage)
                com = build_com_cga_160x100x16(char_attr)  # reuse known-good 80x100 CRTC+3D8 sequence
                default_name = "cga_hicolor_80x100.com"

        except Exception as e:
            messagebox.showerror("Export COM", f"Failed to build COM:\n{e}")
            return

        path = filedialog.asksaveasfilename(
            title="Save DOS COM",
            defaultextension=".com",
            initialfile=default_name,
            filetypes=[("DOS COM", "*.com"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(com)
            messagebox.showinfo("Export COM", f"Saved:\n{path}")
        except Exception as e:
            messagebox.showerror("Export COM", f"Failed to save file:\n{e}")


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