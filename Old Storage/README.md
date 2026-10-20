# Old Storage

Historical and completed work was moved here on October 20, 2026 to keep the
repository root focused on the current CGA Image Studio application.
Nothing was deleted. All 50 moved files were checked with SHA-256 before and
after relocation; the empty `output/imagegen` directory was preserved too.

| Folder | Contents |
| --- | --- |
| `legacy-root/` | Historical v165/v166 applications, 20 early diagnostic generators, seven assembly exports/experiments, original launchers, old IDE instructions and a comparison image |
| `CompositeSource/` | Four Rust composite-rendering reference sources |
| `local-work/` | Eight completed local website/demo helpers and the old empty output folder; ignored by Git |

[move-manifest.json](move-manifest.json) records the original path, archive
path, length and SHA-256 of each of the 42 previously tracked files.
The eight local helpers have their own ignored manifest in `local-work`.
Archived source files retain their original bytes and line endings.

## Current application

Run `run_cga_v167.cmd` from the repository root, or:

```powershell
.\.venv\Scripts\python.exe studio_launcher.py
```

The current application is `cga_v167.py` with its imported modules beside it.
The archive is not needed to run it or build the standalone Windows executable.
Current assets, boot templates, fixtures, tools, tests, demo artifacts, releases
and local emulator/toolchain installations keep their established locations.
`run_stdout.txt` and `run_stderr.txt` remain in the root under the migration rules.

## Running historical Python scripts

From the repository root:

```powershell
.\.venv\Scripts\python.exe tools/run_archived.py --list
.\.venv\Scripts\python.exe tools/run_archived.py generate_cgalk5_test.py --help
.\.venv\Scripts\python.exe tools/run_archived.py cga_v166.py
```

The runner establishes the original working directory and import paths.
For the historical applications it also preserves the root-relative boot
template/debug-output location. It does not modify the archived snapshots.
Generators retain their original behavior and may write files under `files/`;
use their output options when producing a new diagnostic.

The `.cmd` files in `legacy-root` are unchanged historical records, not current
shortcuts. Use the archive runner for the old applications. Working diagnostic
and emulator shortcuts are now in `tools/launchers/`; the two primary app/demo
shortcuts remain in the root. Earlier research notes retain their original
commands as historical evidence; substitute the archive runner or new launcher
path when reproducing those commands.

## Local helpers

The scripts under `local-work/tools/` are completed, machine-specific website
and demo operations. Some modify files immediately when executed or imported,
and their original relative paths no longer describe their archive location.
Keep them as records; review and adapt a copy deliberately if they are needed
again. They are not part of the application or routine validation.

## Cleanup validation

After relocation, all 522 application tests and 578 subtests passed.
A fresh standalone Windows build passed its full smoke check from its own
folder with only Windows system directories on PATH. The archive runner was
checked for argument forwarding, generator imports and the historical v166
bootable-disk export; four relocated diagnostic launchers passed their help
commands from outside the checkout. Current application source was unchanged.

Local verification logs and the separate verification executable are under
`artifacts/repository-cleanup-2026-10-20/`. Existing release files and demo
artifacts were not replaced.
