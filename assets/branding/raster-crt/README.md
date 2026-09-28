# CGA Image Studio identity: Raster CRT

The owner selected option 1, Raster CRT, replacing the earlier selection of option 2, Pixel Forge. Use this design for the software GUI and application icon.

## Files

- raster-crt-identity.png: exact selected artwork, 1536 x 1024. The full logo/wordmark is at the top; the matching rounded-square app icon is at the lower right.
- identity.json: the exact non-destructive crop rectangles used by the website and target brand colors.

This was copied from the website asset directory on 2026-09-27. No application code was changed.

GUI integration now uses `logo.png` and `app.ico`, reproduced with
`python tools/build_branding.py`. `app-icon.png` is the square padded export;
the ICO includes 16, 24, 32, 48, 64, 128 and 256 pixel versions. These retain
the approved opaque background. PyInstaller includes the assets and EXE icon;
this change does not rebuild the standalone package.

## Guidance for the coding agent

Preserve the C-shaped silver CRT, pedestal, and three horizontal cyan/magenta/white bars, in that order. Keep the CGA IMAGE STUDIO lettering for the full logo. Use the standalone CRT symbol for the application icon. Do not use the RetroComputerist parent R or the rejected Pixel Forge design.

The supplied PNG is a concept board with an opaque charcoal background, not a finished transparent logo or Windows ICO. The website displays the original image through the crop rectangles in identity.json. For GUI integration, prepare separate logo and square icon exports from the approved artwork, then generate the application's required ICO sizes. Preserve proportions and include padding when making the slightly rectangular icon crop square. Do not stretch it or assume the source has alpha transparency. Colors in the generated raster may vary slightly from the target palette.

Do not use the entire concept board as a splash-screen logo or application icon. Confirm small-size readability after export.
