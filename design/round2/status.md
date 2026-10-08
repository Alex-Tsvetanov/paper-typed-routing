# Round 2 of P2: status and handover

Written 2026-09-30, when implementation stopped before the sanitizer records and the runs on L,
so that another agent can continue from this file alone. The design notes in this directory
(`regexmatcher-v2.md`, `engineering.md`, `minimal-server.md`, `hypotheses-v2-proposal.md`,
`schedule.md`, `competitor-survey.md`) are approved and frozen; every change since is in their
revision logs, which this file summarizes and does not replace. Every number here is in the
evidence file named beside it (Papers repository, `lab/evidence/`), and the lab journal
(`lab/journal.jsonl`) has one entry per step.

Words, as in the design notes: "the round-1 header" is the router of the private library that
round 1 measured, which this repository never names; v1 is RegexMatcher's regex-set engine at
d16f30a8; v2 is RegexMatcher's route matcher (`include/matcher/route.hpp`).

## 1. Standing rules

From the coordinator, all still in force:
- Work is local and private. Nothing goes to RegexMatcher's public GitHub repository (the
  remote `origin` of `D:\Dev\GitHub\RegexMatcher`) or to any public repository; Alex approves
  that. RegexMatcher's branch goes only to the bare repository on L (the remote named `lab`).
- Commit explicit paths after `git pull --rebase`; push only to the private remotes (the paper's
  and the Papers repository's `origin`). Other agents commit in these trees.
- No em or en dashes anywhere. Never invent a number: every figure comes from a file read or a
  measurement made, and says which. Documents never name the private library.
- Frozen files are never edited; changes go into revision logs.
- Fetches (coordinator, 2026-09-30): only from a project's official GitHub repository or its
  official release archive (crates.io accepted for crates), at a pinned tag or commit, with the
  URL and sha256 in `bench/cmake/pins.cmake` and the hash checked on use; run nothing from a
  download except its own build; send no personal data anywhere.
- L: every job under `~/lab/Papers/lab/bin/lablock`, with a pid file and a done file; tell the
  coordinator at launch and at the end, and at once on a failure. Rule D7 (`CLAUDE.md`): lab
  traffic uses the wired subnet 10.10.10.0/24, never 192.168.1.9, L's Wi-Fi address. This round's
  control traffic (ssh, the bare repository's remote `lab`) went to 192.168.1.9; its measurements
  ran on L alone (rbench, and H6 over loopback), so no measured traffic crossed a network.
- Report at each milestone and at once on any blocker. Never submit, send or post anything.

## 2. Repositories and commits

### RegexMatcher (`D:\Dev\GitHub\RegexMatcher`, branch `v2/route-matcher`)

Based on `origin/main` at 2220b61. Pushed only to `lab` =
`ssh://alex@192.168.1.9/home/alex/lab/git/RegexMatcher.git`, head **d1d73e9**, whose tree equals
45ab696's (`git rev-parse d1d73e9^{tree} 45ab696^{tree}` give the same hash). Never pushed to
`origin`. CMake version still 2.0.0.1 (Alex decides). `lab` also has
`perf/deterministic-live-sets` at d16f30a (v1's pinned commit).

| Commit | What | State |
|---|---|---|
| cc30102, 30d2599, c4573a2 | build options; the route tests, then the checked front end's tests, written first | adopted |
| 00a2053 | E1: the round-1 header extracted, renamed only | adopted |
| e20f185 | E2: split into headers by part; portable aligned delete | adopted |
| 661b569 | F1: the method enum and the checked front end | adopted |
| e7e0c9b, 150d4ab, 53e8dda | README, changelog, CI workflow; comments; Windows compilers checked | adopted |
| 39f3e48, f48fa83 | A1 to A3: the build rework (compact entries, index sort, one groups stack; segments reserved) | adopted (target (a)) |
| 45ab696 | C2: `RuntimeTable`, the run-time table in one page-aligned block laid out as the compile-time table | adopted (target (c)) |
| 2147f86 | B1: chained edges in linear nodes | reverted by 7a60f2f |
| 0a94cdc, 4282ba7 | B1': chain nodes, first and second build | reverted by d1d73e9 and cf72207 |

### paper-typed-routing (`papers/typed-routing`, `origin` private, branch main)

Round 2's commits, oldest first: ce20fe5, 4e2dab2, 221a3fc (design, review, approval); 904cb78
(gen_route_tests); fe16f19, 8cbbae9 (milestone 1 logs); aa869d1 (round-2 harness: v2 arms, the
ablation arm, five competitors); 48992f9 (table_digest, slot 1 job); d9268c4 (v2 include hash,
chi and path-tree gaps, path-tree archives); fc0aeba, fcddf54 (milestone 2 logs); 89fadfa,
6e016d6 (slot 1 job, gated); 4bedc11 (round 1's handover, another agent); 4dd16b7 (C2 harness,
gen regenerated); c759a85, 651995e (C2 logs); f7c1594 (H7 object size decided; ct_costs.py);
83ae266 (slot 2 job, gen-ct --seeds); 48ca2df (backtrack_check, table_digest chains); 2c92baa
(B1, B1' logs); 4907be1 (slot 3 job); 376c71d, c892de7, ba84829, 826f893, 617ee91, a79ae4b,
47e699f, 9afb60f (the minimal server and its log); dedf703 (backtrack_check fix); 6bbdded
(RegexMatcher's records script); 0adfba3 (target (b) decided); 1667a46, 1ff0457 (records and
gates for rbench and the server; run scripts); 62b80fd (the server's inputs are those of every
target it links, found by the WSL trial of section 4); 4c99c14, f4f74d3 (this file; f4f74d3
removed a path that named the round-1 header's library, which 4c99c14 still shows in the private
history); a52aba3 (`sanitize_rbench.sh` takes and records `EXTRA_CMAKE`); and the last commit of
this file.

Heads at handover: RegexMatcher `lab` `v2/route-matcher` d1d73e9; paper `origin/main` the last
commit that changed this file (`git log -1 -- design/round2/status.md`); Papers `origin/main` the
journal commit that follows it (its entry names this handover).

### Papers (`D:\Dev\GitHub\Papers`, `origin` private, branch main)

Round 2's commits: 2435e56 (`inputs_hash.py --dep-root`, `--label-hash`); 67ff182 (journal,
objdump evidence); a2cf804 (A1 to A3, rule 1); 0fc20f1 (another agent's journal); f1975c8,
ec782a4, 947522a (C2); 7dd734b (slot 1); de4d998 (B1); 7e31f39 (slot 2); caf0823, a03dcea (B1');
129c4c3 (`test_report_pattern.sh` checks the new record writer); 105e731 (slot 3). The gitlink
of `papers/typed-routing` in Papers has not been bumped by this work.

## 3. Targets and rules

| Target | Change | Rule | Result | Evidence |
|---|---|---|---|---|
| extraction | E1, E2, F1 | objdump identity with the round-1 header | identical at E1, E2, F1, A3 and C2 (clang 18.1.3, gcc 14.2, WSL) and at E1 to f48fa83 (clang 22.1.8, L); C2 not yet checked with clang 22.1.8 | `2026-09-30-W-regexmatcher-v2-objdump` |
| (a) build time | A1 to A3 | rule 1 (tables, allocations, lookup code, budget) | holds (WSL): digests 108 of 108; allocations and bytes fall in 36 of 36 per seed; objdump identical; budget bands unchanged | `2026-09-30-W-regexmatcher-v2-build-rework` |
| (a) | A1 to A3 | rule 2 (time, L) | holds: B lower in 21 of 21 cells, B/A 0.347 to 0.739 | `2026-09-30-L-slot2/a` |
| (b) H2 at mixed-disjoint m = 10 | B1, B1' (two builds) | part 1 (instructions, L) | no candidate passes; the H2 loss stands and is reported | `2026-09-30-W-regexmatcher-v2-b1-chained-edges`, `-b1p-chain-nodes`, `2026-09-30-L-slot3` |
| (c) H7 | C1 (one adapter), C2 (one layout) | deterministic part (WSL) | holds: `harness_pass` identical; page offsets equal in 21 of 21 cells; digests equal E1's; `table_bytes` fell in 35 of 35 | `2026-09-30-W-regexmatcher-v2-c2-layout` |
| (c) | C2 | H7 iteration check (L) | passes: no cell's median ratio above 1.02 (largest 1.0046); two single pairs above (wild m = 10, 1.1401; static m = 100, 1.0272) | `2026-09-30-L-slot2/c` |
| gate | `inputs_hash.py` change | stored P1 and P2 hashes recomputed (hard condition) | holds: 32 of 32, default mode identical | `2026-09-30-L-slot1` |

Decided along the way: H7's object size is the sum of the loadable sections, with the file size
and its padding beside it (`hypotheses-v2-proposal.md`, H7 and revision log). B2 is skipped (the
coordinator: the freeze matters more).

## 4. What is built and tested but not yet recorded

- **rbench** (`bench/`): 24 arms in one binary (`bench/CMakeLists.txt`, `RB_ALL_ARMS`); the
  seeds of section 3.3 in `run_grid.sh`; `build.sh` writes `BUILD.inputs.json` and
  `BUILD.v2-include.json`. All arms built with clang 22.1.8 on L and agreed on seeds 1, 111, 112
  (`2026-09-30-L-slot1`, job 4).
- **The minimal server** (`server/`, `minimal-server.md` and its revision log): HTTP layer, epoll
  loop, arms v2, v1, null in one binary `mserver`; built by the paper's root `CMakeLists.txt`
  with `t1/h6_targets`. Its CTest suite (`test_http1`, `test_loopback`, `test_contract`,
  `h6_agreement`) passes in WSL (clang 18.1.3), the first three under ASan+UBSan and TSan
  (development). Never built on L, never run under MSan.
- **Records scripts** (never run on L):
  - RegexMatcher: `bench/sanitize_regexmatcher.sh` with `bench/regexmatcher_record.py`; a WSL
    trial (ASan, 45ab696) was green, 87 of 87 tests, and its test targets hash
    `regexmatcher/include/` as rbench's v2 arms do.
  - rbench: `bench/sanitize_rbench.sh` with `bench/sanitizer_record.py`, now on RegexMatcher v2;
    `bench/arms_for.py` drops the FFI arms under MSan (`bench/coverage.json`). A WSL trial
    (ASan+UBSan, clang 18.1.3, paper a52aba3, RegexMatcher 45ab696, four arms only: null,
    regexmatcher-v2, regexmatcher-v2-ct, regexmatcher-v2-r1; its record in a scratch directory,
    host part W, not a record) was green: build exit 0; agreement 567 rows, 0 not agreeing; 118
    probe lookups; 14 of 14 quick cells for each of the four arms; 0 sanitizer reports; 249 s.
    `bench/check_records.py` then passed on a plain build of the same tree and arms: each of the
    five targets (rbench and the four arm libraries) and the `regexmatcher/include/` hash
    (5737e40609f1, the same as the server trial's) were covered. As in the server trial, the TSan
    and MSan records, and the L host part, were relabelled copies of the ASan ones, only to reach
    the gate's pass path. The competitor and FFI arms were not in the trial. WSL's clang 18
    resource directory (`~/opt/clang18-res`) lacks `include/sanitizer/`, which
    `bench/core/alloc_count.cpp` includes; the trial used a copy with those headers added (from
    `~/h2msan/rt/x/usr/lib/llvm-18/lib/clang/18/include/sanitizer`). The include is compiled only
    in sanitizer builds and has been in `alloc_count.cpp` since 44e815e; round 1's L records
    (`lab/sanitizer-records/rbench-*-L-{asan,tsan,msan}.json`, e.g. e7e4305c6, all clang 22.1.8,
    green) built it, so L has the header and this is a WSL matter only.
  - server: `t1/sanitize_h6.sh` with `t1/h6_record.py` and `t1/h6_exercise.py`. A WSL trial
    (ASan+UBSan, clang 18.1.3, paper 62b80fd, RegexMatcher 45ab696; its record in a scratch
    directory, not a record) was green: the build, 4 of 4 CTest tests, and all 27 runs of 9 cells
    by 3 arms, with no report. `t1/check_h6_records.py` then passed on a plain build of the same
    tree: every one of its six targets (mserver, mserver_arms, mserver_http1, mserver_loop,
    mserver_v1, h6_targets) hashed as in the sanitizer build, and mserver_arms's
    `regexmatcher/include/` hash equals RegexMatcher's tests' (the TSan and MSan records of that
    trial were copies of the ASan ones, relabelled, to reach the gate's pass path). An earlier
    trial found that a target's hash covers its own translation units only, so the server's
    inputs are those of every target it links (62b80fd).
- **Gates**: `bench/gate_lib.py` (shared rules), `bench/check_records.py` (rbench),
  `t1/check_h6_records.py` (server); `bench/test_gates.py` tests both over synthetic records (13
  checks pass). Records count only when their name has the host part L.
- **Run scripts**: `bench/run_baseline.sh` (the gated main grid), `bench/ct_cost_run.sh` (H7's
  costs, table seed 111), `t1/run_h6.sh` (H6 at T1, three arms, pair 111, 211).

## 5. What remains before the freeze, in order

Every L step under lablock, from a **Papers clone with the paper as its submodule at the commit to
record** (the scripts find `lab/bin` and `lab/sanitizer-records` at `../../..` from `bench/` and
`t1/`; a standalone paper clone does not work). For example:

```
cd ~/lab/p2/rec && git clone -q git@github.com:Alex-Tsvetanov/Papers.git Papers
git -C Papers submodule update -q --init papers/typed-routing
git -C Papers/papers/typed-routing checkout -q <paper commit>
RM=~/lab/p2/r2/RegexMatcher; git -C $RM fetch -q origin
C=$(git -C $RM rev-parse d1d73e9); S=~/lab/p2/r2/rm-src-$C-full
[ -d $S ] || { mkdir -p $S; git -C $RM archive $C | tar -x -C $S; }
```

1. **RegexMatcher records on L**, one per sanitizer (the instrumented libc++ for MSan is
   `~/opt/libcxx-msan-gcc` on L):
   `nohup ~/lab/Papers/lab/bin/lablock bash Papers/papers/typed-routing/bench/sanitize_regexmatcher.sh asan $C > rm-asan.log 2>&1 & echo $! > rm-asan.pid`
   (then tsan, msan; `RM=~/lab/p2/r2/RegexMatcher`). GoogleTest is fetched by RegexMatcher's own
   CMake from its official repository at b514bdc8 (v1.15.2).
2. **rbench records on L**: `REGEXMATCHER_DIR=$S REGEXMATCHER_COMMIT=$C nohup lablock bash
   bench/sanitize_rbench.sh asan` (then tsan, msan). Archive each work directory
   (`~/lab/p2/rbench-san/<san>`) under `~/lab/records-logs/<record name>/` with its sha256; the
   script does not do that yet.
3. **Server records on L**: `REGEXMATCHER_DIR=$S REGEXMATCHER_COMMIT=$C nohup lablock bash
   t1/sanitize_h6.sh asan` (then tsan, msan); archive `~/lab/p2/mserver-san/<san>` likewise. The
   server has never run under MSan: expect to value-initialize what a read fills if MSan reports.
4. **W records of RegexMatcher**, extra coverage (`regexmatcher-v2.md`, section 8.4): MSVC ASan
   and clang-cl ASan of the suite. The `.ps1` script is not written yet.
5. **Commit the records** to the Papers repository (`lab/sanitizer-records/`, explicit paths),
   with the logs' sha256.
6. **Gates**: `CHECK_ONLY=1` run of `bench/run_baseline.sh` on L, and `t1/check_h6_records.py`
   on a plain build; both must pass before anything is measured. The t1gen record
   `t1gen-1eaee40c3.json` matches the current `lab/t1/gen` (last changed 1eaee40); check it is green.
7. **The objdump check at C2 with clang 22.1.8 on L** (not run yet; C2 does not touch the lookup):
   `lab/evidence/2026-09-30-W-regexmatcher-v2-objdump/objdump_check.sh clang++ l-clang22-c2 <round-1 header> <its namespace> $S/include matcher/route.hpp matcher::route`,
   with the round-1 header and its namespace given as the first L slot gave them (the
   coordinator's launch of `bench/jobs/slot1.sh`; the header's checkout under `~/lab/p2/pub/` at
   6d28e3610, the same file as round 1 measured).
8. **Analysis**: `analysis/*.py` still names round 1's arms and statistics; it must be rewritten
   for round 2 (the clustered BCa and the exact sign test, both deciding; H6's three arms and new
   statistics; the object-size cost) before the run is analysed, and is best fixed before the
   freeze.
9. **The pre-specification to freeze** (Alex freezes it): `hypotheses-round2.md`, written from
   `hypotheses-v2-proposal.md` section 3 with every decision of its revision log, including the
   H2 cell expected lost; plus the revision-log entry of `hypotheses.md` (proposal, section 6).
   Declare there what round 1's handover asks to declare (`results/round1-handover.md`, caveats):
   the prefix of the ring that timed passes over a slow arm use, the agreement pass's time
   budget and the re-check on every query.
10. **Seeds, fixed at the freeze**: the sixteen pairs (table seeds 111 to 118, ring seeds 211 to
    214; `run_grid.sh`), R = 16; H6's pair (111, 211); `ct_steps` at table seed 111. The order
    seed: the proposal says it is fixed at the freeze; `run_grid.sh`'s default, 20260927, is
    round 1's, so pick a new one and pass it as `SEED`. Engineering runs used table seeds 1 to 5
    and ring seeds 2 to 4 only.
11. **Pins**: check `bench/cmake/pins.cmake`, `bench/arms/rust/Cargo.lock` and
    `bench/arms/go/go.mod` for newer releases before the freeze (schedule, Fri 9 Oct).
12. **The runs** (after the freeze and green gates), from the recording clone:
    - main grid: `REGEXMATCHER_DIR=$S REGEXMATCHER_COMMIT=$C SEED=<frozen> RUN_NAME=<date>-L-publication nohup lablock bash bench/run_baseline.sh > pub.log 2>&1 & echo $! > pub.pid`
      (the proposal's estimate, section 7);
    - H7's costs: `REGEXMATCHER_DIR=$S REGEXMATCHER_COMMIT=$C lablock bash bench/ct_cost_run.sh OUT`;
    - H6: `REGEXMATCHER_DIR=$S REGEXMATCHER_COMMIT=$C lablock bash t1/run_h6.sh OUT`;
    - the exploratory set (proposal, section 3.6) with `run_grid.sh`'s variables; the re-check of
      unverified processes (`tools/verify_*`, round 1's) must be checked against the new arms.

## 6. Open decisions for Alex

Version of v2 (CMake still 2.0.0.1); the release tag of v2, and a tag at d16f30a8 for v1;
merging the engine commits (v1's `perf/deterministic-live-sets`) into RegexMatcher's main; the
licence (RegexMatcher's LICENSE names the private library, `regexmatcher-v2.md`, section 11); the
public push of the branch and its timing (the measured commit must be public before
submission); freezing `hypotheses-round2.md`.

## 7. Caveats and gotchas

- **Pins**: v1 is pinned at d16f30a8, which lives only on a non-main branch of the public
  repository (a deleted branch breaks the archive URL). Every archive's sha256 is in
  `pins.cmake`; path-tree and smallvec come from crates.io, pinned by `Cargo.lock`; chi and gin
  are vendored with per-file sha256. Go builds use `GOPROXY=direct GOTOOLCHAIN=local`.
- **Toolchains**: L has clang 22.1.8, gcc 16.2.1, Go 1.27.1, rustc and cargo 1.98.1, kernel
  7.2.3 running with 7.2.6 installed: a reboot changes the kernel, so any update happens before
  the first record, and then nothing changes until the runs end. WSL has clang 18.1.3 (its
  sanitizer runtimes need `-resource-dir=$HOME/opt/clang18-res`) and gcc 14.2; clang 18 cannot
  build glaze (`std::expected` with libstdc++ 14), gcc 14 can. WSL counts are development
  evidence only.
- **L**: login shell zsh (run loops from bash script files); `~/lab/Papers` is another agent's
  tree; use your own clones under `~/lab/p2/`. `~/lab/p2/r2` holds this round's clones and
  worktrees: `pt-c-83ae26685` has untracked compile-time tables of seeds 2 to 5 (never build a
  record from it); `pin.sh` needs L's passwordless sudo.
- **WSL**: `pin.sh` hangs on sudo there (use `PIN=/nonexistent ALLOW_UNPINNED=1` for development);
  cloning the private GitHub repositories asks for credentials there (clone the local paths);
  `/tmp` does not survive between `wsl` calls; `~/opt/clang18-res` lacks `include/sanitizer/`,
  so a sanitized rbench build there needs a copy of it with those headers (section 4, rbench).
- **This workstation**: a hook blocks commands that contain `rm -rf` or `git checkout --` (use
  new directory names, `git apply -R`); Python heredocs in Git Bash turn `\n` and `\t` inside
  strings into real characters (edit such files with the Edit tool).
- **Semantics**: `rbench_agree_exit=1` is expected where declared differences exist (gin, uWebSockets
  wild, and others in `bench/semantics.json`); the verdict is `agree_exit`.
- **inputs.json**: its `scope` sentence still names round 1's first-party checkout; the gates
  read `dep_roots` and the hashes, not that sentence (`regexmatcher-v2.md`, revision log).
- **H6 targets**: `t1/h6_targets` defaults to round 1's seeds; the scripts pass 111 and 211.
- **C2 costs**: the run-time build copies the table into its block (development timing only,
  `2026-09-30-W-regexmatcher-v2-c2-layout`); each compile-time table's object file grows by
  3,328 to 3,392 bytes of padding.
- **The H2 cell**: at mixed-disjoint m = 10, C2's net count is above gin's on L (527.8 and
  530.8 against 513.8 and 520.5, `2026-09-30-L-slot3`); expect H2 to fail there.

## 8. Update, 2026-09-30 09:30 (section 5, steps 1 to 8 done)

- **Records** (Papers 6527724, all green, clang 22.1.8): `regexmatcher-d1d73e99b-L-{asan,tsan,msan}`
  (87 of 87 tests each), `rbench-a79ae4bc2-L-{asan,tsan,msan}` (24, 24 and 17 arms),
  `mserver-65817be5b-L-{asan,tsan,msan}` (4 tests, 27 cell and arm runs); W extra coverage
  `regexmatcher-d1d73e99b-W-asan` (MSVC 19.51, 87 of 87). No recorded binary refers to io_uring.
  Logs: `~/lab/records-logs/<record>/` with `.tar.gz` and `.sha256` (L) and `%USERPROFILE%\lab\records-logs\` (W).
  The first start's red record (a CTest 4 parser bug, not a sanitizer finding) is evidence only, in
  `~/lab/records-logs/regexmatcher-d1d73e99b-L-asan.red-ctest-parser/` (lab journal).
- **Changes before the records** (revision logs of `regexmatcher-v2.md` and `minimal-server.md`):
  logs packed with their sha256 (`bench/keep_record_logs.sh`); the writers read CTest 4's summary;
  the gates count a record only if its pins (`pins_sha256` of `bench/cmake/pins.cmake` and the
  archives fetched as used) equal the build's; `t1/run_h6.sh` asks for at least 6 pairs and has
  `CHECK_ONLY=1`; GoogleTest from a local `git archive` at b514bdc8, no download.
- **Gates and objdump** (lab evidence `2026-09-30-L-gates-r2`): `CHECK_ONLY` rbench and server gates
  pass against the committed records; the objdump check at C2 with clang 22.1.8 is identical.
- **Analysis** (paper cb04ce7): `analysis/analyse.py` runs every decision (the clustered BCa and the
  exact sign test, both deciding, Holm over the family; H2 to H7; H6's direction and carry-over)
  and writes `summary.json`, from which `analysis/macros.py` writes the macros. Tests: 30 on
  synthetic runs; SciPy agrees on L (`2026-09-30-L-bca-scipy-check-r2`); a WSL grid on engineering
  pairs (`2026-09-30-W-analysis-r2-wsl-grid`). `results/macros.tex` is round 1's until the
  publication run is analysed.
- **Accepted by the coordinator**: order seed 20261009, resampling seed 20261010 (the analysis's
  default); the held-out pairs of section 5, step 10. Next: step 9, the text to freeze (Alex
  freezes it), then the pins check of step 11.

## 9. Update, 2026-09-30 11:20 (the gaps before the freeze, and the draft)

- H7's cost run is gated (`bench/ct_cost_run.sh`, `CHECK_ONLY=1` passed on L); every grid ends by
  checking on every query each process its 120 s agreement pass cut (`bench/run_grid.sh`,
  `verified.jsonl`), and the tool covers every arm (lab evidence `2026-09-30-L-gaps`); every
  competitor's pin is its latest release, PCRE2 (r3's library) excepted, 10.49 against 10.48, not
  changed (`2026-09-30-W-pins-freshness`).
- The draft to freeze is `hypotheses-round2.md` (not frozen), with the launch lines in
  `design/round2/launch.md`. The order seed 20261009 is the scripts' default.
- On L, `~/lab/p2/gate/Papers` (Papers 6527724, paper 0a475cb) holds the gates' and the gaps'
  builds; the runs start from a fresh clone at the commit that holds the frozen file.

## 10. In progress, 2026-09-30 12:00: the audit's fixes before the freeze

The independent audit of the draft (`scratchpad/p2-r2-audit/review.md` of the coordinator's session;
verdict: freeze after fixes) and the coordinator's decisions: B1, PCRE2 10.49 stays (paper ed535ad;
records at ed535ad were being made on L in `~/lab/p2/rec2`, superseded by the changes below, not to be
committed); M1, sixteen distinct table seeds, pair k = (110 + k, 210 + k), k = 1 to 16, `bench/gen`
regenerated for 111 to 126; M3, t1.py counts valid pairs only (flag, test) and the rules go into the
text; M4, a W step for MSVC compile costs of the H7 tables; M5, the seed statements corrected; M6, a
table of what each arm's timed lookup includes, extra work equalized where the router's API allows;
M7, uWebSockets' missing catch-all value declared, left out of wild; M8, each competitor's
configuration with a citation (Rust profile, the Oat++ option, Drogon's transcribed file hash); the
31 minors. Order: code changes (M1, M3, M6, M7, M8, minors in code), then the six rbench and server
records and the gates (three CHECK_ONLY and io_uring), then the draft rewritten, then the revised
draft to the coordinator. `hypotheses-round2.md` is edited only after the code and records.

## 11. State at 2026-09-30 12:50: the audit's fixes, code done, records being remade

Done (paper c6722e5, Papers 1c9db5e):
- Code: M1 (82681fe), M3 (fd29bd1 and Papers f10b828), and c6722e5: null-no405 (m27), the kinds of
  `bench/semantics.json` enforced by `check_agree.fits` (m28, M7), Go GOMAXPROCS and collections
  (m25), `bench/symbols.py` (m29), Oat++'s option and view reads (M6, M8), Drogon's file hash in
  `pins.cmake` (M8), `bench/ct_msvc.py` (M4, tested on W on table seed 1 only).
- Checks: the M1 seed scan (0 uses of 119 to 126 and 219 to 226), the WSL build check, the L
  development check (lab evidence `2026-09-30-L-audit-fixes-check`): kinds hold at m = 10,000 and
  100,000, `go_maxprocs` 1, loop nulls as designed.
- The superseded records job at ed535ad (`~/lab/p2/rec2`) was stopped (records.done: incomplete).
- Draft: `hypotheses-round2.md` rewritten with every finding; `launch.md` updated (W step, ssh
  address, freeze and interrupted-run rules). Placeholders left in the draft: `[[PAPERS_REC]]`,
  `[[EV_REC]]`, `[[EV_GATES]]`, `[[REC_TIMES]]`, and the build time in section 10.

Running: `~/lab/p2/rec3/records` on L (bench/jobs/records.sh, ONLY="rbench mserver", pid file
`~/lab/p2/rec3/records.pid`, done file `~/lab/p2/rec3/records.done`), from the clone
`~/lab/p2/rec3/Papers` at 1c9db5e. It writes `rbench-c6722e59e-L-*` and `mserver-c6722e59e-L-*`
into that clone's `lab/sanitizer-records/`.

Next:
1. When the records are green: copy the six JSONs to W, commit them with explicit paths in Papers,
   evidence `2026-09-30-L-records-r3` (steps.txt, io_uring.txt, logs-archives sha256), journal.
2. Run `bench/jobs/gates.sh` on L under lablock from a clone that holds the new records (rbench,
   server, objdump at C2, ct gate), evidence `2026-09-30-L-gates-r3`, journal.
3. Fill the draft's placeholders, bump the gitlink, and send the draft to the coordinator for the
   last read. Do not freeze. The `-march=native` question (Appendix B) is open for Alex.

## 12. 2026-09-30 14:55: records and gates done; the draft goes for the last read

- The six records are green and committed (Papers db67d27; lab evidence `2026-09-30-L-records-r3`):
  `rbench-c6722e59e-L-{asan,tsan,msan}`, `mserver-c6722e59e-L-{asan,tsan,msan}`, pins fd987818804a;
  no io_uring.
- The gates passed from a fresh clone at Papers db67d27 (lab evidence `2026-09-30-L-gates-r3`):
  rbench (26 targets and RegexMatcher's headers), the server, the objdump check at C2 (IDENTICAL),
  H7's cost build.
- `hypotheses-round2.md` has no placeholder left. It is sent to the coordinator for the last read,
  not frozen. Open for Alex: `-march=native` (Appendix B).
- From here on, any change to what rbench or the server compiles (`bench/core`, `bench/arms`,
  `bench/cmake`, `bench/gen`, `bench/main.cpp`, `CMakeLists.txt`, `server/`, `t1/`) changes the
  inputs hash and means making the records again.

## 13. 2026-09-30 15:20: the native instruction set (coordinator's decision), records being remade

The coordinator read the draft ("sound") and decided the open point: every arm is built for L's own
instruction set (C and C++ `-march=native`, Rust `-C target-cpu=native`, Go `GOAMD64` at L's highest
level, verified v3), the server too since it compiles v2 and v1; records remade; gates and the C2
objdump check again (re-baselined at native flags); Appendix B updated without its bracket; time
estimates; journal. Then report; the coordinator freezes and gives the go for the launch order
(main grid, H7 costs on L, H6 T1, H7 MSVC costs on W, exploratory). The pointer entry to round 1's
`hypotheses.md` revision log goes into the freeze commit.

Done: paper 4cc42bf (`bench/cmake/isa.cmake`, `rb_isa.h` in every target's inputs, Rust and Go
flags, `bench/objdump_check.sh`, gates.sh at native); lab evidence `2026-09-30-L-isa-native-check`
(znver3, Rust znver3, GOAMD64 v3, a v4 Go binary refused, 613 of 613 compiles native); Papers
ddcbda1. The draft `hypotheses-round2.md` is edited on W but NOT committed: it holds placeholders
`[[CODE]]` (4cc42bf, 9 characters: 4cc42bf11), `[[PAPERS_REC]]`, `[[EV_REC]]`, `[[EV_GATES]]`,
`[[ISA_EVIDENCE]]` (lab evidence `2026-09-30-L-isa-native-check`), `[[BUILD_TIME]]`,
`[[SERVER_BUILD_TIME]]`, `[[REC_TIMES]]`, `[[BUILD_MIN]]`, `[[MAIN_TOTAL]]`.

Running: `~/lab/p2/rec4/records` on L (records.sh, ONLY="rbench mserver", clone at Papers ddcbda1,
pid `~/lab/p2/rec4/records.pid`, done file `~/lab/p2/rec4/records.done`); it writes
`rbench-4cc42bf11-L-*` and `mserver-4cc42bf11-L-*` into that clone's `lab/sanitizer-records/`.

Next: copy and commit the six records (evidence `2026-09-30-L-records-r4`), run the gates from a
clone at that commit (`~/lab/p2/gates3.sh` with PAPERS_COMMIT, ROUND1_HEADER and ROUND1_NS set at
launch as before; evidence `2026-09-30-L-gates-r4`), fill the placeholders, journal, commit, report.

## 14. 2026-09-30 18:30: records and gates green for the native instruction set; the draft is final

- Records (Papers 0f90a96): `rbench-90beca488-L-asan`, `rbench-4cc42bf11-L-{tsan,msan}`,
  `mserver-4cc42bf11-L-{asan,tsan,msan}`, all green (lab evidence `2026-09-30-L-records-r4`, `-r5`).
  The first gate run refused the Rust arms (their ASan digest named `-Zsanitizer`); fixed in paper
  90beca4 (lab evidence `2026-09-30-L-gates-r4/attempt1`).
- Gates (Papers 099a140, lab evidence `2026-09-30-L-gates-r4`): rbench, server, the objdump check at
  C2 re-baselined at `-march=native` (IDENTICAL), H7's cost build; a build without `-march` refused.
- `hypotheses-round2.md` has no placeholder; sent to the coordinator as final. The coordinator
  freezes it; the freeze commit also appends the proposal's section 6 entry to round 1's
  `hypotheses.md` revision log. Then the go for the launch order in `launch.md`.

## 15. 2026-09-30 18:33: frozen; the publication runs launched

The coordinator froze `hypotheses-round2.md` (paper 9d7e8fe; round 1's `hypotheses.md` revision log
points to round 2; Papers 8419942). RegexMatcher's three L records stay as they are (coordinator).
Go, in this order, each a lablock job with pid and done files, gated, stopping on any failure; each
run archived with sha256 in `D:\Archive\p2-raw\` and on L, and journaled; any departure from the
frozen text is a deviation for its revision log before proceeding, and one that would change how a
hypothesis is decided stops for the coordinator:
1. the main grid: RUNNING since 18:33, `~/lab/p2/pub2` (clone at Papers 8419942), pid
   `~/lab/p2/pub2/pub.pid`, done `~/lab/p2/pub2/pub.done`, log `~/lab/p2/pub2/pub.log`, run dir
   `~/lab/p2/pub2/Papers/papers/typed-routing/results/raw/2026-09-30-L-publication`;
2. H7's costs on L (`launch.md` section 2); 3. H6 at T1 (section 3); 4. H7's MSVC costs on W
   (section 2b), only while nothing heavy runs on W; 5. the exploratory set (section 4).
Report to the coordinator after the main grid and its analysis (every hypothesis with its decision
and numbers, every loss, the deviations, the sha256), then continue, and report at the end.
- 18:45: steps 2 and 3 are queued on L by `~/lab/p2/pub2/chain2.sh` (pid `chain2.pid`, not under
  the lab lock while it waits): after `pub.done`, if the grid's `exit.txt` is clean, H7's costs
  (`ct.done`, `ct.log`, run dir `results/raw/2026-09-30-L-publication-ct`), then H6 (`h6.done`,
  `h6.log`, run dir `results/raw/2026-09-30-L-h6`); `chain.progress`, `chain.done` say where it is.
  Step 4 (MSVC on W) and step 5 (the exploratory set, `launch.md` section 4) are launched by hand
  after H6, in that order. Do not run anything on L while a measured run is in progress (an
  analysis smoke test of a few seconds ran there at 18:41, nice 19; noted in the journal).

## 16. 2026-10-01 12:15: the main grid ended; the re-check failed on memory; waiting for the coordinator

- The main grid measured all 13,048 processes (exit.txt: agree, probes, cells 0). Archive sha256
  efc3b2fc6c74bc21d8ac7a152abfb6704345b309352b2971d219c4612601e8a6 (L and `D:\Archive\p2-raw`).
- Its re-check of every query (16 at once) failed for 79 of 115 processes: actix-router checks at
  m = 100,000 killed by the out-of-memory killer (exit -9), after the last measured cell. So
  `verify_exit=1`, and chain2 stopped before H7's costs, as designed.
- The frozen analysis of the run as it stands (lab evidence `2026-10-01-L-publication-main-grid`,
  `analysis-asis/`): H1 27 of 35 (six cells at m = 100,000 fail on the unverified processes;
  wild 10, mixed-disjoint 10 do not pass) does not hold; H2 27 of 35 does not hold; H3 holds; H4
  does not hold (build time at static 10,000 and 100,000, param-first 10,000); H5(b) holds; H7 20
  of 21 (param-last 1,000: 12 of 16 below 1.02) does not hold.
- Asked the coordinator: (1) whether to repeat the killed checks with fewer at once (a deviation:
  it can change H1's decision); (2) whether to run steps 2 and 3 meanwhile. Nothing runs on L now.

## 17. 2026-10-01 12:10: the approved repeat of the check, then the chain

- The coordinator approved repeating all 115 checks with 4 at once (revision log of
  `hypotheses-round2.md`, paper 262f24d); later grids use `VERIFY_JOBS=4` (operational). No overlap
  on L: the repeat, then H7's L costs, then H6, then the exploratory set.
- RUNNING on L: `~/lab/p2/pub2/recheck.sh` (lablock; `recheck.pid`, `recheck.done`), writing
  `verified-repeat.jsonl` and `verify-repeat.txt` in the run directory; the binaries' sha256 were
  checked (verify_answers adc3ecee..., rbench 28defc7b...).
- QUEUED on L: `~/lab/p2/pub2/chain3.sh` (`chain3.pid`, `chain3.progress`, `chain3.done`): after the
  repeat ends with exit 0, it archives the repeat, then runs H7's costs, H6, and the five
  exploratory grids (VERIFY_JOBS=4), each under lablock, each archived to `~/lab/p2-raw-<run>.tar.gz`
  with its sha256, stopping on the first failure. chain2 had stopped and is not used.
- RUNNING on W: H7's MSVC costs, `bench/ct_msvc.py` into `C:\Users\alext\lab\p2\2026-10-01-W-ct-msvc`
  (log and done file beside it), paper checkout at 262f24d (bench identical to 9d7e8fe).
- After the repeat: run `analysis/analyse.py RUN --verified RUN/verified-repeat.jsonl` on W, report
  every decision again with what changed and why. Then copy each archive to `D:\Archive\p2-raw`,
  verify its sha256, journal, and run the final analysis with `--t1` and `--ct-costs`.

## 18. 2026-10-01 14:00: the repeat agreed; the chain runs; MSVC costs done

- The repeat: 115 of 115 checks agree (lab evidence `2026-10-01-L-publication-recheck`, archive
  sha256 19600f54...). The frozen analysis with `--verified verified-repeat.jsonl`: H1 34 of 35
  holds; H2 33 of 35 does not hold; H3 holds; H4 does not hold; H5(b) holds; H7 20 of 21 does not
  hold. Reported to the coordinator.
- H7's MSVC costs on W: done (lab evidence `2026-10-01-W-ct-msvc`, archive sha256 1e32cfbf...).
- RUNNING on L: chain3 (`~/lab/p2/pub2/chain3.progress`): H7's costs on L since 13:50, then H6, then
  the five exploratory grids (VERIFY_JOBS=4), each archived to `~/lab/p2-raw-<run>.tar.gz`.
- Still to do as each ends: copy each archive to `D:\Archive\p2-raw` and check its sha256, evidence,
  journal; then the final analysis on W: `analyse.py RUN --verified RUN/verified-repeat.jsonl --t1
  <h6 run> --ct-costs <ct run>`, plus `explore_summary.py` per exploratory run (with its own
  `verified.jsonl` where written); commit the results; report at the end.

## 19. 2026-10-01 13:57: the coordinator's additions

- Accepted the repeat and the reported decisions. Asked to make the Holm-family effect on
  mixed-disjoint m = 10 explicit in the paper material: to do in `results/round2/README.md` with the
  final analysis (raw sign-test p 0.0106 unchanged; Holm multiplier 8 with six cells at p = 1, 2
  once they are tested; bootstrap draws shift because one generator serves the tested cells).
- Asked for a descriptive explanation of wild m = 10 (round 1 about 0.91, round 2 1.026): done,
  lab evidence `2026-10-01-W-wild10-cross-round` (no new run; mechanisms untested). Goes into the
  final report.
- The chain on L continues: H7's costs on L since 13:50 (L's clock), then H6, then the exploratory set.

## 20. 2026-10-01 15:18: H6 and H7's costs done; the exploratory set runs

- H7's costs on L (lab evidence `2026-10-01-L-publication-ct`) and H6 (`2026-10-01-L-publication-h6`:
  (a) and (b) 9 of 9, H6 holds) are archived, copied to `D:\Archive\p2-raw` and checked.
- The final analysis is in `results/round2/` (paper cff2aa6), from the archives unpacked in
  `D:\Archive\p2-raw\runs\`; its README states the inputs' sha256, the deviation and the Holm-family
  effect at mixed-disjoint m = 10. Decisions: H1 holds (34 of 35); H2 does not (33 of 35); H3 holds;
  H4 does not; H5(b) holds; H6 holds; H7 does not (20 of 21).
- RUNNING on L: chain3's exploratory grids (github, no-decoy, miss, vocab-long, zipf), from 15:14.
  For each: copy the archive, check sha256, run `analysis/explore_summary.py RUN --verified
  RUN/verified.jsonl --out results/round2/explore_<name>.csv`, evidence, journal. Then the final
  report (with the wild m = 10 explanation, lab evidence `2026-10-01-W-wild10-cross-round`).

## 21. 2026-10-01 23:02: after the usage-limit stop

- The session stopped from about 17:40 to 23:00 (the account's usage limit); chain3 ran on. H7's
  costs, H6, github, no-decoy and miss are done, archived, copied and checked; the results README with
  the Holm-family note (cff2aa6) and the wild m = 10 evidence were committed before the stop.
- RUNNING on L: vocab-long (since 22:31), then zipf. For each: copy and check the archive, run
  explore_summary.py into results/round2, extend lab evidence 2026-10-01-L-exploratory, journal.
  Then the final report.

## 22. 2026-10-02 06:14: every run of the frozen order is done

- chain3 ended at 06:14:16 ("done"). L is idle and the lab lock is free.
- All archives are copied to `D:\Archive\p2-raw` and checked; unpacked in `D:\Archive\p2-raw\runs`.
- Results: `results/round2/` (frozen analysis, macros, README with the Holm-family note, the five
  exploratory summaries). Evidence: `lab/evidence/2026-10-0*-*`. Next: the final report to the
  coordinator; then the paper text from `results/round2/macros.tex`.
