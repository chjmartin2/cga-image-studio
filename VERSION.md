# Version

Current release: **0.167a**, alpha snapshot dated 2026-09-28.
Git tag: `v0.167a`. Next milestone: **1.0 beta** after release validation.

This intentionally rebaselines public numbering around the historical v167
development line. It succeeds `v0.3.0-alpha.3`; previous tags/releases remain
available and are not renamed. The suffix `a` denotes alpha.

The GUI and launcher use `app_version.py`. Windows file properties display
`0.167a` (numeric resource version `0.167.0.0`). The implementation filename
remains `cga_v167.py` for compatibility; use `studio_launcher.py` to launch.

This snapshot does not claim full mode/output or physical-hardware validation.
See `docs/INITIAL_RELEASE_CHECKLIST.md` for remaining acceptance work.
