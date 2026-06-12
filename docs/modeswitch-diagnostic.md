# Mode Switch Diagnostic Image

Generate the fixture:

```powershell
.\.venv\Scripts\python.exe tools\generate_modeswitch_diagnostic_image.py
```

Open `files/modeswitch_diagnostic.png` in CGA Image Studio and use:

```text
Output mode:                320x200 (4 Colors) Mode Switch
Mode Switch writes/line:    2
Mode Switch pattern:        Horizontal Striped
Background color:           Multiple
Tweaked palettes:           Off (mode 04)
Dither family:              None
Keep border black:          Off
```

Click `Convert`, save a GIF, export a bootable DSK, run `TEST.COM`, and capture
a MartyPC screenshot.

With the settings above, the converter preview and saved GIF should reproduce
the source PNG pixel-for-pixel. The fixture is intentionally compatible with
the inherited-left-zone rule, so any visible difference in the MartyPC
screenshot points at COM-side palette selection or packed VRAM interpretation.

The image has two sections:

```text
rows 0..87:    fixed-palette VRAM packing and even/odd-bank probes
rows 88..199:  three-zone palette handoff probes
```

For the lower section, the intended physical zones are:

```text
x 0..144:    inherited final palette from the prior scanline
x 145..272:  palette written by OUT #1
x 273..319:  palette written by OUT #2
```

Run the same conversion a second time with `Keep border black` enabled if an
A/B comparison is needed. With that option enabled, changes in the right zone
and following scanline's left zone are expected; changes in the middle zone
are not.
