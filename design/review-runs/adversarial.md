# Plan: an adversarial benchmark of v2's backtracking (Grok r1 M3)

Status: plan, not frozen. It is frozen by a commit that sets this line to "frozen at <commit>", with the tool and its
analysis, after the tool's sanitizer records and before its timed job. Later changes go into a revision log at the
end, with reasons.

## Why

The pack states the worst case of v2's lookup from its code (Papers `p2-typed-routing/writing/method.md`, "The
matcher's lookup, read from its code"): the trie is a tree, one walk enters each node at most once and resumes at a
node at most once after each kind of child, and a request that finds no route under its own method also walks the
trie of every other method that has routes. No measurement of the worst case exists: the grid's decoy queries
backtrack one choice point deep, and the harness's backtrack counts come from a model of the walk. Grok asks for an
adversarial benchmark (nested choice points, failing at the last segment) and the largest number of backtracks per
query.

## What is measured, and with what

- **v2 at d1d73e99b, unmodified**, timed. The pinned headers, as every v2 arm builds them.
- **A counting copy**, untimed: v2's route headers at d1d73e99b copied and renamed (as `bench/arms/ablation/route_r1.hpp`
  was), with counters added to the walk: node entries, resumptions per node, choice points pushed and popped, and the
  deepest choice stack. A test checks that it returns the same answer as the pinned code on every query of every
  table here. The hook `MATCHER_ROUTE_ON_BACKTRACK` of round 2's engineering builds is not in d1d73e99b, so it cannot
  be used.
- **One new tool target**, `bench/tools/adversarial`, which uses `bench/core`'s timing loop without changing it. A
  change in `bench/core` would change every arm's compiled inputs and void every rbench record; a separate target
  needs only its own records. rbench's own routes cannot express typed parameters and stop at 8 parameters, so the
  tool builds v2's tables directly, up to v2's limits (16 parameters, 32 segments).

## Tables and queries (no seeds: every table is fixed by its family and depth)

- **Two kinds per node, depth k = 1, 2, 4, 8, 12, 16.** Every route has k segments, each either the literal `a` or a
  plain parameter, then one last literal segment: all 2^k combinations, so every node on a path of `a` segments has a
  literal and a parameter child (2^16 = 65,536 routes at k = 16).
- **Four kinds per node, depth k = 1, 2, 4, 6, 8.** Each of the k segments is the literal `1`, an unsigned integer, a
  signed integer or a plain parameter: all 4^k combinations (65,536 routes at k = 8). A segment `1` matches all four,
  so every node is a choice point of four branches, and the unsigned child is tried before the signed one.
- **The same tables with one catch-all route at the root**, so a walk that fails everywhere ends in the catch-all.
- Every table is registered under GET and under PUT.
- **Queries, one per cell:**
  - *miss*: k segments of `a` (or `1`) and then a last segment no route has, under GET. The walk enters every node of
    GET's trie and finds nothing; the lookup then walks PUT's trie for the allowed methods, as for a 405. With the
    catch-all, GET's walk ends in the catch-all and no other trie is walked.
  - *last hit*: the same path ending in the last segment that only the all-parameter route has (in this table family
    every other route ends in another literal), under GET. The walk enters every node before the last branch matches.
  - *other method*: the miss path under DELETE, which has no routes. The lookup finds nothing under DELETE and walks
    GET's and PUT's tries for the allowed methods. It walks the same tries as *miss*, so the two queries' counts are
    equal by design; the times are reported for both.
- Cells: 11 tables with three queries and 11 catch-all tables with the miss query: 44 cells.

## Procedure

As rbench times a cell (`bench/core/runner.hpp`, with rbench's default options): one process per cell and replicate
on CPU 2, a ring of 4,096 copies of the cell's query (rbench's ring size), 21 epochs after one warm-up, at least 5 ms
per epoch, the median ns per lookup over epochs; a pass over a slow cell's ring is cut to a prefix, as rbench cuts a
slow arm's. 10 processes per cell, in an order shuffled with the seed 20261103. The ring repeats one query, so the branch predictor sees the same walk
every time: the times are those of a learned walk, not of a cold one. The counts are exact and do not depend on it.

## What is decided, and what is reported

- **Decided, deterministically: the written bound holds.** For every query, the node entries are at most the number
  of nodes of the tries the lookup walks, and the resumptions at each node are at most four. The counting copy's
  answers equal the pinned code's on every query. If either fails, the paper's code-read bound is wrong, and the
  paper says so.
- **Reported, descriptive:** per cell, the node entries, the choice points pushed and popped (the backtracks), the
  deepest choice stack, and the median over processes of the median ns per lookup with its range; the largest number
  of backtracks per query over all cells; the time per node entered.
- Nothing is dropped: every cell's processes are reported, including any that fail.
- Competitors are not run: the question is v2's own worst case, and other routers' worst cases are not claimed.

## Sanitizer records

The tool target (both the pinned and the counting builds) under clang ASan with UBSan, TSan and MSan on Linux, made
with the record set of `README.md`, step 4.

## Laptop hours

440 processes, about 5,400 s: one process of each of the 44 cells took 542 s in all on the desktop (a planning run
of the built tool, untimed for any result, other work running beside it), the largest 61 s (`two-k16-other-method`);
the k = 16 and four-kinds k = 8 cells are most of it, because the agreement pass checks every copy of the ring.
Round 2's 4.565 s per process, the first estimate, was too low for these tables.
