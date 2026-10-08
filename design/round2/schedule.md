# Round 2 schedule

Status: design for review, round 2 of P2, phase 1. Written Wednesday 2026-09-30. Dates are
targets; each depends on the step before it and on Alex's replies.

## 1. Constraints

- **L** runs round 1's exploratory cells until about the evening of Thursday 1 October. P1 has
  priority on L for its short runs. P1's L publication runs are done (2026-09-29, P1's
  `results/README.md`), and P1's L package freeze runs until its last L run. Every P2 job on L
  runs under `lab/bin/lablock`.
- **W** is free now for building and profiling, natively and in WSL. Nothing heavy runs on W
  while a P1 measurement runs there (Alex says when).
- **WSL** has clang 18.1.3, gcc 14.2, CMake, Ninja, Python 3 and the instrumented libc++ 18
  (`~/opt/libcxx-msan-18`). It has no Go, Rust, perf or valgrind, and installing any of them is
  a download that needs Alex's yes. A full rbench build fetches every competitor with
  FetchContent, which is also a download. So in WSL only v2, the server and rbench's core
  build; the full rbench, and everything with Go or Rust, builds on L, which already holds
  those toolchains and sources.
- **Publishing.** Nothing is pushed to RegexMatcher or any public repository without Alex's
  yes. L runs from fresh clones, so before a public push L gets v2 from a bare repository on L
  (`~/lab/git/RegexMatcher.git`), pushed from W over the management link.
- **Venue.** P2 targets MDPI Future Internet, a journal without a deadline
  (`paper/venues.md`). P1's TELECOM 2026 upload deadline is 2026-11-02, so P1 keeps priority
  where the two compete (D6).

## 2. Steps

| Dates | Step | Where | Output |
|---|---|---|---|
| Wed 30 Sep | These five documents; wait for Alex's reply | | this commit |
| Thu 1 Oct | E1 and E2 in a local RegexMatcher branch; R1 to R18, NEW and NEG written first and ported; the objdump check with clang 18; `inputs_hash.py` `--dep-root` and `--label-hash` with their tests (after Alex's go on the lab change), P1's and round 1's recorded hashes recomputed and unchanged | W, WSL | v2 builds and passes its suite in WSL |
| Thu 1 Oct, evening | L free: the bare repository; the objdump check with clang 22.1.8; the instruction baseline of v2 at E2 on the engineering seeds (every shape at m = 10 to 100,000), with gin, for rule 1 of targets (b) and (a) | L | development baseline, journal entry |
| Fri 2 to Sun 4 Oct | C1 (one adapter template), the rbench renames, `table-digest`, `build_alloc_bytes`, the page-offset fields; A1 to A3 with their deterministic checks; the CT tables at the new seeds generated; the competitor adapters Alex accepts (C++ ones in WSL, chi and path-tree on L) | W, WSL, L | rule 1 of target (a) met |
| Mon 5 Oct | Target (a), rule 2 (v2's build, 10 processes per build, 21 cells) | L | adopt or not, journal |
| Mon 5 to Tue 6 Oct | C2 (one layout); its deterministic checks; the H7 iteration check (21 cells, 10 processes per arm) | WSL, L | adopt, journal |
| Tue 6 to Thu 8 Oct | B1 (or B1'): instruction rule in WSL, then on L; the time rule (about 2 h 12 min on L) | WSL, L | adopt or not, journal |
| Wed 7 to Thu 8 Oct | The minimal server, tests first (section 5 of `minimal-server.md`); the H6 tools rewritten | WSL | server passes its suite and the agreement test |
| Fri 9 Oct | Code freeze: v2 release candidate, rbench, the server. Pins of the eleven competitors checked for newer releases. Alex freezes `hypotheses-round2.md` and the revision-log entry of `hypotheses.md` is committed | W | frozen pre-specification |
| Fri 9 to Sun 11 Oct | Records. L: RegexMatcher v2 suite, rbench and the server, each ASan+UBSan, TSan and MSan. W: RegexMatcher v2 suite with MSVC ASan and clang-cl ASan (extra coverage). L package freeze for P2 starts with the first record | L, W | green records, journal |
| Mon 12 to Tue 13 Oct | The main grid: 14 h 19 min at R = 16 without new competitors, 17 h 50 min with four (estimate, `hypotheses-v2-proposal.md`, section 7); then the answer re-verification | L | raw run, archive and sha256 |
| Wed 14 Oct | The H7 cost run; H6 at T1; the exploratory cells | L | raw runs, archives |
| Thu 15 to Sun 18 Oct | Analysis: the clustered BCa and exact sign test decisions, H6's new statistics, macros; an independent verification of the decisions | W | `results/`, `macros.tex` |
| Mon 19 to Fri 23 Oct | The paper rewritten: lookup speed first, RegexMatcher v2 as the subject, the compile-time checks second, round 1 disclosed as development data; independent fact-check | W | draft |
| after that | Alex: the public push of v2 and its tag, the tag at d16f30a8, the paper repository's publication, submission | | |

## 3. Risks

1. **Reply latency.** Implementation starts on Alex's reply. Each day of delay moves every date
   after it; the plan has no buffer before the records.
2. **L's windows.** The main grid needs one lab-locked window of 14 to 18 hours, then about a
   day for the rest. A reboot, a power loss or a package change inside the P2 freeze breaks the
   gate: round 1 recorded that L runs kernel 7.2.3 while 7.2.6 is installed, so a reboot changes
   the kernel. If L is to be updated, it must happen before the first round-2 record.
3. **The engineering may not reach its targets.** H4 may still be lost in some cells after the
   build rework; B1 may still cost instructions where there is no chain, and then the H2 loss
   at mixed-disjoint m = 10 stands; an H7 cell may cross at another table seed. Each is
   reported as a loss, the claim narrowed by the frozen rule; nothing is re-run to change a
   decision.
4. **New competitors may win cells.** uWebSockets and glaze are C++ routers built for speed. A
   loss in H1 is reported; D2 asks to engineer v2 until it wins before measuring, which would
   move the schedule.
5. **The stricter decision rule.** A cell passes H1 or H7 only under both the clustered
   bootstrap and the exact sign test. With R = 16, H7 needs 13 of 16 pairs below 1.02; in
   round 1, one H7 cell had 8 of 10 (`results/sens_h7.csv`).
6. **Public push and licence.** The paper needs the measured v2 commit public before
   submission, and the licence file of RegexMatcher names the private library
   (`regexmatcher-v2.md`, section 11). Both are Alex's decisions.
7. **The pinned v1 commit** lives only on a non-main branch; if that branch goes, the
   reference arm's tarball URL fails (`regexmatcher-v2.md`, section 3).
8. **Compilers.** Development uses clang 18.1.3 in WSL; the measured builds use clang 22.1.8 on
   L. Instruction evidence from WSL is indicative; every adoption decision that rests on
   instructions is confirmed on L.
9. **The shared lab script.** `inputs_hash.py` is used by P1 and P2; its change must leave every
   existing hash bit-identical, P1's project-mode records included.
10. **CI.** GitHub Actions does not start jobs on Alex's account; the organization's status is
    unknown. The lab records carry the evidence; CI is a convenience.
11. **The time estimate** assumes round 1's average of 5.65 s per process for every arm. Slow
    new arms at m = 100,000 could each spend the 120 s agreement cut per process, as
    actix-router did in 60 processes of round 1.
12. **Scratch profiling was on another CPU.** W is Zen 2 under a hypervisor; L is Zen 3. The H7
    placement finding of `engineering.md` (no effect on W) may not hold on L.

## Revision log

- 2026-09-30: first version, for review.
- 2026-09-30, approved. The main grid now has 22 arms at R = 16 (five added competitors and the
  ablation arm): 12,488 processes, 19 h 35 min at round 1's average (`hypotheses-v2-proposal.md`,
  section 7). Work is local and private: a local branch of RegexMatcher, a bare repository on L
  set up without any build there, development and profiling on W and in WSL. Milestones are
  reported as they are reached. The version, the tags, the engine commits, the licence and the
  public push wait for Alex.
- 2026-09-30, first milestone (the Thu 1 Oct row) reached early on 30 Sep, except what needs L:
  the RegexMatcher branch (tests first, E1, E2, the checked front end, CI file, README,
  changelog), the objdump check with clang 18.1.3 and gcc 14.2, and `inputs_hash.py`'s
  `--dep-root` and `--label-hash` with their tests (P1's stored W inputs recomputed identically).
  The bare repository on L is set up (no build there). Waiting for L: the objdump check with
  clang 22.1.8, P2's stored round-1 inputs recomputed with the new script, and the instruction
  baseline.
- 2026-09-30, second milestone (the Fri 2 to Sun 4 Oct row) reached on 30 Sep, except what needs
  L: C1, the rbench renames, `bench/tools/table_digest`, `build_alloc_bytes`, the page-offset
  fields, A1 to A3 with their deterministic checks, the compile-time tables at the new seeds,
  and the five competitors' adapters. Rule 1 of target (a) holds in WSL (`engineering.md`,
  revision log). The three C++ competitors agree in WSL (uWebSockets with its declared wild
  difference); chi and path-tree compile on W. Waiting for L, in the first slot after round 1's
  exploratory cells, as one lablock job with pid and done files (`bench/jobs/slot1.sh`): the
  objdump check with clang 22.1.8; P2's stored round-1 inputs recomputed with the new
  `inputs_hash.py`, a hard condition before any round-2 record; the instruction baseline with
  gin; and every arm built with clang 22.1.8 and checked by agreement (chi, path-tree, and
  glaze, not yet built with clang). Target (a)'s rule 2 follows on L.
- 2026-09-30, the first L slot (the Thu 1 Oct evening row) ran on 30 Sep, 04:10 to 04:19, after
  round 1's queue closed (lab evidence `2026-09-30-L-slot1`, Papers repository). The stored
  inputs job ran first as the gate and passed: 32 of 32 stored target hashes of P1 and P2
  recomputed identically, and the default mode identical on P2's round-1 build directories, so
  the hard condition before any round-2 record holds. The objdump check with clang 22.1.8 is
  identical at E1, E2, F1 and f48fa83. The instruction baseline (v2 at f48fa83, the ablation
  arm, gin; engineering pairs; pinned) has v2 and the ablation arm equal in every cell and v2
  above gin at mixed-disjoint m = 10 in both pairs. All 24 arms build with clang 22.1.8 and
  agree as `bench/semantics.json` declares. C2 (the Mon 5 to Tue 6 Oct row) is built and its
  deterministic checks hold in WSL (`engineering.md`, revision log); RegexMatcher 45ab696 is in
  the bare repository on L. Next on L: target (a)'s rule 2 and the H7 iteration check of C2.
  Next on W: B1, first in WSL.
- 2026-09-30, the second L slot ran 04:44 to 05:10 (lab evidence `2026-09-30-L-slot2`): target
  (a)'s rule 2 holds in 21 of 21 cells, and A1 to A3 are adopted; C2's H7 iteration check
  passes (no cell's median above 1.02). B1 (the Tue 6 to Thu 8 Oct row) and B1' are built and
  fail rule (b)'s instruction clauses in WSL (`engineering.md`, revision log); an L job with
  gin measures them next.
- 2026-09-30, the third L slot (05:50 to 06:22, with one stopped start; lab evidence
  `2026-09-30-L-slot3`) decided target (b): nothing is adopted, the H2 loss at mixed-disjoint
  m = 10 stands, and RegexMatcher is back at C2. The B1 time rule (Tue 6 to Thu 8 Oct) is not
  needed. On W meanwhile: the minimal server (HTTP layer, epoll loop, three router arms, the
  binary, its tests and the arms' agreement on the nine H6 cells) and RegexMatcher's sanitizer
  records script. Next: the t1 scripts and the records gates, then the freeze.
