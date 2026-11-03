# Plan: language-boundary arms at small sizes (Grok r1 M5)

Status: plan, not frozen. It is frozen by a commit that sets this line to "frozen at <commit>", with the arms and the
analysis, after the build's sanitizer records and before the timed grid. Later changes go into a revision log at the
end, with reasons.

## Why

In the earlier campaign's lookup grid a C++ arm is compiled into the timing loop (v2 behind one out-of-line call), a
Rust arm is one call across a C interface per lookup, and a Go arm runs its timed passes inside Go. The times are raw.
Both cells where v2 is not faster than the fastest competitor are at m = 10, against gin. Grok asks for symmetric
boundary arms at small sizes and for lookup times net of each arm's own null. This run is exploratory: it decides
nothing, and its statistic and cells are fixed here before its data.

## Arms (one rbench build with `ablations.md`, one grid)

| Arm | What it measures |
|---|---|
| `regexmatcher-v2-capi` | v2 behind its own `extern "C"` translation unit, called once per lookup with the call shape of the Rust arms' C functions; the harness's 405 rule applies, as for the Rust arms |
| `capi-null` | an empty function behind the same `extern "C"` shape: the per-call cost of that boundary |
| `rust-null` | an empty Rust function behind the Rust arms' C interface: the per-call cost of the Rust boundary, which no arm measures today |
| `regexmatcher-v2-goloop` | v2 called from a Go loop, one Go-to-C call per lookup, in the Go arms' pass structure (paths copied into Go once, passes and a null pass in Go) |

and, in the same cells, the arms they are compared with: `regexmatcher-v2`, `null`, `null-no405`, `matchit`,
`actix-router`, `path-tree`, `gin`, `httprouter`, `nethttp`, `chi`, and the C++ arms that were the fastest competitor
of some small cell in the earlier campaign, `uwebsockets` and `glaze`.

- **Symmetric for Rust.** `regexmatcher-v2-capi` crosses the same kind of boundary, in the same direction, as the Rust
  arms; it is the symmetric arm. Its translation unit is compiled apart and the build has no link-time optimisation, so
  the call is not inlined.
- **No symmetric arm for Go.** A Go arm's lookups cross no boundary inside its timed pass. v2 called from a Go loop pays
  a Go-to-C call per lookup that no Go arm pays, so `regexmatcher-v2-goloop` shows what a Go program calling v2 would
  pay, and is labelled so; it is not a symmetric comparison. The comparison with the Go arms is made net of each
  language's own null (below).
- The existing C interface of the paper's server (`server/capi/p2v2.cpp`) is not reused: it serves GET only and
  returns no route for a 405.

## Cells and replicates

The seven shapes at m = 10 and m = 100 (14 cells), on the earlier campaign's sixteen seed pairs (table seeds 111 to
126, ring seeds 211 to 226): the small cells, where the boundary weighs most, on the tables that decide the lookup-time
claim. One process per arm, cell and pair, in the shuffled order of the shared grid (the seed 20261104). `regexmatcher-v2`
and `null` at these cells are the ablation grid's processes.

## Statistic (fixed now)

- **Symmetric comparison:** per cell, the ratio of `regexmatcher-v2-capi`'s lookup time to each Rust arm's and to the
  fastest of them, the median over pairs with the 95% BCa interval over pairs (`analysis/h1_stats.py`: clustered by
  table seed, 10,000 resamples, its resampling seed 20261010; the fastest is chosen again in every resample).
- **Net of each arm's own null:** every arm's time per lookup minus its own null's in the same pair: the C++ arms in
  the loop minus `null` or `null-no405` as the earlier campaign pairs them, `regexmatcher-v2-capi` minus `capi-null`,
  the Rust arms minus `rust-null`, and the Go arms and `regexmatcher-v2-goloop` minus their own null pass in Go. Per
  cell, the ratio of v2's net time to the fastest competitor's net time, with its interval as above. Raw times are
  reported beside. A ratio needs a positive net time: an arm whose net time is not positive in some pair, or whose
  null is not usable in every pair, is listed and left out of that cell's net comparison; if that arm has the lowest
  raw median of the competitors in the cell, or has no raw median to rank it by, the cell's net ratio is not computed.
  The number of cells with an arm left out is reported.
- **v2 in a Go loop:** per cell, the ratio of `regexmatcher-v2-goloop`'s time to each Go arm's, labelled as including
  the Go-to-C call.
- An arm takes part in a cell only if every one of its processes there is usable (`analysis/cells.py`); otherwise it
  is listed for that cell as absent or failing, with the reason, and every process that is not usable is listed.
- Exploratory: no hypothesis, no multiplicity adjustment, nothing decided. Nothing is dropped.

## Sanitizer records

A new Go or Rust file changes the compiled inputs of every Go and Rust arm (each language is one library digested over
all its files), so every Go and Rust arm needs new records, with the new arms: the record set of `README.md`, step 4
(clang ASan with UBSan and TSan for all; MSan for the C++ arms, the Go and Rust arms, `rust-null` and
`regexmatcher-v2-goloop` a declared gap as before). The Go arms are built with the pinned Go (`README.md`, "Toolchain
trap").

## Laptop hours

14 arms besides the ablation grid's in 14 cells, 16 pairs: 3,136 processes, 3,100 s to 14,300 s at round 2's 0.995 s
(small tables) to 4.565 s (the main grid's average) per process.
