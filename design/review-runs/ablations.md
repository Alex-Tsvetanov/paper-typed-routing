# Plan: ablations of v2's design choices (Grok r1 M5)

Status: plan, not frozen. It is frozen by a commit that sets this line to "frozen at <commit>", with the arms and the
analysis, after the build's sanitizer records and before the timed grid. Later changes go into a revision log at the
end, with reasons.

## Why

The earlier campaign's only ablation arm (the round-1 header, renamed) measured almost the same lookup time as v2 in
every cell, so no design choice of v2 is tied to its speed. Grok asks for ablations of the choices: 8-byte keys,
hashed against linear edges, the exact-match table (and flat arrays). This run is exploratory: it decides nothing,
and its statistic and cells are fixed here before its data.

## Arms (one rbench build with `boundary-arms.md`, one grid)

Nothing in v2 at d1d73e99b can be switched by a compile flag (`kLinearEdges` is a constant in `route/table.hpp`, the
others are `inline constexpr`), so each variant is v2's route headers at d1d73e99b copied and renamed into its own
namespace under `bench/arms/ablation/`, as `route_r1.hpp` was, with one change:

| Arm | The one change |
|---|---|
| `regexmatcher-v2` | none: the pinned headers, as in the earlier campaign |
| `regexmatcher-v2-copy` | none: the renamed copy itself, the control for every variant |
| `regexmatcher-v2-ab-linear` | `kLinearEdges` above any node's edge count: every node searches its edges linearly |
| `regexmatcher-v2-ab-hashed` | `kLinearEdges` = 0: every node with edges is hashed |
| `regexmatcher-v2-ab-noexact` | the routes of an all-literal method stay in the trie instead of the exact-match table (the split in `table.hpp`) |
| `regexmatcher-v2-ab-bytes` | literal segments compared a byte at a time instead of in 8-byte words, in the walk and the edge search; storage, hashing and layout unchanged |
| `null` | the harness's null arm, for net instructions |

- **The 8-byte keys are ablated in their comparison only.** The word is stored in each edge and feeds the edge hash
  (five places in the table, the walk and the hash). Changing the storage would change the node layout and the hash
  together, so its effect could not be told apart from theirs. The byte arm removes the word comparison that every
  literal segment goes through.
- **Flat arrays are not ablated.** No switch exists, and the arrays are the table itself: another layout would rewrite
  the table and the lookup, which is another matcher, not one choice removed.
- **The copy control.** A copied header compiles to its own lookup function in its own translation unit. The control
  separates that from each change: every variant is compared with the copy first. `bench/objdump_check.sh` must find
  the copy's normalized lookup code equal to the pinned arm's.
- **Correctness.** Every variant must pass the behavioural probes and agree with the semantics file on every query of
  every process, as the earlier campaign's arms did; a variant that fails is reported and not timed.

## Cells and replicates

The earlier campaign's grid: the seven shapes at m = 10, 100, 1,000, 10,000 and 100,000 (35 cells), on its sixteen
seed pairs (table seeds 111 to 126, ring seeds 211 to 226), one process per arm, cell and pair, in a shuffled order
with a fixed seed. These are the cells that decide the lookup-time claim, on the same tables.

## Statistic (fixed now)

- Per cell and variant, the ratio of the variant's lookup time to the copy's, and to the pinned arm's: the median over
  the pairs of the per-pair ratio, with the 95% BCa interval over pairs, as the earlier campaign's lookup-time analysis
  computes it (`analysis/h1_stats.py`).
- Beside it, net instructions per lookup (net of `null`) and branch misses per lookup, as its work-per-lookup analysis
  computes them, and each arm's normalized lookup code size. Editing the walk recompiles the whole lookup function
  (round 2's engineering builds: 1,039 lines became 1,154 and 1,293), so a time difference can come from code layout as
  well as from the change; the instruction counts and code sizes are reported so that a reader can see it.
- Exploratory: no hypothesis, no multiplicity adjustment, nothing decided. Nothing is dropped.

## Sanitizer records

The new arm targets, with the record set of `README.md`, step 4 (clang ASan with UBSan, TSan and MSan on Linux).

## Laptop hours

7 arms, 35 cells, 16 pairs: 3,920 processes, about 17,900 s at round 2's 4.565 s per process.
