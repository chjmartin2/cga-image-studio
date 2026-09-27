# Area 5150 released module unpacking

The release is not a set of ordinary DOS COM programs despite the extensions.
The main `area5150.com` has a self-extractor; its compressed stream begins at
file offset `0x017E`. The other 28 COM files start directly with compressed
streams. All 29 streams use **ZX0 v2** and expand successfully with exact
input consumption, including the stream end marker.

The high-level decoder is based on the format documented by the
[ZX0 author's decompressor](https://github.com/einar-saukas/ZX0/blob/master/src/dzx0.c).
It bounds input, output, gamma values, and backward references. It rejects
truncated or trailing input. It does not execute the released programs.

## Independent validation

Each decoded module was also checked against the **original machine-code
decompressor in the distributed launcher**, from `CS:016B` up to its final
`RET` at `CS:0275`. Unicorn 2.1.4 executed only this isolated routine with
separate source, destination and stack memory. Hooks rejected execution
outside that code range, source overreads, and destination overreads or
nonsequential writes. The decoder's returned length and consumed source
length were checked as well as every output byte.

**All 29 modules matched byte-for-byte.** This verifies faithful unpacking;
it does not simulate CGA timing or establish the behavior of initialization.

| File | Released size | Unpacked size |
|---|---:|---:|
| `area5150.com` | 4,674 | 22,872 |
| `LAKE.COM` | 21,631 | 60,050 |

`LAKE.COM` released SHA-256:
`b13d3e9bf94817d8dd9b38ed0661e783bd730829de6e8ee495a0c9be4e374654`

`LAKE.COM` unpacked SHA-256:
`1192f22cb6dd3fa668acf8cfc221347438f599e8d006621e3ead2dc6f7aae0fe`

The frozen [manifest](unpack_manifest.json) contains the hashes and validation
results for every COM file. Downloaded binaries and the optional emulator
library remain in the ignored `external/research/` directory.

## Reproduce

From the project root, after extracting the release ZIP into
`external/research/area5150/release`:

```powershell
.venv/Scripts/python.exe docs/research/area5150/unpack.py
```

For the independent original-stub check, install the optional CPU emulator
into the isolated research tool directory, then run:

```powershell
.venv/Scripts/python.exe -m pip install --target external/research/python-tools unicorn==2.1.4
.venv/Scripts/python.exe docs/research/area5150/unpack.py --verify-stub
```

Outputs and a fresh manifest are written to
`external/research/area5150/unpacked/`. The source release is unchanged.
Do not run the unpacked effect files as standalone DOS COM programs: they
depend on the demo loader's custom services and memory layout.
