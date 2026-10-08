# Hypotheses of round 2: proposal for a new pre-specification

Status: proposal, round 2 of P2. Written 2026-09-30; the design was approved on 2026-09-30
with the decisions in the revision log at the end, which the text below already carries.
`hypotheses.md` is frozen and is not edited: at the code freeze, section 3 becomes the new
frozen file `hypotheses-round2.md`, before any gated run on the seeds of section 3, and the
entry of section 6 goes into the revision log of `hypotheses.md`.

Words: "the private library", "v1" and "v2" as in `regexmatcher-v2.md`.

## 1. How round 1 is disclosed

Round 1 (the main grid of 2026-09-27, its re-verification, its exploratory runs, its H7 cost
run, and its H6 run of 2026-09-28) measured the round-1 header inside the private library's
build. Under the component model it becomes development data:
- it guided the engineering of round 2 (`engineering.md`) and is cited only there, and in the
  lab journal;
- no round-1 number appears in the paper as a result, and none is carried into round 2's
  analysis;
- its seeds are burned: round 2 uses new held-out seeds (section 3.3);
- the paper says, in its methods, that a development round measured a pre-release of the same
  lookup code with the same harness and design on other seeds, that it guided the changes the
  paper describes, and that its numbers are not reported;
- the round-1 H6 run is not mentioned in the paper (Alex's decision); it measured a server the
  paper no longer uses.

## 2. Changes from the frozen text, each with its reason

1. **The measured implementation is RegexMatcher v2**, the public library's next major version,
   not a router inside the private library (component model, D1). Arm names change:
   `regexmatcher-v2` (the run-time table, H1 to H4), `regexmatcher-v2-ct` (the compile-time
   table, H7). The private library's router arm, reported beside v2 in round 1, and its pre-v2
   router, a reference arm with its own binary, are dropped: both measured the private library.
   The reference arm on RegexMatcher's engine becomes `regexmatcher-v1`, same wrapper, same pin.
2. **Competitors.** The eleven of round 1 stay, at their round-1 pins unless a newer release
   exists at the freeze (checked then, and each change of pin listed). Five are added
   (section 4): uWebSockets' `HttpRouter`, glaze's `route_table`, chi, path-tree and
   cpp-httplib. One description is corrected: matchit is not "the router of axum" at the pinned
   version. matchit is the router library axum builds on; axum 0.8.9 depends on
   `matchit = "=0.8.4"` (`axum/Cargo.toml` at tag `axum-v0.8.9`, read directly 2026-09-30),
   and 0.9.2 is pinned only on axum's unreleased `main`. The arm keeps measuring matchit's
   latest release, 0.9.2. The frozen text's error is corrected through the revision log of
   `hypotheses.md` (section 6).
3. **R = 16 seed pairs instead of 10** (D9). With 10 pairs the smallest one-sided p-value of an
   exact paired test is 2^-10 = 9.77e-4, above Holm's first threshold for H1's family,
   0.025 / 35 = 7.14e-4, so no H1 cell could pass under an exact test whatever the data
   (`analysis/sensitivity.py`). Section 5 shows why 16 and not 12.
4. **New held-out seeds**, never used by any run (section 3.3).
5. **The clustered bootstrap is pre-specified**, clustered by table seed, and **the exact sign
   test is computed for every cell**. A cell passes only if both pass (section 3.4). In round 1
   both were post hoc (`analysis/sensitivity.py`), and the clustered interval crossed H7's
   margin at param-first m = 1,000.
6. **H4's reading is stated in the text**: per (shape, size) cell against the median of the
   competitors included in that cell, as round 1's analysis read it after the run.
7. **H5(a)** is tested in RegexMatcher v2's own suite. "A table of handlers mounted" in the
   private library's application object becomes a compile-time table of route declarations with
   handlers: the same check without the private library.
8. **H5(b)** names RegexMatcher v1 behind its wrapper instead of the private library's pre-v2
   router as the arm that fails the first two probes. In round 1 both failed the same two
   (`results/baseline.md`; the probe records of the main grid for the reference arm); round 2
   runs the probes again.
9. **H5(c) is HTTP/1.1 only.** The HTTP/2 part is dropped: the paper's server has no HTTP/2,
   and in round 1 that part never had green Linux evidence (its MSan record was red, and the
   fixed commit's L records were cancelled on 2026-09-29 when the plan changed; revision log
   of `hypotheses.md`, lab journal). The tests move to the paper's minimal server.
10. **H6 is re-specified for the paper's own server** (`minimal-server.md`): one binary with
    three router arms instead of one server built against two versions of the private library;
    RegexMatcher v1 behind its wrapper as the reference; a direction test and a carry-over test
    instead of the round-1 bounds, which described the private library's server. The minimum
    number of T1 pairs rises from 5 to 6 (D9, section 3.5).
11. **An ablation arm**, exploratory: the round-1 header renamed but not re-engineered
    (section 3.6), in every cell of the main grid, so that the paper can show what round 2's
    engineering contributed. It decides nothing.
12. **The design in time**: section 7.

## 3. The proposed pre-specification

The text below keeps the frozen wording of `hypotheses.md` wherever it still applies.

### 3.1 What is compared

- **RegexMatcher v2**, the route matcher of RegexMatcher's next major release
  (`regexmatcher-v2.md`), with routes added at run time. Routes are checked when the program is
  compiled; lookup is an exact-match table for a method whose routes are all literal and a
  trie over path segments for any other method, with no heap allocation. Arm
  `regexmatcher-v2`: v2's table behind one out-of-line call. It is the arm of H1 to H4.
- **RegexMatcher v2, compile-time table** (`regexmatcher-v2-ct`): the same routes declared as a
  `constexpr` table in a generated translation unit (bench/gen/), at m = 10, 100 and 1,000 for
  every shape and every table seed of this design. It shares its adapter with
  `regexmatcher-v2` (one class template); it is the arm of H7.
- **Competitors** (bench/cmake/pins.cmake has every pin): Crow v1.3.4 (crow::Trie), Drogon
  v1.9.13 (its lookup transcribed), Oat++ 1.3.1, Pistache v0.4.26, the Boost.URL 1.92.0 example
  router, r3 (2.0 branch), matchit 0.9.2 (Rust; matchit is the router library axum builds
  on, and axum 0.8.9 pins matchit 0.8.4; the arm measures matchit's latest release), httprouter
  v1.3.0 (Go), gin v1.12.0 (its router tree, vendored unchanged and called as gin's engine
  calls it), Go's net/http ServeMux with the patterns of Go 1.22 and later (Go 1.27.1), and
  actix-router 0.5.4 (Rust, the router of actix-web); and, added in round 2, uWebSockets'
  `HttpRouter`, glaze's `route_table`, chi, path-tree and cpp-httplib, each at a release pinned
  at the freeze and measured in its documented configuration (section 4). "The fastest
  competitor" of a cell is the competitor with the lowest median lookup time in that cell; it
  can differ from cell to cell.
- **Reference arms**, not competitors: `regexmatcher-v1` (RegexMatcher's engine at d16f30a8
  behind the pattern-to-regex wrapper), and the in-repo radix tree (radix), exact-match hash
  table (hash) and sequential std::regex (std-regex). Their scope is fixed here: hash and radix
  run in every cell in R = 16 processes; std-regex and regexmatcher-v1 run up to m = 10,000 in
  3 processes per cell, on the first three pairs of section 3.3. On the static shape, whose
  one method has only literal routes, v2 answers from its exact-match table, the mechanism of
  hash; that statement covers a method whose routes are all literal only.
- **Null arms**, not compared: as frozen. `null` is one out-of-line call that does not match;
  each Go arm has its own null pass; every cell names the null it is paired with.
- **Ablation arm**, exploratory, not compared: `regexmatcher-v2-r1`, the round-1 header with its
  namespace and macro prefix renamed and nothing else changed (step E1 of
  `regexmatcher-v2.md`), vendored into the harness under a namespace of its own so that it links
  beside v2. It runs in every cell of the main grid in R = 16 processes and decides nothing.

### 3.2 Cells and measurements

As frozen: a cell is one arm, one shape and one size; the seven shapes of bench/core/table.hpp;
m = 10, 100, 1,000, 10,000 and 100,000; a ring of 4,096 all-hit queries; the per-cell
measurements of the frozen text (median ns per lookup over nanobench epochs; instructions,
branch misses and cycles per lookup; L1d, L2 and L1 DTLB misses and every dispatch-stall
unit-mask bit counted on its own; latency percentiles; allocations outside timed loops; build
time; heap bytes held; ffi_call_ns for the Go arms), the compact ring copy, the agreement of
every process with bench/semantics.json at every size, the reporting of "incomparable",
"refused at insert" and "refused" arms, and the budget of 1,800 s per process as a stopping
rule. Added per cell: the bytes allocated during the build (`build_alloc_bytes`) and the page
offsets of the four arrays of v2's table. The timed passes over a slow arm are cut to a prefix
of the ring (`MeasureOptions::pass_budget_s`), as in round 1, and the text now says so.

### 3.3 Seeds and order

R = 16 processes per cell on L, pinned by lab/bin/pin.sh, every arm in one binary. Process k
of a cell (k = 0 to 15) uses the pair (111 + (k mod 8), 211 + ((k + floor(k / 8)) mod 4)):

(111, 211), (112, 212), (113, 213), (114, 214), (115, 211), (116, 212), (117, 213), (118, 214),
(111, 212), (112, 213), (113, 214), (114, 211), (115, 212), (116, 213), (117, 214), (118, 211).

Sixteen distinct pairs; each of the eight table seeds twice, with two different ring seeds;
each ring seed four times. The seeds are held out: round 1 used table seeds 1 to 5 and 101 to
105 and ring seeds 2 to 4 and 201 to 203, and the development profiling of 2026-09-30 used
table seeds 1 and 101 to 105 and ring seeds 2 and 201 to 203. Engineering and iteration runs of
round 2 use table seeds 1 to 5 and ring seeds 2 to 4. The agreement test checks the design's
table seeds for correct answers only, on a ring of its own, and times nothing; `gen-ct`
compiles a table for each. The order of the processes is shuffled with a seed fixed at the
freeze. Every process runs on CPU 2 of L (physical core 1, its SMT sibling idle); the run
records the CPU and its siblings, transparent huge pages, the NMI watchdog, and the compilers
and runtimes of every arm.

### 3.4 Statistics of H1 and H7

A comparison of arms in a cell is paired by seed pair; its statistic is the median over the
pairs of the per-pair ratio. Two computations, both pre-specified, both reported for every
cell:
- **the clustered BCa interval**: 10,000 resamples of the eight table seeds (a cluster keeps
  its two pairs, and within a pair an arm's values stay together), bias correction with ties
  counted as half, acceleration from the jackknife over clusters, resampling seed fixed at the
  freeze; for H1 the fastest competitor is chosen again in every resample. The one-sided
  bootstrap p-value is the level at which the upper bound equals the margin. The interval over
  pairs of round 1 (`analysis/h1_stats.py`) is reported beside it;
- **the exact sign test**: X is the number of pairs whose ratio is below the margin; under H0
  "the median ratio is at least the margin", X is binomial with 16 and 1/2 at the boundary;
  p = P(X >= x).

For H1, each computation runs Holm's step-down over the 35 cells at family-wise alpha = 0.025,
one-sided, an untested cell entering with p = 1. **A cell passes if it passes under both.** If
they disagree in a cell, both are reported and the cell does not pass.

### 3.5 Hypotheses

H1. Lookup time, non-inferiority. In every cell in which a competitor holds the table,
    RegexMatcher v2 (`regexmatcher-v2`) is not slower than the fastest of them. The statistic
    of a cell is the median over the seed pairs of v2's time divided by that of the competitor
    with the lowest median in the cell. The family is the 35 cells of the seven shapes and five
    sizes. In each cell, the null hypothesis "the ratio is at least 1.02" is tested as section
    3.4 states. H1 holds overall if at least 32 of the 35 cells pass and the upper bound of the
    unadjusted 95% clustered BCa interval is at most 1.10 in every cell. Superiority (the null
    hypothesis "the ratio is at least 1.00") is tested the same way, Holm-adjusted over the
    family on its own, and reported per cell; it decides nothing about H1. A cell that
    analysis/cells.py fails does not pass.

H2. Work per lookup. As frozen, with `regexmatcher-v2` as the arm: in every cell, v2 executes
    no more instructions per lookup than the fastest competitor of that cell and takes no more
    branch misses per lookup than the median competitor (medians over the 16 processes),
    instructions compared net against net, raw counts beside; strict, no tolerance and no
    interval; a loss is reported in the cell where it occurs, with the memory-side counters.

H3. No allocation. RegexMatcher v2 makes 0 heap allocations per lookup in every cell, captured
    values included (they are views into the request path).

H4. Build and memory are not the price. At every size, v2's build time is at most the median
    competitor's, and at m = 100,000 it is below 1 s. The heap bytes its table holds are at most
    twice the smallest competitor's. H4 is read per (shape, size) cell against the median of the
    competitors included in that cell (analysis/cells.py), on the cells' medians over processes.
    Heap bytes are malloc's live bytes after the build (C, C++ and Rust arms) plus, for the Go
    arms, the Go heap's live bytes after a collection.

H5. Checked when compiled, correct when run.
    (a) A negative-compilation suite of malformed routes fails to compile, each for the stated
        reason: an unclosed or empty parameter, a catch-all that is not last, a repeated
        parameter name, an unknown type, an empty segment, a missing leading '/', a literal byte
        that is not a pchar, a handler whose parameter count or types do not match the pattern,
        and two routes in one compile-time table that match exactly the same paths, both for
        handlers given one by one and for a compile-time table of route declarations with
        handlers. Each case is a CTest entry with WILL_FAIL in RegexMatcher v2's suite that also
        checks the diagnostic names the reason, so the suite reports 100% passed.
    (b) v2 passes every probe of bench/core/probe.cpp: the most specific route wins in either
        registration order, every RFC 3986 pchar is accepted in a parameter and returned as
        sent, a trailing slash is strict, and a path that matches only under another method
        gives 405. RegexMatcher v1 behind its wrapper fails the first two.
    (c) Over HTTP/1.1, HEAD on a path only GET routes match is served by the GET route with
        the head of the response only, and a 405's Allow lists HEAD when it lists GET (RFC 9110
        sections 9.1 and 9.3.2); tests in the suite of the paper's minimal server.

H6. v2's faster lookup reaches the client. Measured at T1 on L, over loopback, with the paper's
    minimal HTTP/1.1 server (`minimal-server.md`), one binary with three router arms: v1
    behind its wrapper (the reference), v2, and null.
    (a) Direction: in each of nine cells (the seven shapes at m = 10; rest and param-last at
        m = 10,000), the lower bound of the 95% BCa interval of the req/s ratio v2 / v1 is above
        1.00. (a) holds only if all nine lower bounds are above 1.00.
    (b) Carry-over: in each of the nine cells, the lower bound of the 95% BCa interval of
        D_meas / D_T0 is at least 0.5. D_meas = 1/X_v1 - 1/X_v2 is the measured difference in
        time per request, X the arm's req/s; D_T0 = t_v1 - t_v2 is the difference of the two
        arms' median lookup times in round 2's T0 grid, in the cell of the same shape and size
        at pair (111, 211), the pair whose table and ring H6 serves. (b) holds only if all nine
        hold.
    Reported beside each cell, not tested: the null arm's time per request, 1/X_null; the
    ratio predicted from T0, P = (1/X_null + t_v1) / (1/X_null + t_v2); and the measured ratio
    over P.

    Development data informed (b): in round 1's T1 run, with another server and another pair
    of routers, the measured difference per request was 1.04 to 2.25 times the difference of
    the T0 lookup times, over its eight comparable cells (`results/tab_h6.csv`, column
    `diff_ratio`; mixed-overlap was not comparable). The bound 0.5 was chosen below that range.
    The paper says so. D_T0 is one value per cell (v1's reference arm runs the first three pairs
    only, and H6's pair is one of them), so the interval of (b) covers the variation of T1 only.

    Servers and targets: routes of the T0 generator at table seed 111, every route answering
    with the fixed 13-byte body, and GET / for lab/t1's probe; targets from t1gen --paths, one
    per route, each parameter filled as the T0 ring fills it (ring seed 211), in an order
    shuffled with that seed; GET / not in the file. Design (lab/t1, t1.py): one server core,
    CPU 14 of L (its SMT sibling CPU 15 idles), one worker; t1gen on CPUs 2 to 13 with 64
    connections, keep-alive, one request in flight per connection; a fresh server per window,
    probed with one request, a 1 s warm-up and a 5 s window; req/s is completed 2xx responses
    over the measured wall time. Mirrored rounds, v1, v2, null, null, v2, v1, one round per
    pair, v1 the reference. Sequential stopping as t1.py implements it, at least 6 pairs and
    at most 20. Invalid windows as t1.py marks them, listed with their reasons, and a pair with
    an invalid window is left out.

    Statistic: per pair, each arm's mean req/s over its two windows; the ratio v2 / v1, and
    D_meas from the same means; per cell, the median over pairs with its two-sided 95% BCa
    interval over pairs, computed as for H1 (10,000 resamples, fixed seed, ties as half,
    acceleration from the jackknife). No multiplicity adjustment: (a) and (b) each require
    every one of their cells, so each claims only what every one of its tests shows. With at
    least 6 pairs, an exact sign test of a cell can reach p = 2^-6 = 0.0156, below 0.025.

H7. A compile-time table is not slower. On the same routes and the same ring, the
    compile-time table is not slower than v2's table built at run time: in every cell measured,
    the ratio (compile-time / run-time, median ns per lookup) passes both computations of
    section 3.4 at the margin 1.02, each at one-sided alpha = 0.025 per cell (the 95%
    clustered BCa upper bound at most 1.02, and the exact sign test, which needs 13 of 16 pairs
    below 1.02). H7 covers m <= 1,000 only: the seven shapes at m = 10, 100 and 1,000, 21 cells;
    the compile-time arm refuses larger tables by design. Its costs are reported with it, as
    results: the compile time of each table's translation unit and its object size from a
    fresh build at -j1 (bench/ct_costs.py). The object size is the sum of the object file's
    loadable sections, text, rodata, data and bss, named per ELF (`.text*`; `.rodata*` and
    `.data.rel.ro*`; the other `.data*`; `.bss*`), with the file size and its padding reported
    beside it: the tables are aligned to a page (C2, `engineering.md`, section 3.4), and that
    alignment pads the file without adding memory the lookup touches. Clang's
    constant-evaluation budget per table (bench/ct_steps.py, table seed 111 of every shape and
    size, and the GitHub table); MSVC's budget and compile memory from single compiles on W,
    reported as such.

### 3.6 Exploratory, not hypotheses

- Miss-heavy rings: the ratio v2 / fastest competitor per shape when half the queries miss.
- The GitHub API table of go-http-routing-benchmark (203 routes), one cell.
- At m = 10,000 and 100,000: the long-literal vocabulary and a Zipf-distributed ring.
- mixed-overlap without the decoy queries (NO_DECOY), where gin takes part.
- The ablation arm `regexmatcher-v2-r1` in every cell of the main grid (section 3.1): the
  ratio of v2 to it per cell, for lookup time, instructions, build time and heap bytes, reported
  as what round 2's engineering contributed.
- Only if an H7 cell shows a table seed apart from the others: that cell again with the
  compile-time table copied into a heap block in the same binary (`engineering.md`, 3.4).

Dropped from round 1's list, with the reason: the rings of 65,536 and 1,048,576 queries and the
ring layout before the compact copy. Both concern the harness's design, round 1 answered them
as development data, and they took most of round 1's exploratory queue on L.

### 3.7 What would count against the paper's claim

As frozen: H1 or H2 failing in a whole shape narrows the claim to the shapes where it holds, and
the loss is reported. H3 and H5 are not narrowed: failing either means v2 is not done.

## 4. Competitors added in round 2

A survey on 2026-09-30 applied five rules: a lookup callable without a running server (or
transcribable from source), captured path parameters, a pinnable release, evidence of wide use
or of a state-of-the-art claim, and a language the harness reaches (C, C++, Rust through a C
interface, Go through cgo). Its full report, with every source URL, is
`competitor-survey.md`. The facts in the table come from that survey's reads (a research agent,
web reads only) and were not checked again, except the axum correction of section 2; each is
read again at its source before the freeze. The URL column gives the main source; releases,
licences and stars came from the repositories' API pages listed in the survey.

| Candidate | Release | Licence | Mechanism (file read) | Source |
|---|---|---|---|---|
| uWebSockets `HttpRouter` (C++) | v20.80.0 | Apache-2.0 | segment trie, the method first, children static then `:` then `*`, depth first with backtracking (`src/HttpRouter.h`) | https://github.com/uNetworking/uWebSockets/blob/v20.80.0/src/HttpRouter.h |
| glaze `route_table` (C++23) | v9.0.0 | MIT | exact-match map for static paths, then a segment trie with one parameter and one wildcard child per node, parameter checks by function, allocations per lookup (`include/glaze/net/http_router.hpp`) | https://github.com/stephenberry/glaze/blob/v9.0.0/include/glaze/net/http_router.hpp |
| chi (Go) | v5.3.2 | MIT | radix trie with static, regexp, parameter and catch-all nodes; public `Mux.Find` (`tree.go`) | https://github.com/go-chi/chi/blob/v5.3.2/tree.go |
| path-tree (Rust) | 0.8.3 | MIT OR Apache-2.0 | compressed prefix tree, static and parameter children, backtracking (`src/node.rs`) | https://crates.io/api/v1/crates/path-tree |
| cpp-httplib (C++) | v0.58.0 | MIT | per-method list in registration order, first match wins, `PathParamsMatcher` for `/:name` (`httplib.h`) | https://github.com/yhirose/cpp-httplib/blob/v0.58.0/httplib.h |

All five are added (decided 2026-09-30). uWebSockets is the most used C++ router with a
standalone API and a design not yet in the paper; glaze is the closest like-for-like (C++23,
header-only, typed checks, the same precedence); chi and path-tree bring a widely used Go
router and a Rust router that matchit's own published benchmark lists, through the existing
interfaces. cpp-httplib is a competitor, not a reference arm: a real, widely used router,
measured in its documented configuration. It is a linear, order-dependent matcher with no
catch-all without a regular expression, so where its semantics differ from the design's the
difference is declared in `bench/semantics.json` before the freeze, as for round 1's arms. Rejected by the survey, with the failing rule: Beast and POCO (no router), h2o
(prefix match only, no releases since 2019), lithium (no release), mongoose (no route table),
and several Go and Rust routers without evidence of wide use.

Cost of each addition: a pin, an adapter, its answers checked against bench/semantics.json on
the engineering seeds before the freeze (and any declared difference written there), its
sanitizer coverage (header-only C++ arms are instrumented like the others; chi and path-tree
join the FFI arms' declared MSan gap in bench/coverage.json), and 35 x 16 = 560 more processes
in the main grid (section 7).

## 5. Why R = 16

Exact sign test, one-sided, H1's family of 35 cells at family-wise alpha = 0.025; Holm's first
threshold is 7.14e-4. "Cells" is how many cells may have that count and still all pass, when
every other cell has a smaller p.

| R | 2^-R | one pair above the margin | two pairs above | three pairs above |
|---|---|---|---|---|
| 10 | 9.77e-4: no cell can pass | | | |
| 12 | 2.44e-4 | p = 3.17e-3, up to 7 cells | p = 1.93e-2, 1 cell | p = 7.30e-2, none |
| 14 | 6.10e-5 | p = 9.16e-4, up to 27 cells | p = 6.47e-3, up to 3 cells | p = 2.87e-2, none |
| 16 | 1.53e-5 | p = 2.59e-4, all 35 | p = 2.09e-3, up to 11 cells | p = 1.06e-2, up to 2 cells |

For H7 (every cell at one-sided 0.025): R = 12 needs 10 of 12 pairs below the margin, R = 16
needs 13 of 16. In round 1, every H1 cell had all 10 pairs below 1.02 (largest pair ratio
0.946), and six H7 cells had 8 or 9 of 10 (`results/sens_h1.csv`, `sens_h7.csv`). R = 16 lets
every H1 cell carry one noisy pair, and gives the clustered bootstrap eight clusters instead of
five. R = 12 would be the minimum that satisfies D9.

## 6. Proposed revision-log entry for `hypotheses.md`

To be committed when Alex approves this proposal, before any gated run on the new seeds:

> - 2026-09-30, the plan of the PhD changed (component model, 2026-09-29): each paper measures
>   its own minimal implementation of what it studies, and P2's subject is the route matcher of
>   RegexMatcher v2, the public library's next major version. Correction to "What is compared":
>   matchit 0.9.2 is not the router of axum's released versions; matchit is the router library
>   axum builds on, axum 0.8.9 pins matchit 0.8.4, and round 1 measured matchit's latest release.
>   Round 1 (the runs of 2026-09-27 and 2026-09-28) measured a pre-release of the same lookup code
>   inside another code base; it is development data, not reported as results, and its seeds are
>   not reused. Round 2 is pre-specified in `hypotheses-round2.md`, frozen before its run, with
>   these changes, each with its reason there: the arms of v2 renamed, and two arms of round 1
>   dropped; matchit's relation to axum corrected; R = 16 pairs on sixteen new held-out table
>   seeds and ring seeds, so that an exact paired test can pass Holm's threshold (D9); the BCa
>   bootstrap over those independent pairs and the exact sign test pre-specified, a cell passing
>   only under both; five competitors added; every arm built for L's own instruction set
>   (znver3); a second null arm, so that the harness's 405 test is netted out of the arms it
>   applies to; one declared kind of wrong answer per semantic difference; every process checked
>   on every query within the run; an exploratory ablation arm; H4's per-cell reading written into
>   the text; H5(a) in RegexMatcher's suite; H5(c) over HTTP/1.1 only, the HTTP/2 part dropped
>   because the paper's server has no HTTP/2 and that part never had green Linux evidence; H6
>   re-specified for the paper's own minimal server with v1 behind its wrapper as reference.

## 7. Time on L

Round 1's main grid ran 6,202 processes from 09:10 to 18:54 on 2026-09-27, 9 h 44 min
(lab journal; `plan.txt` of the run): 17 arms at R = 10 in 35 cells (5,950 processes) and three
reference arms at R = 3 in 28 cells (252). That is 5.65 s per process on average. Assuming the
same average for every arm of round 2 (it is not: actix-router's 60 processes at m = 100,000
each spent the 120 s agreement cut, and new arms may be slower), the main grid would take:

| Arms at R | Processes | Time |
|---|---|---|
| 16 arms (null, hash, radix, two v2 arms, eleven competitors) at R = 12, 2 reference arms at R = 3 | 6,888 | 10 h 48 min |
| the same at R = 16 | 9,128 | 14 h 19 min |
| with four added competitors, R = 12 | 8,568 | 13 h 26 min |
| with four added competitors, R = 16 | 11,368 | 17 h 50 min |
| **as decided: five added competitors and the ablation arm (22 arms), R = 16** | **12,488** | **19 h 35 min** |

Beside the grid: the answer re-verification of processes the agreement cut stopped early (it
took minutes in round 1), the H7 cost run (round 1: 26 min for 127 tables; round 2's eight table
seeds give 169 tables at -j1, more if the engineering seeds' tables stay in the binary), the exploratory cells of 3.6, and H6 at T1 (round 1: 20 min for
nine cells of two arms at 5 pairs; round 2 has three arms and at least 6 pairs).

## Revision log

- 2026-09-30: first version, for review.
- 2026-09-30, the design approved with these decisions (the text above carries them):
  1. both the clustered bootstrap and the exact sign test decide: a cell passes only under both;
  2. R = 16 on the new seeds;
  3. H6(b) keeps its bound 0.5, and the text discloses that round-1 development data informed it
     (1.04 to 2.25 times the lookup difference, `results/tab_h6.csv`);
  4. five competitors are added, cpp-httplib among them as a competitor measured in its
     documented configuration; matchit is described as the router library axum builds on, and
     the frozen text's error is corrected through the revision log of `hypotheses.md`;
  5. an exploratory ablation arm, the round-1 header renamed but not re-engineered, runs in the
     main grid;
  6. the exploratory set without the ring sizes and the ring layout is confirmed.
  The main grid's estimate becomes 12,488 processes, 19 h 35 min at round 1's average time per
  process. Version, tags, the engine commits, the licence and the public push wait for Alex.
- 2026-09-30, second milestone (paper-typed-routing aa869d1 to d9268c4), where the harness
  stands against the text above:
  1. Section 3.3's seeds are in `bench/run_grid.sh` (the sixteen pairs, R = 16) and in
     `bench/main.cpp`; the compile-time tables of table seeds 1 and 111 to 118 and the GitHub
     table are generated (`bench/gen`, 190 files).
  2. Section 4's five competitors have adapters. Their archives are pinned by commit, URL and
     sha256 in `bench/cmake/pins.cmake`; path-tree's release archive and that of its one
     dependency, smallvec 1.16.2, are the crates on crates.io, pinned by their sha256 in
     `Cargo.lock` and recorded in `pins.cmake`. chi is searched as its Mux searches a request
     (a shim over the tree search, `bench/arms/go/chi/rbshim.go`), since `Mux.Find` returns the
     matched pattern, not the endpoint. cpp-httplib has no catch-all syntax; its documented
     way, a regular-expression route ending in `(.+)`, stands for the catch-all.
  3. Agreement in WSL with gcc 14.2 (table seeds 1, 111 and 112, m = 10 to 1,000, every shape
     and the GitHub table; lab evidence `2026-09-30-W-regexmatcher-v2-build-rework`): glaze
     and cpp-httplib agree in every case; uWebSockets differs at wild only, where its `*`
     captures no value, and that difference is declared in `bench/semantics.json`. clang
     18.1.3 cannot build glaze in WSL (glaze needs `std::expected`, which libstdc++ 14 does not
     offer to clang 18); the measured builds use clang 22.1.8 on L. chi and path-tree compile
     on W and are checked on L; `bench/coverage.json` declares their MSan gap.
- 2026-09-30, C2 (`engineering.md`, revision log): the compile-time tables of `bench/gen` are
  declared aligned to a page, so that the two arms of H7 put every element at the same page
  offset. The object file of each compile-time table then grows by 3,328 to 3,392 bytes (the
  padding to the section's alignment; in WSL, the 22 tables of table seed 1 and github), while
  every section keeps its size. H7's cost "object size per table" (section 3.2 and the frozen
  text) must therefore say what it measures before the freeze: proposed, the sizes of the
  object's sections (`size -A`, as `bench/ct_costs.py` already records them), with the file
  size and its alignment padding reported beside them. For Alex.
- 2026-09-30, H7's object size decided (by the coordinator, as methodology): the sum of the
  loadable sections, text, rodata, data and bss, named per ELF, with the file size and its
  padding beside it, because page alignment adds file padding that does not reach memory the
  lookup touches. H7's text above says so, and `bench/ct_costs.py` records `data_bytes`,
  `bss_bytes` and their sum with text and rodata, `loadable_bytes`. In WSL (clang 18.1.3)
  `loadable_bytes` of all 190 compile-time tables is equal before and after C2, while each
  file grows by 3,328 to 3,392 bytes. This settles the question the entry above left for Alex.
- 2026-09-30, target (b) (`engineering.md`, revision log): no change to the lookup passed its
  adoption rule on L, so the lookup of round 2 is round 1's (C2's, byte for byte the same code
  from E1 on). H2 at mixed-disjoint m = 10 is expected to be lost again: on L at the engineering
  pairs, v2's net count there is 527.8 and 530.8 against gin's 513.8 and 520.5 (lab evidence
  `2026-09-30-L-slot3`). The pre-specification keeps H2 as it is, and the paper reports the cell.
- 2026-09-30, pins before the freeze (section 3.1: each change of pin listed). A read of every
  pinned project's release page (lab evidence `2026-09-30-W-pins-freshness`) found every
  competitor at its latest release, and PCRE2, the library r3 is built with, at 10.48 while 10.49
  came out on 2026-09-28. Counting PCRE2's calls during r3's lookups (lab evidence
  `2026-09-30-L-r3-pcre2-path`) showed it on r3's lookup path: in the rest shape, 6,551 to 8,001
  calls of `pcre2_match` per 4,096 lookups at every size, and in mixed-overlap, where r3's answers
  are a declared disagreement, 4,315 to 6,984. So the pin moves to PCRE2 10.49 (the release
  page's sha256 of the archive, 53c156e1...; coordinator's rule), and rbench's and the server's
  sanitizer records are made again (the gates match the whole `pins.cmake`); RegexMatcher's
  records carry no pins and stand.
- 2026-09-30, the audit of the draft (coordinator's decision M1): the exact sign test needs
  independent pairs, and the design's sixteen pairs shared eight table seeds (and four ring seeds).
  The design becomes sixteen distinct table seeds and sixteen distinct ring seeds, one pair each:
  pair k is (110 + k, 210 + k), k = 1 to 16, table seeds 111 to 126 and ring seeds 211 to 226.
  Table seeds 119 to 126 and ring seeds 219 to 226 had been used by no run, timed or not (every
  run record on W and L scanned). `bench/gen` holds the compile-time tables of the new table seeds
  (168 files; the 190 existing ones regenerate byte for byte); `bench/main.cpp`'s `kTableSeeds`,
  `bench/run_grid.sh`'s pairs and `analysis/cells.py` follow. The bootstrap is still clustered by
  table seed, which is now by pair, so the separate interval over pairs is dropped. H6's pair stays
  (111, 211), the first pair.
- 2026-09-30, the audit's other findings, applied (coordinator's decisions; `hypotheses-round2.md`
  rewritten, not frozen):
  1. B1: rbench's and the server's records made again at paper c6722e5, after M1 and the code fixes
     below, with PCRE2 10.49; the three CHECK_ONLY gates and the io_uring check run again.
  2. M2: H1 stays non-inferiority at 1.02; "faster" rests on the superiority family alone;
     competitors left out of a cell (incomparable, refused, over budget) are not in "the fastest";
     the claim's scope is L, one core, clang 22.1.8.
  3. M3: H6's validity and stopping rules are in the text; `t1.py --valid-pairs-only` counts only
     valid pairs toward the minimum and the stop (Papers f10b828, with a test).
  4. M4: H7's MSVC costs stay, measured on W by `bench/ct_msvc.py` (22 tables, MSVC 19.51.36246, one
     compile at a time, budget, peak memory, object size); compile costs need no sanitizer record.
  5. M5: the seed statements say exactly how each held-out seed was used.
  6. M6: a table of what each arm's timed lookup includes (Appendix A); the Oat++ adapter reads
     its parameters as views; what stays unequal is stated.
  7. M7: uWebSockets' missing catch-all value is a declared semantic difference; it takes no part
     in the wild cells, and its adapter does not compute the value.
  8. M8: each competitor's configuration with its source (Appendix B); Oat++'s
     `OATPP_DISABLE_ENV_OBJECT_COUNTERS` on; Drogon's transcribed file hashed in `pins.cmake`.
     `-march=native` (glaze's guide, uWebSockets' example build) is applied to no arm; left for
     Alex.
  9. The minors: among them a second null arm without a 405 of its own (m27), a kind per declared
     disagreement (m28), the Go runtime's GOMAXPROCS and collections recorded (m25), the timed
     functions' addresses recorded (m29), and every sentence of the draft at 40 words or fewer (m31).
  The proposed entry of section 6 now names the bootstrap over independent pairs instead of the
  clustered one.
- 2026-09-30, the instruction set (coordinator's decision, methodology): every arm is built for
  L's own instruction set. C and C++ targets, v2, v1, the ablation arm, the null arms, the
  compile-time table and the fetched libraries included: `-march=native` (znver3 on L). The Rust
  crate: `-C target-cpu=native` (znver3). The Go archive: `GOAMD64=v3`, the highest level L runs (a
  v4 program refuses to start there), with `-march=native` for the C that cgo compiles. Reasons: two
  competitors document native builds as their best configuration (D2), fairness needs one
  instruction-set level for every arm, and it keeps H2's null subtraction matched. The minimal
  server compiles v2 and v1, so it follows; t1gen is not an arm and stays. The resolved values go
  into a generated `rb_isa.h`, a compiled input of every target, so the records gate ties them.
  rbench's and the server's records are made again (paper 4cc42bf), the gates run again, and the
  objdump check at C2 is made again at the native flags. The scope of the claim adds "L's own
  instruction set" (`hypotheses-round2.md`, sections 1, 2 and 8, Appendix B).
- 2026-09-30, the records for the native instruction set: rbench's and the server's six records at
  paper 4cc42bf are green. The first gate run refused the three Rust arms: their digest header
  named the whole RUSTFLAGS, which under ASan includes `-Zsanitizer=address`, so the ASan build and
  the measured build digested differently. Paper 90beca4 makes the digest name the instruction-set
  flags only, and rbench's ASan record was made again (`rbench-90beca488-L-asan`); the TSan, MSan
  and server records at 4cc42bf match by inputs hash. The gates then passed, the objdump check at
  C2 is identical at the native flags, and a build without `-march` is refused by the gate.
- 2026-09-30, section 6's proposed entry for round 1's revision log now also names the sixteen
  table seeds, the instruction set, the second null arm, the declared kinds and the check on every
  query within the run.
