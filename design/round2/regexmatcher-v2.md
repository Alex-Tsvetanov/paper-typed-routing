# RegexMatcher v2: the route matcher, extracted

Status: design for review, round 2 of P2, phase 1. Nothing here is implemented. Written
2026-09-30. Once Alex approves it, this note is frozen and later changes go into a revision
log at its end.

Words used here:
- "the round-1 header" is the one self-contained header measured in round 1: the private
  checkout at commit 6d28e3610, 1,323 lines, standard library only. It holds the pattern
  parser, the table builder, the lookup and the compile-time table builder. Its namespace,
  its macro prefix and its include path carry the private library's name, so all three
  change.
- "the private library" is the thesis's integration library. This note never names it and
  nothing in v2 depends on it.
- "v1" is RegexMatcher's regex-set engine at commit d16f30a8, the commit the round-1
  reference arm pinned. "v2" is the next major release of `cpp-for-everything/RegexMatcher`,
  which adds the route matcher.

Everything below that says "measured" or "found" was read from a file or run on
2026-09-30, and says where.

## 1. What moves, what is new, what stays out

| Part | Source | In v2 |
|---|---|---|
| Pattern parser: segment kinds (literal, typed, parameter, catch-all), types (string, u64, i64), 12 errors with their byte offset | round-1 header | moved unchanged |
| Typed-segment tests (`matches_u64`, `matches_i64`) | round-1 header | moved unchanged |
| Word helpers: 8-byte loads that never read outside the path, slash search in a word, masks, path and edge hashes | round-1 header | moved unchanged |
| Flat table (nodes, edges, exact-match slots, one label arena), its 64-byte-aligned allocator, `build_table` | round-1 header | moved; the build is reworked afterwards (`engineering.md`, target a) |
| Lookup (`find`, `find_into`, the trie walk, the 405 scan) | round-1 header | moved unchanged |
| Compile-time table (`StaticTable`, `make_static_table`, the named error functions a compiler prints) | round-1 header | moved unchanged |
| Method enum | new | `Get` to `Trace`, values 0 to 8 (section 5) |
| Checked front end: a string literal as a template argument, one `static_assert` per pattern error, the C++ type of each parameter, the handler signature check, declarations of routes with handlers and a compile-time table of them | new code | written tests first (section 6). In round 1 these lived in the private library's router header and were tied to its request, task and response types. v2 has them generic over the trailing arguments a caller adds (section 5.3) |
| HEAD answered by GET, a 405's Allow field, captured values stored as offsets in a request, mounting a table in a server | private library | not in v2. Server behaviour; they go to the paper's minimal server (`minimal-server.md`) |

"Extracted" is true only for the first six rows. The checked front end is new code with the
same checks, and H5(a) depends on it (`hypotheses-v2-proposal.md`).

## 2. Layout and namespace

C++23, header-only, standard library only. Namespace `matcher::route`, helpers in
`matcher::route::detail`. v1 already uses namespace `matcher` (class `matcher::RegexMatcher`
in `include/matcher/core.hpp`), so the route matcher is a sub-namespace beside it. Type and
function names stay as in the round-1 header (`Pattern`, `Segment`, `TableView`, `Built`,
`Match`, `Capture`, `Status`, `RouteSpec`, `build_table`, `find`, `find_into`,
`make_static_table`, `parse_pattern`), because the paper describes them. The macro prefix
becomes `MATCHER_ROUTE_` (`MATCHER_ROUTE_INLINE`, `MATCHER_ROUTE_NOINLINE`).

Final layout (after step E2 below):

```
include/matcher/core.hpp                   v1 regex engine, unchanged
include/matcher/impl/*.ipp                 v1, unchanged
include/matcher/RegexMatcherConfig.h       generated version header (existing mechanism)
include/matcher/route.hpp                  umbrella: includes everything below, and only that
include/matcher/route/config.hpp           MATCHER_ROUTE_* macros, kMaxSegments, kMaxParams, kMethodSlots
include/matcher/route/method.hpp           enum class Method
include/matcher/route/pattern.hpp          SegKind, ParamType, PatternError, describe, Segment, Pattern, parse_pattern, matches_u64/i64
include/matcher/route/detail/words.hpp     load_at, same_from, first_slash, mask_low, mix, path_hash, edge_hash
include/matcher/route/table.hpp            Edge, Node, LiteralSlot, TableView, TableAllocator, Built, RouteSpec, BuildError, build_table
include/matcher/route/lookup.hpp           Capture, Match, Status, find, find_into
include/matcher/route/static_table.hpp     StaticSizes, StaticTable, make_static_table
include/matcher/route/checked.hpp          fixed_string, checked_pattern, param_t, handler checks, Decl, make_route_table
docs/route-semantics.md                    the path semantics (rules 1 to 7 of the round-1 design note, rule 8 excluded)
```

The umbrella never includes `matcher/core.hpp`, and no route header does. That keeps v1 and
v2 apart in a program that uses both (section 8.3).

### 2.1 Extraction in three steps, each its own commit

- **E1, rename only.** `include/matcher/route.hpp` is the round-1 header with the namespace
  and the macro prefix renamed, and its comments rewritten so they name neither the private
  library nor its design note. No code changes. The objdump check of section 9 must show the
  lookup's machine code unchanged.
- **E2, split.** The same code in the files above. The objdump check again. Also in E2, one
  portability fix found today: clang 18.1.3 (WSL, Ubuntu 24.04) rejects the round-1 header
  with four errors "no matching function for call to 'operator delete'", at
  `TableAllocator::deallocate`'s call of the sized, aligned `operator delete`; with
  `-fsized-deallocation` it compiles (the scratch builds of `engineering.md` add that flag).
  Which clang versions need the flag was not checked. E2 calls the unsized aligned form, `::operator delete(p, std::align_val_t{64})`.
  This changes the table's deallocation, not the lookup, so the objdump check of the lookup
  still applies.
- **E3 and later.** The engineering changes of `engineering.md`, one commit each, each with
  its adoption record.

## 3. v1 and v2 in one repository

Three options were considered.

- **Coexist (recommended).** The repository ships both components. v1's engine keeps
  `include/matcher/core.hpp`, its target `RegexMatcher` (exported as `RegexMatcher::core`),
  and C++17. The route matcher is a second header set and a second target,
  `RegexMatcherRoute`, exported as `RegexMatcher::route`, requiring C++23. Neither includes
  the other. The engine is unchanged in v2.0.
- **Replace.** Remove the regex engine from `main`. Rejected: the repository's name, its
  README and its published TELECOM 2024 paper (DOI in the README) are about the engine, and
  the paper needs v1 for two arms anyway.
- **A separate repository.** Rejected: Alex's intent is the next major version of this
  repository.

**v1 stays buildable at its pinned commit.** The reference arm and the H6 baseline fetch v1
as a source tarball of commit d16f30a8, pinned by sha256 (`bench/cmake/pins.cmake`). Facts
about that commit, read today in the local checkout:
- it is on branch `perf/deterministic-live-sets` (local and `origin`), 7 commits after
  `main`'s head 2220b61, and on no other branch;
- its CMakeLists.txt, like `main`'s, declares version 2.0.0.1;
- the tags are `1.0.0.0` and `1.0.0.1`; `origin/stable` declares 1.0.0.1.

If that branch is deleted or force-pushed, GitHub may stop serving the commit, and the pinned
tarball URL fails. Two protections, both needing Alex:
1. a tag at d16f30a8 (a push to the public repository, Alex's yes);
2. the tarball L already fetched for round 1 (its `_deps` copy), archived beside the raw
   runs with its sha256, so a lost URL does not lose the input. No download is needed for
   that.

Whether the 7 engine commits on that branch are merged into `main` for v2 is Alex's choice;
P2 does not need it, because v1 is always the pinned commit.

## 4. Build system

- `cmake_minimum_required(VERSION 3.25)`. Today it is 3.16.3, but the root already uses
  `FILE_SET` (CMake 3.23), and `PROJECT_IS_TOP_LEVEL` (3.21) is used below.
- The global `set(CMAKE_CXX_STANDARD 17)` goes. Each target states its own:
  `target_compile_features(RegexMatcher INTERFACE cxx_std_17)` and
  `target_compile_features(RegexMatcherRoute INTERFACE cxx_std_23)`.
- Options:
  - `REGEXMATCHER_BUILD_TESTS` (default `PROJECT_IS_TOP_LEVEL`);
  - `REGEXMATCHER_BUILD_BENCHMARKS` (default OFF);
  - `REGEXMATCHER_SANITIZER` (`address+undefined`, `thread`, `memory`; `address` with MSVC or clang-cl), applied to every target of the build, fetched test frameworks included;
  - `REGEXMATCHER_MSAN_LIBCXX` (path of an instrumented libc++);
  - `REGEXMATCHER_CT_STEPS` (default 33,554,432, the budget round 1 gave its compile-time tables) and `REGEXMATCHER_CT_JOBS` (default 1, a Ninja job pool for the compile-time-table tests).
- `external/` (GoogleTest v1.15.2 by commit, Google Benchmark v1.8.3) is added only when
  tests or benchmarks are on. Today the root always adds it, so a project that fetches
  RegexMatcher's root also fetches and builds both frameworks and the tests. That is why
  round 1 fetched only the `include/` subdirectory.
- Install and export: a `FILE_SET` for the route headers, targets `RegexMatcher::core` and
  `RegexMatcher::route`. The existing `pkg/RegexMatcher-config.cmake.in` sets
  `RegexMatcher_INCLUDE_DIRS` to `include/RegexMatcher-<version>` while the headers install
  to `include/matcher`; v2 fixes that line.
- The generated `include/matcher/RegexMatcherConfig.h` is written into the source tree at
  configure time and is committed. It stays as it is, regenerated for the new version.

## 5. Public API

### 5.1 Unchanged from the round-1 header

```cpp
namespace matcher::route {
constexpr Pattern parse_pattern(std::string_view text) noexcept;
struct RouteSpec { unsigned method; std::string_view pattern; std::uint32_t route; };
constexpr Built build_table(std::span<const RouteSpec> specs);           // Built::error names the failing route
constexpr Match find(const TableView& t, unsigned method, std::string_view path) noexcept;
constexpr void find_into(const TableView& t, unsigned method, std::string_view path, Match& m) noexcept;
template <auto& Specs> consteval auto make_static_table();                // StaticTable<sizes>
}
```

The lookup keeps its `unsigned method` parameter, the measured signature.

### 5.2 Method enum

```cpp
enum class Method : std::uint8_t { Get, Post, Put, Delete, Patch, Head, Options, Connect, Trace };
constexpr Match find(const TableView& t, Method m, std::string_view path) noexcept;  // forwards
```

The values 0 to 8 are the order the round-1 header's method index had, and rbench's own
method enum (`bench/core/route.hpp`, `Get` to `Options`, 0 to 6) casts into it unchanged.
Keeping the values keeps the harness's cast, the compiled tables in `bench/gen/` and the
objdump check valid. The `Method` overload is an inline forwarder; the harness keeps calling
the `unsigned` form.

### 5.3 The checked front end (new code)

```cpp
template <std::size_t N> struct fixed_string;             // a string literal as a template argument
template <fixed_string P> struct checked_pattern;         // one static_assert per PatternError
template <fixed_string P, std::size_t I> using param_t;   // std::string_view, std::uint64_t, std::int64_t
// The handler takes one argument per parameter of P, in order, then Context... (for example a
// server's request). Two static_asserts: the argument count, then the argument types.
template <fixed_string P, class F, class... Context> consteval void check_handler();
// Converts the captured values and calls F: the typed values cannot fail to convert, because
// the lookup matched them against their type.
template <fixed_string P, auto F, class... Context>
decltype(auto) invoke(std::span<const Capture> values, Context&&... ctx);
// A route with its handler, and a compile-time table of them: a bad pattern, a handler that
// does not fit, or two routes of one method that match the same paths stop the compilation.
template <class Handler> struct Decl { unsigned method; std::string_view pattern; Handler handler; };
template <auto& Decls> consteval auto make_route_table();  // {StaticTable, std::array<Handler, N>}
}
```

The diagnostics say what is wrong without naming a library, for example
`"route pattern: unclosed '{'"` and
`"route handler: takes a different number of parameters than the pattern has"`.

## 6. Tests

GoogleTest, the repository's framework (pinned by commit in `external/`). Behaviours to port,
described here without their origin. Each is one test case; R-numbers are referred to by
`engineering.md`.

| # | Behaviour |
|---|---|
| R1 | Patterns parse into segments: kinds, types, names; the root pattern has no segment; a trailing slash is a final empty literal; percent-encoded and sub-delimiter literals are accepted |
| R2 | Twelve malformed patterns each give their error and byte offset: no leading slash, empty segment, unclosed brace, empty name, bad name, repeated name, unknown type, catch-all not last, three not-a-pchar cases (space, `#`, bad percent escape), brace inside a literal |
| R3 | The most specific route wins in both registration orders: literal, then u64, then plain parameter, then catch-all |
| R4 | A failed literal branch backtracks to the parameter, and to a catch-all with two captured values |
| R5 | A parameter accepts every RFC 3986 pchar and returns it as sent (18 values, `%20` and `%2F` among them) |
| R6 | Literals compare as raw bytes: percent escapes are case-sensitive and never decoded |
| R7 | An empty segment never matches a parameter |
| R8 | A trailing slash is strict, both ways, for literal and parameter routes |
| R9 | A catch-all matches a non-empty remainder as sent (a trailing slash and a double slash inside kept), not `/f` or `/f/`, and a 100-segment path |
| R10 | 405: a method's own most specific route first; otherwise the set of methods that match, with no captured values; 404 when none does |
| R11 | Duplicates are rejected: same shape with other names, the same literal twice; different methods and different types are not duplicates; a bad pattern is its own error |
| R12 | Typed parameters take part in routing: the largest u64, a u64 overflow falling to the string parameter, the smallest i64, an i64 underflow, a non-number |
| R13 | Captured values are views into the path (pointer identity) |
| R14 | Wide nodes (more than 8 literal children, hashed), labels longer than 8 bytes, labels that share their first 8 bytes |
| R15 | A compile-time table answers as `static_assert`s say |
| R16 | A compile-time table answers as the run-time table built from the same routes, over a grid of methods and paths |
| R17 | Word loads give the same bytes at run time as in constant evaluation, at every position of several paths |
| R18 | `find_into` on a reused result gives what `find` gives on a fresh one |
| CT | Every table shape at 10, 100 and 1,000 routes, and the 203-route GitHub API table, built at compile time and at run time, both checked against the reference answers of the P2 harness's generator; one translation unit at a time, with `REGEXMATCHER_CT_STEPS` |
| NEG | Negative compilation, one CTest entry each with `WILL_FAIL` and a check that the compiler's output names the reason: the ten pattern errors that can occur in a literal (unclosed or empty parameter, bad or repeated name, unknown type, catch-all not last, empty segment, missing leading `/`, not a pchar, brace in a literal); a handler with the wrong count and one with the wrong types, given one by one and in a table of declarations; a bad pattern and a duplicate in a compile-time table of specs and of declarations |
| NEW | New code: the method values 0 to 8; `param_t`; `invoke` converting u64 and i64 values; `check_handler` accepting handlers with and without context arguments; `fixed_string` |

The table data of CT (routes, queries, expected answers) is generated by the P2 harness and
committed as headers. It is random pseudo-words, safe to publish.

## 7. CI

The existing `ci.yaml` (Ubuntu 22.04 and 24.04 with gcc 12 as default, macOS 14 to 26,
Windows 2019 and 2022 with MSVC, two generators) stays for v1 as it is. A new workflow,
`route.yaml`, builds and tests the route target:

- Linux clang and gcc, Windows MSVC and clang-cl, macOS AppleClang;
- a Linux job with ASan+UBSan and one with TSan (MSan needs an instrumented libc++; the lab
  records cover it, section 8.4);
- the NEG tests in every compiler job, because their diagnostics differ by compiler;
- CT in its own job at one job at a time, because compile-time tables of 1,000 routes need a
  lot of compiler memory (see below);
- actions pinned by commit.

Minimum compiler versions are not asserted from memory. What is known today:
- clang 22.1.8 (L) and MSVC 19.51 (W) built the round-1 header in round 1;
- clang 18.1.3 (WSL) builds it with `-fsized-deallocation`; E2 is meant to make the flag
  unnecessary, which its first build checks;
- clang 18.1.3 compiled the five param-first 1,000-route compile-time tables of `bench/gen`
  (seeds 101 to 105) in 19.1 to 19.8 s each, at 191,724 to 195,208 KB peak resident memory
  (`/usr/bin/time`, five at once, WSL, 2026-09-30);
- gcc 14.2 (WSL) is installed but not yet tried; AppleClang is not available here.

The first CI run sets the matrix; a compiler that fails goes into the README as unsupported,
with the error. GitHub Actions does not start jobs on Alex's personal account (billing); whether
it runs for the `cpp-for-everything` organization is not known. The paper's evidence does not
depend on CI: the lab records of section 8.4 run the same suite.

## 8. How the benchmark switches to v2, and how the gate covers it

### 8.1 Arms

| Round 1 (described) | Round 2 | Code |
|---|---|---|
| the run-time-table arm (H1, H2, H3, H4) | `regexmatcher-v2`: `build_table`, then `find` through one out-of-line function | as in round 1, renamed |
| the compile-time-table arm (H7) | `regexmatcher-v2-ct`: the tables of `bench/gen`, regenerated for the new seeds | one adapter class template shared with `regexmatcher-v2` (`engineering.md`, target c) |
| the private library's router arm | dropped | it measured the private library |
| the pre-v2 router of the private library (reference, own binary) | dropped | idem |
| `regexmatcher` (reference) | `regexmatcher-v1`: v1 at d16f30a8 behind the pattern-to-regex wrapper | the wrapper moves into one header shared with the H6 server |

### 8.2 Fetching v2

`bench/cmake/arm-regexmatcher-v2.cmake`:

```cmake
set(REGEXMATCHER_DIR "" CACHE PATH "RegexMatcher v2 checkout (before the public release)")
if(REGEXMATCHER_DIR)
    add_subdirectory("${REGEXMATCHER_DIR}" regexmatcher EXCLUDE_FROM_ALL)
else()
    FetchContent_Declare(regexmatcher URL ".../tar.gz/${RB_REGEXMATCHER_V2_COMMIT}"
                         URL_HASH SHA256=${RB_REGEXMATCHER_V2_SHA256})
    FetchContent_MakeAvailable(regexmatcher)
endif()
```

Until Alex approves a public push, only `REGEXMATCHER_DIR` works. L runs from fresh clones,
so L needs the commit another way: a bare repository on L (`~/lab/git/RegexMatcher.git`),
pushed from W over the management link. That is a private copy on a lab host, not a public
push. The publication run needs the measured commit to be public before the paper is
submitted (`schedule.md`).

### 8.3 v1 and v2 in one build

Both define a CMake target `RegexMatcher` if both are added with CMake, and both put headers
under `matcher/`. So:
- v1 is fetched with `SOURCE_SUBDIR no-cmake`, the way rbench already fetches nanobench, so
  none of its CMake runs. An rbench target `rb_regexmatcher_v1` (INTERFACE) points at its
  `include/`.
- Each arm is its own object library with its own include path. No translation unit sees
  both include directories. The v2 umbrella never includes `core.hpp`, so the program holds
  one definition of the engine's templates, v1's.

### 8.4 The inputs gate

Today, `lab/bin/inputs_hash.py` counts as first-party only files under the private library's
checkout (found through its CMake project's source-directory cache entry), the bench
directory, and files generated outside `_deps`. Files under `FETCHCONTENT_BASE_DIR` are left
out, and only the fetched URL and hash are recorded (`third_party.fetched`). A v2 fetched
with FetchContent, or added from a checkout outside the tree, would therefore not be in any
hash, and the gate would pass whatever v2 code was compiled.

Proposal, a lab change in its own commit after Alex's yes:
1. `--dep-root LABEL=CACHE_KEY` (repeatable, in both modes): the directory named by that
   cache entry is a first-party root with that label. v2's root calls
   `project(RegexMatcher ...)`, which puts `RegexMatcher_SOURCE_DIR` in the cache, as the
   private library's project did for its own entry. The roots are sorted longest first, so
   `_deps/regexmatcher-src` wins over the `_deps` exclusion, and a checkout outside the tree
   is covered too.
2. `--label-hash PREFIX` (repeatable): per target, a sha256 over the sorted
   `<path>\t<sha256>` lines whose path starts with PREFIX. The prefix compared is
   `regexmatcher/include/`, not the whole label: a standalone RegexMatcher build also compiles
   its test sources under the same project root, so a hash over the whole label could never
   equal the arm's.
3. Without the new flags the output is bit-identical. `lab/bin/test_inputs_hash.py` gains
   cases for both flags, and the last round-1 records' inputs are recomputed before the
   change is committed and must match.

The gate (`bench/check_records.py`, rewritten for round 2):
- every rbench target is covered per sanitizer by a green rbench record that compiled the
  same inputs, as in round 1, the v2 files now inside those inputs;
- the hash of the prefix `regexmatcher/include/` of the v2 arm's target equals the hash of the
  same prefix of the test targets of a green RegexMatcher record for each of ASan+UBSan, TSan
  and MSan on L. The arm and the tests include only the umbrella, so they compile the same set
  of v2 headers;
- v1 stays third-party, as in round 1: pinned by commit and sha256, recorded in
  `third_party.fetched`, its wrapper hashed as bench code.

The RegexMatcher records come from a new script in the paper repository,
`bench/sanitize_regexmatcher.sh` (and `.ps1` for W). It configures v2 with its tests and one
sanitizer, builds, runs the whole CTest suite with every test's output kept (R, CT, NEG,
NEW), scans it with the shared report pattern (`lab/bin/test_report_pattern.sh` checks it),
and writes `regexmatcher-<commit, 9 characters>-<host>-<sanitizer>.json` to
`lab/sanitizer-records/`. Logs go to `~/lab/records-logs/<record>/`, archived with their
sha256 (D5). On W, an MSVC ASan and a clang-cl ASan record of the suite are extra coverage:
P2 measures on L only, so they do not gate.

## 9. The objdump check (development evidence only)

After E1 and after E2, the lookup's machine code is compared with round 1's:
1. compile one translation unit that defines `find_v2` (the out-of-line lookup both v2 arms
   call) against the round-1 header, and one against v2, with the same compiler and flags;
2. `objdump -d --no-show-raw-insn -M intel -C` of `find_v2` and of every function it calls
   that is not inlined;
3. normalize: drop addresses, map the old namespace to the new one in symbol names;
4. the diff must be empty, except section names, which carry the mangled names.

A dry run today, with clang 18.1.3 in WSL at `-O3 -DNDEBUG -std=c++23`, compared the round-1
header with a scratch copy that only renamed the namespace and the macro prefix: four
functions (`find_v2`, and out of line with clang 18, `find_in`, `walk`, `allowed_methods`),
1,043 lines of normalized disassembly, identical but for the three mangled section names.
The scratch copy lives only in the session's scratch directory and is not committed. With
clang 22.1.8 the check is repeated on L the first time L is free. The check is evidence for
development only. Round 2 measures everything again; no round-1 number is carried over.

## 10. Versioning

Facts: tags `1.0.0.0` and `1.0.0.1` (four parts); `main` declares 2.0.0.1 since commit
2830797 ("Fix Version macros"), untagged; d16f30a8 also declares 2.0.0.1.

Proposal: v2's first release is `2.1.0.0`. It keeps "v2" and the four-part scheme, and it is
above every version `main` has declared, so a version comparison never goes backwards for
someone who built `main`. It is a major change for users of the regex engine's CMake (C++23
for the new target, CMake 3.25), and 2.0.0.1 was never released, so there is no 2.x user to
break. Alternatives: `2.0.0.2`, or three-part `v2.1.0`. Alex decides.

## 11. Licence

`LICENSING.md` (read today): RegexMatcher is dual-licensed, GPLv3 or a commercial licence,
"Copyright (C) 2025 Alex Tsvetanov". It has a clause that grants the commercial licence at no
fee to holders of a commercial licence of another product of the author, and that clause
names the private library. `README.md` states `SPDX-License-Identifier: GPL-3.0-or-later`,
while `LICENSING.md` says "GPLv3" without "or later".

For v2:
- new files carry the SPDX line of the README and a 2026 copyright line;
- the extracted code comes from the private library, which Alex owns; placing it under
  RegexMatcher's licences is his decision (question 3 of the report);
- the clause naming the private library is Alex's text in a public file. The paper cites
  RegexMatcher, so a reader following that citation sees the name. This note does not edit
  it; whether it stays until the private library is published is Alex's decision;
- "or later" or "only" should be made consistent between the README and `LICENSING.md`;
- the paper repository links v2 (GPLv3) into rbench beside MIT, BSD, Apache-2.0 and Go-licensed
  arms, and into the minimal server. That is allowed for GPLv3, but the paper repository then
  needs a licence compatible with GPLv3 for its own code before it is published.

## 12. Files to create or change in RegexMatcher

| File | Action |
|---|---|
| `include/matcher/route.hpp` and `include/matcher/route/*.hpp`, `route/detail/words.hpp` | new (E1, E2) |
| `docs/route-semantics.md` | new: rules 1 to 7 |
| `tests/route/CMakeLists.txt`, `tests/route/test_*.cpp` (R1 to R18, NEW) | new |
| `tests/route/ct_tables/*.hpp`, `test_ct_*.cpp`, `CMakeLists.txt` | new (CT) |
| `tests/route/neg/*.cpp`, `neg/CMakeLists.txt`, `neg/neg_compile.cmake` | new (NEG) |
| `CMakeLists.txt` | minimum 3.25, per-target standards, options, the route target, install and export |
| `include/CMakeLists.txt` | the route `FILE_SET` |
| `tests/CMakeLists.txt`, `external/CMakeLists.txt` | only when tests or benchmarks are on |
| `pkg/RegexMatcher-config.cmake.in` | include directory fixed |
| `.github/workflows/route.yaml` | new |
| `README.md` | the route matcher: usage, semantics link, supported compilers, the P2 paper once it has a DOI |
| `CITATION.cff` | version |
| `CHANGELOG.md` | new: 2.1.0.0 |

Nothing is pushed to the public repository without Alex's yes.

## Revision log

- 2026-09-30: first version, for review.
- 2026-09-30, approved. Decisions that touch this note: the `--dep-root` change of section 8.4
  goes ahead on condition that every existing P1 and P2 hash stays byte-identical, proven by
  `lab/bin/test_inputs_hash.py` on stored files; the ablation arm `regexmatcher-v2-r1` is the E1
  state of section 2.1 (renamed, not re-engineered), vendored into the harness under the
  namespace `matcher::route_r1` and the macro prefix `MATCHER_ROUTE_R1_`, so that it links
  beside v2 in one binary, and checked with the objdump check of section 9. Work happens in a
  local branch of the RegexMatcher checkout, never pushed to GitHub; a bare repository on L is
  the only other copy. Sections 3, 10 and 11 (the tag at d16f30a8, the engine commits, the
  version and the licence) wait for Alex.
- 2026-09-30, during implementation (local branch `v2/route-matcher`, commits cc30102 to
  150d4ab), where the code differs from the text above, and why:
  1. The generated `include/matcher/RegexMatcherConfig.h` is ignored by git on `main`, not
     committed (section 4 said committed); nothing changes.
  2. The checked front end's API, as built: `handlers<R, Context...>` with `get`, `post`, `put`,
     `del`, `patch`, `head`, `options` and `route<M>`, each returning a `Decl<R, Context...>`
     (method, pattern, and a function that converts the captured values and calls the handler);
     `make_route_table<Decls>()` returns `RouteTable{table, routes}`, a match's route being the
     index of its declaration; `invoke<P, F, Context...>(values, ctx...)`; `check_handler<P, F,
     Context...>()`. A generic lambda has no fixed arity and is checked by invocability alone.
     `Method` and the `find` overloads by method are in `route/method.hpp`.
  3. The checked front end's tests are an executable of their own (`route_checked_tests`), so
     that E1 and E2 went green before the new code existed. There are 17 negative-compilation
     cases: ten pattern errors, handler count and types one by one and in declarations, a bad
     pattern and a duplicate in a table of specs, and a duplicate in a table of declarations.
  4. The CT data is generated by a tool of the paper repository, `bench/tools/gen_route_tests`
     (built from `bench/core` alone), not by an rbench subcommand; it equals round 1's
     compile-time-table test data file by file.
  5. The exported targets now carry the namespace `RegexMatcher::`, the test executable is no
     longer installed, and GoogleTest is fetched only when tests are built. In WSL the tests
     build against a local copy of GoogleTest v1.15.2 (`FETCHCONTENT_SOURCE_DIR_GOOGLETEST`),
     so no download happens.
  6. `.github/workflows/route.yaml` pins `actions/checkout` v7.0.1 and `ilammy/msvc-dev-cmd`
     v1.13.0 by commit, read from the GitHub API on 2026-09-30.
  7. Results in WSL (development only): clang 18.1.3 and gcc 14.2 pass 81 of 81 tests; the
     objdump check is identical at E1, E2 and after the checked front end, with both compilers
     (`lab/evidence/2026-09-30-W-regexmatcher-v2-objdump`); development sanitizer runs of the route suite in WSL (clang 18.1.3; ASan+UBSan, TSan, MSan with an instrumented libc++ 18) pass 62 of 62 tests each with no report. The sanitizer builds of
     clang 18 in WSL need `-resource-dir=$HOME/opt/clang18-res`, where its runtimes are.
  8. Also checked on 2026-09-30 (development): natively on W, MSVC 19.51 and clang-cl 22.1.0
     pass the regex engine's, the route and the checked front end's tests and the 17
     negative-compilation cases (59 of 59 each; the compile-time tables of 1,000 routes not
     built on Windows); MSVC /W4 gives 6 warnings C4324, the intended padding of the
     compile-time table's 64-byte-aligned arrays. In WSL the regex engine's 19 tests pass under
     ASan+UBSan, TSan and MSan with no report, so a record of the whole suite is not held back
     by the engine (RegexMatcher commit 53e8dda).
- 2026-09-30, second milestone (RegexMatcher 39f3e48 and f48fa83; paper-typed-routing aa869d1
  to d9268c4), where the code differs from the text above, and why:
  1. The build rework of `engineering.md`, section 1.4, is in `route/table.hpp`: an entry is
     method, route, spec index, first segment and segment count, over one array of segments
     reserved from the number of '/' in all patterns; indices are sorted and split, never
     entries; one stack holds the literal groups of the node being built. The table is
     unchanged (`engineering.md`, revision log). The CMake version stays 2.0.0.1 until Alex
     decides it.
  2. Section 8.2's CMake is `bench/cmake/regexmatcher-v2.cmake`, included once when the build
     has `regexmatcher-v2` or `regexmatcher-v2-ct`; the ablation arm compiles only its vendored
     header and needs neither. A snapshot made with `git archive` has no git metadata, so a
     cache entry `REGEXMATCHER_COMMIT` gives the commit that rbench records as
     `regexmatcher_commit`; without it the field is "unknown".
  3. Section 8.4's prefix hash: `bench/build.sh` writes `BUILD_DIR.v2-include.json`, the hash
     of the inputs under `regexmatcher/include/` of `arm_regexmatcher_v2` and
     `arm_regexmatcher_v2_ct`, from a second run of `inputs_hash.py` over those two targets
     only (`--label-hash` refuses a target that has no file under the prefix, such as
     `arm_null`). In WSL at f48fa83 both arms hash the same 9 headers to the same value.
  4. The `scope` sentence that `inputs_hash.py` writes into every `inputs.json` still names
     round 1's first-party checkout, which round-2 builds do not have. The script's default
     output is kept byte-identical on purpose (P1's and round 1's stored hashes), so the
     sentence stays; the gate reads `dep_roots` and the hashes, not that sentence.
  5. The bare repository on L holds `v2/route-matcher` at f48fa83, pushed from W to the
     remote named `lab`; nothing is pushed to GitHub.
- 2026-09-30, C2 (RegexMatcher 45ab696; paper 4dd16b7): the one layout of `engineering.md`,
  section 3.4, and where it differs from the text above:
  1. New API: `RuntimeTable` (move-only; `view()`, `data()`, `bytes()`, and `error`,
     `error_route`, `error_other` as in `Built`) and `make_runtime_table(specs)`, in
     `route/runtime_table.hpp`; `table_layout(StaticSizes)` and `TableLayout`, `kPageAlign`
     (4,096) beside `kTableAlign` in `route/table.hpp`, where `StaticSizes` moves too.
     `build_table`, `Built`, `StaticTable`'s members and contents, and the lookup are
     unchanged; `make_static_table` checks with `static_assert` that its members lie where
     `table_layout` puts a run-time table's arrays.
  2. The page alignment of a compile-time table is on its declaration
     (`alignas(kPageAlign) constexpr auto t = make_static_table<routes>();`), not on
     `StaticTable`. On the type it would round `sizeof` up to a page, and a table of m = 10
     (1,307 to 2,651 bytes of `.rodata` in WSL, lab evidence `2026-09-30-W-regexmatcher-v2-c2-
     layout`, objsize.txt) would take 4,096; on the declaration only the object's placement
     changes, though the object file pads to the alignment. The library documents the
     declaration.
  3. An empty `std::array` member takes bytes that the standard library chooses, so
     `table_layout` uses `sizeof(std::array<T, 0>)` for an empty array, and the tests check its
     result against `offsetof` on every compiler that builds them.
  4. The run-time arm of the harness builds with `make_runtime_table`; the harness at 4dd16b7
     needs RegexMatcher 45ab696 or later. 45ab696 goes to the bare repository on L after the
     first L slot, which measured f48fa83.
- 2026-09-30, the records scripts before the L records (paper 9ad87ab):
  1. `bench/sanitize_regexmatcher.sh` and `bench/sanitize_rbench.sh` keep their logs as rule D5
     asks: in `~/lab/records-logs/<record>/` (for rbench: the build log, what the build compiled,
     and run_grid.sh's whole output; not the build tree), packed into `<record>.tar.gz` beside
     it, whose sha256 the record carries (`bench/keep_record_logs.sh`). Each refuses to start when
     that directory or archive exists.
  2. Section 8.4's W script is `bench/sanitize_regexmatcher.ps1`: MSVC or clang-cl ASan, Ninja,
     Release, the whole suite with every test's output kept, inputs hashed as on L; the record is
     written by the same `bench/regexmatcher_record.py` and named
     `regexmatcher-<commit>-W-asan.json` (`-W-asan-clangcl.json` for clang-cl). The script counts
     the reports with its own copy of the shared pattern and stops if the writer's count differs;
     `lab/bin/test_report_pattern.sh` checks that copy.
  3. GoogleTest for the records is a local copy of its official repository at the pinned commit
     b514bdc8 (v1.15.2), exported with `git archive` from a checkout that `git fsck --full` found
     sound, and given to CMake as `FETCHCONTENT_SOURCE_DIR_GOOGLETEST`; the record's note gives the
     tree hash and the archive's sha256. No download happens.
- 2026-09-30, after the first L record of RegexMatcher went red on a parser bug (lab journal):
  1. `bench/regexmatcher_record.py` read CTest's summary only in the form
     `P% tests passed, F tests failed out of T`; CTest 4.4.3 on L writes `100% tests passed out
     of 87` when none failed, so `regexmatcher-d1d73e99b-L-asan` went red with 87 of 87 tests
     passed and no report. The writer now accepts both forms (0 failures when the clause is
     absent), with every other condition for green unchanged, and `bench/test_record_writers.py`
     tests it. The red record is kept as evidence beside its logs on L, never in
     `lab/sanitizer-records/`, and the record is made again under its name.
  2. The gate of section 8.4 also matches pins (approved by the coordinator before the freeze):
     rbench's records carry the sha256 of `bench/cmake/pins.cmake` and the archives the build
     fetched as used; `bench/check_records.py` counts a record only if both equal the measured
     build's (`bench/gate_lib.py`), so a build whose pins differ from its records' is refused, and
     `bench/run_baseline.sh` and `bench/ct_cost_run.sh` record the sha256. Before, a changed pin
     of a header-only C++ competitor whose adapter did not change would have passed the gate.
     `bench/test_gates.py` checks a build with one pin changed.
- 2026-09-30, three gaps closed before the freeze (coordinator):
  1. `bench/ct_cost_run.sh`, which measures H7's costs, is gated like every measured build: its
     build of the compile-time arm is hashed and checked by `bench/check_records.py` against the
     records and pins, and the costs are read only if the gate passes (`CHECK_ONLY=1` gates
     without reading costs). The script could not configure before: the compile-time arm needs
     `regexmatcher-v2` in `RB_ARMS` (it defines the lookup both arms call), so both are
     configured and only the compile-time arm's target is built.
  2. Every process is checked on every query of its ring. A process's agreement pass still stops
     at 120 s (the compiled code is unchanged, so are the records); `bench/run_grid.sh` now ends
     every grid by checking each process that pass cut on every query, untimed, with
     `tools/verify_answers` linked from the grid's own build (`tools/build_verify.py`,
     `tools/verify_unverified.py`), and writes `verified.jsonl` into the run;
     `analysis/analyse.py` reads it, and `analysis/cells.py` fails a cell with a process that
     neither check verified. `tools/verify_cover.py` shows the tool covers every arm.
