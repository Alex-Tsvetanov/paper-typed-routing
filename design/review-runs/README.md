# Runs after the review (Alex, Q20261103-p2-2)

Alex's answer, verbatim: "P2-2: I approve the new runs." The question listed four runs, which Grok's round 1 asked
for (Papers `p2-typed-routing/reviews/grok-r1-review.md`): a floor rule fixed before a fresh whole-server run (M1a);
an adversarial benchmark of the lookup's backtracking (M3); ablations of the design choices and symmetric
language-boundary arms (M5). All four are planned here, one file each. None is dropped.

| Plan | Answers | Kind | Systems | New code | New sanitizer records |
|---|---|---|---|---|---|
| `floor-rerun.md` | M1a | the floor rule of round 3, frozen before a fresh run on a new seed pair | Linux, Windows | analysis only (`t3/`) and the new pair's request sets | none: the measured binaries are round 3's |
| `adversarial.md` | M3 | a deterministic check of the written bound; timing descriptive | Linux | one tool target in `bench/tools/` | the tool's |
| `ablations.md` | M5 | exploratory, pre-specified statistic and cells | Linux | renamed forks of v2's route headers as rbench arms | the new arms' |
| `boundary-arms.md` | M5 | exploratory, pre-specified statistic and cells | Linux | four rbench arms (C call, C null, Rust null, Go loop) | every Go and Rust arm's, and the new arms' |

The ablations and the boundary arms are built in one rbench build, gated by one record set and timed in one grid,
so every comparison is within one set of binaries (round 1's lesson: with a different arm set even the null arm moved
about 2.5%). The lookup-harness runs are on Linux only, as the earlier campaign's lookup grid was.

## Sequence

1. **The floor rerun's analysis code on the desktop**, with tests: the plan names and the seed pair in
   `t3/rr_results.py` and `t3/rr_macros.py` (today six fixed plan names and `t111`), the new plans, and the new pair's
   request sets with their manifest rows. Nothing under `bench/`, `server/` or the other paths of
   `t3/jobs/probe.py`'s `COMPILED` changes, so the round-3 binaries still pass the probe's guards.
2. **Freeze `floor-rerun.md`** (its status line names the commit), then the laptop runs it through the coordinator:
   Linux, then Windows.
3. **The lookup-harness code on the desktop**, with untimed tests: the adversarial tool, the ablation forks, the
   boundary arms. It changes `bench/`, which the probe of step 2's jobs guards, so it stays on its own branch until
   those jobs have run, and is merged after.
4. **Records** through the coordinator, on Linux: the pinned Go first (below), then one record set for the new rbench
   build and the tool.
5. **Freeze `adversarial.md`, `ablations.md` and `boundary-arms.md`** with their analysis code, each status line naming
   the commit, before any timed data. Records are not data.
6. **Timed jobs** through the coordinator, on Linux: the adversarial tool, then the grid of steps 3 to 5.
7. Analysis, generated macros, the pack, then the writer through the liaison.

## Laptop hours, from the records

Upper estimates; each comes from a named record of an earlier job.

| Step | System | Estimate | From |
|---|---|---|---|
| New pair's request sets, made and checked | Linux, Windows | at most 853 s and 2,034 s | round 3's bring-up on each system, which made all sixteen pairs' sets |
| Floor rerun: A/A run and campaign, one job | Linux, Windows | 788 s and 922 s | round 3's jobs (journal), the same plans but the pair |
| Floor rerun: k-server run | Linux, Windows | 564 s and 624 s | the same |
| Windows: start at least 15 min after boot | Windows | 900 s | `lab/laptop/README.md` |
| Pinned Go install (user-space, sha256) | Linux | minutes | the laptop's install policy |
| Record set: every rbench arm, the new arms and the tool | Linux | about 6,700 s, plus the new arms | the 25-arm set of f626955eb: 1,581 + 2,258 + 2,822 s |
| Adversarial tool, timed | Linux | about 5,400 s | 440 processes; one process per cell took 542 s on the desktop (planning run, `adversarial.md`) |
| Ablation and boundary grid | Linux | about 21,000 s, at most 32,200 s | 3,920 ablation processes at 4.565 s; 3,136 small-table processes at 0.995 s to 4.565 s |

In all: about 2 h for the floor rerun over both systems, and about 9.2 h (at most 12.3 h) on Linux for the lookup
harness, the new arms' share of the record set on top.

## Toolchain trap (blocks the rbench build)

`bench/cmake/pins.cmake` pins Go `go1.27.1-X:nodwarf5`, and `bench/cmake/arm-nethttp.cmake` stops the configure step
on any other Go. `STATE.md` records Go 1.27.3 on the laptop. The first laptop step of the lookup harness installs the
pinned Go as a user-space download checked by its sha256, under the laptop's install policy.
