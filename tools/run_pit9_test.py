"""Boot a mode-4 export in the isolated PIT9/cycle MartyPC experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cga_mode4_lock import descriptor
from tools.build_startlock import read_files
from tools.make_marty_disk import inject_file
from tools.run_startlock import set_boot_floppy

WORK = ROOT / "external/research/pit9-cycle"


def prepare(disk: Path, phase: int, selected_program: str | None = None) -> dict:
    if phase not in range(12):
        raise ValueError("PIT offset must be 0..11 system-clock ticks")
    fork = WORK / "martypc"
    install = fork / "install"
    manifest = json.loads((WORK / "setup-manifest.json").read_text())
    executable = fork / "target/release/martypc.exe"
    if hashlib.sha256(executable.read_bytes()).hexdigest() != manifest["modified_exe_sha256"]:
        raise ValueError("Isolated executable differs from the recorded test build")
    for entry in manifest["files"]:
        actual = hashlib.sha256((fork / entry["path"]).read_bytes()).hexdigest()
        if actual != entry["modified_sha256"]:
            raise ValueError(f"Isolated source differs from the supplied ZIP: {entry['path']}")
    original = disk.read_bytes()
    files = read_files(bytearray(original))
    programs = [name for name, data in files.items()
                if name.endswith(".COM") and data[0xE00:0xE08] == b"IMGLK001"]
    if selected_program is not None:
        program = selected_program.upper()
        if not program.endswith(".COM"):
            program += ".COM"
        if program not in programs:
            raise ValueError(f"No acquired mode-4 program named {program} on this disk")
    else:
        program = next((name for name in ("TEST.COM", "GUARD.COM") if name in programs),
                       programs[0] if len(programs) == 1 else None)
    if program is None:
        raise ValueError("Disk needs TEST.COM or one acquired mode-4 program")
    descriptor(files[program])
    image = bytearray(original)
    command = program.removesuffix(".COM")
    inject_file(image, (f"@ECHO OFF\r\nPROMPT $P$G\r\n"
                       f"ECHO Isolated PIT offset {phase}, cycle CGA test\r\n"
                       f"ECHO Escape exits. Type {command} to repeat.\r\n"
                       f"{command}\r\n").encode("ascii"), "AUTOEXEC.BAT")
    after = read_files(image)
    if image[:512] != original[:512] or any(
            after.get(name) != data for name, data in files.items()
            if name != "AUTOEXEC.BAT"):
        raise ValueError("Runtime disk changed original program or DOS files")
    runtime = install / "media/floppies" / f"pit9_cycle_phase{phase}_runtime.dsk"
    if disk.resolve() == runtime.resolve():
        raise ValueError("Select the original disk rather than a generated runtime copy")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(image)
    config = (install / "martypc-cga.toml").read_text(encoding="utf-8")
    config = config.replace("$basedir$/../../../files", (ROOT / "files").as_posix())
    for name, value in {"pit_phase": str(phase), "turbo": "false",
                        "patch_roms": "false", "title_hacks": "false",
                        "dram_refresh_simulation": "true", "wait_states": "true"}.items():
        config, count = re.subn(rf"^{name}\s*=\s*[^\r\n]+$",
                                f"{name} = {value}", config, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"Expected one {name} setting")
    config = set_boot_floppy(config, runtime.as_posix())
    parsed = tomllib.loads(config)
    if parsed["machine"]["config_name"] != "cga_studio_5160":
        raise ValueError("Expected the isolated IBM 5160 CGA machine configuration")
    config_path = install / f"martypc-pit9-cycle-phase{phase}.toml"
    config_path.write_text(config, encoding="utf-8")
    return {"program": program, "runtime": str(runtime), "config": str(config_path),
            "source_sha256": hashlib.sha256(original).hexdigest(),
            "com_sha256": hashlib.sha256(files[program]).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disk", nargs="?", type=Path,
                        default=WORK / "hardware-original/cga_320_startlock.dsk")
    parser.add_argument("--phase", type=int, choices=range(12), default=9)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--program", help="COM to run when the disk contains multiple tests")
    args = parser.parse_args()
    result = prepare(args.disk.resolve(), args.phase, args.program)
    print(json.dumps(result, indent=2), flush=True)
    exe = WORK / "martypc/target/release/martypc.exe"
    if not exe.is_file():
        raise SystemExit(f"Build the isolated desktop first: {WORK / 'build-desktop.cmd'}")
    if not args.prepare_only:
        raise SystemExit(subprocess.run([str(exe), "--configfile", result["config"]],
                                        cwd=exe.parents[2] / "install").returncode)


if __name__ == "__main__":
    main()
