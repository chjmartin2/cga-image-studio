# Build from the repository root: python -m PyInstaller --noconfirm CGAImageStudio.spec
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "studio_launcher.py")], pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets/mode4_lock"), "assets/mode4_lock"),
           (str(root / "assets/branding/raster-crt"), "assets/branding/raster-crt"),
           (str(root / "files/dos_boot_template.dsk"), "files")],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["scipy", "pytest"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name="CGAImageStudio", debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False,
          version=str(root / "assets/windows-version.txt"),
          icon=str(root / "assets/branding/raster-crt/app.ico"))
