# Version

Current release: **1.0.0-rc.1**, release candidate dated 2026-10-20.
Git tag: `v1.0.0-rc.1`. This is a prerelease toward **1.0.0**.

This release succeeds `v0.167a`; previous tags and releases remain available
and are not renamed. The `rc.1` suffix denotes the first 1.0 release candidate.

The GUI and launcher use `app_version.py`. Windows file properties display
`1.0.0-rc.1` (numeric resource version `1.0.0.1`, prerelease flag set). The implementation filename
remains `cga_v167.py` for compatibility; use `studio_launcher.py` to launch.

The standalone Windows x64 executable includes CPU acceleration. Optional CUDA
acceleration is available when running from source. The release also includes
the previously reviewed 24-image bootable demo and its exported gallery.

This candidate does not claim full mode/output or physical-hardware validation.
See `docs/INITIAL_RELEASE_CHECKLIST.md` for remaining acceptance work.
