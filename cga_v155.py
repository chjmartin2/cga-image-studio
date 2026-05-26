
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
import threading
from typing import List, Tuple, Optional, Dict
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np
import math

# -----------------------------
# Verbose status tracing support
# -----------------------------
STATUS_CB = None  # set to a callable(str) during conversion for absurd verbosity

def status_dbg(msg: str):
    """Module-level debug status hook (safe no-op if not active)."""
    global STATUS_CB
    cb = STATUS_CB
    if cb is None:
        return
    try:
        cb(str(msg))
    except Exception:
        pass




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


def _palette_name_is_tweaked(name):
    """Return True if a palette dict key (from build_cga_4color_palettes) is a
    Tweaked-family palette (corresponds to BIOS mode 05h on RGB monitors).
    Tweaked palettes are: {cyan, red, light gray} or {light cyan, light red, white}.
    """
    return name.startswith("Tweaked")


def filter_candidates_by_tweaked_mode(candidates_dict, tweaked_mode):
    """Filter a {name: palette} dict to either Tweaked-only or non-Tweaked palettes.
    
    This is the encoder's way of guaranteeing 3D8 stays constant across all 200
    scanlines, allowing the COM builder to use the proven KABLAM fast path
    (single OUT per scanline, no back-to-back register writes).
    
    Args:
        candidates_dict: {name: [bg, fg1, fg2, fg3]} palette dictionary
        tweaked_mode: "off" → restrict to mode-04 (standard) palettes only
                      "on"  → restrict to mode-05 (Tweaked) palettes only
    
    Returns: list of palettes (the .values() of the filtered dict)
    """
    if tweaked_mode == "on":
        filtered = {k: v for k, v in candidates_dict.items() if _palette_name_is_tweaked(k)}
    elif tweaked_mode == "off":
        filtered = {k: v for k, v in candidates_dict.items() if not _palette_name_is_tweaked(k)}
    else:
        filtered = dict(candidates_dict)
    return list(filtered.values())

# Base 4-color palette families (foreground triplets). Background is selected separately in the UI.
CGA_4COLOR_BASESETS = {
    "Cyan/Magenta/White LOW":  [3, 5, 7],
    "Cyan/Magenta/White":      [11, 13, 15],
    "Red/Green/Yellow LOW":    [2, 4, 6],
    "Red/Green/Yellow":        [10, 12, 14],
    "Tweaked Cyan/Red/White LOW": [3, 4, 7],
    "Tweaked Cyan/Red/White":     [11, 12, 15],
    "Dark Red/Green/Brown":    [2, 4, 6],
}

def build_cga_4color_palette(base_name: str, bg_name: str):
    """Build a CGA 320x200 (4-color) RGB palette from a base family + background color."""
    bg_name = (bg_name or "Black").strip()
    if bg_name not in CGA_COLOR_NAMES:
        bg_name = "Black"
    bg_idx = CGA_COLOR_NAMES.index(bg_name)
    fgs = CGA_4COLOR_BASESETS.get(base_name)
    if not fgs:
        # sensible default
        fgs = CGA_4COLOR_BASESETS["Cyan/Magenta/White"]
    return [CGA_COLORS[bg_idx], CGA_COLORS[fgs[0]], CGA_COLORS[fgs[1]], CGA_COLORS[fgs[2]]]







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

# NTSC text-hack patterns (8 pixels wide) used by the 1024-color CGA text composite trick.
# These are the four useful row-0 patterns from the CGA character ROM:
#   0xCC = char 0x55 ('U')   row 0..5 = 0xCC (constant) — works at MaxSL=1 (2 scanlines)
#   0x66 = char 0x13 ('‼')   row 0..2 = 0x66 (constant) — works at MaxSL=1 (2 scanlines)
#   0x22 = char 0xB0 ('░')   row 0 only (rows alternate 0x22/0x88) — needs MaxSL=0 (1 scanline)
#   0x55 = char 0xB1 ('▒')   row 0 only (rows alternate 0x55/0xAA) — needs MaxSL=0 (1 scanline)
#
# 512-color mode uses the first 2 patterns (chars 0x55, 0x13) with the standard
# 80x100 cell timing (MaxSL=1) — "set and forget", static image.
# 1024-color mode uses ALL 4 patterns and requires the canonical mini-frames CRTC
# trick (per reenigne) to suppress row 1 of chars 0xB0/0xB1.
_TEXT_NTSC_PATTERNS_8 = [
    [1, 1, 0, 0, 1, 1, 0, 0],  # 0xCC → char 0x55 'U'
    [0, 1, 1, 0, 0, 1, 1, 0],  # 0x66 → char 0x13 '‼'
    [0, 0, 1, 0, 0, 0, 1, 0],  # 0x22 → char 0xB0 '░'
    [0, 1, 0, 1, 0, 1, 0, 1],  # 0x55 → char 0xB1 '▒'
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
    status_dbg('ENTER _quantize_rgb444()')
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


# ============================================================================
# 80x100 CENTERED 1024-color mode encoder
# ============================================================================
#
# Distinct from the legacy 80x100 (1024 Colors) mode (broken on MartyPC because
# it requires per-scanline mini-frames CRTC tricks). This centered variant uses
# a working two-frame CRTC technique (l100.asm style) and pairs of cells are
# encoded against the FULL composite simulation, considering every unique CGA
# top-row character pattern (not just the 4 hard-coded ones).
#
# Pipeline:
#   1) Build the set of unique top-row 8-bit patterns from the CGA ROM font
#      (~67 unique patterns vs 256 chars).
#   2) Build a "pair gamut LUT" per preset: average sRGB of every
#      (left_pattern, left_fg, left_bg, right_pattern, right_fg, right_bg)
#      combination, bucketed by quantized sRGB into a 3D coarse grid for fast
#      nearest-neighbor search.
#   3) Per cell-pair: compute the target color (16 pixels wide), apply
#      Floyd-Steinberg neighbor error subtraction, find candidates in
#      sRGB buckets around the target, score each via full composite-decode
#      perceptual distance, pick best.
#   4) Pack 4000 chosen pairs (= 8000 cells) into the 16000-byte VRAM image.


def _build_unique_top_row_patterns():
    """Return list of (row0_byte, sample_char) for each unique row-0 pattern.

    The encoder uses row 0 of each character glyph (because the centered
    mode runs at MaxSL=0 so only row 0 is ever shown). Two characters with
    the same row 0 are interchangeable — we keep one representative.
    """
    seen = {}
    for ch in range(256):
        r0 = _CGA_FONT[ch][0]
        if r0 not in seen:
            seen[r0] = ch
    return sorted(seen.items())  # [(row0_byte, char_code), ...]


_UNIQUE_TOP_ROW_PATTERNS_CACHE = None
def _get_unique_top_row_patterns():
    """Cached list of (row0_byte, sample_char) tuples."""
    global _UNIQUE_TOP_ROW_PATTERNS_CACHE
    if _UNIQUE_TOP_ROW_PATTERNS_CACHE is None:
        _UNIQUE_TOP_ROW_PATTERNS_CACHE = _build_unique_top_row_patterns()
    return _UNIQUE_TOP_ROW_PATTERNS_CACHE


def _pattern_pixels(row0_byte, fg, bg):
    """Expand a (row0, fg, bg) tuple to a list of 8 RGBI nibble values.
    Bit 7 of row0 is the leftmost pixel; 1 -> fg, 0 -> bg."""
    out = [0] * 8
    for i in range(8):
        bit = (row0_byte >> (7 - i)) & 1
        out[i] = (fg & 0x0F) if bit else (bg & 0x0F)
    return out


# ---- Perceptual color distance ----------------------------------------------

def _srgb_to_linear(c):
    """sRGB byte (0..255) -> linear float (0..1). Standard sRGB transfer curve."""
    s = c / 255.0
    if s <= 0.04045:
        return s / 12.92
    return ((s + 0.055) / 1.055) ** 2.4


def _linear_to_xyz(rgb_linear):
    """Linear sRGB -> CIE XYZ (D65)."""
    r, g, b = rgb_linear
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    return (x, y, z)


def _xyz_to_lab(xyz):
    """XYZ (D65) -> CIE L*a*b*."""
    xn, yn, zn = 0.95047, 1.00000, 1.08883
    x, y, z = xyz[0] / xn, xyz[1] / yn, xyz[2] / zn
    def f(t):
        return t ** (1.0 / 3.0) if t > 0.008856 else (7.787 * t + 16.0 / 116.0)
    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _rgb_byte_to_lab(rgb):
    """RGB byte tuple -> Lab tuple. Used for perceptual color distance."""
    lin = (_srgb_to_linear(rgb[0]), _srgb_to_linear(rgb[1]), _srgb_to_linear(rgb[2]))
    return _xyz_to_lab(_linear_to_xyz(lin))


def _delta_e_lab2(lab1, lab2):
    """Squared Euclidean distance in Lab space (delta-E*76 squared)."""
    dl = lab1[0] - lab2[0]
    da = lab1[1] - lab2[1]
    db = lab1[2] - lab2[2]
    return dl * dl + da * da + db * db


# ---- Single-cell gamut LUT --------------------------------------------------
#
# Pair-LUT would be ~92M entries (too big to enumerate). Instead we build a
# single-cell LUT (~9616 entries) and combine on the fly during search:
#   For each pair, find top-N candidates for each side via single-cell LUT,
#   then score every (left_cand × right_cand) pair combination through the
#   full composite decoder. With N≈8, that's only ~64 pair-candidates to score
#   per pair, ~256K total composite decodes per image.

_CELL_LUT_CACHE = {}
_CELL_LUT_QUANT_LEVELS = 8


def _build_cell_gamut_lut(preset_name):
    """Build single-cell LUT bucketed by quantized average sRGB.

    Returns dict with:
        'buckets': dict[(qr, qg, qb)] -> list[entry_index]
        'entries': list of dicts:
            'row0':     row-0 byte
            'char':     representative char code for this pattern
            'fg':       fg color (0..15)
            'bg':       bg color (0..15)
            'mean_rgb': isolated-cell mean output RGB (for bucketing only)
        'quant_levels': int
    """
    cache_key = (preset_name, _CELL_LUT_QUANT_LEVELS)
    if cache_key in _CELL_LUT_CACHE:
        return _CELL_LUT_CACHE[cache_key]

    status_dbg(f"Building single-cell gamut LUT for preset '{preset_name}'...")

    # Use the preset's full simulator config (matches the preview path).
    params = _COMPOSITE_PRESETS.get(preset_name, _COMPOSITE_PRESETS["Old CGA"])
    hue, sat, bri, con, shp, new_cga_flag, cgamode = params
    composite = _ReCompositeContextPy()
    composite.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri,
                     contrast=con, sharpness=shp, new_cga=new_cga_flag)
    composite.update_cga16_color(int(cgamode))

    patterns = _get_unique_top_row_patterns()
    Q = _CELL_LUT_QUANT_LEVELS

    entries = []
    buckets = {}

    seen_cells = set()  # dedupe by (effective_row0, fg, bg)
    for (row0, ch) in patterns:
        for fg in range(16):
            for bg in range(16):
                # When fg == bg, all 8 pixels are identical → pattern irrelevant
                eff_row0 = row0 if fg != bg else 0
                eff_char = ch if fg != bg else 0
                key = (eff_row0, fg, bg)
                if key in seen_cells:
                    continue
                seen_cells.add(key)

                # Decode in isolation: pad to 16 pixels by surrounding with bg
                # to give the composite simulator a stable reference. The cell's
                # 8 pixels go in the middle.
                pad = [bg] * 4
                pixels = pad + _pattern_pixels(eff_row0, fg, bg) + pad
                pixels_rgb = composite.decode_scanline_rgba(0, pixels)
                # Take the middle 8 pixels (the actual cell output)
                mid = pixels_rgb[4:12]
                mean_r = sum(p[0] for p in mid) / 8.0
                mean_g = sum(p[1] for p in mid) / 8.0
                mean_b = sum(p[2] for p in mid) / 8.0
                mean_rgb = (mean_r, mean_g, mean_b)

                entry = {
                    'row0': eff_row0,
                    'char': eff_char,
                    'fg': fg,
                    'bg': bg,
                    'mean_rgb': mean_rgb,
                }
                idx = len(entries)
                entries.append(entry)

                qr = max(0, min(Q - 1, int(mean_r * Q / 256.0)))
                qg = max(0, min(Q - 1, int(mean_g * Q / 256.0)))
                qb = max(0, min(Q - 1, int(mean_b * Q / 256.0)))
                buckets.setdefault((qr, qg, qb), []).append(idx)

    status_dbg(f"  cell-LUT done: {len(entries)} unique cell configs, "
               f"{len(buckets)} buckets")

    result = {
        'buckets': buckets,
        'entries': entries,
        'quant_levels': Q,
    }
    _CELL_LUT_CACHE[cache_key] = result
    return result


def _find_candidate_cells(lut, target_rgb, min_count=8):
    """Find candidate cell entries near target_rgb in sRGB bucket space."""
    Q = lut['quant_levels']
    buckets = lut['buckets']
    qr = max(0, min(Q - 1, int(target_rgb[0] * Q / 256.0)))
    qg = max(0, min(Q - 1, int(target_rgb[1] * Q / 256.0)))
    qb = max(0, min(Q - 1, int(target_rgb[2] * Q / 256.0)))

    visited = set()
    out = []
    radius = 0
    while True:
        for dr in range(-radius, radius + 1):
            for dg in range(-radius, radius + 1):
                for db in range(-radius, radius + 1):
                    if abs(dr) != radius and abs(dg) != radius and abs(db) != radius:
                        continue
                    rr, gg, bb = qr + dr, qg + dg, qb + db
                    if not (0 <= rr < Q and 0 <= gg < Q and 0 <= bb < Q):
                        continue
                    key = (rr, gg, bb)
                    if key in visited:
                        continue
                    visited.add(key)
                    if key in buckets:
                        out.extend(buckets[key])
        if len(out) >= min_count:
            return out
        radius += 1
        if radius > Q:
            for v in buckets.values():
                out.extend(v)
            return out


# ---- Pair-grain encoder with FS dithering -----------------------------------

def _decode_batch_wN_border0_np(in_rgbi_batch, ct, sharpness, ri, rq, gi, gq, bi, bq):
    """Numpy-vectorized composite decoder for batches of arbitrary-width
    scanlines with border=0. Returns (N, w, 3) uint8 RGB.

    Width-agnostic generalization of the original w16 decoder. Verified
    bit-for-bit equivalent to _ReCompositeContextPy.decode_scanline_rgba(0,...)
    at widths 8, 12, 16, 24, 32, and 40 during development.

    in_rgbi_batch: (N, w) array of RGBI nibbles (int). w must be a multiple of 4.
    ct:            (1024,) int64 composite_table.
    sharpness, ri, rq, gi, gq, bi, bq: scalar simulator coefficients.
    """
    import numpy as np
    N, w = in_rgbi_batch.shape
    if w % 4 != 0:
        raise ValueError(f"width must be a multiple of 4, got {w}")

    temp = np.zeros((N, w + 10), dtype=np.int64)

    # Border samples at left edge: btab[(x+3)&3] for x=0..3 = ct indices [3,0,1,2]
    temp[:, 0] = ct[3]
    temp[:, 1] = ct[0]
    temp[:, 2] = ct[1]
    temp[:, 3] = ct[2]

    # First content sample uses (in[0], border=0, phase=3)
    temp[:, 4] = ct[(in_rgbi_batch[:, 0] << 2) | 3]

    # Middle samples: for x in 0..w-2, temp[5+x] = ct[(in[x]<<6)|(in[x+1]<<2)|(x&3)]
    a = in_rgbi_batch[:, :w-1]
    b = in_rgbi_batch[:, 1:w]
    x_phase = np.arange(w - 1, dtype=np.int64) & 3
    idx = (a << 6) | (b << 2) | x_phase[None, :]
    temp[:, 5:5 + w - 1] = ct[idx]

    # Last content sample uses (in[w-1], border=0, phase=3)
    temp[:, 5 + w - 1] = ct[(in_rgbi_batch[:, w-1] << 6) | 3]

    # Right edge border samples: btab[x&3] for x=0..4 = ct [0,1,2,3,0]
    temp[:, 5 + w + 0] = ct[0]
    temp[:, 5 + w + 1] = ct[1]
    temp[:, 5 + w + 2] = ct[2]
    temp[:, 5 + w + 3] = ct[3]
    temp[:, 5 + w + 4] = ct[0]

    # atemp/btemp via FIR-like windows
    i_range = np.arange(4, 4 + w + 2, dtype=np.int64)
    atemp = (temp[:, i_range - 4]
             - ((temp[:, i_range - 2] - temp[:, i_range] + temp[:, i_range + 2]) << 1)
             + temp[:, i_range + 4])
    btemp = (temp[:, i_range - 3] - temp[:, i_range - 1]
             + temp[:, i_range + 1] - temp[:, i_range + 3]) << 1

    # In-place temp transforms
    temp[:, 4] = (temp[:, 4] << 3) - atemp[:, 0]
    temp[:, 5] = (temp[:, 5] << 3) - atemp[:, 1]
    iw = np.arange(6, 5 + w + 1, dtype=np.int64)
    aw = iw - 4
    temp[:, iw] = (temp[:, iw] << 3) - atemp[:, aw]

    # Output computation, vectorized over all w pixels
    out_pixel_idx = np.arange(w, dtype=np.int64)
    i_for = 5 + out_pixel_idx
    ap_for = 1 + out_pixel_idx

    c_arr = 2 * temp[:, i_for]
    d_arr = temp[:, i_for - 1] + temp[:, i_for + 1]
    y_arr = ((c_arr + d_arr) << 8) + sharpness * (c_arr - d_arr)
    a_arr = atemp[:, ap_for]
    b_arr = btemp[:, ap_for]

    # Per-pixel rot determines how a/b multiplex into the I/Q axes
    mult_a_ri = np.zeros(w, dtype=np.int64)
    mult_b_ri = np.zeros(w, dtype=np.int64)
    mult_a_rq = np.zeros(w, dtype=np.int64)
    mult_b_rq = np.zeros(w, dtype=np.int64)
    for pix in range(w):
        r = pix & 3
        if r == 0:
            mult_a_ri[pix], mult_b_ri[pix] = 1, 0
            mult_a_rq[pix], mult_b_rq[pix] = 0, 1
        elif r == 1:
            mult_a_ri[pix], mult_b_ri[pix] = 0, -1
            mult_a_rq[pix], mult_b_rq[pix] = 1, 0
        elif r == 2:
            mult_a_ri[pix], mult_b_ri[pix] = -1, 0
            mult_a_rq[pix], mult_b_rq[pix] = 0, -1
        else:
            mult_a_ri[pix], mult_b_ri[pix] = 0, 1
            mult_a_rq[pix], mult_b_rq[pix] = -1, 0

    a_term = mult_a_ri[None, :] * a_arr + mult_b_ri[None, :] * b_arr
    b_term = mult_a_rq[None, :] * a_arr + mult_b_rq[None, :] * b_arr

    rr = y_arr + ri * a_term + rq * b_term
    gg = y_arr + gi * a_term + gq * b_term
    bb = y_arr + bi * a_term + bq * b_term

    rr_out = np.clip(rr >> 13, 0, 255).astype(np.uint8)
    gg_out = np.clip(gg >> 13, 0, 255).astype(np.uint8)
    bb_out = np.clip(bb >> 13, 0, 255).astype(np.uint8)

    return np.stack([rr_out, gg_out, bb_out], axis=-1)


def _decode_batch_w16_border0_np(in_rgbi_batch, ct, sharpness, ri, rq, gi, gq, bi, bq):
    """Width-16 wrapper for backwards compatibility with cell-LUT builder."""
    if in_rgbi_batch.shape[1] != 16:
        raise ValueError(f"This wrapper requires width 16, got {in_rgbi_batch.shape[1]}")
    return _decode_batch_wN_border0_np(in_rgbi_batch, ct, sharpness, ri, rq, gi, gq, bi, bq)


def _rgb_array_to_lab(rgb_uint8):
    """Vectorized RGB-byte -> Lab conversion. Input shape (..., 3) uint8.
    Output shape (..., 3) float64 (L, a, b). Matches _rgb_byte_to_lab elementwise.

    Uses a precomputed 256-entry sRGB linearization table (built lazily on first
    call) for ~2× speedup over the elementwise np.where(...power...) form.
    """
    import numpy as np
    global _SRGB_LIN_TABLE
    if _SRGB_LIN_TABLE is None:
        s = np.arange(256, dtype=np.float64) / 255.0
        _SRGB_LIN_TABLE = np.where(
            s <= 0.04045, s / 12.92, np.power((s + 0.055) / 1.055, 2.4))

    lin = _SRGB_LIN_TABLE[rgb_uint8]  # (..., 3)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]

    # Linear RGB → XYZ (D65, sRGB)
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b

    xn, yn, zn = 0.95047, 1.00000, 1.08883
    fx = np.where(x / xn > 0.008856,
                  np.cbrt(x / xn),
                  7.787 * (x / xn) + 16.0 / 116.0)
    fy = np.where(y / yn > 0.008856,
                  np.cbrt(y / yn),
                  7.787 * (y / yn) + 16.0 / 116.0)
    fz = np.where(z / zn > 0.008856,
                  np.cbrt(z / zn),
                  7.787 * (z / zn) + 16.0 / 116.0)

    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    bL = 200.0 * (fy - fz)
    return np.stack([L, a, bL], axis=-1)


_SRGB_LIN_TABLE = None  # lazily initialized in _rgb_array_to_lab


def _build_all_candidates_array(preset_name):
    """Enumerate ALL 9,616 distinct cell configurations and return:
        - pixels:    (N, 8) int8 array of RGBI nibbles per candidate
        - chars:     (N,) int array of representative CGA char codes
        - attrs:     (N,) int array of CGA attribute bytes  ((bg<<4)|fg)
        - fgs:       (N,) int array of fg values (0..15)
        - bgs:       (N,) int array of bg values (0..15)

    Distinct configurations dedupe the fg==bg case (where the pattern is
    irrelevant — all 8 pixels are the same). For fg==bg we always use
    char=0x00 (space) and row0=0 so the cell renders as a solid attr block.
    """
    import numpy as np
    patterns = _get_unique_top_row_patterns()  # list of (row0_byte, sample_char)

    pixels_list = []
    chars_list = []
    attrs_list = []
    fgs_list = []
    bgs_list = []

    seen = set()
    for row0, ch in patterns:
        for fg in range(16):
            for bg in range(16):
                # Dedupe fg==bg: pattern doesn't matter when fg==bg, so only keep
                # one entry for each fg==bg (with row0=0, char=0).
                if fg == bg:
                    eff_row0 = 0
                    eff_char = 0
                else:
                    eff_row0 = row0
                    eff_char = ch
                key = (eff_row0, fg, bg)
                if key in seen:
                    continue
                seen.add(key)
                pix = _pattern_pixels(eff_row0, fg, bg)
                pixels_list.append(pix)
                chars_list.append(eff_char)
                attrs_list.append(((bg & 0x0F) << 4) | (fg & 0x0F))
                fgs_list.append(fg)
                bgs_list.append(bg)

    return (
        np.asarray(pixels_list, dtype=np.int64),
        np.asarray(chars_list, dtype=np.int64),
        np.asarray(attrs_list, dtype=np.int64),
        np.asarray(fgs_list, dtype=np.int64),
        np.asarray(bgs_list, dtype=np.int64),
    )


_ALL_CANDIDATES_CACHE = {}
def _get_all_candidates(preset_name):
    if preset_name in _ALL_CANDIDATES_CACHE:
        return _ALL_CANDIDATES_CACHE[preset_name]
    result = _build_all_candidates_array(preset_name)
    _ALL_CANDIDATES_CACHE[preset_name] = result
    return result


def encode_image_to_80x100_centered_1024(image_rgb_80x100, preset_name,
                                         dither_strength=1.0,
                                         candidates_per_side=8,  # kept for API compat; unused
                                         progress_cb=None,
                                         row_cb=None,
                                         cancel_event=None,
                                         chroma_lowpass=False):
    """Encode an image into 8000 (char, attr) cell tuples for the centered
    80x100 (1024-color) mode, using EXHAUSTIVE-SEARCH sliding-window encoding.

    Source sampling resolution: 640x100. This is the full horizontal resolution
    of the composite-decoded output (each cell decodes to 8 distinct output
    pixels, so 80 cells × 8 = 640 horizontal samples per row). Sampling at 640
    means the encoder optimizes for per-pixel luma and chroma matches across
    the entire decoded scanline — not just the cell-mean.

    Argument name `image_rgb_80x100` is preserved for API compatibility, but
    the image is now resized to 640x100 internally if it isn't already.

    Algorithm:
        For each cell N:
          - Build 16-pixel batch = [committed left cell's 8 pixels] + [candidate's 8 pixels]
          - For each of ~9,616 candidates, decode 16 pixels and take right 8.
          - Score per-pixel Lab² distance against target's 8 source pixels for cell N.
          - Pick argmin, commit, update left context, distribute cell-grain FS error.

    Args:
        image_rgb_80x100: PIL Image or array; resized to 640x100 if needed.
        preset_name: "Old CGA" or "New CGA".
        dither_strength: 0..1 multiplier on Floyd-Steinberg error diffusion.
        candidates_per_side: kept for API compatibility; ignored.
        progress_cb: optional callable(percent_done_0_to_100).
        row_cb: optional callable(row_index, cells_so_far_list).
        cancel_event: optional threading.Event for cooperative cancellation.
        chroma_lowpass: when True, apply a 4-pixel-wide box low-pass to the
            chroma channels (a, b in Lab) of the target. Luma (L) is preserved
            at full per-pixel resolution. Motivation: composite chroma has a
            4-pixel kernel, so chroma details finer than 4 pixels cannot be
            reproduced by the hardware. Low-passing the target prevents the
            encoder from "chasing" un-reproducible chroma transitions and
            yields a cleaner perceptual score that focuses on what's actually
            achievable. Wired to the GUI "Match contrast / tone to palette"
            checkbox in the centered-mode convert path.

    Returns:
        list of 8000 (char_byte, attr_byte) tuples in row-major order.
    """
    import numpy as np
    from PIL import Image

    # ---- Normalize input to 640x100 ----
    TARGET_W = 640
    TARGET_H = 100
    if hasattr(image_rgb_80x100, 'size'):
        if image_rgb_80x100.size != (TARGET_W, TARGET_H):
            image_rgb_80x100 = image_rgb_80x100.resize(
                (TARGET_W, TARGET_H), Image.LANCZOS)
        img = image_rgb_80x100.convert("RGB")
        target_rgb_np = np.asarray(img, dtype=np.uint8)  # (100, 640, 3)
    else:
        target_rgb_np = np.asarray(image_rgb_80x100, dtype=np.uint8)
        if target_rgb_np.shape[:2] != (TARGET_H, TARGET_W):
            raise ValueError(
                f"Expected (100, 640, 3) source, got {target_rgb_np.shape}. "
                f"Pass a PIL Image to auto-resize."
            )

    # Target Lab per pixel: (100, 640, 3)
    target_lab_np = _rgb_array_to_lab(target_rgb_np)

    # Optional chroma low-pass: 4-pixel box filter on a, b channels only.
    # Preserves L at full resolution. Approximates the composite chroma kernel.
    if chroma_lowpass:
        # Box filter of width 4 along the horizontal axis on channels [1, 2] = a, b.
        # Implementation: cumulative sum trick for fast, exact box average.
        ab = target_lab_np[:, :, 1:3]  # (100, 640, 2)
        # Pad each row with a 2-wide reflect/edge so the filter centers at each pixel
        pad = 2
        ab_padded = np.pad(ab, ((0, 0), (pad, pad), (0, 0)), mode='edge')
        # 4-wide running mean using cumsum: average of [i-1, i, i+1, i+2] (4 samples)
        # Simpler: use a sliding window via numpy. For each output position i,
        # take mean of positions i-1, i, i+1, i+2 from input (i ranges 0..639).
        # That's mean of ab_padded[i+1:i+5] in the padded array.
        # Use cumsum:
        csum = np.cumsum(ab_padded, axis=1, dtype=np.float64)
        # Sum of window [i+1:i+5] = csum[i+5-1] - csum[i+1-1] = csum[i+4] - csum[i]
        # Need csum prepended with 0 to handle i=0 cleanly:
        csum_pre = np.concatenate(
            [np.zeros((csum.shape[0], 1, csum.shape[2]), dtype=csum.dtype), csum],
            axis=1
        )
        # Now sum of window starting at padded-index s of width 4 = csum_pre[s+4] - csum_pre[s]
        # For output pixel i, window starts at s=i+1 (one pixel before center to center+2)
        # Actually the cleanest way: window [i-1, i, i+1, i+2] in original i means
        # padded indices [i+1, i+2, i+3, i+4]. Sum = csum_pre[i+5] - csum_pre[i+1]
        i_range = np.arange(TARGET_W)
        win_sum = csum_pre[:, i_range + 5, :] - csum_pre[:, i_range + 1, :]
        ab_filtered = win_sum / 4.0
        # Replace a, b channels; keep L
        target_lab_np = np.concatenate(
            [target_lab_np[:, :, 0:1], ab_filtered], axis=2
        )

    # ---- Simulator config ----
    params = _COMPOSITE_PRESETS.get(preset_name, _COMPOSITE_PRESETS["Old CGA"])
    hue, sat, bri, con, shp, new_cga_flag, cgamode = params
    ctx = _ReCompositeContextPy()
    ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri,
               contrast=con, sharpness=shp, new_cga=new_cga_flag)
    ctx.update_cga16_color(int(cgamode))
    ct = np.asarray(ctx.composite_table, dtype=np.int64)
    sharpness = ctx.video_sharpness
    ri, rq = ctx.video_ri, ctx.video_rq
    gi, gq = ctx.video_gi, ctx.video_gq
    bi, bq = ctx.video_bi, ctx.video_bq

    # ---- Enumerate all candidates ----
    cand_pixels, cand_chars, cand_attrs, cand_fgs, cand_bgs = _get_all_candidates(preset_name)
    N_CAND = cand_pixels.shape[0]
    status_dbg(
        f"Sliding-window encoder (640×100 source, "
        f"chroma_lowpass={chroma_lowpass}): "
        f"{N_CAND} candidates × {80*100} cells = ~{N_CAND * 80 * 100:,} decodes"
    )

    # ---- FS error accumulator: cell-grain (80×100), Lab space ----
    err = np.zeros((100, 80, 3), dtype=np.float64)

    out_cells = [(0, 0)] * (80 * 100)

    # ---- Precompute right-lookahead context ----
    # For each cell N, the chroma kernel at the right edge of cell N pulls in
    # ~5 pixels from cell N+1. Without context there, the simulator decodes
    # cell N's right edge against zero-padded (black border) input, which is
    # WRONG on hardware (where cell N+1's actual pixels are there). The
    # encoder then optimizes for an unrealistic right neighborhood and the
    # COM output bleeds wrong colors at transitions.
    #
    # Fix: provide a "best guess" for cell N+1's pixels by quantizing the
    # source image's pixels at cell N+1's position to the nearest of the 16
    # CGA RGBI colors. We don't commit those pixels — they're just there to
    # give the simulator a realistic right neighborhood while scoring cell N.
    # When we move to cell N+1, we'll do the real exhaustive search.
    cga_rgb_np = np.array(CGA_COLORS, dtype=np.int64)  # (16, 3)
    # Squared distance from each source pixel to each of the 16 CGA colors.
    # target_rgb_np: (100, 640, 3), cga_rgb_np: (16, 3)
    # Reshape source to (100, 640, 1, 3); broadcast difference: (100, 640, 16, 3)
    src_int = target_rgb_np.astype(np.int64)
    color_diffs = src_int[:, :, None, :] - cga_rgb_np[None, None, :, :]
    color_sqd = (color_diffs * color_diffs).sum(axis=-1)  # (100, 640, 16)
    source_rgbi = color_sqd.argmin(axis=-1).astype(np.int64)  # (100, 640)

    # ---- Batch: width 24 = [left_context_8] + [candidate_8] + [right_lookahead_8] ----
    # We score the MIDDLE 8 pixels (positions 8..15) of the decode against
    # the target. The right 8 (positions 16..23) are the lookahead — used
    # ONLY to give the simulator realistic right-side input so the middle
    # decode reflects what cell N will actually look like on hardware.
    BATCH_W = 24
    batch = np.zeros((N_CAND, BATCH_W), dtype=np.int64)
    batch[:, 8:16] = cand_pixels  # middle: candidates (constant across cells)

    total_cells = 80 * 100
    cells_done = 0
    report_every = 200

    # ---- Main loop ----
    for y in range(100):
        if cancel_event is not None and cancel_event.is_set():
            return out_cells

        left_context = np.zeros(8, dtype=np.int64)

        for x in range(80):
            # Per-cell cancellation check (every 10 cells)
            if (x % 10 == 0) and cancel_event is not None and cancel_event.is_set():
                return out_cells

            # Target: 8 distinct per-pixel Lab values from the 640-wide source.
            tgt_lab_8 = target_lab_np[y, x * 8:(x + 1) * 8, :] + err[y, x, :][None, :]

            # Build batch input: left context + candidate + right lookahead.
            batch[:, :8] = left_context[None, :]
            if x < 79:
                # Lookahead = nearest-CGA quantization of source at cell N+1's position.
                # This gives the simulator a realistic right neighborhood.
                lookahead = source_rgbi[y, (x + 1) * 8:(x + 2) * 8]
                batch[:, 16:24] = lookahead[None, :]
            else:
                # Last cell: no cell N+1. Hardware has horizontal blanking here
                # which acts like a black/border region. Use zeros.
                batch[:, 16:24] = 0

            decoded = _decode_batch_wN_border0_np(
                batch, ct, sharpness, ri, rq, gi, gq, bi, bq)
            # Score the MIDDLE 8 pixels — those are cell N's actual output.
            middle_decoded = decoded[:, 8:16, :]  # (N_CAND, 8, 3)

            middle_lab = _rgb_array_to_lab(middle_decoded)

            # Per-pixel Lab² distance
            diff = middle_lab - tgt_lab_8[None, :, :]
            score = np.einsum('npc,npc->n', diff, diff)

            best_idx = int(np.argmin(score))

            ch = int(cand_chars[best_idx])
            attr = int(cand_attrs[best_idx])
            out_cells[y * 80 + x] = (ch, attr)

            left_context = cand_pixels[best_idx]

            # Cell-grain FS error.
            best_lab = middle_lab[best_idx]  # (8, 3)
            residual = (tgt_lab_8 - best_lab).mean(axis=0)
            rr_vec = residual * dither_strength

            if x + 1 < 80:
                err[y, x + 1, :] += rr_vec * (7.0 / 16.0)
            if y + 1 < 100:
                if x - 1 >= 0:
                    err[y + 1, x - 1, :] += rr_vec * (3.0 / 16.0)
                err[y + 1, x, :] += rr_vec * (5.0 / 16.0)
                if x + 1 < 80:
                    err[y + 1, x + 1, :] += rr_vec * (1.0 / 16.0)

            cells_done += 1
            if progress_cb and (cells_done % report_every == 0):
                progress_cb(cells_done * 100 // total_cells)

        if row_cb is not None:
            try:
                row_cb(y, out_cells)
            except Exception:
                pass

    return out_cells


def encode_image_to_80x100_centered_1024_viterbi(image_rgb_80x100, preset_name,
                                                  k_candidates=64,
                                                  dither_strength=1.0,
                                                  progress_cb=None,
                                                  row_cb=None,
                                                  cancel_event=None,
                                                  chroma_lowpass=False):
    """Per-row Viterbi DP encoder for the 640x100 → 80x100 (1024 colors) mode.

    Unlike the sliding-window encoder (which commits cells greedily, left-to-right,
    one at a time), this finds the GLOBALLY OPTIMAL row encoding within a pruned
    candidate set per cell. The trade-off is:
      - PRUNING: each cell position is restricted to its top K candidates (by
        mean-color distance to the local target). K=64 by default. Candidates
        outside this top-K are never considered, regardless of context.
      - OPTIMALITY: subject to that pruning, the per-row encoding minimizes the
        sum of per-pixel Lab² distances across all 640 pixels of the row,
        accounting for the chroma kernel's bidirectional context dependency.

    Algorithm (per row):
      1. Precompute per-cell pruned candidate sets: cands[N] = top K candidates
         for cell N, ranked by source-target color match.
      2. Forward Viterbi pass: best_score[N][i] = min total score for any path
         ending at candidate i in cell N. Computed as
            best_score[N][i] = min over j (
              best_score[N-1][j] + transition_cost(j_pixels, i_pixels, N)
            )
         where transition_cost decodes a 24-pixel batch [j | i | naive_lookahead]
         and scores the middle 8 against target.
      3. Backward trace: pick the candidate at position 79 with minimum total
         score, walk back via best_prev pointers.

    Vertical FS error diffusion still applies (cross-row), so this encoder
    operates row-by-row and accumulates Lab error vertically. Horizontal FS
    within a row is OFF because Viterbi already globally optimizes the row.

    Args: same as encode_image_to_80x100_centered_1024 plus:
        k_candidates: pruning width per cell. Larger = closer to global optimum
            but proportionally slower (K² transitions per position).

    Returns: list of 8000 (char, attr) tuples.
    """
    import numpy as np
    from PIL import Image

    # ---- Normalize input ----
    TARGET_W = 640
    TARGET_H = 100
    if hasattr(image_rgb_80x100, 'size'):
        if image_rgb_80x100.size != (TARGET_W, TARGET_H):
            image_rgb_80x100 = image_rgb_80x100.resize(
                (TARGET_W, TARGET_H), Image.LANCZOS)
        img = image_rgb_80x100.convert("RGB")
        target_rgb_np = np.asarray(img, dtype=np.uint8)
    else:
        target_rgb_np = np.asarray(image_rgb_80x100, dtype=np.uint8)
        if target_rgb_np.shape[:2] != (TARGET_H, TARGET_W):
            raise ValueError(
                f"Expected (100, 640, 3) source, got {target_rgb_np.shape}."
            )

    target_lab_np = _rgb_array_to_lab(target_rgb_np)

    # Optional chroma low-pass on a, b channels
    if chroma_lowpass:
        ab = target_lab_np[:, :, 1:3]
        ab_padded = np.pad(ab, ((0, 0), (2, 2), (0, 0)), mode='edge')
        csum = np.cumsum(ab_padded, axis=1, dtype=np.float64)
        csum_pre = np.concatenate(
            [np.zeros((csum.shape[0], 1, csum.shape[2]), dtype=csum.dtype), csum],
            axis=1
        )
        i_range = np.arange(TARGET_W)
        win_sum = csum_pre[:, i_range + 5, :] - csum_pre[:, i_range + 1, :]
        ab_filtered = win_sum / 4.0
        target_lab_np = np.concatenate(
            [target_lab_np[:, :, 0:1], ab_filtered], axis=2
        )

    # ---- Simulator config ----
    params = _COMPOSITE_PRESETS.get(preset_name, _COMPOSITE_PRESETS["Old CGA"])
    hue, sat, bri, con, shp, new_cga_flag, cgamode = params
    ctx = _ReCompositeContextPy()
    ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri,
               contrast=con, sharpness=shp, new_cga=new_cga_flag)
    ctx.update_cga16_color(int(cgamode))
    ct = np.asarray(ctx.composite_table, dtype=np.int64)
    sharpness = ctx.video_sharpness
    ri, rq = ctx.video_ri, ctx.video_rq
    gi, gq = ctx.video_gi, ctx.video_gq
    bi, bq = ctx.video_bi, ctx.video_bq

    cand_pixels, cand_chars, cand_attrs, cand_fgs, cand_bgs = _get_all_candidates(preset_name)
    N_CAND_TOTAL = cand_pixels.shape[0]
    K = min(int(k_candidates), N_CAND_TOTAL)

    status_dbg(
        f"Viterbi encoder (K={K}): per-row DP with pruning. "
        f"Total candidate cells: {N_CAND_TOTAL}; transitions/position = {K*K}."
    )

    # ---- Precompute each candidate's MEAN decoded color ----
    # Used for cheap per-cell pruning. Decode each candidate in isolation
    # (black left and right context) once at startup; store the mean Lab.
    # This is a one-time cost.
    iso_batch = np.zeros((N_CAND_TOTAL, 24), dtype=np.int64)
    iso_batch[:, 8:16] = cand_pixels  # candidate in middle; left+right = 0
    iso_decoded = _decode_batch_wN_border0_np(
        iso_batch, ct, sharpness, ri, rq, gi, gq, bi, bq)  # (N, 24, 3)
    iso_middle = iso_decoded[:, 8:16, :]  # (N, 8, 3)
    iso_mean_rgb = iso_middle.mean(axis=1).astype(np.uint8)  # (N, 3)
    iso_mean_lab = _rgb_array_to_lab(iso_mean_rgb)  # (N, 3)

    # ---- Precompute right lookahead (nearest CGA for each source pixel) ----
    cga_rgb_np = np.array(CGA_COLORS, dtype=np.int64)
    src_int = target_rgb_np.astype(np.int64)
    color_diffs = src_int[:, :, None, :] - cga_rgb_np[None, None, :, :]
    color_sqd = (color_diffs * color_diffs).sum(axis=-1)
    source_rgbi = color_sqd.argmin(axis=-1).astype(np.int64)  # (100, 640)

    # ---- FS error accumulator: cell-grain vertical only ----
    err = np.zeros((100, 80, 3), dtype=np.float64)

    out_cells = [(0, 0)] * (80 * 100)

    total_rows = 100
    rows_done = 0

    # ---- Main per-row loop ----
    for y in range(100):
        if cancel_event is not None and cancel_event.is_set():
            return out_cells

        # ---- Step 1: pruning. For each cell position, find top-K candidates. ----
        # Pruning criterion: mean-color L² distance from candidate's isolated
        # decoded mean to the cell's source-target mean (with FS error baked in).
        # This is context-free, fast, robust.
        cell_target_means = np.zeros((80, 3), dtype=np.float64)
        for x in range(80):
            cell_target_means[x, :] = target_lab_np[y, x*8:(x+1)*8, :].mean(axis=0) + err[y, x, :]

        # Distance from each cell target mean to each candidate's mean Lab:
        # shape (80, N_CAND)
        cell_to_cand_diff = cell_target_means[:, None, :] - iso_mean_lab[None, :, :]
        cell_to_cand_dist = (cell_to_cand_diff * cell_to_cand_diff).sum(axis=-1)
        # Top-K candidates per cell (smallest distance)
        cell_top_k_indices = np.argpartition(cell_to_cand_dist, K-1, axis=1)[:, :K]  # (80, K)

        # ---- Step 2: Viterbi forward pass ----
        # best_score[N][i] = min total per-row score for a path ending at
        #                    candidate (cell_top_k_indices[N, i]) in cell N
        # best_prev[N][i]  = the i' that achieved this min at position N-1
        best_score = np.full((80, K), np.inf, dtype=np.float64)
        best_prev  = np.zeros((80, K), dtype=np.int32)

        # Position 0: no prior cell, black left context.
        # Build batch of K candidates with black left, black/lookahead right.
        cands_0 = cell_top_k_indices[0]  # (K,)
        batch_0 = np.zeros((K, 24), dtype=np.int64)
        batch_0[:, 8:16] = cand_pixels[cands_0]
        # Right lookahead for cell 0: source-quantized cell 1 pixels
        lookahead_for_0 = source_rgbi[y, 8:16]  # cell 1 source-quantized
        batch_0[:, 16:24] = lookahead_for_0[None, :]
        decoded_0 = _decode_batch_wN_border0_np(
            batch_0, ct, sharpness, ri, rq, gi, gq, bi, bq)  # (K, 24, 3)
        middle_0 = decoded_0[:, 8:16, :]  # (K, 8, 3)
        middle_0_lab = _rgb_array_to_lab(middle_0)
        tgt_0_lab = target_lab_np[y, 0:8, :] + err[y, 0, :][None, :]  # (8, 3)
        diff_0 = middle_0_lab - tgt_0_lab[None, :, :]
        score_0 = np.einsum('npc,npc->n', diff_0, diff_0)  # (K,)
        best_score[0, :] = score_0

        # Positions 1..79
        for x in range(1, 80):
            cands_curr = cell_top_k_indices[x]   # (K,) candidate indices at position x
            cands_prev = cell_top_k_indices[x-1] # (K,) candidate indices at position x-1

            # Right lookahead for cell x: cell (x+1)'s source-quantized pixels
            if x < 79:
                lookahead = source_rgbi[y, (x+1)*8:(x+2)*8]
            else:
                lookahead = np.zeros(8, dtype=np.int64)

            # Build a batch covering all K*K transitions at this position.
            # Layout: row [i*K + j] = transition from prev=j to curr=i
            # Batch shape: (K*K, 24)
            #   pos 0..7   = prev candidate j's pixels
            #   pos 8..15  = curr candidate i's pixels  
            #   pos 16..23 = lookahead
            prev_pixels = cand_pixels[cands_prev]  # (K, 8)
            curr_pixels = cand_pixels[cands_curr]  # (K, 8)
            # Broadcast: for each (i, j), prev = j's pixels, curr = i's pixels
            # Output [i*K + j] = (prev=j, curr=i)
            ii, jj = np.meshgrid(np.arange(K), np.arange(K), indexing='ij')
            batch_x = np.zeros((K*K, 24), dtype=np.int64)
            batch_x[:, 0:8] = prev_pixels[jj.ravel()]   # j's pixels in left slot
            batch_x[:, 8:16] = curr_pixels[ii.ravel()]  # i's pixels in middle slot
            batch_x[:, 16:24] = lookahead[None, :]

            decoded_x = _decode_batch_wN_border0_np(
                batch_x, ct, sharpness, ri, rq, gi, gq, bi, bq)  # (K*K, 24, 3)
            middle_x = decoded_x[:, 8:16, :]  # (K*K, 8, 3)
            middle_x_lab = _rgb_array_to_lab(middle_x)
            tgt_x_lab = target_lab_np[y, x*8:(x+1)*8, :] + err[y, x, :][None, :]
            diff_x = middle_x_lab - tgt_x_lab[None, :, :]
            trans_cost = np.einsum('npc,npc->n', diff_x, diff_x)  # (K*K,)
            # Reshape to (K, K) where [i, j] = transition cost from prev=j to curr=i
            trans_cost_matrix = trans_cost.reshape(K, K)

            # Compute best path to each curr i:
            #   best_score[x, i] = min over j of (best_score[x-1, j] + trans_cost[i, j])
            # Vectorized:
            #   totals[i, j] = best_score[x-1, j] + trans_cost[i, j]
            #   best_score[x, i] = min over j of totals[i, j]
            #   best_prev[x, i] = argmin over j of totals[i, j]
            totals = best_score[x-1, :][None, :] + trans_cost_matrix  # (K, K)
            best_prev[x, :] = np.argmin(totals, axis=1).astype(np.int32)
            best_score[x, :] = totals[np.arange(K), best_prev[x, :]]

        # ---- Step 3: backward trace ----
        final_best_i = int(np.argmin(best_score[79, :]))
        path = [0] * 80
        path[79] = final_best_i
        for x in range(78, -1, -1):
            path[x] = int(best_prev[x+1, path[x+1]])

        # Convert path (per-position indices into top_k) to chosen candidate indices
        chosen_cand_indices = [int(cell_top_k_indices[x, path[x]]) for x in range(80)]

        # Store row's cells and compute residuals for vertical FS error
        for x in range(80):
            ci = chosen_cand_indices[x]
            out_cells[y*80 + x] = (int(cand_chars[ci]), int(cand_attrs[ci]))

        # ---- Vertical-only FS error diffusion ----
        # Decode the row's chosen cells through the simulator to get actual
        # decoded Lab per cell, compute mean residual per cell, distribute
        # to row y+1 via FS kernel (3/16, 5/16, 1/16 — no 7/16 since that's
        # the horizontal-right neighbor which we don't want to propagate
        # within a row that's already globally optimized).
        if dither_strength > 0 and y + 1 < 100:
            # Decode the actual chosen row in one batch
            chosen_pixels_row = cand_pixels[np.array(chosen_cand_indices)]  # (80, 8)
            # Build full-row decoder input: 80 cells × 8 pixels = 640 pixels
            row_input = chosen_pixels_row.reshape(640)
            row_decoded = ctx.decode_scanline_rgba(0, row_input.tolist())  # 640 px
            row_decoded_np = np.array(row_decoded, dtype=np.uint8).reshape(80, 8, 3)
            row_decoded_lab = _rgb_array_to_lab(row_decoded_np)  # (80, 8, 3)

            for x in range(80):
                tgt_lab_8 = target_lab_np[y, x*8:(x+1)*8, :] + err[y, x, :][None, :]
                residual = (tgt_lab_8 - row_decoded_lab[x]).mean(axis=0)
                rr_vec = residual * dither_strength
                # Distribute only to y+1 (vertical-only diffusion)
                if x - 1 >= 0:
                    err[y + 1, x - 1, :] += rr_vec * (3.0 / 16.0)
                err[y + 1, x, :] += rr_vec * (5.0 / 16.0)
                if x + 1 < 80:
                    err[y + 1, x + 1, :] += rr_vec * (1.0 / 16.0)

        rows_done += 1
        if progress_cb:
            progress_cb(rows_done * 100 // total_rows)
        if row_cb is not None:
            try:
                row_cb(y, out_cells)
            except Exception:
                pass

    return out_cells


def convert_text_ntsc_chosen_to_cells(chosen):
    """Convert legacy 4-pattern 'chosen' list of (fg, bg, pat, swap) tuples
    into the list of (char, attr) tuples expected by
    pack_text_80x100_centered_1024color.

    This is the bridge between the existing 4-pattern LUT pipeline (used by
    the legacy 512/1024 modes and by the "smooth preview" path) and the new
    centered builder, which takes (char, attr) cells regardless of how they
    were chosen. Pattern->char mapping mirrors pack_text_80x100_1024color.
    """
    if len(chosen) != 80 * 100:
        raise ValueError(f"chosen must have 8000 entries, got {len(chosen)}")

    PATTERN_CC = [1, 1, 0, 0, 1, 1, 0, 0]
    PATTERN_66 = [0, 1, 1, 0, 0, 1, 1, 0]
    PATTERN_22 = [0, 0, 1, 0, 0, 0, 1, 0]
    PATTERN_55 = [0, 1, 0, 1, 0, 1, 0, 1]

    out = []
    for fg, bg, pat, swap in chosen:
        pat_list = list(pat)
        if pat_list == PATTERN_CC:
            char_code = 0x55
        elif pat_list == PATTERN_66:
            char_code = 0x13
        elif pat_list == PATTERN_22:
            char_code = 0xB0
        elif pat_list == PATTERN_55:
            char_code = 0xB1
        else:
            char_code = 0x55  # fallback; shouldn't happen with the 4k LUT

        if swap:
            fg_out, bg_out = bg, fg
        else:
            fg_out, bg_out = fg, bg
        attr = ((bg_out & 0x0F) << 4) | (fg_out & 0x0F)
        out.append((char_code, attr))
    return out


# ---- VRAM packer (centered 1024 mode uses byte-rotated layout) -------------

def pack_text_80x100_centered_1024color(cells_8000):
    """Pack 8000 (char, attr) cell tuples into the 16320-byte VRAM data block
    used by the centered builder.

    The L100V4 builder copies 8160 words (16320 bytes) from CS:data to B800:0
    and sets CRTC start address to word 0x1F40 (= byte 16000). Display reads:
        bytes 16000..16319 (320 bytes = 2 rows of image) from end of buffer,
        then wraps to bytes 0..15679 (15680 bytes = 98 more rows).

    So image row 0 -> bytes 16000..16159 of buffer
       image row 1 -> bytes 16160..16319 of buffer
       image rows 2..99 -> bytes 0..15679 of buffer (row R at byte (R-2)*160)
       bytes 15680..16319 of buffer are after rows 0..1 displayed - wait let me redo this.

    Actually: VRAM[16000] is FIRST byte displayed (top-left of image).
    So image row 0 at VRAM bytes 16000..16159 (80 cells × 2 bytes).
    Image row 1 at VRAM bytes 16160..16319 (next 160 bytes).
    Image row 2 at VRAM bytes 0..159 (wrapped).
    Image row 99 at VRAM bytes 15520..15679.
    VRAM bytes 15680..15999 = 320 bytes = NEVER displayed (filler).
    """
    if len(cells_8000) != 8000:
        raise ValueError(f"expected 8000 cells, got {len(cells_8000)}")

    buf = bytearray(16320)

    # Rows 0..1 at buf[16000..16319]
    for row in range(2):
        for col in range(80):
            ch, at = cells_8000[row * 80 + col]
            base = 16000 + row * 160 + col * 2
            buf[base] = ch & 0xFF
            buf[base + 1] = at & 0xFF

    # Rows 2..99 at buf[0..15679]
    for row in range(2, 100):
        for col in range(80):
            ch, at = cells_8000[row * 80 + col]
            base = (row - 2) * 160 + col * 2
            buf[base] = ch & 0xFF
            buf[base + 1] = at & 0xFF

    return bytes(buf)


def build_com_text_80x100_centered_1024color(buffer_16320):
    """Build a standalone DOS .COM that displays an 80x100 image vertically
    centered on screen using the L100V4-verified CRTC technique.

    Args:
        buffer_16320: exactly 16320 bytes of VRAM data as packed by
            pack_text_80x100_centered_1024color.

    Returns:
        bytes — the .COM file contents.
    """
    if len(buffer_16320) != 16320:
        raise ValueError(f"buffer must be 16320 bytes, got {len(buffer_16320)}")

    code = bytearray()
    code += bytes([0x0E, 0x1F])
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])
    code += bytes([0xB9, 0xE0, 0x1F])
    si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])
    code += bytes([0x31, 0xFF])
    code += bytes([0xFC, 0xF3, 0xA5])
    code += bytes([0x31, 0xC0, 0xAB])

    code += bytes([0xBA, 0xD8, 0x03, 0xB0, 0x01, 0xEE])

    crtc_init = [
        (0x00, 0x71), (0x01, 0x50), (0x02, 0x5A),
        (0x03, 0x0A),
        (0x04, 0x63), (0x05, 0x00), (0x06, 0x64), (0x07, 0x7F),
        (0x08, 0x02), (0x09, 0x00), (0x0A, 0x00), (0x0B, 0x00),
        (0x0C, 0x00), (0x0D, 0x00), (0x0E, 0x1F), (0x0F, 0xFF),
    ]
    for reg, val in crtc_init:
        code += bytes([0xBA, 0xD4, 0x03])
        code += bytes([0xB0, reg, 0xEE])
        code += bytes([0x42, 0xB0, val, 0xEE])

    code += bytes([0xBA, 0xD8, 0x03, 0xB0, 0x09, 0xEE])
    code += bytes([0x42, 0xB0, 0x00, 0xEE])

    code += bytes([0xFA])
    code += bytes([0xB2, 0xDA])
    code += bytes([0xB9, 0x00, 0x00])

    # NOTE on keypress handling: We tried multiple approaches (port 0x60/0x64
    # drain loops at startup, BIOS int 16h drain, single port 0x60 read).
    # All variants either break the CRTC two-frame switching on MartyPC OR
    # fail to consume the initial Enter-key scancode. So we use the simplest
    # working solution: pure frame counter, no keypress polling. The COM
    # displays for ~5 seconds (300 frames @ 60Hz) and auto-exits.

    frame_loop_off = len(code)

    code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])
    code += bytes([0xB2, 0xD4])
    for reg, val in [(0x09, 0x00), (0x04, 0x63), (0x06, 0x64),
                     (0x07, 0x7F), (0x0C, 0x1F), (0x0D, 0x40)]:
        word = (val << 8) | reg
        code += bytes([0xB8, word & 0xFF, (word >> 8) & 0xFF, 0xEF])
    code += bytes([0xB2, 0xDA])
    code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])

    for _ in range(99):
        code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])
        code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])

    code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])
    code += bytes([0xB2, 0xD4])
    # NOTE on ordering: tried writing R6=0 (VDisp) FIRST to gate display off
    # immediately and eliminate a thin scanline of stray VRAM content at
    # bottom of image. But that broke vsync detection — when VDisp=0 hits
    # before VTotal updates, CRTC state machine doesn't fire vsync cleanly
    # and the frame loop hangs in waitForVerticalSync.
    # R9 (MaxSL) first matches reenigne's original code and lets vsync work.
    # Accept the thin scanline defect; can revisit later if it matters.
    for reg, val in [(0x09, 0x01), (0x06, 0x00), (0x07, 0x25), (0x04, 0x50)]:
        word = (val << 8) | reg
        code += bytes([0xB8, word & 0xFF, (word >> 8) & 0xFF, 0xEF])
    code += bytes([0xB8, 0x0C, 0x00, 0xEF])
    code += bytes([0x40, 0xEF])
    code += bytes([0xB2, 0xDA])
    code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])

    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])

    # ---- Frame counter exit (300 frames = 5 sec @ 60Hz) ----
    # 300 = 0x012C, little-endian = 2C 01
    code += bytes([0x41])                          # inc cx
    code += bytes([0x81, 0xF9, 0x2C, 0x01])        # cmp cx, 300
    code += bytes([0x74, 0x03])                    # jz +3 → exit
    rel = frame_loop_off - (len(code) + 3)
    rel16 = rel & 0xFFFF
    code += bytes([0xE9, rel16 & 0xFF, (rel16 >> 8) & 0xFF])  # jmp frame_loop

    # exit:
    code += bytes([0xFB])                          # sti
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    code += bytes([0xB4, 0x4C, 0xCD, 0x21])

    data_off = 0x100 + len(code)
    code[si_patch] = data_off & 0xFF
    code[si_patch + 1] = (data_off >> 8) & 0xFF
    return bytes(code) + buffer_16320


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
    status_dbg('ENTER _error_diffusion_dither()')
    intensity = 0.0 if intensity < 0.0 else 1.0 if intensity > 1.0 else float(intensity)

    w, h = image.size
    buf = [[[float(c) for c in image.getpixel((x, y))]
            for x in range(w)] for y in range(h)]
    indices = [0] * (w * h)

    def clamp255(v):
        return 0.0 if v < 0.0 else 255.0 if v > 255.0 else v

    for y in range(h):
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

_SIERRA_LITE_KERNEL = [
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
    return _error_diffusion_dither(image, palette, _SIERRA_LITE_KERNEL, 4, intensity=intensity, serpentine=True)





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

            # Determine fg/bg using the SAME convention as the quantizer:
            # most-common index in the cell = FG (matches quantize_char16_textblock_from_indices)
            counts = {}
            for v in block:
                counts[v] = counts.get(v, 0) + 1
            items = sorted(counts.items(), key=lambda t: t[1], reverse=True)
            fg = items[0][0] & 0x0F
            bg = fg
            if len(items) > 1:
                bg = items[1][0] & 0x0F

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




def build_com_text_80x100_512color(char_attr_16000: bytes) -> bytes:
    """Build a DOS .COM that displays an 80x100 NTSC-text-trick 512-color image
    on a real CGA card with composite output.
    
    The 512-color trick (per reenigne and VileR, used in 8088 MPH):
      - Set BIOS text mode 03h (80x25 color)
      - Disable blink (so attribute bit 7 selects bright BG instead of blink)
      - Tweak CGA mode register 3D8h to enable color burst (composite color)
      - Tweak CRTC for 80x100 cells (100 rows × 2 scanlines/row instead of 25 × 8)
      - Use only chars 0x55 ('U', pattern 0xCC) and 0x13 ('‼', pattern 0x66).
        These chars have IDENTICAL row 0 and row 1 patterns, so they produce
        solid colors at 2 scanlines/row (no per-frame CRTC manipulation needed).
      - Each cell's (FG, BG, char) selection produces a unique apparent color
        when viewed via NTSC composite decoder.
      - 16 FG × 16 BG × 2 chars = 512 distinct combinations.
    
    "Set and forget" — once the screen is set up, the image displays statically
    forever with zero CPU intervention until a key is pressed.
    
    Args:
        char_attr_16000: exactly 16000 bytes of (char, attr) pairs in row-major
            order (80 cols × 100 rows × 2 bytes). Char must be 0x55 or 0x13.
            Attr layout: high nibble = BG (0-15), low nibble = FG (0-15).
    
    Returns:
        bytes — the .COM file contents.
    """
    if len(char_attr_16000) != 16000:
        raise ValueError(f"char_attr_16000 must be exactly 16000 bytes, got {len(char_attr_16000)}")
    
    code = bytearray()
    
    # push cs ; pop ds  (DS = CS so we can read appended data)
    code += bytes([0x0E, 0x1F])
    
    # mov ax, 0x0003 ; int 0x10  (set BIOS text mode 03h)
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    
    # Disable blink: INT 10h, AX=1003h, BX=0000h
    code += bytes([0xB8, 0x03, 0x10, 0xBB, 0x00, 0x00, 0xCD, 0x10])
    
    # OUT 3D8h, AL=01h  (video off during reprogramming, 80-col, no blink, no burst yet)
    code += bytes([0xBA, 0xD8, 0x03, 0xB0, 0x01, 0xEE])
    
    def out_crtc(idx, val):
        # mov dx, 0x3D4 ; mov al, idx ; out dx, al ; inc dx ; mov al, val ; out dx, al
        code.extend([0xBA, 0xD4, 0x03])  # mov dx, 3D4h
        code.extend([0xB0, idx & 0xFF])  # mov al, idx
        code.append(0xEE)                 # out dx, al
        code.append(0x42)                 # inc dx -> 3D5h
        code.extend([0xB0, val & 0xFF])  # mov al, val
        code.append(0xEE)                 # out dx, al
    
    # CRTC tweaks for 80x100 cells (CGA / MC6845 register values)
    out_crtc(0x04, 0x7F)  # Vertical total = 127
    out_crtc(0x06, 0x64)  # Vertical displayed = 100 char rows
    out_crtc(0x07, 0x70)  # Vertical sync position = 112
    out_crtc(0x09, 0x01)  # Max scanline = 1 (each char row = 2 scanlines)
    out_crtc(0x03, 0x0A)  # Hsync width register (default position, normal width)
    
    # OUT 3D8h, AL=09h  (video on, 80-col, no blink, COLOR BURST ON)
    # bit 0 = 80-col text, bit 3 = video enable. bit 2 = 0 → color burst on (composite color).
    code += bytes([0xBA, 0xD8, 0x03, 0xB0, 0x09, 0xEE])
    
    # Copy 16000 bytes to B800:0000
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])  # mov ax, B800h ; mov es, ax
    code += bytes([0x31, 0xFF])                     # xor di, di
    si_patch_at = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])               # mov si, DATA_OFFSET (patched)
    code += bytes([0xB9, 0x40, 0x1F])               # mov cx, 8000
    code += bytes([0xF3, 0xA5])                     # rep movsw  (DOS guarantees DF=0)
    
    # Wait for keypress (loop on int 16h ah=01)
    code += bytes([0xB4, 0x01, 0xCD, 0x16, 0x74, 0xFA])
    # Consume key
    code += bytes([0xB4, 0x00, 0xCD, 0x16])
    
    # Restore mode 03h and exit cleanly
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    code += bytes([0xB4, 0x4C, 0xCD, 0x21])  # int 21h ah=4Ch
    
    # Patch data offset
    data_off = 0x100 + len(code)
    if data_off > 0x1FF0:
        raise ValueError(f"Code section too large: 0x{data_off:04X}")
    code[si_patch_at] = data_off & 0xFF
    code[si_patch_at + 1] = (data_off >> 8) & 0xFF
    
    return bytes(code) + char_attr_16000


def pack_text_80x100_512color(chosen) -> bytes:
    """Convert a list of (fg, bg, pat, swap) cell tuples into 16000 bytes of
    (char, attr) pairs for the 512-color CGA text-NTSC mode.
    
    Pattern → char mapping:
      Pattern [1,1,0,0,1,1,0,0] (0xCC) → char 0x55 ('U')
      Pattern [0,1,1,0,0,1,1,0] (0x66) → char 0x13 ('‼')
    
    Swap handling:
      The simulation's "swap=True" means FG and BG roles are inverted in the
      displayed pattern. On real hardware this is achieved by simply SWAPPING
      the FG and BG values in the attribute byte (since the char's bit pattern
      is fixed, but which bits are "FG" vs "BG" depends on the attribute).
    
    Attribute layout: high nibble = BG (0-15), low nibble = FG (0-15).
    
    Args:
        chosen: list of (fg, bg, pat, swap) tuples, length 8000 (80x100 cells).
    
    Returns:
        16000-byte (char, attr) buffer ready for build_com_text_80x100_512color.
    """
    if len(chosen) != 80 * 100:
        raise ValueError(f"chosen must have 8000 entries (80x100), got {len(chosen)}")
    
    # Pattern identification: 0xCC and 0x66 are the 8-bit row patterns.
    PATTERN_CC = [1, 1, 0, 0, 1, 1, 0, 0]
    PATTERN_66 = [0, 1, 1, 0, 0, 1, 1, 0]
    
    out = bytearray(16000)
    for i, (fg, bg, pat, swap) in enumerate(chosen):
        pat_list = list(pat)
        if pat_list == PATTERN_CC:
            char_code = 0x55
        elif pat_list == PATTERN_66:
            char_code = 0x13
        else:
            # Unknown pattern — shouldn't happen if the LUT only has 512-mode patterns.
            # Fall back to char 0x55 (visually wrong but won't crash).
            char_code = 0x55
        
        # Apply swap by flipping FG and BG in the attribute. The hardware char
        # bitmap is fixed, so swapping FG↔BG in the attr byte produces the same
        # visual effect as inverting the pattern.
        if swap:
            fg_out, bg_out = bg, fg
        else:
            fg_out, bg_out = fg, bg
        
        attr = ((bg_out & 0x0F) << 4) | (fg_out & 0x0F)
        out[i * 2] = char_code
        out[i * 2 + 1] = attr
    
    return bytes(out)


def pack_text_80x100_1024color(chosen) -> bytes:
    """Convert a list of (fg, bg, pat, swap) cell tuples into 16000 bytes of
    (char, attr) pairs for the 1024-color CGA text-NTSC mode (full-screen).
    
    Pattern → char mapping (4 patterns supported in 1024-color mode):
      Pattern [1,1,0,0,1,1,0,0] (0xCC) → char 0x55 ('U')   — row 0..5 all 0xCC
      Pattern [0,1,1,0,0,1,1,0] (0x66) → char 0x13 ('‼')   — row 0..2 all 0x66
      Pattern [0,0,1,0,0,0,1,0] (0x22) → char 0xB0 ('░')   — row 0 only (rows alternate)
      Pattern [0,1,0,1,0,1,0,1] (0x55) → char 0xB1 ('▒')   — row 0 only (rows alternate)
    
    The first two chars work at any MaxSL because their early rows are constant.
    The last two chars require the mini-frames CRTC trick (MaxSL=0, 100 mini-frames
    per CRT frame) to suppress their row 1+ which differs from row 0.
    
    Swap handling:
      "swap=True" means FG and BG roles are inverted. Achieved by SWAPPING the
      FG and BG values in the attribute byte.
    
    Args:
        chosen: list of (fg, bg, pat, swap) tuples, length 8000 (80x100 cells).
    
    Returns:
        16000-byte (char, attr) buffer ready for build_com_text_80x100_1024color.
    """
    if len(chosen) != 80 * 100:
        raise ValueError(f"chosen must have 8000 entries (80x100), got {len(chosen)}")
    
    PATTERN_CC = [1, 1, 0, 0, 1, 1, 0, 0]
    PATTERN_66 = [0, 1, 1, 0, 0, 1, 1, 0]
    PATTERN_22 = [0, 0, 1, 0, 0, 0, 1, 0]
    PATTERN_55 = [0, 1, 0, 1, 0, 1, 0, 1]
    
    out = bytearray(16000)
    for i, (fg, bg, pat, swap) in enumerate(chosen):
        pat_list = list(pat)
        if pat_list == PATTERN_CC:
            char_code = 0x55
        elif pat_list == PATTERN_66:
            char_code = 0x13
        elif pat_list == PATTERN_22:
            char_code = 0xB0
        elif pat_list == PATTERN_55:
            char_code = 0xB1
        else:
            # Unknown pattern — fall back. Shouldn't happen with the LUT we built.
            char_code = 0x55
        
        if swap:
            fg_out, bg_out = bg, fg
        else:
            fg_out, bg_out = fg, bg
        
        attr = ((bg_out & 0x0F) << 4) | (fg_out & 0x0F)
        out[i * 2] = char_code
        out[i * 2 + 1] = attr
    
    return bytes(out)


def build_com_text_80x100_1024color(char_attr_16000: bytes) -> bytes:
    """Build a DOS .COM that displays an 80x100 NTSC-text-trick 1024-color image
    on a real CGA card with composite output, using the canonical mini-frames technique.
    
    The 1024-color mode (per reenigne / 8088 MPH "girl" image):
      - 80x100 logical cells (200 visible scanlines, full screen)
      - Uses ALL 4 useful chars: 0x55, 0x13, 0xB0, 0xB1
      - Chars 0xB0 and 0xB1 have differing row-0 vs row-1 patterns, so MaxSL must
        be 0 (1 scanline per row) to draw only row 0.
      - The MC6845 CRTC can only fit ~127 character rows per frame, so to get 200
        visible scanlines at 1 scanline per row we use the MINI-FRAMES technique:
        100 separate "mini-frames" of 2 scanlines each, with the CRTC start address
        advanced by 80 chars between each one. The CRT vsync output is suppressed
        for 99 of the 100 mini-frames, with one large "overscan" CRTC frame at the
        bottom firing the single CRT vsync per frame.
    
    Per-frame structure (262 scanlines):
      Scanlines 0..199:   100 mini-frames × 2 scanlines (VTotal=1, VDisp=2, MaxSL=0)
                          Start address advances: 0, 80, 160, ..., 7920
      Scanlines 200..261: 62-scanline overscan frame (VTotal=0x3D), single vsync
    
    The CPU is fully occupied by the timing loop while displaying — image is static
    until a key is pressed.
    
    Args:
        char_attr_16000: exactly 16000 bytes of (char, attr) pairs in row-major
            order (80 cols × 100 rows × 2 bytes). Chars must be in {0x55, 0x13, 0xB0, 0xB1}.
            Attr layout: high nibble = BG (0-15), low nibble = FG (0-15).
    
    Returns:
        bytes — the .COM file contents.
    """
    if len(char_attr_16000) != 16000:
        raise ValueError(f"char_attr_16000 must be exactly 16000 bytes, got {len(char_attr_16000)}")
    
    code = bytearray()
    
    # ---- BIOS init: mode 3, disable blink, mode register, palette ----
    code += bytes([0x0E, 0x1F])                          # push cs ; pop ds
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])        # mov ax,3 ; int 10h (mode 03h)
    code += bytes([0xB8, 0x03, 0x10, 0xBB, 0x00, 0x00, 0xCD, 0x10])  # disable blink
    
    code += bytes([0xFA])                                # cli
    
    # ---- Copy 16000 bytes (8000 words) to B800:0000 ----
    code += bytes([0x8C, 0xC8])              # mov ax, cs
    code += bytes([0x8E, 0xD8])              # mov ds, ax
    code += bytes([0xB8, 0x00, 0xB8])        # mov ax, B800h
    code += bytes([0x8E, 0xC0])              # mov es, ax
    code += bytes([0xB9, 0x40, 0x1F])        # mov cx, 8000
    si_data_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])        # mov si, data (will be patched)
    code += bytes([0x31, 0xFF])              # xor di, di
    code += bytes([0xFC])                    # cld
    code += bytes([0xF3, 0xA5])              # rep movsw
    
    # ---- CGA mode register: 0x09 (80-col, video on, color burst on, no blink) ----
    code += bytes([0xBA, 0xD8, 0x03, 0xB0, 0x09, 0xEE])
    # ---- Palette register: 0x00 (border black, etc.) ----
    code += bytes([0x42, 0xB0, 0x00, 0xEE])
    
    # ---- CRTC initial setup (overscan config) ----
    # Invariants throughout frame: VDisp=2, MaxSL=0, VSync=0x18.
    # Only VTotal toggles between 1 (mini-frame) and 0x3D (overscan).
    code += bytes([0xB2, 0xD4])              # mov dl, D4h
    
    crtc_init = [
        (0x00, 0x71),  # HTotal       = 0x71
        (0x01, 0x50),  # HDisp        = 0x50
        (0x02, 0x5A),  # HSyncPos     = 0x5A
        (0x03, 0x00),  # HSyncWidth   = 0 (= 16 on MC6845; intentional per reenigne)
        (0x04, 0x3D),  # VTotal       = 0x3D (initial = overscan, 62 scanlines)
        (0x05, 0x00),  # VTotalAdj    = 0
        (0x06, 0x02),  # VDisp        = 2 (always 2 rows)
        (0x07, 0x18),  # VSyncPos     = 0x18 (vsync at row 24 of overscan = scanline 224)
        (0x08, 0x02),  # Interlace    = 2
        (0x09, 0x00),  # MaxSL        = 0 (1 scanline per row, ALWAYS)
        (0x0A, 0x06),  # CursorStart
        (0x0B, 0x07),  # CursorEnd
        (0x0C, 0x00),  # StartH       = 0
        (0x0D, 0x00),  # StartL       = 0
        (0x0E, 0x03),  # CursorH
        (0x0F, 0xC0),  # CursorL
    ]
    for reg, val in crtc_init:
        word = (val << 8) | reg
        code += bytes([0xB8, word & 0xFF, (word >> 8) & 0xFF, 0xEF])  # mov ax, w16 ; out dx, ax
    
    # ---- Set up registers for frame loop ----
    code += bytes([0xB2, 0xDA])              # mov dl, DAh (DX = 3DAh for status polling)
    code += bytes([0xBB, 0x50, 0x00])        # mov bx, 80 (initial start addr for mini-frame 1)
    code += bytes([0xBD, 0x00, 0x00])        # mov bp, 0 (frame counter; wraps to 0xFFFF on first dec, ~18min @60Hz)

    # ============================================================
    # FRAME LOOP — runs until keypress OR ~65536 frames
    # ============================================================
    # Per-frame exit detection uses two cheap, CLI-safe checks:
    #   (1) read 8042 keyboard controller status port 0x64; bit 0 set = scancode
    #       waiting in the controller's output buffer (works without IRQ 1)
    #   (2) decrement BP frame counter; when it hits 0 we exit
    # We deliberately do NOT use INT 16h here: with CLI in effect the BIOS
    # keyboard buffer is never refilled, so INT 16h can't detect anything,
    # AND the BIOS handler internally STIs and consumes hundreds-to-thousands
    # of cycles that cause us to miss the vsync edge for the next frame's
    # mini-frame setup, which collapses the display back to mode 03h.
    frame_loop_off = len(code)
    
    # Wait for vsync, then no-vsync (clean sync point at start of CRT frame)
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])  # waitForVerticalSync (bit 3 = 1)
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])  # waitForNoVerticalSync (bit 3 = 0)
    
    # ============================================================
    # Lines 0-1: switch to active mini-frame config (VTotal=1)
    # ============================================================
    
    # waitForDisplayEnable (start of line 0)
    code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])
    
    # During line 0: switch VTotal to 1 (= 2 scanlines per CRTC frame)
    code += bytes([0xB2, 0xD4])
    code += bytes([0xB8, 0x04, 0x01, 0xEF])  # mov ax, 0x0104 ; out dx, ax (VTotal = 1)
    code += bytes([0xB2, 0xDA])
    
    # waitForDisplayDisable (end of line 0)
    code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])
    # waitForDisplayEnable (start of line 1)
    code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])
    
    # During line 1: write start address (BX) for mini-frame 1, increment BX
    code += bytes([0xB2, 0xD4])              # mov dl, D4h
    code += bytes([0x88, 0xFC])              # mov ah, bh
    code += bytes([0xB0, 0x0C])              # mov al, 0x0c
    code += bytes([0xEF])                    # out dx, ax (StartH = BH)
    code += bytes([0x88, 0xDC])              # mov ah, bl
    code += bytes([0x40])                    # inc ax (AL: 0x0C → 0x0D)
    code += bytes([0xEF])                    # out dx, ax (StartL = BL)
    code += bytes([0x83, 0xC3, 0x50])        # add bx, 80
    code += bytes([0xB2, 0xDA])              # mov dl, DAh
    
    # waitForDisplayDisable (end of line 1)
    code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])
    
    # ============================================================
    # Lines 2..199: 99 mini-frames (unrolled)
    # 
    # Per mini-frame:
    #   waitForDisplayEnable (scanline 0)
    #   waitForDisplayDisable
    #   waitForDisplayEnable (scanline 1)
    #   write StartAddr = BX, BX += 80
    #   waitForDisplayDisable
    # ============================================================
    
    for _ in range(99):
        code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])  # waitForDisplayEnable
        code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])  # waitForDisplayDisable
        code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])  # waitForDisplayEnable
        # Write start address
        code += bytes([0xB2, 0xD4])                    # mov dl, D4h
        code += bytes([0x88, 0xFC])                    # mov ah, bh
        code += bytes([0xB0, 0x0C, 0xEF])              # mov al, 0x0c ; out
        code += bytes([0x88, 0xDC])                    # mov ah, bl
        code += bytes([0x40, 0xEF])                    # inc ax ; out
        code += bytes([0x83, 0xC3, 0x50])              # add bx, 80
        code += bytes([0xB2, 0xDA])                    # mov dl, DAh
        code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])  # waitForDisplayDisable
    
    # ============================================================
    # Line 200: switch back to overscan (VTotal = 0x3D)
    # ============================================================
    code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])  # waitForDisplayEnable
    code += bytes([0xB2, 0xD4])
    code += bytes([0xB8, 0x04, 0x3D, 0xEF])        # VTotal = 0x3D
    code += bytes([0xB2, 0xDA])
    code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])  # waitForDisplayDisable
    
    # ============================================================
    # Line 201: reset start address to 0, reset BX to 80
    # ============================================================
    code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])  # waitForDisplayEnable
    code += bytes([0xB2, 0xD4])
    code += bytes([0xB8, 0x0C, 0x00, 0xEF])        # mov ax, 0x000C ; out (StartH = 0)
    code += bytes([0x40, 0xEF])                    # inc ax ; out (StartL = 0)
    code += bytes([0xBB, 0x50, 0x00])              # mov bx, 80
    code += bytes([0xB2, 0xDA])
    code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])  # waitForDisplayDisable
    
    # ---- Check for exit: keypress (port 0x64) OR frame counter expired ----
    # in al, 0x64 ; test al, 1 ; jnz exit  (8042 status; bit 0 = scancode ready)
    code += bytes([0xE4, 0x64])                    # in al, 0x64
    code += bytes([0xA8, 0x01])                    # test al, 1
    code += bytes([0x75, 0x06])                    # jnz +6 (skip dec/jz/jmp → exit)
    # dec bp ; jz exit  (frame counter; 0 → 0xFFFF → ... → 0 → exit)
    code += bytes([0x4D])                          # dec bp
    code += bytes([0x74, 0x03])                    # jz +3 (exit)

    rel = frame_loop_off - (len(code) + 3)
    rel16 = rel & 0xFFFF
    code += bytes([0xE9, rel16 & 0xFF, (rel16 >> 8) & 0xFF])  # jmp frame_loop

    # ---- Exit ----
    # Consume any pending scancode from the 8042 (cheap & safe)
    code += bytes([0xE4, 0x60])                    # in al, 0x60
    
    code += bytes([0xFB])                          # sti
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])  # mov ax,3 ; int 10h (restore mode)
    code += bytes([0xB4, 0x4C, 0xCD, 0x21])        # int 21h ah=4Ch (exit)
    
    # ---- Patch data offset ----
    data_off = 0x100 + len(code)
    if data_off > 0xFFF0:
        raise ValueError(f"Code section too large: 0x{data_off:04X}")
    code[si_data_patch] = data_off & 0xFF
    code[si_data_patch + 1] = (data_off >> 8) & 0xFF
    
    return bytes(code) + char_attr_16000




def build_com_text_80x100_char16(char_attr_16000: bytes) -> bytes:
    """Build a DOS .COM that displays an 80x100 text screen (16000 bytes: [ch,attr] pairs) using VGA text tweaks.

    Notes:
      - Sets video mode 03h (80x25 color), disables blink (enables bright background bit),
        then tweaks VGA CRTC to 2 scanlines/row and 100 rows.
      - Unlocks CRTC registers (write 0x11 with bit 7 cleared) before reprogramming, since
        VGA BIOS typically leaves CRTC[0x07,0x09,0x10..0x12] write-protected.
      - Writes the 16000 bytes to B800:0000 (2 bytes per cell).
    """
    if len(char_attr_16000) != 16000:
        raise ValueError("build_com_text_80x100_char16 expects exactly 16000 bytes")

    code = bytearray()

    # Set text mode 03h
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])  # mov ax,0003 ; int 10h

    # Disable blink: INT 10h AX=1003h, BX=0000h
    code += bytes([0xB8, 0x03, 0x10, 0xBB, 0x00, 0x00, 0xCD, 0x10])

    # --- CRTC unlock (VGA only) ---
    # Read CRTC[0x11], clear bit 7, write back. Required before CRTC pokes will stick on VGA.
    # mov dx, 03D4h ; mov al, 11h ; out dx, al ; inc dx ; in al, dx ; and al, 7Fh ; out dx, al ; dec dx
    code += bytes([0xBA, 0xD4, 0x03])  # mov dx, 3D4h
    code += bytes([0xB0, 0x11])        # mov al, 11h
    code += bytes([0xEE])              # out dx, al
    code += bytes([0x42])              # inc dx -> 3D5h
    code += bytes([0xEC])              # in  al, dx
    code += bytes([0x24, 0x7F])        # and al, 7Fh
    code += bytes([0xEE])              # out dx, al
    code += bytes([0x4A])              # dec dx -> 3D4h

    # VGA CRTC tweaks for 80x100 (works on VGA-class adapters / DOSBox / DOSBox-X with svga_*):
    # - 09h: Maximum scan line = 0x41 (bit 6 = double-scan, low nibble = 1 -> 2 scanlines/row)
    #        Many BIOSes load 09h with bit 5..7 carrying timing flags; using 0x41 keeps
    #        the line-compare high bit at 0 and explicitly enables double-scan for safety.
    # - 12h: Vertical display end = 0xC7 (200 pixels visible -> we'll show 100 doubled rows)
    # - 06h: Vertical total = 0xBF (matches mode 03h reset)
    # - 14h: Underline location = 0x1F (disable underline; some BIOSes link it to char height)
    crtc_pairs = [
        (0x09, 0x41),
        (0x14, 0x1F),
        (0x12, 0xC7),
        (0x15, 0xC8),
        (0x16, 0xE2),
        (0x10, 0xE1),
        (0x11, 0x06),  # write back vert retrace end with bit 7 = 0 (still unlocked)
        (0x06, 0xBF),
    ]

    # dx is already 3D4h from the unlock sequence above.
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

    # Restore mode 03h (safe even if already) — BIOS reinitializes CRTC so locked state is restored.
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


# --- 320x200 Mode Switch (per-scanline palette) COM exporter ----------------
# These helpers build a DOS .COM that programs CGA mode 04h, copies a static
# 16KB framebuffer, and then runs a vsync+hsync polling loop that writes a
# new value to port 3D9h on every scanline. With N=1 segment per line, this
# gives one palette change per scanline (200 changes total per frame).
#
# Hardware refresher:
#   - Port 3DAh status register, bit 0 = "display enable inverted" (HIGH during ANY
#     retrace — vblank or hblank); bit 3 = vsync pulse only.
#   - Port 3D9h color-select: bits 0..3 = bg color (0..15), bit 4 = intensity,
#     bit 5 = palette set (0 = R/G/Brown family, 1 = C/M/LightGray family).
#   - Standard CGA polling pattern: wait for vsync pulse (3 edges), then on each
#     scanline wait for active-video → hblank transition before writing 3D9h.
#     The first "1→0" transition after vsync end naturally lands at line 0's
#     display start, no matter how many back-porch lines exist.

# CGA mode 04h foreground triplet sets, indexed by (palette_bit, intensity_bit).
# These are accessible when bit 2 of port 3D8h is CLEAR (color burst enabled).
_CGA_MODE04_FG_SETS = {
    (0, 0): frozenset([2, 4, 6]),    # green, red, brown (low intensity, palette 0)
    (0, 1): frozenset([10, 12, 14]), # light green, light red, yellow (high, palette 0)
    (1, 0): frozenset([3, 5, 7]),    # cyan, magenta, light gray (low, palette 1)
    (1, 1): frozenset([11, 13, 15]), # light cyan, light magenta, white (high, palette 1)
}

# CGA mode 05h ("Tweaked") foreground triplet sets, indexed by intensity_bit.
# Accessible when bit 2 of port 3D8h is SET (color burst disabled). On RGB
# monitors and DOSBox-X this forces an alternate palette that mixes colors from
# both standard mode-04h palette sets — bit 5 of 3D9 is ignored in this mode.
_CGA_MODE05_FG_SETS = {
    0: frozenset([3, 4, 7]),     # cyan, red, light gray (Tweaked LOW)
    1: frozenset([11, 12, 15]),  # light cyan, light red, white (Tweaked HIGH)
}

# CGA Mode Control Register (port 3D8h) values for the two graphics palette modes.
# Bit 1 = graphics, bit 3 = video on, bit 2 = "B&W"/colorburst-disable (selects mode 05h).
_CGA_MODE_3D8_MODE04 = 0x0A  # 0b00001010 — mode 04h (color burst enabled)
_CGA_MODE_3D8_MODE05 = 0x0E  # 0b00001110 — mode 05h (color burst disabled, Tweaked palette)

# Backward-compat alias (kept for any external callers that imported the old name).
_CGA_MODE_SWITCH_FG_SETS = _CGA_MODE04_FG_SETS


def _nearest_cga_index(rgb):
    """Return the CGA color index (0..15) closest to the given RGB tuple."""
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    best_d = 1 << 30
    best_i = 0
    for i, c in enumerate(CGA_COLORS):
        dr = r - c[0]; dg = g - c[1]; db = b - c[2]
        d = dr * dr + dg * dg + db * db
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def palette_to_cga_regs(pal4):
    """Convert a 4-color CGA palette [bg, fg1, fg2, fg3] to the two CGA register
    bytes that produce it: (mode_3d8, color_3d9).

    - mode_3d8 selects between standard CGA palettes (0x0A, mode 04h) and the
      Tweaked palette (0x0E, mode 05h, which on RGB/DOSBox-X gives cyan/red/lt-gray).
    - color_3d9 carries bg color (bits 0..3), intensity (bit 4), and palette
      select (bit 5 — meaningful only in mode 04h; ignored in mode 05h).

    Tries mode 04h first (more flexible, full 4-palette range); falls back to
    mode 05h for Tweaked palettes; if no FG triplet matches exactly (which the
    quantizer should never produce), picks the best-overlap mode-04h set.
    """
    if len(pal4) != 4:
        raise ValueError(f"Expected 4-color palette, got {len(pal4)}")
    bg_idx = _nearest_cga_index(pal4[0])
    fg_idxs = frozenset(_nearest_cga_index(c) for c in pal4[1:4])

    # Try the four mode-04h FG triplets first.
    for (pal_bit, int_bit), expected in _CGA_MODE04_FG_SETS.items():
        if fg_idxs <= expected:
            color_3d9 = (bg_idx & 0x0F) | ((int_bit & 1) << 4) | ((pal_bit & 1) << 5)
            return (_CGA_MODE_3D8_MODE04, color_3d9)

    # Try the two mode-05h (Tweaked) FG triplets.
    for int_bit, expected in _CGA_MODE05_FG_SETS.items():
        if fg_idxs <= expected:
            # In mode 05h, palette-select (bit 5) is ignored; we leave it 0 for cleanliness.
            color_3d9 = (bg_idx & 0x0F) | ((int_bit & 1) << 4)
            return (_CGA_MODE_3D8_MODE05, color_3d9)

    # No exact match — pick the highest-overlap mode-04h set as a graceful fallback.
    best_score = -1
    best_bits = (0, 1)
    for bits, expected in _CGA_MODE04_FG_SETS.items():
        score = len(fg_idxs & expected)
        if score > best_score:
            best_score = score
            best_bits = bits
    pal_bit, int_bit = best_bits
    color_3d9 = (bg_idx & 0x0F) | ((int_bit & 1) << 4) | ((pal_bit & 1) << 5)
    return (_CGA_MODE_3D8_MODE04, color_3d9)


def palette_to_3d9_byte(pal4) -> int:
    """Backward-compat shim: returns just the 3D9 byte from palette_to_cga_regs.
    Note that this throws away the 3D8 (mode select) byte and is therefore not
    sufficient on its own for Tweaked palettes — callers should use
    palette_to_cga_regs() and emit both bytes."""
    return palette_to_cga_regs(pal4)[1]


def derive_indices_320_from_rgb(out_image, pals_by_y):
    """Re-derive per-pixel 0..3 palette indices from an RGB output image plus the
    per-line palettes the quantizer used. Returns a (200, 320) uint8 ndarray.

    For each pixel, finds the nearest match among that line's 4 palette colors.
    For a faithful Mode-Switch output the match is always exact (zero distance).
    """
    arr = np.asarray(out_image, dtype=np.int32)
    if arr.ndim == 2:
        # Grayscale — convert to RGB
        arr = np.stack([arr, arr, arr], axis=-1)
    H, W = arr.shape[:2]
    if (W, H) != (320, 200):
        raise ValueError(f"Expected 320x200 image, got {W}x{H}")
    if len(pals_by_y) != H:
        raise ValueError(f"Expected {H} per-line palettes, got {len(pals_by_y)}")
    indices = np.zeros((H, W), dtype=np.uint8)
    for y in range(H):
        pal = np.asarray(pals_by_y[y], dtype=np.int32)  # (4, 3)
        if pal.shape != (4, 3):
            raise ValueError(f"Palette at y={y} has shape {pal.shape}, expected (4,3)")
        # Compute squared distance from each pixel to each of 4 palette colors.
        diff = arr[y, :, None, :] - pal[None, :, :]   # (W, 4, 3)
        dist = np.sum(diff * diff, axis=2)             # (W, 4)
        indices[y] = np.argmin(dist, axis=1).astype(np.uint8)
    return indices


def pack_cga_320_vram_from_indices(indices_h_w) -> bytes:
    """Pack a (200, 320) uint8 index array into 16KB CGA mode 04h VRAM.

    Mode 04h uses 2 bits per pixel, with even/odd scanline interleaving:
      offset 0x0000: even rows (0, 2, ..., 198), 80 bytes each
      offset 0x2000: odd rows (1, 3, ..., 199), 80 bytes each
    """
    H, W = indices_h_w.shape
    if (W, H) != (320, 200):
        raise ValueError(f"Expected (200, 320) indices, got ({H}, {W})")

    def row_bytes_for_y(y):
        rb = bytearray(80)
        row = indices_h_w[y]
        for bx in range(80):
            x = bx * 4
            p0 = int(row[x]) & 3
            p1 = int(row[x + 1]) & 3
            p2 = int(row[x + 2]) & 3
            p3 = int(row[x + 3]) & 3
            rb[bx] = (p0 << 6) | (p1 << 4) | (p2 << 2) | p3
        return bytes(rb)

    return _pack_cga_16k_interleaved(80, 200, row_bytes_for_y)


def build_palette_3d9_table(pals_by_y) -> bytes:
    """Backward-compat shim: builds a 200-byte table of just the 3D9 bytes.
    Use build_cga_reg_table() instead for a Tweaked-aware (400-byte) layout."""
    if len(pals_by_y) != 200:
        raise ValueError(f"Expected 200 palettes, got {len(pals_by_y)}")
    out = bytearray(200)
    for y in range(200):
        out[y] = palette_to_cga_regs(pals_by_y[y])[1]
    return bytes(out)


def build_cga_reg_table(pals_by_y) -> bytes:
    """Build a 400-byte table containing per-scanline (3D8, 3D9) pairs interleaved.

    Layout: byte[2*y]   = 3D8 (mode-control register, 0x0A or 0x0E)
            byte[2*y+1] = 3D9 (color-select register: bg + intensity + palette)

    The COM's display loop reads two bytes per line via consecutive LODSB
    instructions, writing them to ports 3D8h and 3D9h respectively.
    """
    if len(pals_by_y) != 200:
        raise ValueError(f"Expected 200 palettes, got {len(pals_by_y)}")
    out = bytearray(400)
    for y in range(200):
        m, c = palette_to_cga_regs(pals_by_y[y])
        out[2 * y]     = m & 0xFF
        out[2 * y + 1] = c & 0xFF
    return bytes(out)


def build_com_320_mode_switch_n1(vram16k: bytes, reg_table_400: bytes,
                                  display_frames: int = 1800) -> bytes:
    """Build a stable DOS .COM that displays a 320x200 image with one palette change
    per scanline (CGA Mode Switch, N=1 segments).

    v155 stable foundation:
      - Disables interrupts (CLI) for the entire timing-critical display loop.
        This eliminates IRQ0 timer (~18.2 Hz) jitter that previously caused
        periodic 1-line scanline shifts.
      - DRAM refresh remains active (PIT channel 1 is hardware-driven, not
        interrupt-driven), so memory stays alive.
      - Replaces BIOS keyboard polling (int 16h) with a fixed frame counter.
        int 16h has variable duration that perturbs vsync alignment; eliminating
        it gives perfect per-frame timing.
      - On expiry of the frame counter, restores text mode 03h, re-enables
        interrupts (STI), and returns to DOS via int 21h ah=4Ch.

    Each scanline writes BOTH the Mode Control Register (3D8h) and the Color
    Select Register (3D9h) during hblank. This handles per-line switching
    between standard mode 04h palettes and the mode 05h Tweaked palette
    (cyan/red/lt-gray family), since the latter requires 3D8 bit 2 = 1 to
    activate on RGB monitors and DOSBox-X.

    Behavior:
      1. Set BIOS mode 04h (320x200 4-color)
      2. Copy 16KB framebuffer to B800:0000
      3. CLI; load BP with frame counter
      4. main_loop:
           a. Wait for vsync (bit 3 of 3DAh: not-vsync, then vsync, then end)
           b. Write line 0's (3D8, 3D9) pair during back porch
           c. For each of the next 199 scanlines: wait for active video to end,
              then write that line's (3D8, 3D9) pair during hblank.
           d. dec bp; jz exit; jmp main_loop
      5. On exit: STI, restore text mode 03h, return to DOS via int 21h.

    Args:
        vram16k: 16384 bytes of CGA mode-04h VRAM (interleaved even/odd banks).
                 Mode 04h and 05h share the same pixel layout, so this is correct
                 for both per-line modes.
        reg_table_400: 400 bytes — 200 (3D8, 3D9) pairs, line 0 first.
        display_frames: number of CGA frames to display before auto-exit.
                       Default 1800 = 30 seconds at 60Hz. Max 65535.

    Returns:
        bytes — the .COM file contents
    """
    if len(vram16k) != 16384:
        raise ValueError(f"vram16k must be exactly 16384 bytes, got {len(vram16k)}")
    if len(reg_table_400) != 400:
        raise ValueError(f"reg_table_400 must be 400 bytes, got {len(reg_table_400)}")
    if not (1 <= display_frames <= 65535):
        raise ValueError(f"display_frames must be 1..65535, got {display_frames}")

    # Auto-detect: if 3D8 is constant across all 200 lines, use fast path.
    # Fast path writes 3D8 once at startup, then only writes 3D9 per scanline,
    # cutting hblank work in half and giving more timing margin (eliminating
    # the back-to-back OUTs that were causing leftmost-pixel bleed defects).
    mode_3d8_bytes = reg_table_400[0::2]  # all even indices = 3D8 bytes
    constant_3d8 = all(b == mode_3d8_bytes[0] for b in mode_3d8_bytes)
    
    # Build a 3D9-only table (200 bytes) for the fast path
    pal_3d9_table = reg_table_400[1::2]  # all odd indices = 3D9 bytes

    code = bytearray()

    # push cs ; pop ds  — DS=CS so we can read the appended data section
    code += bytes([0x0E, 0x1F])

    # Set BIOS video mode.
    # 
    # MYSTERY OF 3D8 WRITES (empirically determined, hardware-specific):
    #   - Mode 04, NO explicit 3D8 write after BIOS:    PERFECT
    #   - Mode 04, explicit 3D8 = 0x0A after BIOS:      leftmost-pixel defect
    #   - Mode 05, NO explicit 3D8 write after BIOS:    leftmost-pixel defect
    #   - Mode 05, explicit 3D8 = 0x0E after BIOS:      PERFECT
    # 
    # We don't have a full hardware-level explanation, but the rule is clear:
    # mode 04 wants only the BIOS write; mode 05 needs the explicit write.
    # Possibly the BIOS programs the CGA mode-control register slightly
    # differently for the two modes, leaving the pixel pipeline in different
    # internal states. The explicit 3D8 write nudges mode 05 into a clean
    # state but disrupts the already-clean state of mode 04.
    # 
    # Whatever the cause: do the right thing per mode, empirically.
    if constant_3d8 and mode_3d8_bytes[0] == 0x0E:
        bios_mode = 0x05  # Tweaked palette
        emit_explicit_3d8_write = True
    else:
        bios_mode = 0x04  # Standard graphics
        emit_explicit_3d8_write = False
    # mov ax, bios_mode ; int 0x10
    code += bytes([0xB8, bios_mode & 0xFF, 0x00, 0xCD, 0x10])

    # Conditional explicit 3D8 write (mode 05 only — see comment above).
    if emit_explicit_3d8_write:
        const_3d8 = mode_3d8_bytes[0]
        # mov dx, 0x3D8 ; mov al, const_3d8 ; out dx, al
        code += bytes([0xBA, 0xD8, 0x03, 0xB0, const_3d8, 0xEE])

    # mov ax, 0xB800 ; mov es, ax  — ES = video segment
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])
    # xor di, di  — destination offset 0
    code += bytes([0x31, 0xFF])
    # mov si, FB_OFFSET  — patched after we know code length
    fb_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])
    # mov cx, 0x2000 (8192 words = 16384 bytes)
    code += bytes([0xB9, 0x00, 0x20])
    # cld ; rep movsw
    code += bytes([0xFC, 0xF3, 0xA5])

    # ============================================================
    # Disable interrupts for the entire display loop.
    # ============================================================
    code += bytes([0xFA])              # cli

    # mov bp, display_frames  (frame counter)
    code += bytes([0xBD, display_frames & 0xFF, (display_frames >> 8) & 0xFF])

    # main_loop:
    main_loop_off = len(code)
    # mov dx, 0x3DA  — status port
    code += bytes([0xBA, 0xDA, 0x03])
    # vsync_wait_1: in al,dx; test al,8; jnz vsync_wait_1
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])
    # vsync_wait_2: in al,dx; test al,8; jz  vsync_wait_2
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])
    # vsync_wait_3: in al,dx; test al,8; jnz vsync_wait_3
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])

    # mov si, PAL_OFFSET  — patched
    pal_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])

    if constant_3d8:
        # ===== FAST PATH: write only 3D9 per scanline (LSRAIN6 structure) =====
        # 
        # KEY OPTIMIZATION: LODSB happens AFTER the OUT, still during hblank.
        # This minimizes the post-hblank-detect critical path:
        #
        #   wait_hblank exit
        #   mov al, bl  (2c)   ← BL was pre-loaded during prev iteration's hblank
        #   dec dx      (3c)   ← 3DA -> 3D9
        #   out dx, al  (8c)   ← OUT completes only 13c into hblank
        #   inc dx      (3c)   ← 3D9 -> 3DA (after critical path)
        #   lodsb       (12c)  ← load NEXT palette byte for next iter
        #   mov bl, al  (2c)   ← stash for next iter
        #   loop
        #
        # The OUT lands ~10c earlier in hblank than the simpler structure
        # (LODSB before OUT), giving the CGA pixel pipeline time to latch
        # the new palette before line N+1 starts displaying. This is what
        # eliminates the leftmost-pixel edge defect.
        
        # Now in vertical back porch. Write line 0's 3D9 byte.
        # mov dx, 0x3D9
        code += bytes([0xBA, 0xD9, 0x03])
        # lodsb ; out dx, al  — palette[0] (back porch → takes effect for line 0)
        code += bytes([0xAC, 0xEE])
        
        # Pre-load palette[1] into BL — used by iteration 1 of line_loop.
        # Each subsequent iteration loads the NEXT palette byte after writing.
        # lodsb ; mov bl, al
        code += bytes([0xAC, 0x88, 0xC3])
        
        # mov dx, 0x3DA   ; back to status port
        code += bytes([0xBA, 0xDA, 0x03])
        # mov cx, 199
        code += bytes([0xB9, 0xC7, 0x00])

        # line_loop:
        line_loop_off = len(code)
        # wait_active: in al,dx; test al,1; jnz wait_active
        code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])
        # wait_hblank: in al,dx; test al,1; jz wait_hblank
        code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])
        # === CRITICAL PATH (13c minimum to OUT completion) ===
        # mov al, bl       (restore pre-loaded palette byte)
        code += bytes([0x88, 0xD8])
        # dec dx           (3DA -> 3D9)
        code += bytes([0x4A])
        # out dx, al       (write 3D9)
        code += bytes([0xEE])
        # === END CRITICAL PATH ===
        # inc dx           (3D9 -> 3DA)
        code += bytes([0x42])
        # lodsb            (load next palette byte)
        code += bytes([0xAC])
        # mov bl, al       (stash for next iter)
        code += bytes([0x88, 0xC3])
        # loop line_loop
        loop_disp = line_loop_off - (len(code) + 2)
        if not (-128 <= loop_disp <= 127):
            raise RuntimeError(f"line_loop displacement {loop_disp} out of range")
        code += bytes([0xE2, loop_disp & 0xFF])
    else:
        # ===== SLOW PATH (varying 3D8): apply LSRAIN6 KABLAM optimization =====
        # 
        # Both 3D8 and 3D9 vary per line. Pre-load both into BL (3D8) and BH (3D9)
        # during the previous iteration, then write fast in critical path:
        #
        #   wait_hblank exit
        #   mov al, bl   (2c)   ← 3D8 byte (pre-loaded)
        #   mov dl, 0xD8 (4c)   ← 3DA -> 3D8 (faster than dec dx; dec dx = 6c)
        #   out dx, al   (8c)   ← write 3D8 — completes 14c into hblank
        #   mov al, bh   (2c)
        #   inc dl       (3c)   ← 3D8 -> 3D9
        #   out dx, al   (8c)   ← write 3D9 — completes 27c into hblank
        #   mov dl, 0xDA (4c)   ← 3D9 -> 3DA (after critical path)
        #   lodsw        (16c)  ← load BOTH next bytes: AL=3D8, AH=3D9
        #   mov bx, ax   (2c)   ← BL=3D8, BH=3D9 — ready for next iteration
        #   loop
        
        # Now in vertical back porch. Write line 0's (3D8, 3D9) pair.
        # lodsb           ; AL = 3D8 byte for line 0
        code += bytes([0xAC])
        # mov dx, 0x3D8   ; out dx, al
        code += bytes([0xBA, 0xD8, 0x03, 0xEE])
        # inc dx          ; 3D8 -> 3D9
        code += bytes([0x42])
        # lodsb           ; AL = 3D9 byte for line 0
        code += bytes([0xAC])
        # out dx, al
        code += bytes([0xEE])
        
        # Pre-load line 1's (3D8, 3D9) into BX. lodsw reads AL=3D8 byte, AH=3D9 byte.
        # lodsw ; mov bx, ax
        code += bytes([0xAD, 0x89, 0xC3])
        
        # mov dx, 0x3DA   ; back to status port
        code += bytes([0xBA, 0xDA, 0x03])
        # mov cx, 199
        code += bytes([0xB9, 0xC7, 0x00])

        # line_loop:
        line_loop_off = len(code)
        # wait_active
        code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])
        # wait_hblank
        code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])
        # === CRITICAL PATH ===
        # mov al, bl       (3D8 byte)
        code += bytes([0x88, 0xD8])
        # mov dl, 0xD8     (DX = 0x3D8, faster than dec dx; dec dx)
        code += bytes([0xB2, 0xD8])
        # out dx, al       (write 3D8) — completes 14c into hblank
        code += bytes([0xEE])
        # mov al, bh       (3D9 byte)
        code += bytes([0x88, 0xF8])
        # inc dl           (DX = 0x3D9)
        code += bytes([0xFE, 0xC2])
        # out dx, al       (write 3D9) — completes 27c into hblank
        code += bytes([0xEE])
        # === END CRITICAL PATH ===
        # mov dl, 0xDA     (DX back to 0x3DA)
        code += bytes([0xB2, 0xDA])
        # lodsw ; mov bx, ax  (load next line's pair into BX)
        code += bytes([0xAD, 0x89, 0xC3])
        # loop line_loop
        loop_disp = line_loop_off - (len(code) + 2)
        if not (-128 <= loop_disp <= 127):
            raise RuntimeError(f"line_loop displacement {loop_disp} out of range")
        code += bytes([0xE2, loop_disp & 0xFF])

    # ============================================================
    # End of frame. Decrement counter; if not zero, loop back.
    # ============================================================
    # dec bp ; jz exit (skip 3-byte jmp) ; jmp main_loop
    code += bytes([0x4D])
    code += bytes([0x74, 0x03])
    jmp_back_disp = main_loop_off - (len(code) + 3)
    rel_word = jmp_back_disp & 0xFFFF
    code += bytes([0xE9, rel_word & 0xFF, (rel_word >> 8) & 0xFF])

    # ============================================================
    # exit: BP=0 fell through. STI, restore text mode, exit to DOS.
    # ============================================================
    code += bytes([0xFB])                                # sti
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])        # mov ax, 3 ; int 10h
    code += bytes([0xB4, 0x4C, 0xCD, 0x21])              # mov ah, 4Ch ; int 21h

    # Patch the data offsets and assemble final COM.
    fb_off = 0x100 + len(code)
    pal_off = fb_off + 16384
    code[fb_si_patch]     = fb_off & 0xFF
    code[fb_si_patch + 1] = (fb_off >> 8) & 0xFF
    code[pal_si_patch]    = pal_off & 0xFF
    code[pal_si_patch + 1] = (pal_off >> 8) & 0xFF

    if constant_3d8:
        # Fast path: only 200 bytes of 3D9 values
        return bytes(code) + vram16k + bytes(pal_3d9_table)
    else:
        # Slow path: 400 bytes of (3D8, 3D9) pairs
        return bytes(code) + vram16k + reg_table_400


# --- N>=2 Mode Switch (cycle-counted in-line palette writes) ----------------
#
# For N=1 we only write 3D9 during hblank, so timing is forgiving. For N>=2 we
# need to write 3D9 *during active video* at specific horizontal positions.
# The 8088's hardcoded instruction timings make this practical with hand-tuned
# delay padding between writes.
#
# Cycle budget:
#   - CGA mode 04h: 304 cycles per scanline @ 4.77MHz, ~213 cycles active video
#   - 320 pixels at 1.5 pixels/cycle (7.16MHz pixel clock vs 4.77MHz CPU)
#   - Per-write cost (LODSB + OUT to 3D9 with DX preloaded): ~20 cycles
#   - Practical max N: ~8 with equal segments
#
# Strategy:
#   - Write the line's 3D8 (mode register) and segment 0's 3D9 during hblank
#   - Wait for active video to start (poll bit 0 of 3DAh: 1 -> 0)
#   - Cycle-count N-1 in-line 3D9 writes, with NOP/JMP/LOOP delays between them
#   - The line counter lives in BP (LOOP only knows about CX, so we free CX
#     for use as a delay-loop counter)
#
# Polling jitter:
#   The IN/TEST/JZ poll loop is 8 cycles per iteration. The actual exit happens
#   0..8 cycles after bit 0 changes, which translates to ~0..12 pixels of
#   horizontal jitter per line. Real CGA hardware exhibits the same effect.
#
# Tweaked palettes (mode 05h):
#   For N>=2, we currently write 3D8 once per line but cannot vary 3D8 between
#   segments within the same line. The exporter validates that all segments on
#   a given line agree on 3D8; if not, it falls back to mode 04h for that line.

# Cost in cycles for "LODSB + OUT DX, AL" with DX already holding 0x3D9.
# 8088 reference: LODSB = 12c, OUT = 8c. Total = 20c.
_NSEG_WRITE_COST_CYCLES = 20

# Cycles per pixel during CGA mode 04h active video (213.3 / 320).
_NSEG_CYCLES_PER_PIXEL = 213.3 / 320.0


def _emit_delay_no_register(target_cycles):
    """Emit bytes that delay approximately target_cycles 8088 cycles WITHOUT
    clobbering any register. Uses NOP (3c, 1B) and JMP-to-next-instruction
    (EB 00, 15c, 2B). Returns (bytes, actual_cycles).

    For target >= 30 cycles, this is wasteful in code-size; use _emit_delay_loop
    instead. This function works up to ~120 cycles before becoming silly.
    """
    if target_cycles <= 0:
        return (b'', 0)
    n_jmp = target_cycles // 15
    remainder = target_cycles - n_jmp * 15
    n_nop = round(remainder / 3.0)
    code = b'\xEB\x00' * n_jmp + b'\x90' * n_nop
    actual = n_jmp * 15 + n_nop * 3
    return (bytes(code), actual)


def _emit_delay_loop(target_cycles):
    """Emit a delay using MOV CX, k ; .L: LOOP .L. Clobbers CX.

    Cycle math: MOV CX, imm16 (4c) + (k-1) * LOOP-taken (17c each) + 1 LOOP-not-taken (5c)
                = 4 + 17(k-1) + 5 = 17k - 8 cycles.
    Range: minimum effective k=2 (26c). For larger targets, choose k to land near target.
    Returns (bytes, actual_cycles, clobbers_cx=True).
    """
    if target_cycles < 26:
        # Loop construct can't go below 26 cycles cleanly; fall back to NOP/JMP
        code, actual = _emit_delay_no_register(target_cycles)
        return (code, actual, False)
    k = max(2, round((target_cycles + 8) / 17.0))
    actual = 17 * k - 8
    code = bytearray([0xB9, k & 0xFF, (k >> 8) & 0xFF, 0xE2, 0xFE])
    # Fine-tune with NOPs for any leftover slack
    diff = target_cycles - actual
    if diff >= 2:
        n_nop = round(diff / 3.0)
        code += b'\x90' * n_nop
        actual += n_nop * 3
    return (bytes(code), actual, True)


def _emit_delay_smart(target_cycles, prefer_no_clobber=False):
    """Pick the most accurate delay primitive for target_cycles.

    Strategy:
      - Compute both NOP/JMP and LOOP versions where applicable.
      - Pick whichever has smaller cycle error (closer to target).
      - Tie-break by code size (smaller is better).
    If prefer_no_clobber is set, ONLY use NOP/JMP (forces no-CX-clobber).

    Returns (bytes, actual_cycles, clobbers_cx).
    """
    if target_cycles <= 0:
        return (b'', 0, False)
    # Always evaluate the NOP/JMP option
    code_nj, actual_nj = _emit_delay_no_register(target_cycles)
    err_nj = abs(actual_nj - target_cycles)
    if prefer_no_clobber or target_cycles < 26:
        return (code_nj, actual_nj, False)
    # Evaluate LOOP option
    k = max(2, round((target_cycles + 8) / 17.0))
    actual_lp = 17 * k - 8
    code_lp = bytearray([0xB9, k & 0xFF, (k >> 8) & 0xFF, 0xE2, 0xFE])
    diff = target_cycles - actual_lp
    if diff >= 2:
        n_nop = round(diff / 3.0)
        code_lp += b'\x90' * n_nop
        actual_lp += n_nop * 3
    err_lp = abs(actual_lp - target_cycles)
    # Pick best by (error, then code size)
    if err_nj < err_lp:
        return (code_nj, actual_nj, False)
    elif err_nj == err_lp and len(code_nj) <= len(code_lp):
        return (code_nj, actual_nj, False)
    else:
        return (bytes(code_lp), actual_lp, True)


def _emit_delay_exact(target_cycles):
    """Emit bytes that delay EXACTLY target_cycles using NOP (3c, 1B), INC AX
    (2c, 1B, opcode 0x40), and JMP-to-next (15c, 2B).

    Clobbers AX (low byte gets incremented). This is fine in our cycle-counted
    inner loop because every LODSB completely overwrites AL before each OUT
    consumes it — so AX is "scratch" between any LODSB+OUT pair and the next
    LODSB.

    The 2-cycle INC AX granularity lets us hit any target >= 2 exactly. The
    only impossible target is 1 cycle (closest is INC AX at 2c).

    Returns (bytes, actual_cycles).
    """
    if target_cycles <= 0:
        return (b'', 0)
    if target_cycles == 1:
        return (b'\x40', 2)  # impossible to hit 1c exactly; closest is 2c

    best_code = None
    best_actual = -1
    best_size = 10**9
    best_err = 10**9
    # Try every n_jmp from 0 to target//15
    for n_jmp in range(target_cycles // 15 + 1):
        rem = target_cycles - n_jmp * 15
        if rem < 0:
            continue
        # Hit rem exactly with NOPs (3c) and INC AX (2c)
        if rem == 0:
            a, b, actual, err = 0, 0, n_jmp * 15, 0
        elif rem == 1:
            a, b, actual, err = 0, 1, n_jmp * 15 + 2, 1   # overshoot by 1
        elif rem == 2:
            a, b, actual, err = 0, 1, n_jmp * 15 + 2, 0
        elif rem == 3:
            a, b, actual, err = 1, 0, n_jmp * 15 + 3, 0
        elif rem % 2 == 0:
            a, b, actual, err = 0, rem // 2, n_jmp * 15 + rem, 0
        else:  # odd, >= 5
            a, b, actual, err = 1, (rem - 3) // 2, n_jmp * 15 + rem, 0
        size = n_jmp * 2 + a + b
        if (err, size) < (best_err, best_size):
            best_err = err
            best_size = size
            best_code = b'\xEB\x00' * n_jmp + b'\x90' * a + b'\x40' * b
            best_actual = actual

    return (best_code, best_actual)


def _plan_n_segment_cycle_targets(N, W=320):
    """Given N equal segments of total width W, return a list of N-1 cycle offsets
    from the start of active video at which palette[1..N-1] should be written.

    The cycle offsets correspond to the pixel column where each new segment begins.
    """
    if N <= 1:
        return []
    base = W // N
    extra = W - base * N
    boundaries_px = []
    pos = 0
    for i in range(N):
        w = base + (1 if i < extra else 0)
        if i > 0:
            boundaries_px.append(pos)
        pos += w
    return [int(round(p * _NSEG_CYCLES_PER_PIXEL)) for p in boundaries_px]


def build_n_segment_data_table(pals_by_y, N) -> tuple:
    """Build the per-line data table for N>=2 Mode Switch.

    Layout per line: 1 byte 3D8 + N bytes 3D9 = (1 + N) bytes
    Total bytes: 200 * (1 + N)

    For each line:
      - Compute (3D8, 3D9) for each of N segments via palette_to_cga_regs
      - If all N agree on 3D8: use it
      - Else: fall back to 3D8=0x0A (mode 04h) for that line, and re-derive
        each segment's 3D9 by mapping the palette into mode 04h's repertoire

    Returns (data_bytes, mode_mismatch_count) where mode_mismatch_count is the
    number of lines that had to fall back to mode 04h due to mixed-mode segments.
    """
    if N < 2:
        raise ValueError(f"build_n_segment_data_table requires N>=2, got {N}")
    if len(pals_by_y) != 200:
        raise ValueError(f"Expected 200 lines, got {len(pals_by_y)}")
    out = bytearray(200 * (1 + N))
    mismatches = 0
    for y in range(200):
        line_pals = pals_by_y[y]
        if len(line_pals) != N:
            raise ValueError(f"Line {y} has {len(line_pals)} segments, expected {N}")
        regs = [palette_to_cga_regs(p) for p in line_pals]
        # Check 3D8 agreement
        modes = set(m for m, _ in regs)
        if len(modes) == 1:
            line_3d8 = next(iter(modes))
        else:
            # Mixed mode 04h/05h within one line — fall back to mode 04h.
            # Re-derive each segment's 3D9 in mode-04h-only mode by forcing 3D8=0x0A.
            line_3d8 = _CGA_MODE_3D8_MODE04
            mismatches += 1
            new_regs = []
            for p in line_pals:
                # Force the mode 04h fallback: pick the closest mode-04h FG triplet.
                # We do this by skipping the mode 05h branch in palette_to_cga_regs.
                bg_idx = _nearest_cga_index(p[0])
                fg_idxs = frozenset(_nearest_cga_index(c) for c in p[1:4])
                best_score = -1
                best_bits = (0, 1)
                for bits, expected in _CGA_MODE04_FG_SETS.items():
                    score = len(fg_idxs & expected)
                    if score > best_score:
                        best_score = score
                        best_bits = bits
                pal_bit, int_bit = best_bits
                color_3d9 = (bg_idx & 0x0F) | ((int_bit & 1) << 4) | ((pal_bit & 1) << 5)
                new_regs.append((line_3d8, color_3d9))
            regs = new_regs
        base = y * (1 + N)
        out[base] = line_3d8
        for i, (_, c) in enumerate(regs):
            out[base + 1 + i] = c
    return (bytes(out), mismatches)


def derive_indices_320_from_rgb_n_seg(out_image, pals_by_y, N, W=320, H=200):
    """Same as derive_indices_320_from_rgb but handles per-segment palettes.

    pals_by_y[y] is a list of N 4-color palettes covering equal segments of W.
    For each pixel, picks the nearest color from THAT segment's palette.
    """
    arr = np.asarray(out_image, dtype=np.int32)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    if (arr.shape[1], arr.shape[0]) != (W, H):
        raise ValueError(f"Expected {W}x{H} image, got {arr.shape[1]}x{arr.shape[0]}")
    if len(pals_by_y) != H:
        raise ValueError(f"Expected {H} per-line palettes, got {len(pals_by_y)}")

    # Compute equal-segment boundaries
    base = W // N
    extra = W - base * N
    seg_starts = []
    pos = 0
    for i in range(N):
        seg_starts.append(pos)
        pos += base + (1 if i < extra else 0)
    seg_starts.append(W)  # sentinel

    indices = np.zeros((H, W), dtype=np.uint8)
    for y in range(H):
        line_pals = pals_by_y[y]
        if len(line_pals) != N:
            raise ValueError(f"Line {y} has {len(line_pals)} segments, expected {N}")
        for s in range(N):
            x0, x1 = seg_starts[s], seg_starts[s + 1]
            pal = np.asarray(line_pals[s], dtype=np.int32)
            if pal.shape != (4, 3):
                raise ValueError(f"Palette y={y} seg={s} shape {pal.shape}, expected (4,3)")
            diff = arr[y, x0:x1, None, :] - pal[None, :, :]
            dist = np.sum(diff * diff, axis=2)
            indices[y, x0:x1] = np.argmin(dist, axis=1).astype(np.uint8)
    return indices


def build_com_320_mode_switch_n(vram16k: bytes, data_table: bytes, N: int,
                                  cycle_correction: int = 0) -> bytes:
    """Build a DOS .COM that displays a 320x200 image with N palette segments per scanline.

    Per-line data layout (in data_table): 1 byte 3D8 + N bytes 3D9 = (1+N) bytes
    Total data_table size: 200 * (1+N) bytes

    cycle_correction: shifts ALL in-line write boundaries by this many cycles. Positive
        values move boundaries to the right (later writes), negative values move them
        left (earlier writes). Useful for empirical calibration in a specific emulator
        environment where the default cycle math doesn't quite match.

    Per-line code structure:
      - During hblank: write line's 3D8, then write seg-0's 3D9
      - Wait for active video to start (poll 3DAh bit 0: 1 -> 0)
      - For seg i (i = 1..N-1): cycle-counted delay, then write 3D9
      - After last segment: poll 3DAh bit 0 to detect active end (next hblank),
        then loop

    Args:
        vram16k: 16384 bytes of CGA VRAM (interleaved even/odd banks)
        data_table: 200 * (1+N) bytes: 200 lines of [3D8, 3D9_0, ..., 3D9_(N-1)]
        N: number of segments per scanline (must be 2..8)
        cycle_correction: per-boundary cycle offset (default 0)

    Returns:
        bytes — the .COM file contents
    """
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8 for the N-segment builder, got {N}")
    if len(vram16k) != 16384:
        raise ValueError(f"vram16k must be 16384 bytes, got {len(vram16k)}")
    expected_data = 200 * (1 + N)
    if len(data_table) != expected_data:
        raise ValueError(f"data_table must be {expected_data} bytes, got {len(data_table)}")

    # Pre-plan delays for the N-1 in-line writes
    cycle_targets = _plan_n_segment_cycle_targets(N, 320)
    if cycle_correction != 0:
        cycle_targets = [t + cycle_correction for t in cycle_targets]
    # cycle_targets[i] is the cycle position (from start of active) at which
    # we want segment i+1's 3D9 write to land. We need delays BEFORE each write
    # such that (cumulative-cycles-from-active-start) == cycle_targets[i]
    # WHEN the OUT instruction begins executing. The OUT itself takes 8c, so we
    # aim for the OUT to start at cycle_target.

    code = bytearray()

    # ---- Setup ----
    # push cs ; pop ds
    code += bytes([0x0E, 0x1F])
    # mov ax, 0x0004 ; int 0x10  — set BIOS mode 04h
    code += bytes([0xB8, 0x04, 0x00, 0xCD, 0x10])
    # mov ax, 0xB800 ; mov es, ax
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])
    # xor di, di
    code += bytes([0x31, 0xFF])
    # mov si, FB_OFFSET (patched)
    fb_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])
    # mov cx, 0x2000
    code += bytes([0xB9, 0x00, 0x20])
    # cld ; rep movsw
    code += bytes([0xFC, 0xF3, 0xA5])

    # ---- Display loop ----
    display_loop_off = len(code)
    # mov dx, 0x3DA
    code += bytes([0xBA, 0xDA, 0x03])
    # vsync_wait_1: in al,dx; test al,8; jnz vsync_wait_1
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])
    # vsync_wait_2: jz
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])
    # vsync_wait_3: jnz
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])

    # mov si, DATA_OFFSET (patched)
    data_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])
    # mov bp, 200  — line counter (BP is free; CX gets clobbered by delay loops)
    code += bytes([0xBD, 0xC8, 0x00])

    # ---- Per-line loop ----
    # For line N: during hblank, write 3D8 then seg-0 3D9. Then wait for active
    # video, then do N-1 timed in-line writes.
    line_loop_off = len(code)

    # During hblank from prior line (or back porch for line 0): write 3D8, then 3D9_0
    # We're already in hblank/back-porch here on entry (line 0 case) or just exited active (later lines).
    # Actually for line 0 we're in back porch (bit 0 = 1). For later lines, we just exited
    # the active-end poll. Either way, bit 0 = 1 and we have hblank time.
    #
    # Write 3D8:
    # lodsb       ; AL = 3D8 byte
    code += bytes([0xAC])
    # mov dx, 0x3D8 ; out dx, al
    code += bytes([0xBA, 0xD8, 0x03, 0xEE])
    # inc dx       (3D8 -> 3D9)
    code += bytes([0x42])
    # lodsb        ; AL = 3D9 for seg 0
    code += bytes([0xAC])
    # out dx, al   ; write 3D9 for seg 0 (effective for the upcoming line)
    code += bytes([0xEE])
    # DX is now 0x3D9. We'll keep it there during in-line writes.

    # Wait for active video to start (bit 0 of 3DAh: 1 -> 0)
    # Need to switch DX to 3DAh, poll, then back to 3D9.
    # Actually let's use a different register for status: AX is free for AL,
    # but we need DX for IN. Hmm. Better: temporarily set DX to 0x3DA, poll, set back.
    # But the polling jitter (~8c) goes on the wrong side of "active starts" — we exit
    # AFTER bit 0 is already 0, so we're already inside active video.
    #
    # Plan: mov dx, 0x3DA ; .wait: in al,dx; test al,1; jnz .wait ; (then) ...
    # When we exit the wait, beam is at column ~0..8 of active. The cycle-count
    # for our N-1 in-line writes starts here.
    # BUT then we have to mov dx, 0x3D9 again before the writes — and that takes 4c.
    # Bake those 4c into the delay budget for segment 1.

    # mov dx, 0x3DA
    code += bytes([0xBA, 0xDA, 0x03])
    # wait_active_start: in al,dx; test al,1; jnz wait_active_start
    code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])
    # mov dx, 0x3D9 (4c — counted toward seg-1 delay budget below)
    code += bytes([0xBA, 0xD9, 0x03])

    # ---- In-line writes (N-1 of them) ----
    # State on entry: DX=0x3D9, SI points to seg-1 byte for this line.
    # Cycle counter: we exited "wait_active_start" + executed mov dx,0x3D9 (4c).
    # So cycles_so_far = 4 + jitter (treat as 4 nominal).
    cycles_so_far = 4  # nominal cycles since "active start" reference point

    for i in range(N - 1):
        # Target: the OUT for seg (i+1) should COMMIT at cycle_targets[i].
        # OUT takes 8c and the write commits ~mid-instruction. To approximate that,
        # aim for OUT to START at cycle_target - 4 (so it commits at cycle_target).
        # Before the OUT we need LODSB (12c). So the delay block should land us at
        # cycle (target - 4 - 12) = target - 16 right before LODSB starts.
        target_at_lodsb_start = cycle_targets[i] - 16
        delay_needed = target_at_lodsb_start - cycles_so_far
        if delay_needed < 0:
            # Can't go back in time. The N is too large for equal segments;
            # this is a code-gen sanity check.
            raise RuntimeError(
                f"N={N} segment {i+1}: delay budget exhausted "
                f"(needed {delay_needed} cycles, segments too tight)"
            )
        # Emit delay (will use NOP/JMP for small, LOOP for large; CX clobbered if LOOP)
        delay_bytes, actual_delay, _clobbers_cx = _emit_delay_smart(delay_needed)
        code += delay_bytes
        # lodsb
        code += bytes([0xAC])
        # out dx, al
        code += bytes([0xEE])
        cycles_so_far += actual_delay + 12 + 8

    # ---- End of line: wait for active to end (next hblank) ----
    # We need to (a) get DX back to 3DAh to poll bit 0, (b) wait for hblank.
    # During this wait, the rest of the active line is rendering with seg N-1's palette.
    # mov dx, 0x3DA
    code += bytes([0xBA, 0xDA, 0x03])
    # wait_hblank: in al,dx; test al,1; jz wait_hblank
    code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])
    # We're now in hblank (or vblank for line 199 — both have bit 0 = 1).

    # Decrement line counter and loop back.
    # dec bp
    code += bytes([0x4D])
    # jnz line_loop  (short)
    line_disp = line_loop_off - (len(code) + 2)
    if not (-128 <= line_disp <= 127):
        # If this happens, code section is too large for short jump. Use jcc->jmp pattern.
        # JZ +3, JMP near
        code += bytes([0x74, 0x03])
        long_disp = line_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])
    else:
        code += bytes([0x75, line_disp & 0xFF])

    # ---- Keypress check ----
    # mov ah, 0x01 ; int 0x16
    code += bytes([0xB4, 0x01, 0xCD, 0x16])
    # jz display_loop  (no key, repeat frame)
    jz_disp = display_loop_off - (len(code) + 2)
    if -128 <= jz_disp <= 127:
        code += bytes([0x74, jz_disp & 0xFF])
    else:
        code += bytes([0x75, 0x03])
        long_disp = display_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])

    # ---- Cleanup and exit ----
    # mov ah, 0 ; int 0x16  (consume keypress)
    code += bytes([0xB4, 0x00, 0xCD, 0x16])
    # mov ax, 0x0003 ; int 0x10  (text mode)
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    # ret
    code += bytes([0xC3])

    # Patch offsets
    fb_off = 0x100 + len(code)
    data_off = fb_off + 16384
    code[fb_si_patch]     = fb_off & 0xFF
    code[fb_si_patch + 1] = (fb_off >> 8) & 0xFF
    code[data_si_patch]     = data_off & 0xFF
    code[data_si_patch + 1] = (data_off >> 8) & 0xFF

    return bytes(code) + vram16k + data_table


# --- Diagnostic / calibration builders for N>=2 timing -----------------------
#
# These helpers produce test .COM files that visualize where N-segment palette
# transitions actually land in a target environment (e.g., DOSBox-X). Use them
# when the production builder shows boundary jitter or systematic offset.
#
# How polling jitter works (and why we need calibration):
#   The wait_active_start poll loop is `IN; TEST; JNZ`, which on 8088 takes
#   8 + 4 + 16 = 28 cycles per iteration. The CGA status bit can change at any
#   point during that window, so the loop exits 0..28 cycles after the actual
#   active-video-start. At 1.5 pixels per cycle that's up to ~42 pixels of
#   per-line horizontal jitter. DRAM refresh stalls (4 cycles per ~72 cycles
#   of active CPU) add another ~12 cycles of variance per line.
#
#   Net effect: every line has its own random horizontal offset, applied to
#   ALL N segment boundaries on that line. Boundaries don't shift relative to
#   each other within one line, but they do shift line-to-line and frame-to-
#   frame, producing the "flickering boundary" effect.
#
#   The calibration COMs below help identify whether you're seeing constant
#   offset (fixable with cycle_correction parameter) or true jitter (which
#   requires an architectural change to the polling strategy).

# Per-segment "signature" palettes (mode 04h compatible). 8 distinct palettes
# for use in calibration patterns up to N=8.
_CALIBRATION_PALETTES = [
    [(0, 0, 0), (0, 170, 0), (170, 0, 0), (170, 85, 0)],          # idx1=green
    [(0, 0, 0), (85, 255, 85), (255, 85, 85), (255, 255, 85)],    # idx1=lgreen
    [(0, 0, 0), (0, 170, 170), (170, 0, 170), (170, 170, 170)],   # idx1=cyan
    [(0, 0, 0), (85, 255, 255), (255, 85, 255), (255, 255, 255)], # idx1=lcyan
    [(0, 0, 170), (0, 170, 0), (170, 0, 0), (170, 85, 0)],        # idx1=green on blue
    [(0, 0, 170), (85, 255, 85), (255, 85, 85), (255, 255, 85)],  # idx1=lgreen on blue
    [(170, 170, 170), (0, 170, 0), (170, 0, 0), (170, 85, 0)],    # idx1=green on lgray
    [(170, 170, 170), (85, 255, 85), (255, 85, 85), (255, 255, 85)],# idx1=lgreen on lgray
]


def _calibration_segment_starts(N, W=320):
    """Return list of starting columns for N equal segments of total width W."""
    base = W // N
    extra = W - base * N
    starts = []
    pos = 0
    for i in range(N):
        starts.append(pos)
        pos += base + (1 if i < extra else 0)
    starts.append(W)
    return starts


def build_calibration_static_n_seg(N, cycle_correction=0):
    """Build a calibration .COM where every segment uses the SAME palette.

    If this COM displays cleanly (no flicker), the cycle-counted code path itself
    is working correctly — any flicker in the production builder must come from
    timing variation between palettes.

    If this COM still flickers, the issue is in the polling/dispatch logic
    rather than in the per-line palette switching.
    """
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    pal = _CALIBRATION_PALETTES[0]  # all segments use the same palette
    seg_palettes = [pal] * N
    pals_by_y = [seg_palettes] * 200

    # Framebuffer: visible content ALL pixels = idx 1 (so they all show the same color)
    indices = np.full((200, 320), 1, dtype=np.uint8)

    data_table, _ = build_n_segment_data_table(pals_by_y, N)
    vram = pack_cga_320_vram_from_indices(indices)
    return build_com_320_mode_switch_n(vram, data_table, N, cycle_correction=cycle_correction)


def build_calibration_boundary_ruler_n_seg(N, cycle_correction=0):
    """Build a calibration .COM showing where N-segment boundaries actually land.

    Image structure:
      - Each segment uses a distinct palette so its displayed color is unique
      - All pixels are filled with index 1 (the "primary" foreground)
      - At each EXPECTED segment boundary, a 4-pixel-wide black ruler stripe
        is encoded in the framebuffer (using index 0)

    What you see in DOSBox-X:
      - If timing is perfect: black rulers center exactly on the color transitions
      - If timing has constant offset: rulers shifted from transitions by a fixed amount
      - If boundaries jitter: rulers visible at their FB position; transitions wander
        line-to-line. The framebuffer rulers are stable (they're just pixel data),
        so they serve as a fixed reference against the moving palette boundaries.

    The width of the visible "wrong-palette zone" between a ruler and the actual
    transition tells you how off the timing is in cycles:
      - 1 pixel of mismatch ≈ 0.67 cycles
      - Use cycle_correction to compensate (positive = move boundary right)
    """
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    seg_palettes = [_CALIBRATION_PALETTES[i % len(_CALIBRATION_PALETTES)] for i in range(N)]
    pals_by_y = [seg_palettes] * 200

    # Framebuffer: all pixels = idx 1, except 4-pixel ruler stripes at boundaries
    indices = np.full((200, 320), 1, dtype=np.uint8)
    seg_starts = _calibration_segment_starts(N, 320)
    for i in range(1, N):
        b = seg_starts[i]  # boundary column (start of segment i)
        for col in (b - 2, b - 1, b, b + 1):
            if 0 <= col < 320:
                indices[:, col] = 0  # black bg

    # Also draw a row of 1-pixel-wide marks at very top (rows 0..1) for visual scale
    # Every 10 columns is marked
    for col in range(0, 320, 10):
        indices[0:2, col] = 0

    data_table, _ = build_n_segment_data_table(pals_by_y, N)
    vram = pack_cga_320_vram_from_indices(indices)
    return build_com_320_mode_switch_n(vram, data_table, N, cycle_correction=cycle_correction)


def build_calibration_sweep_n_seg(N, corrections=None):
    """Build a calibration .COM that uses DIFFERENT cycle corrections for different
    vertical bands of the screen, all in ONE run.

    Each correction value gets a horizontal band of (200 / len(corrections)) lines.
    The user runs ONE COM and sees all corrections at once; the band where rulers
    align with transitions tells you the right correction value.

    How it works internally:
      - We can't change cycle_correction at runtime (it's baked into code).
      - Instead, we make the per-line code conditional on the line counter:
        a small "switch" at top of line_loop selects which delay sequence to use.
      - To keep this manageable, this builder generates a SEPARATE inner code
        path per correction value, then dispatches based on a band lookup table.

    Implementation: We don't actually do that runtime dispatch (it's complex).
    Instead, this just builds a COM with the median correction applied uniformly.
    For multi-band testing, generate separate COMs via build_calibration_boundary_ruler_n_seg
    with different corrections.
    """
    if corrections is None:
        corrections = list(range(-8, 9, 2))
    middle_idx = len(corrections) // 2
    return build_calibration_boundary_ruler_n_seg(N, cycle_correction=corrections[middle_idx])


def build_calibration_multiband_sweep_n_seg(N, corrections=None):
    """Build a single .COM that displays MULTIPLE cycle corrections on different
    horizontal bands of the screen, so you can compare all at once.

    Strategy:
      The line_loop is unrolled in code: instead of one shared per-line snippet
      that does a fixed cycle pattern, we emit a sequence of code blocks where
      each block handles a vertical band with its own cycle_correction value.
      The blocks are concatenated; control flows from top to bottom naturally.

    Each band is 200 // len(corrections) lines tall. Within each band, the
    same correction is applied to all in-line writes.

    A small "label stripe" is drawn at the very LEFT (cols 0..3) of each line
    encoding the band index in framebuffer pixels. This makes it easy to
    identify which band shows the cleanest alignment.

    Returns:
        bytes — the .COM file contents
    """
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    if corrections is None:
        corrections = list(range(-8, 9, 2))  # 9 corrections: -8, -6, ..., +6, +8
    K = len(corrections)
    if K > 16:
        raise ValueError(f"Too many corrections ({K}); max 16")
    if K == 0:
        raise ValueError("Need at least one correction value")

    band_h = 200 // K
    # Lines covered exactly. Last band absorbs any remainder.
    band_starts = [i * band_h for i in range(K)]
    band_starts.append(200)  # sentinel

    # Cycle targets per correction
    base_targets = _plan_n_segment_cycle_targets(N, 320)
    band_targets = [[t + c for t in base_targets] for c in corrections]

    # Build framebuffer with rulers + band-index labels at left edge
    seg_palettes = [_CALIBRATION_PALETTES[i % len(_CALIBRATION_PALETTES)] for i in range(N)]
    seg_starts = _calibration_segment_starts(N, 320)
    indices = np.full((200, 320), 1, dtype=np.uint8)
    # Boundary rulers
    for i in range(1, N):
        b = seg_starts[i]
        for col in (b - 2, b - 1, b, b + 1):
            if 0 <= col < 320:
                indices[:, col] = 0
    # Band-separator stripes (1px black row at the start of each band)
    for k in range(K):
        y = band_starts[k]
        if y < 200:
            indices[y, :] = 0  # single black row separating bands
    # Top scale ticks (every 10 cols) on row 0 (already overwritten by separator
    # for k=0, so do row 1 too for visibility)
    for col in range(0, 320, 10):
        indices[1, col] = 0

    # Build per-line palette table — same N palettes on every line
    pals_by_y = [seg_palettes] * 200
    data_table, _ = build_n_segment_data_table(pals_by_y, N)
    vram = pack_cga_320_vram_from_indices(indices)

    # ---- Now build the multiband COM with K inner code blocks ----
    code = bytearray()

    # Setup
    code += bytes([0x0E, 0x1F])               # push cs ; pop ds
    code += bytes([0xB8, 0x04, 0x00, 0xCD, 0x10])  # mov ax, 4 ; int 10h
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])  # mov ax, B800 ; mov es, ax
    code += bytes([0x31, 0xFF])               # xor di, di
    fb_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])         # mov si, FB_OFFSET (patched)
    code += bytes([0xB9, 0x00, 0x20])         # mov cx, 0x2000
    code += bytes([0xFC, 0xF3, 0xA5])         # cld ; rep movsw

    # Display loop start
    display_loop_off = len(code)
    code += bytes([0xBA, 0xDA, 0x03])         # mov dx, 0x3DA
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])  # vsync_wait_1
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])  # vsync_wait_2
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])  # vsync_wait_3

    data_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])         # mov si, DATA_OFFSET (patched)

    # ---- Per-band code blocks ----
    # Each block: mov bp, band_height ; <inner line_loop> with band's correction
    for k in range(K):
        bh = band_starts[k + 1] - band_starts[k]
        # mov bp, bh
        code += bytes([0xBD, bh & 0xFF, (bh >> 8) & 0xFF])
        # band's line_loop:
        band_loop_off = len(code)
        # In-hblank writes (3D8 + 3D9_0)
        code += bytes([0xAC])                 # lodsb (3D8)
        code += bytes([0xBA, 0xD8, 0x03, 0xEE])  # mov dx, 3D8 ; out
        code += bytes([0x42])                 # inc dx -> 3D9
        code += bytes([0xAC, 0xEE])           # lodsb (3D9_0) ; out
        # Wait active start
        code += bytes([0xBA, 0xDA, 0x03])     # mov dx, 0x3DA
        code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])  # wait_active
        code += bytes([0xBA, 0xD9, 0x03])     # mov dx, 0x3D9 (4c baseline)
        # In-line writes with this band's targets
        cycle_targets_band = band_targets[k]
        cycles_so_far = 4
        for i in range(N - 1):
            target_at_lodsb_start = cycle_targets_band[i] - 16
            delay_needed = target_at_lodsb_start - cycles_so_far
            if delay_needed < 0:
                # Allow small negatives by emitting no delay (will overshoot a bit)
                delay_bytes, actual_delay = b'', 0
            else:
                delay_bytes, actual_delay, _ = _emit_delay_smart(delay_needed)
            code += delay_bytes
            code += bytes([0xAC, 0xEE])       # lodsb ; out (3D9 seg i+1)
            cycles_so_far += actual_delay + 12 + 8
        # Wait hblank
        code += bytes([0xBA, 0xDA, 0x03])     # mov dx, 0x3DA
        code += bytes([0xEC, 0xA8, 0x01, 0x74, 0xFB])  # wait_hblank
        # dec bp; jnz band_loop
        code += bytes([0x4D])                 # dec bp
        line_disp = band_loop_off - (len(code) + 2)
        if -128 <= line_disp <= 127:
            code += bytes([0x75, line_disp & 0xFF])
        else:
            # Long-form
            code += bytes([0x74, 0x03])
            long_disp = band_loop_off - (len(code) + 3)
            code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])

    # Keypress check
    code += bytes([0xB4, 0x01, 0xCD, 0x16])
    jz_disp = display_loop_off - (len(code) + 2)
    if -128 <= jz_disp <= 127:
        code += bytes([0x74, jz_disp & 0xFF])
    else:
        code += bytes([0x75, 0x03])
        long_disp = display_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])

    # Cleanup
    code += bytes([0xB4, 0x00, 0xCD, 0x16])
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    code += bytes([0xC3])

    # Patch
    fb_off = 0x100 + len(code)
    data_off = fb_off + 16384
    code[fb_si_patch] = fb_off & 0xFF
    code[fb_si_patch + 1] = (fb_off >> 8) & 0xFF
    code[data_si_patch] = data_off & 0xFF
    code[data_si_patch + 1] = (data_off >> 8) & 0xFF

    return bytes(code) + vram16k_from_indices(indices) + data_table


def vram16k_from_indices(indices):
    """Convenience: pack indices to 16K VRAM (alias for pack_cga_320_vram_from_indices)."""
    return pack_cga_320_vram_from_indices(indices)





def render_calibration_preview(N, cycle_correction=0):
    """Render a software-only preview of what the calibration COM should display
    if cycle math is exact. Use this to compare against the actual DOSBox-X output.
    """
    seg_palettes = [_CALIBRATION_PALETTES[i % len(_CALIBRATION_PALETTES)] for i in range(N)]
    seg_starts = _calibration_segment_starts(N, 320)

    img = np.zeros((200, 320, 3), dtype=np.uint8)
    indices = np.full((200, 320), 1, dtype=np.uint8)
    for i in range(1, N):
        b = seg_starts[i]
        for col in (b - 2, b - 1, b, b + 1):
            if 0 <= col < 320:
                indices[:, col] = 0
    for col in range(0, 320, 10):
        indices[0:2, col] = 0

    for s in range(N):
        x0, x1 = seg_starts[s], seg_starts[s + 1]
        pal_rgb = seg_palettes[s]
        for x in range(x0, x1):
            for y in range(200):
                img[y, x] = pal_rgb[indices[y, x]]

    return Image.fromarray(img, "RGB")


# --- Whole-frame cycle-counted N-segment builder ----------------------------
#
# This is an alternative to build_com_320_mode_switch_n that polls only ONCE
# per frame (at vsync) instead of once per scanline. After the vsync poll, every
# scanline takes exactly 304 cycles by precise cycle accounting — no more
# per-line poll jitter.
#
# Trade-off:
#   - Per-line polling jitter (0..39 cycles per line, independent per line) is
#     replaced by per-FRAME polling jitter (0..39 cycles, shared across all 200
#     lines). Within a frame, all boundaries shift TOGETHER. Frame-to-frame, the
#     whole image shifts as a unit. This looks much cleaner than per-line jitter.
#   - Drift accumulation: we trust the cycle math for 200*304 = 60800 cycles. Any
#     systematic per-iteration error of 1c becomes 200c (~1 scanline) drift over
#     the frame. We use _emit_delay_exact for sub-cycle accuracy to minimize this.
#   - DRAM refresh stalls (4c every ~72c on real 8088) are unmodeled. On real
#     hardware this adds ~12c of variance per scanline. DOSBox-X's modeling of
#     refresh depends on `cycles=` config.
#
# Architecture:
#   1. push cs ; pop ds ; mode 04h ; copy framebuffer to B800 (one-time setup)
#   2. display_loop: vsync poll (3 edges of bit 3)
#   3. During back porch: write line 0's 3D8 + 3D9_seg0
#   4. wait_active_start (single poll) — this is the only per-frame timing reference
#   5. cycle_count_loop (200 iterations, exactly 304 cycles each):
#        - Pad to seg-1 boundary; write seg 1 of CURRENT line
#        - Pad to seg-2 boundary; write seg 2; ... (up to seg N-1)
#        - Pad to hblank-start (cycle 213 of current line)
#        - Write 3D8 + 3D9_seg0 for NEXT line
#        - Pad to (304 - dec_jnz_cost)
#        - dec bp ; jnz cycle_count_loop
#   6. Keypress check; loop or exit
#
# Data layout (v2):
#   - 2 prologue bytes: line 0's 3D8, line 0's 3D9_seg0
#   - 200 per-iteration records of (N+1) bytes each:
#       [seg1, seg2, ..., seg(N-1), next_3D8, next_seg0]
#     where "next" means line K+1 for iteration K (line K is the one being
#     displayed during this iteration's active period).
#   - Iteration 200's "next line" bytes are dummies (line 200 doesn't exist;
#     the writes happen during retrace and never affect display).
#   - Total: 2 + 200*(N+1) bytes.

# Constants for whole-frame timing (CGA mode 04h)
_WF_CYCLES_PER_SCANLINE = 304    # 4.77MHz / 15.7kHz hsync
_WF_HBLANK_START_CYCLE = 213     # last 91 cycles of each scanline are hblank
_WF_DEC_BP_JNZ_COST = 19         # dec bp (3) + jnz taken (16)


def build_n_segment_data_table_v2(pals_by_y, N) -> tuple:
    """Build the v2 layout data table consumed by build_com_320_mode_switch_n_whole_frame.

    Layout: 2 prologue bytes (line 0 3D8, seg0) + 200 iteration records.
    Each iteration record (N+1 bytes): [seg1..segN-1 of current line, 3D8 of next, seg0 of next].

    Returns (bytes, mode_mismatch_count) where mismatches are lines that had
    mixed mode 04h/05h segments and got forced to mode 04h (same fallback as v1).
    """
    if N < 2:
        raise ValueError(f"v2 builder requires N>=2, got {N}")
    if len(pals_by_y) != 200:
        raise ValueError(f"Expected 200 lines, got {len(pals_by_y)}")

    # Convert each line's palettes to (3D8, [3D9 per segment])
    line_regs = []
    mismatches = 0
    for y in range(200):
        line_pals = pals_by_y[y]
        if len(line_pals) != N:
            raise ValueError(f"Line {y} has {len(line_pals)} segments, expected {N}")
        regs = [palette_to_cga_regs(p) for p in line_pals]
        modes = set(m for m, _ in regs)
        if len(modes) == 1:
            line_regs.append((next(iter(modes)), [c for _, c in regs]))
        else:
            mismatches += 1
            seg_3d9s = []
            for p in line_pals:
                bg_idx = _nearest_cga_index(p[0])
                fg_idxs = frozenset(_nearest_cga_index(c) for c in p[1:4])
                best_score = -1
                best_bits = (0, 1)
                for bits, expected in _CGA_MODE04_FG_SETS.items():
                    score = len(fg_idxs & expected)
                    if score > best_score:
                        best_score = score
                        best_bits = bits
                pal_bit, int_bit = best_bits
                seg_3d9s.append((bg_idx & 0x0F) | ((int_bit & 1) << 4) | ((pal_bit & 1) << 5))
            line_regs.append((_CGA_MODE_3D8_MODE04, seg_3d9s))

    out = bytearray()
    # Prologue: line 0's 3D8 + seg0
    out.append(line_regs[0][0])
    out.append(line_regs[0][1][0])
    # Per-iteration records
    for K in range(200):
        # Iteration K+1 displays line K. Record contains:
        #   line K's seg1..segN-1, then line K+1's 3D8, seg0
        for i in range(1, N):
            out.append(line_regs[K][1][i])
        if K < 199:
            out.append(line_regs[K + 1][0])
            out.append(line_regs[K + 1][1][0])
        else:
            # Dummy "next line" bytes for last iteration
            out.append(_CGA_MODE_3D8_MODE04)
            out.append(0x00)
    return (bytes(out), mismatches)


def build_com_320_mode_switch_n_whole_frame(vram16k, data_table_v2, N,
                                              cycle_correction=0):
    """Build a DOS .COM that displays a 320x200 image with N palette segments per line,
    using whole-frame cycle-counted timing (no per-line polling).

    Args:
        vram16k: 16384-byte CGA mode-04h framebuffer
        data_table_v2: 2 + 200*(N+1) bytes from build_n_segment_data_table_v2
        N: 2..8 segments per scanline
        cycle_correction: shifts in-line write boundaries by this many cycles

    Returns: bytes, the .COM file
    """
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    if len(vram16k) != 16384:
        raise ValueError(f"vram16k must be 16384 bytes, got {len(vram16k)}")
    expected_data = 2 + 200 * (N + 1)
    if len(data_table_v2) != expected_data:
        raise ValueError(f"data_table_v2 must be {expected_data} bytes, got {len(data_table_v2)}")

    cycle_targets = _plan_n_segment_cycle_targets(N, 320)
    if cycle_correction != 0:
        cycle_targets = [t + cycle_correction for t in cycle_targets]

    code = bytearray()

    # ---- One-time setup ----
    code += bytes([0x0E, 0x1F])                       # push cs ; pop ds
    code += bytes([0xB8, 0x04, 0x00, 0xCD, 0x10])     # mov ax,4 ; int 10h (mode 04)
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])     # mov ax,B800 ; mov es,ax
    code += bytes([0x31, 0xFF])                       # xor di, di
    fb_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])                 # mov si, FB_OFFSET (patched)
    code += bytes([0xB9, 0x00, 0x20])                 # mov cx, 0x2000
    code += bytes([0xFC, 0xF3, 0xA5])                 # cld ; rep movsw

    # ---- Display loop ----
    display_loop_off = len(code)
    code += bytes([0xBA, 0xDA, 0x03])                 # mov dx, 0x3DA
    # vsync_wait_1 (jnz to self while bit3=1)
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])     # vsync_wait_2 (jz)
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])     # vsync_wait_3 (jnz)

    # We're in vertical back porch. Pre-load SI and write line 0's 3D8 + seg0.
    data_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])                 # mov si, DATA_OFFSET (patched)
    code += bytes([0xAC])                             # lodsb (line 0 3D8)
    code += bytes([0xBA, 0xD8, 0x03, 0xEE])           # mov dx, 0x3D8 ; out
    code += bytes([0x42])                             # inc dx -> 0x3D9
    code += bytes([0xAC, 0xEE])                       # lodsb (seg0) ; out

    # Wait for line 0 active to start (THE ONLY per-frame timing reference)
    code += bytes([0xBA, 0xDA, 0x03])                 # mov dx, 0x3DA
    code += bytes([0xEC, 0xA8, 0x01, 0x75, 0xFB])     # wait_active_start (jnz while bit0=1)

    # Set DX = 0x3D9 for in-line writes; init line counter
    code += bytes([0xBA, 0xD9, 0x03])                 # mov dx, 0x3D9
    code += bytes([0xBD, 0xC8, 0x00])                 # mov bp, 200

    # ---- Cycle-counted line loop (exactly 304 cycles per iteration) ----
    cycle_count_loop_off = len(code)
    cycles_so_far = 0  # cycles consumed within this iteration

    # In-active writes: segments 1..N-1 of current line
    for i in range(N - 1):
        target_lodsb_start = cycle_targets[i] - 16  # OUT commits ~12+4 cycles after lodsb start
        delay_needed = target_lodsb_start - cycles_so_far
        if delay_needed < 0:
            raise RuntimeError(
                f"Whole-frame N={N} seg {i+1}: delay budget exhausted "
                f"(needed {delay_needed} cycles)")
        delay_bytes, actual = _emit_delay_exact(delay_needed)
        code += delay_bytes
        cycles_so_far += actual
        code += bytes([0xAC, 0xEE])                   # lodsb ; out (3D9 seg i+1)
        cycles_so_far += 12 + 8

    # Pad to start of hblank (cycle 213 of this line)
    delay_needed = _WF_HBLANK_START_CYCLE - cycles_so_far
    if delay_needed < 0:
        raise RuntimeError(
            f"Whole-frame N={N}: in-line writes overran hblank start "
            f"(at cycle {cycles_so_far}, hblank starts at {_WF_HBLANK_START_CYCLE})")
    delay_bytes, actual = _emit_delay_exact(delay_needed)
    code += delay_bytes
    cycles_so_far += actual

    # During hblank: write NEXT line's 3D8 + 3D9_seg0
    code += bytes([0xBA, 0xD8, 0x03])                 # mov dx, 0x3D8
    code += bytes([0xAC, 0xEE])                       # lodsb (next 3D8) ; out
    code += bytes([0x42])                             # inc dx -> 0x3D9
    code += bytes([0xAC, 0xEE])                       # lodsb (next seg0) ; out
    cycles_so_far += 4 + 12 + 8 + 2 + 12 + 8          # = 46

    # Pad to (304 - dec_bp_jnz_cost = 285)
    delay_needed = _WF_CYCLES_PER_SCANLINE - _WF_DEC_BP_JNZ_COST - cycles_so_far
    if delay_needed < 0:
        raise RuntimeError(
            f"Whole-frame N={N}: hblank writes overran scanline budget "
            f"(at cycle {cycles_so_far}, dec/jnz needs {_WF_DEC_BP_JNZ_COST} more)")
    delay_bytes, actual = _emit_delay_exact(delay_needed)
    code += delay_bytes
    cycles_so_far += actual

    # dec bp ; jnz cycle_count_loop
    code += bytes([0x4D])                             # dec bp (3c)
    line_disp = cycle_count_loop_off - (len(code) + 2)
    if -128 <= line_disp <= 127:
        code += bytes([0x75, line_disp & 0xFF])       # jnz short (16c taken / 4c not)
    else:
        # Long-form
        code += bytes([0x74, 0x03])                   # jz +3
        long_disp = cycle_count_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])
    cycles_so_far += 3 + 16   # nominal: dec + jnz taken

    # Sanity: cycles_so_far should equal 304 exactly
    if cycles_so_far != _WF_CYCLES_PER_SCANLINE:
        raise RuntimeError(
            f"Whole-frame N={N}: cycle accounting off by "
            f"{cycles_so_far - _WF_CYCLES_PER_SCANLINE} cycles per iteration "
            f"(actual {cycles_so_far}, target {_WF_CYCLES_PER_SCANLINE})")

    # ---- After loop: keypress check, then exit or repeat ----
    code += bytes([0xB4, 0x01, 0xCD, 0x16])           # mov ah,1 ; int 16h
    jz_disp = display_loop_off - (len(code) + 2)
    if -128 <= jz_disp <= 127:
        code += bytes([0x74, jz_disp & 0xFF])
    else:
        code += bytes([0x75, 0x03])
        long_disp = display_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])

    code += bytes([0xB4, 0x00, 0xCD, 0x16])           # consume key
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])     # text mode
    code += bytes([0xC3])                             # ret

    # Patch FB and DATA offsets
    fb_off = 0x100 + len(code)
    data_off = fb_off + 16384
    code[fb_si_patch] = fb_off & 0xFF
    code[fb_si_patch + 1] = (fb_off >> 8) & 0xFF
    code[data_si_patch] = data_off & 0xFF
    code[data_si_patch + 1] = (data_off >> 8) & 0xFF

    return bytes(code) + vram16k + data_table_v2


def build_calibration_whole_frame_n_seg(N, cycle_correction=0):
    """Calibration COM using whole-frame cycle counting. Same boundary-ruler image
    as build_calibration_boundary_ruler_n_seg, but with the new architecture.

    If this version DOESN'T flicker but the per-line-poll version DID, the
    diagnosis is confirmed: per-line polling jitter was the problem.
    """
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    seg_palettes = [_CALIBRATION_PALETTES[i % len(_CALIBRATION_PALETTES)] for i in range(N)]
    pals_by_y = [seg_palettes] * 200

    indices = np.full((200, 320), 1, dtype=np.uint8)
    seg_starts = _calibration_segment_starts(N, 320)
    for i in range(1, N):
        b = seg_starts[i]
        for col in (b - 2, b - 1, b, b + 1):
            if 0 <= col < 320:
                indices[:, col] = 0
    for col in range(0, 320, 10):
        indices[0:2, col] = 0

    data_v2, _ = build_n_segment_data_table_v2(pals_by_y, N)
    vram = pack_cga_320_vram_from_indices(indices)
    return build_com_320_mode_switch_n_whole_frame(vram, data_v2, N,
                                                     cycle_correction=cycle_correction)


def build_calibration_static_whole_frame(N=4):
    """Same-palette test for whole-frame timing. Should display a perfectly stable
    solid green field if the cycle-counted code path itself is sound."""
    pal = _CALIBRATION_PALETTES[0]
    seg_palettes = [pal] * N
    pals_by_y = [seg_palettes] * 200
    indices = np.full((200, 320), 1, dtype=np.uint8)
    data_v2, _ = build_n_segment_data_table_v2(pals_by_y, N)
    vram = pack_cga_320_vram_from_indices(indices)
    return build_com_320_mode_switch_n_whole_frame(vram, data_v2, N)


def build_com_320_mode_switch_n_whole_frame_constdelay(vram16k, data_table_v2, N,
                                                         vsync_end_to_active_cycles,
                                                         cycle_correction=0):
    """Variant that replaces the wait_active_start poll with a constant-cycle delay
    from vsync end. This eliminates ALL polling after vsync_wait_3.

    If frame-level flicker disappears with this builder (vs the polling version),
    the active_start poll is the jitter source. If it persists, the jitter is
    coming from something else (DRAM refresh, prefetch effects, etc.).

    vsync_end_to_active_cycles: how many CPU cycles to wait between vsync end
       and line 0 active start. Standard CGA: ~9120c (30 back-porch lines * 304c).
       This will need calibration per host emulator.
    """
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    if len(vram16k) != 16384:
        raise ValueError(f"vram16k must be 16384 bytes, got {len(vram16k)}")
    expected_data = 2 + 200 * (N + 1)
    if len(data_table_v2) != expected_data:
        raise ValueError(f"data_table_v2 must be {expected_data} bytes, got {len(data_table_v2)}")

    cycle_targets = _plan_n_segment_cycle_targets(N, 320)
    if cycle_correction != 0:
        cycle_targets = [t + cycle_correction for t in cycle_targets]

    code = bytearray()
    code += bytes([0x0E, 0x1F])
    code += bytes([0xB8, 0x04, 0x00, 0xCD, 0x10])
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])
    code += bytes([0x31, 0xFF])
    fb_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])
    code += bytes([0xB9, 0x00, 0x20])
    code += bytes([0xFC, 0xF3, 0xA5])

    display_loop_off = len(code)
    code += bytes([0xBA, 0xDA, 0x03])
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])

    # vsync_wait_3 just exited. Now: skip the active_start poll and do a constant
    # cycle-counted delay until line 0 active start.

    data_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])              # mov si, DATA_OFFSET (4c)
    code += bytes([0xAC])                          # lodsb (line 0 3D8) (12c)
    code += bytes([0xBA, 0xD8, 0x03, 0xEE])        # mov dx,0x3D8 ; out (4+8c)
    code += bytes([0x42])                          # inc dx (2c)
    code += bytes([0xAC, 0xEE])                    # lodsb (seg0) ; out (12+8c)
    # cycles consumed since vsync_end exit: 4+12+4+8+2+12+8 = 50

    # We need to land at "cycle 0 of cycle_count_loop iteration 1" = exactly 4c
    # before the first lodsb of iteration 1 (the mov dx,0x3D9 at start of loop).
    # If we want iteration 1 to start at "actual line 0 active start", and we
    # entered vsync_wait_3 exit at vsync_end_to_active_cycles before active start,
    # then total delay needed before mov dx,0x3D9 = vsync_end_to_active_cycles - 4.
    # Currently consumed 50 cycles since vsync_wait_3 exit. So pad needed:
    #   pad_cycles = (vsync_end_to_active_cycles - 4) - 50

    pad_cycles = vsync_end_to_active_cycles - 4 - 50
    if pad_cycles < 0:
        raise ValueError(
            f"vsync_end_to_active_cycles={vsync_end_to_active_cycles} too small; "
            f"already consumed 50 cycles for setup writes")
    # Use LOOP for the bulk delay (since it's large), no clobber concern outside loop
    # CX is free at this point.
    delay_bytes, actual_delay, _ = _emit_delay_smart(pad_cycles, prefer_no_clobber=False)
    code += delay_bytes

    code += bytes([0xBA, 0xD9, 0x03])              # mov dx, 0x3D9 (4c)
    code += bytes([0xBD, 0xC8, 0x00])              # mov bp, 200 (4c)

    # ---- Cycle-counted line loop (304c per iteration, identical to original) ----
    cycle_count_loop_off = len(code)
    cycles_so_far = 0

    for i in range(N - 1):
        target_lodsb_start = cycle_targets[i] - 16
        delay_needed = target_lodsb_start - cycles_so_far
        if delay_needed < 0:
            raise RuntimeError(f"seg {i+1} delay budget exhausted")
        delay_bytes, actual = _emit_delay_exact(delay_needed)
        code += delay_bytes
        cycles_so_far += actual
        code += bytes([0xAC, 0xEE])
        cycles_so_far += 20

    delay_needed = _WF_HBLANK_START_CYCLE - cycles_so_far
    if delay_needed < 0:
        raise RuntimeError("hblank pad overrun")
    delay_bytes, actual = _emit_delay_exact(delay_needed)
    code += delay_bytes
    cycles_so_far += actual

    code += bytes([0xBA, 0xD8, 0x03])
    code += bytes([0xAC, 0xEE])
    code += bytes([0x42])
    code += bytes([0xAC, 0xEE])
    cycles_so_far += 4 + 12 + 8 + 2 + 12 + 8

    delay_needed = _WF_CYCLES_PER_SCANLINE - _WF_DEC_BP_JNZ_COST - cycles_so_far
    if delay_needed < 0:
        raise RuntimeError("final pad overrun")
    delay_bytes, actual = _emit_delay_exact(delay_needed)
    code += delay_bytes
    cycles_so_far += actual

    code += bytes([0x4D])
    line_disp = cycle_count_loop_off - (len(code) + 2)
    if -128 <= line_disp <= 127:
        code += bytes([0x75, line_disp & 0xFF])
    else:
        code += bytes([0x74, 0x03])
        long_disp = cycle_count_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])
    cycles_so_far += 19

    if cycles_so_far != _WF_CYCLES_PER_SCANLINE:
        raise RuntimeError(
            f"const-delay variant: per-iteration cycles {cycles_so_far} != 304")

    code += bytes([0xB4, 0x01, 0xCD, 0x16])
    jz_disp = display_loop_off - (len(code) + 2)
    if -128 <= jz_disp <= 127:
        code += bytes([0x74, jz_disp & 0xFF])
    else:
        code += bytes([0x75, 0x03])
        long_disp = display_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])

    code += bytes([0xB4, 0x00, 0xCD, 0x16])
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])
    code += bytes([0xC3])

    fb_off = 0x100 + len(code)
    data_off = fb_off + 16384
    code[fb_si_patch] = fb_off & 0xFF
    code[fb_si_patch + 1] = (fb_off >> 8) & 0xFF
    code[data_si_patch] = data_off & 0xFF
    code[data_si_patch + 1] = (data_off >> 8) & 0xFF

    return bytes(code) + vram16k + data_table_v2


def build_calibration_constdelay_n_seg(N, vsync_end_to_active_cycles=9120,
                                         cycle_correction=0):
    """Calibration COM using whole-frame timing WITHOUT active_start poll
    (constant cycle delay from vsync end). Tests whether eliminating the
    active_start poll removes residual frame-level flicker."""
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    seg_palettes = [_CALIBRATION_PALETTES[i % len(_CALIBRATION_PALETTES)] for i in range(N)]
    pals_by_y = [seg_palettes] * 200

    indices = np.full((200, 320), 1, dtype=np.uint8)
    seg_starts = _calibration_segment_starts(N, 320)
    for i in range(1, N):
        b = seg_starts[i]
        for col in (b - 2, b - 1, b, b + 1):
            if 0 <= col < 320:
                indices[:, col] = 0
    for col in range(0, 320, 10):
        indices[0:2, col] = 0

    data_v2, _ = build_n_segment_data_table_v2(pals_by_y, N)
    vram = pack_cga_320_vram_from_indices(indices)
    return build_com_320_mode_switch_n_whole_frame_constdelay(
        vram, data_v2, N,
        vsync_end_to_active_cycles=vsync_end_to_active_cycles,
        cycle_correction=cycle_correction)


def build_calibration_per_line_jitter_test(N=4):
    """Diagnostic image to distinguish frame-level shift vs per-line chaos."""
    return build_calibration_whole_frame_n_seg(N)


def build_calibration_perline_palette_only(N=4):
    """KEY DIAGNOSTIC: each line has a different (uniform) palette, but all N
    segments within a line are the SAME palette.

    This means the in-active 3D9 writes happen with the SAME value as the
    hblank seg0 write — the writes still occur (cycle-counted timing path is
    identical to WN4) but the value never changes within a line.

    Hypothesis matrix:
      - If this is STABLE: flicker comes from CHANGING 3D9 mid-scanline
        (the act of writing different values during active video). We then
        need a different architecture (e.g., write all 4 palettes during
        hblank using more registers or self-modifying code).
      - If this FLICKERS: the act of writing 3D9 during active video itself
        is the issue, regardless of the value being written. This points at
        DRAM-refresh interaction with the OUT instructions or an emulator
        artifact.
    """
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    palettes = _CALIBRATION_PALETTES  # 8 distinct calibration palettes
    pals_by_y = []
    for y in range(200):
        pal_idx = y % len(palettes)
        line_pal = palettes[pal_idx]
        pals_by_y.append([line_pal] * N)  # all N segments same

    # Image content: solid foreground with a simple grid of black markers
    indices = np.full((200, 320), 1, dtype=np.uint8)
    for col in range(0, 320, 16):
        indices[:, col] = 0
    for row in range(0, 200, 25):
        indices[row, :] = 0

    data_v2, _ = build_n_segment_data_table_v2(pals_by_y, N)
    vram = pack_cga_320_vram_from_indices(indices)
    return build_com_320_mode_switch_n_whole_frame(vram, data_v2, N)


def build_calibration_high_contrast_n_seg(N=4):
    """Same boundary-ruler image as WN4 but with maximum-contrast palettes
    (full white vs full black per segment) to make any flicker more visible.

    If the flicker is value-magnitude dependent, this should look WORSE.
    If similar to WN4, the flicker is not value-dependent."""
    if not (2 <= N <= 8):
        raise ValueError(f"N must be 2..8, got {N}")
    # High-contrast alternating palettes
    high_contrast = [
        ((0, 0, 0), (255, 255, 255), (170, 170, 170), (85, 85, 85)),    # B/W
        ((0, 0, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255)),    # bright cyan/magenta
        ((0, 0, 0), (255, 0, 0), (0, 255, 0), (255, 255, 0)),          # bright RGB
        ((85, 85, 85), (170, 170, 170), (0, 0, 0), (255, 255, 255)),   # mixed
        ((0, 170, 170), (170, 0, 170), (170, 170, 170), (0, 0, 0)),    # cyan/mag/gray
        ((170, 85, 0), (170, 170, 170), (0, 0, 0), (255, 255, 255)),    # brown/gray
        ((0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0)),
        ((0, 0, 0), (255, 255, 0), (0, 255, 255), (255, 0, 255)),
    ]
    seg_palettes = [high_contrast[i % len(high_contrast)] for i in range(N)]
    pals_by_y = [seg_palettes] * 200

    indices = np.full((200, 320), 1, dtype=np.uint8)
    seg_starts = _calibration_segment_starts(N, 320)
    for i in range(1, N):
        b = seg_starts[i]
        for col in (b - 2, b - 1, b, b + 1):
            if 0 <= col < 320:
                indices[:, col] = 0

    data_v2, _ = build_n_segment_data_table_v2(pals_by_y, N)
    vram = pack_cga_320_vram_from_indices(indices)
    return build_com_320_mode_switch_n_whole_frame(vram, data_v2, N)


def build_calibration_n2_only(use_constdelay=True):
    """Minimal test: N=2, single in-active write per line at cycle 107.
    Has the FEWEST possible in-active writes. If WN2 also flickers, the issue
    is that ANY in-active write causes problems. If WN2 is more stable than
    WN4/WN8, the problem scales with number of writes."""
    seg_palettes = [_CALIBRATION_PALETTES[0], _CALIBRATION_PALETTES[1]]
    pals_by_y = [seg_palettes] * 200

    indices = np.full((200, 320), 1, dtype=np.uint8)
    # Mark the boundary at column 160
    for col in (158, 159, 160, 161):
        indices[:, col] = 0

    data_v2, _ = build_n_segment_data_table_v2(pals_by_y, 2)
    vram = pack_cga_320_vram_from_indices(indices)
    if use_constdelay:
        return build_com_320_mode_switch_n_whole_frame_constdelay(
            vram, data_v2, 2, vsync_end_to_active_cycles=9120)
    else:
        return build_com_320_mode_switch_n_whole_frame(vram, data_v2, 2)


def build_palette_cycle_diag_com(initial_bx=4):
    """Build an INTERACTIVE palette-cycling diagnostic .COM.

    Continuously writes 3D9 palette values in a tight loop with NO scanline
    awareness — barrels straight through hsync. Each frame syncs once at
    vsync, then the inner loop runs ~1500 times writing palettes back-to-back.

    The delay between writes is controlled by BX:
        per-iteration cycle cost ≈ 41 + (17*BX - 12) cycles
        At ~1.5 pixels per cycle, that's the spacing between palette changes.

    Default BX=4 ≈ 95 cycles ≈ 142 pixels per palette change (~half a scanline).

    Interactive keys (during run):
        '+' or '='  : BX += 1 (~17 cycle / ~25 pixel finer step)
        '-' or '_'  : BX -= 1 (clamped to min 1)
        ']'         : BX += 16 (~272 cycle / ~408 pixel coarse step)
        '['         : BX -= 16 (clamped)
        'q', 'Q', ESC : quit

    On exit, switches to text mode and prints the final BX value, the
    equivalent CPU cycles per palette change, and approximate pixel spacing.

    The framebuffer is filled with byte 0x6C (pixels = 1,2,3,0 repeating),
    so all 4 palette colors are visible as a 4-pixel-wide vertical stripe
    pattern. As palettes cycle, you see colored bars of 4 colors each
    sweeping across the screen.
    """
    code = bytearray()

    # === Setup ===
    code += bytes([0x0E, 0x1F])                        # push cs ; pop ds
    code += bytes([0xB8, 0x04, 0x00, 0xCD, 0x10])      # mov ax,4 ; int 10h (mode 04)
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])      # mov ax,B800 ; mov es,ax

    # Fill framebuffer with 0x6C6C → byte 0x6C = pixels 01,10,11,00 = indices 1,2,3,0
    # (16-bit fill via stosw is twice as fast as 8-bit stosb)
    code += bytes([0x31, 0xFF])                        # xor di, di
    code += bytes([0xB8, 0x6C, 0x6C])                  # mov ax, 6C6Ch
    code += bytes([0xB9, 0x00, 0x20])                  # mov cx, 2000h (8K words)
    code += bytes([0xFC, 0xF3, 0xAB])                  # cld ; rep stosw

    # Set 3D8 to mode 04 (color burst on, 320x200 4-color, video on)
    code += bytes([0xBA, 0xD8, 0x03])                  # mov dx, 3D8h
    code += bytes([0xB0, 0x0A])                        # mov al, 0Ah
    code += bytes([0xEE])                              # out dx, al

    # Initialize BX = delay parameter
    code += bytes([0xBB, initial_bx & 0xFF, (initial_bx >> 8) & 0xFF])  # mov bx, init

    # === Main loop start ===
    main_loop_off = len(code)

    # Vsync wait (3 edges of bit 3 of 3DA). Interrupts OK during this — they
    # only affect the polling loop, which retries until vsync edge anyway.
    code += bytes([0xBA, 0xDA, 0x03])                  # mov dx, 3DAh
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])      # while bit 3 = 1
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])      # while bit 3 = 0
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])      # while bit 3 = 1

    # MASK INTERRUPTS for the timing-sensitive inner loop.
    # The 18.2 Hz timer interrupt (every ~55ms = ~3 frames) and any keyboard
    # interrupt would otherwise fire mid-loop and inject a ~50+ cycle stall,
    # destroying the regular palette-cycling rhythm. This is exactly the trick
    # reenigne uses at the top of his demos. We re-enable before INT 16h.
    code += bytes([0xFA])                              # cli

    # Set up DX = 3D9 for palette writes
    code += bytes([0xBA, 0xD9, 0x03])                  # mov dx, 3D9h

    # Inner loop counter (1500 iterations covers any reasonable BX)
    INNER_COUNT = 1500
    code += bytes([0xBD, INNER_COUNT & 0xFF, (INNER_COUNT >> 8) & 0xFF])  # mov bp

    # SI = palette table (will be patched)
    pal_si_init_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])                  # mov si, palette_table

    # === Inner loop ===
    inner_loop_off = len(code)
    code += bytes([0xAC])                              # lodsb (load palette byte)
    code += bytes([0xEE])                              # out dx, al (write 3D9)

    # Wrap SI when it reaches palette_end
    pal_end_patch = len(code) + 2
    code += bytes([0x81, 0xFE, 0x00, 0x00])            # cmp si, palette_end
    code += bytes([0x72, 0x03])                        # jb +3 (skip wrap)
    pal_start_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])                  # mov si, palette_start

    # Delay loop: mov cx, bx ; loop $-0
    code += bytes([0x89, 0xD9])                        # mov cx, bx
    code += bytes([0xE2, 0xFE])                        # loop $ (17*CX - 12 cycles total)

    # End of inner iteration: dec bp ; jnz inner
    code += bytes([0x4D])                              # dec bp
    inner_disp = inner_loop_off - (len(code) + 2)
    if -128 <= inner_disp <= 127:
        code += bytes([0x75, inner_disp & 0xFF])
    else:
        code += bytes([0x74, 0x03])                    # jz +3 (skip long jump)
        long_disp = inner_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])

    # === Re-enable interrupts before talking to BIOS ===
    code += bytes([0xFB])                              # sti

    # === Check keyboard ===
    code += bytes([0xB4, 0x01, 0xCD, 0x16])            # mov ah,1 ; int 16h (peek)
    main_back_disp = main_loop_off - (len(code) + 2)
    if -128 <= main_back_disp <= 127:
        code += bytes([0x74, main_back_disp & 0xFF])   # jz main_loop (no key)
    else:
        code += bytes([0x75, 0x03])                    # jnz +3
        long_disp = main_loop_off - (len(code) + 3)
        code += bytes([0xE9, long_disp & 0xFF, (long_disp >> 8) & 0xFF])

    # Got a key. Read it (consumes from buffer).
    code += bytes([0xB4, 0x00, 0xCD, 0x16])            # mov ah,0 ; int 16h (AL=ASCII)

    # === Key handling ===
    quit_patches = []

    # ESC (1Bh) → quit
    code += bytes([0x3C, 0x1B])
    code += bytes([0x74, 0x00])
    quit_patches.append(len(code) - 1)

    # 'q' (71h) → quit
    code += bytes([0x3C, 0x71])
    code += bytes([0x74, 0x00])
    quit_patches.append(len(code) - 1)

    # 'Q' (51h) → quit
    code += bytes([0x3C, 0x51])
    code += bytes([0x74, 0x00])
    quit_patches.append(len(code) - 1)

    # Action blocks
    inc_block = bytes([0x43])                          # inc bx
    dec_block = bytes([0x83, 0xFB, 0x01, 0x76, 0x01, 0x4B])  # cmp bx,1 ; jbe +1 ; dec bx
    inc16_block = bytes([0x83, 0xC3, 0x10])            # add bx, 16
    dec16_block = bytes([0x83, 0xFB, 0x11, 0x76, 0x03, 0x83, 0xEB, 0x10])  # cmp bx,17 ; jbe +3 ; sub bx,16

    handled_jumps = []  # patch list for "jmp do_handled"

    def emit_kbd_handler(key_char, action_bytes):
        # cmp al, key_char ; jnz +X ; <action> ; jmp short do_handled
        nonlocal code, handled_jumps
        code += bytes([0x3C, key_char])
        skip = len(action_bytes) + 2  # skip action + 2-byte jmp
        code += bytes([0x75, skip])
        code += action_bytes
        code += bytes([0xEB, 0x00])  # jmp short (patched)
        handled_jumps.append(len(code) - 1)

    emit_kbd_handler(0x2B, inc_block)    # '+'
    emit_kbd_handler(0x3D, inc_block)    # '='
    emit_kbd_handler(0x2D, dec_block)    # '-'
    emit_kbd_handler(0x5F, dec_block)    # '_'
    emit_kbd_handler(0x5D, inc16_block)  # ']'
    emit_kbd_handler(0x5B, dec16_block)  # '['

    # Default fall-through: do_handled
    do_handled_off = len(code)
    for off in handled_jumps:
        disp = do_handled_off - (off + 1)
        if not (-128 <= disp <= 127):
            raise RuntimeError(f"Handled jump out of range: {disp}")
        code[off] = disp & 0xFF

    # do_handled: jmp main_loop (long form)
    handled_disp = main_loop_off - (len(code) + 3)
    code += bytes([0xE9, handled_disp & 0xFF, (handled_disp >> 8) & 0xFF])

    # === do_quit ===
    do_quit_off = len(code)
    for off in quit_patches:
        disp = do_quit_off - (off + 1)
        if not (-128 <= disp <= 127):
            raise RuntimeError(f"Quit jump out of range: {disp}")
        code[off] = disp & 0xFF

    # Re-enable interrupts (in case we somehow got here with CLI active)
    code += bytes([0xFB])                              # sti

    # Switch to text mode 03h
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])      # mov ax,3 ; int 10h

    # Print "Final BX = "
    msg1_patch = len(code) + 1
    code += bytes([0xBA, 0x00, 0x00])                  # mov dx, msg1
    code += bytes([0xB4, 0x09, 0xCD, 0x21])            # int 21h AH=9 (print $-string)

    # Print BX in decimal:
    #   AX = BX
    #   CX = 0 (digit count)
    #   loop: divide AX by 10, push remainder, inc CX, until AX==0
    #   pop and print CX times
    code += bytes([0x53])                              # push bx (save BX)
    code += bytes([0x8B, 0xC3])                        # mov ax, bx
    code += bytes([0x31, 0xC9])                        # xor cx, cx

    div_loop_off = len(code)
    code += bytes([0x31, 0xD2])                        # xor dx, dx
    code += bytes([0xBE, 0x0A, 0x00])                  # mov si, 10
    code += bytes([0xF7, 0xF6])                        # div si (DX:AX / SI)
    code += bytes([0x52])                              # push dx (digit)
    code += bytes([0x41])                              # inc cx
    code += bytes([0x09, 0xC0])                        # or ax, ax
    div_back = div_loop_off - (len(code) + 2)
    code += bytes([0x75, div_back & 0xFF])             # jnz div_loop

    print_digit_off = len(code)
    code += bytes([0x5A])                              # pop dx
    code += bytes([0x80, 0xC2, 0x30])                  # add dl, '0'
    code += bytes([0xB4, 0x02, 0xCD, 0x21])            # mov ah,2 ; int 21h (print DL)
    print_back = print_digit_off - (len(code) + 2)
    code += bytes([0xE2, print_back & 0xFF])           # loop print_digit

    code += bytes([0x5B])                              # pop bx (restore)

    # Print "\r\nPress any key to exit\r\n"
    msg2_patch = len(code) + 1
    code += bytes([0xBA, 0x00, 0x00])                  # mov dx, msg2
    code += bytes([0xB4, 0x09, 0xCD, 0x21])

    # Wait for key
    code += bytes([0xB4, 0x00, 0xCD, 0x16])            # int 16h AH=0

    # Exit cleanly
    code += bytes([0xB4, 0x4C, 0xCD, 0x21])            # mov ah,4Ch ; int 21h

    # === Data ===

    # Palette table (4 distinct CGA mode-04h palettes for 3D9)
    # 0x00 = palette 0 low  (bg=black, fg=green/red/brown)
    # 0x10 = palette 0 high (bg=black, fg=lt-green/lt-red/yellow)
    # 0x20 = palette 1 low  (bg=black, fg=cyan/magenta/lt-gray)
    # 0x30 = palette 1 high (bg=black, fg=lt-cyan/lt-magenta/white)
    palette_data = bytes([0x00, 0x10, 0x20, 0x30])
    pal_off_in_seg = 0x100 + len(code)
    pal_end_off_in_seg = pal_off_in_seg + len(palette_data)
    code += palette_data

    code[pal_si_init_patch:pal_si_init_patch + 2] = bytes([
        pal_off_in_seg & 0xFF, (pal_off_in_seg >> 8) & 0xFF])
    code[pal_end_patch:pal_end_patch + 2] = bytes([
        pal_end_off_in_seg & 0xFF, (pal_end_off_in_seg >> 8) & 0xFF])
    code[pal_start_patch:pal_start_patch + 2] = bytes([
        pal_off_in_seg & 0xFF, (pal_off_in_seg >> 8) & 0xFF])

    # Messages
    msg1 = b"Final BX = $"
    msg1_off_in_seg = 0x100 + len(code)
    code += msg1
    code[msg1_patch:msg1_patch + 2] = bytes([
        msg1_off_in_seg & 0xFF, (msg1_off_in_seg >> 8) & 0xFF])

    msg2 = b"\r\nPress any key to exit\r\n$"
    msg2_off_in_seg = 0x100 + len(code)
    code += msg2
    code[msg2_patch:msg2_patch + 2] = bytes([
        msg2_off_in_seg & 0xFF, (msg2_off_in_seg >> 8) & 0xFF])

    return bytes(code)



def cga_color_select_for_320_palette_name(palette_name: str, bg_name: str = None) -> int:
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

    # Background nibble
    bg_idx = 0
    if bg_name is None:
        # Backward compatibility: allow old names like "... (bg=Blue)"
        m = re.search(r"\(bg=([^)]+)\)", palette_name)
        if m:
            bg_name = m.group(1).strip()
    if bg_name and bg_name in CGA_COLOR_NAMES:
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
    strength: 0.0..3.0 (clamped). 1.0 is "natural" amplitude; higher pushes
              the dither pattern more aggressively. The GUI Scale enforces 0..3.
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

_CHAR_GLYPHS = None  # legacy global; kept for backwards-compat with any external code


def ensure_char_glyphs():
    """Return the parsed 256x8 CGA ROM font masks."""
    return _CGA_FONT

def quantize_char16_textblock_from_indices(pre_indices, subsample=False, progress_cb=None):
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
        if progress_cb and (row % 2 == 0):
            try:
                progress_cb(row / max(1, num_rows))
            except Exception:
                pass
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



# --- 80x100 (4352 Colors) HiColor (8x2 block) mode -----------------------------------------

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

# Pixel-art upscalers (pure Python, no external deps)
#
# These are intentionally conservative implementations designed to preserve hard
# edges when upscaling low-res / pixel-art sources before CGA quantization.
#
# Important:
# - Canonical xBR and hqNx implementations are quite large and typically shipped
#   as optimized C/C++ code. For this project we implement *practical* variants
#   that capture the spirit: edge-aware neighbor selection with optional simple
#   blending.
# - These are only applied when the requested operation is an integer upscale
#   (2x/3x/4x). Otherwise we fall back to Pillow resamplers.


def _rgb_to_int(p):
    return (int(p[0]) << 16) | (int(p[1]) << 8) | int(p[2])


def _int_to_rgb(v):
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


def _blend(a, b, t_num, t_den):
    """Blend two packed RGB ints with ratio t_num/t_den toward b."""
    ar, ag, ab = _int_to_rgb(a)
    br, bg, bb = _int_to_rgb(b)
    r = (ar * (t_den - t_num) + br * t_num) // t_den
    g = (ag * (t_den - t_num) + bg * t_num) // t_den
    b2 = (ab * (t_den - t_num) + bb * t_num) // t_den
    return (r << 16) | (g << 8) | b2


def _color_close(a, b, thr=30):
    """Simple RGB distance threshold on packed ints."""
    ar, ag, ab = _int_to_rgb(a)
    br, bg, bb = _int_to_rgb(b)
    dr = ar - br
    dg = ag - bg
    db = ab - bb
    return (dr * dr + dg * dg + db * db) <= (thr * thr)


def _scale2x_core(src_int, w, h, blend_mode=False):
    """Scale2x/EPX core with optional diagonal blending."""
    dst_w, dst_h = w * 2, h * 2
    dst = [0] * (dst_w * dst_h)

    def at(x, y):
        x = 0 if x < 0 else (w - 1 if x >= w else x)
        y = 0 if y < 0 else (h - 1 if y >= h else y)
        return src_int[y * w + x]

    for y in range(h):
        for x in range(w):
            E = at(x, y)
            B = at(x, y - 1)
            D = at(x - 1, y)
            F = at(x + 1, y)
            H = at(x, y + 1)

            # Standard Scale2x rule
            if D == F and B != H:
                E0 = D
                E1 = F
            else:
                E0 = E
                E1 = E

            if B == H and D != F:
                E2 = B
                E3 = H
            else:
                E2 = E
                E3 = E

            # Optional "xBR-ish" diagonal blending: if one diagonal is strong
            # and the other is weak, bias the corner toward the diagonal.
            if blend_mode:
                A = at(x - 1, y - 1)
                C = at(x + 1, y - 1)
                G = at(x - 1, y + 1)
                I = at(x + 1, y + 1)
                # top-left corner
                if _color_close(A, E) and not _color_close(I, E):
                    E0 = _blend(E0, A, 1, 2)
                # top-right
                if _color_close(C, E) and not _color_close(G, E):
                    E1 = _blend(E1, C, 1, 2)
                # bottom-left
                if _color_close(G, E) and not _color_close(C, E):
                    E2 = _blend(E2, G, 1, 2)
                # bottom-right
                if _color_close(I, E) and not _color_close(A, E):
                    E3 = _blend(E3, I, 1, 2)

            ox = x * 2
            oy = y * 2
            dst[(oy) * dst_w + (ox)] = E0
            dst[(oy) * dst_w + (ox + 1)] = E1
            dst[(oy + 1) * dst_w + (ox)] = E2
            dst[(oy + 1) * dst_w + (ox + 1)] = E3

    return dst, dst_w, dst_h


def _pixel_upscale(img: Image.Image, algo: str, factor: int) -> Image.Image:
    """Integer pixel-art upscale (2x/3x/4x)."""
    factor = int(factor)
    if factor < 2:
        return img

    src = img.convert("RGB")
    w, h = src.size
    pix = list(src.getdata())
    src_int = [_rgb_to_int(p) for p in pix]

    algo = (algo or "").lower().strip()

    # xBR (practical variant): Scale2x w/ diagonal blending. For 3x/4x we
    # repeat 2x and then optionally resize with nearest to exact factor.
    if algo.startswith("xbr"):
        cur_int, cw, ch = src_int, w, h
        reps = 1
        if factor == 4:
            reps = 2
            factor2 = 2
        else:
            factor2 = factor
        for _ in range(reps):
            cur_int, cw, ch = _scale2x_core(cur_int, cw, ch, blend_mode=True)

        out = Image.new("RGB", (cw, ch))
        out.putdata([_int_to_rgb(v) for v in cur_int])
        if out.size != (w * factor, h * factor):
            out = out.resize((w * factor, h * factor), resample=getattr(Image, "Resampling", Image).NEAREST)
        return out

    # hqX (practical variant): Scale2x without blending (clean edges). We use
    # repeated 2x for 4x, and 2x + nearest for 3x.
    if algo.startswith("hq"):
        cur_int, cw, ch = src_int, w, h
        reps = 1
        if factor == 4:
            reps = 2
        for _ in range(reps):
            cur_int, cw, ch = _scale2x_core(cur_int, cw, ch, blend_mode=False)
        out = Image.new("RGB", (cw, ch))
        out.putdata([_int_to_rgb(v) for v in cur_int])
        if out.size != (w * factor, h * factor):
            out = out.resize((w * factor, h * factor), resample=getattr(Image, "Resampling", Image).NEAREST)
        return out

    return img


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




def apply_input_adjustments(img, brightness_val=0, contrast_val=0, r_gain_pct=100, g_gain_pct=100, b_gain_pct=100):
    """Apply brightness/contrast and RGB gain to the *input* image before any scaling/quantization.
    brightness_val, contrast_val: -100..100 (0 = no change)
    *_gain_pct: 0..200 (100 = no change)
    """
    status_dbg('ENTER apply_input_adjustments()')
    if img is None:
        return None
    # Work in RGB to keep pipelines consistent
    work = img.convert("RGB") if img.mode != "RGB" else img.copy()

    # Brightness / contrast
    if brightness_val != 0:
        bf = max(0.0, min(2.0, 1.0 + (brightness_val / 100.0)))
        work = ImageEnhance.Brightness(work).enhance(bf)
    if contrast_val != 0:
        cf = max(0.0, min(2.0, 1.0 + (contrast_val / 100.0)))
        work = ImageEnhance.Contrast(work).enhance(cf)

    # RGB gains
    rg = max(0.0, r_gain_pct / 100.0)
    gg = max(0.0, g_gain_pct / 100.0)
    bg = max(0.0, b_gain_pct / 100.0)
    if rg != 1.0 or gg != 1.0 or bg != 1.0:
        r, g, b = work.split()
        rlut = [min(255, max(0, int(i * rg + 0.5))) for i in range(256)]
        glut = [min(255, max(0, int(i * gg + 0.5))) for i in range(256)]
        blut = [min(255, max(0, int(i * bg + 0.5))) for i in range(256)]
        work = Image.merge("RGB", (r.point(rlut), g.point(glut), b.point(blut)))
    return work


def resize_with_mode(image, target_w, target_h, scale_mode, resample_name):
    """
    scale_mode:
      - "Fit (letterbox)" => preserve aspect, black bars
      - "Fill (crop)"     => preserve aspect, crop overflows
      - "Stretch"         => ignore aspect
    """
    # Extended scaling filters / pipelines
    # NOTE: filter_name must be defined before we choose a base resampler.
    filter_name = (resample_name or "").strip()

    # Base resampler used by non-pipeline modes and as fallback for pipeline modes.
    resample = get_resample_filter(filter_name or resample_name)
    src_w, src_h = image.size

    def _do_resize(img, size, base_resample):
        """Resize helper that supports pipeline filters beyond a single resampler."""
        tw, th = size
        # --- Pixel-art upscalers (xBR / hqNx) ---
        # These are only meaningful for integer *upscales*. We apply them first,
        # then (if needed) do a final correction resize with the base resampler.
        if filter_name.startswith("xBR") or filter_name.startswith("hq"):
            # Parse factor from the name, e.g. "xBR 2x", "hq4x"
            name_l = filter_name.lower().replace(" ", "")
            factor = 0
            for k in ("2x", "3x", "4x"):
                if k in name_l:
                    factor = int(k[0])
                    break

            if factor >= 2:
                scaled = _pixel_upscale(img, algo=filter_name, factor=factor)
                if scaled.size != (tw, th):
                    scaled = scaled.resize((tw, th), resample=base_resample)
                return scaled

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




# --- Staggered Mode Switch helpers ------------------------------------------
#
# When "staggered mode switch" is enabled, the segment boundaries (x-positions
# where the foreground color changes mid-scanline) shift by a uniform amount
# per scanline, producing diagonal seams instead of vertical seams. Reflective
# stagger means the offset bounces between 0 and a max value (so we never wrap
# around the right edge — segments stay coherent).
#
# Auto stagger step defaults to seg_w // 4. Max offset is capped at seg_w // 2
# so segments stay reasonably balanced (first segment grows to 1.5*seg_w, last
# shrinks to 0.5*seg_w at peak offset).
#
# Image-aware optimization searches a small set of candidate stagger steps and
# picks the one whose PASS-1 (palette selection only) quantization error is
# lowest for the given image. This matches the actual quantizer's objective.

def equal_segments(N, W):
    """Return base segments as (start, width) tuples, distributed as evenly as possible.

    Examples:
      equal_segments(6, 640) -> [(0,107),(107,107),(214,107),(321,107),(428,106),(534,106)]
      equal_segments(6, 320) -> [(0,54),(54,54),(108,53),(161,53),(214,53),(267,53)]
      equal_segments(4, 640) -> [(0,160),(160,160),(320,160),(480,160)]   (clean division)

    For N values that don't divide W exactly, the first (W mod N) segments get +1 width.
    Width imbalance is at most 1 pixel.
    """
    if N <= 0:
        return []
    base = W // N
    extra = W - base * N
    out = []
    pos = 0
    for i in range(N):
        w = base + (1 if i < extra else 0)
        out.append((pos, w))
        pos += w
    return out


def staggered_segments_at_offset(N, W, offset):
    """Build the visible stripes for a given per-line offset.

    Uses equal_segments() for the base partition (so segment widths are balanced
    even when N doesn't divide W). Offset shifts each segment's left edge by the
    same amount with cyclic wraparound.

    Returns a list of (x0, x1, logical_seg_idx) tuples in left-to-right order.
    Length is N when offset==0 (clean alignment), otherwise typically N+1 (the
    segment whose right edge crosses W is split into two stripes).
    """
    base_segs = equal_segments(N, W)
    if N <= 1 or offset == 0:
        return [(s, s + w, i) for i, (s, w) in enumerate(base_segs)]

    # Shifted lefts. Each entry: (shifted_x, logical_idx, width)
    shifted = [(((s + offset) % W), i, w) for i, (s, w) in enumerate(base_segs)]
    shifted.sort(key=lambda t: t[0])

    if shifted[0][0] == 0:
        # No wrap stripe needed — segments tile [0, W) cleanly even after rotation
        stripes = []
        for k in range(N):
            start, idx, _w = shifted[k]
            end = shifted[k + 1][0] if k + 1 < N else W
            stripes.append((start, end, idx))
        return stripes

    # Wrap stripe at the start [0, shifted[0][0]) belongs to the segment whose right
    # edge wrapped past W. With segment widths <= W/N + 1, exactly one segment wraps
    # at any given time — and it's the one with the LARGEST shifted_left (since its
    # right edge = shifted_left + width crosses W).
    wrap_seg_idx = shifted[-1][1]
    stripes = [(0, shifted[0][0], wrap_seg_idx)]
    for k in range(N):
        start, idx, _w = shifted[k]
        end = shifted[k + 1][0] if k + 1 < N else W
        stripes.append((start, end, idx))
    return stripes


def precompute_stagger_offsets(H, N, W, mode, stagger_step=None, seed=42):
    """Generate per-line stagger offsets for all H lines.

    Modes:
      "none" / None / falsy => zeros (no stagger)
      "triangle"            => reflective triangle wave 0 -> seg_w -> 0 -> seg_w -> 0 ...
      "random"              => independent random offset per line in [0, seg_w),
                               drawn from a seeded RNG so results are reproducible.

    NOTE: as of v153 the random mode uses precompute_stagger_layouts() instead, which
    produces jittered boundaries with no wraparound. This function is kept for backward
    compatibility and the triangle-mode code path.
    """
    if N <= 1 or not mode or mode == "none" or mode == "None":
        return [0] * H

    base_segs = equal_segments(N, W)
    # Use the LARGEST segment width as the "typical" seg_w for offset bounds. This way the
    # per-line offset never exceeds any single segment's width, keeping wraparound clean.
    seg_w = max((w for (_s, w) in base_segs), default=(W // max(1, N)))

    if mode == "triangle":
        if stagger_step is None or stagger_step <= 0:
            stagger_step = max(1, seg_w // 4)
        max_offset = seg_w
        K = max(1, max_offset // stagger_step)
        cycle = 2 * K
        offsets = []
        for y in range(H):
            p = y % cycle
            phase = p if p <= K else cycle - p
            offsets.append(min(max_offset, phase * stagger_step))
        return offsets

    if mode == "random":
        import random as _random
        rng = _random.Random(seed)
        return [rng.randint(0, max(0, seg_w - 1)) for _ in range(H)]

    return [0] * H


def precompute_stagger_layouts(H, N, W, mode, stagger_step=None, seed=42):
    """Return H per-line stripe layouts. Each is a list of (x0, x1, log_si) tuples.

    This is the new (v153) primary API for stagger. It unifies triangle and random
    modes under a single representation: each line is described directly by its
    visible stripes. Quantizers and the diagnostic strip both consume layouts[y]
    directly without separately computing offsets and stripes.

    Modes:
      "none"     => uniform partition for every line; exactly N stripes per line
      "triangle" => reflective triangle wave with cyclic wraparound; N or N+1 stripes
                    per line (the wrap stripe shares logical_seg_idx with the last)
      "random"   => independent jittered boundaries; EXACTLY N stripes per line
                    (no wraparound — interior boundaries jitter ±seg_w/2 around the
                    equal-partition positions, bounded to keep all segments non-empty)
    """
    base_segs = equal_segments(N, W)

    # No-stagger or N=1 — uniform partition every line
    if N <= 1 or not mode or mode in ("none", "None"):
        layout = [(s, s + w, i) for i, (s, w) in enumerate(base_segs)]
        return [list(layout) for _ in range(H)]

    if mode == "triangle":
        # Triangle wave with cyclic wraparound (sliding bands look)
        offsets = precompute_stagger_offsets(H, N, W, "triangle", stagger_step, seed)
        return [staggered_segments_at_offset(N, W, offsets[y]) for y in range(H)]

    if mode == "random":
        # Each line: jittered boundaries with NO wraparound. Exactly N stripes per line.
        # This matches the user-facing semantic: "N segments per line, randomly placed."
        return _random_jittered_layouts(H, N, W, seed)

    # Fallback
    layout = [(s, s + w, i) for i, (s, w) in enumerate(base_segs)]
    return [list(layout) for _ in range(H)]


def _random_jittered_layouts(H, N, W, seed):
    """Per-line layouts where the N-1 interior boundaries are jittered ±seg_w/2
    around their equal-partition positions, with bounds to keep segments non-empty.
    No wraparound. Each line's layout has EXACTLY N stripes.

    The jitter range is bounded to ensure adjacent boundaries can't cross, and the
    last segment can't shrink to zero.

    Segment widths after jitter range from ~seg_w/2 to ~3*seg_w/2 (a 3:1 width ratio).
    """
    import random as _random
    rng = _random.Random(seed)
    seg_w = W // N
    half = seg_w // 2 if seg_w >= 2 else 0
    layouts = []
    for _ in range(H):
        boundaries = [0]
        for k in range(1, N):
            center = k * seg_w
            lo = max(boundaries[-1] + 1, center - half)
            hi = min(W - (N - k), center + half)
            if hi <= lo:
                b = max(lo, min(hi, center))
                if b <= boundaries[-1]:
                    b = boundaries[-1] + 1
            else:
                b = rng.randint(lo, hi)
            boundaries.append(b)
        boundaries.append(W)
        layout = [(boundaries[i], boundaries[i + 1], i) for i in range(N)]
        layouts.append(layout)
    return layouts


# Backward-compat triangle-only entry point. Used by callers that only need triangle stagger.
def staggered_segments(y, N, W, stagger_step):
    """Return visible stripes for line y under triangle-wave stagger (legacy entry point)."""
    if stagger_step is None or stagger_step <= 0 or N <= 1:
        return staggered_segments_at_offset(N, W, 0)
    base_segs = equal_segments(N, W)
    seg_w = max((w for (_s, w) in base_segs), default=(W // max(1, N)))
    max_offset = seg_w
    K = max(1, max_offset // stagger_step)
    cycle = 2 * K
    p = y % cycle
    phase = p if p <= K else cycle - p
    offset = min(max_offset, phase * stagger_step)
    return staggered_segments_at_offset(N, W, offset)


def seg_for_x_from_segments(stripes, W):
    """Return a list of length W where seg_for_x[x] is the logical segment owning pixel x."""
    seg_for_x = [0] * W
    for (x0, x1, log_si) in stripes:
        for x in range(x0, x1):
            seg_for_x[x] = log_si
    return seg_for_x


# --- Backward-compat shim ---------------------------------------------------
# v149/v150 had a staggered_boundaries() that returned N+1 boundary positions.
# Code that calls it externally can keep using it (returns uniform boundaries
# with the offset cap at seg_w/2), but the internal quantizer now uses the
# wraparound semantics via staggered_segments() above.
def staggered_boundaries(y, N, W, stagger_step):
    """Legacy shim: returns the N+1 boundary positions for the visible stripes.
    Note: with wraparound, there can be N+2 boundaries (one extra for the wrap-stripe
    at the start). Callers that need the full topology should use staggered_segments().
    """
    seg_w = W // N
    if stagger_step <= 0 or N <= 1:
        return [k * seg_w for k in range(N)] + [W]
    stripes = staggered_segments(y, N, W, stagger_step)
    bounds = [s[0] for s in stripes] + [W]
    return bounds


def _stagger_step_candidates(seg_w):
    """Return the candidate stagger steps tried by image-aware optimization."""
    raw = {max(1, seg_w // d) for d in (8, 6, 4, 3, 2)}
    return sorted(raw)


def find_best_stagger_step_640(image_rgb, N, W=640, H=200):
    """Search candidate stagger steps for the 640x200 2-color mode switch.

    Returns the stagger_step that minimizes total PASS-1 (palette-selection)
    quantization error across the image. NumPy-vectorized.
    """
    if N <= 1:
        return 1

    arr = np.asarray(image_rgb.convert("RGB"), dtype=np.float32)  # (H, W, 3)
    if arr.shape[0] != H or arr.shape[1] != W:
        # Caller is expected to have resized; this is just a safety guard.
        from PIL import Image as _PI
        image_rgb = image_rgb.resize((W, H), _PI.LANCZOS)
        arr = np.asarray(image_rgb.convert("RGB"), dtype=np.float32)

    cga = np.asarray(CGA_COLORS, dtype=np.float32)  # (16, 3)

    # Precompute per-pixel error for each of 16 fg choices. The "2-color palette"
    # error per pixel is min(dist_to_black, dist_to_fg).
    dist_to_black = (arr * arr).sum(axis=2)                       # (H, W)
    diff = arr[:, :, None, :] - cga[None, None, :, :]             # (H, W, 16, 3)
    dist_to_fg = (diff * diff).sum(axis=3)                        # (H, W, 16)
    err_per_pixel_per_fg = np.minimum(dist_to_black[:, :, None], dist_to_fg)  # (H, W, 16)

    seg_w = W // N
    test_steps = _stagger_step_candidates(seg_w)

    best_step = test_steps[0]
    best_score = float("inf")

    for step in test_steps:
        total = 0.0
        for y in range(H):
            stripes = staggered_segments(y, N, W, step)
            # Group stripes by logical segment (one segment may have 2 stripes if it wraps)
            # Sum the per-fg error contribution from all stripes that belong to the same segment.
            # Then for each logical segment, take min across the 16 fg choices.
            seg_err_per_fg = np.zeros((N, 16), dtype=np.float32)
            for (x0, x1, log_si) in stripes:
                if x1 <= x0:
                    continue
                seg_err_per_fg[log_si] += err_per_pixel_per_fg[y, x0:x1, :].sum(axis=0)
            total += float(seg_err_per_fg.min(axis=1).sum())
        if total < best_score:
            best_score = total
            best_step = step

    return best_step


def find_best_stagger_step_320(image_rgb, N, W=320, H=200):
    """Search candidate stagger steps for the 320x200 4-color mode switch.

    Pure-Python (~5x slower than the 640 search because there are 112 candidate
    4-color palettes vs 16 candidate fgs, and we can't easily vectorize the
    per-segment palette selection without a large per-pixel-per-palette table).

    Returns the stagger_step that minimizes total PASS-1 quantization error.
    """
    if N <= 1:
        return 1

    img = image_rgb.convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)

    pix = img.load()
    work = [[pix[x, y] for x in range(W)] for y in range(H)]

    candidates = list(CGA_4COLOR_PALETTES.values()) if isinstance(CGA_4COLOR_PALETTES, dict) else list(CGA_4COLOR_PALETTES)
    if not candidates:
        return max(1, (W // N) // 4)

    seg_w = W // N
    test_steps = _stagger_step_candidates(seg_w)

    def nearest_dist(rgb, pal):
        r, g, b = rgb
        best = float("inf")
        for (pr, pg, pb) in pal:
            dr = r - pr; dg = g - pg; db = b - pb
            d = dr*dr + dg*dg + db*db
            if d < best:
                best = d
        return best

    best_step = test_steps[0]
    best_score = float("inf")

    for step in test_steps:
        total = 0.0
        for y in range(H):
            stripes = staggered_segments(y, N, W, step)
            row = work[y]

            # For each logical segment, find the best palette by summing the error
            # contribution across all stripes that belong to it (the wrap segment
            # has two stripes; everyone else has one).
            seg_x_ranges = [[] for _ in range(N)]
            for (x0, x1, log_si) in stripes:
                if x1 > x0:
                    seg_x_ranges[log_si].append((x0, x1))

            for si in range(N):
                ranges = seg_x_ranges[si]
                if not ranges:
                    continue
                best_seg_err = float("inf")
                for pal in candidates:
                    err = 0.0
                    skip = False
                    for (rx0, rx1) in ranges:
                        for x in range(rx0, rx1):
                            err += nearest_dist(row[x], pal)
                            if err >= best_seg_err:
                                skip = True
                                break
                        if skip:
                            break
                    if err < best_seg_err:
                        best_seg_err = err
                total += best_seg_err
        if total < best_score:
            best_score = total
            best_step = step

    return best_step


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
    staggered=False,            # legacy bool flag (kept for compat)
    stagger_step=None,
    stagger_mode=None,          # "none" | "triangle" | "random". If None, falls back to staggered flag.
    stagger_seed=42,            # used by random mode
    progress_cb=None,
    debug=DEBUG_MODE_SWITCH,
    return_palettes=False,
    tweaked_mode="off",         # "off" → mode-04 palettes only (3D8=0x0A constant)
                                # "on"  → mode-05 Tweaked palettes only (3D8=0x0E constant)
):
    """
    320x200 Mode Switch:
      - Choose a 4-color CGA palette PER SCANLINE.
      - Render the scanline left-to-right (optionally serpentine) using that palette.
      - Error diffusion propagates from the *working/original* pixel value (work[y][x]) into future pixels,
        including the pixel(s) below, so palette choice for the next scanline can be influenced.
    """
    status_dbg('ENTER quantize_320x200_mode_switch()')

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
    # Restrict by tweaked_mode so the resulting reg_table will have a CONSTANT
    # 3D8 byte (0x0A for "off", 0x0E for "on") across all 200 scanlines.
    # This guarantees the COM builder's fast path (single OUT per scanline, no
    # back-to-back register writes that cause leftmost-pixel edge defects).
    if isinstance(CGA_4COLOR_PALETTES, dict):
        candidates = filter_candidates_by_tweaked_mode(CGA_4COLOR_PALETTES, tweaked_mode)
    else:
        candidates = list(CGA_4COLOR_PALETTES)
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
    # Keys MUST match the names the GUI passes in self.diffusion_var (see diffusion_cb values).
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
        "Sierra-2": [(1,0,4/16),(2,0,3/16),
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

    # Resolve stagger mode: explicit stagger_mode wins; otherwise fall back to legacy `staggered` bool.
    _seg_n_top = int(max(1, min(8, int(segments_per_line))))
    if stagger_mode is None:
        _eff_mode = "triangle" if staggered else "none"
    else:
        _eff_mode = stagger_mode
    # Precompute the per-line offsets once (cheap; same for triangle and random)
    _line_layouts = precompute_stagger_layouts(H, _seg_n_top, W, _eff_mode, stagger_step, stagger_seed)

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
        # Up to 8 mode switches per scanline => up to 8 palette segments. (8088 timing
        # math caps practical mode switches at ~8 per active scanline; see CHANGES.)
        seg_n = int(max(1, min(8, int(segments_per_line))))
        seg_w = W // seg_n if seg_n > 0 else W
        seg_pals = [candidates[0]] * seg_n
        seg_idxs = [0] * seg_n
        seg_errs = [0.0] * seg_n

        # Use precomputed per-line stagger offset (mode-dependent; "none" gives 0).
        # equal_segments() in staggered_segments_at_offset distributes the remainder fairly
        # so segment widths are balanced even when N doesn't divide W (e.g. N=6, W=640).
        stripes = _line_layouts[y]

        # Group stripe x-ranges by logical segment (1 or 2 ranges per segment)
        seg_x_ranges = [[] for _ in range(seg_n)]
        for (sx0, sx1, log_si) in stripes:
            if sx1 > sx0:
                seg_x_ranges[log_si].append((sx0, sx1))

        row = work[y]

        for si in range(seg_n):
            ranges = seg_x_ranges[si]
            if not ranges:
                continue

            best_err = float("inf")
            best_pal = candidates[0]
            best_pal_idx = 0

            for p_i, pal in enumerate(candidates):
                err = 0.0
                early_out = False
                for (rx0, rx1) in ranges:
                    for x in range(rx0, rx1):
                        _, d = nearest_index(row[x], pal)
                        err += d
                        if err >= best_err:
                            early_out = True
                            break
                    if early_out:
                        break
                if err < best_err:
                    best_err = err
                    best_pal = pal
                    best_pal_idx = p_i

            seg_pals[si] = best_pal
            seg_idxs[si] = best_pal_idx
            seg_errs[si] = best_err

        chosen_palettes[y] = (seg_pals[0] if seg_n == 1 else seg_pals)

        # Precompute per-pixel logical-segment lookup for PASS-2.
        seg_for_x = seg_for_x_from_segments(stripes, W)


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
            # Logical segment owning this pixel (may differ from physical x // seg_w due to stagger wrap)
            si = seg_for_x[x]
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


def quantize_640x200_2color_mode_switch(
    image_rgb_640x200,
    dither_family="Diffusion",
    diffusion_name="Floyd-Steinberg",
    diffusion_intensity=1.0,
    serpentine=True,
    ordered_matrix_size=4,
    ordered_strength=1.0,
    segments_per_line=1,
    staggered=False,            # legacy bool flag
    stagger_step=None,
    stagger_mode=None,          # "none" | "triangle" | "random". If None, falls back to staggered flag.
    stagger_seed=42,
    progress_cb=None,
    return_palettes=False,
):
    """
    640x200 (2 Colors) Mode Switch:
      - Background is always BLACK (CGA BIOS mode 06h has no background register;
        port 3D9h bits 0-3 select the foreground color, bg is fixed at black).
      - Per scanline (and optionally per segment within scanline), choose the best
        foreground color from 16 CGA candidates. Up to 6 segments per scanline.
      - Output is a 1bpp bitmap (1 = foreground, 0 = black) — but the *displayed*
        color of "1" pixels varies per scanline/segment.
      - Error diffusion propagates between scanlines exactly as in
        quantize_320x200_mode_switch(), so future palette choices see propagated error.

    Returns:
        pimg: 640x200 RGB image (simulated final appearance with chosen FG colors)
        [if return_palettes=True]: also returns chosen_palettes -- a list of length H,
        each entry being either a 2-color palette [black, fg_rgb] (segments_per_line==1)
        or a list of 2-color palettes (segments_per_line>1).
    """
    status_dbg('ENTER quantize_640x200_2color_mode_switch()')

    img = image_rgb_640x200.convert("RGB")
    W, H = img.size
    if W != 640 or H != 200:
        img = img.resize((640, 200), Image.LANCZOS)
        W, H = img.size

    pix = img.load()
    work = [[[float(pix[x, y][0]), float(pix[x, y][1]), float(pix[x, y][2])] for x in range(W)] for y in range(H)]

    # 16 candidate 2-color palettes: black + each CGA color (including black/black=degenerate
    # which simply produces an all-black scanline if that minimizes error — fine).
    BLACK = (0, 0, 0)
    candidates = [[BLACK, CGA_COLORS[fg]] for fg in range(16)]

    chosen_palettes = [None] * H

    # Ordered dithering: pre-apply offsets to the WORK buffer (same approach as the 320 version).
    ord_n = int(ordered_matrix_size)
    if ord_n < 2: ord_n = 2
    if ord_n > 16: ord_n = 16
    ord_strength = float(ordered_strength)
    if ord_strength < 0.0: ord_strength = 0.0
    if ord_strength > 3.0: ord_strength = 3.0

    if dither_family == "Ordered" and ord_strength > 0.0:
        ord_matrix = get_ordered_matrix(ord_n)
        ord_den = float(ord_n * ord_n)
        base = 32.0
        for yy in range(H):
            row = work[yy]
            for xx in range(W):
                t = ord_matrix[yy % ord_n][xx % ord_n] / ord_den
                off = (t - 0.5) * base * ord_strength
                r, g, b = row[xx]
                row[xx][0] = min(255.0, max(0.0, r + off))
                row[xx][1] = min(255.0, max(0.0, g + off))
                row[xx][2] = min(255.0, max(0.0, b + off))

    # Same kernel set as the 320 version. Keys MUST match the GUI's diffusion_var values.
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
        "Sierra-2": [(1,0,4/16),(2,0,3/16),
                     (-2,1,1/16),(-1,1,2/16),(0,1,3/16),(1,1,2/16),(2,1,1/16)],
        "Sierra Lite": [(1,0,2/4), (-1,1,1/4), (0,1,1/4)],
        "Atkinson": [(1,0,1/8),(2,0,1/8),(-1,1,1/8),(0,1,1/8),(1,1,1/8),(0,2,1/8)],
    }

    intensity = float(diffusion_intensity)
    if intensity < 0.0: intensity = 0.0
    if intensity > 3.0: intensity = 3.0

    kernel = KERNELS.get(diffusion_name, KERNELS["Floyd-Steinberg"])

    out_pixels = [(0, 0, 0)] * (W * H)

    def nearest_index_2(old_rgb, pal2):
        """Fast 2-color nearest: returns 0 (black) or 1 (fg) and the squared distance."""
        r, g, b = old_rgb
        # palette[0] is BLACK by construction; just compute distance to (0,0,0)
        d0 = r*r + g*g + b*b
        pr, pg, pb = pal2[1]
        dr = r - pr; dg = g - pg; db = b - pb
        d1 = dr*dr + dg*dg + db*db
        if d1 < d0:
            return 1, d1
        return 0, d0

    # Resolve stagger mode and precompute per-line offsets once
    _seg_n_top = int(max(1, min(8, int(segments_per_line))))
    if stagger_mode is None:
        _eff_mode = "triangle" if staggered else "none"
    else:
        _eff_mode = stagger_mode
    _line_layouts = precompute_stagger_layouts(H, _seg_n_top, W, _eff_mode, stagger_step, stagger_seed)

    for y in range(H):
        if progress_cb is not None and (y % 8) == 0:
            try:
                progress_cb(y / float(H))
            except Exception:
                pass

        # --- PASS 1: choose best fg per segment based on CURRENT work[y] ---
        # Up to 8 segments per scanline (8088 timing math).
        seg_n = int(max(1, min(8, int(segments_per_line))))
        seg_w = W // seg_n if seg_n > 0 else W
        seg_pals = [candidates[15]] * seg_n  # placeholder (white)
        seg_idxs = [15] * seg_n

        # Stripes for this scanline using precomputed mode-aware offset.
        # equal_segments() inside staggered_segments_at_offset distributes the remainder
        # fairly across segments (e.g. N=6, W=640: widths 107,107,107,107,106,106).
        stripes = _line_layouts[y]

        # Group stripe x-ranges by logical segment
        seg_x_ranges = [[] for _ in range(seg_n)]
        for (sx0, sx1, log_si) in stripes:
            if sx1 > sx0:
                seg_x_ranges[log_si].append((sx0, sx1))

        row = work[y]

        for si in range(seg_n):
            ranges = seg_x_ranges[si]
            if not ranges:
                continue

            best_err = float("inf")
            best_pal = candidates[15]
            best_pal_idx = 15

            for p_i, pal in enumerate(candidates):
                err = 0.0
                # Inline the 2-color nearest test for speed
                fr, fg_, fb = pal[1]
                early_out = False
                for (rx0, rx1) in ranges:
                    for x in range(rx0, rx1):
                        r, g, b = row[x]
                        d0 = r*r + g*g + b*b
                        dr = r - fr; dg = g - fg_; db = b - fb
                        d1 = dr*dr + dg*dg + db*db
                        err += d0 if d0 < d1 else d1
                        if err >= best_err:
                            early_out = True
                            break
                    if early_out:
                        break
                if err < best_err:
                    best_err = err
                    best_pal = pal
                    best_pal_idx = p_i

            seg_pals[si] = best_pal
            seg_idxs[si] = best_pal_idx

        chosen_palettes[y] = (seg_pals[0] if seg_n == 1 else list(seg_pals))

        # Precompute per-pixel logical-segment lookup for PASS-2.
        seg_for_x = seg_for_x_from_segments(stripes, W)

        # --- PASS 2: render scanline and diffuse error forward (Diffusion family only) ---
        if serpentine and (y % 2 == 1):
            xs = range(W - 1, -1, -1)
            k_use = [(-dx, dy, w) for (dx, dy, w) in kernel]
        else:
            xs = range(W)
            k_use = kernel

        for x in xs:
            old = row[x]
            si = seg_for_x[x]
            pal_use = seg_pals[si]
            idx, _ = nearest_index_2(old, pal_use)
            new = pal_use[idx]
            out_pixels[y * W + x] = new

            if dither_family == "Diffusion" and intensity > 0.0:
                er = old[0] - new[0]
                eg = old[1] - new[1]
                eb = old[2] - new[2]

                row[x][0] = float(new[0]); row[x][1] = float(new[1]); row[x][2] = float(new[2])

                for dx, dy, w in k_use:
                    xx = x + dx
                    yy = y + dy
                    if 0 <= xx < W and 0 <= yy < H:
                        f = w * intensity
                        work[yy][xx][0] = min(255.0, max(0.0, work[yy][xx][0] + er * f))
                        work[yy][xx][1] = min(255.0, max(0.0, work[yy][xx][1] + eg * f))
                        work[yy][xx][2] = min(255.0, max(0.0, work[yy][xx][2] + eb * f))

    pimg = Image.new("RGB", (W, H))
    pimg.putdata(out_pixels)

    if return_palettes:
        return pimg, chosen_palettes
    return pimg


class CgaConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CGA Converter v155")
        self.geometry("1040x720")

        self.src_image = None
        self.output_pimage = None
        self.effective_80x100_image = None
        # For NTSC text-trick modes (512/1024): list of (fg, bg, pat, swap) tuples,
        # one per 80x100 cell, in row-major order. Used for COM export.
        self.text_ntsc_chosen = None
        # For centered 1024 mode (40-pattern path): list of (char, attr) tuples
        # produced by the full encoder. When present, export uses these
        # directly without re-encoding. Refreshed each Convert call.
        self.text_ntsc_centered_cells = None
        # For centered 1024 mode: original 80x100 source image, stashed at convert
        # time so the COM export can re-encode it through the full pair encoder.
        self.text_ntsc_src80 = None
        # For centered 1024 mode with 40-pattern encoder: 640x100 source for
        # per-pixel encoding. Stashed at convert time alongside src80. The
        # 40-pattern encoder operates at 640 wide; src80 is only used by the
        # 4-pattern legacy LUT path.
        self.text_ntsc_src640 = None
        # Threading state for the slow centered-40-pattern encoder. When an
        # encode is in progress, _centered_encoder_thread is non-None and the
        # _centered_encoder_cancel event can be set to abort it (used when the
        # user starts a new Convert before the previous one finishes).
        self._centered_encoder_thread = None
        self._centered_encoder_cancel = None
        # The encoder preset+source used for the currently-running worker.
        # Used by the worker's on-completion handler to verify state hasn't
        # changed since the worker started (e.g., user changed mode mid-encode).
        self._centered_encoder_token = 0
        self.mid_tk_image = None
        self.src_tk_image = None
        self.out_tk_image = None

        # Input adjustments (applied before scaling / quantization)
        self.in_brightness_var = tk.IntVar(value=0)   # -100..100
        self.in_contrast_var   = tk.IntVar(value=0)   # -100..100
        self.in_r_gain_var     = tk.IntVar(value=100) # 0..200 (% gain)
        self.in_g_gain_var     = tk.IntVar(value=100)
        self.in_b_gain_var     = tk.IntVar(value=100)

        self.show_input_adjust_var = tk.BooleanVar(value=False)  # show/hide 'Input Adjust' section

        self.status_var = tk.StringVar(value="Ready.")
        self.progress_var = tk.StringVar(value="0%")
        self._left_preview_after_id = None  # debounce for live input-adjust preview

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

        ttk.Checkbutton(
            controls,
            text="Input Adjust",
            variable=self.show_input_adjust_var,
            command=self._toggle_input_adjust,
        ).pack(side=tk.LEFT, padx=(12,4))

        options = ttk.LabelFrame(self, text="Options")
        options.pack(side=tk.TOP, fill=tk.X, padx=8, pady=4)

        # Mode
        ttk.Label(options, text="Output mode:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.mode_var = tk.StringVar(value="320x200 (4 Colors)")
        mode_cb = ttk.Combobox(
            options,
            textvariable=self.mode_var,
            state="readonly",
            values=[
                "320x200 (4 Colors)",
                "640x200 (2 Colors)",
                "160x200 (16 Colors) Composite",
                "80x100 (512 Colors)",
                "80x100 (1024 Colors) Mini-Frames",
                "80x100 (1024 Colors)",
                "640x100 (1024 Colors)",
                "160x100 (16 Colors)",
                "640x200 (16 Colors) Char",
                "80x100 (4352 Colors) HiColor",
                "320x200 (4 Colors) Mode Switch",
                "640x200 (2 Colors) Mode Switch",
            ],
            width=30,
        )
        mode_cb.grid(row=0, column=1, sticky="w", padx=4, pady=2)
        mode_cb.bind("<<ComboboxSelected>>", self.on_mode_changed)

        # STOP button for 640x100 (1024 Colors) background encoder. Visible only
        # in that mode, enabled only while an encode is running. The encoder for
        # that mode takes ~3 minutes and runs on a worker thread; this button
        # lets the user cancel without waiting for completion.
        self.text_ntsc_stop_btn = ttk.Button(
            options, text="Stop encode", command=self.on_centered_encoder_stop,
            state="disabled",
        )
        self.text_ntsc_stop_btn.grid(row=0, column=7, sticky="w", padx=4, pady=2)
        self.text_ntsc_stop_btn.grid_remove()

        # Search depth slider (K) for the Viterbi per-row encoder, used by the
        # 640x100 (1024 Colors) mode. K controls how many candidate cells per
        # position the DP considers. K=64 is the sweet spot (default). Higher
        # values produce slightly cleaner output at proportionally longer
        # encode times; lower values trade quality for speed.
        #   K=8    ~5s    (preview-grade quality)
        #   K=32   ~25s   (good)
        #   K=64   ~85s   (default — high quality)
        #   K=128  ~5min  (slightly cleaner)
        #   K=256  ~15min (diminishing returns)
        # Time scales roughly as K^1.7 due to vectorized batching efficiency.
        self.text_ntsc_k_var = tk.IntVar(value=64)
        self.text_ntsc_k_label = ttk.Label(options, text="Search depth (K):")
        self.text_ntsc_k_slider = ttk.Scale(
            options,
            from_=8, to=256,
            orient="horizontal",
            length=180,
            variable=self.text_ntsc_k_var,
            command=self._on_text_ntsc_k_changed,
        )
        self.text_ntsc_k_value_label = ttk.Label(options, text="64  (~85s)")
        # Hidden until centered 640x100 mode is selected.
        self.text_ntsc_k_label.grid(row=1, column=5, sticky="e", padx=4, pady=2)
        self.text_ntsc_k_slider.grid(row=1, column=6, sticky="w", padx=4, pady=2)
        self.text_ntsc_k_value_label.grid(row=1, column=7, sticky="w", padx=4, pady=2)
        self.text_ntsc_k_label.grid_remove()
        self.text_ntsc_k_slider.grid_remove()
        self.text_ntsc_k_value_label.grid_remove()

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

        # Background color selection (used by 320x200 4-color and Mode Switch modes)
        ttk.Label(options, text="Background Color Selection:").grid(row=0, column=4, sticky="e", padx=4, pady=2)
        self.bg_color_var = tk.StringVar(value="Black")
        self.bg_color_cb = ttk.Combobox(
            options,
            textvariable=self.bg_color_var,
            state="readonly",
            values=list(CGA_COLOR_NAMES),
            width=18,
        )
        self.bg_color_cb.grid(row=0, column=5, sticky="w", padx=4, pady=2)
        self.bg_color_cb.state(["disabled"])


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

        # (v134) Composite palette preview swatch removed for now.
        self.composite_palette_canvas = None


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
        self.scale_var = tk.StringVar(value="Stretch")
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
            values=[
                "Lanczos",
                "Lanczos + Unsharp",
                "Gaussian (prefilter) + Lanczos",
                "Multi-pass Box (downscale)",
                "Bicubic",
                "Bilinear",
                "Box (Area)",
                "Hamming",
                "Nearest",
            ],
            width=20,
        )
        resample_cb.grid(row=2, column=3, sticky="w", padx=4, pady=2)

        # --- Input adjustments (Brightness/Contrast + RGB gains) ---
        adj_frame = ttk.LabelFrame(options, text="Input Adjust")
        self.input_adjust_frame = adj_frame
        # place after scaling controls; adjust row if needed later
        adj_frame.grid(row=99, column=0, columnspan=2, sticky="ew", padx=4, pady=(8, 2))
        adj_frame.columnconfigure(1, weight=1)

        ttk.Label(adj_frame, text="Brightness").grid(row=0, column=0, sticky="w", padx=4)
        self.in_brightness_scale = ttk.Scale(adj_frame, from_=-100, to=100, variable=self.in_brightness_var, orient="horizontal", command=self._schedule_left_preview_update)
        self.in_brightness_scale.grid(row=0, column=1, sticky="ew", padx=4)

        ttk.Label(adj_frame, text="Contrast").grid(row=1, column=0, sticky="w", padx=4)
        self.in_contrast_scale = ttk.Scale(adj_frame, from_=-100, to=100, variable=self.in_contrast_var, orient="horizontal", command=self._schedule_left_preview_update)
        self.in_contrast_scale.grid(row=1, column=1, sticky="ew", padx=4)

        ttk.Label(adj_frame, text="R Gain").grid(row=2, column=0, sticky="w", padx=4)
        self.in_r_gain_scale = ttk.Scale(adj_frame, from_=0, to=200, variable=self.in_r_gain_var, orient="horizontal", command=self._schedule_left_preview_update)
        self.in_r_gain_scale.grid(row=2, column=1, sticky="ew", padx=4)

        ttk.Label(adj_frame, text="G Gain").grid(row=3, column=0, sticky="w", padx=4)
        self.in_g_gain_scale = ttk.Scale(adj_frame, from_=0, to=200, variable=self.in_g_gain_var, orient="horizontal", command=self._schedule_left_preview_update)
        self.in_g_gain_scale.grid(row=3, column=1, sticky="ew", padx=4)

        ttk.Label(adj_frame, text="B Gain").grid(row=4, column=0, sticky="w", padx=4)
        self.in_b_gain_scale = ttk.Scale(adj_frame, from_=0, to=200, variable=self.in_b_gain_var, orient="horizontal", command=self._schedule_left_preview_update)
        self.in_b_gain_scale.grid(row=4, column=1, sticky="ew", padx=4)

        ttk.Button(adj_frame, text="Reset", command=self._reset_input_adjust).grid(row=0, column=2, rowspan=5, sticky="ns", padx=(8,4), pady=2)

        # Apply initial show/hide state for Input Adjust
        self._toggle_input_adjust()


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

        # Target video card (affects .COM export for 80x100 text-trick modes:
        # 160x100 16-color, 640x200 Char16, 80x100 HiColor).
        # - "CGA": original CGA register pokes (3D8h disable, MC6845 CRTC pokes 04/06/07/09,
        #          3D8h re-enable). Works on real CGA hardware and DOSBox machine=cga.
        # - "EGA/VGA": INT 10h AX=1003h to disable blink, plus extended VGA CRTC programming
        #              (12/15/16/10/11/06/09). Works on EGA/VGA cards and DOSBox machine=svga_*
        #              (default in DOSBox/DOSBox-X). Recommended for most modern emulator setups.
        ttk.Label(options, text="Target video card:").grid(row=6, column=0, sticky="w", padx=4, pady=2)
        self.target_video_var = tk.StringVar(value="CGA")
        self.target_video_cb = ttk.Combobox(
            options,
            textvariable=self.target_video_var,
            state="readonly",
            values=["CGA", "EGA/VGA"],
            width=12,
        )
        self.target_video_cb.grid(row=6, column=1, sticky="w", padx=4, pady=2)

        # Mode Switch: number of palette segments per scanline (1..8).
        # 1 means one palette for the whole line. The 8088 timing budget caps practical
        # mode switches at ~8 per active scanline (44.7us active / 2.5us per OUT),
        # so the upper bound is 8.
        ttk.Label(options, text="Mode Switch segments per line:").grid(row=6, column=3, sticky="e", padx=4, pady=2)
        self.ms_switches_var = tk.IntVar(value=1)
        self.ms_switches_spin = ttk.Spinbox(
            options,
            from_=1,
            to=8,
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
        self.ms_show_palette_cb.grid(row=7, column=0, columnspan=3, sticky="w", padx=4, pady=2)

        # Tweaked palette mode selector (Mode Switch only).
        # 
        # When OFF: encoder restricts per-line palette choices to standard CGA
        #   mode 04 palettes (palette select bit 5 of 3D9; 4 palette options:
        #   green/red/yellow LOW/HIGH, cyan/magenta/white LOW/HIGH).
        #   3D8 = 0x0A constant for all 200 lines.
        # 
        # When ON: encoder restricts to mode 05 "Tweaked" palettes
        #   (cyan/red/light-gray, light-cyan/light-red/white).
        #   3D8 = 0x0E constant for all 200 lines.
        # 
        # Either way 3D8 is written ONCE at startup (not per-line). The COM 
        # builder's fast path then writes only 3D9 per scanline (single OUT, 
        # no back-to-back register writes that caused leftmost-pixel defects).
        ttk.Label(options, text="Tweaked palettes:").grid(row=9, column=3, sticky="e", padx=4, pady=2)
        self.tweaked_mode_var = tk.StringVar(value="off")
        tweaked_frame = ttk.Frame(options)
        tweaked_frame.grid(row=9, column=4, columnspan=2, sticky="w", padx=4, pady=2)
        ttk.Radiobutton(
            tweaked_frame, text="Off (mode 04)", variable=self.tweaked_mode_var, value="off"
        ).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(
            tweaked_frame, text="On (mode 05)", variable=self.tweaked_mode_var, value="on"
        ).pack(side=tk.LEFT, padx=2)

        # Stagger mode (applies to both 320 and 640 Mode Switch).
        #   None         => uniform segment boundaries (no stagger)
        #   Triangle wave => reflective offset 0->seg_w->0 across scanlines (sliding bands)
        #   Random per line => independent random offset per line, breaks vertical clustering
        ttk.Label(options, text="Stagger mode:").grid(row=7, column=3, sticky="e", padx=4, pady=2)
        self.ms_stagger_mode_var = tk.StringVar(value="None")
        self.ms_stagger_mode_cb = ttk.Combobox(
            options,
            textvariable=self.ms_stagger_mode_var,
            state="readonly",
            values=["None", "Triangle wave", "Random per line"],
            width=18,
        )
        self.ms_stagger_mode_cb.grid(row=7, column=4, columnspan=2, sticky="w", padx=4, pady=2)
        self.ms_stagger_mode_cb.bind("<<ComboboxSelected>>", lambda e: self._on_stagger_toggle())

        # Image-aware optimization (slow): tries 5 candidate stagger steps and picks the one
        # with lowest PASS-1 quantization error. Only enabled in Triangle wave mode.
        self.ms_stagger_optimize_var = tk.BooleanVar(value=False)
        self.ms_stagger_optimize_cb = ttk.Checkbutton(
            options,
            text="Optimize stagger to image content (slow, Triangle wave only)",
            variable=self.ms_stagger_optimize_var,
        )
        self.ms_stagger_optimize_cb.grid(row=8, column=3, columnspan=3, sticky="w", padx=4, pady=2)
        self.ms_stagger_optimize_cb.state(["disabled"])

        # Backward-compat alias (so old code paths that still reference ms_stagger_var don't crash)
        self.ms_stagger_var = tk.BooleanVar(value=False)

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
        self.preview_scale_var = tk.StringVar(value="1x")
        preview_cb = ttk.Combobox(
            options,
            textvariable=self.preview_scale_var,
            state="readonly",
            values=["1x", "2x", "3x", "4x"],
            width=5,
        )
        preview_cb.grid(row=2, column=5, sticky="w", padx=4, pady=2)
        preview_cb.bind("<<ComboboxSelected>>", self.on_preview_scale_changed)

        # Image frames
        img_frame = ttk.Frame(self)
        img_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=4)

        left_frame = ttk.LabelFrame(img_frame, text="Input")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.mid_frame = ttk.LabelFrame(img_frame, text="80x100 Effective")
        # start hidden; only show for 80x100 HiColor mode
        self.mid_label = ttk.Label(self.mid_frame, text="(HiColor mode only)")
        self.mid_label.pack(fill=tk.BOTH, expand=True)
        self.right_frame = ttk.LabelFrame(img_frame, text="Output")
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.left_label = ttk.Label(left_frame, text="No image loaded")
        self.left_label.pack(fill=tk.BOTH, expand=True)

        # Tone-match preview (only shown for 320x200 4-color + "Match contrast / tone" enabled)
        self.tone_preview_frame = ttk.LabelFrame(left_frame, text="Tone-match (4-color only)")
        # start hidden
        self.tone_preview_img_label = ttk.Label(self.tone_preview_frame, text="(Enable 'Match contrast / tone' in 320x200 4-color)")
        self.tone_preview_img_label.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4,2))
        self.tone_preview_stats = ttk.Label(self.tone_preview_frame, text="", justify="left")
        self.tone_preview_stats.pack(fill=tk.X, padx=4, pady=(0,4))

        out_inner = ttk.Frame(self.right_frame)
        out_inner.pack(fill=tk.BOTH, expand=True)

        self.preview_size_label = ttk.Label(self.right_frame, text="", anchor="w")
        self.preview_size_label.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0,4))

        # Scrollable output preview (Canvas + scrollbars)
        self.out_canvas_frame = ttk.Frame(out_inner)
        self.out_canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.out_canvas = tk.Canvas(self.out_canvas_frame, highlightthickness=0)
        self.out_vscroll = ttk.Scrollbar(self.out_canvas_frame, orient="vertical", command=self.out_canvas.yview)
        self.out_hscroll = ttk.Scrollbar(self.out_canvas_frame, orient="horizontal", command=self.out_canvas.xview)
        self.out_canvas.configure(yscrollcommand=self.out_vscroll.set, xscrollcommand=self.out_hscroll.set)

        self.out_canvas.grid(row=0, column=0, sticky="nsew")
        self.out_vscroll.grid(row=0, column=1, sticky="ns")
        self.out_hscroll.grid(row=1, column=0, sticky="ew")
        self.out_canvas_frame.grid_rowconfigure(0, weight=1)
        self.out_canvas_frame.grid_columnconfigure(0, weight=1)

        self.out_canvas_img_id = None
        self.out_tk_image = None

        # Mousewheel scrolling (Windows/macOS/Linux)
        def _out_canvas_on_mousewheel(event):
            try:
                if getattr(event, "num", None) == 4:
                    self.out_canvas.yview_scroll(-3, "units")
                elif getattr(event, "num", None) == 5:
                    self.out_canvas.yview_scroll(3, "units")
                else:
                    delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
                    if delta != 0:
                        self.out_canvas.yview_scroll(delta * 3, "units")
            except Exception:
                pass

        self.out_canvas.bind("<MouseWheel>", _out_canvas_on_mousewheel)
        self.out_canvas.bind("<Button-4>", _out_canvas_on_mousewheel)
        self.out_canvas.bind("<Button-5>", _out_canvas_on_mousewheel)

        # Optional: Mode Switch palette strip (diagnostic) — full-width image map
        # showing the per-scanline segment layout including stagger offsets.
        # Lives BELOW the output canvas (banner-style) so it can show its full width.
        self.ms_pal_frame = ttk.LabelFrame(self.right_frame, text="Mode Switch layout map")
        # Don't pack it here; _update_right_preview will pack/forget based on whether a strip exists.
        self.ms_pal_label = ttk.Label(self.ms_pal_frame, text="")
        self.ms_pal_label.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.ms_pal_tk = None
        self.ms_pal_pimage = None
        self.composite_encoded_pimage = None

        self._refresh_palette_choices()
        # Apply initial mode-dependent enable/disable logic (ensures BG selector enables for 320x200 4-color)
        self.on_mode_changed()
        # Status bar
        status_frame = ttk.Frame(self)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 6))
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor='w')
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress_label = ttk.Label(status_frame, textvariable=self.progress_var, anchor='e')
        self.progress_label.pack(side=tk.LEFT, padx=(8, 0))
        self.on_dither_family_changed()
        self._update_dither_labels()

    def _reset_status_steps(self):
        self._status_step_idx = 0

    def status_step(self, msg: str):
        """Absurdly verbose status line with step counter; forces UI flush."""
        try:
            self._status_step_idx += 1
        except Exception:
            self._status_step_idx = 1
        self.set_status(f"[{self._status_step_idx:03d}] {msg}")
        try:
            self.update_idletasks()
        except Exception:
            pass


    def set_status(self, text: str):
        """Update the status bar and keep UI responsive."""
        try:
            self.status_var.set(text)
            self.update_idletasks()
        except Exception:
            pass


    def set_progress(self, pct: int):
        """Update the progress percent label and keep UI responsive."""
        try:
            pct = int(pct)
            if pct < 0:
                pct = 0
            if pct > 100:
                pct = 100
            self.progress_var.set(f"{pct}%")
            self.update_idletasks()
        except Exception:
            pass






    def is_4color_mode(self):
        m = self.mode_var.get()
        return m.startswith("320x200 (4 Colors)") and ("Mode Switch" not in m)


    def is_mono_mode(self):
        # Plain 640x200 2-color (single foreground for the whole image).
        # NOT 640x200 (2 Colors) Mode Switch — that's its own thing.
        m = self.mode_var.get()
        return m.startswith("640x200 (2 Colors)") and ("Mode Switch" not in m)


    def is_16color_low_mode(self):
        return self.mode_var.get().startswith("160x100 (16 Colors)")


    def is_16color_char_mode(self):
        m = self.mode_var.get()
        return m.startswith("640x200 (16 Colors)") and ("Char" in m)


    def is_hicolor_mode(self):
        return "HiColor" in self.mode_var.get()

    
    def is_composite_mode(self):
        m = self.mode_var.get()
        return ("Composite" in m) and ("160x200" in m)

    def is_text_ntsc_4k_mode(self):
        """True for any of the 1024-color text-NTSC modes:
          - "80x100 (1024 Colors) Mini-Frames" — legacy mini-frames CRTC trick (broken on MartyPC)
          - "80x100 (1024 Colors)"             — 4-pattern centered (cell-grain encoder)
          - "640x100 (1024 Colors)"            — 40-pattern centered (per-pixel encoder)
        """
        m = self.mode_var.get()
        return (m == "80x100 (1024 Colors) Mini-Frames"
                or m == "80x100 (1024 Colors)"
                or m == "640x100 (1024 Colors)")

    def is_text_ntsc_centered_mode(self):
        """True for the two centered-CRTC modes (the L100V4 builder).
        Both produce a vertically-centered 80x100 image on screen, but they
        differ in encoder:
          - "80x100 (1024 Colors)"  → 4-pattern legacy LUT encoder (fast, smooth)
          - "640x100 (1024 Colors)" → 40-pattern exhaustive encoder (slow, vivid)
        """
        m = self.mode_var.get()
        return (m == "80x100 (1024 Colors)"
                or m == "640x100 (1024 Colors)")

    def is_text_ntsc_640_mode(self):
        """True only for the new 640x100 mode — the 40-pattern per-pixel encoder
        running on a background thread. Used to gate the STOP button and the
        slow background-encode path."""
        return self.mode_var.get() == "640x100 (1024 Colors)"

    def is_text_ntsc_80x100_centered_mode(self):
        """True only for the 4-pattern centered mode. Used to dispatch convert
        and export to the simple legacy LUT path."""
        return self.mode_var.get() == "80x100 (1024 Colors)"
    
    def is_text_ntsc_512_mode(self):
        """512-color subset of the NTSC text trick — uses only chars 0x55 and 0x13.
        These two chars have IDENTICAL row 0 and row 1 patterns, so they work in
        the standard 80x100 mode (2 scanlines/row) without CRTC manipulation per
        scanline. 'Set and forget' — static image, zero CPU load after setup.
        """
        return self.mode_var.get().startswith("80x100 (512 Colors)")
    
    def is_text_ntsc_mode(self):
        """True for any NTSC text trick mode (512 or 1024). They share the same
        simulation pipeline (build LUT, dither in 80x100 cell space) — only the
        candidate patterns differ.
        """
        return self.is_text_ntsc_4k_mode() or self.is_text_ntsc_512_mode()


    def is_mode_switch_mode(self):
        # ONLY the original 320x200 4-color Mode Switch.
        # The 640x200 2-color Mode Switch has its own predicate (is_640_2color_mode_switch_mode).
        return self.mode_var.get() == "320x200 (4 Colors) Mode Switch"

    def is_640_2color_mode_switch_mode(self):
        return self.mode_var.get() == "640x200 (2 Colors) Mode Switch"

    def is_any_mode_switch(self):
        """True for either Mode Switch variant — used for shared UI logic."""
        return self.is_mode_switch_mode() or self.is_640_2color_mode_switch_mode()

    def get_target_size(self):
        if self.is_4color_mode() or self.is_mode_switch_mode():
            return 320, 200
        if self.is_mono_mode():
            return 640, 200
        if self.is_640_2color_mode_switch_mode():
            return 640, 200
        if self.is_text_ntsc_mode():
            # Effective logical resolution of the NTSC text-trick modes (512/1024).
            return 80, 100
        if self.is_composite_mode():
            self.status_step('Mode branch: Composite 160x200')
            return 160, 200
        if self.is_16color_low_mode():
            return 160, 100
        # char 16-color
        if self.is_16color_char_mode():
            return 640, 200
        # 80x100 HiColor (internally uses 640x200 blocks)
        if self.is_hicolor_mode():
            self.status_step('Mode branch: 80x100 (HiColor)')
            return 640, 200
        return 640, 200

    def _refresh_palette_choices(self):
        if self.is_4color_mode():
            self.status_step('Mode branch: 320x200 (4 Colors)')
            names = sorted(CGA_4COLOR_BASESETS.keys())
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
                    self.palette_var.set("Black / White" if "Black / White" in names else names[0])
            else:
                self.palette_var.set("")
        elif self.is_composite_mode():
            names = ["(Composite mode)"]
            self.palette_cb["values"] = names
            self.palette_cb.state(["disabled"])
            self.palette_var.set("(Composite mode)")
        elif self.is_640_2color_mode_switch_mode():
            # No palette dropdown choice — the algorithm picks the best foreground per scanline
            # from all 16 CGA colors. Show a clarifying placeholder.
            names = ["(per-scanline foreground; no palette choice)"]
            self.palette_cb["values"] = names
            self.palette_cb.state(["disabled"])
            self.palette_var.set("(per-scanline foreground; no palette choice)")
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
                self.status_step('Preview: updated right preview')
                self._update_mid_preview()

    def on_mode_changed(self, event=None):
        self._refresh_palette_choices()

        # Background color selection is only meaningful in 320x200 4-color and Mode Switch modes.
        if getattr(self, "bg_color_cb", None) is not None:
            if self.is_mode_switch_mode():
                self.status_step('Mode branch: Mode Switch 320x200 (4 Colors)')
                vals = ["Multiple"] + list(CGA_COLOR_NAMES)
                self.bg_color_cb["values"] = vals
                self.bg_color_cb.state(["!disabled"])
                if self.bg_color_var.get() not in vals:
                    self.bg_color_var.set("Multiple")
            elif self.is_4color_mode():
                vals = list(CGA_COLOR_NAMES)
                self.bg_color_cb["values"] = vals
                self.bg_color_cb.state(["!disabled"])
                if self.bg_color_var.get() not in vals or self.bg_color_var.get() == "Multiple":
                    self.bg_color_var.set("Black")
            else:
                self.bg_color_cb.state(["disabled"])


        # Default diffusion method for Mode Switch variants (strong vertical propagation
        # plays well with per-scanline palette choice).
        if self.is_any_mode_switch():
            # Only override if blank or "None"; don't stomp user choice
            if getattr(self, "diffusion_var", None) is not None:
                if self.diffusion_var.get() in ("", "None"):
                    self.diffusion_var.set("Horizontal Striped")

        # Show/hide the STOP button for the 640x100 (1024 Colors) background
        # encoder. STOP is only meaningful in that mode (the 4-pattern modes
        # encode synchronously and don't need cancellation).
        if getattr(self, "text_ntsc_stop_btn", None) is not None:
            if self.is_text_ntsc_640_mode():
                self.text_ntsc_stop_btn.grid()
            else:
                self.text_ntsc_stop_btn.grid_remove()

        # Show/hide the Search depth (K) slider, also gated on 640x100 mode.
        if getattr(self, "text_ntsc_k_slider", None) is not None:
            if self.is_text_ntsc_640_mode():
                self.text_ntsc_k_label.grid()
                self.text_ntsc_k_slider.grid()
                self.text_ntsc_k_value_label.grid()
                # Refresh the displayed value/time-estimate label
                self._on_text_ntsc_k_changed(self.text_ntsc_k_var.get())
            else:
                self.text_ntsc_k_label.grid_remove()
                self.text_ntsc_k_slider.grid_remove()
                self.text_ntsc_k_value_label.grid_remove()

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


        # Enable Composite palette controls in Composite and NTSC Text modes (512/1024)
        if getattr(self, "composite_palette_cb", None) is not None:
            if self.is_composite_mode() or self.is_text_ntsc_mode():
                self.composite_palette_cb.state(["!disabled"])
            else:
                self.composite_palette_cb.state(["disabled"])
        if getattr(self, "composite_palette_canvas", None) is not None:
            # Hide visual emphasis when disabled by clearing border
            if self.is_composite_mode() or self.is_text_ntsc_mode():
                self.composite_palette_canvas.configure(highlightbackground="#888")
            else:
                self.composite_palette_canvas.configure(highlightbackground="#bbb")

        # Enable Target Video Card selector only for modes whose .COM export
        # uses the 80x100 text-mode trick (different programming on CGA vs VGA).
        if getattr(self, "target_video_cb", None) is not None:
            if (self.is_16color_low_mode()
                    or self.is_16color_char_mode()
                    or self.is_hicolor_mode()):
                self.target_video_cb.state(["!disabled"])
            else:
                self.target_video_cb.state(["disabled"])

        # Enable Stagger Mode Switch dropdown only when in a Mode Switch mode.
        # The optimize sub-checkbox is further gated on the dropdown selection
        # (handled by _on_stagger_toggle).
        if getattr(self, "ms_stagger_mode_cb", None) is not None:
            if self.is_any_mode_switch():
                self.ms_stagger_mode_cb.state(["!disabled"])
            else:
                self.ms_stagger_mode_cb.state(["disabled"])
        # Re-evaluate the optimize sub-checkbox state.
        if hasattr(self, "_on_stagger_toggle"):
            self._on_stagger_toggle()

        self._update_mid_preview()
        self._update_right_preview()

    
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
        if self.is_mode_switch_mode() or self.is_640_2color_mode_switch_mode():
            return CGA_16COLOR_PALETTE
        if self.is_4color_mode():
            base_name = self.palette_var.get()
            bg_name = getattr(self, "bg_color_var", tk.StringVar(value="Black")).get()
            return build_cga_4color_palette(base_name, bg_name)
        if self.is_mono_mode():
            name = self.palette_var.get()
            if name not in CGA_MONO_PALETTES:
                name = "Black / White"
            return CGA_MONO_PALETTES.get(name)
        # Both 16-color modes share the same palette
        return CGA_16COLOR_PALETTE


    def _on_stagger_toggle(self):
        """Update the optimize sub-checkbox state based on the stagger-mode dropdown.
        Only enabled when stagger mode == Triangle wave AND we're in a mode-switch mode AND segs > 1.
        """
        try:
            mode = self.ms_stagger_mode_var.get() if hasattr(self, "ms_stagger_mode_var") else "None"
            seg_n = int(getattr(self, "ms_switches_var", tk.IntVar(value=1)).get())
            in_ms_mode = self.is_any_mode_switch()
            triangle_active = mode == "Triangle wave" and in_ms_mode and seg_n > 1
            if triangle_active:
                self.ms_stagger_optimize_cb.state(["!disabled"])
            else:
                self.ms_stagger_optimize_cb.state(["disabled"])
                if mode in ("None", "Random per line"):
                    # Optimize is meaningless without triangle stagger; clear the sub-toggle.
                    self.ms_stagger_optimize_var.set(False)
        except Exception:
            pass


    def _build_mode_switch_strip(self, pals_by_y, target_w, seg_n, staggered=False, stagger_step=None, stagger_mode=None, stagger_seed=42, palette_size=4):
        """Build a full-width diagnostic image showing the per-scanline mode-switch layout.

        For each scanline:
          1. Computes the visible stripes (with stagger wraparound — one logical
             segment may produce two stripes, one on the right edge wrapping to
             a sliver on the left edge).
          2. Paints the chosen palette colors into each stripe's actual x-range.
             When the same logical segment appears in two stripes, both get the
             same palette so the visual continuity is preserved.

        For 4-color palettes (320 mode), the 4 colors are shown as vertical stripes
        filling each visible stripe's width. For 2-color palettes (640 mode), only
        the FG color is shown (BG is always black -> uninteresting to visualize).

        Returns a PIL RGB image of size (target_w, 200), or None on error.
        """
        try:
            H = 200
            arr = np.zeros((H, target_w, 3), dtype=np.uint8)

            seg_w_uniform = max(1, target_w // max(1, seg_n))

            # Resolve effective stagger mode and precompute offsets — same logic as quantizers
            if stagger_mode is None:
                _eff_mode = "triangle" if staggered else "none"
            else:
                _eff_mode = stagger_mode
            _line_layouts = precompute_stagger_layouts(H, seg_n, target_w, _eff_mode, stagger_step, stagger_seed)

            for y in range(H):
                entry = pals_by_y[y] if y < len(pals_by_y) else None
                if entry is None:
                    continue

                # Normalize entry shape to a list of segment palettes (one per logical segment)
                if seg_n == 1:
                    seg_pals = [entry]
                else:
                    if isinstance(entry, list) and len(entry) > 0 and isinstance(entry[0], (list, tuple)) and len(entry[0]) > 0 and isinstance(entry[0][0], (list, tuple)):
                        seg_pals = entry
                    else:
                        seg_pals = [entry] * seg_n

                # Build stripes from precomputed offset (matches what the quantizer used).
                # With wraparound the segment whose right edge crosses W is split into two
                # stripes sharing the same logical_seg_idx (and palette).
                stripes = _line_layouts[y]

                for (x0, x1, log_si) in stripes:
                    if x1 <= x0:
                        continue
                    pal = seg_pals[log_si] if log_si < len(seg_pals) else None
                    if pal is None or len(pal) < palette_size:
                        continue
                    stripe_width = x1 - x0

                    if palette_size == 4:
                        # 4 palette colors as vertical sub-stripes within this visible stripe
                        for ci in range(4):
                            cx0 = x0 + (ci * stripe_width) // 4
                            cx1 = x0 + ((ci + 1) * stripe_width) // 4
                            if cx1 <= cx0:
                                continue
                            arr[y, cx0:cx1] = (int(pal[ci][0]), int(pal[ci][1]), int(pal[ci][2]))
                    elif palette_size == 2:
                        # 2-color: paint the FG color across the stripe (BG is always black)
                        arr[y, x0:x1] = (int(pal[1][0]), int(pal[1][1]), int(pal[1][2]))

            return Image.fromarray(arr, 'RGB')
        except Exception:
            return None


    def _toggle_input_adjust(self):
        """Show/hide the 'Input Adjust' section to save vertical space."""
        frame = getattr(self, "input_adjust_frame", None)
        if frame is None:
            return
        show = bool(getattr(self, "show_input_adjust_var", tk.BooleanVar(value=True)).get())
        try:
            if show:
                frame.grid()         # restore prior grid options
            else:
                frame.grid_remove()  # remember grid options for restore
        except Exception:
            # Be defensive; Tk can throw if widget is mid-destroy
            pass


    # --- Centered 40-pattern background encoder ---
    # The 40-pattern encoder takes ~3 minutes per image. It runs in a worker
    # thread so the GUI stays responsive. The worker calls back into the GUI
    # via self.after(0, ...) for thread-safe widget updates.

    def _on_text_ntsc_k_changed(self, value):
        """User moved the search-depth slider. Update the displayed value
        and time estimate. Does NOT trigger a re-convert — value takes effect
        on the next Convert click.

        Time estimate fit: t ≈ 85 * (K/64)^1.7 seconds. Derived from
        measurements at K=16, 32, 64; matches reasonably well across the
        tested range due to vectorized batching efficiency.
        """
        try:
            k = int(float(value))
        except Exception:
            return
        # Estimate encode time
        secs = 85.0 * (max(1, k) / 64.0) ** 1.7
        if secs < 60:
            t_str = f"~{int(round(secs))}s"
        else:
            t_str = f"~{secs/60:.1f}min"
        try:
            self.text_ntsc_k_value_label.configure(text=f"{k}  ({t_str})")
        except Exception:
            pass

    def on_centered_encoder_stop(self):
        """User clicked the STOP button. Cancel any running 40-pattern encoder."""
        cancel = getattr(self, '_centered_encoder_cancel', None)
        if cancel is not None:
            cancel.set()
            self.set_status("Stopping encode...")
        # Disable the button so the user can't double-click
        try:
            if getattr(self, "text_ntsc_stop_btn", None) is not None:
                self.text_ntsc_stop_btn.state(["disabled"])
        except Exception:
            pass

    def _centered_encoder_worker(self, src, preset, token, cancel_event,
                                  chroma_lowpass=False, k_candidates=64):
        """Background-thread entry point. Runs the per-row Viterbi DP encoder,
        scheduling per-row preview updates and final completion on the GUI
        thread via self.after().

        The Viterbi encoder finds the globally optimal encoding per row within
        a pruned candidate set (K candidates per cell). Compared to the older
        greedy sliding-window encoder, it produces dramatically cleaner outlines
        and sharper color region boundaries because each cell's choice is
        informed by the constraint structure of the entire row.

        Args:
            src: 640x100 PIL Image. Encoder operates at full horizontal resolution.
            preset: composite preset name.
            token: encoder generation counter for stale-callback guarding.
            cancel_event: threading.Event for cooperative cancellation.
            chroma_lowpass: when True, applies a 4-pixel-wide box filter to
                chroma channels (a, b) of the Lab target. Tied to the GUI
                "Match contrast / tone to palette" checkbox.
            k_candidates: search depth — number of candidate cells per position
                that the DP considers. Larger = closer to globally optimal but
                proportionally slower (K² transitions per position). Tied to the
                GUI "Search depth (K)" slider. Default 64.
        """
        try:
            def progress_cb(pct):
                if cancel_event.is_set():
                    return
                self.after(0, self._centered_encoder_on_progress, token, pct)

            def row_cb(y_done, cells_snapshot):
                if cancel_event.is_set():
                    return
                cells_copy = list(cells_snapshot)
                self.after(0, self._centered_encoder_on_row, token, y_done, cells_copy, preset)

            cells = encode_image_to_80x100_centered_1024_viterbi(
                src, preset,
                k_candidates=k_candidates,
                dither_strength=1.0,
                progress_cb=progress_cb,
                row_cb=row_cb,
                cancel_event=cancel_event,
                chroma_lowpass=chroma_lowpass,
            )
            if cancel_event.is_set():
                self.after(0, self._centered_encoder_on_cancelled, token)
            else:
                self.after(0, self._centered_encoder_on_done, token, cells, preset)
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            self.after(0, self._centered_encoder_on_error, token, err_msg)

    def _centered_encoder_on_progress(self, token, pct):
        """Update status bar with percent done. Runs on GUI thread."""
        if token != self._centered_encoder_token:
            return  # stale callback from a cancelled encoder
        try:
            k_value = 64
            if hasattr(self, 'text_ntsc_k_var'):
                try:
                    k_value = int(self.text_ntsc_k_var.get())
                except Exception:
                    pass
            self.set_status(
                f"Encoding 640x100 (1024 Colors) Viterbi K={k_value} — {pct}% (background)"
            )
            self.set_progress(pct)
        except Exception:
            pass

    def _centered_encoder_on_row(self, token, y_done, cells_snapshot, preset):
        """Render the partial preview with rows up to y_done filled in.
        Runs on GUI thread. Throttled to every ~5 rows to keep preview
        updates from saturating the event loop."""
        if token != self._centered_encoder_token:
            return  # stale
        # Throttle: only render every 5 rows (still visibly rolling, much cheaper).
        if (y_done % 5) != 0 and y_done != 99:
            return
        try:
            placeholder = getattr(self, '_centered_encoder_placeholder', None)
            preview = self._render_centered_preview_from_cells(
                cells_snapshot, preset, rows_filled=y_done + 1,
                background_image=placeholder)
            self.output_pimage = preview
            self._update_right_preview()
        except Exception:
            pass  # never let preview rendering crash the encoder

    def _centered_encoder_on_done(self, token, cells, preset):
        """Encoder finished. Stash cells, render the final preview, restore
        status. Runs on GUI thread."""
        if token != self._centered_encoder_token:
            return  # a newer encoder has been started; ignore this result
        try:
            self.text_ntsc_centered_cells = cells
            preview = self._render_centered_preview_from_cells(
                cells, preset, rows_filled=100)
            self.output_pimage = preview
            self._update_right_preview()
            self.set_status("Ready.")
            self.set_progress(100)
        except Exception as e:
            self.set_status(f"Encode finished but preview update failed: {e}")
        finally:
            self._centered_encoder_thread = None
            # Disable STOP button
            try:
                if getattr(self, "text_ntsc_stop_btn", None) is not None:
                    self.text_ntsc_stop_btn.state(["disabled"])
            except Exception:
                pass

    def _centered_encoder_on_error(self, token, err_msg):
        """Worker raised an exception. Surface it. Runs on GUI thread."""
        if token != self._centered_encoder_token:
            return
        self.set_status(f"Encode failed: {err_msg}")
        self._centered_encoder_thread = None
        # Disable STOP button
        try:
            if getattr(self, "text_ntsc_stop_btn", None) is not None:
                self.text_ntsc_stop_btn.state(["disabled"])
        except Exception:
            pass

    def _centered_encoder_on_cancelled(self, token):
        """Worker exited early because cancel_event was set. Runs on GUI thread.
        Only acts if this is still the most recent encoder (token match) — if
        a NEW encoder has started since, we don't want to disable its STOP."""
        if token != self._centered_encoder_token:
            # The user started a NEW encoder before this one exited. Leave the
            # button state alone — the new encoder's own lifecycle controls it.
            return
        self.set_status("Encode cancelled.")
        self._centered_encoder_thread = None
        # Disable STOP button
        try:
            if getattr(self, "text_ntsc_stop_btn", None) is not None:
                self.text_ntsc_stop_btn.state(["disabled"])
        except Exception:
            pass

    def _render_centered_preview_from_cells(self, cells, preset, rows_filled=100,
                                            background_image=None):
        """Render a 640x200 letterboxed preview from (char, attr) cells.

        rows_filled: only render rows 0..rows_filled-1 from the cells.
        background_image: optional 640x200 PIL image to use for rows that haven't
            been encoded yet (and for the top/bottom black bars). When provided,
            unfilled rows show the placeholder content rather than black, so the
            rolling preview overlays the placeholder progressively as the
            encoder fills in rows from the top.
        """
        params = _COMPOSITE_PRESETS.get(preset, _COMPOSITE_PRESETS["Old CGA"])
        hue, sat, bri, con, shp, new_cga, cgamode = params
        ctx = _ReCompositeContextPy()
        ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri,
                   contrast=con, sharpness=shp, new_cga=new_cga)
        ctx.update_cga16_color(int(cgamode))

        # Start with the background (placeholder) or black canvas
        if background_image is not None and background_image.size == (640, 200):
            preview = background_image.copy()
        else:
            preview = Image.new("RGB", (640, 200), (0, 0, 0))

        # Render the filled rows and paste them onto the preview at the
        # centered offset (y=50). Unfilled rows are left as the placeholder.
        if rows_filled > 0:
            rows_to_render = min(rows_filled, 100)
            rgb_out = []
            for ycell in range(rows_to_render):
                in_rgbi = [0] * 640
                for xcell in range(80):
                    ch, attr = cells[ycell * 80 + xcell]
                    row0 = _CGA_FONT[ch][0]
                    fg = attr & 0x0F
                    bg = (attr >> 4) & 0x0F
                    x0 = xcell * 8
                    for k in range(8):
                        bit = (row0 >> (7 - k)) & 1
                        in_rgbi[x0 + k] = fg if bit else bg
                rgb_out.extend(ctx.decode_scanline_rgba(0, in_rgbi))

            filled_img = Image.new("RGB", (640, rows_to_render))
            filled_img.putdata([_quantize_rgb444(px) for px in rgb_out])
            # Paste rows on top of placeholder at the centered offset.
            preview.paste(filled_img, (0, 50))

        return preview


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
        # Apply live input adjustments to the LEFT preview.
        preview = apply_input_adjustments(
            self.src_image,
            brightness_val=int(self.in_brightness_var.get()),
            contrast_val=int(self.in_contrast_var.get()),
            r_gain_pct=int(self.in_r_gain_var.get()),
            g_gain_pct=int(self.in_g_gain_var.get()),
            b_gain_pct=int(self.in_b_gain_var.get()),
        )
        max_w, max_h = 400, 400
        preview.thumbnail((max_w, max_h), resample=get_resample_filter("Lanczos"))
        self.src_tk_image = ImageTk.PhotoImage(preview)
        self.left_label.configure(image=self.src_tk_image, text="")

    

    
    def _schedule_left_preview_update(self, *_args):
        """Debounced update so slider drags don't re-render on every tick."""
        if self._left_preview_after_id is not None:
            try:
                self.after_cancel(self._left_preview_after_id)
            except Exception:
                pass
            self._left_preview_after_id = None
        # 30ms debounce feels responsive without hammering CPU
        self._left_preview_after_id = self.after(30, self._update_left_preview)

    def _reset_input_adjust(self):
        """Reset input-adjust sliders to defaults."""
        try:
            self.in_brightness_var.set(0)
            self.in_contrast_var.set(0)
            self.in_r_gain_var.set(100)
            self.in_g_gain_var.set(100)
            self.in_b_gain_var.set(100)
            self._schedule_left_preview_update()
        except Exception:
            pass



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

        # --- Output-pixel aspect normalization ---
        # Keep previews in a simple nearest-neighbor "square pixel" space.
        # Common CGA-mode normalizations:
        #   80x100  -> 320x200 (x4, x2)
        #   160x100 -> 320x200 (x2, x2)
        #   160x200 -> 320x200 (x2, x1)
        #   640x200 -> 640x400 (x1, x2)
        w, h = img.size
        norm_w, norm_h = w, h
        try:
            if (w, h) == (80, 100):
                norm_w, norm_h = (w * 4), (h * 2)
            elif (w, h) == (160, 100):
                norm_w, norm_h = (w * 2), (h * 2)
            elif (w, h) == (160, 200):
                norm_w, norm_h = (w * 2), h
            elif (w, h) == (640, 200):
                norm_w, norm_h = w, (h * 2)
        except Exception:
            norm_w, norm_h = w, h

        if (norm_w, norm_h) != (w, h):
            img = img.resize((norm_w, norm_h), resample=get_resample_filter("Nearest"))
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
        if getattr(self, 'out_canvas', None) is not None:
            if self.out_canvas_img_id is None:
                self.out_canvas_img_id = self.out_canvas.create_image(0, 0, anchor='nw', image=self.out_tk_image)
            else:
                self.out_canvas.itemconfigure(self.out_canvas_img_id, image=self.out_tk_image)
            w, h = preview.size
            self.out_canvas.configure(scrollregion=(0, 0, w, h))
        else:
            # Fallback for older UI variants (right_label was used before the scrollable canvas);
            # the current UI always has out_canvas, so this branch is defensive only.
            rl = getattr(self, 'right_label', None)
            if rl is not None:
                rl.configure(image=self.out_tk_image, text="")
        try:
            if hasattr(self, "preview_size_label"):
                w, h = preview.size
                self.preview_size_label.configure(text=f"Preview: {w}x{h}")
        except Exception:
            pass
        self._update_tone_preview()

        # Mode Switch layout map (diagnostic): full-width image showing per-scanline
        # segment positions with chosen palette colors filling each segment's actual x-range.
        if getattr(self, 'ms_pal_pimage', None) is not None:
            strip = self.ms_pal_pimage
            try:
                # Match the preview's WIDTH (since we now display the strip as a banner below the canvas).
                pw = preview.size[0]
                # Preserve aspect of the strip image (which is target_w x 200).
                ph = max(20, int(strip.size[1] * (pw / strip.size[0])))
                strip_r = strip.resize((pw, ph), resample=get_resample_filter('Nearest'))
                self.ms_pal_tk = ImageTk.PhotoImage(strip_r)
                self.ms_pal_label.configure(image=self.ms_pal_tk, text='')
                # Show the frame (pack it if not already shown)
                if hasattr(self, 'ms_pal_frame') and not self.ms_pal_frame.winfo_ismapped():
                    self.ms_pal_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(4, 4))
            except Exception:
                self.ms_pal_label.configure(image='', text='')
                if hasattr(self, 'ms_pal_frame') and self.ms_pal_frame.winfo_ismapped():
                    self.ms_pal_frame.pack_forget()
        else:
            self.ms_pal_label.configure(image='', text='')
            if hasattr(self, 'ms_pal_frame') and self.ms_pal_frame.winfo_ismapped():
                self.ms_pal_frame.pack_forget()

    def on_preview_scale_changed(self, event=None):
        """When Preview scale changes, re-render the output preview (and size label)."""
        try:
            self._update_right_preview()
        except Exception:
            pass

    def on_convert(self):
        global STATUS_CB
        self._reset_status_steps()
        self.status_step('Convert clicked')

        # Enable module-level tracing during this conversion
        try:
            STATUS_CB = self.status_step
        except Exception:
            pass

        # Settings dump (every conversion). All references are guarded with getattr().
        try:
            self.status_step(f"MODE: {self.mode_var.get()}")
        except Exception:
            self.status_step("MODE: <error>")

        def _dump_var(lbl, var):
            try:
                if var is None:
                    self.status_step(f"{lbl}: <missing>")
                else:
                    self.status_step(f"{lbl}: {var.get()}")
            except Exception:
                self.status_step(f"{lbl}: <error>")

        _dump_var("Scaling", getattr(self, "scale_var", None))
        _dump_var("PreviewScale", getattr(self, "preview_scale_var", None))
        _dump_var("DitherFamily", getattr(self, "dither_family_var", None))
        _dump_var("DitherMethod", getattr(self, "diffusion_var", None))
        _dump_var("DitherIntensity", getattr(self, "dither_intensity_var", None))
        _dump_var("OrderedSize", getattr(self, "ordered_size_var", None))
        _dump_var("OrderedStrength", getattr(self, "ordered_strength_var", None))
        _dump_var("CGA Palette", getattr(self, "palette_var", None))
        _dump_var("BG Color Selection", getattr(self, "bg_color_var", None))
        _dump_var("CompositePalette", getattr(self, "composite_palette_var", None))
        _dump_var("ModeSwitchSegments", getattr(self, "ms_switches_var", None))
        _dump_var("InputBrightness", getattr(self, "in_brightness_var", None))
        _dump_var("InputContrast", getattr(self, "in_contrast_var", None))
        _dump_var("InputRGain", getattr(self, "in_r_gain_var", None))
        _dump_var("InputGGain", getattr(self, "in_g_gain_var", None))
        _dump_var("InputBGain", getattr(self, "in_b_gain_var", None))
        _dump_var("TargetVideoCard", getattr(self, "target_video_var", None))
        _dump_var("StaggerMode", getattr(self, "ms_stagger_mode_var", None))
        _dump_var("StaggerOptimize", getattr(self, "ms_stagger_optimize_var", None))

        try:
            if self.src_image is None:
                self.status_step("INPUT: None")
            else:
                self.status_step(f"INPUT: size={self.src_image.size} mode={self.src_image.mode}")
        except Exception:
            self.status_step("INPUT: <error>")

        if self.src_image is None:
            messagebox.showinfo("No image", "Please open an image first.")
            return

        self.set_status("Converting...")
        self.set_progress(0)
        # Clear Mode Switch diagnostic strip unless a Mode Switch conversion sets it
        self.ms_pal_pimage = None

        mode = self.mode_var.get()
        # Remember the mode used to generate the current output so the preview can
        # apply mode-specific display adjustments (e.g., composite aspect correction)
        # even if the user changes the dropdown after converting.
        self.last_output_mode = mode

        palette = None
        composite_palette = None
        if self.is_composite_mode() or self.is_text_ntsc_mode():
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

        # Apply input adjustments ONCE here; every conversion branch uses this adjusted source.
        # Previously several branches (Mode Switch / HiColor / NTSC-4K / Optimize) bypassed this.
        adjusted_src = apply_input_adjustments(
            self.src_image,
            brightness_val=int(self.in_brightness_var.get()),
            contrast_val=int(self.in_contrast_var.get()),
            r_gain_pct=int(self.in_r_gain_var.get()),
            g_gain_pct=int(self.in_g_gain_var.get()),
            b_gain_pct=int(self.in_b_gain_var.get()),
        )

        resized = resize_with_mode(
            adjusted_src,
            target_w,
            target_h,
            scale_mode,
            resample_name,
        )

        self.set_progress(20)

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

        self.set_progress(30)

        if self.is_640_2color_mode_switch_mode():
            # 640x200 (2 Colors) Mode Switch:
            #   - background is fixed = black (CGA mode 06h has no bg register)
            #   - foreground color picked per scanline (and per segment within scanline) from 16 candidates
            scaled = resize_with_mode(adjusted_src, 640, 200, scale_mode, resample_name)
            toned_ms640 = scaled

            want_pal_strip = bool(getattr(self, 'ms_show_palette_var', tk.BooleanVar(value=False)).get())
            seg_n = int(getattr(self, "ms_switches_var", tk.IntVar(value=1)).get())

            # Resolve stagger mode from the dropdown
            _stagger_label = getattr(self, "ms_stagger_mode_var", tk.StringVar(value="None")).get()
            if _stagger_label == "Triangle wave" and seg_n > 1:
                stagger_mode = "triangle"
            elif _stagger_label == "Random per line" and seg_n > 1:
                stagger_mode = "random"
            else:
                stagger_mode = "none"

            stagger_step = None
            stagger_seed = 42
            if stagger_mode == "triangle":
                seg_w = 640 // seg_n
                stagger_step = max(1, seg_w // 4)  # auto-Δ default
                if bool(getattr(self, "ms_stagger_optimize_var", tk.BooleanVar(value=False)).get()):
                    self.set_status("Optimizing stagger step (image-aware)...")
                    stagger_step = find_best_stagger_step_640(toned_ms640.convert("RGB"), seg_n)
                    self.status_step(f"Best stagger step (640): {stagger_step} px")

            if dither_family == "Ordered":
                pimg = quantize_640x200_2color_mode_switch(
                    toned_ms640,
                    dither_family="Ordered",
                    ordered_matrix_size=ordered_size,
                    ordered_strength=ordered_strength,
                    serpentine=serpentine,
                    segments_per_line=seg_n,
                    stagger_mode=stagger_mode,
                    stagger_step=stagger_step,
                    stagger_seed=stagger_seed,
                    progress_cb=(lambda frac: self.set_progress(int(30 + frac*65))),
                    return_palettes=True,
                )
            elif dither_family in ("Diffusion", "Error diffusion"):
                pimg = quantize_640x200_2color_mode_switch(
                    toned_ms640,
                    dither_family="Diffusion",
                    diffusion_name=diffusion_method,
                    diffusion_intensity=dither_intensity,
                    serpentine=serpentine,
                    segments_per_line=seg_n,
                    stagger_mode=stagger_mode,
                    stagger_step=stagger_step,
                    stagger_seed=stagger_seed,
                    progress_cb=(lambda frac: self.set_progress(int(30 + frac*65))),
                    return_palettes=True,
                )
            else:
                pimg = quantize_640x200_2color_mode_switch(
                    toned_ms640,
                    dither_family="None",
                    serpentine=serpentine,
                    segments_per_line=seg_n,
                    stagger_mode=stagger_mode,
                    stagger_step=stagger_step,
                    stagger_seed=stagger_seed,
                    progress_cb=(lambda frac: self.set_progress(int(30 + frac*65))),
                    return_palettes=True,
                )

            pals_by_y = None
            if isinstance(pimg, tuple) and len(pimg) == 2:
                pimg, pals_by_y = pimg

            # Always remember the per-line palettes for the COM exporter (and any
            # subsequent diagnostic uses). Falls back to None if we didn't request them.
            self.ms_pals_by_y = pals_by_y
            self.ms_seg_n = seg_n
            self.ms_stagger_mode = stagger_mode
            self.ms_stagger_step = stagger_step
            self.ms_stagger_seed = stagger_seed

            # Full-width diagnostic strip: shows where each segment falls on each scanline
            # (including the staggered offset, if any) with the chosen FG color filling the
            # segment's actual x-range. BG is always black for 640 mode switch.
            if want_pal_strip and pals_by_y is not None:
                self.ms_pal_pimage = self._build_mode_switch_strip(
                    pals_by_y,
                    target_w=640,
                    seg_n=seg_n,
                    stagger_mode=stagger_mode,
                    stagger_step=stagger_step,
                    stagger_seed=stagger_seed,
                    palette_size=2,
                )
            else:
                self.ms_pal_pimage = None

            self.output_pimage = pimg
            self._update_right_preview(); self._update_mid_preview()
            self.set_progress(100)
            self.set_status("Ready.")
            try:
                STATUS_CB = None
            except Exception:
                pass
            return

        if self.is_mode_switch_mode():
            # Mode-switch raster palette per scanline (CGA 320x200 4-color with per-scanline palette/background changes)
            # Work on a 320x200 image regardless of other target sizes.
            scaled = resize_with_mode(adjusted_src, 320, 200, scale_mode, resample_name)
            toned_ms = scaled  # keep full RGB so dithering influences per-scanline palette selection
            # Mode Switch background behavior:
            #   - 'Multiple' => allow background/palette to vary per scanline (current behavior)
            #   - any color  => force that CGA background color for all scanlines
            forced_bg_idx = None
            bg_sel = getattr(self, 'bg_color_var', tk.StringVar(value='Multiple')).get()
            if bg_sel and bg_sel != 'Multiple' and bg_sel in CGA_COLOR_NAMES:
                forced_bg_idx = CGA_COLOR_NAMES.index(bg_sel)

            want_pal_strip = bool(getattr(self, 'ms_show_palette_var', tk.BooleanVar(value=False)).get())
            seg_n_320 = int(getattr(self, "ms_switches_var", tk.IntVar(value=1)).get())

            # Resolve stagger mode from the dropdown
            _stagger_label_320 = getattr(self, "ms_stagger_mode_var", tk.StringVar(value="None")).get()
            if _stagger_label_320 == "Triangle wave" and seg_n_320 > 1:
                stagger_mode_320 = "triangle"
            elif _stagger_label_320 == "Random per line" and seg_n_320 > 1:
                stagger_mode_320 = "random"
            else:
                stagger_mode_320 = "none"

            stagger_step_320 = None
            stagger_seed_320 = 42
            if stagger_mode_320 == "triangle":
                seg_w_320 = 320 // seg_n_320
                stagger_step_320 = max(1, seg_w_320 // 4)
                if bool(getattr(self, "ms_stagger_optimize_var", tk.BooleanVar(value=False)).get()):
                    self.set_status("Optimizing stagger step (image-aware, slow for 320)...")
                    stagger_step_320 = find_best_stagger_step_320(toned_ms.convert("RGB"), seg_n_320)
                    self.status_step(f"Best stagger step (320): {stagger_step_320} px")

            # Resolve tweaked palette mode from GUI ("off" = mode 04 only, "on" = mode 05 Tweaked only)
            tweaked_mode_320 = getattr(self, "tweaked_mode_var", tk.StringVar(value="off")).get()

            if dither_family == "Ordered":
                pimg = quantize_320x200_mode_switch(
                    toned_ms,
                    forced_bg_idx=forced_bg_idx,
                    dither_family="Ordered",
                    ordered_matrix_size=ordered_size,
                    ordered_strength=ordered_strength,
                    serpentine=serpentine,
                    segments_per_line=seg_n_320,
                    stagger_mode=stagger_mode_320,
                    stagger_step=stagger_step_320,
                    stagger_seed=stagger_seed_320,
                    progress_cb=(lambda frac: self.set_progress(int(30 + frac*65))),
                    return_palettes=True,
                    tweaked_mode=tweaked_mode_320,
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
                    segments_per_line=seg_n_320,
                    stagger_mode=stagger_mode_320,
                    stagger_step=stagger_step_320,
                    stagger_seed=stagger_seed_320,
                    progress_cb=(lambda frac: self.set_progress(int(30 + frac*65))),
                    return_palettes=True,
                    tweaked_mode=tweaked_mode_320,
                )
            else:
                pimg = quantize_320x200_mode_switch(
                    toned_ms,
                    forced_bg_idx=forced_bg_idx,
                    dither_family="None",
                    serpentine=serpentine,
                    segments_per_line=seg_n_320,
                    stagger_mode=stagger_mode_320,
                    stagger_step=stagger_step_320,
                    stagger_seed=stagger_seed_320,
                    progress_cb=(lambda frac: self.set_progress(int(30 + frac*65))),
                    return_palettes=True,
                    tweaked_mode=tweaked_mode_320,
                )

            # If requested, Mode Switch can return (image, palettes_by_scanline)
            pals_by_y = None
            if isinstance(pimg, tuple) and len(pimg) == 2:
                pimg, pals_by_y = pimg

            # Always remember the per-line palettes for the COM exporter
            self.ms_pals_by_y = pals_by_y
            self.ms_seg_n = seg_n_320
            self.ms_stagger_mode = stagger_mode_320
            self.ms_stagger_step = stagger_step_320
            self.ms_stagger_seed = stagger_seed_320

            # Full-width diagnostic strip (320x200): each scanline shows where the
            # actual segment boundaries fell (with stagger if enabled), and within
            # each segment the 4 chosen palette colors as vertical stripes.
            if want_pal_strip and pals_by_y is not None:
                self.ms_pal_pimage = self._build_mode_switch_strip(
                    pals_by_y,
                    target_w=320,
                    seg_n=seg_n_320,
                    stagger_mode=stagger_mode_320,
                    stagger_step=stagger_step_320,
                    stagger_seed=stagger_seed_320,
                    palette_size=4,
                )
            else:
                self.ms_pal_pimage = None

            self.output_pimage = pimg
            self._update_right_preview(); self._update_mid_preview()
            self.set_progress(100)
            self.set_status("Ready.")
            try:
                STATUS_CB = None
            except Exception:
                pass
            return
        if self.is_16color_char_mode():
            # Text-block mode constraint is too strong to dither "during" mapping.
            self.set_progress(40)
            # Instead:
            #   1) Convert to a normal 640x200 CGA 16-colour bitmap using the selected dither.
            #   2) Map that 16-colour result into the 8x2 character-slice constraints.
            if dither_family == "Ordered":
                pre_p = apply_ordered_dither(toned, CGA_16COLOR_PALETTE, matrix_size=ordered_size, strength=ordered_strength)
            elif dither_family in ("Error diffusion", "Diffusion"):
                pre_p = apply_diffusion_dither(toned, CGA_16COLOR_PALETTE, diffusion_method, intensity=dither_intensity, serpentine=serpentine)
            else:
                pre_p = apply_diffusion_dither(toned, CGA_16COLOR_PALETTE, "None", intensity=0.0)

            self.set_progress(65)
            pre_indices = list(pre_p.getdata())
            pimg = quantize_char16_textblock_from_indices(
                pre_indices,
                subsample=bool(self.char16_subsample_var.get()),
                progress_cb=(lambda frac: self.set_progress(int(65 + frac * 30)))
            )

        elif self.is_hicolor_mode():
            # 80x100 HiColor: scale the source into 80x100 using the selected scaling mode,
            # apply dithering in 80x100 cell space, then expand to 640x200 using 2x8 patterns.
            resized80 = resize_with_mode(adjusted_src, 80, 100, scale_mode, resample_name)
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

        elif self.is_text_ntsc_mode():
            # CGA NTSC text-trick modes (512 and 1024 colors).
            # Logical resolution: 80x100 cells (each cell is 8x2 CGA pixels).
            # 
            # 512-color mode: uses chars 0x55 (pattern 0xCC) and 0x13 (pattern 0x66).
            #   These chars have IDENTICAL row-0 and row-1 patterns → work in 
            #   the standard 80x100 mode (2 scanlines/row), no per-frame CRTC trickery.
            #   "Set and forget" — static image, zero CPU load after setup.
            # 
            # 1024-color mode would ADD chars 0xB0 and 0xB1 (patterns 0x22, 0x55),
            #   whose row 0 ≠ row 1 — requires the CRTC mini-frame trick to display
            #   correctly. Currently the simulation/encoder only uses the 512 subset
            #   (so 1024-mode preview is actually 512-mode preview); full 1024 support
            #   is planned for the future.
            preset = (self.composite_palette_var.get() or "Old CGA").strip()
            lut = _build_text_ntsc_4k_lut(preset)  # [(avg_rgb, fg, bg, pat, swap), ...]
            palette1024 = [avg for (avg, _fg, _bg, _pat, _swap) in lut]

            # 1) Scale source into 80x100 logical cells.
            src80 = resize_with_mode(adjusted_src, 80, 100, scale_mode, resample_name).convert("RGB")

            # Stash the original 80x100 source for use by the centered-1024
            # COM export, which re-encodes via the full unique-pattern pair
            # encoder (NOT via the simplified 4-pattern preview path used here).
            self.text_ntsc_src80 = src80

            # Also produce a 640x100 source for the 40-pattern encoder, which
            # operates at the full horizontal resolution of the composite-decoded
            # output. Sampled directly from the adjusted source (not from src80,
            # which has already lost horizontal detail by being resized to 80 wide).
            src640 = resize_with_mode(adjusted_src, 640, 100, scale_mode, resample_name).convert("RGB")
            self.text_ntsc_src640 = src640

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
            
            # Stash for COM export (512-color mode uses these to pack chars + attrs)
            self.text_ntsc_chosen = chosen

            # Centered 1024-color modes come in two flavors as separate
            # dropdown items:
            #   "80x100 (1024 Colors)"  → 4-pattern LUT encoder (synchronous, fast)
            #   "640x100 (1024 Colors)" → 40-pattern exhaustive encoder (background)
            # Both produce centered output via the L100V4 CRTC builder. The
            # 4-pattern path above already populated text_ntsc_chosen and the
            # 4-pattern preview render. The 40-pattern path kicks off a worker
            # thread that posts the real preview asynchronously.
            use_40_patterns = self.is_text_ntsc_640_mode()

            if use_40_patterns:
                # ---- 640x100 (1024 Colors) path: BACKGROUND THREAD ----
                # The Viterbi per-row DP encoder takes ~80-100 seconds per image.
                # Running it on the GUI thread would freeze the window. So we:
                #   1. Letterbox the source image as an immediate placeholder.
                #   2. Kick off a worker thread that runs the encoder, posting
                #      progress and per-row preview updates back to the GUI via
                #      self.after() (Tk-safe).
                #   3. When the worker finishes, it updates the preview to the
                #      true 40-pattern render and stashes cells for export.
                #
                # Cancellation: if the user starts a new Convert while one is in
                # progress, we set the cancel event on the running worker and
                # spawn a new one. The old worker exits at the next row boundary.

                # Cancel any in-flight worker
                prev_cancel = getattr(self, '_centered_encoder_cancel', None)
                if prev_cancel is not None:
                    prev_cancel.set()

                # Build placeholder: just the source image scaled to 640x100
                # and letterboxed. As the slow 40-pattern encoder fills rows
                # from the top, the real output overlays the source row by
                # row, giving a visible "rendering over the source" effect.
                # This is cheaper than synthesizing a 4-pattern preview and
                # gives the user a clear visual reference for what's being
                # encoded versus what's still source.
                preview_placeholder = Image.new("RGB", (640, 200), (0, 0, 0))
                preview_placeholder.paste(src640, (0, 50))

                pimg = preview_placeholder

                # Stash the placeholder so the rolling preview can overlay
                # encoded rows on top of it instead of blacking out unfilled
                # rows. As the encoder completes rows top-to-bottom, those
                # rows replace the placeholder source while remaining rows
                # continue to show the original source for context.
                self._centered_encoder_placeholder = preview_placeholder.copy()

                # Capture state needed by the worker — don't read self in worker.
                self._centered_encoder_token = (self._centered_encoder_token + 1) & 0x7FFFFFFF
                worker_token = self._centered_encoder_token

                # Chroma low-pass: tied to the "Match contrast / tone to palette"
                # checkbox. When True, the encoder applies a 4-pixel-wide box
                # filter to the a,b channels of the Lab target before scoring.
                # This prevents the encoder from chasing chroma details finer
                # than the composite kernel can carry (which would produce
                # noisy output). When False, the encoder scores literally
                # against the source — the user accepts noise on inputs with
                # high-frequency chroma transitions.
                chroma_lowpass = bool(self.tone_var.get()) if hasattr(self, 'tone_var') else False

                # Search depth K from the slider (default 64). Bounded to a
                # sensible range to prevent silly values from the slider.
                k_value = 64
                if hasattr(self, 'text_ntsc_k_var'):
                    try:
                        k_value = max(8, min(256, int(self.text_ntsc_k_var.get())))
                    except Exception:
                        k_value = 64

                # Spin up worker. Passes src640 (640x100 source produced above)
                # plus the chroma_lowpass flag and search depth K.
                self._centered_encoder_cancel = threading.Event()
                cancel_event = self._centered_encoder_cancel
                worker = threading.Thread(
                    target=self._centered_encoder_worker,
                    args=(src640, preset, worker_token, cancel_event, chroma_lowpass, k_value),
                    daemon=True,
                )
                self._centered_encoder_thread = worker
                # Clear any stale cells from a previous encode so export waits for the real ones
                self.text_ntsc_centered_cells = None
                # Enable STOP button while encoding
                try:
                    if getattr(self, "text_ntsc_stop_btn", None) is not None:
                        self.text_ntsc_stop_btn.state(["!disabled"])
                except Exception:
                    pass
                worker.start()

                # The worker will update status and preview asynchronously.
                # Set initial status before returning to the synchronous convert flow.
                est_secs = 85.0 * (max(1, k_value) / 64.0) ** 1.7
                if est_secs < 60:
                    est_str = f"~{int(round(est_secs))}s"
                else:
                    est_str = f"~{est_secs/60:.1f}min"
                self.set_status(
                    f"Encoding 640x100 (1024 Colors) Viterbi K={k_value} — 0% (background, {est_str})"
                )
            else:
                # 4-pattern path: drop any stashed 40-pattern cells (so export
                # for 4-pattern doesn't accidentally use stale 40-pattern cells).
                self.text_ntsc_centered_cells = None

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

                # For the CENTERED variant, the actual hardware display is:
                #   ~50 scanlines of black overscan (top)
                #   100 scanlines of image content (MaxSL=0 = 1 scanline per cell-row)
                #   ~50 scanlines of black overscan (bottom)
                # Show this in the preview by letterboxing the 640x200 raster:
                # take the existing 200-row preview (which has each cell-row doubled),
                # collapse to 100 scanlines (every other row), then center it on a
                # fresh 640x200 black canvas. Result: 50 black + 100 image + 50 black,
                # which matches the on-screen geometry of the COM output.
                if self.is_text_ntsc_centered_mode():
                    centered = Image.new("RGB", (640, 200), (0, 0, 0))
                    # Take only the odd-indexed rows to collapse 200 → 100 (or
                    # equivalently re-render at 1 scanline per cell-row).
                    single_rows = rgb_img.crop((0, 0, 640, 200))
                    # Use resize to halve height (better than nearest sampling of alt rows)
                    single_rows = single_rows.resize((640, 100), Image.LANCZOS)
                    centered.paste(single_rows, (0, 50))
                    rgb_img = centered

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
        if not self.is_text_ntsc_mode():
            self.text_ntsc_chosen = None
            self.text_ntsc_src80 = None
            self.text_ntsc_src640 = None
            self.text_ntsc_centered_cells = None
        self._update_right_preview()
        self.set_status("Ready.")
        # Clear module-level tracing hook so Tk-only callbacks don't keep firing it.
        try:
            STATUS_CB = None
        except Exception:
            pass

    def on_optimize(self):
        if self.src_image is None:
            messagebox.showinfo("No image", "Please open an image first.")
            return

        # Both 16-color bitmap modes have fixed palette; nothing to optimize
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

        # Apply input adjustments before scoring palettes (matches on_convert behavior)
        adjusted_src = apply_input_adjustments(
            self.src_image,
            brightness_val=int(self.in_brightness_var.get()),
            contrast_val=int(self.in_contrast_var.get()),
            r_gain_pct=int(self.in_r_gain_var.get()),
            g_gain_pct=int(self.in_g_gain_var.get()),
            b_gain_pct=int(self.in_b_gain_var.get()),
        )

        base_resized = resize_with_mode(adjusted_src, target_w, target_h, scale_mode, resample_name)
        _, grad_map = compute_gray_and_gradient(base_resized)

        step = 2
        self.set_status("Optimizing palette...")

        # 4-color mode: optimize BOTH the palette family AND background color
        if self.is_4color_mode():
            best_base = None
            best_bg = None
            best_score = float("inf")

            base_names = list(CGA_4COLOR_BASESETS.keys())
            bg_names = list(CGA_COLOR_NAMES)
            total = len(base_names) * len(bg_names)
            i = 0

            for bg_name in bg_names:
                pal_bg = None
                for base_name in base_names:
                    i += 1
                    if i == 1 or i % 16 == 0:
                        self.set_status(f"Optimizing palette... {i}/{total}")
                    pal_bg = build_cga_4color_palette(base_name, bg_name)
                    if self.tone_var.get():
                        img_for_score, _dbg = tone_image_to_palette_debug(base_resized, pal_bg)
                    else:
                        img_for_score = base_resized
                    score = compute_palette_score(img_for_score, pal_bg, grad_map, bg_index=0, step=step)
                    if score < best_score:
                        best_score = score
                        best_base = base_name
                        best_bg = bg_name

            if best_base is None or best_bg is None:
                messagebox.showinfo("No palette", "No palettes available to optimize.")
                return

            self.palette_var.set(best_base)
            if getattr(self, "bg_color_var", None) is not None:
                self.bg_color_var.set(best_bg)

            self.on_convert()
            self.set_status("Ready.")
            return

        # 2-color mode: optimize foreground color (background is always black)
        if self.is_mono_mode():
            palettes = CGA_MONO_PALETTES
            best_name = None
            best_score = float("inf")
            total = len(palettes)

            for j, (name, pal) in enumerate(palettes.items(), start=1):
                if j == 1 or j % 8 == 0:
                    self.set_status(f"Optimizing palette... {j}/{total}")
                score = compute_palette_score(base_resized, pal, grad_map, bg_index=0, step=step)
                if score < best_score:
                    best_score = score
                    best_name = name

            if best_name is None:
                messagebox.showinfo("No palette", "No palettes available to optimize.")
                return

            self.palette_var.set(best_name)
            self.on_convert()
            self.set_status("Ready.")
            return

        # Other modes: nothing to optimize
        self.on_convert()
        self.set_status("Ready.")

    def on_export_com(self):
        """Export the current converted image as a DOS .COM (static CGA)."""
        mode = self.mode_var.get()

        SUPPORTED = (
            "320x200 (4 Colors)",
            "320x200 (4 Colors) Mode Switch",
            "640x200 (2 Colors)",
            "160x200 (16 Colors) Composite",
            "160x100 (16 Colors)",
            "640x200 (16 Colors) Char",
            "80x100 (4352 Colors) HiColor",
            "80x100 (512 Colors)",
            "80x100 (1024 Colors) Mini-Frames",
            "80x100 (1024 Colors)",
            "640x100 (1024 Colors)",
        )
        if mode not in SUPPORTED:
            # Provide specific guidance for the explicitly-not-yet-supported modes.
            if mode == "640x200 (2 Colors) Mode Switch":
                messagebox.showinfo(
                    "Export COM — not yet supported",
                    "640x200 (2 Colors) Mode Switch .COM export is not yet implemented.\n\n"
                    "Per-scanline foreground changes are achievable on real hardware by "
                    "polling the CGA status port (3DAh bit 0) for hsync and writing the "
                    "new foreground nibble to port 3D9h. Multi-segment-per-scanline mode "
                    "additionally requires cycle-counted code to write 3D9h at known "
                    "horizontal screen positions.\n\n"
                    "Use 'Save GIF...' to export a previewable image for now."
                )
            else:
                messagebox.showinfo(
                    "Export COM",
                    "COM export is supported for:\n"
                    "- 320x200 (4-color)\n"
                    "- 320x200 (4-color) Mode Switch (N=1 only)\n"
                    "- 640x200 (2-color)\n"
                    "- 160x200 Composite (16-color)\n"
                    "- 160x100 (16-color)\n"
                    "- 640x200 (char 16-color)\n"
                    "- 80x100 (4352 Colors) HiColor\n"
                    "- 80x100 (512 Colors)\n"
                    "- 80x100 (1024 Colors) Mini-Frames\n"
                    "- 80x100 (1024 Colors)\n"
                    "- 640x100 (1024 Colors)",
                )
            return

        if self.output_pimage is None:
            messagebox.showinfo("Export COM", "Please click Convert first so there is an output image to export.")
            return

        # Helper: pick the right COM stub for 80x100 text-trick modes
        # based on the user's "Target video card" selection.
        target_video = (getattr(self, "target_video_var", None).get()
                        if getattr(self, "target_video_var", None) is not None
                        else "CGA")

        def build_text80x100_com(buf16000: bytes) -> bytes:
            """Build a COM that programs 80x100 text-mode for either CGA or VGA."""
            if target_video == "EGA/VGA":
                return build_com_text_80x100_char16(buf16000)
            return build_com_cga_160x100x16(buf16000)

        try:
            if mode == "320x200 (4 Colors)":
                vram = pack_cga_320x200_4color_vram(self.output_pimage)
                pal_name = (self.palette_var.get() or "").strip()
                bg_name = getattr(self, "bg_color_var", tk.StringVar(value="Black")).get()
                palbyte = cga_color_select_for_320_palette_name(pal_name, bg_name=bg_name)
                # "Tweaked" palette family corresponds to BIOS mode 05h on real CGA
                # (cyan/red/white forced, regardless of palette-select bit). All other
                # 4-color presets use BIOS mode 04h.
                if pal_name.startswith("Tweaked"):
                    mode_bios = 0x0005
                else:
                    mode_bios = 0x0004
                com = build_com_static_cga(mode_bios, vram, color_select_3d9=palbyte)
                default_name = "cga_320.com"

            elif mode == "320x200 (4 Colors) Mode Switch":
                # Per-scanline palette change (CGA mode 04h with timed 3D9h writes).
                # N=1: simple builder (writes 3D8+3D9 once per line during hblank).
                # N>=2: cycle-counted in-line writes during active video.
                seg_n = int(getattr(self, "ms_seg_n", 1))
                if not (1 <= seg_n <= 8):
                    messagebox.showinfo(
                        "Export COM — N out of range",
                        f"320x200 Mode Switch .COM export supports N=1..8 segments per line. "
                        f"You have N={seg_n} selected.\n\n"
                        f"Set 'Mode Switch segments per line' to 1..8 and click Convert again, "
                        f"then retry Export COM."
                    )
                    return
                stagger_mode = getattr(self, "ms_stagger_mode", "none")
                if stagger_mode and stagger_mode != "none":
                    messagebox.showinfo(
                        "Export COM — stagger not yet supported",
                        f"320x200 Mode Switch .COM export currently supports stagger=None "
                        f"only. You have '{stagger_mode}' selected.\n\n"
                        f"Set 'Stagger mode' to None and click Convert again, then retry."
                    )
                    return
                pals_by_y = getattr(self, "ms_pals_by_y", None)
                if pals_by_y is None or len(pals_by_y) != 200:
                    messagebox.showinfo(
                        "Export COM",
                        "No per-scanline palettes available. Please click Convert first."
                    )
                    return

                if seg_n == 1:
                    # Simple N=1 path
                    idx_arr = derive_indices_320_from_rgb(self.output_pimage, pals_by_y)
                    vram = pack_cga_320_vram_from_indices(idx_arr)
                    reg_table = build_cga_reg_table(pals_by_y)
                    com = build_com_320_mode_switch_n1(vram, reg_table)
                    default_name = "cga_320_modeswitch_n1.com"
                else:
                    # N>=2 cycle-counted path
                    idx_arr = derive_indices_320_from_rgb_n_seg(
                        self.output_pimage, pals_by_y, seg_n)
                    vram = pack_cga_320_vram_from_indices(idx_arr)
                    data_table, mismatches = build_n_segment_data_table(pals_by_y, seg_n)
                    if mismatches > 0:
                        messagebox.showinfo(
                            "Export COM — Mode 04h fallback",
                            f"{mismatches} of 200 lines had segments mixing standard "
                            f"(mode 04h) and Tweaked (mode 05h) palettes. For N>=2 the .COM "
                            f"writes 3D8 only once per line, so those lines fell back to "
                            f"the closest mode-04h equivalent.\n\n"
                            f"This may produce slightly different colors than the preview "
                            f"on those lines.\n\n"
                            f"Saving anyway."
                        )
                    com = build_com_320_mode_switch_n(vram, data_table, seg_n)
                    default_name = f"cga_320_modeswitch_n{seg_n}.com"

            elif mode == "160x200 (16 Colors) Composite":
                # Export as CGA 640x200 2-color (BIOS mode 06h). The *apparent* 16 colors
                # come from composite artifacting on a real NTSC composite display.
                if getattr(self, "composite_bits_pimage", None) is None:
                    raise ValueError("No composite hi-res image available. Please Convert first.")
                vram = pack_cga_640x200_2color_vram(self.composite_bits_pimage)

                # Foreground nibble for mode 06h: use White (15). (Composite decoding ignores RGBI fg color,
                # but we keep it sane for RGB displays.)
                palbyte = 0x0F
                # BIOS mode 06h sets bit 2 of port 3D8h (no colorburst, B/W). We clear bit 2
                # (value 0x1A: bit4=hi-res, bit3=video on, bit1=graphics, bit0/2 cleared) to
                # re-enable composite NTSC colorburst.
                com = build_com_static_cga(0x0006, vram, color_select_3d9=palbyte, mode_control_3d8=0x1A)
                default_name = "cga_composite_160x200.com"

            elif mode == "640x200 (2 Colors)":
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

            elif mode == "160x100 (16 Colors)":
                vram_text = pack_cga_160x100_16color_text_vram(self.output_pimage)
                com = build_text80x100_com(vram_text)
                default_name = "cga_160x100.com"

            elif mode == "640x200 (16 Colors) Char":
                char_attr = pack_text_80x100_char16(self.output_pimage)
                com = build_text80x100_com(char_attr)
                default_name = "cga_char16_80x100.com"

            elif mode == "80x100 (4352 Colors) HiColor":
                # HiColor uses the same 80x100 text tweak as the char16 mode; the only difference
                # is how the 640x200 output was produced. We repack the 8x2 blocks into (ch,attr).
                char_attr = pack_text_80x100_char16(self.output_pimage)
                com = build_text80x100_com(char_attr)
                default_name = "cga_hicolor_80x100.com"

            elif mode == "80x100 (512 Colors)":
                # CGA NTSC text-trick 512-color mode (per reenigne / 8088 MPH).
                # Uses chars 0x55 and 0x13 with all 16 FG × 16 BG combinations.
                # "Set and forget" — once displayed, no CPU intervention needed.
                # REQUIRES composite output to see all 512 colors.
                chosen = getattr(self, "text_ntsc_chosen", None)
                if chosen is None:
                    messagebox.showinfo(
                        "Export COM",
                        "No 80x100 cell data available. Please click Convert first."
                    )
                    return
                char_attr = pack_text_80x100_512color(chosen)
                com = build_com_text_80x100_512color(char_attr)
                default_name = "cga_512color.com"

            elif mode == "80x100 (1024 Colors) Mini-Frames":
                # CGA NTSC text-trick 1024-color full-screen mode (per reenigne / 8088 MPH).
                # Uses ALL 4 useful chars: 0x55, 0x13, 0xB0, 0xB1.
                # Requires the canonical mini-frames CRTC technique:
                #   100 mini-frames per CRT frame, each 2 scanlines tall, MaxSL=0.
                # CPU is fully occupied by the timing loop while displaying.
                # REQUIRES composite output to see all 1024 colors.
                # NOTE: this mode is LEGACY and does NOT work on MartyPC because
                # mini-frames CRTC reprogramming isn't supported there. Use
                # "80x100 (1024 Colors)" or "640x100 (1024 Colors)" for working alternatives.
                chosen = getattr(self, "text_ntsc_chosen", None)
                if chosen is None:
                    messagebox.showinfo(
                        "Export COM",
                        "No 80x100 cell data available. Please click Convert first."
                    )
                    return
                char_attr = pack_text_80x100_1024color(chosen)
                com = build_com_text_80x100_1024color(char_attr)
                default_name = "cga_1024color_miniframes.com"

            elif mode == "80x100 (1024 Colors)":
                # 80x100 1024-color centered mode — 4-pattern LUT encoder.
                # Cells were produced synchronously during Convert and stashed
                # in self.text_ntsc_chosen as (fg, bg, pat, swap) tuples. The
                # helper converts them to (char, attr) for the centered builder.
                chosen = getattr(self, 'text_ntsc_chosen', None)
                if chosen is None:
                    messagebox.showinfo(
                        "Export COM",
                        "No 80x100 cell data available. Please click Convert first."
                    )
                    return
                try:
                    cells = convert_text_ntsc_chosen_to_cells(chosen)
                    buf = pack_text_80x100_centered_1024color(cells)
                    com = build_com_text_80x100_centered_1024color(buf)
                    default_name = "cga_80x100_1024c.com"
                except Exception as e:
                    messagebox.showerror("Export COM",
                                         f"Failed to encode 80x100 (1024 Colors):\n{e}")
                    return

            elif mode == "640x100 (1024 Colors)":
                # 640x100 1024-color centered mode — 40-pattern exhaustive encoder.
                # Cells were produced asynchronously during Convert by the
                # background worker and stashed in self.text_ntsc_centered_cells.
                # If the worker is still running, ask the user to wait. If
                # neither cached cells nor a running worker, re-encode now
                # synchronously (slow, blocks GUI).
                try:
                    cells = getattr(self, 'text_ntsc_centered_cells', None)
                    if cells is None:
                        worker = getattr(self, '_centered_encoder_thread', None)
                        if worker is not None and worker.is_alive():
                            messagebox.showinfo(
                                "Export COM",
                                "The 640x100 (1024 Colors) encoder is still running in the "
                                "background. Please wait for it to finish "
                                "(status bar shows progress), then try again."
                            )
                            return
                        # Fallback re-encode at 640x100.
                        src640 = getattr(self, 'text_ntsc_src640', None)
                        if src640 is None:
                            messagebox.showinfo(
                                "Export COM",
                                "Please click Convert first so there is a source image to encode."
                            )
                            return
                        preset = (self.composite_palette_var.get()
                                  if hasattr(self, 'composite_palette_var') else "Old CGA")
                        chroma_lowpass = bool(self.tone_var.get()) if hasattr(self, 'tone_var') else False
                        k_value = 64
                        if hasattr(self, 'text_ntsc_k_var'):
                            try:
                                k_value = max(8, min(256, int(self.text_ntsc_k_var.get())))
                            except Exception:
                                k_value = 64
                        status_dbg(f"Encoding 640x100 (1024) Viterbi K={k_value} ({preset}, chroma_lowpass={chroma_lowpass})...")
                        cells = encode_image_to_80x100_centered_1024_viterbi(
                            src640, preset,
                            k_candidates=k_value,
                            dither_strength=1.0,
                            chroma_lowpass=chroma_lowpass,
                        )

                    buf = pack_text_80x100_centered_1024color(cells)
                    com = build_com_text_80x100_centered_1024color(buf)
                    default_name = "cga_640x100_1024c.com"
                except Exception as e:
                    messagebox.showerror("Export COM",
                                         f"Failed to encode 640x100 (1024 Colors):\n{e}")
                    return

        except Exception as e:
            messagebox.showerror("Export COM", f"Failed to build COM:\n{e}")
            return

        # Suffix the filename so the user can tell the variants apart.
        if target_video == "EGA/VGA" and default_name.endswith(".com"):
            default_name = default_name[:-4] + "_vga.com"

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