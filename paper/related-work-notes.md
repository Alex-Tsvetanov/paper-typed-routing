# P2 related work: working notes

Working notes for the related-work section of P2, "Compile-time-checked HTTP routing at the
speed of the fastest tries". Not paper prose. Written 2026-09-27.

How each source was checked:
- Papers: DOI metadata from `https://api.crossref.org/works/<doi>`. What a paper contributes is
  taken from its abstract (OpenAlex record) or from the publisher's page, as stated per entry.
  Full texts were not read unless stated. A sentence about a paper's content therefore says no
  more than its abstract says.
- Software: tag, commit, date and licence from the GitHub API or crates.io, read on 2026-09-27.
  Every version is the pin of `bench/cmake/pins.cmake`, and every pinned commit matches its tag.
  Claims about how a competitor matches come from its README or source at that tag, read on
  2026-09-27, and the file is named.
- Pages and WG21 papers: the official page or PDF was read.

The keys are those of `paper/refs.bib`. Relation labels: "builds on", "differs from",
"compares against", "background" (cited for a definition or a method, no claim of novelty).

## (a) Tries, URL routing and router benchmarks

- `delabriandais1959file`, `fredkin1960trie`. The first descriptions of the digital search
  tree (Fredkin's name "trie"). Background: router v2's parameter routes live in a trie.
- `morrison1968patricia`. PATRICIA, the compressed binary trie that skips single-branch nodes.
  Differs from: router v2 does not compress paths. Path compression was built and measured in
  this round and rejected (design/router-v2.md, "Path compression, tried and not adopted").
  The radix trees of httprouter and gin are compressed tries in this line.
- `aoe1989doublearray`. The double-array trie, a compact flat array encoding of a trie.
  Background for flattened tries. Router v2 flattens its trie into contiguous node, edge and
  label arrays after the build; it does not use the double-array encoding.
- `heinz2002burst`. The burst trie for large sets of strings in memory: about the memory of a
  binary search tree, as fast as a trie, slower than a hash table, keys kept near sorted
  (abstract). Background: mixing trie nodes with other containers is an older idea than router
  v2's hashed edges.
- `leis2013art`. The adaptive radix tree picks a node layout by the number of children, and
  its abstract reports lookup comparable to hash tables. Builds on the same idea: router v2
  scans up to 8 literal children linearly and hashes above 8. ART keys on bytes; v2 keys on
  whole path segments and adds typed-parameter and catch-all children with a fixed precedence.
- `zhang2015urlrouting`. Peer-reviewed URL routing paper (WISA 2015). Per its abstract: routes
  in a trie searched depth first instead of a table of regular expressions, static segments in
  a hash table, and about 10% of the time of the ASP.NET routing module with many routes.
  Closest in structure to router v2 (a segment trie with hashed literal segments). Differs:
  the abstract reports no compile-time checking, no allocation claim, and a comparison with
  one table-based router only.
- `dsouza2018htu`. Work-in-progress paper (SOCA 2018): a hash-trie for REST URL matching,
  embedded in an HTTP server. The abstract gives no numbers. Related structure; P2 differs by
  measuring against current production routers under pre-registered hypotheses.
- `zeng2017mh`. Multi-pattern URL matching with hash and binary tables (PLOS ONE). Per its
  abstract it targets string matching from a fixed start in HTTP streams (security, load
  balancing), not routing with parameters. Differs from P2 in problem: no captures, no
  precedence between literal and parameter.
- `bernerslee2005rfc3986`, `fielding2022rfc9110`. The path grammar (pchar) that a parameter
  accepts, and the HEAD and 405 rules that router v2's semantics follow (design/router-v2.md,
  rules 2, 6 and 8). Background.
- `schmidt2020gohttproutingbench`. The Go router benchmark suite; its README says it compares
  Go request routers on the routing structure of real-world APIs. Builds on: P2's exploratory
  real-world table is its GitHub API list (commit d8f3b858, BSD 3-Clause, `github_test.go`).
  Differs: that suite times Go routers inside Go; P2 times routers of four languages behind one
  harness, with null arms and answer checks.

Peer-reviewed literature on the routing performance of web frameworks is thin. Crossref and OpenAlex
searches ("URL routing", "HTTP request routing", "URL matching web server", "web framework
routing performance", "REST URI template matching") found the three papers above and nothing
else on point. Semantic Scholar's search API returned HTTP 429 and was not used for search.

### Competitor routers (compares against)

All at the pins of `bench/cmake/pins.cmake`. Mechanism statements come from the file named.

- `schmidt2019httprouter` (v1.3.0, 2019). README: "A compressing dynamic trie (radix tree)
  structure", children ordered by priority, "zero bytes of garbage" when matching, and "Only
  explicit matches": a static route and a parameter cannot share a path segment for one method
  (the reason it refuses mixed-overlap, hypotheses.md). It redirects on a trailing slash by
  default; router v2 never redirects (rule 4).
- `gin2026gin` (v1.12.0). `tree.go` carries Julien Schmidt's copyright and httprouter's BSD
  notice: gin's router tree is derived from httprouter. P2 vendors `tree.go` unchanged.
- `ahmed2026matchit` (0.9.2). matchit is the router library axum builds on; axum's latest
  release, 0.8.9, pins matchit 0.8.4 (`axum2026axum`), so the arm measures matchit's latest
  release, not the one axum 0.8.9 uses (corrected 2026-10-02). README: "A high
  performance, zero-copy URL router"; static and dynamic segments may overlap and static wins;
  catch-all must be last. Licence "MIT AND BSD-3-Clause", with `LICENSE.httprouter` in the
  repository. Same precedence rule as router v2 for literal against parameter; matchit has no
  typed parameters.
- `actix2026router` (0.5.4, the router of actix-web). Licence and tag checked. Its matching
  algorithm was not read for these notes.
- `go2026go1271` and `amsterdam2024routing`. Go's ServeMux with the patterns of Go 1.22 and
  later. The Go blog post (Jonathan Amsterdam, 13 February 2024) states "the most specific
  pattern wins", that `{name...}` matches the rest of the path, and that two patterns that
  overlap with neither more specific make registration panic. Same precedence principle as
  router v2 (rule 5). Differs: the conflict is found when the program runs, not when it
  compiles.
- `crow2026crow` (v1.3.4). `include/crow/routing.h`, class `Trie`: each node holds a key, a
  parameter type and a `std::vector` of children.
- `drogon2026drogon` (v1.9.13). `lib/src/HttpControllersRouter.cc`, `route()`: the path is
  copied and lower-cased, looked up in `std::unordered_map`s of simple and plain controllers,
  and on a miss matched with `std::regex_match` against each parameter route in turn.
- `oatpp2024oatpp` (1.3.1). `src/oatpp/web/url/mapping/Router.hpp`, `getRoute`: a
  `std::list` of (pattern, endpoint) pairs, each pattern tried until one matches.
- `pistache2024pistache` (v0.4.26). `include/pistache/router.h`, `SegmentTreeNode`: a
  segment tree whose children are `std::unordered_map`s for fixed, parameter and optional
  segments plus one splat child. A segment trie like router v2's, with node-based maps where
  v2 has flat arrays.
- `boosturl2026router` (boost-1.92.0, `example/router`). `detail/impl/router.cpp` defines
  segment templates and a comment states literal segments take precedence. An example, not a
  library component.
- `r32026r3` (2.0 branch). README: a C router that "compiles your R3Route paths into a prefix
  trie", with PCRE2 as a dependency.

## (b) Lookup structures in networking

Cited only as far as they inform segment tries.

- `andersson1993adaptive`. Tries with adaptive branching (title only; no abstract available
  in OpenAlex or Crossref).
- `nilsson1999lctrie`. The LC-trie combines path and level compression; its search depth grows
  as Theta(log log n) with the table for a large class of distributions, independent of the
  address length (abstract). Differs from: router v2 branches on whole segments, not bits, so
  a node's fan-out is its set of literal children, and it compresses neither levels nor paths. Useful to explain why
  the trie depth of v2 is the number of segments, independent of the table size (the
  "growth with the table" measure of design/router-v2.md).
- `srinivasan1999cpe`. Controlled prefix expansion turns a prefix set into one with fewer
  prefix lengths, giving "Expanded Tries" whose performance can be tuned, with attention to
  cache behaviour (abstract). Background on choosing how much a trie step consumes; v2's step
  is one segment.
- `degermark1997small`. Forwarding tables small enough to fit in a general-purpose
  processor's cache, giving a few million lookups per second in software (abstract).
  Background on cache-sized tables.
- `waldvogel1997scalable`. Binary search on hash tables organised by prefix length (abstract).
  Background: hashing per level instead of walking a trie. v2 hashes within a node only.
- `ruizsanchez2001survey`, `gupta2001classification`, `taylor2005survey`. Surveys of IP lookup
  and packet classification. Background for the design space and its vocabulary.
- `eatherton2004treebitmap`. A lookup scheme that scales in speed and table size, updates
  fast, and fits a forwarding engine's memory architecture (abstract). Background.
- `asai2015poptrie`. A multiway trie that uses the population count instruction on bit-vector
  indices to keep the structure within the CPU cache, evaluated with a CPU cycle analysis
  (abstract). Builds on the methodological point: P2 reports instructions, branch misses and
  cache misses per lookup beside time.
- `wang2012nce`, `so2013ndn`, `yuan2015lnpm`. Name lookup in named data networking, where
  names are hierarchical with variable-length components separated like URL path segments
  (abstracts). So et al. look names up in hash tables; Wang et al. encode components; Yuan and
  Crowley binary-search hash tables by component count. Closest networking analogue of a
  segment trie. Differs: these do longest-prefix matching on names; router v2 does exact
  matching with typed parameters, catch-all and precedence, and returns captures.

## (c) Hashing and perfect hashing for static key sets

- `peterson1957addressing`. Estimates of the search needed to locate a record under several
  addressing methods, with formulas for an "open" system (abstract). Background: v2's hashed
  edges and its exact-match table are open-addressing tables confirmed by a full comparison.
- `celis1985robinhood`. Open addressing with an insertion rule that sharply reduces the
  variance of probe counts, giving a constant expected number of probes even for full tables
  (abstract). Background; v2 does not use it.
- `pagh2004cuckoo`. Cuckoo hashing (title only; no abstract available). Background; v2 does
  not use it.
- `fredman1984sparse`. A set of n items stored in n + o(n) space with constant-time membership
  queries (abstract). `pibiri2021pthash`: construction of minimal perfect hash functions for
  static key sets, trading construction time, lookup time and space (abstract).
  `czech1992optimal` and `belazzougui2009chd`: minimal perfect hash construction (titles only;
  no abstracts available). Differs from: a compile-time table in v2 knows its keys
  when compiled, so a perfect hash is possible in principle, but v2 builds the same open-
  addressing layout at compile time and at run time so that one lookup function serves both
  (design/router-v2.md, "Tables at run time and at compile time"). A perfect hash for the
  compile-time table is an option P2 did not test; say so, do not claim it was worse.
- `gnu2025gperf`. GNU gperf 3.3 generates perfect hash functions as C or C++ code from a list
  of strings (its page). Differs: an external generator, not a C++ constant evaluation.
- `guelton2024frozen`. `frozen` 1.2.0: header-only constexpr containers; its README says the
  `unordered_*` containers are "guaranteed *perfect*" and initialisation is free when
  `constexpr`. The closest C++ software to a compile-time hash table. Differs: a general
  container, not a router; no segment trie, no captures.

## (d) Typed routing and compile-time checking of string DSLs

- `danvy1998unparsing`. Typed printf in ML by changing the representation of the control
  string (abstract). Background: the classic case of a string whose content decides the types
  of the arguments, as a route pattern decides a handler's parameters.
- `balat2006ocsigen`. Ocsigen (OCaml) uses the type system to produce valid XHTML and "valid
  remote function calls through links and form clicking", and manages URLs (abstract). Typed
  links and services in OCaml. Differs: no lookup-speed evaluation in the abstract.
- `mainland2007quasiquoting`. Quasiquotation in GHC with a compile-time guarantee that
  quasiquoted data is type-correct (abstract). Background: the mechanism by which Haskell
  checks a DSL written as a string at compile time. The claim that Yesod's route files use it
  is not verified; do not write it.
- `mestanogullari2015servant`. Servant: a web API is a Haskell type, interpreted as a server
  that dispatches to handlers, as a client and as documentation (abstract). Closest typed
  routing work. Differs: the API is a type, not a string pattern; the abstract reports no
  lookup performance.
- `chlipala2015urweb`. Ur/Web: a statically typed functional language for web applications
  (abstract). Background for typed web programming. The abstract does not mention routing or
  link checking; do not claim either from it.
- `blanvillain2022regex`. Scala regular expressions checked during type checking with match
  types, with a minor impact on compile time (abstract). The Scala example of a string DSL
  checked at compile time. No peer-reviewed Scala typed-routing paper was found.
- `rocket2024rocket`. Rocket 0.5.1 (Rust). The route attribute documentation states "Every
  identifier, except for `_`, that appears in a dynamic parameter ... must appear as an
  argument to the function", and each such argument's type must implement a guard trait. The
  guide (v0.5) says colliding routes make Rocket "emit an error and abort launch". Differs:
  handler agreement is checked by a procedural macro, so during compilation (inferred from the
  attribute being a macro; the page does not say "compile time"), but route collisions are
  found at launch. Router v2 rejects duplicates in a compile-time table when it compiles.
- `snyder2018p0732`. P0732R2 (2018-06-06) proposes class types as non-type template
  parameters (first page read). Its adoption into C++20 was not checked against a WG21 record.
  Builds on: router v2 passes the pattern as a class-type NTTP.
- `dusikova2019p1433`, `dusikova2026ctre`. CTRE passes a regular expression as a class NTTP
  (`fixed_string`), checks it when compiling and generates the matcher (P1433R0, 2019-01-21,
  first page). Builds on the same technique; P2 applies it to route patterns and handler
  signatures. Alex's RegexMatcher paper is the run-time regex side of the same lineage.
- `zverovich2021p2216`, `zverovich2026fmt`. P2216R3 makes invalid `std::format` strings
  ill-formed at compile time; fmt's README shows a format string checked at compile time.
  Builds on: the pattern of checking a string argument against argument types when compiling.
- `porkolab2010dsl`. A compile-time parser generator in C++ template metaprogramming, with a
  type-safe printf as its demonstration (abstract). Earlier C++ route to the same goal, before
  constexpr strings.

## (e) Zero-overhead abstraction and constant evaluation

- `stroustrup2012foundations`. States C++'s aims as "a simple and direct mapping to hardware"
  and "zero-overhead abstraction mechanisms", and defines light-weight abstraction as one
  without overheads beyond careful hand coding (p. 2, read in the open-access PDF). H7's claim
  ("a compile-time table costs nothing at run time") is this principle, tested.
- `stroustrup2020hopl`. History of C++ from 2006 to 2020, covering the language features of
  C++11 to C++20 (abstract). Background for constexpr and NTTP evolution.
- `dosreis2010constexpr`. The design of generalised constant expressions, implemented in GCC
  and adopted for the next standard (abstract). Background for `consteval` table building.
- `smith2020n4861`. The C++20 working draft. Annex B [implimits] recommends at least 512
  recursive constexpr invocations and 1,048,576 full-expressions in a core constant expression,
  as guidelines that "do not determine compliance". Background for the budgets of
  design/router-v2.md.
- `llvm2026clangmanual`. `-fconstexpr-steps`: limit on full-expressions in one constant
  evaluation, default 1048576, 0 disables it.
- `gcc2026dialect`. `-fconstexpr-ops-limit`: default 33554432 (1<<25), GCC 16.2 manual. GCC is
  not a measured compiler in P2; cite only if the paper mentions it.
- `microsoft2026constexpr`. `/constexpr:steps`: default 100,000. Matches design/router-v2.md
  ("at its default of 100,000 the compiler crashes on a 100-route table").

## (f) Benchmarking methodology and statistics

- `leitnerankerl2026nanobench`. The microbenchmark library of the harness (v4.6.0). Compares
  against nothing; tool citation.
- `browne2000papi`, `manpages2026perfeventopen`. Portable counter access (PAPI; title) and the
  Linux interface the harness uses (`bench/core/runner.hpp` and `cache_counters.cpp` call
  `perf_event_open`). Background.
- `weaver2013nondeterminism`. Events that should be exact, such as retired instructions, show
  run-to-run variation and overcount on x86_64, across eleven CPU implementations (abstract).
  Background for H2: it is why P2 reports instruction counts with their spread over processes
  and epochs rather than as exact values.
- `amd2026ppr`. UNVERIFIED placeholder: the AMD document that defines events 0xAE and 0xAF on
  L's CPU was not found. The hypotheses rest on a validation run
  (lab/evidence/2026-09-27-L-dispatch-stall-validation) rather than on the manual; cite that
  run and find the manual before citing it.
- `mytkowicz2009wrong`. Changing a seemingly innocuous aspect of an experimental setup can
  bias an evaluation enough to draw wrong conclusions (abstract). Background for pinning, seed
  pairs, and the RING_LAYOUT exploratory comparison.
- `curtsinger2013stabilizer`. Statistically sound performance evaluation (title; the abstract
  excerpt available is generic). Cite only for the general point.
- `georges2007rigorous`. Run-to-run non-determinism makes Java benchmarking non-trivial
  (abstract). `kalibera2013rigorous`: valid results need repetition at several levels and
  proper variation estimates (abstract). `hoefler2015scientific`: a survey of 120 papers finds
  reporting lacking and proposes statistically sound analysis and reporting guidelines
  (abstract). `laaber2019cloud`: microbenchmark variability in cloud environments (title only;
  no abstract available). Background for R = 10 processes and intervals over processes.
- `efron1987bca`. Bootstrap confidence intervals with second-order correctness in parametric
  and nonparametric problems (abstract). `diciccio1996bootstrap`: a survey of BC_a,
  bootstrap-t, ABC and calibration (Project Euclid page). `efron1993bootstrap`: textbook
  (title). Builds on: H1, H6 and H7 use BCa intervals over paired seeds.
- `virtanen2020scipy`. SciPy, whose `scipy.stats.bootstrap` computes the intervals.
- `holm1979simple`. Holm's step-down procedure (partly unverified, see refs.bib). H1 uses it
  at family-wise alpha 0.025.
- `schuirmann1987tost`, `wellek2010testing`. One-sided tests against a margin (TOST) and the
  equivalence and non-inferiority framework. Builds on: H1 and H7 are non-inferiority tests
  with margin 1.02.

## (g) Alex Tsvetanov's prior work

- `stankov2024regex` (TELECOM 2024, Stankov and Tsvetanov). Matching one URL against many
  whole-string regular expressions with a prefix-tree structure, motivated by web servers whose
  routes are regexes (abstract). This is RegexMatcher's regex-set engine, v1, the earlier paper on
  the library that P2 reworks into v2. Cited plainly as the author's earlier, co-authored work.
  v1 is a reference arm and H6's baseline (`regexmatcher2026v1`, the commit the arms pin).
- The two publish/subscribe papers of earlier drafts (`tsvetanov2025pubsub`,
  `tsvetanov2025dispatch`) were removed from refs.bib on 2026-10-02: Alex says they are
  unrelated to P2.

## Gap statement

Each clause names a verified source that has one property and one that lacks it. "Found" means
found in the searches and sources of these notes, not proven absent.

1. Compile-time checking of routes exists in typed web frameworks (`mestanogullari2015servant`
   in Haskell types, `balat2006ocsigen` in OCaml types, `rocket2024rocket` in a Rust macro), and
   compile-time checking of string DSLs exists in C++ (`dusikova2019p1433`,
   `zverovich2021p2216`, `porkolab2010dsl`). None of the abstracts or pages read reports a
   lookup-time comparison with radix-tree routers.
2. Fast routers document radix or trie matching without allocation (`schmidt2019httprouter`:
   zero garbage; `ahmed2026matchit`: zero-copy), and the two peer-reviewed routing papers found
   (`zhang2015urlrouting`, `dsouza2018htu`) describe tries with hashed segments. None of the C++
   READMEs, pages or abstracts read describes checking a route's pattern, its handler's signature
   and its duplicates together at compile time: Crow checks tags and handler types but finds
   duplicates at run time (`crow2026routing`), RESTinio checks handler arguments of a route
   expression (`stiffstream2025restinio`). Yesod does all three in Haskell (revision of
   2026-09-28: its quasiquoter rejects malformed route lines and overlaps at compile time, and
   types each route's arguments), and reports no lookup-time comparison. Elsewhere, duplicate or
   ambiguous routes are found at run time where they are found at all: registration panics in
   Go's ServeMux (`amsterdam2024routing`), launch errors in Rocket, refusals at insert in
   httprouter. (Updated 2026-10-02 after the fact-check: this item predated the Yesod revision.)
3. The evaluations of router speed found are benchmark suites kept beside routers (Go routers,
   `schmidt2020gohttproutingbench`; Rust routers, matchit's README benchmark in
   `ahmed2026matchit` and wayfind's `benches/` in `sworn2026wayfind`; API gateways on real route
   sets, `vm0012024gateways`) and a comparison with a single table-based router
   (`zhang2015urlrouting`). No source found compares routers of several languages on the same
   tables with answers checked for agreement and pre-specified non-inferiority tests (BCa
   intervals, Holm).

What P2 does that no source found does: a C++ router whose route patterns, handler parameter
counts and types, and duplicate routes are checked when the program compiles (class-type NTTP
patterns and constexpr tables), whose lookup allocates nothing and returns views, and which is
measured against the routers of C++, Rust and Go on shared tables under frozen, pre-registered
non-inferiority hypotheses, with the compile-time table tested against the run-time table for
zero run-time cost (H7).

Do not claim from this: that P2 is the first typed router, or the first segment trie with
hashed children (Pistache's `SegmentTreeNode` and `zhang2015urlrouting` are both segment
structures with hashed literal children).

## Could not confirm

- Holm (1979): volume, issue, pages and the JSTOR page. JSTOR did not load; no DOI is
  registered (doi.org 404 for 10.2307/4615733). Entry kept with author, title, journal, year.
- The AMD Processor Programming Reference for L's CPU (Ryzen 7 5800H): not located on
  docs.amd.com. Placeholder entry only.
- Rocket: that the dynamic-parameter check runs at compile time is inferred from the route
  attribute being a macro; the documentation read does not say "compile time".
- P0732R2's adoption into C++20: not checked against a WG21 motion record.
- actix-router's matching algorithm: not read.
- Full texts of the routing papers (`zhang2015urlrouting`, `dsouza2018htu`, `zeng2017mh`):
  only abstracts were read, so their evaluation details (tables, hardware, statistics) are
  unknown.
- No abstract was available (OpenAlex and Crossref) for `andersson1993adaptive`,
  `pagh2004cuckoo`, `czech1992optimal`, `belazzougui2009chd` and `laaber2019cloud`, and only a
  generic excerpt for `curtsinger2013stabilizer`; their use above is limited to their titles.
- Author given names are as Crossref records them; where it gives initials (for example
  `leis2013art`, `nilsson1999lctrie`), initials are kept.
- Clang's manual shows no version on the page; the default of 1048576 was read on
  2026-09-27.

## Considered and left out

- Links (FMCO 2006) and Eliom (APLAS 2016): verified in Crossref, but no abstract was
  available to confirm a routing relevance.
- Botelho, Pagh and Ziviani (WADS 2007): Crossref gives no year for the chapter.
- BBHash (SEA 2017): its LIPIcs DOI is not registered with Crossref (404); not checked in
  DataCite.
- Schmidt's 1990 gperf paper (USENIX C++ Conference): no DOI found in Crossref; the software
  release is cited instead.
- Stroustrup, "Abstraction and the C++ Machine Model" (ICESS 2004): verified in Crossref, but
  Springer's page redirected to a login, so its content could not be read.
- ISO/IEC 14882:2020 (iso.org page returned 403): the working draft N4861 is cited instead.
- HAT-trie (ACSC 2007): no Crossref DOI found in these searches.

## Counts

refs.bib holds 87 entries: 85 verified and 2 marked UNVERIFIED (`holm1979simple`, partly;
`amd2026ppr`, placeholder). The 85 verified are 56 papers and books checked by DOI (3 of them
Alex's own, copied from bib/own.bib), 2 RFCs checked by DOI, 4 WG21 documents read at
open-std.org, and 23 software and documentation entries. A test document with `\nocite{*}`
and IEEEtran.bst ran through pdflatex and BibTeX with no warning.

## Revision of 2026-09-28 (review of the first draft)

Read at primary sources on 2026-09-28; keys in `refs.bib`, section (h).

- `crow2026routing`, Crow v1.3.4 at the pinned commit ae0fef0 (the tag resolves to it).
  `CROW_ROUTE(app, url)` expands to `app.template route<crow::black_magic::get_parameter_tag(url)>(url)`
  (`include/crow/app.h`), unless `CROW_MSVC_WORKAROUND` is defined, when it is `route_dynamic`.
  `get_parameter_tag` is a constexpr function over the pattern (`include/crow/utility.h`): it
  maps `<int>`, `<uint>`, `<float>` or `<double>`, `<str>` or `<string>`, and `<path>` to argument
  types, and an unknown tag reaches a `throw` inside it, so the pattern does not compile. The rule
  is a `TaggedRule<Args...>`; assigning a handler selects one of the `wrapped_handler_call`
  overloads by whether the handler can be called with those arguments (`include/crow/middleware.h`,
  `enable_if` on `CallHelper`), so a handler whose parameters do not take them does not compile.
  So Crow checks, when compiling, the parameter tags of a pattern and the count and types of a
  handler's parameters against them. It does not check the rest of the pattern at compile time:
  the leading `/` is checked by `validate()` at run time, a route that already exists throws
  "handler already exists" at run time (`Trie::add`), and nothing checks pchar or catch-all
  position. `route_dynamic` checks handler types at run time ("Handler type is mismatched with
  URL parameters"). The harness measures `crow::Trie` directly, not `CROW_ROUTE`.
- `yesod2026routing`, `yesod2025core`. The Yesod book: "Yesod defines a Domain Specific Language
  (DSL) for specifying routes, and provides Template Haskell functions to convert this DSL to
  Haskell code"; "By default, Yesod will ensure that no two routes have the potential to overlap
  with each other"; "The arguments have the types of the dynamic pieces for each route". In
  yesod-core 1.6.28.1, `parseRoutes` is a `QuasiQuoter` whose `quoteExp` calls `error` with
  "Overlapping routes" when `findOverlapNames` finds any, so the check fails the compile.
  This corrects the earlier note that forbade a Yesod claim: the quasiquotation is now read.
- `play2026routing`, Play 3.0.x: "Routes are defined in the conf/routes file, which is compiled",
  and "If there is a conflict, the first route (in declaration order) is used". So Play compiles
  its route file but resolves overlaps by order; it does not reject them.
- `stiffstream2025restinio`, RESTinio v.0.7.4, `easy_parser_router.hpp`: `path_to_params`
  builds a route from parsers, and their results reach the handler as separate arguments
  (`call_with_tuple`), so a handler whose parameters do not take them does not compile. The
  route is a C++ expression, not a pattern string; overlap handling was not read.
- `zeng2017mh` (PLOS ONE, open access): full text read. It matches literal URLs from a fixed
  start in HTTP streams (firewalls, traffic analysis, load balancing); no parameters or
  precedence. The full texts of `zhang2015urlrouting` and `dsouza2018htu` (IEEE) were not
  available; statements about them still rest on their abstracts.
- Not verified: Holm (1979)'s volume and pages (JSTOR refused the reader and the OpenAlex API
  answered with a rate limit).

## Revision of 2026-10-02 (round 2)

- The paper is now about RegexMatcher v2 (`cpp-for-everything/RegexMatcher`), the route matcher
  the author extracted and reworked, not about the router of the thesis's integration library.
  Where these notes say "router v2", read the round-1 header, whose lookup v2 keeps
  (hypotheses-round2.md, section 1). The paper never names the integration library.
- "Pre-registered" above means pre-specified: the hypotheses are fixed in the paper's
  repository (round 2 at commit 9d7e8fe) before the run. The paper says "pre-specified in the
  repository", never "pre-registered".
- Added for the five round-2 competitors, at the pins of `bench/cmake/pins.cmake`:
  `uwebsockets2026uwebsockets` (v20.80.0, 3ffd6f4), `berry2026glaze` (v9.0.0, d78832c),
  `hirose2026httplib` (v0.58.0, 4f3f9ef), `chi2026chi` (v5.3.2, 3893906), `viz2025pathtree`
  (0.8.3, annotated tag to 158f350; crate sha256 equal to the pin). Each tag was resolved through
  the GitHub API without authentication on 2026-10-02 and equals the pin; release dates from
  `lab/evidence/2026-09-30-W-pins-freshness/pins.txt`. Mechanism statements about them in the
  paper come from `design/round2/competitor-survey.md` and the adapters' Appendix A rows
  (hypotheses-round2.md); the survey's facts were read by an agent at the URLs it lists.
- Added `axum2026axum`: axum 0.8.9's `axum/Cargo.toml` (tag axum-v0.8.9) holds
  `version = "0.8.9"` and `matchit = "=0.8.4"`, read 2026-10-02.
- Added `regexmatcher2026v1`: RegexMatcher at d16f30a8 (the v1 pin), on the public branch
  `perf/deterministic-live-sets`; authors from the repository's CITATION.cff.
- Counts: refs.bib holds 97 entries: the 87 of the first count, the 5 of the revision of
  2026-09-28, less the two publish/subscribe papers, and these seven.

## Revision of 2026-10-02, after the fact-check

- The gap statement (item 2) is scoped to C++ sources; Yesod does all three checks in Haskell. The
  paper says so.
- Added `sworn2026wayfind` (wayfind at 2300ca7, `benches/matchit.rs` times wayfind, actix-router,
  matchit and ntex-router among others) and `vm0012024gateways` (the gateway benchmark at 8122a5c:
  Kong, APISIX and Tyk on route sets of the OpenAI, Okta and GitHub interfaces), both read through
  the GitHub API without authentication. matchit's README at v0.9.2 holds its benchmark of Rust
  routers over 130 routes (read 2026-10-02).
- Crow v1.3.4's `Trie::add` inserts one character per node and `optimizeNode` merges single-child
  chains (`include/crow/routing.h` at ae0fef0, read 2026-10-02): a character trie, not a trie of
  whole segments. The introduction says so.
- Counts: refs.bib holds 99 entries.
