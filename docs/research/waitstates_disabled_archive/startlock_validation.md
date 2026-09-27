# STARTLCK validation — 2026-09-14

The final demo acquired a visible palette marker at **CGA pixel (9, 8)** in each of MartyPC's four exposed PIT phase settings. A separate cold disk boot ran all **3,600 frames**, restored text mode, and returned to the DOS `A:\>` prompt automatically.

This is an emulator result from the unchanged MartyPC core at commit `05c0d088e84ad6bbfac9b3f0d051e7eadefd9f44`, using an IBM 5160, 640 KiB, CGA, non-turbo 8088, normal DRAM refresh simulation, and GLaBIOS 0.2.6 XT. It is not physical-hardware validation.

Tested `files/STARTLCK.COM`: 36,608 bytes, SHA-256 `3e0e514005cb41809a209ad1311e63bd1426d6a9f820411a8a0af9fdc2417537`.

## Observations

| Marty PIT phase | Independent startups | Marker pairs | Marker-on, after OUT | Marker-off, after OUT | Period |
|---|---:|---:|---|---|---:|
| 0 | 1 | 307 | (210, 46) | (130, 47) | 79,648 CPU cycles |
| 1 | 1 | 307 | (210, 46) | (130, 47) | 79,648 CPU cycles |
| 2 | 1 | 307 | (210, 46) | (130, 47) | 79,648 CPU cycles |
| 3 | 1 | 304 | (210, 46) | (114, 47) | 79,648 CPU cycles |

Every marker observation, including the first, is included. Coordinates are in CGA master-clock dots and physical scanlines, sampled at instruction boundaries. They are not a separately instrumented I/O latch timestamp.

The raw framebuffer independently shows black-to-red starting at (210, 46). The active aperture starts at (192, 38); two dots represent one 320-pixel graphics pixel. This gives **(9, 8)**, with nine visible black pixels before the transition. The final ruler deliberately leaves this region black so white reference marks cannot hide an earlier transition.

All 1,225 completed visible frames in the phase sweep have the same FNV-1a-64 hash, `E50DA485F4B44E8F`. The final visible frame from each phase has SHA-256 `f04bd4d0e28b4a169174c0175ca8684b0d2b47efe213341753429584e40b61d9`. Phase 3 restores black 16 master-clock dots earlier in horizontal blanking; the visible output is identical. The first completed raw frame has one extra red pixel in nonvisible row 0. No visible frames were discarded to obtain the result.

The separate disk test observed 3,600 marker pairs with the same phase-0 positions and period. All 3,599 full visible frames before teardown have the same visible hash above. The last marker is followed by cleanup before another complete graphics frame. The [final captured screen](../../external/research/startlock-validation/disk/phase0-frame.png) shows the completion message and DOS prompt.

## Method and reproduction

The harness links the existing `marty_core` crate without modifying emulator code. It preserves normal instruction execution, CGA wait states, and refresh scheduling. The phase values call `Machine::pit_adjust(phase & 3)`, matching the desktop frontend. These are the emulator's exposed settings, not proof of an exhaustive hardware phase matrix.

The four short tests boot GLaBIOS for 20 million CPU cycles, then inject the actual COM at `1000:0100` through Marty's program-loading API, set its DOS-style segment/stack registers, and execute 30 million CPU cycles. These are four COM-injection runs, not four DOS boots. The disk test instead cold-boots the actual image, runs its DOS and AUTOEXEC normally, and continues for 420 million CPU cycles. The disk-loaded COM executes at segment `0C60`.

From the project directory, with the local Marty toolchain installed:

```powershell
0..3 | ForEach-Object {
    cmd /c tools\validate_startlock.cmd files/STARTLCK.COM $_ 30000000
}
.\.venv\Scripts\python.exe tools/validate_startlock.py
cmd /c tools\validate_startlock.cmd files/STARTLCK.DSK 0 420000000 external/research/startlock-validation/disk
.\.venv\Scripts\python.exe tools/validate_startlock.py --directory external/research/startlock-validation/disk --phases 0
```

The harness and summarizer are [validate_startlock.rs](../../tools/validate_startlock.rs), [validate_startlock.cmd](../../tools/validate_startlock.cmd), and [validate_startlock.py](../../tools/validate_startlock.py). Raw CSVs, framebuffer captures, and generated summaries are under `external/research/startlock-validation/`; disk-run results are in its `disk/` subfolder.

The durable [JSON record](startlock_validation.json) includes hashes, first observations, counts, phase results, and disk results. Its [SHA-256 file](startlock_validation.json.sha256) protects the record. The recorded disk hash identifies the image at validation time; changes only to bundled explanatory text can change that disk hash without changing the tested COM.

No physical CGA card, repeated power-on survey, or keyboard Escape test was performed. Automatic acquisition, sustained output in these emulator runs, actual disk autoboot, and automatic DOS return were exercised.

Validated disk SHA-256: `400eea02a0f257f82a634cfc2b6c2c35bca4e8b5678048ed466b8561bc7c7e7e`. Delivered disk SHA-256: `b2c4fd5f9f3eab8bacf78417e1e88c48aa35eef12de3388eeda277d9dbe32db6`. The final packaging update changed bundled README text and FAT timestamps; the parent build check verified unchanged boot sector, DOS, AUTOEXEC, and COM content.
