# Hypotheses of round 3 (DRAFT)

**DRAFT, 2026-10-23. Not frozen. Not a pre-registration yet.** It freezes only after a timing
probe on the laptop gives its hours, those hours are stated to Alex, and he approves them. Until
then every number below that is not marked as measured is a proposal. Round 2's frozen file,
`hypotheses-round2.md`, is the prior study and is never edited. Its labels H1 to H7 keep their
meaning; round 3's hypotheses continue at H8.

**2026-10-28: this draft will not be frozen as written.** Alex chose decision 21 (a): round 3 runs in the
new loop, a round-robin campaign of about 10 minutes per system reported as the median and standard
deviation per contestant. H8 to H10's tests below do not run; the text stays as the drafted design.

Design: `design/round3/end-to-end.md` (draft). Router list and its re-check:
`design/round3/router-survey.md`.

## 1. What is measured

Requests per second of HTTP/1.1 servers over loopback on one laptop (AMD Ryzen 7 5800H), on its
Arch Linux and on its Windows 11, one system at a time. Each server serves the routes of one
round-2 table, mixed-disjoint or static, at m = 10, 100, 1,000, 10,000 and 100,000, and P2's own
load generator
sends the round-2 T0 ring of the same seed pair (4,096 paths, all hits). Every found route
answers 200 with a fixed 13-byte body; the handler folds the route id and every captured value
into a sink, as round 2's timed loops do.

## 2. Arms

- The C++ server, one binary: v2 (RegexMatcher 2.1.0.0, the measured public release), null, and
  the C and C++ competitors of round 2 that build on the system: Crow, Drogon (transcribed lookup),
  Oat++, Pistache, Boost.URL's example router, r3, uWebSockets, glaze, cpp-httplib. On Windows r3
  and Pistache are absent (they do not build with MSVC; `router-survey.md`, re-check). Boost.URL
  needs Boost 1.92.0 headers on both systems (open, `STATE.md`).
- The Go program (net/http): httprouter, gin, net/http's ServeMux, chi, null.
- The Rust program (hyper on tokio's current-thread runtime): matchit, path-tree, actix-router,
  null.
- Pins: round 2's (`bench/cmake/pins.cmake`, the lock files). The servers' own crates and Go's
  toolchain are pinned by their lock files and `lab/laptop/versions.md` (open: Go and Rust on the
  laptop).

## 3. Replicates and windows

R = 16 seed pairs, round 2's (table seeds 111 to 126, ring seeds 211 to 226). Per pair, size and
system, one mirrored round per program, a fresh server per window, a 1 s warm-up and a 5 s window
(lab/t1's window rules), and a window is invalid when other processes took more than 10% of one CPU
over it, or when it has no record of them (a guard; decision 16: the lab quiets Windows Update and
Defender for the runs; decision 19: on Windows also the Software Protection restart task). The A/A
pilot and the timing probe come first.

A round with an invalid window counts for no arm. After a system's last planned window, each round
(one program's mirrored round at one shape, size and pair) with a window invalid only for host
reasons runs once more, whole and in its order. Host reasons: other processes above 10% of one CPU
or no record of them; no CPU or clock sample over the window, or a sample span more than 50 ms off
the generator's window. The rerun replaces the round; the original rows stay in the record. A window
that also failed for an arm's reason starts no rerun (a crashing server's error reporter is another
process), a round whose invalid windows are all an arm's is not rerun, and a rerun is not rerun
(decision 18; p2run's `rerun_host_faults`).

## 3a. The A/A pilot (fixed 2026-10-26, before it runs)

- Runs: v2 against v2 in each program (the C++ server, the Go program, the Rust program), one
  mirrored round of four windows per cell (entry 0's windows 1 and 4, entry 1's windows 2 and 3), at
  every cell of H8 (two shapes, five sizes, sixteen pairs), on both systems: 1,920 windows per
  system (`t3/plans/pilot-L.json`, `pilot-W.json`), with the bring-up's gated builds and the
  campaign's window values. A/A only: no arm is compared with another.
- The analysis takes exactly one file per system, both systems, each one complete timed run of that
  system's committed pilot plan; it refuses anything else.
- A window counts if it is valid by the runner's rules, has at least one completed answer, and has a
  record of other processes showing at most 10% of one CPU over it (the campaign's rule, section 3).
  A replicate (system, program, shape, size, pair) counts only if its four windows count.
- Per replicate, X_e is the mean req/s (completed answers over the window's wall time) of entry e's
  two windows; r = X_0 / X_1 and d = 1/X_0 - 1/X_1 in ns.
- delta = the largest of 1.02, the 97.5th percentile of r and the 97.5th percentile of 1/r, over all
  counted replicates of both systems; percentiles by linear interpolation (type 7); rounded up to
  four decimals.
- Per system and program, the median and the 97.5th percentile of |d|: the A/A noise from which H9's
  minimum D_T0 and H10's margin are fixed before the freeze.
- Code: `t3/pilot_analysis.py` (commit 716ac9b). Alex chose all three programs (decision 14) and the
  reading above (15) on 2026-10-26. On other processes (16) he chose no rule: "Shut those processes
  down" (Windows Update and Defender, quieted by the lab); the 10% rule stays as a guard.
- Result (2026-10-27, both systems; `design/round3/aa-pilot.json`): 954 of 960 replicates count;
  delta = 1.02, the floor (pooled 97.5th percentiles: r 1.0106, 1/r 1.0104).

## 3b. p2gen against t1gen (reported only; decision 17, fixed 2026-10-26 before it runs)

On Arch, the C++ server's null arm in an A/A round per pair, entry 0 driven by p2gen and entry 1 by
lab/t1's t1gen (sources equal to its green records' commit 1eaee40c3, Release, clang 22.1.8), static
m = 10, sixteen pairs (`t3/plans/gencheck-L.json`, `t3/jobs/gencheck.py`), every window rule of the
runner. Per pair q = X_p2gen / X_t1gen; reported: the median of q and its distribution-free interval
from the order statistics (q_(4), q_(13) for sixteen pairs, 97.87%). No pass rule
(`t3/gencheck_analysis.py`).

## 4. Hypotheses (proposed)

H8. In the same server, v2 is not slower than each competitor.
    - Same server: the C++ server for the C and C++ competitors; the Go program, with v2 behind its
      C interface (through cgo), for the Go competitors; the Rust program, likewise, for the Rust
      competitors. The language boundary counts against v2.
    - Family: every competitor that builds on the system, x 5 sizes x 2 shapes: at most 16 x 10 on
      Arch and 15 x 10 on Windows, 310 cells.
    - Per pair, the ratio X_v2 / X_competitor of the two arms' mean req/s over their two windows.
    - A cell holds if the lower bound of the 95% BCa interval of the median ratio is above
      1 / delta and the exact one-sided sign test passes at alpha = 0.025 after Holm over the
      family. With R = 16, 2^-16 = 1.53e-5 is below 0.025 / 310 = 8.06e-5 (D9).
    - delta is the larger of 1.02 and the A/A pilot's 97.5th percentile of the ratio of v2 to
      itself (or its inverse), fixed in this file before the pilot runs (Alex, 2026-10-23): section 3a.
      The pilot gave delta = 1.02.
    - A competitor whose windows in a cell are invalid only by the error-share rule, because it
      cannot sustain the load, is reported as "does not sustain the load", with its completed
      requests and req/s, and leaves the family (Alex, 2026-10-23).
    - Superiority is reported beside it with the same machinery and bound 1.00.

H9. v2's faster lookup carries over to the client in the C++ server.
    - Per cell and pair, D_meas = 1/X_competitor - 1/X_v2 against D_T0 = t_competitor - t_v2, the
      two arms' round-2 T0 lookup times at the same pair (round 2's raw grid has all sixteen).
    - A cell holds if the lower bound of the 95% BCa interval of D_meas / D_T0 is at least 0.5,
      round 2's H6(b) bound. A cell whose T0 difference is not positive does not hold.
    - Where D_T0 is small the ratio is unstable (for example uWebSockets against v2 at m = 10, about
      18 ns in round 2). A cell whose D_T0 is below a minimum, to be fixed before the freeze from
      the A/A pilot's noise in time per request, is reported and not tested.

H10. v2's routing costs a request no more than each Go and Rust router's costs it, each in its
    own server (Alex, 2026-10-23, to be worded at the freeze).
    - Per pair, the increments I_v2 = 1/X_v2 - 1/X_null of the C++ server and I_r = 1/X_r - 1/X_null
      of router r's own program, in ns per request. The difference I_v2 - I_r, tested against a
      margin in ns taken from the A/A pilot's noise in time per request. Not a ratio: the increments
      are sub-microsecond differences of noisy per-request times near 10 us, and their ratio is
      unstable and can change sign.
    - Family: 7 routers x 5 sizes x 2 shapes x 2 systems = 140 cells; 0.025 / 140 = 1.79e-4.
    - The boundary is stated with every result: the servers and runtimes differ.

Reported, not tested:
- Raw req/s of every arm, per program.
- The null arm's time per request on each system: the same-hardware contrast of the two systems'
  network paths.
- The H7 compile costs with MSVC on the laptop's Windows (round 2's H7 procedure).

## 5. What would count against the claim

A cell of H8 that fails, or a competitor whose increment is below v2's in its own server. Both are
reported as they come out.

## 6. Open before the freeze

Alex answered the design questions on 2026-10-23 (`design/round3/decisions-for-alex.md`). Open:
1. P2's load generator and runner, built and A/A-checked against `t1gen` on Linux.
2. The wording of H10.
3. The laptop hours, from a timing probe.

## Revision log

- 2026-10-23: first draft.
- 2026-10-26: section 3a, the A/A pilot's procedure and rule, fixed before it runs. Before it, the
  timing probe ran on both systems (pre-freeze, never analysed for H8 to H10); no arm was compared.
- 2026-10-26: Alex's answers to decisions 14 to 17 (sections 3 and 3a); the rule is unchanged.
- 2026-10-27: the W pilot ran (1,920 windows; 6 of 480 replicates dropped, 5 by the guard in 5 bursts
  of the Software Protection service, 1 by a PDH fault). Alex's answers to decisions 18 and 19: the
  rerun of host-spoiled rounds and the quieting of that service (section 3). The pilot's rule is unchanged.
- 2026-10-27: the L pilot ran (1,920 of 1,920 windows valid, 480 of 480 replicates count). The analysis
  of both pilots (716ac9b's code; the current code gives the same output, byte for byte): delta = 1.02
  (section 3a). H9's minimum and H10's margin: decision 20, open.
- 2026-10-28: Alex's answer to decision 21: (a). Round 3 runs in the new loop (mixed-disjoint, m = 1,000 and
  100,000, pair (111, 211), R = 7 round-robin rounds of 1.5 s windows, every contestant, one A/A run per
  system), with no tested family. H8 to H10 are not tested and this draft is not frozen; decision 20 is moot.
