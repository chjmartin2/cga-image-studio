# Fresh randomized Cheetara runs — October 8, 2026

The unchanged Phase 9 Cheetara COM was booted again in 20 fresh processes for each CGA clocking mode, with MartyPC's own PIT and CGA startup randomization enabled.

| CGA clocking | Exact randomized launches | Completed randomized frames |
|---|---:|---:|
| Default | 0/20 | 5,827 |
| Cycle | 20/20 | 5,873 |

One additional fixed PIT 9 / CGA 0 control per mode reproduced the difference: default failed and cycle passed. The total including both controls was 12,282 completed frames. These are actual core display-buffer comparisons through the headless observation harness, not desktop screenshots. Default-mode error patterns changed between launches; within each run the output was stable. Every tested cycle-mode frame matched the intended RGBI pixels exactly.

The development branch was checked live and still points to commit 6f9ac9c0ab643c371931bd8a993152c2598d9f42. No re-encoding or COM edits were made. SHA-256: 43e4aef4da292e43e91be10f3cbe20ccc021a073382deb336472088d13f99f4c. The main MartyPC executable is unchanged, and the previous run evidence was preserved.

These random samples do not exhaust the 192 PIT/CGA combinations and do not establish physical-hardware compatibility.

Actual rendered comparison sheets:

- [Default CGA](../../artifacts/marty-randomized-oct08-repeat/launch-comparison.png)
- [Cycle CGA](../../artifacts/marty-randomized-cycle-oct08-repeat/launch-comparison.png)

Per-launch phases, frame counts and hashes are in the adjacent JSON report. Raw traces are under external/research/marty-randomized/runs-oct08-repeat and runs-cycle-oct08-repeat.
