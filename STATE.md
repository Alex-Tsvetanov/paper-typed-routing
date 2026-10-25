# P2 round 3, state digest

Under 200 lines. Read this first. Updated 2026-10-25.

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
  `build-info.json`), `gen/` (`p2gen`, the load generator), `p2run.py` (the window runner),
  `jobs/probe.py` and `plans/probe-*.json` (the timing probe, `test_probe.py`).
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
4. D5 tooling and the laptop jobs (Opus, 2026-10-24): 0 CRITICAL, 2 HIGH, 3 MEDIUM, 4 LOW. Fixed: bare
   commands resolved on the job's PATH (Windows); records only on the laptop's host and CPU, checked again
   by the gate; toolchains and found trees compared; no green record without kept logs; the system's arms
   required and logged; no inherited sanitizer options; p2v2.h in the Go hash; Go caches under P2R3; the
   /tmp check. Kept: crates in P4's CARGO_HOME (D2); RapidJSON by git tag on Linux (in each record). Then
   development found Rust's two leaked boxes (freed after the runtime), actix-router's deliberate leak
   (suppressed, ASan only), Rust ASan on Windows on Visual Studio's runtime (LLVM's now first on LIB).
5. Timed path and probe (Sonnet, 2026-10-25): 1 HIGH (a failed `others` record made a driver fault), 1 MEDIUM
   (a vacuous post-run binary check), 5 LOW; all but 1 LOW fixed. 6. The Windows clock (Sonnet): 5 LOW, 4 fixed.

## To settle in the frozen text (with the freeze proposal and its hours)

- delta for H8 from the A/A pilot; the minimum D_T0 for H9; H10's margin in ns.
- The runner's validity additions beyond lab/t1 (connect errors, server alive and exit 0, sample
  span within 50 ms of the window, a missing generator key, the stop after 8 consecutive faults)
  and its reconnect rule (reconnects allowed only as far as timeouts, connect errors and lost
  requests explain them; `peer_closes` above 0 invalidates a window).
- The overload edges: zero completions with timeouts is invalid; connect errors during overload make
  the window invalid.
- Whether, and above what share, other processes' CPU (`others`) makes a window invalid; boost off;
  each system's clock reference (Arch's idle CPUs read 3,201 MHz, busy ones about 3,168: a 1% bias).

## Laptop requests

The coordinator schedules them. Jobs drafted in the lab queue's format with `plain` sentences:
`t3/jobs/requests-2026-10-24.json` (rows 0, 2 to 4, at 3ff814e50), `requests-2026-10-25.json` (row 5).
0, 2, 3. Bring-up, `t3/jobs/bringup.py OUT` (p2r3-bringup-l, -w): toolchains checked, the Release build
   with every arm, CTest, the inputs hash, the Go and Rust programs, the request sets (all 160 cells
   checked), the suite, the runner's and record tools' tests, a count-mode pass of p2run. Row 0's A/A
   check of p2gen against t1gen stays in the pilot.
4. Records, `t3/jobs/records.py OUT` (p2r3-records-l, -w): L ASan+UBSan, TSan and MSan, W clang-cl ASan.
   Rows 0, 2 to 4 DONE, 2026-10-25, at 3ff814e, every job exit 0 (archives `laptop-archive\gap9-w-q2-p2-a18f07bb\`
   and `gap9-a-q1-5b0f7b2a\`, sha256 checked). W: bring-up 02:11:46 to 03:11:48 EEST (840 checks, 168 of 168
   windows); records to 03:41:56 EET: p2r3-3ff814e50-W-asan green, 0 reports, 5,270 s, filed in Papers
   `lab/sanitizer-records/laptop-w/` (7e0e6a0). L: bring-up 09:48:38 to 10:48:39 EET (880 checks, 176 of 176);
   records to 13:48:43: -L-asan, -L-tsan, -L-msan green, 0 reports (MSan's first run), 1,615, 1,711 and 2,582
   s, in `lab/sanitizer-records/` (7fd305b). Gates (`t3/check_records.py --host-tag W --records
   <Papers>/lab/sanitizer-records/laptop-w`; L with `lab/sanitizer-records`): green, W 21 targets
   (mserver-go's gap), L 23 (Go's MSan, Rust's TSan and MSan gaps).
1. Toolchains: done on both systems, 2026-10-24. W (Papers `lab/laptop/queues/gap2-w-q2-p2-toolchains.json`,
   a27b47e): under `C:\Users\alext\opt` go-1.27.3, meson-1.12.1, libevent-2.1.13-stable, rapidjson-1.1.0 wraps,
   boost-1.92.0, llvm-22.1.8, P4's Rust 1.99.0. L (`a1-p2-toolchains-l`): `~/opt/p2/go1.27.3`, Rust 1.99.0 in
   `~/opt/rustup` and `~/opt/cargo`, no pacman change. meson's and libevent's pins are GitHub's asset digests.
5. Timing probe before the freeze (`t3/jobs/probe.py PLAN OUT`, quiet, boost off; `t3/plans/probe-L.json`,
   `probe-W.json`): one mirrored round of every arm at m = 10 and 100,000, both shapes, pair (111, 211), 176
   windows on L and 168 on W, timing the bring-ups' binaries (refused unless their sha256s and the compiled
   sources equal 3ff814e's). Pre-freeze: never analysed for H8 to H10, never cited. Approved by Alex
   (2026-10-25, via the coordinator), chain A3, at 25fbd22. Archives' sha256 checked; binary checks empty.
   W, p2r3-probe-w (gap14-w-q1), 14:55:38 to 15:25:40 EET: exit 3 after 8 windows, each "clock_drift" 67.8%:
   the windows read 3,175 MHz, labrec's boost-off clock; the reference 1,892, four 0.5 s PDH samples in
   which 5 or 6 of 13 idle CPUs read 0. Fixed in f5bf53e (one 10 s interval, zeros left out, `cpus_counted`),
   reviewed (nothing above LOW, fixed in 39bf126). L, p2r3-probe-l (gap14-a-q1), 15:26:33 to 15:56:35 EET:
   exit 0, quiet passed, 176 windows: 172 valid, 4 overloaded (Drogon and actix-router at m = 100,000,
   mixed-disjoint, only the error share); reference 3,197.8 MHz, drift at most 0.96%; `others` in every
   window, at most 1.99% of one CPU; start-up at m = 100,000 at most 5.0 s (Drogon); spacing 6.05 s at
   m = 10, 6.56 s at 100,000. NEXT: p2r3-probe-w-2 at 39bf126 (`t3/jobs/requests-2026-10-25-w2.json`), about
   20 min (Windows' 6.29 s spacing, plus 0.52 s at m = 100,000 as on L, 18 s start, the 10 s clock), timeout
   10,800 s; slots today to 01:30 or Monday 2026-10-26 after 19:15.
6. The campaign after the freeze: L 7,040 windows (22 arms x 2 x 160 pairs and sizes), 12.02 h at the L probe's
   spacing; W 6,720 windows, 11.43 h at plan v2's 6.123 s until its probe; together 23.45 h, 1.19 calendar days
   at 19.68 measuring hours a day, plus the A/A pilot and H7's MSVC costs on W (0.33 h, plan v2).

## Lab requests

1. Done 2026-10-23 (image 7f39a629ada0: Rust 1.98.1, Go 1.27.1, Boost 1.92.0). Wanted: Go 1.27.3 and
   Rust 1.99.0 side by side in the image (Alex, 2026-10-23); until then the container runs others.
2. Done 2026-10-24 by me with the coordinator's yes: the archives of `C:\Users\alext\lab\dl-gap1-p2-2026-10-24`
   and `dl-gap2-p2-2026-10-24` (read only) copied out, each sha256 checked against its MANIFEST.json,
   unpacked by the laptop script's methods into `D:\Dev\worktrees\p2r3-build\tools\`, each tree equal to
   the laptop's: go-1.27.3 f26081f4, meson-1.12.1 ab0a6ca0, libevent-2.1.13-stable f7e9383b, boost-1.92.0
   69370b3e, llvm-22.1.8 d96c2cc1, rapidjson-1.1.0 bf7ced29 with its wraps c1480d0e (full: `tools\UNPACKED.txt`).
   A desktop rustup install of 1.98.1 (02:10) was removed; the jobs set RUSTUP_AUTO_INSTALL=0.
3. Done 2026-10-25 by the coordinator: the records filed (7fd305b, 7e0e6a0); `lab/bin/test_report_pattern.sh`
   lists `t3/record.py` (skipped in the Papers checkout, which lacks round 3; this file's pattern checked).

## Alex decides

Answered on 2026-10-23 (AskUserQuestion; details in `design/round3/decisions-for-alex.md`):
1. v2 inside the Go and Rust programs. 2. P2's own generator and runner. 3. clang-cl on Windows.
4. Overloaded linear-scan routers reported, out of the tested family. 5. The cross-server routing
cost tested (H10). 6. Mixed-disjoint and static, five sizes each. 7. H8's margin from the A/A
pilot. 8. The latest releases; then Crow's 1.3.5 pre-release and Go 1.27.3. 9. Boost headers added.
10. Pistache's meson build on Windows. 11. Go routers as their libraries' handlers. 12. Push
`round3` at the freeze. 13. (2026-10-24) Pistache's logging installer patched out of the fetched
meson build (it would write into Program Files, the event log and HKCU).

Queue plan (Alex, 2026-10-23, Papers `lab/laptop/queue-plan-2026-10-draft.md` section 10): gap block
approved; D1 no pacman change on L until P4's Arch blocks end, versions side by side under `~/opt`;
D2 P2 keeps Go 1.27.3 and takes P4's Rust 1.99.0; D4 P4's idle day: read-only jobs only.

Open with Alex: none. The frozen-text items above go to him with the freeze proposal and its hours.

## Commits on `round3` (local, not pushed)

1862c01 to 06adfe5 (servers, reviews 1 to 3, decisions, pins, v2 arms, generator, runner, final
suites); a27b47e f9fc513 083b47c (Laptop request 1); 40e08db to 3ff814e (D5 tooling, laptop jobs,
Windows Pistache and boost-url, review 4); c7153b3 to 25fbd22 (the probe, `others`, review 5); f5bf53e
39bf126 (the Windows clock, review 6); and the commits of these updates. `bench/` equals round 2's files except `isa.cmake`.

## Next engineering

The Windows probe rerun (Laptop request 5); W's row 6 hours from it; the freeze proposal and its hours.
