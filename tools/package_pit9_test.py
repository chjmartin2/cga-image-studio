"""Package the locally validated original/guarded hardware comparison."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as cga
from tools.build_startlock import read_files
from tools.make_marty_disk import (inject_file, delete_existing_root_file,
                                  normalize_83, parse_layout)

WORK = ROOT / "external/research/pit9-cycle"
OUT = ROOT / "artifacts/pit9-cycle"
README = """CGA Image Studio - Cheetara hardware comparison, 2026-10-07

This is an experimental comparison package. Lockstep acquisition is unchanged;
the main encoder and normal MartyPC installation are unchanged.

ORIG.COM   Exact original Cheetara program from the hardware-tested disk.
GUARD.COM  New encoding of its intended RGBI image. Adjacent palettes share
           colors in 9-10-pixel seam strips, making small boundary displacement
           harmless there. Color detail near seams is reduced intentionally.
RAWREG.COM Unguarded independent palette/index registration diagnostic.
           Background rows expose the actual moving palette boundaries.
GREG.COM   Guarded registration image with an accompanying expected preview.

Boot CGATEST.DSK (360 KiB) to run GUARD automatically. Escape exits; each image
also stops after about 60 seconds. At DOS type ORIG, GUARD, RAWREG or GREG.
The COM files can also be copied to an existing DOS system. Use normal-speed
8088/IBM-compatible CGA hardware. Compare programs with their included previews.
The raw test may still show shifted edges. A stable guarded picture does not
prove acquisition or refresh timing is exact.

Record machine, CPU/clock, CGA card, BIOS and command. Photograph ORIG and GUARD
on the same boot, then repeat GUARD after returning to DOS and after cold power
cycles. Photograph RAWREG/GREG if there are errors. Note jitter, row slant,
shifted regions, startup failures and whether Escape/DOS return work.

The supplied MartyPC modification enables cycle CGA clocking and PIT offset 9.
The exact original reproduces a consistent error in that isolated emulator.
Guarded encoding passes all 12 offsets times eight startup paddings, DOS boots,
five successive DOS launches at offsets 0/3/6/9 and a full display at offset 9.
This is emulator evidence; physical validation remains outstanding.

SHA256.json records payload hashes. No emulator, ROM or third-party release
archive is included. This package has not been sent to anyone.
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    programs = {"ORIG.COM": WORK / "hardware-original/TEST.COM",
                "GUARD.COM": WORK / "guarded/CHEETG.COM",
                "RAWREG.COM": WORK / "calibration/INDEXDG.COM",
                "GREG.COM": WORK / "guarded/GREG.COM"}
    disk = bytearray(cga.build_bootable_dsk_from_com(programs["GUARD.COM"].read_bytes()))
    delete_existing_root_file(disk, parse_layout(disk), normalize_83("TEST.COM"))
    for name, path in programs.items():
        inject_file(disk, path.read_bytes(), name)
        (OUT / name).write_bytes(path.read_bytes())
    inject_file(disk, b"@ECHO OFF\r\nPROMPT $P$G\r\n"
                     b"ECHO ORIG original, GUARD tolerant image, RAWREG edges, GREG guarded test\r\n"
                     b"GUARD\r\n", "AUTOEXEC.BAT")
    inject_file(disk, README.replace("\n", "\r\n").encode("ascii"), "README.TXT")
    for name, path in programs.items():
        assert read_files(disk)[name] == path.read_bytes()
    (OUT / "CGATEST.DSK").write_bytes(disk)
    (OUT / "README.txt").write_text(README, encoding="ascii")
    previews = {"ORIG-preview.png": WORK / "hardware-original/expected.png",
                "GUARD-preview.png": WORK / "guarded/CHEETG-preview.png",
                "RAWREG-preview.png": WORK / "calibration/expected.png",
                "GREG-preview.png": WORK / "guarded/GREG-preview.png"}
    for name, path in previews.items():
        (OUT / name).write_bytes(path.read_bytes())
    names = [*programs, *previews, "CGATEST.DSK", "README.txt"]
    hashes = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in names}
    (OUT / "SHA256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    archive = OUT / "Cheetara-hardware-comparison.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for name in [*names, "SHA256.json"]:
            z.write(OUT / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(name)).hexdigest() == digest
                   for name, digest in hashes.items())
    print(f"Verified {archive} ({archive.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
