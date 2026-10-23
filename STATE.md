# P2 round 3, state digest

Under 200 lines. Read this first. Updated 2026-10-24.

## What round 3 is

The end-to-end block of P2 (brief `p2-typed-routing/AGENTS.md` in the Papers repository; plan v2
section 2.2 and the P2 row of section 3.2): v2 and each external router hosted in an HTTP server,
round 2's table sizes, both systems of the laptop. Plus the H7 MSVC compile costs on the laptop's
Windows. Round 2 is the prior study; its frozen files are never edited.

## Worktree and base

- `D:\Dev\worktrees\p2-round3`, branch `round3`, from 801aa8c: the committed gitlink and `main`.
  The manuscript branch (d38847f) adds only `paper/` changes, so round 3 stays off it.
- Worktree links are relative (`git worktree repair --relative-paths`); that also rewrote
  `D:\Dev\GitHub\paper-arms-e`'s link, which still resolves.
- Outside the repository: request sets `D:\Dev\worktrees\p2r3-data\sets\<shape>\m<m>\t<seed>\`,
  builds `D:\Dev\worktrees\p2r3-build\`, container trees in the docker volume `p2r3-home`.

## Rules

No timing on the desktop; no laptop access; nothing pushed; drafts only (no freeze); the
integration library never named; no em or en dashes.

## Documents

- `design/round3/end-to-end.md`: the design draft (contrasts, cells, replicates, request sets,
  server contract, hosting, Windows, generator and runner spec, risks, hours).
- `design/round3/decisions-for-alex.md`: the twelve decisions and Alex's answers.
- `design/round3/router-survey.md`: the router survey and my re-check of the claims used.
- `hypotheses-round3.md`: DRAFT, H8 (v2 not slower in the same server), H9 (carry-over), H10
  (routing cost across servers, as a difference in ns).

## What exists (code)

- `server/` C++ server `mserver`: v2 (RegexMatcher 2.1.0.0), v1 (Linux), null, and round 2's C and
  C++ adapters compiled unchanged through a shim; epoll on Linux, IOCP on Windows; `--check` mode;
  the probe `GET /` answered before any router; one path copy per request for every arm;
  `--router ??` lists each arm's release. Round-3 pins in `server/cmake/pins-round3.cmake`
  (overrides round 2's `bench/cmake/pins.cmake`, which is untouched).
- `server/capi/`: v2 behind a C interface (`p2v2_build`, `p2v2_find`, `p2v2_build_info`), built in
  the C++ server's CMake tree.
- `server/go/` `mserver-go` (net/http; each router as its library's handler): v2 (cgo on Linux, a
  DLL call on Windows), httprouter, gin (real v1.12.0), nethttp, chi (real v5.5.0), null.
- `server/rust/` `mserver-rs` (hyper 1.12.0 on tokio current-thread): v2 (C call), matchit,
  path-tree, actix-router, null.
- `t3/`: `e2e_requests.cpp` and `make_requests.py` (160 cells: two shapes, five sizes, sixteen
  pairs; digests in `requests-manifest.tsv`), `check_server.py`, `run_checks.py`,
  `build_programs.py` (one Go and one Rust binary per system against a named C++ build, sha256s in
  `build-info.json`), `gen/` (`p2gen`, the load generator), `p2run.py` (the window runner).
- `bench/cmake/isa.cmake`: MSVC (`/arch:AVX2`) and clang-cl (`-march=native`) branches.

## Pins (Alex, 2026-10-23: the latest releases)

cpp-httplib v0.63.0, chi v5.5.0, Drogon 1.9.14 (label only, same router file), Crow 1.3.5 (a
pre-release), Go 1.27.3 (to install); the rest already latest. Each changed router's lookup code was
compared with round 2's pin and found the same (`pins-round3.cmake`, `router-survey.md`).

## Arms per system

| Program | Linux (container, clang 22.1.8) | Windows (desktop, clang-cl 22.1.0 and MSVC) |
|---|---|---|
| mserver | v2 null crow drogon oatpp pistache boost-url r3 uwebsockets glaze cpp-httplib | v2 null crow drogon oatpp uwebsockets glaze cpp-httplib |
| mserver-go | v2 httprouter gin nethttp chi null | same |
| mserver-rs | v2 matchit path-tree actix-router null | same |

Windows gaps: r3 (POSIX headers; absent by design); Pistache (Alex chose its meson build with
libevent; not yet built, needs meson and libevent); boost-url (needs Boost 1.92.0 headers there).

## Functional checks (desktop, untimed)

Every arm: every route of pair (111, 211) at all five sizes, and the T0 rings of pairs 112 to 126 at
m = 1,000, on both shapes; at m = 100,000 the linear-scan arms get the ring only. Final suites,
2026-10-23, all three programs in one run, Go and Rust built by `t3/build_programs.py` only:
- Linux (container): 880 of 880 (22 arms). mserver sha256 9ea7cd75..., mserver-go dc405e3a...,
  mserver-rs 586dfe70...; the v2 library both link, 988f2c45..., matches `build-info.json`.
- Windows (desktop, clang-cl 22.1.0): 760 of 760 (19 arms). mserver fd0e5c73..., mserver-go
  74fba04d..., mserver-rs 1a86633f...; p2v2.dll a66a8780..., as recorded.
- CTest on Linux: 6 of 6 (unit, loopback, H6 agreement, contract, p2gen unit and edge); loopback
  test on Windows 10 of 10 (release and MSVC ASan).
- p2gen: unit, net and edge tests in every tree; count mode against all three programs completed
  every request with no error. p2run: 73 unit tests; count mode 36 of 36 windows on each system.
- Development sanitizers (not records): ASan+UBSan and TSan on Linux, MSVC ASan on Windows, clean.
- Not run on the desktop, by rule: any timed mode. Kernel features used: epoll, IOCP, loopback TCP.

## Reviews

1. Whole first diff (Opus): 0 CRITICAL, 3 HIGH, 3 MEDIUM, 10 LOW; all HIGH and MEDIUM fixed; one LOW
   (reset on close) proved a real Windows bug and was fixed.
2. Generator and v2 arms (Opus): 0 CRITICAL, 1 HIGH (nothing tied the Go and Rust v2 arms to the C++
   build; fixed by `build_programs.py`, `p2v2_build_info` and the start lines), 3 MEDIUM (fixed),
   8 LOW (fixed or documented).
3. The runner was reviewed by a fresh agent inside its own task, which adopted the findings.

## To settle in the frozen text (with the freeze proposal and its hours)

- delta for H8 from the A/A pilot; the minimum D_T0 for H9; H10's margin in ns.
- The runner's validity additions beyond lab/t1 (connect errors, server alive and exit 0, sample
  span within 50 ms of the window, a missing generator key, the stop after 8 consecutive faults)
  and its reconnect rule (reconnects allowed only as far as timeouts, connect errors and lost
  requests explain them; `peer_closes` above 0 invalidates a window).
- The overload edges: zero completions with timeouts is invalid; connect errors during overload make
  the window invalid.

## Laptop requests

Each runs on the laptop between campaigns; the coordinator schedules them.
0. P2's generator and runner: Release builds, D5 records (L ASan+UBSan, TSan, MSan; W clang-cl
   ASan), and the A/A check of `p2gen` against `t1gen` on L in the pilot. No measured basis.
1. Toolchains. W: done 2026-10-24, 01:06 to 01:19, four jobs, each exit 0 (Papers
   `lab/laptop/queues/gap2-w-q2-p2-toolchains.json` at a27b47e; its `gap2-w-p2-toolchains.ps1` holds
   every pin: file, bytes, sha256). Under `C:\Users\alext\opt`: go-1.27.3, meson-1.12.1 (run as
   `python meson.py`, not installed), libevent-2.1.13-stable (source only, not yet built),
   rapidjson-1.1.0 (Pistache's wrap files, packed), boost-1.92.0 (headers in `boost\`), llvm-22.1.8
   (`bin\clang-cl.exe`, clang 22.1.8, LLD 22.1.8); Rust 1.99.0 is P4's (RUSTUP_HOME and CARGO_HOME
   `C:\Users\alext\opt\rustup` and `cargo`). Read from the check job's versions.txt in
   `C:\Users\alext\lab\laptop-archive\gap2-w-q2-p2-toolchains-1384391a\`. meson 1.12.1 and libevent
   2.1.13-stable were pinned on 2026-10-24 (latest stable; both publish only a GPG signature, so the
   sha256s are GitHub's asset digests, meson's equal to PyPI's). L: Go 1.27.3 and Rust 1.99.0 under
   `~/opt` come with the Arch visit (`gap1-a-p2-toolchains.sh`). Open: pkgconf, until Pistache's
   first Windows build.
2. Request sets on L and W, generated there or copied, checked with `make_requests.py --verify`.
   No measured basis.
3. Release builds of the three programs (`build_programs.py --cxx-build ...`) and the functional
   suite on L and W. No measured basis.
4. D5 records of `mserver` with all arms (L ASan+UBSan, TSan, MSan; W clang-cl ASan); Go `-race`
   and Rust gaps in `bench/coverage.json`. No measured basis for this arm set.
5. Timing probe before the freeze: every arm at m = 10 and 100,000, pair 111, both shapes, 2
   windows each: 176 windows on L (1,109 s at H6's 6.30 s per window), 168 on W (1,029 s at plan
   v2's 6.123 s), plus start-up at m = 100,000, no measured basis (round 2's table builds alone
   reach 4.6 s).
6. The campaign after the freeze: L 22 arms x 2 windows x 160 pairs and sizes = 7,040 windows,
   44,352 s = 12.32 h; W 21 arms, 6,720 windows, 41,147 s = 11.43 h. Together 23.75 h, 1.21
   calendar days at 19.68 measuring hours a day. Plus the A/A pilot and start-up (no measured
   basis), and H7's MSVC costs on W, 0.33 h (plan v2's desktop basis).

## Lab requests

1. Done 2026-10-23 (image 7f39a629ada0): Rust 1.98.1, Go 1.27.1, Boost 1.92.0. Wanted in the
   image, side by side, so the desktop's Linux checks use the laptop's versions: Go 1.27.3 and
   Rust 1.99.0 (Alex, 2026-10-23). Until then those checks are development checks of other patch
   releases.
2. LLVM 22.1.8 (clang-cl) on the desktop, which has 22.1.0, plus meson, libevent and Boost 1.92.0
   headers for the desktop's Windows checks of Pistache and boost-url.

## Alex decides

Answered on 2026-10-23 (AskUserQuestion; details in `design/round3/decisions-for-alex.md`):
1. v2 inside the Go and Rust programs. 2. P2's own generator and runner. 3. clang-cl on Windows.
4. Overloaded linear-scan routers reported, out of the tested family. 5. The cross-server routing
cost tested (H10). 6. Mixed-disjoint and static, five sizes each. 7. H8's margin from the A/A
pilot. 8. The latest releases; then Crow's 1.3.5 pre-release and Go 1.27.3. 9. Boost headers added.
10. Pistache's meson build on Windows. 11. Go routers as their libraries' handlers. 12. Push
`round3` at the freeze.

Laptop queue plan, answered by Alex on 2026-10-23 (Papers `lab/laptop/queue-plan-2026-10-draft.md`,
section 10), as it touches P2: the toolchain gap block is approved (Laptop request 1); D1 no pacman
upgrade or install on L until P4's Arch blocks end, extra versions side by side under `~/opt`; D2
Go side by side, P2 keeps 1.27.3 while P4, P7 and P5 use 1.27.2, and P2 takes Rust 1.99.0, the
version P4 installs (not the image's 1.98.1); D4 P4's idle day carries read-only jobs only.

Open with Alex: none. The frozen-text items above go to him with the freeze proposal and its hours.

## Commits on `round3` (local, not pushed)

1862c01 723a235 354a536 dd5ae0a (first servers), d8b51eb a8c3f8b 4942900 (first review), e8af074
cfc8d11 6829ed0 b69bde7 9596d62 f40d81a (state, decisions, answers, spec), 9444920 7fc0fed 1ecdeb0
69557f8 (pins, v2 arms, generator, Crow), 9d7366b 7459902 508f54d (second review), 62ed742
(runner), 2e93c25 8c95d9d 06adfe5 (final suites), a27b47e (meson and libevent pins), and the
commit of this update. `bench/` equals round 2's files except `isa.cmake`.

## Next engineering

Pistache's meson build on Windows and boost-url there (after the tools arrive); the laptop's
bring-up (requests 0 to 4); the timing probe; then the freeze proposal with its hours.
