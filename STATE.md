# P2 round 3, state digest

Under 200 lines. Read this first. Updated 2026-10-24, late.

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

No timing on the desktop; no laptop access; nothing pushed; drafts only; no em or en dashes.

## Documents

- `design/round3/end-to-end.md`: the design draft (contrasts, cells, replicates, request sets,
  server contract, hosting, Windows, generator and runner spec, risks, hours).
- `design/round3/decisions-for-alex.md`: the thirteen decisions and Alex's answers.
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
- D5 and the laptop jobs (`design/round3/end-to-end.md`, section 8), one Python code path for both
  systems: `t3/labsteps.py` (toolchains, configure, inputs, logs), `t3/sanitize.py` (one record:
  build, CTest, inputs, programs, request-set cells, suite, count-mode load; name
  `p2r3-<code>-<L|W>-<san>`; `--desktop` reads no time and names it `-desktop`), `t3/record.py`,
  `t3/coverage.json` (round 3's gaps; round 2's `bench/coverage.json` untouched),
  `t3/check_records.py` (the gate), `t3/source_hash.py` (Go and Rust inputs),
  `t3/jobs/bringup.py`, `t3/jobs/records.py`, `t3/test_records.py`; `server/tests/test_p2v2.cpp`
  (v2's C interface, static and DLL); `server/cmake/boost-headers/` (Boost on Windows,
  `P2_BOOST_ROOT`); `server/cmake/pistache-windows.cmake` (`P2_MESON`, `P2_LIBEVENT_SRC`,
  `P2_RAPIDJSON_WRAP`); clang-cl ASan links the driver's runtime (root `CMakeLists.txt`).

## Pins (Alex, 2026-10-23: the latest releases)

cpp-httplib v0.63.0, chi v5.5.0, Drogon 1.9.14 (label only, same router file), Crow 1.3.5 (a
pre-release), Go 1.27.3 (to install); the rest already latest. Each changed router's lookup code was
compared with round 2's pin and found the same (`pins-round3.cmake`, `router-survey.md`).

## Arms per system

| Program | Linux (container, clang 22.1.8) | Windows (desktop, clang-cl 22.1.8) |
|---|---|---|
| mserver | v2 null crow drogon oatpp pistache boost-url r3 uwebsockets glaze cpp-httplib | the same but r3 |
| mserver-go | v2 httprouter gin nethttp chi null | same |
| mserver-rs | v2 matchit path-tree actix-router null | same |

Windows: r3 absent (POSIX headers). Pistache through `server/cmake/pistache-windows.cmake`: libevent
with its CMake, Pistache's meson build of its static library, the logging installer's line removed
from the fetched `src/meson.build` (Alex, 2026-10-24); nothing installed (checked: no Program Files
folder, no HKCU key); 40 of 40 checks. boost-url through `server/cmake/boost-headers/`: 40 of 40.
Round 2's adapters and every file compiled on Linux are unchanged by both.

## Functional checks (desktop, untimed)

Every arm: every route of pair (111, 211) at all five sizes, and the T0 rings of pairs 112 to 126 at
m = 1,000, on both shapes; at m = 100,000 the linear-scan arms get the ring only. Latest passes
(2026-10-24, the laptop's tool versions; `t3/jobs/bringup.py` and `records.py` as the laptop runs
them, Laptop requests 0 to 4): Linux 880 of 880 (22 arms), Windows 840 of 840 (21 arms, Pistache and
boost-url included); CTest 8 of 8 on Linux, 7 of 7 on Windows; count mode 176 of 176 and 168 of 168
windows. Not run on the desktop, by rule: any timed mode. Kernel features used: epoll, IOCP, TCP.

## Reviews

1. First diff (Opus): 0 CRITICAL, 3 HIGH, 3 MEDIUM, 10 LOW; HIGH and MEDIUM fixed, one LOW too.
2. Generator and v2 arms (Opus): 0 CRITICAL, 1 HIGH (Go and Rust tied to the C++ v2 build), 3 MEDIUM;
   all fixed. 3. The runner: reviewed by a fresh agent in its own task.
4. D5 tooling and the laptop jobs (Opus, 2026-10-24): 0 CRITICAL, 2 HIGH, 3 MEDIUM, 4 LOW. Fixed:
   bare commands resolved on the job's PATH (Windows); records only on the laptop's host and CPU,
   checked again by the gate; Go and Rust toolchains and found tool trees compared; no green record
   without kept logs; the system's arms required; the arm list logged; no inherited sanitizer
   options; p2v2.h in the Go hash; Go caches under P2R3; the /tmp check. Kept: crates in P4's shared
   CARGO_HOME (Alex's D2); RapidJSON by git tag on Linux, as round 2 (listed in each record).
   The development passes then found: Rust's two leaked boxes (now freed after the runtime) and
   actix-router's deliberate leak (round 2's suppression, ASan builds only); Rust ASan on Windows
   linked Visual Studio's runtime (LLVM's now first on LIB); libevent's and meson's checks under ASan.

## To settle in the frozen text (with the freeze proposal and its hours)

- delta for H8 from the A/A pilot; the minimum D_T0 for H9; H10's margin in ns.
- The runner's validity additions beyond lab/t1 (connect errors, server alive and exit 0, sample
  span within 50 ms of the window, a missing generator key, the stop after 8 consecutive faults)
  and its reconnect rule (reconnects allowed only as far as timeouts, connect errors and lost
  requests explain them; `peer_closes` above 0 invalidates a window).
- The overload edges: zero completions with timeouts is invalid; connect errors during overload make
  the window invalid.

## Laptop requests

The coordinator schedules them. The next request is rows 0, 2, 3 and 4: four jobs drafted in the lab
queue's format, with commands, outputs, times and `plain` sentences, in `t3/jobs/requests-2026-10-24.json`,
at commit 3ff814e50. Untimed, none quiet-checked; on each system the bring-up comes before the records.
0, 2, 3. Bring-up, `t3/jobs/bringup.py OUT` (p2r3-bringup-l, p2r3-bringup-w): the toolchains checked
   (clang or clang-cl 22.1.8, Go 1.27.3, Rust 1.99.0), the Release build with every arm of the system,
   CTest, the inputs hash, the Go and Rust programs, the request sets made there and checked (all 160
   cells), the functional suite, the runner's and record tools' tests, a count-mode pass of p2run.
   Expected 1 h each, timeout 4 h. Row 0's A/A check of p2gen against t1gen stays in the pilot.
4. Records after each bring-up, `t3/jobs/records.py OUT` (p2r3-records-l, p2r3-records-w):
   `t3/sanitize.py` under L ASan+UBSan, TSan and MSan and W clang-cl ASan; gaps in `t3/coverage.json`.
   L expected 3 h, timeout 8 h (lower bound: round 2's three rbench records on L took 1,581, 2,258 and
   2,822 s; round 3 adds the suite under each sanitizer); W 1.5 h, timeout 6 h; no measured basis.
   W: DONE on the laptop, 2026-10-25, at 3ff814e (as the coordinator reported; the archives in
   `laptop-archive\gap9-w-q2-p2-a18f07bb\`, sha256 3ac9251f... and 3066863e..., checked by me):
   p2r3-bringup-w 02:11:46 to 03:11:48 EEST, exit 0, every step green (840 checks, 168 of 168
   windows); p2r3-records-w 03:11:54 EEST to 03:41:56 EET, exit 0, record p2r3-3ff814e50-W-asan
   green, 0 reports, host DESKTOP-A1RHS5R, filed in Papers `lab/sanitizer-records/laptop-w/` (7e0e6a0).
   W gate (`t3/check_records.py --host-tag W --records <Papers>/lab/sanitizer-records/laptop-w`) on
   that bring-up's build: green, 21 targets, mserver-go's declared gap. L: running in Arch visit A2.
   Desktop development passes at 3ff814e were green (L ASan 880 checks, L TSan 680 in a container
   with seccomp unconfined). MSan has run nowhere yet; it is the last step of p2r3-records-l, so a
   failure there keeps the ASan and TSan records, and a fix and a rerun may follow.
1. Toolchains: done on both systems, 2026-10-24. W, four jobs exit 0, 01:06 to 01:19 (Papers
   `lab/laptop/queues/gap2-w-q2-p2-toolchains.json` at a27b47e, its `.ps1` holding every pin): under
   `C:\Users\alext\opt` go-1.27.3, meson-1.12.1, libevent-2.1.13-stable, rapidjson-1.1.0 (the wrap
   files), boost-1.92.0, llvm-22.1.8; Rust 1.99.0 is P4's. L, job `a1-p2-toolchains-l` exit 0, ending
   03:24:57: `~/opt/p2/go1.27.3` and Rust 1.99.0 in `~/opt/rustup` and `~/opt/cargo`, no pacman
   change. meson 1.12.1 and libevent 2.1.13-stable were pinned on 2026-10-24 (latest stable; both
   publish only a GPG signature, so the sha256s are GitHub's asset digests). No pkgconf needed.
5. Timing probe before the freeze: every arm at m = 10 and 100,000, pair 111, both shapes, 2 windows
   each: 176 windows on L (1,109 s at H6's 6.30 s per window), 168 on W (1,029 s at plan v2's
   6.123 s), plus start-up at m = 100,000, no measured basis (round 2's table builds reach 4.6 s).
6. The campaign after the freeze: L 22 arms x 2 windows x 160 pairs and sizes = 7,040 windows,
   44,352 s = 12.32 h; W 21 arms, 6,720 windows, 41,147 s = 11.43 h. Together 23.75 h, 1.21 calendar
   days at 19.68 measuring hours a day. Plus the A/A pilot and start-up (no measured basis), and H7's
   MSVC costs on W, 0.33 h (plan v2's desktop basis).

## Lab requests

1. Done 2026-10-23 (image 7f39a629ada0: Rust 1.98.1, Go 1.27.1, Boost 1.92.0). Wanted: Go 1.27.3 and
   Rust 1.99.0 side by side in the image (Alex, 2026-10-23); until then the container runs others.
2. Done 2026-10-24 by me with the coordinator's yes: the lab's checked archives copied out of
   `C:\Users\alext\lab\dl-gap1-p2-2026-10-24` and `dl-gap2-p2-2026-10-24` (read only), each sha256
   checked against its MANIFEST.json, unpacked into `D:\Dev\worktrees\p2r3-build\tools\` by the
   laptop script's methods, each tree equal to the laptop's (files and bytes): go-1.27.3 (f26081f4...),
   meson-1.12.1 (ab0a6ca0...), libevent-2.1.13-stable (f7e9383b...), boost-1.92.0 (69370b3e...),
   llvm-22.1.8 (d96c2cc1...), rapidjson-1.1.0 with its two wrap files packed (bf7ced29..., c1480d0e...).
   Full digests in `tools\UNPACKED.txt`. Side effect, undone: a desktop run made rustup install a
   1.98.1 toolchain (02:10); removed, and the jobs set RUSTUP_AUTO_INSTALL=0.
3. After the laptop's records: copy them into `lab/sanitizer-records`; add `t3/record.py` to
   `lab/bin/test_report_pattern.sh`'s list of record writers.

## Alex decides

Answered on 2026-10-23 (AskUserQuestion; details in `design/round3/decisions-for-alex.md`):
1. v2 inside the Go and Rust programs. 2. P2's own generator and runner. 3. clang-cl on Windows.
4. Overloaded linear-scan routers reported, out of the tested family. 5. The cross-server routing
cost tested (H10). 6. Mixed-disjoint and static, five sizes each. 7. H8's margin from the A/A
pilot. 8. The latest releases; then Crow's 1.3.5 pre-release and Go 1.27.3. 9. Boost headers added.
10. Pistache's meson build on Windows. 11. Go routers as their libraries' handlers. 12. Push
`round3` at the freeze. 13. (2026-10-24) Pistache's meson build with its logging installer patched
out of the fetched copy (it would copy a DLL into Program Files, install an event-log manifest and
write HKCU keys).

Queue plan (Alex, 2026-10-23, Papers `lab/laptop/queue-plan-2026-10-draft.md` section 10): the gap
block approved; D1 no pacman change on L until P4's Arch blocks end, versions side by side under
`~/opt`; D2 P2 keeps Go 1.27.3 and takes P4's Rust 1.99.0; D4 P4's idle day: read-only jobs only.

Open with Alex: none. The frozen-text items above go to him with the freeze proposal and its hours.

## Commits on `round3` (local, not pushed)

1862c01 to 06adfe5 (servers, reviews 1 to 3, decisions, pins, v2 arms, generator, runner, final
suites); a27b47e f9fc513 083b47c (Laptop request 1); 40e08db to 3ff814e (D5 tooling, laptop jobs,
Windows Pistache and boost-url, review 4); and the commit of this update. `bench/` equals round 2's
files except `isa.cmake`.

## Next engineering

The laptop's bring-up and records (the request above); the timing probe; then the freeze proposal
with its hours and the frozen-text items above.
