# P2 round 3, state digest (under 200 lines; read this first; updated 2026-10-27)

## What round 3 is

The end-to-end block of P2 (brief `p2-typed-routing/AGENTS.md` in the Papers repository; plan v2
section 2.2 and the P2 row of section 3.2): v2 and each external router hosted in an HTTP server,
round 2's table sizes, both systems of the laptop. Plus the H7 MSVC compile costs on the laptop's
Windows. Round 2 is the prior study; its frozen files are never edited.

## Worktree and base

- `D:\Dev\worktrees\p2-round3`, branch `round3`, from 801aa8c: the committed gitlink and `main`.
  The manuscript branch (d38847f) adds only `paper/` changes, so round 3 stays off it.
- Worktree links are relative (`git worktree repair --relative-paths`; paper-arms-e's link still resolves).
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
  `build-info.json`), `gen/` (`p2gen`, the load generator), `p2run.py` (the window runner); laptop
  jobs `jobs/probe.py`, `pilot.py`, `gencheck.py` with `plans/*.json`; `pilot_analysis.py`, `gencheck_analysis.py`.
- `bench/cmake/isa.cmake`: MSVC (`/arch:AVX2`) and clang-cl (`-march=native`) branches.
- D5 (`end-to-end.md`, section 8), one Python code path for both systems: `t3/labsteps.py`, `t3/sanitize.py`
  (one record `p2r3-<code>-<L|W>-<san>`: build, CTest, inputs, programs, request-set cells, suite, count-mode
  load), `t3/record.py`, `t3/coverage.json` (round 3's gaps), `t3/check_records.py` (the gate),
  `t3/source_hash.py` (Go and Rust inputs), `t3/jobs/bringup.py`, `records.py`; `server/tests/test_p2v2.cpp`
  (v2's C interface, static and DLL); `server/cmake/boost-headers/` and `pistache-windows.cmake` (Windows);
  clang-cl ASan links the driver's runtime (root `CMakeLists.txt`).

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
Round-robin count checks (2026-10-28, ed3b7e0, 500 requests a window, desktop builds of the bring-up's compiled
sources): W A/A 84 of 84, campaign 280 of 294; L (container) 84 of 84, 292 of 308; every settle quiet; the rest
are p2gen timeouts of arms the probes found overloaded at m = 100,000 (W Oat++, actix-router; L Drogon,
actix-router, Oat++). All servers' peak memory at m = 100,000: W 3.75 GiB, L 4.04 GiB (actix-router 1.95, 2.13).

## Reviews

1. First diff (Opus): 3 HIGH, 3 MEDIUM, 10 LOW; HIGH, MEDIUM, one LOW fixed. 2. Generator and v2 arms (Opus):
   1 HIGH (Go and Rust tied to the C++ v2 build), 3 MEDIUM; fixed. 3. The runner: a fresh agent in its own task.
4. D5 tooling and the laptop jobs (Opus, 2026-10-24): 0 CRITICAL, 2 HIGH, 3 MEDIUM, 4 LOW. Fixed: bare commands
   on the job's PATH; records only on the laptop's host and CPU; toolchains and found trees compared; no green
   record without kept logs; arms required and logged; no inherited sanitizer options; p2v2.h in the Go hash
   (then Rust's leaked boxes freed, actix-router's leak suppressed for ASan).
5. Timed path and probe (Sonnet, 2026-10-25): 1 HIGH (a failed `others` record made a driver fault), 1 MEDIUM
   (a vacuous post-run binary check), 5 LOW; all but 1 LOW fixed. 6. The Windows clock (Sonnet): 5 LOW, 4 fixed.
7. The A/A pilot (Sonnet, 2026-10-26): 2 HIGH (the analysis took incomplete or doubled files), 3 MEDIUM, 6 LOW; fixed.
9. The rerun (Sonnet, 2026-10-27): no HIGH, 3 MEDIUM (streak across phases, rerun bookkeeping, an arm's second draw), 4 LOW; fixed.
10. Round-robin (Opus, 2026-10-28): no HIGH, 1 MEDIUM (a server mid-start missed by the stop), 3 LOW; 3 fixed, 1 by design.

## Method the paper must state (the new loop has no frozen text)

- The runner's validity additions beyond lab/t1 (connect errors, server alive and exit 0, sample span within
  50 ms of the window, a missing generator key, the stop after 8 consecutive faults), its reconnect rule
  (reconnects only as far as timeouts, connect errors and lost requests explain them; `peer_closes` above 0
  invalidates), and the overload edges (zero completions with timeouts, or connect errors: invalid).
- Round-robin: one warm-up per server per size; before each window the size's servers settle (together at most
  10% of one CPU, up to 30 s, else the window is invalid); idle servers' CPU recorded; reruns within the size.
- Boost off; each system's clock reference (Arch's idle CPUs read 3,201 MHz, busy ones about 3,168: 1% bias).

## Laptop requests

The coordinator schedules them. Jobs drafted in the lab queue's format with `plain` sentences:
`t3/jobs/requests-2026-10-24.json` (rows 0, 2 to 4, at 3ff814e50), `requests-2026-10-25.json` (row 5).
0, 2, 3. Bring-up, `t3/jobs/bringup.py OUT` (p2r3-bringup-l, -w): toolchains checked, the Release build
   with every arm, CTest, the inputs hash, the Go and Rust programs, the request sets (all 160 cells
   checked), the suite, the runner's and record tools' tests, a count-mode pass of p2run.
4. Records, `t3/jobs/records.py OUT` (p2r3-records-l, -w): L ASan+UBSan, TSan and MSan, W clang-cl ASan.
   Rows 0, 2 to 4 DONE 2026-10-25 at 3ff814e, every job exit 0, archives' sha256 checked: W bring-up 840 checks, 168
   of 168 windows, p2r3-3ff814e50-W-asan green (Papers `lab/sanitizer-records/laptop-w/`, 7e0e6a0); L 880 checks, 176
   of 176, -L-asan, -tsan, -msan green (7fd305b). Gates green: W 21 targets (mserver-go's gap), L 23 (Go, Rust gaps).
1. Toolchains: done on both systems, 2026-10-24. W (Papers `lab/laptop/queues/gap2-w-q2-p2-toolchains.json`,
   a27b47e): under `C:\Users\alext\opt` go-1.27.3, meson-1.12.1, libevent-2.1.13-stable, rapidjson-1.1.0 wraps,
   boost-1.92.0, llvm-22.1.8, P4's Rust 1.99.0. L (`a1-p2-toolchains-l`): `~/opt/p2/go1.27.3`, Rust 1.99.0 in
   `~/opt/rustup` and `~/opt/cargo`, no pacman change. meson's and libevent's pins are GitHub's asset digests.
5. Timing probe before the freeze (`t3/jobs/probe.py PLAN OUT`, quiet, boost off; `t3/plans/probe-L.json`,
   `probe-W.json`): one mirrored round of every arm at m = 10 and 100,000, both shapes, pair (111, 211),
   timing the bring-ups' binaries (refused unless their sha256s and compiled sources equal 3ff814e's).
   Pre-freeze: never analysed for H8 to H10, never cited. Approved by Alex (2026-10-25, via the coordinator).
   DONE on both. Every archive's sha256 checked, every binary check empty, quiet passed:
   - W at 25fbd22 (p2r3-probe-w): exit 3, "clock_drift" (idle CPUs read 0 in 0.5 s); fixed in f5bf53e, 39bf126.
   - L at 25fbd22 (p2r3-probe-l, 15:26 to 15:56 EET, archive 022e401c): exit 0, 176 windows, 172 valid, 4
     overloaded on the error share only (Drogon, actix-router; m = 100,000, mixed-disjoint); reference 3,197.8
     MHz, drift at most 0.96%; start-up at m = 100,000 at most 5.0 s; spacing 6.05 s at m = 10, 6.56 s at 100,000.
   - W at 39bf126 (p2r3-probe-w-2, 16:10 to 16:30 EET, archive 7f81c663): exit 0, 168 windows, 162 valid, 6
     overloaded on the error share only (Oat++ at m = 100,000 on both shapes, actix-router mixed-disjoint);
     reference 3,169.8 MHz, 13 of 13 CPUs over 10.001 s, drift at most 0.34%; start-up at most 5.75 s; 6.29, 6.81 s.
6. The campaign, decision 21 (a) (Alex, 2026-10-28): the new loop, round-robin, every contestant, mixed-disjoint,
   m = 1,000 and 100,000, pair (111, 211), R = 7, 1.5 s windows; the A/A run (v2 twice per program) first, in the
   same job (`t3/jobs/rr.py`, `t3/plans/rr-aa-L.json`, `rr-L.json`, `rr-aa-W.json`, `rr-W.json`; analysis
   `t3/rr_results.py`, rules fixed before the runs; request `t3/jobs/requests-2026-10-28-rr.json`, about 15 min
   per system). The 24 h design (H8 to H10 tested, 24.28 h) does not run. Desktop count check: see Functional checks.
7. A/A pilot (p2r3-pilot-l, -w at dec7e54, `t3/jobs/requests-2026-10-26-pilot.json`; `t3/jobs/pilot.py`,
   `t3/plans/pilot-L.json`, `pilot-W.json`; rule in `hypotheses-round3.md` 3a, analysis `t3/pilot_analysis.py`):
   v2 against v2 in all three programs, one 4-window round at every H8 cell, 1,920 windows per system, the
   bring-ups' binaries; desktop count check 96 of 96 reduced windows; review 7 fixed. W DONE
   2026-10-27 03:13 to 06:40 (gap17-w-q1, tools ed917f3, exit 0, archive 6c1e18ba checked): 1,919 of 1,920
   valid (seq 831: PDH status 0x800007d6 at its end, failed closed); drift at most 0.14%, 13 CPUs counted in
   every window; others median 0.52%, 8 windows above 10% in 5 bursts (taskhostw.exe and sppsvc.exe start,
   then System up to 37.8%: 03:31, 03:40, 04:28, 05:27, 06:18); 474 of 480 replicates count. L DONE 2026-10-27
   19:48 to 23:03 (gap17-a-q1, tools 3200992, exit 0, archive 3058490f checked, Papers 3c075c3): 1,920 of 1,920
   valid, drift at most 0.95%, others median 0.66% and at most 1.83%; 480 of 480 count. Analysis of both
   (`design/round3/aa-pilot.json`; 716ac9b's code and HEAD's give the same bytes): 954 replicates, pooled
   q97.5 of r 1.0106 and of 1/r 1.0104, so delta = 1.02, the floor. |d| median and q97.5 in ns: L C++ 23.5,
   76.0; Go 36.5, 123.7; Rust 28.0, 92.7; W 45.7, 154.6; 77.1, 315.0; 47.2, 167.2. Decision 20 (H9, H10): moot.
8. p2gen against t1gen on L (p2r3-gencheck-l at 606c59b, `t3/jobs/requests-2026-10-26-gencheck.json`;
   `gencheck.py`, `plans/gencheck-L.json`, `gencheck_analysis.py`; hypotheses 3b; decision 17): 64 windows,
   about 7 min, timeout 1 h; t1gen equal to its records' 1eaee40c3; review 8 no HIGH. DONE 2026-10-26, ending
   23:53 EET, exit 0 (archive 9761e71f checked): 64 of 64 valid, t1gen's 7 self-tests passed, quiet passed, drift
   at most 0.83%, others at most 1.16%. Median q = X_p2gen / X_t1gen 0.99805, [0.99439, 1.00309] (97.87%), 16 pairs.

## Lab requests

1 to 3 done (2026-10-23 to 25): image 7f39a629ada0; the lab's archives unpacked into `p2r3-build\tools\`
(`UNPACKED.txt`); records filed (7fd305b, 7e0e6a0), test_report_pattern.sh lists `t3/record.py`.

## Alex decides

Answered on 2026-10-23 (AskUserQuestion; details in `design/round3/decisions-for-alex.md`):
1. v2 inside the Go and Rust programs. 2. P2's own generator and runner. 3. clang-cl on Windows.
4. Overloaded linear-scan routers reported, out of the tested family. 5. The cross-server routing
cost tested (H10). 6. Mixed-disjoint and static, five sizes each. 7. H8's margin from the A/A
pilot. 8. The latest releases; then Crow's 1.3.5 pre-release and Go 1.27.3. 9. Boost headers added.
10. Pistache's meson build on Windows. 11. Go routers as their libraries' handlers. 12. Push
`round3` at the freeze. 13. (2026-10-24) Pistache's logging installer patched out of the fetched
meson build (it would write into Program Files, the event log and HKCU). (2026-10-26) 14. The pilot in
all three programs. 15. delta from each direction's 97.5th percentile. 16. "Shut those processes down":
Windows Update and Defender's real-time protection off on W for good (Alex runs Papers
`lab/laptop/alex-admin-quiet.ps1`, e3dc740; a lab job checks it); the 10% rule stays a guard. 17. t1gen reported only.
(2026-10-27) 18. Host-spoiled rounds rerun once at each system's end (p2run 668f289). 19. Alex quiets
SvcRestartTask on W after P4's c3 (the coordinator's script; sppsvc may rewrite it, -Check shows; reruns cover).

Laptop time (Alex, 2026-10-26): 24/7, no approval; requests to the coordinator; design, scope, pushes to Alex.
The new loop (Alex, 2026-10-27, via the coordinator; covers round 3): campaigns of 5 to 10 minutes, median and
std dev per contestant, one fixed A/A run per OS, replacing D9's Holm test. (2026-10-28) 21. Round 3 in it: (a),
1.5 s windows, m = 1,000 and 100,000, R = 7, the A/A run per OS (row 6); 20 moot. No frozen file precedes it.

## Commits on `round3` (local, not pushed)

1862c01 to 06adfe5 (servers, reviews 1 to 3, generator, runner); a27b47e to 083b47c (request 1); 40e08db to
3ff814e (D5, laptop jobs, review 4); c7153b3 to 39bf126 (probe, `others`, Windows clock, reviews 5, 6); 76baac8
to dec7e54 (A/A pilot, review 7); 14325c0 606c59b (t1gen check, review 8); 3caa3c6 668f289 (rerun); 89230bf ed3b7e0
(round-robin, review 10, settle); docs. `bench/` is round 2's but `isa.cmake`.

## Next engineering

Row 6's request (at ed3b7e0) is with the coordinator. Then `t3/rr_results.py` over its four records.
