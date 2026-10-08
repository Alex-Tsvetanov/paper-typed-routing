# Hypotheses of round 2

Status: FROZEN on 2026-09-30 by the coordinator on Alex's standing instruction, before any gated run on the seeds of section 4. Written on 2026-09-30 from
`design/round2/hypotheses-v2-proposal.md` (section 3 and every decision of its revision log), the
coordinator's decisions of 2026-09-30, and the independent audit of the first draft, whose every
finding is applied (the proposal's revision log lists them). Alex freezes this file before any
gated run on the seeds of section 4. In this file, the commit that freezes it changes this status
line and nothing else. The same commit appends the entry of the proposal's section 6 to the
revision log of `hypotheses.md` (round 1), which otherwise stays frozen. Every later change to this
file goes into the revision log at the end, as a deviation with its reason.

Words:
- "v1" is RegexMatcher's regex-set engine at commit d16f30a8.
- "v2" is RegexMatcher's route matcher (`include/matcher/route.hpp`), the subject of the paper.
- "the round-1 header" is the router that round 1 measured, which this file does not name.
- "L" is the lab host (Ryzen 7 5800H, Zen 3); "W" is the Windows workstation (Ryzen 5 3600).

## 1. What is measured, and what it rests on

- **RegexMatcher v2 at commit d1d73e99b7b26f54ba75354f4880780ece32e8ed** (branch
  `v2/route-matcher`). Its tree equals that of 45ab696, step C2 of `design/round2/engineering.md`.
  The run builds it from a snapshot of that commit (`git archive`), given as `REGEXMATCHER_DIR`
  and `REGEXMATCHER_COMMIT`.
- **The harness** (rbench, `bench/`) at code commit 90beca488, the last commit that changed its
  compiled sources. Every arm is in one binary.
- **The minimal server** (`server/`, `t1/`): one binary with three router arms, v2, v1 and null.
  It compiles `bench/core` and reads `bench/cmake`. Its records name code commit 4cc42bf11. The
  one later change there, 90beca488, is to the Rust arms' build file, which the server does not
  compile; the gate matches the server's inputs with its records' (lab evidence
  `2026-09-30-L-gates-r4`). It is compiled for the same instruction set as rbench, since H6
  compares arms within it. The load generator, t1gen, is not an arm; its build and record are
  unchanged (`t1gen-1eaee40c3`).
- **The instruction set** is L's own, for every arm (section 2, Appendix B). On L,
  `-march=native` resolves to clang's target CPU znver3, rustc's `native` to znver3, and the Go
  arms get GOAMD64 v3. Each build writes these into `rb_isa.h` (`bench/cmake/isa.cmake`), which is
  a compiled input of every first-party target. So a build for another instruction set has other
  inputs, and the records gate refuses it.
- **Sanitizer records**, all green, clang 22.1.8 on L, committed in the Papers repository
  (`lab/sanitizer-records/`, Papers 0f90a96):
  - `regexmatcher-d1d73e99b-L-{asan,tsan,msan}`: RegexMatcher's whole suite, 87 tests each,
    built with RegexMatcher's own flags, without `-march`. The gate matches them by
    RegexMatcher's headers. v2's code as the run compiles it, at the native flags, runs under
    every sanitizer in rbench's and the server's records;
  - `rbench-90beca488-L-asan`, `rbench-4cc42bf11-L-tsan` and `rbench-4cc42bf11-L-msan`: every
    arm, except that MSan leaves out the seven FFI arms, the gap `bench/coverage.json` declares.
    The records are matched by inputs, whatever the commit. 90beca488 made the Rust arms' digest
    in an ASan build equal to the measured build's, so only the ASan record was made again (lab
    evidence `2026-09-30-L-gates-r4/attempt1`);
  - `mserver-4cc42bf11-L-{asan,tsan,msan}`: the server with its H6 exercise;
  - on W, extra coverage that gates nothing: `regexmatcher-d1d73e99b-W-asan` (MSVC 19.51.36246.0).
- **io_uring.** No binary of the records links liburing or refers to io_uring (lab evidence
  `2026-09-30-L-records-r4` and `2026-09-30-L-records-r5`). So MemorySanitizer's known blind spot,
  the kernel's writes through io_uring, does not apply.
- **The gates.** Every measured build on L is hashed and refused unless green records on L of
  every sanitizer compiled the same first-party inputs. The measured builds are the main grid, the
  exploratory runs, H7's costs on L and the H6 server. The records must also match:
  - the compiler and the configuration;
  - the sha256 of `bench/cmake/pins.cmake`, which was
    fd987818804ada347ef5ef74977909412e0775cd698e510b51a86631885d15fc when the records were made;
  - for every archive both fetched, the same URL and hash (`bench/gate_lib.py`);
  - RegexMatcher's headers (hash 5737e40609f1), which its own three records must cover.

  A pin changed after the records makes every build fail its gate until the records are made
  again. The CHECK_ONLY gates of rbench, the server and H7's cost build passed against these
  records (lab evidence `2026-09-30-L-gates-r4`).
- **The lookup's machine code.** `find_v2` compiled against the round-1 header and against v2 at
  d1d73e9, both with clang 22.1.8 at the harness's flags (`-march=native` included), gives
  identical code: 4 functions, 1,107 lines each (`bench/objdump_check.sh`, lab evidence
  `2026-09-30-L-gates-r4`). The check was first made without `-march`, against development
  baselines, and was made again at the native flags.
- **A build for another instruction set is refused.** Every arm built without `-march`, with
  Rust's default CPU and `GOAMD64=v1`, failed the records gate (lab evidence
  `2026-09-30-L-gates-r4`).
- **H7's MSVC costs need no record.** They are compiler measurements of code that is never
  executed (H7).
- **The lab host is frozen.** L runs kernel 7.2.3, clang 22.1.8 and Go go1.27.1-X:nodwarf5, with
  kernel 7.2.6 installed. No package update and no reboot on L from the first record above
  (2026-09-30) to the end of the last run.
- **Round 1 is development data.** Round 1 measured the round-1 header inside another code base:
  the main grid of 2026-09-27, its re-verification, its exploratory runs, its H7 cost run and its
  H6 run of 2026-09-28. It guided the engineering of round 2, and is cited only there and in the
  lab journal. No round-1 number appears in the paper as a result or enters this analysis. Its
  seeds are not reused. The paper's methods say that a development round measured a pre-release
  of the same lookup code, with the same harness and design, on other seeds. They say that it
  guided the changes the paper describes, and that its numbers are not reported. The round-1 H6
  run is not mentioned in the paper.

## 2. What is compared

- **RegexMatcher v2**, routes added at run time (`regexmatcher-v2`), the arm of H1 to H4. Routes
  are checked when the program is compiled. Lookup is an exact-match table for a method whose
  routes are all literal, and a trie over path segments for any other method. It makes no heap
  allocation. The arm is v2's table behind one out-of-line call (`find_v2`).
- **RegexMatcher v2, compile-time table** (`regexmatcher-v2-ct`), the arm of H7. The same routes
  are declared as a `constexpr` table in a generated translation unit (`bench/gen/`). There is one
  per shape at m = 10, 100 and 1,000, for table seed 1 and every table seed of section 4, and one
  for the GitHub table. Each is aligned to a page, as the run-time table's block is. It shares its
  adapter with `regexmatcher-v2` (one class template).
- **Competitors**, sixteen, each at the release `bench/cmake/pins.cmake` pins, by commit and the
  sha256 of its source archive (the Rust crates by `Cargo.lock`, the Go modules by `go.sum`):
  - Crow v1.3.4 (`crow::Trie`);
  - Drogon v1.9.13, its lookup transcribed from `lib/src/HttpControllersRouter.cc` at that tag,
    whose sha256, size and transcribed line ranges `pins.cmake` records;
  - Oat++ 1.3.1;
  - Pistache v0.4.26;
  - the Boost.URL 1.92.0 example router;
  - r3, the head of its maintained 2.0 branch (83d362f; its last tag, 1.3.4, is from 2015), with
    PCRE2 10.49;
  - matchit 0.9.2 (Rust). matchit is the router library axum builds on; axum 0.8.9 pins matchit
    0.8.4, and the arm measures matchit's latest release;
  - httprouter v1.3.0 (Go);
  - gin v1.12.0, its router tree vendored unchanged and called as gin's engine calls it;
  - Go's net/http ServeMux, with the patterns of Go 1.22 and later (Go 1.27.1);
  - actix-router 0.5.4 (Rust), the router of actix-web;
  - uWebSockets v20.80.0 (`uWS::HttpRouter`);
  - glaze v9.0.0 (`glz::route_table`);
  - chi v5.3.2 (Go);
  - path-tree 0.8.3 (Rust);
  - cpp-httplib v0.58.0, its path matcher. It has no catch-all syntax; a regular-expression route
    ending in `(.+)`, its documented way, stands for the catch-all.

  On 2026-09-30 each pin was the project's latest release, or, for r3, the head of its 2.0 branch
  (read-only release pages, `lab/evidence/2026-09-30-W-pins-freshness`). PCRE2 moved to 10.49,
  released on 2026-09-28, because it is on r3's lookup path
  (`lab/evidence/2026-09-30-L-r3-pcre2-path`).
  PCRE2 is built without JIT, and r3 never calls `pcre2_jit_compile`, so JIT would not apply.
- **Each competitor's configuration** is in Appendix B, with its source: the library's
  documentation where it has one, else "library default, not documented".
- **Every arm is compiled for L's own instruction set**, v2 included (Appendix B): the C and C++
  arms with `-O3 -DNDEBUG -std=c++23 -march=native` and no LTO, the Rust arms with
  `-C target-cpu=native`, the Go arms with `GOAMD64=v3`. On L, `-march=native` resolves to znver3.
- **What each arm's timed lookup includes** is in Appendix A. Each arm is timed from the method and
  the path, in the form its library's request carries them, to the route and the captured values
  as the router's API returns them. Framework steps outside route lookup are left out for every
  arm: request and context pooling, and response writing. Where the router's API runs a handler to
  report the route (uWebSockets and the Go arms), the handler only records the route and, for
  net/http, copies its values.
- **"The fastest competitor"** of a cell is the competitor with the lowest median lookup time
  among those included in the cell (`analysis/cells.py`). A competitor absent from the cell is not
  one of them. It is absent if it refused the table, exceeded the time budget, or differs by its
  declared path semantics. It can differ from cell to cell.
- **Reference arms**, not competitors:
  - `regexmatcher-v1`, v1 at d16f30a8 behind the pattern-to-regex wrapper;
  - the in-repo radix tree (`radix`), exact-match hash table (`hash`) and sequential std::regex
    (`std-regex`).

  hash and radix run in every cell in R = 16 processes. std-regex and regexmatcher-v1 run up to
  m = 10,000, in 3 processes per cell, on the first three pairs of section 4. On the static shape,
  whose one method has only literal routes, v2 answers from its exact-match table, the mechanism
  of hash. That statement covers a method whose routes are all literal only.
- **Null arms**, not compared. Each measures the harness's loop around a lookup that does not
  match: one out-of-line call that reads the path's length. H2 subtracts the null of the same loop:
  - `null` answers 405 itself, so the harness adds nothing to its answer. It is the null of every
    arm whose lookups the harness calls and that answers 405 itself: v2, the compile-time table and
    the ablation arm.
  - `null-no405` has no 405 of its own, so the harness applies its 405 rule to it: the test of
    each answer against "no route", the fallback never taken. It is the null of every other arm
    whose lookups the harness calls: the C++ competitors, the Rust competitors behind their C
    functions, and the reference arms.
  - Each Go arm has a null pass of its own, in its own process: the same loop over the same loaded
    data, with the router's lookup replaced by a call that reads only the path's length.

  Every cell names the null it is paired with (`loop_null`: "null", "null-no405" or "own").
- **The ablation arm**, exploratory, not compared: `regexmatcher-v2-r1`, the round-1 header with
  its namespace and macro prefix renamed and nothing else changed (step E1 of
  `design/round2/regexmatcher-v2.md`). It is vendored under a namespace of its own, so that it
  links beside v2. It runs in every cell of the main grid in R = 16 processes and decides nothing.

## 3. Cells and measurements

A cell is one arm, one table shape and one table size:
- the seven shapes of `bench/core/table.hpp`: static, param-last, param-first, rest, wild,
  mixed-disjoint, mixed-overlap;
- m = 10, 100, 1,000, 10,000 and 100,000 routes;
- a ring of 4,096 lookups drawn uniformly over the table's routes, all hits.

Per cell (`bench/core/runner.hpp`):
- the median ns per lookup over nanobench epochs;
- instructions, branch misses and cycles per lookup;
- L1d misses, L2 misses of data requests and L1 DTLB misses per lookup;
- dispatch-resource stall cycles per lookup for every unit-mask bit of AMD events 0xAE and 0xAF,
  each bit counted on its own and never summed;
- latency percentiles, one lookup at a time. Behind a foreign-function boundary they include one
  call across it, and are reported apart;
- heap allocations per lookup, counted only in the allocation pass and the build, never in a
  timed loop;
- the build time, the bytes allocated during the build (`build_alloc_bytes`), and the heap bytes
  held by the built table;
- the page offsets of the four arrays of v2's table (`table_layout`);
- for the Go arms, outside every timed loop: the cost of an empty call across cgo (`ffi_call_ns`),
  `GOMAXPROCS` (`go_maxprocs`) and the number of Go collections during the timed epochs
  (`go_gc_cycles_in_epochs`).

The run also keeps, from its build, the address modulo 64 of every timed function
(`symbols.tsv`, `bench/symbols.py`). The layout of the code is fixed per binary, so every process
of an arm runs the same alignment; the file says what that alignment was.

An arm without a 405 of its own gets the harness's: on a miss, the same path under every other
method that has routes. It is Crow's and httprouter's own rule.

The timed loops of the harness read a compact copy of the ring, made in each process before the
table is built. A Go arm loads its own copy of the ring into Go's heap at its first timed pass,
after the build. Every process runs on CPU 2 of L, the Go runtime included, so `GOMAXPROCS` is 1
there. Go's collector and its system monitor share that CPU with the timed loop. They take wall
time that the counters of the measuring thread do not count. So for the Go arms the thread's
clock (cycles over time) and the spread of their time over the epochs are reported beside their
times.

Declared here because round 1's text did not say them:
- **Timed passes over a slow arm run on a prefix of the ring.** A timed pass that would take
  longer than 0.25 s is cut to the prefix that fits, never to fewer than 16 queries
  (`MeasureOptions::pass_budget_s`). The ring is in random order. Every cell records the length
  (`lookups_per_pass`). The cut is decided from the agreement pass's time, which for a Go arm
  includes one cgo call per query. A cut arm repeats a short prefix, which warms its predictors
  and caches. So a cut arm's time and counters are optimistic for it. The analysis flags every
  cell where v2 or the fastest competitor was cut, and H2 reports its median-competitor branch
  misses with and without the cut competitors.
- **Every process is checked on every query of its ring.** In each process, an agreement pass
  checks the route and every captured value of each query against the ring's expectation. The
  pass stops after 120 s, once at least 64 queries were checked (`verify_budget_s`; `verified_all`
  says whether it reached every query). After its last measured cell, every run checks each process
  that the pass cut on every query of the same table and ring. The check is untimed, with
  `tools/verify_answers` linked from the run's own build (`bench/run_grid.sh`,
  `tools/verify_unverified.py`, written to the run as `verified.jsonl`). A check counts only if its
  table and ring digests equal the process's. A process that neither check verified on every
  query fails its cell (`analysis/cells.py`). So the rule "on every query" holds for every process
  of a run before any analysis. The tool covers every arm (`tools/verify_cover.py`), and a grid on
  L ran the re-check end to end (lab evidence `2026-09-30-L-gaps`).
- **The stopping rule.** The time budget of a process is 1,800 s. When a cell's first process
  exceeds it, the cell's other processes are not run, and the cell is reported as "exceeds budget".

A cell counts for a hypothesis only if the arm agrees with the ring's expectation on every query
(above). Every process's answers are also judged at every size against `bench/semantics.json`
(`bench/check_agree.py --cells`). A disagreement not declared there fails the run. An arm that is
ok in some processes and not in others fails the cell. The analysis prints every competitor it
leaves out of a cell, with the reason. Arms that disagree are reported, not dropped:
- **Declared path semantics.** An arm whose answers differ on a shape by its declared semantics is
  measured all the same, and shown as "incomparable: N of 4,096 answers differ", N counted in every
  process and reported as its range. It takes no part in that shape's cells, and so it is not a
  candidate for the fastest competitor there. Each declaration names the one kind of wrong answer
  it allows; any other wrong answer fails the cell. The four declarations:
  - Boost.URL's example router on mixed-overlap, kind "values": the right route on every query, but
    a value captured in a branch it left is kept;
  - gin on mixed-overlap, kind "404": no route for a query resolved by backtracking, and right
    values wherever the route is right;
  - r3 on mixed-overlap, kind "404", as gin, and at larger sizes for other queries of a group too;
  - uWebSockets on wild, kind "values": its `*` matches the rest of the path but returns no value
    for it. The adapter does not compute the value, because uWebSockets' router does not give it.
    So uWebSockets takes no part in the five wild cells.

  The kind is checked over the queries the agreement pass verified. A declared arm's status is
  not "ok", so the final check on every query does not run for it.
- **Refused tables.** An arm that rejects a table while it is built is shown as "refused at
  insert" or "refused", with the router's reason (for example hash on every shape with parameters).
- **Anything else** is a failure of the run, not an absent arm.

## 4. Seeds and order

R = 16 processes per cell on L, pinned by `lab/bin/pin.sh`, every arm in one binary, all in the
same run. Process k of a cell (k = 1 to 16) uses the pair (110 + k, 210 + k):

(111, 211), (112, 212), (113, 213), (114, 214), (115, 215), (116, 216), (117, 217), (118, 218),
(119, 219), (120, 220), (121, 221), (122, 222), (123, 223), (124, 224), (125, 225), (126, 226).

Sixteen pairs with sixteen distinct table seeds and sixteen distinct ring seeds, so no two pairs
share a table or a ring. The pairs are independent, and the analysis treats them so (section 5).

The seeds are held out: no run has timed them.
- Round 1 used table seeds 1 to 5 and 101 to 105, and ring seeds 2 to 4 and 201 to 203.
- Round 2's engineering, iteration and development runs timed table seeds 1 to 5 with ring seeds
  2 to 4. The quick cells of the sanitizer records used the pair (1, 2) only.

The held-out seeds have been used for correct answers only, timing nothing:
- the agreement test (`rbench agree` at m = 10, 100 and 1,000), on the first 1,024 queries of ring
  seed 2, with which every run of `bench/run_grid.sh` starts. Its table seeds are 1 and those of
  the design. They were 111 to 118 before the design had sixteen table seeds (paper 82681fe), and
  are 111 to 126 since. It ran in the sanitizer records and the development grids;
- the agreement jobs of the first L slot and of the build rework in WSL (table seeds 1, 111 and
  112), and a development check in WSL on 2026-09-30 (table seeds 1 and 111);
- the minimal server's agreement test and its sanitizer records, at H6's pair (111, 211);
- `bench/gen`, which holds the compile-time tables of table seeds 1 and 111 to 126, written by
  `rbench gen-ct`. Every full build of rbench compiles them, and Ninja records their compile
  times; none was read. Both earlier runs of `bench/ct_cost_run.sh` were CHECK_ONLY.

Table seeds 119 to 126 and ring seeds 219 to 226 came with the sixteen-pair design. A scan of every
run's rows and plans on W, on L and in the archives found no use of them before it (lab journal,
2026-09-30).

The order of the processes is shuffled with the order seed **20261009** (`SEED`), fixed here. It
has shuffled no run. Round 1 used 20260926 and 20260927. Round 2's development grids, and the
records' quick grids before paper 3c71533, used 20260927; the others ran unshuffled.

Every process runs on CPU 2 of L (physical core 1; its SMT sibling runs nothing of ours), the same
for every arm. The run records the CPU and its siblings, the transparent huge pages, the NMI
watchdog, the governor, and the compilers and runtimes of every arm. The analysis refuses a run
without the sixteen design pairs: a cell whose v2 processes do not use exactly the sixteen pairs
above cannot pass.

A run that stops early is archived, reported in the lab journal, and not used. It is started again
in full, under a new name, with the same seeds.

## 5. Statistics of H1 and H7

A comparison of arms in a cell is paired by seed pair. Its statistic is the median over the 16
pairs of the per-pair ratio. Two computations, both pre-specified, both reported for every cell
(`analysis/stats.py`):
- **The BCa interval.** 10,000 resamples of the 16 pairs, drawn with replacement. Within a pair,
  an arm's values stay together. For H1 the fastest competitor is chosen again in every resample.
  - The bias correction z0 counts ties as half.
  - The acceleration comes from the jackknife over pairs. The 16 leave-one-out medians take two
    values, eight times each. So the acceleration is 0 whenever the fastest competitor is the same
    in every leave-one-out set, as it always is for H7. The interval is then the bias-corrected
    percentile interval.
  - The one-sided p-value of "the ratio is at least the margin" is the level alpha at which the
    upper bound of the BCa interval at 1 - 2 alpha equals the margin.
  - The share of resamples below the margin is clipped to [1/(2B), 1 - 1/(2B)] before that
    inversion, B = 10,000. With z0 and the acceleration at 0, the smallest p-value is then about
    5.0e-5.
- **The exact sign test.** X is the number of pairs whose ratio is below the margin; a tie at the
  margin counts as not below. Under H0 "the median ratio is at least the margin", X is binomial
  with 16 and 1/2 at the boundary. p = P(X >= x), computed exactly.

For H1, each computation runs Holm's step-down over the 35 cells at family-wise alpha = 0.025,
one-sided. A cell cannot be tested if `analysis/cells.py` fails it, or if no competitor takes part
in it (section 8). It enters Holm with p = 1 and does not pass. A cell passes if it passes under
both computations. If they disagree in a cell, both are reported and the cell does not pass.

Rule D9 asks for enough replicates that an exact paired test can pass the family's Holm threshold
(2^-R < alpha/m), and for a clustered bootstrap. On sixteen independent table seeds:
- With R = 16 the smallest one-sided sign-test p is 2^-16 = 1.53e-5, below Holm's first threshold
  for 35 cells, 0.025 / 35 = 7.14e-4.
- One pair at or above the margin gives p = 2.59e-4, two give 2.09e-3, three give 1.06e-2.
- The bootstrap's smallest p, about 5.0e-5, is also below 7.14e-4.
- Each table seed is in one pair, so the bootstrap clustered by table seed is the bootstrap over
  pairs above.

The resampling seed is **20261010**: one generator per hypothesis, seeded 20261010, in the stated
order.
- For H1 the generator serves the 35 cells in the family's order: each shape in the order of
  section 3, and within a shape the sizes in increasing order. Each tested cell draws its
  resamples once.
- For H7 likewise, over its 21 cells.
- For H6, over its nine cells in the order H6 lists them. Each tested cell draws the resamples of
  (a), then, where D_T0 is positive, those of (b).
- A cell that is not tested draws nothing.

The seed was used once before, on a development grid in WSL (15 pairs of engineering seeds); that
grid cannot preview a resample of this run.

The implementation computes the normal distribution with Python's `statistics.NormalDist`. On L
it gave SciPy's BCa interval to the last digit on the same draws, and the sign test agreed with
`scipy.stats.binomtest` to 1e-16 (`lab/evidence/2026-09-30-L-bca-scipy-check-r2`).

## 6. Hypotheses

H1. Lookup time, non-inferiority. In every cell in which a competitor holds the table,
    RegexMatcher v2 (`regexmatcher-v2`) is not slower than the fastest of them.
    - The statistic of a cell is the median over the seed pairs of v2's time divided by that of
      the fastest competitor of the cell (section 2).
    - The family is the 35 cells of the seven shapes and five sizes.
    - In each cell, the null hypothesis "the ratio is at least 1.02" is tested as section 5 states.
    - H1 holds overall if at least 32 of the 35 cells pass, and the upper bound of the unadjusted
      95% BCa interval is at most 1.10 in every tested cell. H1's 1.10 cap applies to tested
      cells; a cell that cannot be tested does not pass, and so counts against the 32.
    - Superiority, the null hypothesis "the ratio is at least 1.00", is tested the same way, with
      both computations, Holm-adjusted over the family on its own. It is reported per cell. It
      decides nothing about H1.
    - The paper calls v2 faster than the fastest competitor only in the cells that pass the
      superiority test. H1 alone supports "not slower" (non-inferiority at 1.02), never "faster".
    - A cell where v2's or the fastest competitor's timed passes ran on a prefix of the ring says
      so (section 3).

H2. Work per lookup. In every cell, v2 executes no more instructions per lookup than the fastest
    competitor of that cell, and takes no more branch misses per lookup than the median
    competitor.
    - The median competitor's branch misses are the median over the included competitors of each
      one's median over its processes.
    - Values are medians over the 16 processes.
    - Instructions are compared net against net: each process's count minus that of the null of
      its own loop (section 2). Raw counts are reported beside the net ones.
    - Branch misses are compared raw, not net.
    - The comparison is strict: no tolerance and no interval.
    - A cell that cannot be judged does not hold: one that `analysis/cells.py` fails, one without
      a competitor, or one whose null count is missing.
    - A loss is reported in the cell where it occurs, with the memory-side counters of v2 and of
      the fastest competitor.
    - Development data predicts one loss. At mixed-disjoint m = 10, on L at the engineering pairs,
      v2's net count was 527.8 and 530.8 against gin's 513.8 and 520.5 (lab evidence
      `2026-09-30-L-slot3`). Those builds had no `-march` and gin no `GOAMD64`, so the prediction
      is for other code than the run's. No change to the lookup passed its adoption rule
      (`design/round2/engineering.md`, target b), and the cell is judged as every other.

H3. No allocation. RegexMatcher v2 makes 0 heap allocations per lookup in every cell, captured
    values included (they are views into the request path). H3 holds only if every process of the
    35 cells ended ok and counted 0.

H4. Build and memory are not the price. At every size, v2's build time is at most the median
    competitor's, and at m = 100,000 it is below 1 s. The heap bytes its table holds are at most
    twice the smallest competitor's.
    - H4 is read per (shape, size) cell, against the competitors included in that cell
      (`analysis/cells.py`), on the cells' medians over processes.
    - v2's build time is the median over processes of each process's median build time. It is
      compared with the median of the included competitors' build times.
    - v2's heap bytes are compared with twice the smallest included competitor's.
    - Heap bytes are malloc's live bytes after the build (C, C++ and Rust arms) plus, for the Go
      arms, the Go heap's live bytes after a collection.
    - H4 holds if all three hold in every cell. A cell that cannot be judged does not hold.

H5. Checked when compiled, correct when run.
    (a) A negative-compilation suite of malformed routes fails to compile, each for its stated
        reason. The cases are the 17 files of `tests/route/neg/` in RegexMatcher at d1d73e9, one
        CTest entry each (`route_neg_compile_<case>`, label `neg`):
        - an unclosed '{', an empty parameter name, a parameter name that is not a valid name;
        - a catch-all that is not the last segment, a repeated parameter name, an unknown type;
        - an empty segment, a missing leading '/', a byte that is not an RFC 3986 pchar, a brace
          inside a literal segment;
        - a handler whose parameter count or types do not match the pattern;
        - two routes in one compile-time table that match exactly the same paths, and a malformed
          pattern in such a table;
        - in a compile-time table of route declarations with handlers: two routes that match the
          same paths, and a handler whose parameter count or types do not match its pattern.

        Each entry has WILL_FAIL and checks that the diagnostic names the reason, so the suite
        reports 100% passed. The evidence is RegexMatcher's sanitizer records of the measured
        commit (section 1). They carry the number of tests (87) and of failures (0); the names
        of the tests are in each record's log archive, whose sha256 the record holds.
    (b) v2 passes every probe of `bench/core/probe.cpp`:
        - the most specific route wins, in either registration order;
        - every RFC 3986 pchar is accepted in a parameter and returned as sent;
        - a trailing slash is strict;
        - a path that matches only under another method gives 405.

        H5(b) is v2's part, decided by the probes of the publication run (`analysis/h5_stats.py`).
        Whether RegexMatcher v1 behind its wrapper fails the first two, as it did in round 1, is
        reported beside it and decides nothing.
    (c) Over HTTP/1.1, HEAD on a path only GET routes match is served by the GET route, with the
        head of the response only. A 405's Allow lists HEAD when it lists GET (RFC 9110 sections
        9.1 and 9.3.2). These are tests in the suite of the paper's minimal server; their
        evidence is the server's sanitizer records (section 1). HTTP/2 is out of scope: the
        paper's server has none.

H6. v2's faster lookup reaches the client. Measured at T1 on L, over loopback, with the paper's
    minimal HTTP/1.1 server (`design/round2/minimal-server.md`). One binary has three router arms:
    v1 behind its wrapper (the reference), v2, and null.
    (a) Direction. The nine cells are the seven shapes at m = 10, and rest and param-last at
        m = 10,000. In each, the lower bound of the 95% BCa interval of the req/s ratio v2 / v1 is
        above 1.00. (a) holds only if all nine lower bounds are above 1.00.
    (b) Carry-over. In each of the nine cells, the lower bound of the 95% BCa interval of
        D_meas / D_T0 is at least 0.5.
        - D_meas = 1/X_v1 - 1/X_v2 is the measured difference in time per request, X the arm's
          req/s.
        - D_T0 = t_v1 - t_v2 is the difference of the two arms' lookup times in round 2's T0 grid.
          Each is that arm's `ns_median` in its process at pair (111, 211), in the cell of the same
          shape and size. That is the pair whose table and ring H6 serves.
        - The T0 process must be usable (section 3). A T0 cell where v2 is not faster fails H6(b).
        - At m = 10,000, t_v1 may rest on a prefix of the ring (`lookups_per_pass`, reported).
        - D_T0 is one value per cell, so the interval of (b) covers the variation of T1 only. It
          does not include the error of D_T0.
        - (b) holds only if all nine hold.

    Reported beside each cell, not tested:
    - the null arm's time per request, 1/X_null;
    - the ratio predicted from T0, P = (1/X_null + t_v1) / (1/X_null + t_v2), and the measured
      ratio over P;
    - the sign test. The H6 sign test is reported and does not decide: per cell, the exact
      one-sided sign test of the pairs whose ratio is above 1.00, and of those whose carry-over is
      at least 0.5.

    Development data informed (b). In round 1's T1 run, with another server and another pair of
    routers, the measured difference per request was 1.04 to 2.25 times the difference of the T0
    lookup times. That was over its eight comparable cells (`results/tab_h6.csv`, column
    `diff_ratio`); mixed-overlap was not comparable. The bound 0.5 was chosen below that range, and
    the paper says so.

    Servers and targets:
    - the routes of the T0 generator at table seed 111, every route answering with the fixed
      13-byte body, and GET / for lab/t1's probe;
    - targets from `t1/h6_targets`, one per route, each parameter filled as the T0 ring fills it
      (ring seed 211), in an order shuffled with that seed; GET / is not in the file.

    Design (lab/t1, `t1.py`):
    - one server core, CPU 14 of L (its SMT sibling, CPU 15, idles), one worker, epoll;
    - t1gen on CPUs 2 to 13, 64 connections, keep-alive, one request in flight per connection;
    - a fresh server per window, probed with one request, then a 1 s warm-up and a 5 s window;
    - req/s is completed 2xx responses over the measured wall time;
    - mirrored rounds, v1, v2, null, null, v2, v1, with v1 the reference. One round is one pair.

    Valid windows and pairs (`t1.py`, as `t1/run_h6.sh` calls it with `--valid-pairs-only`):
    - A window is invalid if the server did not start, or its probe did not return 200 with the
      body, or it completed no request. It is also invalid if its error share exceeds 0.1%, if
      t1gen's CPUs were more than 90% busy, or if the mean CPU MHz drifts more than 2% from the
      session's value.
    - Invalid windows are listed with their reasons. A round with an invalid window of any arm is
      not a valid pair, and is left out of every statistic.

    Stopping, per cell (`t1.py`, `--min-pairs 6 --max-pairs 20`):
    - Only valid pairs count toward the minimum and the stop.
    - The stop looks at v2 against v1 and at null against v1, each through a 95% percentile
      bootstrap interval of the geometric mean of the valid pairs' ratios.
    - After each round with at least 6 valid pairs, the cell stops when, for both, that interval
      lies wholly outside [0.98, 1.02] or its half-width is below 1% of that mean.
    - Otherwise it continues, to 20 rounds at most, valid or not.
    - A cell with fewer than 6 valid pairs at its end does not hold, for (a) or for (b).

    Statistic: per pair, each arm's mean req/s over its two windows. From these, the ratio
    v2 / v1 and D_meas. Per cell, the median over pairs, with its two-sided 95% BCa interval over
    pairs, computed as for H1: 10,000 resamples, the generator of section 5, ties as half, the
    acceleration from the jackknife over pairs. With an even number of pairs that acceleration is
    0 (section 5). No multiplicity adjustment: (a) and (b) each require every one of their cells,
    so each claims only what every one of its tests shows. With at least 6 pairs, an exact sign
    test of a cell can reach p = 2^-6 = 0.0156, below 0.025 (rule D9).

H7. A compile-time table is not slower. On the same routes and the same ring, the compile-time
    table is not slower than v2's table built at run time.
    - In every cell measured, the ratio (compile-time / run-time, median ns per lookup) passes both
      computations of section 5 at the margin 1.02, each at one-sided alpha = 0.025 per cell.
    - That is, the upper bound of the 95% BCa interval is at most 1.02, and the exact sign test
      passes, which needs 13 of 16 pairs below 1.02.
    - H7 covers m <= 1,000 only: the seven shapes at m = 10, 100 and 1,000, 21 cells. The
      compile-time arm refuses larger tables by design.
    - A cell whose processes of either arm are not all usable, or whose pairs are not the
      design's, does not hold.
    - Each compile-time table is compiled with the constant-evaluation budget 33,554,432 steps
      (`-fconstexpr-steps`, `bench/cmake/arm-regexmatcher-v2-ct.cmake`).

    Its costs are reported with it, as results. They are compiler measurements of code that is
    never executed, so they need no sanitizer record.
    - On L, a fresh build of the compile-time arm at -j1 (`bench/ct_cost_run.sh`, gated as every
      measured build; `bench/ct_costs.py`) costs all 358 tables of `bench/gen`. They are the 336
      of the sixteen held-out table seeds, the 21 of table seed 1 and the GitHub table. The costs
      are the compile time of each table's translation unit and its object size.
    - The object size is the sum of the sections named `.text*`, `.rodata*` and `.data.rel.ro*`,
      the other `.data*`, and `.bss*`. The file size is reported beside it: the tables are aligned
      to a page, and that alignment pads the file without adding memory the lookup touches.
    - Clang's constant-evaluation need per table (`bench/ct_steps.py`) is measured against the
      budget, for table seed 111 of every shape and size and for the GitHub table.
    - On W, MSVC 19.51.36246 (the compiler of RegexMatcher's W record), for the same 22 tables,
      compiled one at a time (`bench/ct_msvc.py`):
      - the flags are those of RegexMatcher's `route_ct_table_tests` in a Release configure with
        the W record's options and no sanitizer, with the bench directory on the include path;
      - the budget is searched with `/constexpr:steps` N, N = 1,048,576 (cl's default) times 4^k,
        until the table compiles; a factor of 4 between the last failure and the first pass is
        halved once;
      - one more compile at 33,554,432 gives the peak memory (the Job Object's peak committed
        memory of cl.exe), the object size (the file) and the wall time, which is information
        only.

## 7. Exploratory, not hypotheses

Each runs with `bench/run_grid.sh`'s variables from the gated build of the main grid, with the
same order seed. Each is summarized by `analysis/explore_summary.py` (v2 against the fastest
competitor per cell, with net instructions). None has an interval or decides anything. Each uses R
processes per cell on the first R pairs of section 4, and the reference arms as in the main grid:
- **Miss-heavy rings** (`MISS=500`): the ratio v2 / fastest competitor per shape when half the
  queries miss. Every shape and size, R = 3.
- **The GitHub API table** of go-http-routing-benchmark (203 routes; `SHAPES=github SIZES=203`):
  one cell, R = 16.
- **The long-literal vocabulary** (`VOCAB=long`, literals of 12 to 24 letters, because v2 keys a
  segment on its first 8 bytes), at m = 10,000 and 100,000 in every shape, R = 3.
- **A Zipf-distributed ring** (`ZIPF=1`), at m = 10,000 and 100,000 in every shape, R = 3.
- **mixed-overlap without the decoy queries** (`NO_DECOY=1 SHAPES=mixed-overlap`), where gin takes
  part: without the decoys the walk never backtracks. Every size, R = 16.
- **The ablation arm** `regexmatcher-v2-r1` in every cell of the main grid (section 2): the ratio
  of v2 to it per cell, for lookup time, net instructions, build time and heap bytes
  (`analysis/ablation.py`), reported as what round 2's engineering contributed.
- **Only if an H7 cell shows a table seed apart from the others:** that cell again, with the
  compile-time table copied into a heap block in the same binary (`design/round2/engineering.md`,
  3.4).

Dropped from round 1's list, with the reason: the rings of 65,536 and 1,048,576 queries, and the
ring layout before the compact copy. Both concern the harness's design; round 1 answered them as
development data.

## 8. What would count against the paper's claim

The claim is that v2 is the fastest route matcher measured here. Its scope is L, one core (CPU 2),
clang 22.1.8 and L's own instruction set (znver3), against the competitors of section 2 in the
configurations of Appendix B.
- "Faster" rests on the superiority family of H1 alone, cell by cell. H1 itself supports only
  "not slower".
- "The fastest" is said of a cell only against the competitors included in it. A competitor left
  out as incomparable, refused or over budget is named with the reason, and is not claimed to be
  slower.
- H1 or H2 failing in a whole shape (every size of it) narrows the claim to the shapes where it
  holds, and the loss is reported. A loss in a single cell is reported in that cell.
- H3 and H5 are not narrowed: failing either means v2 is not done.
- H4, H6 or H7 failing is reported as a loss of that hypothesis, and the paper does not make its
  claim.
- A cell without any competitor cannot be tested (section 5), and the claim says nothing about it.

## 9. The analysis

`analysis/analyse.py` computes every decision above except H5(a) and H5(c), whose evidence is the
named records. It reads the runs: the main grid with its `verified.jsonl`, the H6 T1 run, and the
H7 cost run. It writes the tables and `summary.json`. `analysis/macros.py` writes the paper's
macros (`results/macros.tex`) from `summary.json` alone, so every number of the paper comes from
the analysis. The MSVC costs of H7 are reported from `bench/ct_msvc.py`'s `tables.jsonl` as they
are. The analysis's tests pass on synthetic runs (`analysis/test_stats.py`, `test_decisions.py`,
`test_pipeline.py`). It ran on a development grid in WSL
(`lab/evidence/2026-09-30-W-analysis-r2-wsl-grid`).
Nothing is run again to change a decision.

## 10. Time

Measured durations, on L unless said (lab journal and the files named):
- Round 1's main grid: 6,202 processes from 09:10 to 18:54 on 2026-09-27, 9 h 44 min, 5.650 s per
  process on average.
- Its re-check of the 76 processes the agreement budget cut: 1 h 20 min 39 s, with 6 checks at
  once.
- Its exploratory runs (lab journal, 2026-09-30 04:06):
  - GitHub: 179 processes in 3 min 43 s, 1.246 s each;
  - miss-heavy, the whole grid at R = 10: 6,202 processes in 10 h 52 min, 6.308 s each;
  - the long vocabulary, m = 10,000 and 100,000 at R = 10: 2,443 processes in 8 h 58 min,
    13.213 s each;
  - the Zipf ring, the same cells: 2,443 processes from 19:42 to 04:06, 8 h 24 min, 12.378 s each.
- Its H7 cost run: 127 tables in 26 min 4 s, 12.31 s per table.
- Its H6 run: nine cells, two arms, 5 pairs each, 180 windows in 19 min 54 s, 6.63 s per window.
- Its MSVC costs on W: 65 compiles of 22 tables in 14 min 54 s.
- Round 2, 2026-09-30, at the native instruction set:
  - the rbench build of every arm (358 compile-time tables) and its gate, 6 min 52 s;
  - the server and t1gen builds and their gate, 10 s;
  - the rbench and server records, 1 h 57 min 37 s for the six (rbench 1,589, 2,258 and 2,841 s;
    the server 83, 122 and 159 s), and rbench's ASan record again after the fix, 1,586 s.

Estimates. Each row uses the round-1 average named in it, for every arm of round 2. The new arms
may be slower or faster, and round 1 was built without `-march`, so the native build may change
the averages too. The main grid has 23 arms at R = 16 in 35 cells, and 2 reference arms at R = 3
in 28 cells.

| Run | Processes (windows) | Average used | Estimate |
|---|---|---|---|
| main grid | 13,048 | main grid, 5.650 s | 20 h 29 min, and the build and gate, 7 min |
| the check on every query at the end of the main grid | at most 131 | measured (below) | 37 min to about 1 h |
| H7's costs on L: 358 tables at -j1, the budgets of 22 | | H7 cost run, 12.31 s per table | about 1 h 13 min |
| H7's costs on W: 22 tables with MSVC | | round 1's MSVC costs; a development compile of 2026-09-30 (below) | 15 to 20 min |
| H6 at T1: nine cells, three arms, 6 to 20 rounds | 324 to 1,080 windows | H6 run, 6.63 s | 36 min to 1 h 59 min |
| GitHub cell, R = 16 | 374 | GitHub, 1.246 s | 8 min |
| mixed-overlap without decoys, R = 16 | 1,864 | main grid, 5.650 s (round 1 never ran it) | 2 h 56 min |
| miss-heavy, R = 3 (R = 16) | 2,583 (13,048) | miss-heavy, 6.308 s | 4 h 32 min (22 h 52 min) |
| long vocabulary, R = 3 (R = 16) | 1,008 (5,194) | long vocabulary, 13.213 s | 3 h 42 min (19 h 4 min) |
| Zipf ring, R = 3 (R = 16) | 1,008 (5,194) | Zipf ring, 12.378 s | 3 h 28 min (17 h 52 min) |

On W, a development run of `bench/ct_msvc.py` on table seed 1 (lab journal, 2026-09-30 15:00) took
2 min 48 s for one 1,000-route table over its five compiles. At that rate the seven 1,000-route
tables alone take about 20 min, more than round 1's 14 min 54 s for all 22.

The check on every query at the end of the main grid comes from checks of every arm in every cell
of its scope, at the engineering pair (1, 2) on L on 2026-09-30, four at once
(`lab/evidence/2026-09-30-L-gaps`). That build had no `-march`.
- A check of every query took longer than the 120 s budget in nine cells. So at most 131
  processes of the main grid are cut and checked again:
  - actix-router at m = 100,000 in six shapes (132.6 to 238.8 s each; 96 processes);
  - Drogon at param-first m = 100,000 (166.8 s; 16);
  - net/http's ServeMux at wild m = 100,000 (155.9 s; 16);
  - regexmatcher-v1 at param-first m = 10,000 (2,245.5 s; 3).
- Their checks add up to 8 h 0 min of CPU time. With 16 at once, the slowest first, the re-check
  takes between 37 min 26 s (the longest check) and about 1 h (the total over L's 8 physical
  cores).
- Inside the grid, each cut process spends its 120 s budget on its agreement pass (131 x 120 s =
  4 h 22 min). Round 1's average time per process carries such processes in about the same share:
  76 of 6,202 there, at most 131 of 13,048 here.

Altogether, at the designs above:
- the main grid with its build and re-check: about 21 h 13 min to 21 h 36 min;
- H7's costs: about 1 h 13 min on L and 15 to 20 min on W;
- H6: 36 min to 1 h 59 min;
- the exploratory runs as section 7 sets them (the GitHub cell and no-decoy at R = 16, the three
  others at R = 3): about 14 h 45 min, and the re-checks their slow arms need.

Each run on L is a separate lablocked job, so they need not be consecutive.

## Appendix A. What each arm's timed lookup includes

The harness, for every arm (`bench/core/runner.hpp`):
- The timed loop calls the arm's own pass if it has one (the Go arms), else the harness's loop over
  the compact ring copy. The loop adds each route id, and each captured value's length and first
  byte, to a sink the compiler cannot drop.
- For an arm without a 405 of its own, a "no route" answer triggers a lookup of the same path under
  every other method that has routes. Any hit makes the answer 405. On the grid's all-hit rings the
  fallback runs only for a wrong answer; its test runs on every lookup.
- The allocation pass and the latency samples call each lookup through the harness, for every arm.
  So a Go arm's latency includes one cgo call per lookup.

Method step: "index" means the harness passes the method as an enum, and the adapter indexes one
router per method; "string" means the router takes the method's name.

| arm | the timed call | method step | captured values | 405 | loop; null |
|---|---|---|---|---|---|
| regexmatcher-v2 | `find_v2` (out of line), which calls `matcher::route::find` | index into v2's table | views into the path (pointer and length) | its own | harness; null |
| regexmatcher-v2-ct | the same, on the compile-time table | the same | the same | its own | harness; null |
| regexmatcher-v2-r1 | `find_r1` (out of line) | the same | views | its own | harness; null |
| regexmatcher-v1 | the wrapper's match, which calls v1's `match_with_groups` | index | offsets into the path; v1 returns a new result vector per call | harness | harness; null-no405 |
| radix, hash, std-regex | the in-repo lookup | index | views (hash: none) | harness | harness; null-no405 |
| Crow | `crow::Trie::find(path)` | index, one trie per method | Crow copies each value into a `std::string`; views into them | harness (Crow's own rule) | harness; null-no405 |
| Oat++ | `Router::getRoute` | index; Oat++'s HttpRouter uses a map by method | parameters as views (`getVariables()`); the catch-all tail through `getTail()`, which copies it into an `oatpp::String` | harness | harness; null-no405 |
| Boost.URL | `parse_path(path)`, then `router::find` | index | views into the path | harness | harness; null-no405 |
| r3 | `match_entry_createl`, `r3_tree_match_route`, `match_entry_free` (one match entry per lookup, as r3's examples do) | a method bit in the entry, one tree | views into the path | harness | harness; null-no405 |
| Drogon | the transcribed `route()`: a lower-cased copy of the path, the two maps, then `std::regex_match` over the regex routes | index | a new `vector<string>` per match, as Drogon builds it | harness | harness; null-no405 |
| Pistache | `sanitizeResource(path)`, then `findRoute` | index | `as<std::string>()` copies, Pistache's only public read | harness | harness; null-no405 |
| matchit | `Router::at` behind one C call | index | offsets into the path | harness | harness; null-no405 |
| actix-router | `Path::set`, then `Router::recognize` behind one C call | index | offsets into the path, not decoded | harness | harness; null-no405 |
| path-tree | `PathTree::find` behind one C call | index | offsets into the path | harness | harness; null-no405 |
| uWebSockets | `HttpRouter::route(method, path)`; the handler stores the id | string | views (`getParameters()`); none for `*` | harness | harness; null-no405 |
| glaze | `route_table::match(method, path)` | a switch to glaze's method | glaze returns decoded strings in a map; one find per name | harness | harness; null-no405 |
| cpp-httplib | `req.path.assign(path)`, then the method's matchers in order | index | `:name` values: copies in `path_params`; regex groups: views into the request's path | harness | harness; null-no405 |
| httprouter | `Router.Lookup(method, path)`, then the handler, in Go | string, one router | offsets into the path | the harness's rule, in Go | own; own |
| gin | the vendored tree's `getValue`, then the handlers, in Go | string, compared with each method tree | offsets; values found after a backtrack copied | the harness's rule, in Go | own; own |
| net/http | `ServeMux.ServeHTTP` on one reused request, in Go | string, in the request | the handler copies each `PathValue` | its own | own; own |
| chi | `rctx.Reset`, `methodMap`, `tree.FindRoute`, then the handler, in Go | string, a map to a method bit | offsets into the path | the harness's rule, in Go | own; own |

What remains unequal, stated rather than removed, because removing it would leave the router's API:
- Copies of captured values that the router's API makes (Crow, Oat++'s tail, Drogon, Pistache,
  glaze, cpp-httplib's named values) are in those arms' times. v2 returns views.
- The adapters of Oat++ and Pistache index one router per method, where the framework looks the
  method up in a map. This removes a step from those arms, never adds one. Boost.URL's example
  router, matchit and path-tree have no methods; their adapters keep one router per method.
- gin's adapter copies the values of a query resolved by backtracking into its buffer. Only
  mixed-overlap has such queries, and there gin is declared incomparable.
- v2's lookup is an out-of-line call, while header-only competitors can be inlined into the timed
  loop. This adds work to v2 only.
- The Go arms take the method as a string, inside the timed lookup; net/http's latency and
  agreement lookups also find their prebuilt request in a Go map, which its timed pass does not.
- r3 allocates and frees one match entry per lookup, as its API requires.

## Appendix B. Competitor configurations

Common builds:
- Every arm is compiled for L's own instruction set (`bench/cmake/isa.cmake`). On L these resolve
  to clang's target CPU znver3, rustc's znver3, and GOAMD64 v3 (lab evidence
  `2026-09-30-L-isa-native-check`).
- C and C++: clang 22.1.8, CMake Release (`-O3 -DNDEBUG`), `-std=c++23`, `-march=native`, no LTO.
  The flags are the same for every C and C++ target: v2, v1, the compile-time table, the ablation
  arm, the null arms, the reference arms and the competitors. The libraries fetched and built with
  them get the same flags (Oat++, Pistache, Boost.URL, r3 and PCRE2).
- Rust: `cargo build --release --locked`, with the harness's release profile: opt-level 3, fat LTO
  (`lto = true`), one codegen unit, `panic = "abort"` (`bench/arms/rust/Cargo.toml`). Cargo's
  default release profile has thin local LTO, 16 codegen units and unwinding. The Cargo Book
  (profiles) says fat LTO optimizes across all crates, and that more codegen units may produce
  slower code. So the harness's profile is at least cargo's default, and favors the Rust arms.
  The crate is compiled with `RUSTFLAGS=-C target-cpu=native`; Rust's standard library is the
  prebuilt one.
- Go: go1.27.1-X:nodwarf5, `go build -buildmode=c-archive -trimpath`, `CGO_ENABLED=1`,
  `GOAMD64=v3`, the highest x86-64 level L supports. glibc's loader on L reports v3 and v2 as
  supported and v4 not, and a program built with `GOAMD64=v4` refuses to start on L. The C that
  cgo compiles gets `-march=native` too. No profile-guided optimization: it needs a profile of a
  workload, and none is part of this design.

| competitor | build and run-time configuration | the library's documentation |
|---|---|---|
| Crow v1.3.4 | header only, `ASIO_STANDALONE`; log level Warning | no optimization advice; its setup page compiles with plain `g++ main.cpp -lpthread`; its logging guide sets Warning |
| Oat++ 1.3.1 | its own CMake, static; `OATPP_DISABLE_ENV_OBJECT_COUNTERS` on | its CMakeLists.txt (line 38): the option disables object counting "for Release builds for better performance" |
| Boost.URL 1.92.0 | the library and its example router, a static library | library default, not documented |
| r3, 2.0 branch at 83d362f | its seven sources compiled by the harness; PCRE2 10.49 by its CMake, 8-bit, static, no JIT | r3's README has no build flags; r3 never calls `pcre2_jit_compile`, so PCRE2's JIT would not apply |
| Drogon v1.9.13 | its lookup transcribed into the adapter, common C++ flags; the file's sha256 and line ranges in `pins.cmake` | its install guide asks for `CMAKE_BUILD_TYPE=Release` when building the library, which the harness does not build |
| Pistache v0.4.26 | its own CMake, Release, static, tests and SSL off | its README builds with meson's release build type; CMake Release is used here |
| matchit 0.9.2 | common Rust | library default, not documented |
| httprouter v1.3.0 | common Go | library default, not documented |
| gin v1.12.0 | common Go; the router tree vendored, called without gin's engine | its deployment page sets `GIN_MODE=release`, which governs debug output only; the vendored lookup reads no mode |
| net/http, Go 1.27.1 | common Go | no build advice |
| actix-router 0.5.4 | common Rust, default features | library default, not documented |
| uWebSockets v20.80.0 | header only; only `HttpRouter` compiled; `-march=native` | its README gives no flags; its own example build script uses `-march=native -O3` and LTO |
| glaze v9.0.0 | header only; its CMake adds nothing else on Linux; `-march=native` | its guide on performance recommends `-O2` or `-O3`, and `-march=native` when the program runs where it was built, as here |
| chi v5.3.2 | common Go; its package sources vendored, each with its sha256 | library default, not documented |
| path-tree 0.8.3 | common Rust | library default, not documented |
| cpp-httplib v0.58.0 | header only, no TLS, no compression | library default, not documented |

Why one instruction set for every arm, and why L's own:
- Two competitors document a native build as their best configuration: glaze's guide recommends
  `-march=native` when the program runs where it was built, and uWebSockets' example build uses it.
- Fairness needs the same instruction-set level for every arm, v2 included, so no arm gets it alone.
- It keeps H2's subtraction matched. The harness's loop around each lookup is compiled into each
  arm's translation unit, so a flag for one arm alone would change its loop and not its null's.
- LTO stays off for every C and C++ arm, v2 included; of their documentation, only uWebSockets'
  example build uses it.

Each build writes what these resolve to into `rb_isa.h`, a compiled input of every target, and each
result line carries the target CPU (`march`, `target_cpu`, `rust_target_cpu`, `goamd64`).

H7's MSVC costs on W use the flags of RegexMatcher's own compile-time-table test target, with no
`/arch` option. They are compiler measurements of code that never runs on L.

## Revision log

- 2026-10-01, the main grid's check on every query (deviation, approved by the coordinator before
  the repeat). The frozen text fixes the check but not how many checks run at once; section 10's
  "16 at once" was a time estimate with no memory budget. On L (15 GB), 16 actix-router checks at
  m = 100,000, up to 2 GB each, exhausted memory. The kernel killed 79 of the 115 checks (exit -9),
  all after the last measured cell, and none of the 115 reported a wrong answer (lab evidence
  `2026-10-01-L-publication-main-grid`). All 115 checks are repeated with 4 at once, untimed, by
  the same `verify_answers` binary from the run's own build (sha256
  adc3ecee37906df51540e36698d322f7b7425e0e0185037093c565f65179f5d4, checked before use; rbench
  sha256 28defc7b28bf2405b4ac2b45d0463adb0f86f77c627e8a995f5176eede4f2206), into a separate file,
  `verified-repeat.jsonl`. The original `verified.jsonl` is kept; the new file is archived with its
  own sha256, and the analysis reads the complete new file. The repeat checks answers only: no
  timing is re-measured or replaced. It repeats the frozen procedure after an infrastructure fault,
  and it can change H1's decision; that is why it waited for the coordinator. All later grids (the
  exploratory runs) run their check with 4 at once (`VERIFY_JOBS=4`), an operational setting.
- 2026-10-02, the paper's second macro file (no decision changes). Section 9 says
  `analysis/macros.py` writes the paper's macros from `summary.json` alone. The paper also needs
  numbers that `summary.json` does not carry: the per-cell rows of its tables, H7's costs, the
  exploratory runs, the ablation arm, the design's constants, the tool versions and the archives.
  `results/round2/macros.tex` stays as `macros.py` wrote it; a second file,
  `results/round2/macros-paper.tex`, is written after the run by `analysis/paper_macros.py` from
  the analysis's outputs in `results/round2`, the runs' evidence and records, and the unpacked main
  grid. It decides nothing, and an independent recomputation from the raw archives matched every
  value (fact-check of 2026-10-02).
- 2026-10-02, the conditional exploratory run of section 7 (H7's cell with the compile-time table
  copied into a heap block). Its condition held: at param-last m = 1,000, table seed 124 stood
  apart (ratio 1.1595, equal instructions). The run was not made in the frozen order, after the
  main grid. It was made afterwards on 2026-10-02, as an exploratory run that decides nothing,
  gated by records of its own (rbench-35554b313-L-{asan,tsan,msan}-ctheap), with its summary in
  `results/round2/explore_ct_heap.csv` (paper b1ae477); the paper reports it as such.
- 2026-10-02, how the paper mentions round 1 (no decision changes). Section 1 says the round-1 H6
  run is not mentioned in the paper; H6 says the bound 0.5 was chosen below that run's range "and
  the paper says so". The paper follows section 1: it says the bound was chosen before the run,
  informed by development data from an earlier build that it does not report. The Discussion also
  says, in words and without numbers, that development builds favoured v2 at wild m = 10, and that
  the run differs from them in the instruction set and the Go build level.
- 2026-10-02, the build of that conditional run (no decision changes). Section 7 runs exploratory
  grids from the gated build of the main grid. That build has no heap-block arm, so this run used a
  fresh build (paper 35554b3) that adds one opt-in arm, `regexmatcher-v2-ct-heap`, and changes no
  file the measured arms compile. The new arm was gated by its own records before the run; the
  other arms by the existing records, matched by inputs hash.
