# Initial release closeout checklist

Working checklist — 2026-09-27. Baseline: v0.3.0-alpha.3.

## Interactive validation agreement

- [x] Raiders refreshed after the text-mode color correction; user confirmed
  it looks great in Marty. Alpha.3 demo disk and checksums refreshed.
- [x] Native GUI rebuild: grouped modes, contextual sidebar, collapsible
  advanced settings, unified Export menu, fit previews, native theme, tooltips.
  User confirmed the new GUI is great.
- [x] Follow-up: restore full-width identity banner with native activity bar.
  Implemented Ready / Working / percentage progress and cancellation/error
  states, X stop button, and whole-pixel automatic preview zoom. User confirmed
  the GUI looks and works great on 2026-09-28.

Next proposed item: output-validity safeguards across all modes. Verify that
changing an input or conversion setting cannot export stale output under new
settings; preview-only zoom must not invalidate a conversion. Include export
before conversion, during background work, and after cancellation/failure.

- [x] **640x200 Multicolor Composite implementation — user confirmed complete.**
  Includes the exhaustive bitmap encoder, Old/New CGA selection, the explicit
  After each line / During line search selector, the diffusion-method-None fix,
  and the corrected composite control layout. User reviewed side-by-side,
  signed difference, and absolute-error comparisons and closed this item.
  Native Marty composite visual and physical-hardware qualification remain
  separate release-validation tasks; this signoff does not imply those passed.

- [x] **Mini-Frames retained and visually validated in native MartyPC.** User
  confirmed both no-dither and Floyd–Steinberg diagnostics. At user request,
  exports now use a display-length dropdown (5, 10, 30, 60, 120, 300 seconds;
  default 30) instead of a keyboard-triggered exit. Default output is byte-exact
  to the approved diagnostic. All six GUI duration exports pass; 19 exporter
  tests and 54 subtests pass. Durations are nominal at 60 frames/second.

Completed item: fix and validate the 80x100 512-color encoder's four-pattern
selection versus two-pattern export mismatch. Converter now restricts candidate
patterns to 0xCC/0x66 (characters 55h/13h); export rejects unsupported patterns
instead of silently substituting. Four-pattern modes are unchanged. The focused
unit/export checks pass (21 tests, 54 subtests). The exporter also now uses
16-character horizontal sync to retain composite color. User confirmed the
corrected 512 test displayed perfectly; this item is complete.

Complete one checklist item at a time. Report the change and verification, then
wait for explicit user confirmation before starting the next item. Automated
checks do not substitute for user acceptance.

- [x] Remove 640x200 Mode Switch from the GUI. Source syntax and menu checks passed;
  user confirmed all requested GUI checks. Experimental code and the
  [deferred mode backlog](DEFERRED_MODES.md) are preserved. No package rebuild requested.

Completed item: user-authorized development detour — add **640x200 Multicolor
Composite** using the Prince exhaustive bitmap-search method, and clarify the
160x200 description without changing that algorithm. Implementation and
automated validation complete; user confirmed implementation complete. See
[implementation and validation](MULTICOLOR_COMPOSITE.md). No package rebuild.

User-reported validation defect: Error diffusion + method None still diffused
in Multicolor Composite because the missing kernel fell back to Floyd-Steinberg.
The conversion entry point now treats that explicit selection as no dithering
before dispatching to any mode. Regression compares actual GUI bitmap and
preview bytes against Dither family None. User retest pending.

Current extension, explicitly requested: default-off **Diffuse error during
search** for Multicolor Composite. Candidate paths carry horizontal residuals;
merged states retain the winner's error. This approximate option preserves the
original exhaustive method when off. Automated checks and user A/B review are
tracked in MULTICOLOR_COMPOSITE.md; user confirmation remains pending.

Follow-up: replace that checkbox with **Composite error diffusion: After each
line / During line search**, defaulting to After each line. Both choices require
Convert. A real GUI round-trip test checks After → During → After and requires
the final bitmap and preview to exactly reproduce the first result. User
confirmation of the selector remains pending.

GUI follow-up: moved Composite model (Old/New CGA) to its own row and composite
diffusion timing to a separate row. Previously they overlapped mode-switch
optimization and HiColor controls. Live Tk geometry checks verify neither is
covered, both Old/New choices work, and visibility survives switching through
HiColor and Mode Switch. User visual confirmation pending.

Historical review (Mini-Frames recommendation superseded by successful user testing):
Source review finds distinct methods:
512 uses two composite character patterns and a static display; Mini-Frames uses
four patterns with an active CRTC timing loop; regular 1024 uses the centered
four-pattern path; HiColor uses foreground/background character fill masks.
The Mini-Frames exporter explicitly documents historical failure in MartyPC.
That comment is not a fresh emulator test. Recommendation: defer Mini-Frames
from the release menu, preserve its source, and retain the other three pending
their individual runtime qualification. Awaiting user decision; no additional
mode has been removed.

Further source review, requested before a removal decision:
- Mini-Frames intends full-height 200-scanline output; regular 80x100 1024
  uses 100 centered scanlines and an active CRTC loop, not a static display.
- All 512/1024 text-composite modes and 160x200 Composite use NTSC simulation.
  HiColor uses RGB foreground/background spatial averaging, not NTSC decoding.
- Release defect: 512 conversion uses the shared four-pattern LUT, while its
  packer supports only two patterns and substitutes character 0x55 for others.
  Restrict its encoder gamut and verify preview/export agreement before acceptance.
- Centered 1024 exporter currently auto-exits after 300 loop iterations (commented
  as about five seconds); keyboard exit is absent. Validate and decide desired behavior.
- Centered 80x100 preview halves a doubled image with LANCZOS; check against a
  direct one-scanline-per-cell render during preview accuracy qualification.
- Color-count labels describe combinations/approximate gamuts, not proven counts
  of distinct displayed colors. Review labels before release.

These are source findings, not newly completed emulator tests. No mode removal
or GUI relabeling is approved by this review alone.

## Release agreement

- [ ] Agree on the retained feature set before implementation cleanup.
- [ ] Freeze new features; fix defects, simplify the interface, add help, and qualify exports.
- [ ] Choose release number and supported Windows versions.
- [ ] Define supported emulator machines, video cards, and display connections per mode.
- [ ] Agree that physical hardware qualification is deferred. Record the reported thin palette-boundary seams on an unidentified “NEW CGA” card using aligned 8 writes. The inspected `C:\dos\cga_320_startlock.dsk` contains the current aligned timing code. Exact host and card remain unknown.
- [ ] Preserve current timing templates unless a reproducible failure justifies changing them.

“100% validation” means every retained mode and every supported output has a completed acceptance record, every applicable control/value is exercised, and required interaction tests pass. It is not a claim about every possible input image, every combination of settings, or untested physical hardware. No untested cell counts as passed. Unsupported combinations must be disabled and explained.

## 1. Mode audit — decide together

These are the 13 current GUI entries, not 13 confirmed distinct hardware capabilities. DOS support below reflects exporter branches, not completed validation. For each entry record Keep / Merge / Advanced / Remove, rationale, and replacement where applicable.

| Current mode | Current DOS export path | Decision / evidence needed |
|---|---|---|
| 320x200 (4 Colors) | Present | Baseline; qualify all palettes and background colors |
| 640x200 (2 Colors) | Present | Baseline; qualify foreground/background behavior |
| 160x200 (16 Colors) Composite | Present | Old/New CGA models; composite rendering and expected color tolerance |
| 640x200 Multicolor Composite | Added in current source | Exhaustive bitmap NTSC search; automated checks passed; user visual acceptance pending |
| 80x100 (512 Colors) | Present | Explain apparent colors and compare against other 80x100 modes |
| 80x100 (1024 Colors) Mini-Frames | Present | Identify unique benefit, temporal behavior, and limitations |
| 80x100 (1024 Colors) | Present | Compare with Mini-Frames; check for functional duplication |
| 640x100 (1024 Colors) | Present | Qualify background encoder, cancellation, preview, and runtime |
| 640x200 (1024 Colors) | Present | Verify effective resolution, display method, and runtime |
| 160x100 (16 Colors) | Present | Compare text-mode implementation and target-card variants |
| 640x200 (16 Colors) Char | Present | Explain character restrictions; qualify subsampling option |
| 80x100 (4352 Colors) HiColor | Present | Verify apparent-color claim and color-limit option |
| 320x200 (4 Colors) Mode Switch | Present | Treat 1, 8, and 8 staggered as separate acceptance cases |
| 640x200 (2 Colors) Mode Switch | Not implemented | Removed from GUI; user validated. Retained as deferred source work. |

- [ ] Compare related modes using the same photos, artwork, gradients, and line patterns.
- [ ] Record differences in resolution, colors, flicker, artifacts, conversion speed, and hardware requirements.
- [ ] Remove a mode only after showing it is redundant or agreeing it is outside release scope.
- [ ] Consolidate duplicate names/options without losing a useful conversion method.
- [ ] Distinguish simultaneous hardware colors from spatially or temporally blended apparent colors.
- [ ] Put specialist controls behind an Advanced section where appropriate.
- [ ] Preserve reference images and old export examples before retiring paths.

## 2. GUI and interaction cleanup

- [ ] Make the primary flow clear: Open image → choose mode/settings → Convert → inspect → Export.
- [ ] Group controls into Mode, Image adjustment, Dithering, Preview, and Export.
- [ ] Give each mode a short plain-language description and hardware/display requirements.
- [ ] Add hover instructions to every button and non-obvious control; include effect, applicability, and any required next step.
- [ ] Provide keyboard-accessible help as well as hover text; do not rely on tooltips alone.
- [ ] Show only relevant controls; explain disabled controls where useful.
- [ ] Use consistent language for palette changes: 1, 8, 8 staggered. Explain the fixed alternating stagger without implying randomness or animation.
- [ ] Disable conversion until an image is loaded; disable exports until a valid conversion exists.
- [ ] Track changes that invalidate output across all modes. Prevent exporting old image data with newly selected settings.
- [ ] Separate preview-only changes from settings that require reconversion.
- [ ] Show conversion progress and busy state; prevent conflicting actions and duplicate jobs.
- [ ] Verify cancellation and window close during long conversions leave no orphan worker or corrupted output.
- [ ] Give useful errors with a recovery step; remove implementation jargon from normal dialogs.
- [ ] Make save dialogs, extensions, default filenames, overwrite behavior, and cancellation consistent.
- [ ] Label GIF as an image preview and COM/ASM/DSK by purpose; explain animation where applicable.
- [ ] Verify Optimize Palette, reset, tone-match, difference view, and palette-layout map behavior.
- [ ] Clarify scaling, pixel aspect ratio, effective-resolution preview, and image cropping.
- [ ] Test resizing, small screens, Windows scaling at 100/125/150/200%, focus order, shortcuts, and readable contrast.
- [ ] Display one consistent product name and release version in title, About, executable metadata, and documentation.
- [ ] Confirm whether settings persistence is already supported; document/reset it consistently. Defer new persistence features unless needed for release.

## 3. Conversion and control validation

- [ ] Create a deterministic fixture set: photo, flat-color artwork, grayscale/color ramps, all CGA indices, one-pixel lines, checkerboards, odd dimensions, portrait and landscape.
- [ ] Test supported input formats and explicitly establish handling of transparency, animated inputs, orientation metadata, and color profiles.
- [ ] Test tiny and large inputs, corrupt files, unsupported formats, missing files, and canceled dialogs.
- [ ] Verify Fit/letterbox, Fill/crop, and Stretch with each resampler.
- [ ] Exercise every input-adjustment slider at default and extremes; confirm reset and conversion agree.
- [ ] Exercise every diffusion algorithm, ordered size 2–16, dither strength, serpentine setting, and no-dither case where applicable.
- [ ] Exercise every palette/background selection and Old/New CGA composite setting where applicable.
- [ ] Exercise target CGA versus EGA/VGA only for modes that support those targets.
- [ ] Exercise border, palette-aware dithering, HiColor limit, character subsampling, and other mode-specific controls.
- [ ] Test mode switches in both directions and repeated conversions for stale state or settings leakage.
- [ ] Verify deterministic output where intended; record intentional temporal or stochastic behavior.
- [ ] Define a finite interaction matrix: exhaustive small/high-risk combinations, pairwise coverage for broad independent options, and documented exceptions.
- [ ] Compare preview data with the exported bitmap, palette plan, and temporal sequence using an independent decoder where practical.

## 4. Output acceptance — every retained mode

Create a result row for each mode/submode × supported target/display configuration × output type. Treat aligned 8, staggered 8, and 1 change as separate submodes. Mark unsupported cases N/A with a reason, not Pass.

- [ ] GIF: reopen, verify dimensions, palette, frame count, timing, looping, and correspondence with preview as applicable.
- [ ] COM: run under DOS in native MartyPC; verify appearance, stability, keyboard exit, restored text mode, and rerun without reboot.
- [ ] ASM: assemble with documented NASM command; require byte equality to the corresponding COM or explain unavoidable metadata differences; run the assembled result in MartyPC.
- [ ] DSK: verify FAT structure, program integrity, boot files, and boot sector; cold-boot the actual exported disk in MartyPC and check automatic display and exit behavior.
- [ ] Verify long paths, spaces, Unicode filenames, read-only destinations, overwrite refusal, and disk-write errors.
- [ ] Ensure canceled/failed exports leave no misleading partial files and preserve existing files.
- [ ] Confirm exports are self-contained and require no developer checkout at runtime.

GIF is checked in an image viewer/decoder, not as a DOS executable. ASM is tested through the assembled COM. COM and DSK are directly executed in MartyPC.

## 5. MartyPC qualification

- [ ] Pin the emulator build, ROMs, machine configuration, speed, video card, output type, wait states, and refresh settings in each report.
- [ ] Use real CPU wait states and refresh behavior; preserve the corrected eight-write validator configuration.
- [ ] Select RGBI versus composite intentionally. Verify the emulator supports each required card variant; document any gaps instead of treating unmatched configurations as valid.
- [ ] Capture native MartyPC screenshots for every retained mode and target; review them together against studio previews.
- [ ] Use exact digital pixel comparisons for applicable RGBI modes. Define justified visual/color tolerances for composite and temporal modes before acceptance.
- [ ] Verify complete frame sequences for temporal modes, not just a favorable still frame.
- [ ] Run a defined stability test for every mode; extend timing-sensitive modes with startup-phase, cold-boot, and reentry cases.
- [ ] Rerun both eight-write qualification suites and GUI export suites after relevant changes; retain hashes and results.
- [ ] Obtain native visual confirmation for 8 staggered; existing aligned confirmation does not cover it.
- [ ] Qualify the single-change-per-line path independently; eight-write results do not cover it.
- [ ] Test border/clipping, first/last rows, palette boundaries, flicker, image drift, and DOS restoration.
- [ ] Record physical-hardware edge seams as unresolved/deferred; do not tune them from photographs or label emulator success as hardware certification.

## 6. Code and repository cleanup

- [ ] Inventory active application code versus old versions, experiments, calibration tools, and archived evidence.
- [ ] Establish one obvious application entry point and remove confusing obsolete launchers from the user-facing distribution.
- [ ] Remove dead/duplicate code only after checking references and preserving needed regression fixtures.
- [ ] Consolidate mode definitions and capability metadata so the GUI, conversion, exports, help, and tests agree.
- [ ] Separate GUI state, conversion logic, and export assembly incrementally where it reduces defects; avoid a wholesale rewrite before release.
- [ ] Centralize output-validity checks and error handling.
- [ ] Preserve byte-exact timing templates and rebuild checks through cleanup.
- [ ] Review worker/thread shutdown, temporary files, file handles, image memory, and repeated-use behavior.
- [ ] Review dependency pins, bundled files, licenses, ROM/DOS redistribution permissions, and source attribution.
- [ ] Remove machine-specific absolute paths from shipping code and documentation.
- [ ] Keep large raw traces and local tooling out of the release while retaining reproducible evidence and hashes.
- [ ] Run relevant regression tests after each change; add tests for meaningful defects and acceptance behavior, not cosmetic implementation details.

## 7. Instructions and release packaging

- [ ] Write a short Quick Start with a first successful conversion and bootable export.
- [ ] Add a mode guide with examples, hardware requirements, apparent-color explanation, and recommended starting settings.
- [ ] Document every control, export format, and how to assemble ASM.
- [ ] Document how to boot a DSK or run a COM in MartyPC, select RGBI/composite, exit, and rerun.
- [ ] Explain 1/8/8 staggered, fixed staggering, and current hardware-testing limits in plain language.
- [ ] Document troubleshooting for blank output, incorrect colors, unsupported configurations, and conversion/export errors.
- [ ] Build the standalone Windows EXE from a clean environment; verify all profiles, templates, and help assets are bundled.
- [ ] Test on a Windows environment without Python, NASM, or the source checkout; include non-admin operation and paths with spaces/non-ASCII characters.
- [ ] Confirm startup time, representative conversion time, long-running conversion responsiveness, memory use, and repeated conversion/export reliability.
- [ ] Scan release contents for accidental local data, unnecessary artifacts, and missing licenses.
- [ ] Prepare versioned release notes, known limitations, sample outputs, reproducible build instructions, and SHA256 checksums.
- [ ] Download the staged release artifacts and verify their hashes and launch behavior.

## 8. Final signoff

- [ ] All retained mode/output matrix cells are Pass or justified N/A; no untested supported cells remain.
- [ ] No unresolved crash, wrong-output, data-loss, broken export, or misleading capability defect remains.
- [ ] Native visual review is completed for every supported mode/configuration.
- [ ] Tooltips, help, and GUI terminology agree with actual behavior.
- [ ] Remaining nonblocking limitations are documented and accepted together.
- [ ] Release candidate is tested from the exact packaged artifact intended for publication.
- [ ] Save a clean Git checkpoint, tag, publish release assets, and verify the public download.
- [ ] Archive the completed acceptance matrix and evidence with the release.

## How we will work through this

Recommended order: mode decisions → acceptance matrix and baseline failures → GUI/help and focused cleanup → complete export/emulator qualification → packaged release candidate → joint signoff.

Use this record for each acceptance case:

| Case ID | Mode / options | Input fixture | Output | Machine / display | Expected result | Actual / status | Evidence / hash | Issue / retest |
|---|---|---|---|---|---|---|---|---|
| Pending | | | | | | Not run | | |

Existing alpha.3 evidence is a useful baseline: 31 regression tests plus 59 subtests; separate aligned and staggered 44-case core suites; 12 GUI-option export cases per eight-write profile. These are historical results, not a completed acceptance matrix for all 13 modes or a new test run for this checklist.
