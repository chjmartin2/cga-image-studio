# Standalone Windows build

The v0.3.0-alpha.3 release includes a single-file Windows x64 executable.
Download `CGAImageStudio.exe` from the GitHub release and double-click it.
Python, NASM, and MartyPC are not required to run the converter. A DOS computer
or emulator is required to run exported COM programs. The executable includes
the mode-4 profile and DOS disk template. It is not code-signed.

Eight-write conversion and COM, ASM, and DSK exports use the corrected, validated
MartyPC timing profile. Choose **320x200 (4 Colors) Mode Switch**, **8 writes**,
or **8 staggered**, then convert and export. Staggered uses fixed alternating
palette boundaries shared by the preview and exports, with no frame-to-frame
movement. Change the selection and click Convert again before exporting.
Full studio feature validation and physical CGA hardware
qualification remain outstanding. Restart older running copies before testing.

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
and eight-write COM/ASM/DSK generation. It does not validate every feature or raster timing.

Open `cga-image-studio.code-workspace` in VS Code to reopen the project with its
local Python interpreter selected. Native MartyPC builds, raw research downloads,
local shortcuts, and the downloaded forum PDF remain outside Git; curated
research notes, experiment programs, captures, and their manifests are retained.
