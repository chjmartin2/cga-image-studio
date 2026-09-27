"""Boot a verified fresh copy of the Picard mode-4 disk in the local MartyPC build."""
from pathlib import Path
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_startlock import read_files
from tools.run_startlock import set_boot_floppy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", nargs="?", type=int, choices=range(4), default=0)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    install = ROOT/"external/martypc/install"
    exe = ROOT/"external/martypc/target/release/martypc.exe"
    master = ROOT/"files/IMGLCK.DSK"
    baseline = install/"martypc-cga.toml"
    for path in (exe, master, baseline):
        if not path.is_file():
            raise SystemExit(f"Required file missing: {path}")
    image = master.read_bytes()
    files = read_files(bytearray(image))
    for name in ("IMGLCK.COM", "REGLOCK.COM"):
        if files.get(name) != (ROOT/"files"/name).read_bytes():
            raise SystemExit(f"The disk does not contain the current {name}; rebuild with tools/build_imagelock.py")
    if b"IMGLCK" not in files.get("AUTOEXEC.BAT", b"").splitlines():
        raise SystemExit("The Picard disk is missing its automatic startup command")
    runtime = install/"media/floppies"/f"imagelock_phase{args.phase}_runtime.dsk"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(master, runtime)
    config = baseline.read_text(encoding="utf-8")
    settings = {"pit_phase": str(args.phase), "turbo": "false", "patch_roms": "false",
                "title_hacks": "false", "dram_refresh_simulation": "true", "wait_states": "true"}
    for name, value in settings.items():
        config, count = re.subn(rf"^{name}\s*=\s*[^\r\n]+$", f"{name} = {value}", config, flags=re.MULTILINE)
        if count != 1:
            raise SystemExit(f"Expected exactly one {name} configuration setting")
    if tomllib.loads(config)["machine"]["config_name"] != "cga_studio_5160":
        raise SystemExit("The Picard launcher requires the cga_studio_5160 machine configuration")
    config = set_boot_floppy(config, runtime.as_posix())
    config_path = install/f"martypc-imagelock-phase{args.phase}.toml"
    config_path.write_text(config, encoding="utf-8")
    print(f"Picard: phase {args.phase}; verified IMGLCK and REGLOCK on drive A.", flush=True)
    print("IBM 5160 / CGA; turbo off; refresh and wait states on.", flush=True)
    print(f"Boot disk SHA256: {hashlib.sha256(image).hexdigest()}", flush=True)
    if not args.prepare_only:
        result = subprocess.run([str(exe), "--configfile", str(config_path)], cwd=install)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
