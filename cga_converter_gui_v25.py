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
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import numpy as np


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
    import re
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


def apply_diffusion_dither(image, palette, method_name, intensity=1.0, serpentine=True):
    """
    Diffusion dithering family.

    intensity: 0.0..1.0 scales the diffused error (0 => no diffusion, 1 => full diffusion).
    serpentine: if True, alternate scan direction each row and mirror the kernel.
    """
    intensity = 0.0 if intensity < 0.0 else 1.0 if intensity > 1.0 else float(intensity)

    # Kernels are defined for left-to-right scan.
    if method_name == "Floyd-Steinberg":
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

def quantize_char16_textblock_from_indices(pre_indices):
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
      - We choose the character that minimizes colour error against the pre-quantized
        16-colour target.

    Returns a 'P' image with the CGA 16-colour palette.
    """
    w, h = 640, 200
    if len(pre_indices) != w * h:
        raise ValueError("quantize_char16_textblock_from_indices expects 640x200 indices")

    # Precompute 16x16 squared-distance matrix between CGA palette colours
    dist = [[0]*16 for _ in range(16)]
    for a in range(16):
        ar, ag, ab = CGA_16COLOR_PALETTE[a]
        for b in range(16):
            br, bg, bb = CGA_16COLOR_PALETTE[b]
            dr = ar - br
            dg = ag - bg
            db = ab - bb
            dist[a][b] = dr*dr + dg*dg + db*db

    num_cols = 80
    num_rows = 100
    cell_w = 8
    cell_h = 2

    out = [0] * (w * h)

    # local refs for speed
    row01 = _CGA_FONT_ROW01

    # small reusable counts
    counts = [0] * 16

    for row in range(num_rows):
        y0 = row * cell_h
        for col in range(num_cols):
            x0 = col * cell_w

            # Gather the 16 target indices for this 8x2 block
            # and find two most frequent colours as FG/BG candidates.
            for i in range(16):
                counts[i] = 0

            block = [0]*16
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

            # Search all 256 characters (row0,row1 masks) for best match
            best_code = 0
            best_err = float("inf")

            # Precompute dist lookups for fg/bg for speed
            # err contribution uses dist[target][chosen]
            for code in range(256):
                m0, m1 = row01[code]
                err = 0

                # Row 0 (dy=0): block[0..7]
                # bit 7 -> x0
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
            if dither_family == "Error diffusion":
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




def quantize_320x200_mode_switch(
    image_rgb_320x200,
    dither_family="Diffusion",
    diffusion_name="Floyd-Steinberg",
    diffusion_intensity=1.0,
    serpentine=True,
    ordered_matrix_size=4,
    ordered_strength=1.0,
):
    """
    CGA 320x200 raster "mode switch": choose a (background + 3-color) CGA 4-color mapping per scanline.

    The converter greedily selects, for each scanline, the CGA 4-color palette (from CGA_4COLOR_PALETTES)
    that best matches the current working pixels for that scanline, then quantizes that scanline using
    the selected dithering strategy. Error diffusion, if enabled, propagates normally across rows.
    """
    img = image_rgb_320x200.convert("RGB")
    w, h = img.size
    if (w, h) != (320, 200):
        raise ValueError("Mode Switch expects a 320x200 RGB image")

    candidates = list(CGA_4COLOR_PALETTES.values())
    rgb_to_idx = {tuple(c): i for i, c in enumerate(CGA_COLORS)}

    pix = img.load()
    buf = [[[pix[x, y][0], pix[x, y][1], pix[x, y][2]] for x in range(w)] for y in range(h)]
    out_idx = [[0] * w for _ in range(h)]

    # Ordered matrix
    ord_matrix = None
    if dither_family == "Ordered":
        ord_matrix = get_ordered_matrix(int(ordered_matrix_size))
        mh = len(ord_matrix)
        mw = len(ord_matrix[0])
        mmax = mw * mh

    # Diffusion kernel selection
    kernel = divisor = None
    if dither_family == "Diffusion" and diffusion_name != "None":
        if diffusion_name == "Floyd-Steinberg":
            kernel, divisor = _FS_KERNEL, 16
        elif diffusion_name == "Atkinson":
            kernel, divisor = _ATKINSON_KERNEL, 8
        elif diffusion_name == "Jarvis-Judice-Ninke":
            kernel, divisor = _JJN_KERNEL, 48
        elif diffusion_name == "Stucki":
            kernel, divisor = _STUCKI_KERNEL, 42
        elif diffusion_name == "Burkes":
            kernel, divisor = _BURKES_KERNEL, 32
        elif diffusion_name == "Sierra":
            kernel, divisor = _SIERRA_KERNEL, 32
        elif diffusion_name == "Sierra-2":
            kernel, divisor = _SIERRA2_KERNEL, 16
        elif diffusion_name == "Sierra Lite":
            kernel, divisor = _SIERRA_LITE_KERNEL, 4

    diffusion_intensity = 0.0 if diffusion_intensity < 0.0 else 1.0 if diffusion_intensity > 1.0 else float(diffusion_intensity)

    for y in range(h):
        row = buf[y]

        # choose palette per scanline based on current (possibly error-adjusted) row
        best_pal = candidates[0]
        best_err = None
        for pal in candidates:
            err = 0.0
            for x in range(w):
                r, g, b = row[x]
                bestd = None
                for pr, pg, pb in pal:
                    dr = r - pr
                    dg = g - pg
                    db = b - pb
                    d = dr * dr + dg * dg + db * db
                    if bestd is None or d < bestd:
                        bestd = d
                err += bestd
                if best_err is not None and err >= best_err:
                    break
            if best_err is None or err < best_err:
                best_err = err
                best_pal = pal

        pal = best_pal

        rev = serpentine and (y % 2 == 1)
        x_range = range(w - 1, -1, -1) if rev else range(w)

        for x in x_range:
            old = row[x]

            # Ordered offset
            if dither_family == "Ordered" and ord_matrix is not None:
                t = ord_matrix[y % mh][x % mw] / float(mmax)
                off = (t - 0.5) * float(ordered_strength) * 255.0
                r = clamp255(old[0] + off)
                g = clamp255(old[1] + off)
                b = clamp255(old[2] + off)
            else:
                r, g, b = old

            # nearest among 4
            best_rgb = pal[0]
            bestd = None
            for pr, pg, pb in pal:
                dr = r - pr
                dg = g - pg
                db = b - pb
                d = dr * dr + dg * dg + db * db
                if bestd is None or d < bestd:
                    bestd = d
                    best_rgb = (pr, pg, pb)

            out_idx[y][x] = rgb_to_idx[tuple(best_rgb)]

            if kernel is not None and divisor is not None:
                err_r = (old[0] - best_rgb[0]) * diffusion_intensity
                err_g = (old[1] - best_rgb[1]) * diffusion_intensity
                err_b = (old[2] - best_rgb[2]) * diffusion_intensity
                for dx, dy, wgt in kernel:
                    ddx = -dx if rev else dx
                    xx = x + ddx
                    yy = y + dy
                    if 0 <= xx < w and 0 <= yy < h:
                        p = buf[yy][xx]
                        f = wgt / float(divisor)
                        p[0] = clamp255(p[0] + err_r * f)
                        p[1] = clamp255(p[1] + err_g * f)
                        p[2] = clamp255(p[2] + err_b * f)

    # Build output P image with fixed 16-color palette
    pimg = Image.new("P", (w, h))
    pimg.putdata([i for row in out_idx for i in row])

    pal_flat = []
    for r, g, b in CGA_16COLOR_PALETTE:
        pal_flat.extend([r, g, b])
    pal_flat.extend([0] * (768 - len(pal_flat)))
    pimg.putpalette(pal_flat)
    return pimg
class CgaConverterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CGA Converter v25")
        self.geometry("1040x640")

        self.src_image = None
        self.output_pimage = None
        self.effective_80x100_image = None
        self.mid_tk_image = None
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
            values=["Lanczos", "Nearest"],
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

        # HiColor character limiting
        self.hicolor_limit_var = tk.BooleanVar(value=True)
        self.hicolor_limit_cb = ttk.Checkbutton(
            options,
            text="Limit HiColor characters (solids + shades + stripes)",
            variable=self.hicolor_limit_var,
        )
        self.hicolor_limit_cb.grid(row=5, column=0, columnspan=6, sticky="w", padx=4, pady=2)

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

        self.right_label = ttk.Label(right_frame, text="No output yet")
        self.right_label.pack(fill=tk.BOTH, expand=True)

        self._refresh_palette_choices()
        self.on_dither_family_changed()
        self._update_dither_labels()

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

    
    def is_mode_switch_mode(self):
        return "320x200 Mode Switch" in self.mode_var.get()

    def get_target_size(self):
        if self.is_4color_mode() or self.is_mode_switch_mode():
            return 320, 200
        if self.is_mono_mode():
            return 640, 200
        if self.is_16color_low_mode():
            return 160, 100
        # char 16-color
        if self.is_16color_char_mode():
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
        else:
            # 16-color modes: fixed palette
            names = ["CGA 16-color"]
            self.palette_cb["values"] = names
            self.palette_cb.state(["disabled"])
            self.palette_var.set("CGA 16-color")

    def on_mode_changed(self, event=None):
        self._refresh_palette_choices()

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

        # NOTE: No aspect correction here; preview shows native pixel geometry.

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
        dither_family = self.dither_family_var.get()
        diffusion_method = self.diffusion_var.get()
        diffusion_intensity = float(self.dither_intensity_var.get())
        serpentine = bool(self.serpentine_var.get())
        ordered_size = int(self.ordered_size_var.get())
        ordered_strength = float(self.ordered_strength_var.get())

        resized = resize_with_mode(self.src_image, target_w, target_h, scale_mode, resample_name)

        if self.tone_var.get():
            toned = tone_image_to_palette(resized, palette)
        else:
            toned = resized



        if self.is_mode_switch_mode():
            # Mode-switch raster palette per scanline (CGA 320x200 4-color with per-scanline palette/background changes)
            # Work on a 320x200 image regardless of other target sizes.
            scaled = resize_with_mode(self.src_image, 320, 200, scale_mode, resample_name)
            if self.tone_var.get():
                toned_ms = tone_image_to_palette(scaled, CGA_16COLOR_PALETTE)
            else:
                toned_ms = scaled

            if dither_family == "Ordered":
                pimg = quantize_320x200_mode_switch(
                    toned_ms,
                    dither_family="Ordered",
                    ordered_matrix_size=ordered_size,
                    ordered_strength=ordered_strength,
                    serpentine=serpentine,
                )
            elif dither_family == "Diffusion" and diffusion_method != "None":
                pimg = quantize_320x200_mode_switch(
                    toned_ms,
                    dither_family="Diffusion",
                    diffusion_name=diffusion_method,
                    diffusion_intensity=diffusion_intensity,
                    serpentine=serpentine,
                )
            else:
                pimg = quantize_320x200_mode_switch(
                    toned_ms,
                    dither_family="None",
                    serpentine=serpentine,
                )

            self.output_pimage = pimg
            self._update_output_preview()
            return
        if self.is_16color_char_mode():
            # Text-block mode constraint is too strong to dither "during" mapping.
            # Instead:
            #   1) Convert to a normal 640x200 CGA 16-colour bitmap using the selected dither.
            #   2) Map that 16-colour result into the 8x2 character-slice constraints.
            if dither_family == "Ordered":
                pre_p = apply_ordered_dither(toned, CGA_16COLOR_PALETTE, matrix_size=ordered_size, strength=ordered_strength)
            elif dither_family == "Error diffusion":
                pre_p = apply_diffusion_dither(toned, CGA_16COLOR_PALETTE, diffusion_method, intensity=diffusion_intensity, serpentine=serpentine)
            else:
                pre_p = apply_diffusion_dither(toned, CGA_16COLOR_PALETTE, "None", intensity=0.0)

            pre_indices = list(pre_p.getdata())
            pimg = quantize_char16_textblock_from_indices(pre_indices)

        elif self.is_hicolor_mode():
            # 80x100 HiColor: scale the source into 80x100 using the selected scaling mode,
            # apply dithering in 80x100 cell space, then expand to 640x200 using 2x8 patterns.
            resized80 = resize_with_mode(self.src_image, 80, 100, scale_mode, resample_name)
            if self.tone_var.get():
                toned80 = tone_image_to_palette(resized80, palette)
            else:
                toned80 = resized80

            pimg, effective = quantize_80x100_hicolor(
                toned80.convert("RGB"),
                dither_family=dither_family,
                diffusion_name=diffusion_method,
                intensity=diffusion_intensity,
                ordered_size=int(self.ordered_size_var.get()),
                ordered_strength=float(self.ordered_strength_var.get()),
                limit_chars=bool(self.hicolor_limit_var.get()),
            )

            self.effective_80x100_image = effective
            self._update_mid_preview()
        else:
            # Normal modes: honour dithering choice
            if dither_family == "Ordered":
                pimg = apply_ordered_dither(toned, palette, matrix_size=ordered_size, strength=ordered_strength)
            elif dither_family == "Error diffusion":
                pimg = apply_diffusion_dither(toned, palette, diffusion_method, intensity=diffusion_intensity, serpentine=serpentine)
            else:
                pimg = apply_diffusion_dither(toned, palette, "None", intensity=0.0)

        self.output_pimage = pimg
        if not self.is_hicolor_mode():
            self.effective_80x100_image = None
            if getattr(self, "mid_label", None) is not None:
                self.mid_label.configure(image="", text="(HiColor mode only)")
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