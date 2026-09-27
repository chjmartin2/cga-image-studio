# Local MartyPC source build

This project has a separate checkout of [MartyPC](https://github.com/dbalsom/martypc) under `external/martypc`. The existing Desktop installation is independent of this build.

## Build and launch

From the CGA Studio project directory, run:

```powershell
cmd /c tools\build_martypc.cmd
cmd /c run_martypc_latest.cmd
```

The build script initializes the installed Visual Studio C++ toolchain and runs:

```text
cargo build --locked --release -p martypc_eframe --bin martypc
```

Double-click **`MartyPC Latest.lnk`** in the project root, or use the CMD launcher
above. A second copy of the shortcut is beside the build executable. The shortcut
uses an absolute configuration path and sets the working folder to `install`.

The executable is `external/martypc/target/release/martypc.exe`. Running that raw
EXE directly from its build folder produces a missing-configuration error because
its configuration and ROMs are under `install`. The CMD launcher changes to that
directory, supplies the absolute path to `martypc-cga.toml`, and forwards arguments.

To recreate the shortcuts after moving the project or rebuilding in a new location:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/create_martypc_shortcuts.ps1
```

For a build log in PowerShell:

```powershell
cmd /c tools\build_martypc.cmd *> external\marty-toolchain\build-release.log
$LASTEXITCODE
```

## Version and toolchain

The source checked on September 14, 2026 is upstream `main`, commit [`05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44`](https://github.com/dbalsom/martypc/commit/05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44), dated September 7, 2026. The workspace package version is **0.5.0**. This is a source build, not the older 0.4.1 release archive.

The checkout pins **Rust 1.92.0** in `rust-toolchain.toml`. This installation uses the `x86_64-pc-windows-msvc` host with the default desktop features. Upstream requests the WebAssembly standard-library target as well; rustup installs it even when the requested binary is native Windows.

Tools and caches are local to this workspace:

| Component | Location |
| --- | --- |
| Rustup proxies and Cargo cache | `external/marty-toolchain/cargo` |
| Rust toolchains | `external/marty-toolchain/rustup` |
| libclang 18.1.1 | `external/marty-toolchain/clang/clang/native/libclang.dll` |
| Visual Studio Build Tools | Discovered with Microsoft's `vswhere.exe` |
| Release output | `external/martypc/target/release` |

The script sets `CARGO_HOME`, `RUSTUP_HOME`, and `LIBCLANG_PATH` for its process only. It does not require changing the user's permanent `PATH`. libclang is used by the OPL dependency's binding generator. The upstream MSVC configuration requests an 8 MiB stack.

The source tree and isolated toolchain are ignored by CGA Studio's Git repository; the build script and this guide are project files. Preserve the local configuration files when replacing the external checkout.

## CGA baseline

The launcher's configuration is `external/martypc/install/martypc-cga.toml`. It uses the separate machine definition `install/configs/machines/cga_studio_5160.toml`:

| Setting | Value |
| --- | --- |
| Machine | IBM 5160, 640 KiB, non-turbo 4.77 MHz |
| BIOS | Bundled GLaBIOS XT 0.2.6, unique alias `glabios_xt_0.2.6` |
| Video | CGA with monitor emulation enabled |
| PIT phase | 0 initially |
| CPU wait states | Enabled |
| DRAM DMA refresh simulation | Enabled |
| Display | RGBI, integer scaling, nearest filtering, Accurate aperture |
| CRT effects / aspect correction | Disabled |
| Disk drives | Two 360 KiB drives, strict image compatibility |
| Boot disk | Verified STARTLCK runtime copy, `install/media/floppies/startlock_phase0_runtime.dsk` |

For the active start-line experiment, the general launcher now boots a runtime
copy of `files/STARTLCK.DSK`, which contains and automatically runs `STARTLCK.COM`.
The earlier plain-DOS configuration is preserved as
`install/martypc-cga-dos-only.toml`; its disk is unchanged. The demo launcher
verifies that the selected disk contains the current COM before starting MartyPC.
The `files` directory is also added as a floppy-resource path for the disk browser.
The bundled GLaBIOS is convenient for testing; it does not make the machine's BIOS
identical to the original IBM hardware.

In this upstream commit, native automount uses a direct path relative to the working directory and sets the mounted disk writable. `write_protect_default = true` applies to the disk-loading UI, but is not applied by native automount. The separate runtime disk avoids using the project's master template as the mounted image. Use the emulator's disk write-protection control when required.

MartyPC's emulated starting phase is deterministic. For timing investigation, close the process, change `machine.pit_phase` in `martypc-cga.toml` to 0, 1, 2, or 3, and launch a fresh process for each run. Record the phase, commit, exact COM/disk hash, and observed transition positions. A correct picture at phase 0 alone is insufficient evidence of a phase-independent acquisition method. Emulator results also need comparison with physical CGA hardware.

## Get subsequent updates

Check the source tree before updating, then fast-forward `main` and rebuild:

```powershell
git -C external/martypc status --short
git -C external/martypc fetch origin main
git -C external/martypc merge --ff-only origin/main
cmd /c tools\build_martypc.cmd
```

The custom machine definition may appear as an untracked file; it belongs to this local test setup. Resolve any unexpected tracked changes before updating. `--ff-only` stops if the checkout has diverged. Do not run `cargo update` merely to obtain MartyPC changes: `--locked` intentionally builds the dependency versions selected by the upstream commit. A future commit may change the pinned Rust version or configuration schema; rustup follows the checkout's toolchain file.

## Recreate the isolated prerequisites

For a new workspace, first install Visual Studio's C++ Build Tools and Git. Follow the upstream [Windows build instructions](https://github.com/dbalsom/martypc/blob/05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44/BUILDING.md). Clone upstream into `external/martypc`, then use the official Windows `rustup-init.exe` with these process environment variables:

```powershell
$martyToolDir = Join-Path (Get-Location).Path 'external/marty-toolchain'
$env:CARGO_HOME = Join-Path $martyToolDir 'cargo'
$env:RUSTUP_HOME = Join-Path $martyToolDir 'rustup'
# Run the downloaded official rustup-init.exe with:
# -y --no-modify-path --profile minimal --default-host x86_64-pc-windows-msvc --default-toolchain 1.92.0
```

This workspace's libclang was installed using Python's `libclang==18.1.1` wheel into `external/marty-toolchain/clang`; an existing Visual Studio LLVM installation can also supply the DLL if the script's `LIBCLANG_PATH` is adjusted. Restore the custom configuration and machine file, or create them from upstream defaults using the baseline table above.

## Validation record

Checked September 14, 2026:

- Locked release build passed with Rust 1.92.0 and MSVC. A clean build completed in 2 minutes 11 seconds; upstream compiler warnings remain.
- `--help` and `--version` exited successfully; the binary reports `Version: 0.5.0`.
- `--configfile martypc-cga.toml --machinescan` exited successfully and listed `cga_studio_5160` among 24 machine configurations.
- `--configfile martypc-cga.toml --romscan --nosound` exited successfully and found a complete `glabios_xt_0.2.6` ROM set.
- A 10-second startup probe initialized the custom machine, resolved its GLaBIOS image, initialized the GPU display pipeline, ran at a logged 4.7727 MHz, and successfully loaded the DOS disk into drive A:. The window closed normally. The source and runtime disk hashes still matched afterward. No CGA experiment was started.

The executable is 32,181,248 bytes, SHA-256:

```text
0234E53512EE0D086DDB88C62A3CF44E05A5407712B3B9DE02B14190292C983F
```

Local logs are in `external/marty-toolchain/`: `build-release.log`, `marty-help.log`, `marty-version.log`, `marty-machinescan.log`, `marty-romscan.log`, and `marty-startup*.log`.

These checks establish a working local source build and basic startup. They do not validate the project's raster timing on an IBM CGA card.
