# Round 2 engineering: targets, causes, adoption rules

Status: design for review, round 2 of P2, phase 1. Nothing here is implemented. Written
2026-09-30. Once Alex approves it, this note is frozen and later changes go into a revision
log at its end.

Words: "the round-1 header", "the private library", "v1" and "v2" as in
`regexmatcher-v2.md`. "The run-time arm" and "the compile-time arm" are round 1's two arms
of the table (the table built by `build_table`, and the table built while compiling), both
calling one out-of-line lookup, `find_v2`.

Three targets, each with the round-1 facts, profiling data gathered today, a hypothesis
about the cause, the proposed changes, and an adoption rule declared before anything is
measured. Correctness stays exactly as in round 1 (section 4).

## 0. Where the numbers come from

- **Round 1, lab host L** (Ryzen 7 5800H, Zen 3, clang 22.1.8): `results/tab_h2.csv`,
  `tab_h4.csv`, `tab_h7.csv`, `sens_h7.csv`, and the raw main grid
  `D:\Archive\p2-raw\p2-raw-2026-09-27-L-publication.tar.gz` (sha256
  1aed9e0d86495cf50ad7e286f2aaefdcf0dedc1a719dcaffc9e12beea71bba10, checked today),
  `cells.jsonl`.
- **Today, W in WSL**: Ubuntu 24.04 under WSL2 (kernel 6.6.114.1) on W (Ryzen 5 3600, Zen 2),
  clang 18.1.3, `-O3 -DNDEBUG -std=c++23 -fsized-deallocation`, the flags of round 1's arms
  plus the one clang 18 needs (`regexmatcher-v2.md`, step E2). The drivers compile the
  round-1 header (or a scratch copy of it with timing marks) and rbench's table and ring
  generator (`bench/core/table.cpp`, `route.cpp`, `sha256.cpp`, `github_api.cpp`)
  unchanged. They are scratch files of this session, not committed:
  - `prof_build`: the run-time arm's build as rbench drives it (`add()` renders each route
    and pushes it, `finalize()` builds), with a mark at each phase of `build_table` and every
    `operator new` counted; median of 5 builds, table seed 1;
  - `prof_insn`: exact user-space instruction counts, by single-stepping a child process with
    `ptrace` through one pass of the run-time arm's adapter over a ring (4,096 lookups),
    each instruction mapped to its function;
  - `prof_ct`: lookup time of the same table in several places (section 3).

Different CPU, different compiler, a hypervisor: times from WSL are compared only with
times from the same process or host. Instruction and allocation counts transfer across
hosts, but not exactly across compilers (clang 18 against 22). Nothing from WSL is a
result; round 2 measures everything again on L.

## 1. Target (a): build time at m >= 1,000

### 1.1 Round 1

H4 failed: the run-time arm's build was slower than the median competitor's in 20 of 35
cells, all seven shapes at m = 1,000 and 10,000 and six at 100,000 (wild holds there)
(`tab_h4.csv`). Ratios of v2's median build time to the median competitor's:

| m | static | param-last | param-first | rest | wild | mixed-disjoint | mixed-overlap |
|---|---|---|---|---|---|---|---|
| 1,000 | 2.21 | 1.55 | 2.40 | 1.16 | 1.87 | 1.57 | 1.25 |
| 10,000 | 2.13 | 1.21 | 1.96 | 1.12 | 1.37 | 1.29 | 1.09 |
| 100,000 | 1.50 | 1.27 | 1.55 | 1.12 | 0.91 | 1.14 | 1.17 |

The build time rbench records is the wall time of all `add()` calls plus `finalize()`
(`bench/core/runner.hpp`), so it includes the arm's own work of rendering each route into a
pattern string.

### 1.2 Profile (WSL, clang 18.1.3, table seed 1, median of 5 builds, microseconds)

| Shape, m | total | `add()` | parse into entries | split | sort and duplicate check | exact-match table | trie |
|---|---|---|---|---|---|---|---|
| static, 1,000 | 1,308.7 | 92.5 | 150.3 | 577.6 | 337.0 | 35.1 | 0.0 |
| param-first, 1,000 | 1,217.3 | 80.6 | 100.3 | 586.3 | 331.6 | 0.0 | 76.1 |
| rest, 1,000 | 1,523.6 | 90.1 | 366.0 | 630.3 | 317.2 | 0.0 | 89.9 |
| mixed-disjoint, 1,000 | 1,493.5 | 95.3 | 365.6 | 621.9 | 290.8 | 0.0 | 92.0 |
| static, 10,000 | 23,236.9 | 1,145.9 | 4,780.3 | 11,230.2 | 5,211.1 | 800.3 | 0.1 |
| param-first, 10,000 | 22,527.7 | 844.6 | 4,563.3 | 10,482.9 | 5,136.6 | 0.1 | 815.7 |
| rest, 10,000 | 19,511.6 | 943.7 | 3,269.4 | 9,357.7 | 4,772.9 | 0.0 | 1,022.8 |
| mixed-disjoint, 10,000 | 19,403.6 | 935.9 | 3,828.8 | 9,044.1 | 4,326.8 | 0.1 | 921.5 |
| static, 100,000 | 318,810.6 | 13,306.1 | 51,057.3 | 94,620.4 | 118,433.3 | 16,391.7 | 0.1 |
| param-first, 100,000 | 291,484.3 | 12,482.3 | 45,829.8 | 86,455.6 | 114,053.3 | 0.1 | 15,358.5 |
| rest, 100,000 | 324,407.1 | 13,104.4 | 51,071.2 | 109,900.6 | 118,515.4 | 0.0 | 23,247.6 |
| mixed-disjoint, 100,000 | 323,867.9 | 13,788.7 | 52,166.8 | 107,013.1 | 106,270.6 | 0.1 | 19,244.8 |

"Parse into entries" is the loop that parses every pattern into the build's entry type and
appends it to a vector; "split" moves each entry into the list of exact-match methods or of
trie methods; "sort" sorts each list by value. The three together took 81.4% to 91.3% of
the build in every row. The harness's `add()` took 3.7% to 7.1%; the trie took at most 7.2%.

Why, from `sizeof` and the allocation counter:
- the build's entry holds a parsed pattern, which holds a fixed array of 32 segments of
  24 bytes: `sizeof(Pattern)` is 784 and `sizeof(Entry)` is 800 bytes, whatever the route's
  length (the benchmark's routes have 3 to 5 segments);
- the parse step reserves one vector of entries: 800,000 bytes at m = 1,000;
- the split pushes entries into two vectors that are not reserved: 11 allocations and
  1,637,600 bytes at m = 1,000; 18 and 209,714,400 bytes at 100,000;
- the sort moves 800-byte entries in place (0 allocations);
- the trie phase made 241 allocations for 1,034 nodes (param-first, 1,000) and 50,387 for
  145,894 nodes (mixed-disjoint, 100,000): the growth of the node, edge and arena vectors,
  and a vector of literal groups in each node that has literal children.

The compile-time table is built by the same `build_table` during constant evaluation, so the
same copies cost constant-evaluation steps there (clang needs more than 8,388,608 and at most
16,777,216 steps for a 1,000-route table, `results/README.md`), and compiler memory (MSVC
peaked at 7.4 GB on one 1,000-route table in round 1, `design/router-v2.md`).

### 1.3 Hypothesis (a)

H4 is lost to the bookkeeping of the build, not to the table: copying and sorting a fixed
800-byte entry per route. If the three entry phases cost nothing, the WSL build would take
8.7% to 18.6% of its current time (the remainder in the table's rows). That bounds what the
change can remove on that host; it is not a projected result.

### 1.4 Changes

- **A1, compact entries.** Parse every pattern into one shared array of segment records
  (kind, type, and the offset and length of the text inside the route's pattern string),
  holding only the segments a pattern has. An entry becomes method, route, spec index, first
  segment and segment count.
- **A2, sort indices.** Sort 32-bit indices of entries with the same comparison; split into
  exact-match methods and trie methods by index, without copies.
- **A3, no allocation per node.** One scratch stack for the literal groups of the node being
  built; nodes, edges and arena reserved from counts known after the sort.
- **A4, the harness's `add()` stays.** Rendering a pattern string is how the library is used;
  it is 3.7% to 7.1% of the build here.

Invariant: the table the build produces (nodes, edges, exact-match slots, arena, roots, the
method bit sets) is byte-identical to the round-1 header's for the same routes. The lookup
therefore cannot change through the table, and the compile-time tables are the same objects.

### 1.5 Adoption rule (a), declared before measuring

1. **Deterministic, in WSL or on L.**
   - Byte-identical tables for every shape at m = 10, 100, 1,000, 10,000 and 100,000 at
     table seed 1, and for the GitHub table. A new rbench subcommand, `table-digest`, prints
     the sha256 of a table's arrays; it runs against the round-1 header and against v2.
   - Allocations per build (rbench's `build_allocs`) and bytes allocated per build (a new
     field, `build_alloc_bytes`) both fall in every shape at m >= 1,000.
   - The lookup's machine code is unchanged (the objdump check of `regexmatcher-v2.md`,
     section 9).
   - The clang constant-evaluation budget of every table (`bench/ct_steps.py`) does not
     rise.
2. **Time, only if 1 holds.** A and B are two rbench binaries built with the same arms (every
   arm, so that the two binaries differ only in v2's code); only v2's arm runs from each.
   Every shape at m = 1,000, 10,000 and 100,000, at least 10 processes per build, alternating
   A B B A, engineering seeds only. Adopted if, in every cell, the median over processes of
   `build_s_median` is lower in B. The goal is to fall below the round-1 median competitor
   of each cell (the table in 1.1), but the rule does not depend on it: whether H4 holds is
   decided by round 2's run, and a miss is reported.

## 2. Target (b): H2 at mixed-disjoint, m = 10

### 2.1 Round 1

H2 was lost in 1 of 35 cells: at mixed-disjoint m = 10 the run-time arm ran 510.6 net
instructions per lookup (median over the ten pairs; range 500.7 to 514.0) against gin's
480.5 (448.0 to 501.6), while running faster than gin in every pair (`tab_h2.csv`; per
pair, 46.4 to 48.7 ns against 50.6 to 56.1 ns, `cells.jsonl`). Per pair, v2's net count is
above gin's by 0.8 (pair 102:201) to 61.0 (105:201); gin's count varies with the table.

Attempts during round 1 (revision log of `hypotheses.md`, lab journal):
- hashed edges above 4 children instead of 8: no change (517.5 against 518.0);
- the walk always inlined into the lookup: 8 fewer raw instructions at one pair; the loss
  stayed;
- path compression (a chain of single-child literal nodes as one edge): the cell went to
  442.7 net against gin's 498.0, but 28 cells of the H1 iteration grid were more than 2%
  slower, most with 6 to 16 more net instructions per lookup, 14 to 16 on rest, which has no
  chain to merge. The extra instructions were the test, at every literal step, of whether
  the edge is chained. Rejected.

### 2.2 Profile (WSL, clang 18.1.3, the five table and ring seed pairs 101:201 to 105:202)

Instructions per lookup, one pass of 4,096 lookups through the run-time arm's adapter
(`find_v2` out of line, the captured values copied into rbench's capture struct, the
harness's fold):

| Part | Instructions per lookup |
|---|---|
| the trie walk | 426.8 to 437.8 |
| `find_v2` (the result's fields set, the method and path checked, the 405 branch) | 41.0 |
| `find_in` (the exact-match test, the method's root) | 23.0 |
| the harness loop with the adapter's capture copy and the fold | 63.3 to 63.8 |
| total | 554.7 to 565.2 |
| the null arm (loop 26.0, its lookup 4.0) | 30.0 |

So 524.7 to 535.2 net here, against 500.7 to 514.0 on L with clang 22.1.8: the counts are
close, not equal, across compilers.

Per query class (the route the query targets), mean instructions per lookup:

| Target route | pair 101:201 | range over the five pairs |
|---|---|---|
| `/a/l/l`, fully literal | 447.1 | 440.2 to 476.0 |
| `/b/r/{p0}` | 524.0 | 503.9 to 524.0 |
| `/b/r/{p0}/s` | 619.6 | 598.2 to 619.6 |
| `/b/r/{p0}/s/{p1}` | 757.0 | 737.6 to 757.0 |

One more literal segment (`/b/r/{p0}` to `/b/r/{p0}/s`) cost 91.5 to 103.2 instructions,
one more parameter segment 136.6 to 139.4, over the five pairs.

The adapter's copy of the captured values into rbench's struct and the fold over them are in
v2's net count, as every C++-called arm's own copy is in its count. gin folds its parameters
inside Go and its null pass does not. Changing that would change the harness for every arm,
so this design does not propose it. If Alex wants it, it goes into the pre-specification as a
declared harness change.

How gin walks (`bench/arms/go/gin/tree.go`, `getValue`, vendored unchanged): each node
compares its whole prefix with one string comparison (`path[:len(prefix)] == prefix`), which
can span several segments, then scans a string of first bytes to pick the child; a
parameter's end is found by a byte loop. In a mixed-disjoint table of 10 routes, the literal
tail under a top-level word, and `r` under `b` in a group, are runs of single-child nodes.
gin compares such a run at once; v2 takes one full trie step per segment, about 92 to 103
instructions each in the profile above.

### 2.3 Hypothesis (b)

The loss is v2's per-segment step on runs of single-child literal segments. Round 1's path
compression is the evidence that the mechanism is right: it removed the loss. Its
regressions came from where the chain test sat (every literal edge of every node), not from
compressing chains.

### 2.4 Changes

- **B1, chains only where there are chains.** A node's edge scan already has a kind chosen at
  build time (linear up to 8 literal children, hashed above). A third kind, "linear with
  chained edges", is given only to a node that has at least one chained edge. Nodes of the
  other two kinds run round 1's code; the chain's tail compare and its advance of the path
  position are inside the third kind's branch only. The chain's tail length goes into the
  4 bytes of padding that `Edge` already has (8 + 4 + 4 + 4 bytes in a 24-byte struct), so a
  table without chains is byte-identical to round 1's.
- **B1', the alternative, if B1 still costs where there are no chains.** A chain becomes a
  node of its own kind with no edges and no parameter children. The walk reaches its test
  only where a node found nothing, which on an all-hit ring happens at chain nodes only.
- **B2, lower priority.** The fixed cost before the first segment (`find_v2`, `find_in` and
  the walk's entry together; round 1's inlining attempt removed 8 of it).

Which of B1 and B1' is built is decided by the rule below, B1 first.

### 2.5 Adoption rule (b), declared before measuring

1. **Deterministic: instructions per lookup, net of the null arm,** A and B built with the
   same arms, every shape at m = 10 to 100,000, engineering pairs (table seed 1, ring seeds 2
   and 3), the adapter and the harness unchanged:
   - in every cell whose table has no chained edge, B runs no more instructions per lookup
     than A (a rise of 0.5 or more fails; round 1's counts reproduced to a median absolute
     percentage error near 1e-8);
   - in no cell does B run more;
   - at mixed-disjoint m = 10, B's net count is below gin's in both engineering pairs.
   On L with clang 22.1.8 and hardware counters when L is free; before that, in WSL with the
   single-step counter and clang 18.1.3, stated as such.
2. **Time, only if 1 holds.** All 35 cells of H1, A and B built with the same arms (every
   arm), v2's arm and the null arm run from each, at least 10 processes per build and cell,
   alternating A B B A, on L (about 1,400 processes, so about 2 h 12 min at round 1's average
   of 5.65 s per process). Rejected if any cell's median over processes of B's time divided by
   A's exceeds 1.01. In round 1 a null arm ran about 2.5% slower in a binary built with other
   arms (lab journal, path compression), which is why both binaries hold every arm.
3. **Correctness:** R1 to R18, CT and NEG pass; the probes pass; answers agree with
   `bench/semantics.json`; rbench's model of the backtracking walk matches a counting build of
   B on every table, as round 1 checked it.

## 3. Target (c): H7 at param-first, m = 1,000

### 3.1 Round 1

The compile-time table was not slower by more than 2% in any of the 21 cells: at
param-first m = 1,000 the ratio was 1.0032 with the BCa interval [1.0023, 1.0140]
(`tab_h7.csv`). The bootstrap clustered by table seed, run after the freeze, gave
[1.0026, 1.0249], above the margin; 8 of 10 pairs were below 1.02, the exact sign test's p was
0.0547, and the largest pair ratio 1.0297 (`sens_h7.csv`).

Per pair (`cells.jsonl`; compile-time arm against run-time arm):

| Pair | Time ratio | Instructions | Cycles | L1d misses | DTLB misses |
|---|---|---|---|---|---|
| 101:201 | 1.0006 | 510.0 / 511.0 | 153.4 / 153.4 | 1.071 / 3.406 | 0.0181 / 0.0186 |
| 101:203 | 1.0068 | 510.0 / 511.0 | 154.8 / 153.8 | 1.020 / 3.407 | 0.0181 / 0.0182 |
| 102:201 | 1.0030 | 511.1 / 512.1 | 154.1 / 153.7 | 1.054 / 3.432 | 0.0177 / 0.0185 |
| 102:202 | 1.0029 | 510.5 / 511.5 | 153.7 / 153.3 | 1.043 / 3.442 | 0.0179 / 0.0181 |
| 103:202 | 1.0034 | 508.7 / 509.7 | 153.5 / 153.0 | 1.366 / 3.424 | 0.0179 / 0.0184 |
| 103:203 | 1.0040 | 509.6 / 510.6 | 154.5 / 154.0 | 1.028 / 3.463 | 0.0178 / 0.0181 |
| 104:201 | 1.0297 | 511.9 / 512.9 | 159.9 / 155.2 | 1.501 / 3.395 | 0.0179 / 0.0182 |
| 104:203 | 1.0249 | 513.3 / 514.3 | 161.0 / 157.1 | 1.039 / 3.406 | 0.0179 / 0.0181 |
| 105:201 | 1.0021 | 513.5 / 514.5 | 157.3 / 157.0 | 1.039 / 3.450 | 0.0180 / 0.0183 |
| 105:202 | 1.0026 | 513.0 / 514.0 | 156.8 / 156.5 | 1.039 / 3.421 | 0.0186 / 0.0183 |

What this rules out, on L: instructions (the compile-time arm runs exactly one fewer per
lookup in every pair), L1d misses (it has about a third of the run-time arm's), DTLB misses
(equal), branch misses (within 0.05 per lookup in every pair). The two slow pairs are both
table seed 104, with 3.9 to 4.7 more cycles per lookup; no single dispatch-stall bit
accounts for them.

Two structural differences between the arms:
- **the adapters.** The two arms are two adapter classes around the same `find_v2`; the one
  instruction per lookup between them is theirs;
- **the layout.** The compile-time table's arrays are contiguous in one object whose address
  is fixed at link time, so its page offset is the same in every process of one binary. The
  run-time table's four arrays are four heap allocations, placed by the heap's state. In one
  process in WSL today their page offsets were nodes 2,816, edges 2,752, arena 1,984; the
  compile-time table's were 1,984, 2,304 and 3,392. That the run-time arm has three times
  the L1d misses on L fits arrays whose hot first lines fall into the same cache sets.

### 3.2 Profile (WSL, clang 18.1.3)

`prof_ct` holds, in one process, the same param-first 1,000-route table three ways: built at
run time; the compile-time table of `bench/gen` (compiled with clang 18.1.3 at a budget of
33,554,432 steps); and the compile-time table's bytes copied, in its own layout, into a
page-aligned heap block starting at 0, 512, ..., 3,584 bytes into a page (8 offsets). All
ten variants are timed through one out-of-line `find_v2`, in 42 rotating epochs of 20 passes
over the ring (the first epoch dropped), and each process reports each variant's median.
60 processes: table seeds 101 to 105 by ring seeds 201 to 203, four times.

- Compile-time over run-time: median 1.0008 over the 60 processes, range 0.9916 to 1.0139;
  per table seed, medians 0.9994 (104) to 1.0023.
- The same bytes at 8 page offsets, over run-time: means 1.0001 to 1.0020 per offset, no
  offset slower across processes. Within one process the 8 offsets spread by a median factor
  of 1.0098 (at most 1.0289), which is the noise of one measurement.

On Zen 2 under WSL, where the table lies does not move the lookup by more than that noise,
and table seed 104 is not slower. W is a different microarchitecture and a different binary
(the compile-time tables sit at other addresses than in L's binary), so this does not refute
an effect on L; it shows the effect is not a property of the lookup's code.

### 3.3 Hypothesis (c)

The crossing at param-first m = 1,000 comes from two things together: a small placement
effect on L that is fixed per binary and table (the compile-time table's address, and so its
cache sets, are set at link time; the run-time table's four arrays fall elsewhere), and a
design with five clusters of two pairs, where one table seed with two slow pairs moves the
clustered interval. It is not the lookup, which is one function for both arms.

### 3.4 Changes

- **C1, one adapter.** Both arms become one adapter class template that differs only in where
  its table view comes from. The objdump of the two instantiations' lookup is compared and
  must be identical.
- **C2, one layout.** The run-time table owns one page-aligned block holding nodes, edges,
  exact-match slots and arena at exactly the offsets the compile-time table uses, and the
  compile-time table is aligned to 4,096 bytes. Every element then has the same page offset
  in both arms; what remains is heap memory against memory of the binary. Each cell records
  the page offsets of the four arrays (new fields). The table's contents do not change.
  Exact-size storage can only lower H4's heap bytes; that is checked (section 4).
- **C3, the design.** More table seeds in round 2, so the clustered bootstrap has more
  clusters (`hypotheses-v2-proposal.md`).

If the effect appears again, at another table seed, in round 2's run: H7 is decided by the
frozen rule of the proposal, nothing is dropped or run again, the cell is reported with its
counters, and one exploratory run follows: the compile-time table copied into a heap block in
the same binary, as in 3.2, to separate the table's placement from its content.

### 3.5 Adoption rule (c), declared before measuring

C1 and C2 are adopted on deterministic evidence: identical lookup code of the two
instantiations (objdump); equal recorded page offsets for the two arms in every cell; tables
byte-identical to round 1's contents (`table-digest`); `find_v2` unchanged. Then one H7
iteration check on L (the 21 cells, engineering seeds, at least 10 processes per arm, both
arms in one binary, as H7 is run): no cell whose median ratio exceeds 1.02. If a cell does,
C2 is still adopted (it removes a known difference), and the cell goes to Alex before the
pre-specification is frozen.

## 4. What stays exactly as in round 1

- The path semantics, rules 1 to 7 of `design/router-v2.md` (rule 8, HEAD, moves to the
  server).
- The probes of `bench/core/probe.cpp`, run on every arm; the agreement of every process's
  answers with `bench/semantics.json` at every size; the check of rbench's backtracking
  model against a counting build.
- H3: no heap allocation per lookup, captured values included.
- The compile-time checks: every case of the NEG list (`regexmatcher-v2.md`, section 6),
  each a CTest entry with `WILL_FAIL` and a check of the diagnostic.
- The compile-time table's costs reported with H7: compile time and object size per table,
  and clang's budget per table.

Every change runs v2's whole suite (R1 to R18, CT, NEG, NEW) before anything is timed, and
H4's heap bytes of every cell of the engineering grid are compared before and after (they
must not rise).

## 5. Order, tools, and what is not attempted

Order: E1 and E2 (extraction, `regexmatcher-v2.md`); C1 (harness); A1 to A3; C2; B1 (or B1');
B2 last and only if time allows. The build and layout changes come before the one change to
the lookup's code, so each piece of instruction evidence is about one change.

Tools added to the paper repository for this: rbench `table-digest`; the fields
`build_alloc_bytes` and the four page offsets; and a single-step instruction counter for
WSL, `bench/tools/stepcount` (the scratch `prof_insn` made into a tool), so that instruction
evidence does not wait for L.

Not attempted in round 2: path compression in hashed nodes, perfect hashing for
compile-time tables, SIMD segment scans.

## Revision log

- 2026-09-30: first version, for review.
- 2026-09-30, approved. The single-step counter becomes a tool of the paper repository later,
  not in this round's first steps (section 5); until then it stays a scratch driver and its
  output is development evidence only. The exploratory ablation arm (`hypotheses-v2-proposal.md`,
  section 3.1) is the E1 state and does not change any adoption rule here.
- 2026-09-30, second milestone (development, WSL on W, not pinned; the evidence is in the
  Papers repository, `lab/evidence/2026-09-30-W-regexmatcher-v2-build-rework`). A1 to A3 are in
  RegexMatcher 39f3e48 as section 1.4 describes; one change came after: the build reserves its
  array of segments from the number of '/' in all patterns (f48fa83), because at 39f3e48 the
  static shape made one allocation more than before at every size (table seed 1), which rule 1
  forbids. Rule 1 of target (a), clause by clause, with clang 18.1.3:
  1. `table-digest` is a tool of its own, `bench/tools/table_digest`, not an rbench
     subcommand. The paper's code may not include the round-1 header, so round 1's tables are
     those of E1 (00a2053), the round-1 header renamed, whose lookup the objdump check shows
     identical. At table seeds 1, 2 and 3, all 36 tables (every shape at the five sizes, and
     the GitHub table) have equal digests and array sizes at E1, before the rework (53e8dda)
     and after it (f48fa83): 108 of 108.
  2. The build's allocations and allocated bytes both fall from 53e8dda to f48fa83 in all 36
     tables at each seed, m = 10 and 100 included. At seed 1, mixed-disjoint m = 100,000 goes
     from 50,406 allocations and 328,421,472 bytes to 61 and 47,195,216.
  3. The objdump check at f48fa83 is identical with clang 18.1.3 and gcc 14.2.
  4. `bench/ct_steps.py` puts all 21 compile-time tables of table seed 1 and the GitHub table
     in the same band at 53e8dda and at f48fa83. The tool resolves a factor of 2, so a rise
     inside a band would not show.
  Rule 1 therefore holds in WSL; clang 22.1.8 on L repeats the objdump check (the first L
  slot, `bench/jobs/slot1.sh`), and rule 2 comes next on L. RegexMatcher's whole suite passes
  81 of 81 at f48fa83 with clang 18.1.3 and gcc 14.2 (section 4). Development timing, not rule
  2 (3 processes per arm, the ablation arm and v2 in one binary, 12 cells at m >= 1,000): v2's
  median build time is 0.349 to 0.571 times the ablation arm's, with equal table bytes and
  equal instructions per lookup in every cell. Section 4's comparison of H4's heap bytes
  covers 17 of the engineering grid's 35 cells so far (these 12, and static, wild and
  mixed-overlap at m = 10 and 1,000 in a dry run of the harness), all equal; the other cells
  are compared on L before the freeze.
  C1 is in the harness: one adapter template (`bench/arms/rm_arm.hpp`) for the run-time and
  compile-time arms. Its deterministic part holds in WSL: the measured loop, `harness_pass`,
  is the same machine code in both arms (241 instructions); the functions that build or bind
  the table differ, as they must. The page offsets of the four arrays are recorded per cell
  (`table_layout`); C2 and the H7 iteration check follow.
- 2026-09-30, C2 (RegexMatcher 45ab696, paper 4dd16b7; development, WSL on W, not pinned;
  evidence in the Papers repository, `lab/evidence/2026-09-30-W-regexmatcher-v2-c2-layout`).
  The run-time table is now a `RuntimeTable`: `build_table`'s table copied into one block
  aligned to 4,096 bytes, its arrays at the offsets the compile-time table's members have
  (`table_layout`). The compile-time tables of `bench/gen` are declared
  `alignas(matcher::route::kPageAlign)`: the alignment is on the declaration, not on
  `StaticTable`, so no table grows. Adoption rule (c), deterministic part, in WSL:
  1. identical lookup code of the two instantiations: `harness_pass` is the same machine code
     in both arms (241 instructions);
  2. equal recorded page offsets for the two arms in every cell: 21 of 21 (every shape at m =
     10, 100 and 1,000, table seed 1; an empty array is recorded as null);
  3. tables byte-identical to round 1's contents: 108 of 108 digests equal E1's (seeds 1 to 3);
  4. `find_v2` unchanged: the objdump check is identical with clang 18.1.3 and gcc 14.2, and on
     L with clang 22.1.8 at E1 to f48fa83 (the first L slot).
  C2 is adopted on this evidence; the H7 iteration check on L (21 cells, engineering seeds, at
  least 10 processes per arm) comes next. Section 4: `table_bytes` of the run-time arm fell in
  all 35 cells of table seed 1 and rose in none; the build makes one allocation more than at
  f48fa83 (the block) and still fewer allocations and bytes than 53e8dda in every table. The
  copy is new work in the build: in development timing (3 processes per arm, 12 cells) v2's
  median build time is 0.375 to 0.648 times the ablation arm's, against 0.349 to 0.571 before
  the copy. The object file of each compile-time table grows by 3,328 to 3,392 bytes, the
  padding to the section's new alignment, while every section keeps its size
  (`hypotheses-v2-proposal.md`, revision log).
- 2026-09-30, the second L slot (lab evidence `2026-09-30-L-slot2`, Papers repository; clang
  22.1.8, pinned, ten engineering pairs: table seeds 1 to 5, ring seeds 2 and 3).
  Target (a), rule 2: two binaries with every arm, RegexMatcher 53e8dda (A) and f48fa83 (B),
  only v2's arm run, A B B A, 10 processes per binary and cell. B's median build time is lower
  in 21 of 21 cells, B/A from 0.347 to 0.739. A1 to A3 are adopted. Whether H4 holds is decided
  by the main grid, as section 1.5 says.
  C2, the H7 iteration check: RegexMatcher 45ab696, both v2 arms in one binary with every arm,
  10 processes per arm and cell. No cell's median ratio exceeds 1.02 (the largest 1.0046, at
  mixed-overlap m = 100; param-first m = 1,000, round 1's crossing cell, 0.9938), so nothing goes
  to Alex. Two single pairs exceed 1.02: wild m = 10 (1.1401, its cell's median 0.9975) and
  static m = 100 (1.0272, median 0.9920).
- 2026-09-30, target (b), B1 and then B1', in the declared order (development, WSL on W,
  clang 18.1.3, hardware counters, not pinned; evidence in the Papers repository,
  `lab/evidence/2026-09-30-W-regexmatcher-v2-b1-chained-edges` and `-b1p-chain-nodes`). A is C2
  (RegexMatcher 45ab696); every build is correct (rule (b), part 3): `bench/tools/backtrack_check`,
  a counting build through the new hook `MATCHER_ROUTE_ON_BACKTRACK`, matches rbench's model on
  290 tables with every answer the ring's, tables without a chain keep E1's digest, agreement
  and probes pass. Part 1, net instructions per lookup, table seed 1, ring seeds 2 and 3:
  1. B1 (chained edges in linear nodes, Edge::tail in its padding, a third node kind; 2147f86,
     reverted in 7a60f2f): mixed-disjoint m = 10 falls by 66.6 and 70.0, but B runs 0.5 or more
     more in 13 of 35 cells, 12 of them without a chained edge (mixed-disjoint m >= 1,000,
     mixed-overlap m >= 100, wild), and 21 more at mixed-overlap m = 10. Not adopted.
  2. B1' (a chain node, tested only where a node found nothing; 0a94cdc): a rise in 16 of 35
     cells, 1 without a chain node, and mixed-disjoint m = 10 rises (16.7, 19.7). A second build
     (4282ba7: chain nodes only for runs of two or more segments, the run compared a word at a
     time) rises in 30 of 35 cells, 28 without a chain node. Not adopted.
  `find_v2`'s normalized machine code has 1,039 lines at C2, 1,154 and 1,293 in the two B1'
  builds, with 1,009 and 1,198 lines differing and no call added: code added to the walk
  changes how the whole function is compiled. The instruction clauses are L's, with clang
  22.1.8, and the gin clause needs L; the next L job measures A, B1 and both B1' builds in one
  arm set with gin, so that these rejections, or any change to them, rest on L. If no build
  passes all three clauses there, the loss of H2 at mixed-disjoint m = 10 stands and is
  reported; B2 stays last, and only if time allows. No rule changed.
- 2026-09-30, target (b) decided on L (the third L slot, lab evidence `2026-09-30-L-slot3`;
  clang 22.1.8, pinned; one arm set with gin for every candidate; table seed 1, ring seeds 2
  and 3; net instructions per lookup against C2). No candidate passes part 1 of rule (b):
  B1 fails clauses 1 and 2 (every trie cell without a chain rises, by 13.8 to 20.8) and holds
  clause 3 (mixed-disjoint m = 10: 470.7 and 477.6 against gin's 513.8 and 520.5); B1' as first
  built holds clause 1 and fails clause 2 (12 cells with chain nodes rise) and clause 3 (532.1
  and 538.2); its second build fails all three. A third B1' build was not made: its `find_v2`
  code was not confined to the chain. Part 2 is not run. As declared, the loss of H2 at
  mixed-disjoint m = 10 stands and is reported, and RegexMatcher returns to C2 (d1d73e9, the
  same tree as 45ab696, in the bare repository on L). B2 is attempted only if time allows before
  the freeze. No rule changed.
