# Round 3: decisions for Alex

Written 2026-10-23 by the round-3 session. Each item: what is to decide, the facts, the options with
their cost, and a recommendation. Hours use the measured basis of `end-to-end.md`, section 11: one
window is 6.30 s on the laptop's Arch (H6) and 6.123 s on its Windows (plan v2). The base campaign
is 3,200 windows (5.60 h) on Arch and 2,880 windows (4.90 h) on Windows, before the pilot and
start-up. Answer by number and letter.

**Answered by Alex on 2026-10-23:** 1 (a), 2 (b), 3 (b), 4 (b), 5 (b), 6 (b), 7 (b), 8 (b),
9 (a), 10 (a), 11 (a), 12 (a). Recorded in `STATE.md`, "Alex decides".

## 1. A same-server contrast against the Go and Rust routers

**What.** Today only the C and C++ routers run in the same server as v2, so only they are tested
against v2 end to end. The Go and Rust routers run in their own programs (your rule in the brief),
and against them the paper can only report each router's cost per request over its own server's
null arm, a cross-server comparison that is not tested.

**Why it matters.** On mixed-disjoint, the fastest competitor in round 2 is gin at every size
(`results/round2/h1.csv`). At m = 10, v2 was not slower than gin but not faster either (51.8 against
53.4 ns per lookup). The next fastest are Go and Rust routers too (httprouter, matchit). So without a
same-server contrast, round 3 tests v2 end to end only against routers it already beat clearly.

**How.** Add v2 behind a C interface to the Go and the Rust program, as one more arm in each. The
language boundary then counts against v2 (cgo costs tens of ns per call; round 2 measured it as
`ffi_call_ns`; a Rust call into C is a plain call), which is the honest direction.

**Options.**
- (a) Both programs. +4 windows per pair and size: +0.56 h on Arch, +0.54 h on Windows. cgo on
  Windows needs a MinGW gcc on the laptop (Go's cgo does not use MSVC) and v2 built with it for that
  arm: a toolchain item for the laptop.
- (b) Rust only. +0.28 h and +0.27 h. Easy on both systems. Covers matchit, path-tree and
  actix-router, not gin.
- (c) Neither. The Go and Rust comparison stays reported, not tested.

**Recommendation.** (a). gin is the router a reviewer will compare v2 with.

## 2. The load generator on Windows

**What.** lab/t1's generator `t1gen` and its runner `t1.py` are Linux only (epoll, `taskset`,
`/proc`). Nothing can time a Windows window today, the timing probe included. This is the first
blocker of the Windows half.

**Options.**
- (a) Port lab/t1 to Windows, as lab tooling: `t1gen` on IOCP or WSAPoll, `t1.py` with Windows
  affinity and counters. Other papers could use it. It is lab work, through the coordinator.
- (b) P2's own portable generator and runner in P2's repository, C++23, epoll and IOCP, with t1's
  window rules, used on both systems. Your brief says "C++23 for this paper's server and generator",
  and P3 and P4 have their own. One generator on both systems makes the cross-system contrast
  cleaner. Before use, an A/A check on Linux against `t1gen` (no arm comparison).
- (c) Reuse P3's or P4's Windows generator. Quickest, but it ties P2 to another paper's code, which
  the component model avoids.

**Recommendation.** (b).

## 3. The C++ compiler on Windows

**What.** The C++ server is built with clang 22.1.8 on Arch and MSVC 19.51 on Windows. Then a
difference between the systems is the system plus the compiler, which weakens the point of
measuring both systems on one laptop. The Go and Rust programs use the same compiler on both.

**Options.**
- (a) MSVC only. Installed on the laptop; Windows' own compiler. The paper states the compiler
  confound.
- (b) clang-cl 22.1.8 only. Same compiler on both systems. Needs LLVM 22.1.8 installed on the
  laptop's Windows (download with sha256), a clang-cl branch in `bench/cmake/isa.cmake` (today a
  clang-cl build would get `/arch:AVX2`, not `-march=native`), and the Windows records made with
  clang-cl's ASan (rule D5 allows it). Not yet tried with the six Windows arms.
- (c) clang-cl for the tested cells, and MSVC reported beside them. The C++ server's windows on
  Windows measured twice: 16 of 36 windows per round, +1,280 windows, +2.18 h.

**Recommendation.** (b), with (a) as the fallback if an arm does not build with clang-cl.

## 4. Routers that scan linearly at m = 100,000

**What.** Four routers scan their routes one by one. In round 2, one lookup at m = 100,000 took
30.1 ms (actix-router), 7.80 ms (Drogon), 3.95 ms (Oat++) and 0.96 ms (cpp-httplib). On one server
core that allows at most about 33, 128, 253 and 1,043 requests per second, before any HTTP cost. In
a 5 s window with 64 connections, actix-router completes about 165 requests, and each request
waits behind the others. Such a window may fail lab/t1's validity rules (an error share above 0.1%
if the generator times out), and then the cell fails for want of valid pairs, although v2 is far
faster there.

**Options.**
- (a) Measure them like every other cell, same rules. If their windows are invalid, the cell is
  reported as failed.
- (b) Same windows, plus a rule fixed now: a competitor whose windows are invalid only by the error
  rule, because it cannot keep up with the load, is reported as "does not sustain the load", with
  its completed count and req/s, and leaves the tested family.
- (c) Longer windows for these cells (for example 30 s). More completions, more hours.
- (d) Leave these four routers out at m = 100,000, as round 2's time budget did at the lookup level.

**Recommendation.** (b): every cell is measured and shown, and the rule is set before any data.

## 5. Whether the routing cost across servers is a tested hypothesis

**What.** For the Go and Rust routers, the paper can report each router's time per request over
its own program's null arm, beside v2's over the C++ server's null arm. The two come from different
servers and runtimes: subtraction removes most of the server's own cost, not its interaction with
the router (Go's scheduler and collector, tokio).

**Options.**
- (a) Report it with intervals and the boundary stated, not tested.
- (b) Test it as its own hypothesis, with its own Holm family.

**Recommendation.** (a) if you choose 1(a); then the tested comparison against gin and matchit is
the same-server one, and the cross-server numbers are context. (b) only if you choose 1(c).

## 6. Which table shapes

**What.** The design uses one shape, mixed-disjoint, at the five sizes: plan v2's 80 cells. All
sixteen competitors take part in it in round 2, and it mixes literal and parameter routes. Static
(the case where a hash or a radix tree can lead) and the other one-layout shapes are not run end to
end.

**Options.**
- (a) Mixed-disjoint only. Base hours.
- (b) Add static at all five sizes. +5.60 h on Arch, +4.90 h on Windows.
- (c) Add static at m = 10 and m = 100,000 only. +2.24 h and +1.96 h.

**Recommendation.** (a). Round 2 already shows where v2 wins and loses per shape at the lookup
level; the end-to-end question is whether that reaches the client, and one mixed shape answers it.

## 7. The margin of "not slower" (H8)

**What.** H8 says v2 is not slower than each C and C++ router in the same server, at a margin
delta. Plan v2 says margins come from the new A/A pilot by a rule fixed before it. Round 2 used
1.02 for H1 and H7.

**Options.**
- (a) delta = 1.02, as round 2.
- (b) delta = the larger of 1.02 and the A/A pilot's 97.5th percentile of the v2-against-v2 ratio
  (or its inverse), fixed in the frozen file before the pilot runs.
- (c) Superiority only (bound 1.00), no margin.

**Recommendation.** (b). End to end, the run-to-run noise may be wider than 2%, and the pilot
measures it.

## 8. Pins

**What.** Round 3 uses round 2's pins, so the servers run the code round 2 timed. Newer releases
exist since 2026-09-30, checked again (`router-survey.md`, re-check):
- cpp-httplib: six releases, v0.59.0 to v0.63.0; its matchers are unchanged.
- chi: v5.4.0 and v5.5.0; its lookup is unchanged.
- Drogon: v1.9.14; the transcribed router file is byte for byte the same.
- Crow: 1.3.5, a pre-release.
- Go: 1.27.2 and 1.27.3; round 2 used 1.27.1.

**Options.**
- (a) Keep round 2's pins, including Go 1.27.1 on both systems; list the newer releases.
- (b) Move every arm to its latest release.

**Recommendation.** (a). Where a newer release exists, its lookup code is the same, so (b) changes
nothing measured and breaks the link to round 2's lookup data.

## 9. The Boost.URL arm

**What.** The boost-url arm needs the Boost 1.92.0 headers. The dev image has Boost's libraries
but not its headers, and the laptop's Windows has none. Boost.URL's example router has not been
built with MSVC by anyone that the survey found.

**Options.**
- (a) Add the headers to the image and to the laptop's Windows (Boost's release archive, checked
  by sha256); keep boost-url on Arch, and on Windows if it builds.
- (b) Arch only.
- (c) Drop boost-url from round 3, with the reason.

**Recommendation.** (a).

## 10. Pistache on Windows

**What.** Pistache v0.4.26's CMake build passes GCC flags to MSVC. Its Windows build goes through
meson and libevent instead, which the survey found in its CI and which is not tried here.

**Options.**
- (a) Bring up its meson build with libevent on the laptop's Windows: a new pinned dependency and
  engineering time with no measured basis.
- (b) Absent on Windows, with the reason. Windows loses 5 of its cells.

**Recommendation.** (b).

## 11. How the Go routers are hosted (confirm)

**What.** After the review, each Go router runs as the `http.Handler` its library documents: gin's
Engine (`gin.New()` in release mode), chi's Mux, httprouter's Router, net/http's ServeMux. So each
request pays the library's own steps around the lookup (gin's pooled Context, chi's route context).
Round 2 timed the lookup alone. The C and C++ routers run in the paper's server as bare lookups,
because they have no handler layer apart from their own full servers.

**Options.**
- (a) Keep it: each router as a server would use it.
- (b) Bare lookups in the Go program too, as round 2 timed them (needs per-request state that the
  vendored shims do not have; the review found the earlier attempt charged gin a lock).

**Recommendation.** (a).

## 12. The public timestamp of the pre-registration

**What.** `hypotheses-round3.md` must be frozen and publicly timestamped before the first
confirmatory window. P2's repository is public. Nothing of round 3 is pushed.

**Options.**
- (a) Push the `round3` branch, with the frozen file, at the freeze and before any confirmatory
  window. The engineering commits become public with it.
- (b) Push only the frozen file's commit (a branch cut at the freeze), and the engineering later.
- (c) A Zenodo record of the frozen file at the freeze, the push later.

**Recommendation.** (a).

## 13. Pistache on Windows: its build installs into the system (2026-10-24)

**What.** Pistache v0.4.26's meson build on Windows runs its script `src/winlog/installman.ps1` as a
build step of the library: it copies `pistachelog.dll` into `C:\Program Files\pistache_distribution\bin`
and installs an event-log manifest with `wevtutil im` (both as administrator), and writes registry
keys under `HKCU\Software\pistacheio`. Pistache's CMake build has no Windows path at all. Decision 10
chose the meson build before this was known.

**Options.**
- (a) The meson build without its installer: the one line of the fetched copy's `src/meson.build`
  that makes the library depend on it is removed; Pistache's C++ code is unchanged, and its router
  code (`src/server/router.cc`) makes no log call.
- (b) The meson build as published, installed as administrator on the laptop and the desktop.
- (c) Pistache absent on Windows: 10 cells fewer.

**Recommendation.** (a). **Answered by Alex on 2026-10-24 (AskUserQuestion): (a).**

## 14. The A/A pilot: which servers (2026-10-26)

**What.** H8's delta (decision 7) comes from an A/A pilot: v2 against itself in a mirrored round of
four windows (the first entry's windows 1 and 4 against the second entry's 2 and 3, the pattern of
`lab/laptop/aa_trial.py`), at every cell of H8 (two shapes, five sizes, sixteen pairs), on both
systems, with the bring-up's gated builds. One delta covers H8's cells in three servers: the C++
server, the Go program and the Rust program. Hours at the probes' measured spacing (6.05 to 6.56 s a
window on Arch, 6.29 to 6.81 s on Windows; v2 starts fast, so these are upper bounds).

**Options.**
- (a) v2 against v2 in all three programs: 1,920 windows per system, at most 3.3 h on Arch and 3.4 h
  on Windows (Windows quiet for all of its half).
- (b) The C++ server only: 640 windows per system, about 1.1 h each. The Go and Rust cells then get a
  delta measured in another server.

**Recommendation.** (a). One delta is applied to all three servers' cells, so it should be measured
in all three; laptop time no longer limits it. **Answered by Alex on 2026-10-26 (AskUserQuestion): (a).**

## 15. The percentile that sets delta (2026-10-26)

**What.** Decision 7 (b) reads "the A/A pilot's 97.5th percentile of the v2-against-v2 ratio (or its
inverse)". Per pilot replicate (program, shape, size, pair, system), r = X_first / X_second, each X
the mean req/s of that entry's two windows, as H8's ratio. Pooled over all replicates of both systems,
the percentile by linear interpolation (numpy's default). The words allow two readings.

**Options.**
- (a) delta = the largest of 1.02, the 97.5th percentile of r, and the 97.5th percentile of 1/r: each
  direction's one-sided 2.5% point, whichever entry is named first.
- (b) delta = the larger of 1.02 and the 97.5th percentile of max(r, 1/r): the folded ratio, so 1.25%
  in each tail; a larger delta than (a).

**Recommendation.** (a). H8 tests one direction (is v2 slower) at 2.5%; (a) is the noise of that
direction for either naming of the two entries. **Answered by Alex on 2026-10-26 (AskUserQuestion): (a).**

## 16. Other processes' CPU during a window (2026-10-26)

**What.** p2run records per timed window the CPU of every other process, from just before p2gen
starts to just after it exits (`others`, the lab's `labrec`). No rule uses it yet. The probes: on
Arch at most 1.99% of one CPU in 176 windows; on Windows a median of 0.78%, 2 of 168 windows above
5% (8.3% and 23.6%: Windows Update's MoUsoCoreWorker, svchost, Defender), no single process above 10%.
The rule also decides which pilot windows count, so it moves delta.

**Options.**
- (a) A window is invalid when other processes together exceed 10% of one CPU (the lab's quiet check's
  limit for one process, applied to their sum). In the probes: 1 window of 344.
- (b) Record only, no rule; the share is reported beside the results.
- (c) Invalid above 5%: 2 windows of 344.

**Recommendation.** (a). A window where other work took a tenth of a CPU is not the quiet host the
method states. With R = 16 a cell of H8 can lose two pairs and still pass Holm (2^-14 = 6.1e-5 below
8.06e-5), and the probes suggest about one such window in 170, all on Windows.
**Answered by Alex on 2026-10-26 (AskUserQuestion), none of the options: "Shut those processes down."**
Windows Update and Defender are to be quieted on the laptop's Windows for the runs, by the lab (his
`alex-admin.ps1`), not by this session; passed to the coordinator. The 10% rule of (a) stays in the
text and the analysis as a guard unless he says otherwise.

## 17. p2gen against t1gen on Arch (2026-10-26)

**What.** The design says p2gen is "A/A-checked against t1gen on Linux before use (no arm compared)",
with no pass rule. `t1gen` is lab/t1's generator, Linux only, not yet built on the laptop. H8 to H10
compare arms under one generator, so a bias common to both arms cancels in their ratio.

**Options.**
- (a) Report only: on Arch, the C++ server's null arm driven by t1gen and by p2gen in alternation
  (x y y x) over 16 rounds; the ratio of req/s and its interval reported, no pass rule.
- (b) A pass rule: the ratio's 95% interval within [0.98, 1.02], or the campaign waits for an
  explanation. The 2% is round 2's margin, not a measured basis for two generators.
- (c) Drop the check; the A/A pilot measures p2gen's own noise.

**Recommendation.** (a). There is no basis for a threshold between two generators, and the tested
ratios do not depend on a shared bias. **Answered by Alex on 2026-10-26 (AskUserQuestion): (a).**
