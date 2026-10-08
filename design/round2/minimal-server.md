# The paper's minimal HTTP/1.1 server

Status: design for review, round 2 of P2, phase 1. Nothing here is implemented. Written
2026-09-30. Once Alex approves it, this note is frozen and later changes go into a revision
log at its end.

Words: "the private library", "v1" and "v2" as in `regexmatcher-v2.md`.

In round 1, H5(c) was tested in the private library's own suite and H6 ran the private
library's server twice, once per router. Under the component model this repository needs its
own server with exactly the features H5(c) and H6 study, optimized as far as that scope
allows. Everything else is out.

## 1. What it must do, and for which hypothesis

| Behaviour | For |
|---|---|
| HTTP/1.1 over TCP on loopback, keep-alive, one worker thread | H6 |
| The routes of one table, read from the routes file `h6_targets` writes (`GET <pattern>` per line, rbench's syntax: `{name}` a parameter, `{*name}` a catch-all), each answering 200 with the fixed 13-byte body `Hello, World!` | H6 |
| `GET /` with the same body, for lab/t1's readiness probe; it is not in the targets file | H6 |
| The request target's path given to the router as sent, without its query | H6, rule 1 of the semantics |
| HEAD on a path that only GET routes match: the GET route answers with the status line and header fields of the GET response (Content-Length 13 included) and no content | H5(c) |
| A route registered for HEAD wins over the GET fallback | H5(c) |
| 405 when only routes of other methods match, with an Allow field listing them; Allow lists HEAD whenever it lists GET | H5(c) |
| 404 when no route of any method matches | H5(c), H6 (never on its targets) |
| Pipelined requests answered in order | correctness; round 1's server answered a second pipelined request with 400 (`results/README.md`), and this server must not |
| `--port P --workers 1 --routes FILE --router v2\|v1\|null`; readiness when the listening socket accepts; SIGTERM or SIGINT stops it cleanly | lab/t1's contract (`t1.py`: `start_server`, `wait_ready`, `probe`, `stop_process`) |

H5(c) is HTTP/1.1 only in round 2. The HTTP/2 part is dropped with its reason in the revision
log (`hypotheses-v2-proposal.md`): the server has no HTTP/2, and the HTTP/2 evidence of round
1 was never green on Linux.

Out of scope, and refused rather than half done:
- request bodies with a transfer coding: 501, then close;
- a request head over 8 KiB: 431, then close;
- a target not in origin form: 400;
- more than one worker: refused at start;
- TLS, HTTP/2, compression, static files, timers other than the Date cache.

A request body with Content-Length is read and discarded. HTTP/1.0 requests are answered and
the connection closes unless the request asks for keep-alive; `Connection: close` is honoured.
Every response carries a Date field, formatted once per second and copied.

## 2. Structure

```
server/CMakeLists.txt        added to the paper's root CMakeLists.txt
server/src/main.cpp          arguments, the routes file, the signal thread, the arm table
server/src/loop.cpp          epoll: listener, connections, buffers
server/src/http1.cpp         request parsing, the response bytes, HEAD and 405
server/src/route.hpp         the router interface below
server/src/route_v2.cpp      RegexMatcher v2
server/src/route_v1.cpp      v1 behind the pattern-to-regex wrapper
server/src/route_null.cpp    the null router
server/tests/                unit tests, the loopback tests, the arms' agreement test
```

**One binary, three router arms.** The HTTP and I/O code is compiled once. The router is
chosen at start (`--router`) and called through one function pointer:

```cpp
struct RouteResult {
    std::uint8_t status;        // found, method not allowed, not found
    std::uint8_t count;         // captured values
    std::uint16_t allowed;      // with 405: bit m for every method that matches
    std::uint32_t route;
    std::array<matcher::route::Capture, 16> values;   // views into the path; never zeroed
};
using FindFn = void (*)(const void* router, unsigned method, std::string_view path, RouteResult& out);
```

The arms then differ only in the function behind the pointer and in the router's data, so
the server's machine code is the same for both sides of H6's ratio, and one set of sanitizer
records covers all three arms. Round 1 built one server source twice against two
libraries; H6's text says how this changes (`hypotheses-v2-proposal.md`).

- **v2 arm**: `find_into` of RegexMatcher v2 into the reused result; the table is built at
  start with `build_table` (rbench's run-time arm, the same code).
- **v1 arm**: RegexMatcher's engine at d16f30a8 behind the wrapper rbench's reference arm
  uses, moved into one header shared by both (`bench/arms/regexmatcher_v1_wrap.hpp`): one union
  automaton per method; a parameter becomes `([A-Za-z0-9_.%\-]+)`, a catch-all
  `([A-Za-z0-9_.%\-\/]+)`; `compile()` after the last route; `match_with_groups`, the
  lowest route id wins, the captured values from the reported offsets; 405 by trying the
  other methods, as rbench's harness does for arms without their own. Its parameter class is
  narrower than a pchar, so it fails the H5(b) probes; it is judged only on H6's targets,
  whose parameter values are `[a-z0-9]`. The loopback agreement test checks, on every H6
  table, that the v1 and v2 arms answer every target with the same route and the same
  captured values.
- **null arm**: answers route 0 without reading the path, no captured values. It measures the
  server's time per request without routing (H6, `hypotheses-v2-proposal.md`).

The HEAD fallback and the Allow field live in `http1.cpp`, above the router interface, so they
are the same code for every arm. The router answers for the method it is asked; this is rule
8 of the round-1 design note, now in the server.

## 3. I/O backend: epoll

One worker thread runs an epoll loop:
- the listener is non-blocking and level-triggered; `accept4` with `SOCK_NONBLOCK |
  SOCK_CLOEXEC` until `EAGAIN`; `TCP_NODELAY` on each connection;
- a connection has one input and one output buffer, allocated once and reused;
- on readable: `recv` until `EAGAIN` or a full buffer, parse every complete request in it,
  append each response to the output buffer, then one `send`; `EPOLLOUT` is armed only when a
  `send` was partial, and disarmed when the buffer drains;
- a signal thread waits in `sigwait` for SIGTERM and SIGINT, sets an atomic stop flag and
  writes an eventfd the loop watches.

At depth 1 with keep-alive, a request costs one `recv` and one `send`; one `epoll_wait`
serves every connection that is ready.

Why epoll:
1. **MemorySanitizer.** Round 1's red MSan record came from io_uring: the kernel's writes into
   a buffer are invisible to MSan, while `recv`, which MSan intercepts, passed the same test on
   epoll (`results/README.md`, "H5(c) over HTTP/2"). With epoll every byte the server reads
   comes through an intercepted call, so the L records need no unpoisoning. The
   `epoll_event` array is value-initialized anyway.
2. **The ratio.** Both router arms run the same backend, so its cost is on both sides of H6's
   ratio. A faster backend would make routing a larger share of a request; the simpler one
   makes the direction test of H6 harder to pass, not easier.
3. **Development.** The same code runs in WSL (kernel 6.6) and on L (kernel 7.2.3 in round 1).

Considered and not chosen:
- io_uring with multishot accept and receive and registered buffers: fewer system calls per
  request, but it needs value-initialization and unpoisoning for MSan (P1's design took that
  discipline for its loop), and I/O is not what P2 studies;
- a thread per connection: 64 threads on one core, whose switches would dominate.

## 4. Optimization within this scope

- No heap allocation per request in steady state, in the server's own code: buffers per
  connection, the router's result on the stack and reused, response bytes built once at start
  (status line, header fields, body), the Date field patched in place once a second.
- The v2 arm calls `find_into`, so the 16 captured values are written, never zeroed or
  copied.
- No logging per request.
- `-O3 -DNDEBUG -std=c++23`, the flags of rbench's arms, one compiler for all arms.

The v1 arm allocates in every lookup: round 1's T0 counted 4 to 210.8 allocations per lookup
for the reference arm on the same engine (`results/table_s1_all_arms.csv`, the
`regexmatcher` rows). That is the baseline's own cost, measured as it is.

## 5. Tests, written first

| Test | Checks |
|---|---|
| parser | request line, header fields, a split read, a pipelined buffer of three requests, each refusal of section 1 |
| response writer | a GET response and a HEAD response are byte-identical up to the end of the header section, and the HEAD response ends there |
| HEAD and 405 | HEAD on a GET-only path answered by the GET route; an explicit HEAD route wins; 405 lists the matching methods and HEAD whenever GET; 404 |
| loopback, raw socket | byte-exact answers; HEAD then GET on one keep-alive connection (no body after the HEAD response, so the GET response parses); three pipelined requests answered in order; `Connection: close` |
| lab/t1 contract | readiness on connect, `GET /` answers the probe with the 13-byte body, SIGTERM exits with 0 |
| agreement | on each H6 table, every target answered with the same route and captured values by the v1 and v2 arms, and route 0 by the null arm |

The loopback tests are one C++ executable (no third-party test framework, so the MSan build
needs no instrumented framework), run by CTest.

## 6. H6 tools

- `t1/h6_targets.cpp` stays (it compiles `bench/core` unchanged) and gains `--table-seed` and
  `--ring-seed`, so the round-2 pair is given, not built in.
- `t1/run_h6.sh` is rewritten: it builds the server once, gates it (section 7), and for each
  cell writes an `arms.json` with three arms that differ only in `--router`, as round 1's
  script wrote its two per cell. lab/t1's `t1.py` and `t1gen` are used unchanged.
- The private library's build (its checkout option in the root CMakeLists.txt and in
  `t1/build_h6.sh`) is removed, and `t1/h6_server.cpp` goes; the repository's history keeps
  it.

## 7. Sanitizer plan

**L, clang 22.1.8, gating.** Three records, ASan+UBSan, TSan and MSan (libc++ instrumented,
at the prefix round 1's L records used, `$HOME/opt/libcxx-msan-gcc`), each named
`mserver-<commit, 9 characters>-L-<sanitizer>.json`. Each builds the server with all three
arms, then:
1. runs the whole test suite of section 5, every test's output kept and scanned with the
   shared report pattern;
2. runs a reduced H6 exercise: for each of the nine H6 cells and each arm, the sanitized
   server serves the cell's targets through `t1gen` for a short window at depth 1, then one
   pipelined burst; zero errors, the body checked, SIGTERM, exit code 0, no report. Round 1's
   `t1/h6_exercise.py` and `t1/h6_record.py` are the pattern.

TSan sees two threads, the worker and the signal thread, meeting in the atomic stop flag and
the eventfd. MSan sees only intercepted calls (section 3). No report is waived. Logs go to
`~/lab/records-logs/<record>/` and are archived with their sha256.

**W.** The server is Linux-only (epoll), so W has no server record. RegexMatcher's own W
records cover the library (`regexmatcher-v2.md`, section 8.4).

**WSL, development only.** clang 18.1.3 with ASan+UBSan, TSan and MSan against the
instrumented libc++ 18 at `~/opt/libcxx-msan-18` (present today), as P1's development used.
Never a record.

**The gate** (`t1/check_h6_records.py`, rewritten): the server's compiled inputs, hashed in
project mode with `--dep-root regexmatcher=RegexMatcher_SOURCE_DIR`, must match a green L
record of each sanitizer; the hash of the prefix `regexmatcher/include/` must match green
RegexMatcher records
(`regexmatcher-v2.md`, section 8.4); v1 is third-party, pinned, and its wrapper is hashed as
this repository's code; `t1gen` is gated by its own record, as in round 1. The run refuses to
start otherwise.

## 8. Files

| File | Action |
|---|---|
| `server/**` | new (section 2) |
| `CMakeLists.txt` (paper root) | the private library's part replaced by `add_subdirectory(server)` and the RegexMatcher fetch of `regexmatcher-v2.md`, section 8.2; a project option for the sanitizer, not the private library's option name |
| `bench/arms/regexmatcher_v1_wrap.hpp` | new: the wrapper, shared by rbench's reference arm and the server |
| `t1/h6_targets.cpp` | seeds as arguments |
| `t1/run_h6.sh`, `t1/check_h6_records.py`, `t1/sanitize_h6.sh`, `t1/h6_exercise.py`, `t1/h6_record.py` | rewritten for one binary with three arms |
| `t1/h6_server.cpp`, `t1/build_h6.sh` | removed |
| `analysis/h6_stats.py`, `analysis/macros_h6.py` | the three arms and the H6 statistics of `hypotheses-v2-proposal.md` |

## Revision log

- 2026-09-30: first version, for review.
- 2026-09-30, approved: epoll only.
- 2026-09-30, first implementation (paper commits 376c71d to 47e699f; development in WSL, clang
  18.1.3, tests written before the code), and where it differs from the text above:
  1. The router interface's result is RegexMatcher v2's `Match` itself (`server/src/route.hpp`),
     so the v2 arm calls `find_into` into the reused result with nothing copied, as section 2
     intends; the v1 and null arms set the same fields.
  2. Refusals, each followed by closing the connection: 400, 431 and 501 as section 1 says;
     501 also for a method token the server does not know (the nine methods of RegexMatcher v2
     are known); and 413 for a request larger than a connection's 64 KiB input buffer (a body
     with Content-Length is skipped only when it fits), which section 1 did not name.
  3. The responses carry Date, Content-Type: text/plain (200 only) and Content-Length, then
     Connection when the connection closes, or is HTTP/1.0 with keep-alive. 404 and 405 have no
     content; 405 lists Allow in the order GET, HEAD, POST, PUT, DELETE, PATCH, OPTIONS, CONNECT,
     TRACE.
  4. The v1 arm is a library of its own (`server/src/arm_v1.cpp`), whose translation unit sees
     v1's include directory and not v2's, as rbench keeps its arms apart (both checkouts have a
     `matcher/core.hpp`). v1 is fetched as rbench fetches it (`bench/cmake/regexmatcher-v1.cmake`,
     split out of `arm-regexmatcher-v1.cmake`). The root path, which has no segment, is given
     the expression `\/`.
  5. Tests (CTest, no test framework): `test_http1` (parser, responses, HEAD and 405, no
     allocation per request), `test_loopback` (section 5's loopback list), `test_contract` (the
     binary, lab/t1's contract, for each arm), and `h6_agreement` (the arms on the nine H6
     cells at pair (111, 211), through `t1/h6_targets`; correctness only). All pass in WSL,
     and the first three under ASan+UBSan and TSan (development, not records).
  6. The root CMakeLists.txt builds `h6_targets` and adds `server/`; its sanitizer option is
     `P2_SANITIZER`. `t1/h6_server.cpp` and `t1/build_h6.sh` are removed. Still to do: the t1
     scripts of sections 6 and 7 (`run_h6.sh`, `sanitize_h6.sh`, `h6_exercise.py`,
     `h6_record.py`, `check_h6_records.py`), with the records work of the other gates, and the
     MSan run, which needs the instrumented libc++.
- 2026-09-30, before the L records (paper 9ad87ab):
  1. `t1/run_h6.sh` asked t1.py for at least 5 pairs, while H6 (`hypotheses-v2-proposal.md`,
     section 3.5) asks for at least 6, so that an exact sign test of a cell can reach
     2^-6 = 0.0156, below 0.025 (rule D9). It now asks for 6.
  2. `t1/sanitize_h6.sh` keeps a record's logs as rule D5 asks: everything in its work directory
     but the build tree is copied to `~/lab/records-logs/<record>/` and packed into
     `<record>.tar.gz` beside it, whose sha256 the record carries (`bench/keep_record_logs.sh`,
     shared with the other records scripts). The script refuses to start when that directory or
     archive exists, so a record is never made again over an earlier one.
- 2026-09-30, after the first L record went red on a parser bug (lab journal):
  1. CTest 4.4.3 on L writes its summary as `100% tests passed out of 87` when no test failed,
     without the clause `, 0 tests failed`; `t1/h6_record.py` required that clause, as did
     `bench/regexmatcher_record.py`, whose first L record went red on it with 87 of 87 tests
     passed and no report. Both writers now read `(\d+)% tests passed(?:, (\d+) tests failed)? out
     of (\d+)`, counting 0 failures when the clause is absent; every other condition for green is
     unchanged. `bench/test_record_writers.py` tests both writers with both forms and with a
     summary that has failures, which stays red.
  2. The pins (approved by the coordinator before the freeze): the server's records carry the
     sha256 of `bench/cmake/pins.cmake` (`pins_sha256`, CRLF read as LF) beside the archives the
     build fetched as used (`third_party.fetched`); `t1/check_h6_records.py` counts a record only
     if both equal the measured build's, so a build whose pins differ from its records' is
     refused; `t1/run_h6.sh` records the sha256 in its provenance. `bench/test_gates.py` checks a
     build with RegexMatcher v1's pin changed.
  3. Both change `t1/`, so the server records' code commit (the last commit that changed the
     server's sources, `t1` among them) moves from 9ad87ab to the commit of these changes.
- 2026-09-30, `t1/run_h6.sh` takes `CHECK_ONLY=1`, as `bench/run_baseline.sh` does: it builds the
  server and t1gen, runs the gate, checks that t1gen's own record (`t1gen-<commit>.json`, the rule
  lab/t1's t1.py applies to every window) is green, and measures nothing. The full run makes the
  same t1gen check before it measures. Not compiled, so no record changes.
- 2026-09-30, the audit of the draft:
  1. (M3) Only valid pairs count toward H6's minimum of 6 and toward the stop: `t1/run_h6.sh` passes
     `--valid-pairs-only` to lab/t1's `t1.py` (Papers repository; a round counts only if all six of
     its windows are valid, `lab/t1/test_t1_pairs.py`), so the driver cannot stop at six rounds of
     which fewer than six are valid. Without the flag `t1.py` behaves as before.
  2. (m22) Section 7 says the records' H6 exercise serves each cell's targets through t1gen for a
     short window; the records script uses `t1/h6_exercise.py` instead, which requests every target
     once over one keep-alive connection, then GET / and an unmatched path, then a pipelined
     burst, untimed.
