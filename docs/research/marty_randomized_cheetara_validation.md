# Cheetara in randomized MartyPC — October 7, 2026

The exact Phase 9 Cheetara export passes all 20 randomized DOS boots in the latest MartyPC core's cycle-clocked mode. It fails all 20 randomized boots in the default dynamic CGA mode. Fixed PIT 9 / CGA 0 controls show the same difference: cycle passes, dynamic fails.

| CGA clocking | Randomized launches | Exact launches | Completed randomized frames | Fixed PIT 9 / CGA 0 |
|---|---:|---:|---:|---|
| Default (dynamic) | 20 | 0 | 5831 | Fails: 2,573 wrong logical pixels per frame |
| Cycle | 20 | 20 | 5861 | Passes: every pixel matches |

Both controls and all randomized runs together produced 12,274 completed frames. Within each launch, the rendered image hash stayed constant. Default-mode errors ranged from 1,376 to 7,186 wrong logical pixels per frame. All cycle-mode frames had zero wrong dots and zero unequal two-dot pixel pairs. Randomization was performed by MartyPC's own initialize_clock_phases function, independently in each process, rather than a test-side substitute RNG. The selected PIT and CGA offsets are recorded for every launch.

This identifies an observable difference between the emulator's dynamic and cycle clocking paths. It does not prove which emulation path matches physical hardware. The supplied PIT9 ZIP explicitly used cycle clocking, so the cycle-mode comparison is the relevant continuation of those earlier successful tests.

## Inputs and method

- Latest development commit: [6f9ac9c0ab643c371931bd8a993152c2598d9f42](https://github.com/dbalsom/martypc/commit/6f9ac9c0ab643c371931bd8a993152c2598d9f42), October 5, 2026.
- Input: artifacts/pit9-locked/CHEETL.COM, SHA-256 `43e4aef4da292e43e91be10f3cbe20ccc021a073382deb336472088d13f99f4c`. No changes or re-encoding.
- Boot disk: artifacts/pit9-locked/CGATEST.DSK; TEST.COM was verified byte-for-byte equal to CHEETL.COM.
- Independent DOS boots under GLaBIOS 0.2.6, IBM 5160, non-turbo 8088; wait states and DMA refresh enabled.
- 110 million emulated CPU cycles per launch; about 289–295 completed image frames after boot and acquisition.
- A headless observation harness executes the latest unmodified core and captures its actual display buffer. Cycle mode is selected through the existing video-card API. All 227 core files match the downloaded upstream source archive.
- Pixel comparison checks all 128,000 rendered master-clock dots against the intended 320×200 RGBI image, including both dots per logical pixel.
- These 20 random launches per mode sample startup combinations; they do not exhaust all 192 PIT/CGA combinations.
- The main MartyPC executable is unchanged. The earlier supplied emulator and hardware packet are unchanged.

## Evidence

- Full results, phases and provenance: marty_randomized_cheetara_validation.json.
- Actual default-mode rendered examples: ../../artifacts/marty-randomized/launch-comparison.png.
- Actual cycle-mode rendered examples: ../../artifacts/marty-randomized-cycle/launch-comparison.png.
- Private source, observation harness and raw traces: external/research/marty-randomized.

The latest desktop executable was also built in the isolated research directory and launched with the Cheetara disk and both randomization options enabled. Pixel statistics above come from the core observation harness, not desktop screenshots. Desktop build SHA-256: 2350a40891fbec7044c1238964ba3b37b4acfa5aef7e81e1b0f4021fb1a43bae. The local desktop configuration was adapted to the newer serial-bridge schema. No changes were made to upstream emulator source.
