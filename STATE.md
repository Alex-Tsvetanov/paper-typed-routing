# P2 round 3, state digest

Under 200 lines. Read this first. Updated 2026-10-23, evening.

## What round 3 is

The end-to-end block of P2 (brief `p2-typed-routing/AGENTS.md` in the Papers repository; plan v2
section 2.2 and the P2 row of section 3.2). v2 in an HTTP server against each external router
hosted in an HTTP server, at round 2's table sizes (m = 10, 100, 1,000, 10,000, 100,000), on both
systems of the laptop. Plus the H7 MSVC compile costs measured again on the laptop's Windows.
Round 2 is the prior study; its frozen files are never edited.

## Worktree and base

- Worktree `D:\Dev\worktrees\p2-round3`, branch `round3`, from 801aa8c.
- Why 801aa8c: it is the committed gitlink and the tip of `main`. The manuscript branch
  `dev/alex-tsvetanov/jss-manuscript` (d38847f) adds two commits that change only `paper/`,
  `.gitignore` (`*.spl`) and a dated note at the end of `design/round2/schedule.md`. No code
  differs. Round 3 is engineering, so it stays off the manuscript branch and its owner's edits.
- The worktree links are relative (`git worktree repair --relative-paths`), so git works in the
  `papers-dev` container. The repair also made `D:\Dev\GitHub\paper-arms-e`'s link relative; it
  still resolves (checked).
- Scratch outside the repository: request sets `D:\Dev\worktrees\p2r3-data\requests\`, builds
  `D:\Dev\worktrees\p2r3-build\`, container build trees in the docker volume `p2r3-home`.

## Rules that bind this work

- No timing on the desktop. No req/s, latency or compile-time number from it, ever.
- No laptop access; laptop jobs go under "Laptop requests". Nothing pushed.
- Linux builds in `papers-dev:arch-2026-10-23`; Windows with the desktop's MSVC 19.51.36246.
- `hypotheses-round3.md` and `design/round3/end-to-end.md` are drafts. No freeze here.

## Documents

- `design/round3/end-to-end.md`: the design draft. Estimand (same-server contrast tested;
  increments across servers reported), cells, replicates, request sets, the server contract,
  hosting per language, Windows, risks, Alex's decisions, laptop time.
- `design/round3/router-survey.md`: the survey of the sixteen routers (Sonnet), with my re-check of
  the claims round 3 uses at its end.
- `hypotheses-round3.md`: DRAFT hypotheses H8 (v2 not slower in the C++ server) and H9
  (carry-over), and what is reported only.

## What exists (code)

- `server/` C++ server `mserver`: v2, v1 (Linux), null and round 2's C and C++ adapters compiled
  unchanged through a shim (`server/src/shim/core/runner.hpp`, `server/src/external.hpp`).
  `--check` mode echoes route and values. The probe `GET /` is answered before any router. epoll on
  Linux (`loop.cpp`), IOCP on Windows (`loop_iocp.cpp`), shared HTTP code (`answer_all`).
  RegexMatcher comes from the pinned 2.1.0.0 archive.
- `server/go/` Go program `mserver-go` (net/http): httprouter, gin, nethttp, chi, null.
  `bench/arms/go/gin/rbserve.go` adds per-request lookup state to round 2's gin shim.
- `server/rust/` Rust program `mserver-rs` (hyper 1.12.0, tokio 1.54.1 current-thread): matchit,
  path-tree, actix-router, null.
- `t3/e2e_requests.cpp`, `t3/make_requests.py`: request sets of the 80 cells (mixed-disjoint, five
  sizes, sixteen seed pairs); `t3/requests-manifest.tsv` holds their digests (files not committed).
- `t3/check_server.py` (one arm, one cell), `t3/run_checks.py` (the suite).
- `bench/cmake/isa.cmake`: an MSVC branch (`/arch:AVX2`); the clang output is unchanged.

## Arms per system (built 2026-10-23)

| Program | Linux (container, clang 22.1.8) | Windows (MSVC 19.51) |
|---|---|---|
| mserver | v2 null crow drogon oatpp pistache r3 uwebsockets glaze cpp-httplib | v2 null crow drogon oatpp uwebsockets glaze cpp-httplib |
| mserver-go | httprouter gin nethttp chi null (cross-built, Go 1.27.0) | same (Go 1.27.0) |
| mserver-rs | waits: no Rust in the image | matchit path-tree actix-router null (cargo 1.98.1) |

Absent and why: boost-url on both (no Boost 1.92.0 headers); r3 on Windows (POSIX headers);
Pistache on Windows (its CMake gives cl GCC flags; its meson build not tried).

## Functional checks

Every arm answers every route of pair (111, 211) at all five sizes, and the T0 rings of pairs 112
to 126 at m = 1,000; at m = 100,000 the four linear-scan arms get the ring only (`run_checks.py`).
- Final suites, after every review fix (2026-10-23, binaries of commit a8c3f8b's sources):
  - Linux (container, `--cpus 2`): 300 checks, 0 failed (mserver's 10 arms, mserver-go's 5, 20
    checks each). The 80 request-set cells matched `t3/requests-manifest.tsv`.
  - Windows (desktop, MSVC build; Go and Rust from `t3/build_programs.py`): 340 checks, 0 failed
    (mserver 8, mserver-go 5, mserver-rs 4 arms).
  - Before the fixes the same suites gave the same totals, 0 failed.
- Linux check of mserver-rs: waits for a Rust toolchain in the image (Lab request 1).
- Development sanitizers, not records: ASan+UBSan and TSan (clang 22.1.8, container; TSan with
  `seccomp=unconfined`) on all ten Linux arms, and MSVC ASan on all eight Windows arms, each at
  m = 1,000 with every route and the ring: no report, clean exits; the unit tests pass under each.
  These ran before the review fixes; after them, ASan+UBSan and MSVC ASan ran the loopback test
  (below). MSan not run: no instrumented libc++ in the image.
- Loopback test (`server/tests/test_loopback.cpp`, now on both systems, after the fixes): Windows
  release 10 of 10 runs and MSVC ASan 10 of 10 (8 and 4 of 10 before the graceful close); Linux
  release 9 of 9 and ASan+UBSan 9 of 9. Linux CTest 4 of 4.
- Not exercised on the desktop: the IOCP path for a TCP provider that is not IFS (`skip_` false);
  the desktop's providers are all IFS. A partial overlapped send did not occur either (every
  WSASend completed whole), so that branch is untested.
- Kernel blind spots: none used. epoll and loopback TCP only; no io_uring, no eBPF.

## Review

A fresh Opus review of the whole diff (2026-10-23): no CRITICAL; 3 HIGH, 3 MEDIUM, 10 LOW.
Fixed:
- H1: only the external C++ arms paid a path copy. Now the server copies the path once per
  request into one reused string for every arm, v2 and null included (`route.hpp`, `http1.cpp`).
- H2: chi was hosted below its documented use. Every Go router is now its library's
  `http.Handler`: gin's Engine (real v1.12.0 module; its `tree.go` sha256 89d06fd0... equals round
  2's vendored copy), chi's Mux, httprouter's Router, net/http's ServeMux. `bench/arms/go/gin/
  rbserve.go` is gone.
- H3: Rust now builds with `-C target-cpu=native` (`server/rust/.cargo/config.toml`, checked by
  `build.rs` and a start-up line); Go's `GOAMD64=v3` is set by `t3/build_programs.py` and printed
  at start.
- M1 (IOCP accept slots re-posted every pass), M2 (Go sink atomic; a `-race` build is clean), M3
  (loopback test ported to Windows: see below).
- L1 (static check that no C++ adapter has its own 405), L2 (IOCP teardown never frees memory with
  an operation in flight), L3 (IFS check before skipping completion packets), L5 (Rust runtime
  without a time driver, comments true), L6 (C++ sink stored at teardown), L9 (exit code 3 for a
  refused table in all three programs), L10 (stale comments).
- L4 turned out real on Windows: the ported loopback test lost the 413 to a reset, because the
  server closed with unread input and a Windows client drops received data on a reset. The IOCP
  backend now closes gracefully (shutdown of the send side, then reads and drops input until the
  peer closes, at most 2 s). The epoll backend keeps round 2's close (a Linux client keeps the
  data); its spin after a peer half-close is fixed.
Documented, not changed: L7 (methods other than GET differ by library; never measured), L8 (a
child in its own process group gets Ctrl-Break only).

## Laptop requests

Each job runs on the laptop between campaigns; the coordinator schedules them.
0. **The Windows load generator and runner** (blocks every Windows window, the probe included):
   Alex chose P2's own portable generator (2026-10-23); it is engineering here, then a laptop job
   to build and A/A-check it against `t1gen` on L. No measured basis.
0b. **clang-cl 22.1.8 on W** (Alex, 2026-10-23): LLVM installed and checked by sha256, like the
   other W tools in `lab/laptop/versions.md`, plus MinGW gcc for Go's cgo. No measured basis.
1. **Request sets on L and W.** Not committed (about 10 MB per cell at m = 100,000). Either
   generate them there with `t3/make_requests.py` and `e2e_requests` (every-route set at m =
   100,000 for pair 111 only), or copy them; either way check them with `make_requests.py --verify`
   against `t3/requests-manifest.tsv`. Length: no measured basis (the desktop's time is not one).
2. **Toolchains on W and L.** Go 1.27.1 (round 2's) and the Rust toolchain on W; confirm both on
   L and add them to `lab/laptop/versions.md`. Shares P4's planned Go and Rust bring-up on W.
   Length: no measured basis.
3. **Release builds** of `mserver`, `mserver-go`, `mserver-rs` on L and W, and the functional suite
   (`t3/run_checks.py`) on each. Length: no measured basis for these builds; the desktop suite is
   not a basis (other hardware).
4. **Sanitizer records (D5)** of `mserver` with all its arms: L ASan+UBSan, TSan, MSan
   (instrumented libc++); W MSVC ASan. Go and Rust coverage gaps go in `bench/coverage.json`.
   Length: no measured basis for this arm set.
5. **Timing probe** before the freeze: every arm at m = 10 and m = 100,000, pair (111, 211), two
   windows each, on mixed-disjoint: 80 windows on L, 72 on W (before the arms Alex added; with them
   88 and 84). Basis: H6's 6.30 s per window on L and plan v2's
   6.123 s on W give 504 s and 441 s, plus server start-up at m = 100,000, which has no measured
   basis (round 2 measured the table build alone at up to 4.6 s, Drogon). lab/t1's readiness wait
   is 15 s.
6. **The campaign**, after the freeze, with Alex's answers of 2026-10-23 (two shapes; v2 in the Go
   and Rust programs; Pistache on W): L 22 arms, 44 windows per pair and size, 7,040 windows,
   44,352 s = 12.32 h; W 21 arms, 42 windows, 6,720 windows, 41,147 s = 11.43 h. Basis: H6's
   6.30 s per window on L, plan v2's 6.123 s on W. Together 23.75 h, 1.21 calendar days at 19.68
   measuring hours a day. Plus the A/A pilot and start-up (no measured basis), and H7's MSVC costs
   on W, 0.33 h by plan v2's desktop basis.

## Lab requests

1. `papers-dev`: add Go 1.27.1, the Rust toolchain matching the laptop, and the `boost` headers
   (the snapshot has `boost-libs` 1.92.0 but not the headers). Blocks the Linux checks of
   `mserver-rs` and the boost-url arm.
2. A Windows load generator and runner with lab/t1's window rules, if the coordinator chooses
   lab tooling over P2's own generator (Laptop request 0).
3. Boost 1.92.0 headers on the laptop's Windows, for boost-url there (or Alex drops it on W).
4. lab/t1's readiness wait (15 s) may be short for m = 100,000 start-ups; the probe will tell.

## Alex decides

Answered by Alex on 2026-10-23 (AskUserQuestion; the options are in
`design/round3/decisions-for-alex.md`):
1. Same-server test against Go and Rust: **v2 as an arm inside both programs** (cgo needs MinGW
   gcc on the laptop's Windows).
2. Windows load generator: **P2's own portable C++23 generator and runner**, used on both systems,
   A/A-checked against `t1gen` on Linux.
3. Windows C++ compiler: **clang-cl 22.1.8** (MSVC the fallback for an arm that fails).
4. Linear-scan cells at m = 100,000: **same windows; a router that cannot sustain the load is
   reported with its counts and leaves the tested family**, by a rule fixed in the frozen file.
5. Routing cost across servers: **a tested hypothesis** with its own Holm family.
6. Shapes: **mixed-disjoint and static, at all five sizes.**
7. H8's margin: **the larger of 1.02 and the A/A pilot's 97.5th percentile**, rule frozen before
   the pilot.
8. Pins: **the latest releases** (Crow's 1.3.5 is a pre-release, so Crow stays at its latest
   release, 1.3.4, unless Alex says otherwise; RegexMatcher stays 2.1.0.0, the measured library).
9. Boost.URL: **add the Boost 1.92.0 headers** to the image and the laptop's Windows.
10. Pistache on Windows: **bring up its meson build with libevent.**
11. Go hosting: **keep each library's documented handler.**
12. Timestamp: **push `round3` at the freeze**, before any confirmatory window.

Still open: none from Alex. Engineering these answers need, in order: P2's generator (2), clang-cl
on the desktop and the laptop (3), v2's C interface in Go and Rust (1), the re-pins (8), the static
request sets (6), Pistache's meson build on Windows (10), the Boost headers (9).

## Commits on `round3` (local, not pushed)

1862c01 723a235 354a536 dd5ae0a (round-3 docs, request sets, servers), d8b51eb a8c3f8b 4942900
(review fixes; d8b51eb also removes `bench/arms/go/gin/rbserve.go`), e8af074 cfc8d11 6829ed0
(state, decisions, Alex's answers), and the commit of this update.

Side effects outside this worktree: the relative-path repair also rewrote the `.git` link of
`D:\Dev\GitHub\paper-arms-e` (still resolves). `bench/` equals round 2's files except the MSVC
branch of `bench/cmake/isa.cmake`.
