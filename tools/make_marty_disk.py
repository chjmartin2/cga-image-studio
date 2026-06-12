"""Create a MartyPC-friendly FAT12 disk image containing a test COM.

Default workflow:
  - source COM: files/TEST.COM
  - template:   files/dos_boot_template.dsk, if it exists
  - output:     files/marty_work.dsk
  - image name: TEST.COM in the root directory

Use --extra SOURCE=NAME to replace or add additional root-level files while
building an image, for example AUTOEXEC.BAT or CONFIG.SYS.

If the template is missing, the tool creates a blank 1.44 MB FAT12 data disk.
That image is not bootable, but it can be mounted as a data floppy from DOS.
"""

from __future__ import annotations

import argparse
import math
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_SOURCE = Path("files") / "TEST.COM"
DEFAULT_TEMPLATE = Path("files") / "dos_boot_template.dsk"
DEFAULT_OUTPUT = Path("files") / "marty_work.dsk"
DEFAULT_IMAGE_NAME = "TEST.COM"


@dataclass(frozen=True)
class Fat12Layout:
    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    fat_count: int
    root_entries: int
    total_sectors: int
    media_descriptor: int
    sectors_per_fat: int

    @property
    def root_dir_sectors(self) -> int:
        return (self.root_entries * 32 + self.bytes_per_sector - 1) // self.bytes_per_sector

    @property
    def fat_start(self) -> int:
        return self.reserved_sectors * self.bytes_per_sector

    @property
    def root_start(self) -> int:
        sectors = self.reserved_sectors + self.fat_count * self.sectors_per_fat
        return sectors * self.bytes_per_sector

    @property
    def data_start(self) -> int:
        sectors = (
            self.reserved_sectors
            + self.fat_count * self.sectors_per_fat
            + self.root_dir_sectors
        )
        return sectors * self.bytes_per_sector

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def data_cluster_count(self) -> int:
        data_sectors = (
            self.total_sectors
            - self.reserved_sectors
            - self.fat_count * self.sectors_per_fat
            - self.root_dir_sectors
        )
        return data_sectors // self.sectors_per_cluster

    @property
    def fat_size_bytes(self) -> int:
        return self.sectors_per_fat * self.bytes_per_sector


def read_u16(buf: bytearray, offset: int) -> int:
    return buf[offset] | (buf[offset + 1] << 8)


def write_u16(buf: bytearray, offset: int, value: int) -> None:
    buf[offset] = value & 0xFF
    buf[offset + 1] = (value >> 8) & 0xFF


def write_u32(buf: bytearray, offset: int, value: int) -> None:
    buf[offset] = value & 0xFF
    buf[offset + 1] = (value >> 8) & 0xFF
    buf[offset + 2] = (value >> 16) & 0xFF
    buf[offset + 3] = (value >> 24) & 0xFF


def parse_layout(image: bytearray) -> Fat12Layout:
    if len(image) < 512:
        raise ValueError("Image is too small to contain a FAT boot sector")

    bps = read_u16(image, 11)
    spc = image[13]
    reserved = read_u16(image, 14)
    fats = image[16]
    root_entries = read_u16(image, 17)
    total16 = read_u16(image, 19)
    media = image[21]
    spf = read_u16(image, 22)
    total32 = (
        image[32]
        | (image[33] << 8)
        | (image[34] << 16)
        | (image[35] << 24)
    )
    total = total16 or total32

    if bps not in (512, 1024, 2048, 4096):
        raise ValueError(f"Unsupported bytes/sector in image: {bps}")
    if spc == 0 or reserved == 0 or fats == 0 or root_entries == 0 or spf == 0 or total == 0:
        raise ValueError("Image does not look like a FAT12 floppy image with a valid BPB")
    if total * bps > len(image):
        raise ValueError("FAT BPB total sector count is larger than the image file")

    return Fat12Layout(
        bytes_per_sector=bps,
        sectors_per_cluster=spc,
        reserved_sectors=reserved,
        fat_count=fats,
        root_entries=root_entries,
        total_sectors=total,
        media_descriptor=media,
        sectors_per_fat=spf,
    )


def create_blank_1440k_image() -> bytearray:
    layout = Fat12Layout(
        bytes_per_sector=512,
        sectors_per_cluster=1,
        reserved_sectors=1,
        fat_count=2,
        root_entries=224,
        total_sectors=2880,
        media_descriptor=0xF0,
        sectors_per_fat=9,
    )
    image = bytearray(layout.total_sectors * layout.bytes_per_sector)

    image[0:3] = b"\xEB\x3C\x90"
    image[3:11] = b"MSDOS5.0"
    write_u16(image, 11, layout.bytes_per_sector)
    image[13] = layout.sectors_per_cluster
    write_u16(image, 14, layout.reserved_sectors)
    image[16] = layout.fat_count
    write_u16(image, 17, layout.root_entries)
    write_u16(image, 19, layout.total_sectors)
    image[21] = layout.media_descriptor
    write_u16(image, 22, layout.sectors_per_fat)
    write_u16(image, 24, 18)  # sectors/track
    write_u16(image, 26, 2)   # heads
    write_u32(image, 28, 0)   # hidden sectors
    write_u32(image, 32, 0)   # total sectors, 32-bit fallback
    image[36] = 0             # drive number
    image[38] = 0x29          # extended boot signature
    write_u32(image, 39, 0x20260530)
    image[43:54] = b"CGA WORK   "
    image[54:62] = b"FAT12   "
    message = b"Non-system disk. Mount as data disk.\r\n$"
    image[62:62 + len(message)] = message
    image[510:512] = b"\x55\xAA"

    for fat_index in range(layout.fat_count):
        fat_start = layout.fat_start + fat_index * layout.fat_size_bytes
        image[fat_start:fat_start + 3] = bytes([layout.media_descriptor, 0xFF, 0xFF])

    return image


def normalize_83(name: str) -> bytes:
    if "/" in name or "\\" in name or ":" in name:
        raise ValueError("Image filename must be a root-level 8.3 name")
    parts = name.upper().split(".")
    if len(parts) > 2 or not parts[0]:
        raise ValueError(f"Invalid 8.3 filename: {name}")
    stem = parts[0]
    ext = parts[1] if len(parts) == 2 else ""
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$%'-_@~`!(){}^#&")
    if len(stem) > 8 or len(ext) > 3:
        raise ValueError(f"Filename is not 8.3-compatible: {name}")
    if any(ch not in allowed for ch in stem + ext):
        raise ValueError(f"Filename contains characters DOS 8.3 names should avoid: {name}")
    return stem.ljust(8).encode("ascii") + ext.ljust(3).encode("ascii")


def fat_offset(cluster: int) -> int:
    return cluster + cluster // 2


def get_fat_entry(image: bytearray, layout: Fat12Layout, cluster: int) -> int:
    off = layout.fat_start + fat_offset(cluster)
    if cluster & 1:
        return ((image[off] >> 4) | (image[off + 1] << 4)) & 0xFFF
    return (image[off] | ((image[off + 1] & 0x0F) << 8)) & 0xFFF


def set_fat_entry_one(image: bytearray, fat_base: int, cluster: int, value: int) -> None:
    rel = fat_offset(cluster)
    off = fat_base + rel
    value &= 0xFFF
    if cluster & 1:
        image[off] = (image[off] & 0x0F) | ((value << 4) & 0xF0)
        image[off + 1] = (value >> 4) & 0xFF
    else:
        image[off] = value & 0xFF
        image[off + 1] = (image[off + 1] & 0xF0) | ((value >> 8) & 0x0F)


def set_fat_entry(image: bytearray, layout: Fat12Layout, cluster: int, value: int) -> None:
    for fat_index in range(layout.fat_count):
        fat_base = layout.fat_start + fat_index * layout.fat_size_bytes
        set_fat_entry_one(image, fat_base, cluster, value)


def cluster_offset(layout: Fat12Layout, cluster: int) -> int:
    return layout.data_start + (cluster - 2) * layout.cluster_size


def dos_datetime(now: datetime) -> tuple[int, int]:
    date = ((now.year - 1980) << 9) | (now.month << 5) | now.day
    time = (now.hour << 11) | (now.minute << 5) | (now.second // 2)
    return date, time


def root_entry_offsets(layout: Fat12Layout):
    for i in range(layout.root_entries):
        yield layout.root_start + i * 32


def clear_cluster_chain(image: bytearray, layout: Fat12Layout, start_cluster: int) -> None:
    cluster = start_cluster
    seen = set()
    max_cluster = layout.data_cluster_count + 1
    while 2 <= cluster <= max_cluster and cluster not in seen:
        seen.add(cluster)
        next_cluster = get_fat_entry(image, layout, cluster)
        set_fat_entry(image, layout, cluster, 0)
        if next_cluster >= 0xFF8:
            break
        cluster = next_cluster


def delete_existing_root_file(image: bytearray, layout: Fat12Layout, dos_name: bytes) -> None:
    for off in root_entry_offsets(layout):
        first = image[off]
        if first == 0x00:
            break
        if first == 0xE5:
            continue
        if image[off:off + 11] == dos_name:
            start_cluster = read_u16(image, off + 26)
            if start_cluster:
                clear_cluster_chain(image, layout, start_cluster)
            image[off] = 0xE5


def prune_root_files(image: bytearray, layout: Fat12Layout, keep_names: list[str]) -> None:
    keep = {normalize_83(name) for name in keep_names}
    for off in root_entry_offsets(layout):
        first = image[off]
        if first == 0x00:
            break
        if first == 0xE5:
            continue
        attributes = image[off + 11]
        if attributes & 0x18:  # Keep volume labels and directories.
            continue
        if bytes(image[off:off + 11]) in keep:
            continue
        start_cluster = read_u16(image, off + 26)
        if start_cluster:
            clear_cluster_chain(image, layout, start_cluster)
        image[off] = 0xE5


def find_free_root_entry(image: bytearray, layout: Fat12Layout) -> int:
    for off in root_entry_offsets(layout):
        if image[off] in (0x00, 0xE5):
            return off
    raise ValueError("Root directory is full")


def find_free_clusters(image: bytearray, layout: Fat12Layout, count: int) -> list[int]:
    clusters = []
    max_cluster = layout.data_cluster_count + 1
    for cluster in range(2, max_cluster + 1):
        if get_fat_entry(image, layout, cluster) == 0:
            clusters.append(cluster)
            if len(clusters) == count:
                return clusters
    raise ValueError("Not enough free clusters in image")


def inject_file(image: bytearray, source_bytes: bytes, image_name: str) -> None:
    layout = parse_layout(image)
    dos_name = normalize_83(image_name)

    delete_existing_root_file(image, layout, dos_name)

    clusters_needed = max(1, math.ceil(len(source_bytes) / layout.cluster_size))
    clusters = find_free_clusters(image, layout, clusters_needed)

    for i, cluster in enumerate(clusters):
        next_value = 0xFFF if i == len(clusters) - 1 else clusters[i + 1]
        set_fat_entry(image, layout, cluster, next_value)

        src_start = i * layout.cluster_size
        chunk = source_bytes[src_start:src_start + layout.cluster_size]
        dst = cluster_offset(layout, cluster)
        image[dst:dst + layout.cluster_size] = b"\x00" * layout.cluster_size
        image[dst:dst + len(chunk)] = chunk

    entry = find_free_root_entry(image, layout)
    image[entry:entry + 32] = b"\x00" * 32
    image[entry:entry + 11] = dos_name
    image[entry + 11] = 0x20  # archive
    date, time = dos_datetime(datetime.now())
    write_u16(image, entry + 22, time)
    write_u16(image, entry + 24, date)
    write_u16(image, entry + 26, clusters[0])
    write_u32(image, entry + 28, len(source_bytes))


def build_image(
    source: Path | None,
    template: Path,
    output: Path,
    image_name: str,
    delete_names: list[str] | None = None,
    extra_files: list[tuple[Path, str]] | None = None,
    keep_names: list[str] | None = None,
) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    if template.exists():
        if template.resolve() == output.resolve():
            raise ValueError("Template and output paths must be different")
        shutil.copyfile(template, output)
        image = bytearray(output.read_bytes())
        mode = f"copied template {template}"
    else:
        image = create_blank_1440k_image()
        mode = "created blank 1.44 MB FAT12 data disk"

    layout = parse_layout(image)
    if keep_names:
        prune_root_files(image, layout, keep_names)
    if delete_names:
        for name in delete_names:
            delete_existing_root_file(image, layout, normalize_83(name))

    if source is not None:
        inject_file(image, source.read_bytes(), image_name)
    if extra_files:
        for extra_source, extra_name in extra_files:
            inject_file(image, extra_source.read_bytes(), extra_name)
    output.write_bytes(image)
    return mode


def parse_extra_file(value: str) -> tuple[Path, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--extra must use SOURCE=NAME syntax")
    source, image_name = value.rsplit("=", 1)
    if not source or not image_name:
        raise argparse.ArgumentTypeError("--extra must use SOURCE=NAME syntax")
    return Path(source), image_name


def dos_text_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a MartyPC FAT12 work disk.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--name", default=DEFAULT_IMAGE_NAME)
    parser.add_argument(
        "--delete",
        action="append",
        default=[],
        metavar="NAME",
        help="Delete a root-level 8.3 file from the copied template before injection.",
    )
    parser.add_argument(
        "--keep-only",
        action="append",
        default=[],
        metavar="NAME",
        help="Delete root-level files except repeated NAME values before injection.",
    )
    parser.add_argument(
        "--no-inject",
        action="store_true",
        help="Only copy/create and prune the output image. Do not inject --source.",
    )
    parser.add_argument(
        "--extra",
        action="append",
        type=parse_extra_file,
        default=[],
        metavar="SOURCE=NAME",
        help="Replace or add an additional root-level file in the output image.",
    )
    parser.add_argument(
        "--extra-text",
        action="append",
        type=parse_extra_file,
        default=[],
        metavar="SOURCE=NAME",
        help="Replace or add a DOS text file, normalizing line endings to CRLF.",
    )
    args = parser.parse_args()

    source = None if args.no_inject else args.source
    text_extras = [(source_path, image_name) for source_path, image_name in args.extra_text]
    mode = build_image(
        source,
        args.template,
        args.output,
        args.name,
        args.delete,
        args.extra,
        args.keep_only,
    )
    if text_extras:
        image = bytearray(args.output.read_bytes())
        for text_source, text_name in text_extras:
            inject_file(image, dos_text_bytes(text_source), text_name)
        args.output.write_bytes(image)
    print(f"{mode}")
    for name in args.delete:
        print(f"Deleted {name.upper()} from copied image if present")
    if args.keep_only:
        print(f"Kept only {', '.join(name.upper() for name in args.keep_only)}")
    if source is not None:
        print(f"Injected {args.source} as {args.name.upper()} into {args.output}")
    else:
        print(f"Wrote pruned template image to {args.output}")
    for extra_source, extra_name in args.extra:
        print(f"Injected {extra_source} as {extra_name.upper()} into {args.output}")
    for text_source, text_name in text_extras:
        print(f"Injected DOS text {text_source} as {text_name.upper()} into {args.output}")


if __name__ == "__main__":
    main()
