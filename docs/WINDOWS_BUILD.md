# Standalone Windows build

The v0.3.0-alpha.1 checkpoint includes a single-file Windows x64 executable.
Download `CGAImageStudio.exe` from the GitHub release and double-click it.
Python, NASM, and MartyPC are not required to run the converter. A DOS computer
or emulator is required to run exported COM programs. The executable includes
the mode-4 profile and DOS disk template. It is not code-signed.

Eight-write conversion previews remain experimental. COM, ASM, and DSK export
using the withdrawn eight-write profile is intentionally blocked. This is not
the final feature-complete or fully validated release.

Build on Windows x64 with Python 3.12, including Tcl/Tk:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm CGAImageStudio.spec
$check = Start-Process .\dist\CGAImageStudio.exe -ArgumentList '--smoke-test', 'smoke.json' -PassThru -Wait -WindowStyle Hidden
if ($check.ExitCode -ne 0) { throw 'Packaged smoke check failed' }
Get-Content smoke.json
```

The smoke check constructs the GUI and exercises bundled image libraries, CGA
packing, static COM/ASM generation, disk-template injection, eight-write preview,
and the export guard. It does not validate every feature or raster timing.

Open `cga-image-studio.code-workspace` in VS Code to reopen the project with its
local Python interpreter selected. Native MartyPC builds, raw research downloads,
local shortcuts, and the downloaded forum PDF remain outside Git; curated
research notes, experiment programs, captures, and their manifests are retained.
