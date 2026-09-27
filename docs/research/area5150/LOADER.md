# Released Area 5150 loader contract

Analyzed 2026-09-14 from the downloaded Evoke 2022 party release. All addresses below are runtime offsets with COM origin `0100h`; an unpacked-file offset is the runtime offset minus `0100h`. Names assigned to routines are analytical descriptions, not recovered source symbols.

## Result

The released loader starts the decompressed `LAKE.COM` at its allocated segment's `0100h`, with `DS`, `ES`, and `SS` initially equal to that segment. The two `INT F0h / AH=0Ch` calls in Lake are **resource lookups**, not timing calibration. They obtain the already loaded and decompressed `SAMPLES.DAT` and `TUNE.DAT`.

The examined loader path does **not** patch Lake's words at `45E4h`, `45E6h`, or `45E8h`. Those words retain the released payload values `13FDh`, `0045h`, and `0000h` at entry. This conclusion follows from the actual load, decompress, context-initialization, and dispatch path, not merely the absence of literal address references.

This is static analysis of the released loader. It does not establish every register or memory value in the separately modified hardware-capture launcher, and it does not prove behavior over multiple power-on phases. The initializer byte comparison is documented independently in `capture_match.json`.

## Inputs and reproducibility

- Original package: `external/research/area5150/area5150.zip`, SHA-256 `acc37410944e52a111ebb7028ebd9a3233daa9454e8761c3f4fa99ae613a2be5`.
- Unpacked loader: `external/research/area5150/unpacked/area5150.com`, 22,872 bytes, SHA-256 `93ce5773d8570c742905b667664c18f29bed462a85f6e3da6b0b05d2e1102c73`.
- Unpacked effect: `external/research/area5150/unpacked/LAKE.COM`, 60,050 bytes, SHA-256 `1192f22cb6dd3fa668acf8cfc221347438f599e8d006621e3ead2dc6f7aae0fe`.
- Disassembly: `loader.linear.asm`, produced with Capstone 5.0.7 in 16-bit x86 mode. Its warning is significant: data after `0CEAh` is not executable merely because a linear decoder prints mnemonics there. The tables below were decoded as data.

## Script records that load and run Lake

The main loop at `012Ah..014Fh` selects a record, dispatches on its first byte through the word table at `0CEAh`, and advances the record index. Routine `01A4h` computes the record address as `1718h + index * 64`. Each record has an action byte, a 13-byte filename field, and action-dependent fields beginning at offset `+0Eh`.

| Index | Loader offset | Action | Resource | Meaning recovered from handler |
|---:|---:|---:|---|---|
| 254 | `5698h` | `01h` | LAKE.COM | Load executable through `04C6h` |
| 255 | `56D8h` | `02h` | SAMPLES.DAT | Load data through `0480h` |
| 256 | `5718h` | `02h` | TUNE.DAT | Load data through `0480h` |
| 257 | `5758h` | `04h` | LAKE.COM | Decompress through `062Bh` |
| 258 | `5798h` | `04h` | SAMPLES.DAT | Decompress through `062Bh` |
| 259 | `57D8h` | `04h` | TUNE.DAT | Decompress through `062Bh` |
| 260 | `5818h` | `08h` | LAKE.COM | Enter saved execution context through `06C7h` |
| 261 | `5858h` | `0Bh` | LAKE.COM | Free its allocation through `0800h` |
| 262 | `5898h` | `0Bh` | SAMPLES.DAT | Free its allocation |
| 263 | `58D8h` | `0Bh` | TUNE.DAT | Free its allocation |

The load records contain these three words at `+0Eh/+10h/+12h`:

| Resource | Uncompressed size, paragraphs | Packed bytes | Executable allocation field |
|---|---:|---:|---:|
| LAKE.COM | `0EAAh` = 3,754 | `547Fh` = 21,631 | `1000h` |
| SAMPLES.DAT | `0FE5h` = 4,069 | `B406h` = 46,086 | `0000h` |
| TUNE.DAT | `02D8h` = 728 | `0591h` = 1,425 | `0000h` |

The paragraph count is rounded up: `0EAAh * 16 = 60,064`, whereas Lake's actual decompressed stream is 60,050 bytes. Do not interpret the size returned by the resource service as the exact compressed or uncompressed byte count.

## Entry and context

Executable handler `04C6h` allocates memory, reads the packed stream to offset `0100h` (`0502h`), and synthesizes the portions of a PSP used by the demo: `INT 20h` at offset zero, the allocation-end segment at `+2`, and the environment segment at `+2Ch` (`0510h..0522h`).

Routine `0534h` initializes a registry context. It writes `0100h` to the initial and saved IP fields (`0554h..055Dh`), and the allocation segment to the initial/saved CS and DS/ES/SS fields (`055Ah..0569h`). It sets the initial flags with IF enabled and TF/DF clear (`0544h..054Eh`). The stack calculation caps the size at `0FFEh` paragraphs and subtracts two bytes (`056Ch..0581h`); for Lake this gives `SP=FFDEh`. Routine `0699h` writes a zero return word at that stack position.

The decompressor at `062Bh` moves the packed bytes out of the destination's way and calls the common depacker at `0E7Eh`, using `DI=0100h` for executable resources (`063Dh..0676h`). It does not apply an EXE relocation table or a Lake-specific patch list.

Action `08h` at `06C7h` restores the context and enters by `IRET` at `0728h`. Its first entry is therefore `LakeSegment:0100h`. The allocation segment depends on available DOS memory; `0100h` is the fixed entry offset, not a fixed physical address. `INT 20h` is hooked to `0754h`, which restores the loader's stack and returns to its dispatcher.

## INT F0h, AH=0Ch

The loader installs interrupt vector `F0h` to its `0A24h` handler at `02CEh..02EEh`. The handler saves the caller's stack, switches to a loader-owned interrupt stack, masks AH to its low four bits, and dispatches through a 16-word table at `0D04h`. Entry 12 (`0D1Ch`) contains `0CAEh`.

The resource lookup service at `0CAEh`:

1. Saves DS/SI and the current resource-registry pointer.
2. Passes the caller's `ES:DI` filename to the registry search at `05BFh`.
3. Selects the matching resource record via `01D0h`.
4. Returns the record's uncompressed paragraph count in AX, allocation segment in ES, and zero in DI (`0CC7h..0CCDh`).
5. Restores the current registry pointer, DS/SI, caller BX, and caller stack; returns with `IRET` (`0CCFh..0CE8h`).

The searched registry has 24 records of 64 bytes beginning at loader `0FF9h`. This service does not open a file or decompress one; the script has already done both. Its found-resource path contains no CGA, PIT, PIC, or refresh-register access.

At Lake `0100h`, DI is `45EAh`, pointing to `SAMPLES.DAT`. After the first service return, Lake saves the returned segment at `45C6h`. It restores ES to CS and sets DI=`45F6h`, pointing to `TUNE.DAT`. After the second return at `0116h`, it saves ES at `45C8h`, multiplies AX by 16, and saves the resulting paragraph-rounded byte length (`2D80h`) at `45CAh`.

## Why there is no loader timing-word adjustment on this path

The Lake script has no action `09h`, the command-tail-copy handler at `07D2h`. That handler itself writes only to the effect PSP beginning at `0080h`, not to arbitrary offsets.

For the actual Lake path, executable-memory writes outside decompression are the synthesized PSP fields and the initial stack word at `FFDEh`. Registry/context writes stay in the loader's segment. The main dispatcher has no additional Lake-specific action between decompression and entry. Resource service `AH=0Ch` reads the registry and changes return registers, without writing to the Lake allocation.

As a secondary check, the little-endian constants `E4 45`, `E6 45`, and `E8 45` do not appear anywhere in the unpacked loader. The stronger evidence remains the traced generic handlers and the exact Lake script above.

## Provenance references

- [Author-submitted release page](https://www.pouet.net/prod.php?which=91938): the downloaded archive's NFO identifies it as the 2022 party version.
- [GloriousCow, Bus Sniffing the IBM 5150: Part 1, October 1, 2023](https://martypc.blogspot.com/2023/10/bus-sniffing-ibm-5150.html): describes decompressing the released loader and modifying its execution script to jump directly to the credits, naming that launcher `acredits.com`.
- [Published Area5150 hardware capture](https://github.com/dbalsom/marty_tools/tree/23d99544ebf8aaf009bf2a551f048bb4b68a39a7/bus_sniffer/captures/area5150): uses the name `CREDITS.COM`; the independent byte comparison in this research directory ties the captured initializer to the released decompressed `LAKE.COM`.
