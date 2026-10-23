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
- Linux suite: PENDING (running).
- Windows suite: PENDING (running).
- Development sanitizers (not records): ASan+UBSan in the container and MSVC ASan: PENDING.
- Kernel blind spots: none used. epoll and loopback TCP only; no io_uring, no eBPF.

## Review

Fresh Opus review of the diff: PENDING.

## Laptop requests

Each job runs on the laptop between campaigns; the coordinator schedules them.
1. **Toolchains on W and L.** Go 1.27.1 (round 2's) and the Rust toolchain on W; confirm both on
   L and add them to `lab/laptop/versions.md`. Shares P4's planned Go and Rust bring-up on W.
   Length: no measured basis.
2. **Release builds** of `mserver`, `mserver-go`, `mserver-rs` on L and W, and the functional suite
   (`t3/run_checks.py`) on each. Length: no measured basis for these builds; the desktop suite is
   not a basis (other hardware).
3. **Sanitizer records (D5)** of `mserver` with all its arms: L ASan+UBSan, TSan, MSan
   (instrumented libc++); W MSVC ASan. Go and Rust coverage gaps go in `bench/coverage.json`.
   Length: no measured basis for this arm set.
4. **Timing probe** before the freeze: every arm at m = 10 and m = 100,000, pair (111, 211), two
   windows each: 80 windows on L, 72 on W. Basis: H6's 6.30 s per window on L and plan v2's
   6.123 s on W give 504 s and 441 s, plus server start-up at m = 100,000, which has no measured
   basis (round 2 measured the table build alone at up to 4.6 s, Drogon). lab/t1's readiness wait
   is 15 s.
5. **The campaign**, after the freeze: about 5.60 h on L and 4.90 h on W, plus the A/A pilot and
   start-up (`end-to-end.md`, section 11). Plus H7's MSVC costs on W, 0.33 h by plan v2's desktop
   basis.

## Lab requests

1. `papers-dev`: add Go 1.27.1, the Rust toolchain matching the laptop, and the `boost` headers
   (the snapshot has `boost-libs` 1.92.0 but not the headers). Blocks the Linux checks of
   `mserver-rs` and the boost-url arm.
2. A Windows load generator and runner with lab/t1's window rules: `t1gen` and `t1.py` are Linux
   only (epoll, `taskset`, `/proc`). Blocks every Windows window, the probe included.
3. Boost 1.92.0 headers on the laptop's Windows, for boost-url there (or Alex drops it on W).
4. lab/t1's readiness wait (15 s) may be short for m = 100,000 start-ups; the probe will tell.

## Alex decides

1. v2 behind its C interface inside the Go and Rust programs, as a same-server control against the
   fastest Go and Rust routers (gin and matchit lead several round-2 cells)? Adds 4 windows per pair
   and size per system.
2. The Windows C++ compiler: MSVC (installed) or clang-cl 22.1.8 (to install), for the cross-OS
   contrast.
3. Linear-scan cells at m = 100,000 (actix-router about 33 lookups per second there by round 2's
   lookup time alone): measure and report counts, or report without testing below a set count.
4. Whether the routing increment across servers becomes a tested hypothesis.
5. Pins: keep round 2's (recommended, so T1 runs the code T0 timed) although newer releases exist
   (cpp-httplib six, chi two, Drogon 1.9.14 with an identical router file, Go 1.27.3).
6. Pistache on Windows through its meson build, or absent there.
7. Any push of `round3` to the public repository (nothing is pushed).

## Commits on `round3`

None yet.
