"""Launch an exported mode-4 disk with a fresh mount and the tested Marty settings.

The original export is read-only. Each launch rebuilds the runtime disk from it,
verifies the COM bytes, and starts the program through DOS AUTOEXEC.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cga_mode4_lock import descriptor
from tools.build_startlock import read_files
from tools.make_marty_disk import inject_file
from tools.run_startlock import set_boot_floppy


def prepare_export(source, phase=0, install=None):
    source = Path(source).resolve()
    install = Path(install) if install is not None else ROOT/"external/martypc/install"
    original = source.read_bytes()
    contents = read_files(bytearray(original))
    candidates = [name for name, payload in contents.items()
                  if name.endswith(".COM") and payload[0xE00:0xE08] == b"IMGLK001"]
    program = "TEST.COM" if "TEST.COM" in candidates else (candidates[0] if len(candidates) == 1 else None)
    if program is None:
        raise ValueError("Expected TEST.COM or a single acquired mode-4 program on the disk")
    descriptor(contents[program])
    if phase not in range(4):
        raise ValueError("PIT phase must be 0, 1, 2 or 3")
    runtime = install/"media/floppies"/f"cga_export_phase{phase}_runtime.dsk"
    if source == runtime.resolve():
        raise ValueError("Select the original exported disk, not this launcher's temporary runtime copy")
    payload = bytearray(original)
    command = program.removesuffix(".COM")
    autoexec = (f"@ECHO OFF\r\nPROMPT $P$G\r\n"
                f"ECHO Fresh CGA export: {program}\r\n"
                f"ECHO Escape exits. Type {command} to repeat.\r\n{command}\r\n").encode("ascii")
    inject_file(payload, autoexec, "AUTOEXEC.BAT")
    after = read_files(payload)
    for name, data in contents.items():
        if name != "AUTOEXEC.BAT" and after.get(name) != data:
            raise ValueError(f"Runtime disk changed {name}")
    if payload[:512] != original[:512] or after["AUTOEXEC.BAT"] != autoexec:
        raise ValueError("Runtime disk boot verification failed")
    baseline = install/"martypc-cga.toml"
    config = baseline.read_text(encoding="utf-8")
    settings = {"pit_phase": str(phase), "turbo": "false", "patch_roms": "false",
                "title_hacks": "false", "dram_refresh_simulation": "true", "wait_states": "true"}
    for name, value in settings.items():
        config, count = re.subn(rf"^{name}\s*=\s*[^\r\n]+$", f"{name} = {value}", config, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"Expected exactly one {name} configuration setting")
    parsed = tomllib.loads(config)
    if parsed["machine"]["config_name"] != "cga_studio_5160":
        raise ValueError("The test launcher requires the cga_studio_5160 machine configuration")
    config = set_boot_floppy(config, runtime.as_posix())
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(payload)
    config_path = install/f"martypc-cga-export-phase{phase}.toml"
    config_path.write_text(config, encoding="utf-8")
    return {"source": source, "runtime": runtime, "config": config_path,
            "program": program, "com_sha256": hashlib.sha256(contents[program]).hexdigest(),
            "source_sha256": hashlib.sha256(original).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disk", type=Path)
    parser.add_argument("--phase", type=int, choices=range(4), default=0)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    result = prepare_export(args.disk, args.phase)
    print(f"Fresh export: {result['source']}", flush=True)
    print(f"Verified {result['program']} SHA256 {result['com_sha256']}", flush=True)
    print("IBM 5160 / CGA; turbo off; refresh and wait states on.", flush=True)
    if not args.prepare_only:
        install = ROOT/"external/martypc/install"
        executable = ROOT/"external/martypc/target/release/martypc.exe"
        result = subprocess.run([str(executable), "--configfile", str(result["config"])], cwd=install)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
