"""Package the full-palette timing repair for a separate physical hardware test."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_startlock import read_files
from tools.make_marty_disk import inject_file


def main():
    directory = ROOT / "artifacts/pit9-locked"
    original = (ROOT / "external/research/pit9-cycle/hardware-original/TEST.COM").read_bytes()
    disk = bytearray((directory / "CHEETL.DSK").read_bytes())
    inject_file(disk, original, "ORIG.COM")
    readme = """Cheetara full-palette PIT9/cycle timing experiment

CGATEST.DSK is a bootable 360 KiB DOS disk. It automatically runs TEST.
At the DOS prompt:
  TEST     - Cheetara with the new CPU/CGA/CRTC acquisition and raster timing
  REGLOCK  - independent registration pattern using all four framebuffer indices
  ORIG     - exact original TEST.COM from cga_320_startlock (1).zip
Escape exits the image. It also finishes after about 60 seconds.

This candidate repairs registration and instruction spacing. It uses the normal
eight-region quantizer with unrestricted palette choices. There are no seam
guard strips and no requirement for neighboring palettes to share colors.
The new measured region boundaries are 0,24,59,113,159,207,248,288,320.

CHEETL-modified-MartyPC.png is actual modified-core rendered output, enlarged
without filtering. CHEETL-preview.png is the encoder's expected 320x200 image.
The input was reconstructed from the intended RGBI image in the original COM;
the original source artwork was not available. Geometry changes require a new
encoding, so this is not claimed to be byte-identical to the original image.

All 12 PIT offsets and eight startup paddings pass exact pixel comparisons for
the image and registration pattern. DOS boots, repeated DOS launches, and the
full 60-second run also pass. CPU wait states and PIT1 DMA refresh stay enabled.

Physical hardware has not been tested. Please compare TEST, REGLOCK and ORIG,
repeat from DOS, and try cold boots. Record machine/CPU/CGA details and photos.
This local packet does not update the main studio encoder or main MartyPC.
"""
    inject_file(disk, readme.replace("\n", "\r\n").encode("ascii"), "README.TXT")
    files = read_files(disk)
    assert files["TEST.COM"] == (directory / "CHEETL.COM").read_bytes()
    assert files["REGLOCK.COM"] == (directory / "REGLOCK.COM").read_bytes()
    assert files["ORIG.COM"] == original
    assert len(disk) == 360 * 1024
    (directory / "CGATEST.DSK").write_bytes(disk)
    (directory / "ORIG.COM").write_bytes(original)
    (directory / "README.txt").write_text(readme, encoding="ascii")
    names = ["CGATEST.DSK", "CHEETL.COM", "REGLOCK.COM", "ORIG.COM",
             "CHEETL-preview.png", "REGLOCK-preview.png",
             "CHEETL-modified-MartyPC.png", "README.txt", "manifest.json"]
    hashes = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}
    (directory / "SHA256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    packet = directory / "Cheetara-PIT9-locked-test.zip"
    with zipfile.ZipFile(packet, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names + ["SHA256.json"]:
            archive.write(directory / name, name)
    with zipfile.ZipFile(packet) as archive:
        assert archive.testzip() is None
        for name, expected in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
    print(json.dumps({"packet": str(packet), "sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
                      "bytes": packet.stat().st_size, "disk_files": {name: len(data) for name, data in files.items()}}, indent=2))


if __name__ == "__main__":
    main()
