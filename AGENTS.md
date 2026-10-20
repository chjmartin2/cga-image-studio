# CGA Image Studio agent instructions

## Master repository

This Source folder is the owner-designated master checkout. Preserve the original folders elsewhere on the computer. Read ../AGENTS.md and ../Notes/MIGRATION.md for the archive boundaries and import evidence.

## Repository layout

Current application modules, the two primary launchers and build configuration
remain in the root. Historical application snapshots, root-level experiments,
assembly exports and reference code are preserved under `Old Storage`; consult
its `README.md` and `move-manifest.json` before restoring or relocating them.
Do not delete archived material as a cleanup step.

Use `tools/run_archived.py` for historical Python scripts and
`tools/launchers/` for the current diagnostic/emulator shortcuts. The
`Old Storage/local-work/` folder contains local-only one-off scripts and must
remain ignored. Keep current runtime assets, fixtures, toolchains and generated
release/demo artifacts at their established paths.

## RetroComputerist website updates

Whenever the owner requests a GitHub push or software release, read and follow the current workflow at:

`D:\RetroComputerist\Website\PROJECT-UPDATE-WORKFLOW.md`

Website project ID: `cga-image-studio`. Website repository: `D:\RetroComputerist\Website`. Read the workflow fresh and follow its linked instructions. Keep detailed website requirements there, not duplicated here. Prepare and validate any useful website draft; report blockers. Code push/release authorization does not automatically approve website publication. Do not edit the superseded website checkout under .codex.

Do not add private sibling folders, original release ZIPs, third-party bundles or unreviewed samples to GitHub as part of a routine push.
