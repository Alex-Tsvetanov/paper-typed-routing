# Provenance of the cited commits

The public history of this repository starts at the root commit
`f626955ebd94398a1376af4d48d61ee7a9ca9f6c`. The work before it was done in an earlier history of
this repository, which is archived privately. The paper, `results/round2/` (`macros.tex`,
`macros-paper.tex`, `summary.json` and the README), `hypotheses-round2.md`, the design notes, the
analysis and the sanitizer records cite commits of that earlier history. This file maps each of
them to this history. Checked on 2026-10-08.

## The measured code

Every measured build was made in a checkout of the earlier history. Each run records the commit
it was built at (its repository head). The code commit, the last commit that changed the compiled
sources of the program, is named by the run or by its sanitizer records.

| Run | Built at | Code commit | Cited as |
|---|---|---|---|
| main grid (H1 to H4, H5(b) and H7), its repeated check, and the five exploratory runs | `9d7e8fe` | rbench `90beca488d68d29bf98aa16bce415c3b02892785` | `\RbenchCommit`, `\RbenchCommitFull`; `summary.json`, `provenance` |
| H7's costs on L (clang) | `9d7e8fe` | rbench `90beca488` | `ct-provenance.txt` of the run |
| H6 at T1 (the minimal server) | `9d7e8fe` | the server `4cc42bf11ace589f29de6194142c1d8cb7dfd062` | `\ServerCommit`; the server's records |
| H7's heap-block follow-up (exploratory) | `35554b313301727d642280524a0a05e343126744` | rbench `35554b3` | `results/round2/README.md`; `hypotheses-round2.md`, revision log |
| H7's MSVC costs on W | `262f24d` | (no record; bench/ as at `9d7e8fe`) | the run's evidence in the Papers repository |

`9d7e8fe0a510514225b3235a515bba1837972a95` is also the commit that froze `hypotheses-round2.md`
(`\PreSpecCommit`; below). All of them map to the root commit
`f626955ebd94398a1376af4d48d61ee7a9ca9f6c`: what the measured builds compiled is byte-identical
there. The paper names the root commit beside the measured ones (`\RbenchPublicCommitFull` and
`\ServerPublicCommit` in `results/round2/macros-paper.tex`, through `PUBLIC_COMMIT` in
`analysis/paper_macros.py`, which stops on a measured commit it does not list).

### Same files

Git names each file and directory by a hash of its content. These names are the same at the
measured commits and at the root commit:

| Path | Type | Git object id at `4cc42bf11`, `90beca488`, `9d7e8fe`, `35554b3` and the root |
|---|---|---|
| `CMakeLists.txt` | blob | `5be030d64d5b` |
| `bench/main.cpp` | blob | `9d15a3a74244` |
| `bench/core` | tree | `06d644140280` |
| `bench/gen` | tree | `da41b49f54eb` |
| `bench/coverage.json` | blob | `489768d249f3` |
| `bench/semantics.json` | blob | `214325eeb1c5` |
| `bench/cmake/isa.cmake` | blob | `f09ff2a9b3ab` |
| `server` | tree | `09ddb5866814` |
| `t1` | tree | `757a166e6b75` |
| `tools` | tree | `854e1aebdcdc` |

To check a commit of this history: `git rev-parse <commit>:bench/core`, and so on for each path.

These paths differ between a measured commit and the root. None of them is compiled into a
measured target. The list is the output of this command, for each measured commit:

    git diff --name-status <commit> f626955 -- bench server t1 tools CMakeLists.txt

| Path | Changed by | Why the measured builds compile the same files |
|---|---|---|
| `bench/arms/regexmatcher_v2_ct_heap.cpp`, `bench/cmake/arm-regexmatcher-v2-ct-heap.cmake` | `35554b3` (added) | the exploratory arm `regexmatcher-v2-ct-heap`, compiled only into its own target `arm_regexmatcher_v2_ct_heap`, which no build has unless `RB_ARMS` names it |
| `bench/CMakeLists.txt` | `35554b3` | adds `RB_OPT_IN_ARMS` (that arm) and accepts it in `RB_ARMS`; the default arm list `RB_ALL_ARMS` and the build of every other arm are unchanged |
| `bench/build.sh`, `bench/run_baseline.sh` | `35554b3` | scripts: hash the new arm's RegexMatcher headers, pass `RB_ARMS` to the build |
| `bench/cmake/pins.cmake` | `4c7727c` | the pin of RegexMatcher v2, used only when no `REGEXMATCHER_DIR` is given (Pins, below) |
| `bench/data/LICENSE-cpp-httplib`, `bench/data/LICENSE-drogon` | `fd52f0b` (added) | licence texts |
| `bench/cmake/ffi-rust.cmake` (from `4cc42bf11` only) | `90beca488` | the Rust arms' build; the server does not compile them |

Between `35554b3` and the root only `bench/cmake/pins.cmake` and the two licence texts differ; the
tree `bench/arms` is `3585ee61461a` at both.

### Same inputs hashes

Each run and each sanitizer record states an inputs hash per build target: the sha256 of the text
made of one line `<path>\t<sha256 of the file>\n` per first-party file the target compiled,
sorted by path, RegexMatcher's files under the label `regexmatcher/` (the Papers repository's
`lab/bin/inputs_hash.py`, which `bench/build.sh` and `t1/sanitize_h6.sh` call). It includes the
generated `rb_isa.h`, so it also fixes the instruction set.

Every target that a measured build compiled has one inputs hash, the same in the measured run's
`inputs.json`, in the records that gated it, in the records named for the root commit and in the
gate builds of this tree (below). The table gives the first 12 hexadecimal digits; the full values
are equal. "Measured in" names the runs whose `inputs.json` holds the target: the main grid (its
build also served the exploratory runs), the heap-block run, the H6 run and H7's costs on L. The
other columns count the records of each set, and the gate builds, that name the target.

| Target | Inputs hash | Measured in | Old records | New records | Gate builds |
|---|---|---|---|---|---|
| `arm_actix_router` | `24bebe5f3cf8` | main grid, heap-block run | 2 | 2 | 2 |
| `arm_boost_url` | `bbda11ee59d2` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_chi` | `f82be386c215` | main grid, heap-block run | 2 | 2 | 2 |
| `arm_cpp_httplib` | `041aaa89b466` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_crow` | `6580d5eb5b43` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_drogon` | `b083c7e2425c` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_gin` | `16a13ec27e84` | main grid, heap-block run | 2 | 2 | 2 |
| `arm_glaze` | `b362d9622c12` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_hash` | `b84d110ed58d` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_httprouter` | `4dfa375b6868` | main grid, heap-block run | 2 | 2 | 2 |
| `arm_matchit` | `ec15686f5701` | main grid, heap-block run | 2 | 2 | 2 |
| `arm_nethttp` | `fb5c95ed7b5d` | main grid, heap-block run | 2 | 2 | 2 |
| `arm_null` | `c28863960f80` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_null_no405` | `dcccadc0b390` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_oatpp` | `3ca1255281b0` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_path_tree` | `ef592e172914` | main grid, heap-block run | 2 | 2 | 2 |
| `arm_pistache` | `bf527a09466b` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_r3` | `0d19bf007750` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_radix` | `0b10bfc29d3f` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_regexmatcher_v1` | `ba9717f321bb` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_regexmatcher_v2` | `40659420a207` | main grid, heap-block run | 6 | 6 | 2 |
| `arm_regexmatcher_v2_ct` | `68ffd39f47f8` | main grid, heap-block run, H7 costs (clang) | 6 | 6 | 3 |
| `arm_regexmatcher_v2_ct_heap` | `857126bcff1b` | heap-block run | 3 | 3 | 1 |
| `arm_regexmatcher_v2_r1` | `edf8f2f51a39` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_std_regex` | `f9f01d0b3baa` | main grid, heap-block run | 3 | 3 | 2 |
| `arm_uwebsockets` | `5c8b92353357` | main grid, heap-block run | 3 | 3 | 2 |
| `h6_targets` | `f8149ba8f4d0` | H6 run | 3 | 3 | 1 |
| `mserver` | `fbebb0e050a0` | H6 run | 3 | 3 | 1 |
| `mserver_arms` | `f329db787dd7` | H6 run | 3 | 3 | 1 |
| `mserver_http1` | `e87addc7ec46` | H6 run | 3 | 3 | 1 |
| `mserver_loop` | `0b0a2ef3b075` | H6 run | 3 | 3 | 1 |
| `mserver_v1` | `5d6f89d967b0` | H6 run | 3 | 3 | 1 |
| `rbench` | `39b25d41d9e6` | main grid, heap-block run | 6 | 6 | 2 |

The full comparison, of every target in every source, is the Papers repository's
`lab/evidence/2026-10-08-L-p2-public-records/compare.txt`.

### Pins

The sanitizer gates (`bench/gate_lib.py`) accept a record only if it was made with the build's
`bench/cmake/pins.cmake` (its sha256, CRLF read as LF) and the same fetched archives. Every
measured run of round 2, and the 16 records made for its final pins (those below among them),
used the file whose sha256 is
`fd987818804ada347ef5ef74977909412e0775cd698e510b51a86631885d15fc`. `\PinsSha`, from
`summary.json`, keeps that value: it names the pin file of the runs. Commit `4c7727c` of the earlier
history then pinned RegexMatcher v2 at its measured commit, `d1d73e99b`, held by its release
2.1.0.0. The file at the root has sha256
`51dd14076cb4633e155e6446c55fa5e79a0cbf95d6783c91d7484b5af36ad665`. The change sets
`RB_REGEXMATCHER_V2_COMMIT` and `RB_REGEXMATCHER_V2_SHA256` (they were empty) and rewords their
comment; nothing else in the file changed (7 lines in and 5 out, all in that block, from
`git diff 90beca488 f626955 -- bench/cmake/pins.cmake`). `bench/cmake/regexmatcher-v2.cmake`
uses them only when no `REGEXMATCHER_DIR` is given. Every measured build, and every record of
rbench and of the server, old and new, gave `REGEXMATCHER_DIR`, a `git archive` snapshot of
`d1d73e99b` (on L, `~/lab/p2/r2/rm-src-d1d73e99b7b26f54ba75354f4880780ece32e8ed-full`), so no
compiled file changed.

Under the pin rule, the 16 records made with the earlier file no longer cover a build of this
tree. The records named for the root commit, below, were made with the root's file, so the gates
pass on this tree. No reported number changes.

### Sanitizer records

The measured builds were gated by these records, kept in the author's laboratory repository
(Papers, `lab/sanitizer-records/`, not public). Each is green with 0 sanitizer reports, Clang
22.1.8 on L, pins `fd987818804a`. A record covers a build when it names the same inputs hash per
target, compiler, configuration, pins and fetched archives, whatever its commit.

| Record | Covers |
|---|---|
| `rbench-90beca488-L-asan` | rbench and its 25 arms, ASan and UBSan |
| `rbench-4cc42bf11-L-tsan` | rbench and its 25 arms, TSan |
| `rbench-4cc42bf11-L-msan` | rbench and 18 arms, MSan (the seven FFI arms are the gap `bench/coverage.json` declares) |
| `rbench-35554b313-L-{asan,tsan,msan}-ctheap` | rbench and the three v2 arms with `regexmatcher-v2-ct-heap` |
| `mserver-4cc42bf11-L-{asan,tsan,msan}` | the minimal server, its tests and the H6 exercise, and `h6_targets` |
| `regexmatcher-d1d73e99b-L-{asan,tsan,msan}` | RegexMatcher's suite at `d1d73e99b`; matched by its headers (`5737e40609f1`) |

`rbench-4cc42bf11-L-asan` and the records named for `c6722e59e` and `65817be5b` were made before
these and superseded by them. The records of RegexMatcher, the three on L and
`regexmatcher-d1d73e99b-W-asan` (MSVC on W, extra coverage that gates nothing), are named for
RegexMatcher's commit `d1d73e99b`, carry no pins and do not depend on this repository's history.

#### Records named for this history

These records were made on 2026-10-08 on L for this history. They are named for its code commit,
the root commit `f626955ebd94398a1376af4d48d61ee7a9ca9f6c` (`f626955eb`), as
`bench/sanitize_rbench.sh` and `t1/sanitize_h6.sh` name a record (the last commit that changed
the program's sources). They were made from a clone of this history at the root commit, with
`bench/jobs/records.sh` (`ONLY="rbench mserver"`) and `bench/sanitize_rbench.sh` for the opt-in
arm (`TAG=ctheap`), RegexMatcher from the same snapshot of `d1d73e99b`, under the lab lock at nice
0. Each is green with 0 sanitizer reports, Clang 22.1.8, and pins `51dd14076cb4` (the root's
`pins.cmake`). Each names the inputs hashes of the table above, and every other field of each
equals that of the record of the same kind made for the measured build (`rbench-90beca488-L-asan`,
`rbench-4cc42bf11-L-tsan`, `rbench-4cc42bf11-L-msan`, `rbench-35554b313-L-*-ctheap`,
`mserver-4cc42bf11-L-*`), except the commit, the repository head, the date, the time, the logs and
the pins. The steps of each (build, agreement test, probes, quick cells, the server's tests and
H6 exercise) have the same statuses as there. L ran kernel 7.2.6 on 2026-10-08 (7.2.3 at the
runs);
the records name the compiler, not the kernel. The logs of each are in `~/lab/records-logs/` on L,
with the sha256 of their archive in the record. No binary of these records links liburing or
refers to io_uring.

| Record | Sanitizer | Covers | Time (s) |
|---|---|---|---|
| `rbench-f626955eb-L-asan` | ASan and UBSan | rbench and its 25 arms | 1,581 |
| `rbench-f626955eb-L-tsan` | TSan | rbench and its 25 arms | 2,258 |
| `rbench-f626955eb-L-msan` | MSan | rbench and 18 arms (the declared gap of the seven FFI arms) | 2,822 |
| `rbench-f626955eb-L-asan-ctheap` | ASan and UBSan | rbench and the three v2 arms with `regexmatcher-v2-ct-heap` | 381 |
| `rbench-f626955eb-L-tsan-ctheap` | TSan | the same | 384 |
| `rbench-f626955eb-L-msan-ctheap` | MSan | the same | 315 |
| `mserver-f626955eb-L-asan` | ASan and UBSan | the minimal server, its tests, the H6 exercise, `h6_targets` | 83 |
| `mserver-f626955eb-L-tsan` | TSan | the same | 121 |
| `mserver-f626955eb-L-msan` | MSan | the same | 159 |

The paper's records on W are RegexMatcher's (`regexmatcher-d1d73e99b-W-asan`, extra coverage that
gates nothing); no record of this repository's code is made on W, so none is named for the root
commit there.

### The gates on this tree

On 2026-10-08, after the records above, in the same clone of the root commit on L, each
measured build was made again and gated (`CHECK_ONLY=1`, nothing measured), against the records
of the Papers repository with the nine above added:

- rbench with every arm (`bench/run_baseline.sh`, the main grid's build): gate passed;
- rbench with every arm and `regexmatcher-v2-ct-heap` (the heap-block run's build): gate passed;
- the server and `h6_targets` (`t1/run_h6.sh`, the H6 run's build): gate passed;
- the compile-time arm of H7's costs (`bench/ct_cost_run.sh`): gate passed.

In each, every target was covered by the records named for the root commit (the seven FFI arms by
ASan and TSan, MSan being their declared gap), RegexMatcher's headers (`5737e40609f1`) by its three
records on L, and none by a record made with the earlier `pins.cmake`. Each build's inputs hashes
are those of the table above. The logs are in `lab/evidence/2026-10-08-L-p2-public-records/` of
the Papers repository.

## The pre-specification: `9d7e8fe`

`9d7e8fe0a510514225b3235a515bba1837972a95` froze `hypotheses-round2.md` on 2026-09-30, before the
run (`\PreSpecCommit`). It is in the earlier history only. The file there, blob
`e7d05278f9169700cf07dce3afcd53b3d2baacf0` (57,466 bytes), is a byte prefix of the file at the
root, blob `63638f99cf0dea7e2d19e6628555e7d558b49a4a` (61,161 bytes). The 41 lines after it are the
entries of its revision log dated 2026-10-01 and 2026-10-02 (commits `262f24d`, `3fbbb86`,
`3210b8e` and `7c1e248` of the earlier history). The paper says that the commit is in the earlier
history and that the published history holds the file as frozen, with those entries appended.

## Generated results

At the root commit, the generators regenerate every generated file of `results/round2/` from the
unpacked archives that `results/round2/README.md` lists, each identical to the committed file
after line endings are converted to LF: `analysis/analyse.py` writes `summary.json`, `macros.tex`
and the ten tables (`ablation.csv`, `all_arms.csv`, `h1.csv`, `h2.csv`, `h3.csv`, `h4.csv`,
`h5b.csv`, `h6.csv`, `h7.csv`, `h7_costs.csv`); `analysis/macros.py` writes `macros.tex` from the
committed `summary.json`; `analysis/explore_summary.py` writes the five `explore_<run>.csv`;
`analysis/ct_heap_summary.py` writes `explore_ct_heap.csv`. `analysis/paper_macros.py`, with
`PUBLIC_COMMIT` added, writes `macros-paper.tex` with the two public-commit macros added and every
other line unchanged. No number of the paper changed. The commands and the comparison are the
Papers repository's `lab/evidence/2026-10-08-L-p2-public-records/w-regen.txt`.

## Round 1's files, archived privately

Round 1 is development data (`hypotheses-round2.md`, section 1). These files of round 1 name the
other code base it was measured in. They are in the earlier history and not in this one: the
frozen `hypotheses.md` and `design/router-v2.md` (frozen with it), `results/README.md` (round 1's
run), `results/macros.tex` (round 1's macros), `results/baseline.md`, `results/baseline_agree.csv`,
`results/baseline_cells.csv`, `results/baseline_probes.csv`, `results/ct_msvc_W.jsonl`,
`results/ct_msvc_W.md`, `results/tab_h4.csv`, `results/tab_left_out.csv` and
`results/table_s1_all_arms.csv`. The paper cites none of them. Comments in
`bench/core/probe.cpp`, `bench/arms/go/httprouter.go`, `bench/arms/go/nethttp.go` and
`t1/h6_targets.cpp`, which are compiled and so are kept byte for byte, and several notes still
name `hypotheses.md` or `design/router-v2.md`. `results/round1-handover.md` cites commits of the
other code base; they are not commits of this repository.

## Other cited commits

None of these is a measured state, and none is in this history. Each is in the archived earlier
history; the subject is that commit's.

| Commit | Date | Cited in | Subject |
|---|---|---|---|
| `44e815ea3` | 2026-09-26 | `design/round2/status.md`; `results/round1-handover.md` | feat(bench): rbench, the router lookup harness, with six arms and the gated pipeline |
| `00624f3a7` | 2026-09-26 | `results/round1-handover.md` | feat(bench): the agreement pass has a time budget; the Go arm reports its heap |
| `4a501c417` | 2026-09-26 | `results/round1-handover.md` | fix(bench): Pistache builds against libc++ for MemorySanitizer; the gate matches records by compiled inputs |
| `21d737c50` | 2026-09-26 | `results/round1-handover.md` | feat(bench): the compile-time and run-time table arms share one out-of-line lookup; ct_costs.py |
| `941cec85e` | 2026-09-27 | `results/round1-handover.md` | fix(bench): ring_walk models router v2 after v2-g; descriptions of mixed-disjoint follow |
| `e7e4305c6` | 2026-09-27 | `design/round2/status.md`; `results/round1-handover.md` | feat(bench): the lead's delta audit before the freeze |
| `a2db64ad1` | 2026-09-27 | `analysis/stats.py`; `analysis/test_stats.py`; `results/round1-handover.md` | docs: freeze hypotheses and the router v2 design note (2026-09-27) |
| `d11216d28` | 2026-09-27 | `results/round1-handover.md` | feat(t1): the H6 build, sanitizer record, gate, T1 driver and analysis |
| `7a5715121` | 2026-09-28 | `results/round1-handover.md` | fix(bench,t1): sanitizer report pattern also counts ERROR: MemorySanitizer and ERROR: ThreadSanitizer |
| `ed4f2c2b8` | 2026-09-29 | `results/round1-handover.md` | fix(analysis,paper): the prefix cut never applied to the fastest competitor of any H1 cell, as a macro-backed sentence |
| `ce20fe53b` | 2026-09-30 | `design/round2/status.md`; `results/round1-handover.md` | docs(design): round 2 design, for review before any implementation |
| `4e2dab213` | 2026-09-30 | `design/round2/status.md` | docs(design): round 2 review fixes: the competitor survey kept with its sources, the gate compares v2's include prefix, only observed compiler facts |
| `221a3fc38` | 2026-09-30 | `design/round2/status.md` | docs(design): round 2 approved; the decisions in the proposal's text and every note's revision log |
| `904cb78e9` | 2026-09-30 | `design/round2/status.md` | feat(bench): gen_route_tests, the paper's tables as test data for RegexMatcher v2 |
| `fe16f19fb` | 2026-09-30 | `design/round2/status.md` | docs(design): round 2 first milestone: what the implementation does differently, and where it stands |
| `8cbbae9c6` | 2026-09-30 | `design/round2/status.md` | docs(design): RegexMatcher v2 on MSVC and clang-cl, and the regex engine under sanitizers (revision log) |
| `aa869d129` | 2026-09-30 | `design/round2/hypotheses-v2-proposal.md`; `design/round2/regexmatcher-v2.md`; `design/round2/status.md` | feat(bench): round-2 harness: RegexMatcher v2's arms, the ablation arm, five new competitors |
| `48992f97a` | 2026-09-30 | `design/round2/status.md` | feat(bench): table_digest (the tables v2 builds, as digests, and the build's allocations); the first L slot's job |
| `d9268c432` | 2026-09-30 | `design/round2/hypotheses-v2-proposal.md`; `design/round2/regexmatcher-v2.md`; `design/round2/status.md` | feat(bench): v2 include hash per build, sanitizer gaps of chi and path-tree, path-tree's archives in pins.cmake, slot 1 job clones its own checkouts |
| `fc0aeba8b` | 2026-09-30 | `design/round2/status.md` | docs(design): round 2 second milestone (revision logs); slot 1 job: no Go proxy, no toolchain fetch |
| `fcddf54ec` | 2026-09-30 | `design/round2/status.md` | docs(design): engineering.md revision log: how many cells the heap-bytes comparison covers so far |
| `89fadfa53` | 2026-09-30 | `design/round2/status.md` | fix(bench): slot 1 job header: lablock's path on L, the clone to run it from, four jobs |
| `6e016d616` | 2026-09-30 | `design/round2/status.md` | fix(bench): slot 1 job gates on the stored-inputs recompute |
| `4bedc1131` | 2026-09-30 | `bench/jobs/slot2.sh`; `design/round2/status.md` | docs(results): round 1 handover, where every archive, record and script lives, with sha256, and the caveats for round 2 |
| `4dd16b74e` | 2026-09-30 | `design/round2/engineering.md`; `design/round2/regexmatcher-v2.md`; `design/round2/status.md` | feat(bench): the v2 arm builds RegexMatcher v2's RuntimeTable (C2); compile-time tables page-aligned |
| `c759a8512` | 2026-09-30 | `design/round2/status.md` | docs(design): C2 (one layout) in the revision logs: RuntimeTable, the deterministic part of rule (c), the object-size question for H7's costs |
| `651995eee` | 2026-09-30 | `design/round2/status.md` | docs(design): schedule revision log: the first L slot ran and passed its gate; C2 built |
| `f7c15943c` | 2026-09-30 | `design/round2/status.md` | docs(design), feat(bench): H7's object size is the sum of the loadable sections, with the file size and its padding beside it (decided); ct_costs.py records data, bss and loadable_bytes |
| `83ae26685` | 2026-09-30 | `design/round2/status.md` | feat(bench): the second L slot's job (target (a) rule 2, C2's H7 iteration check); gen-ct --seeds |
| `48ca2dfdc` | 2026-09-30 | `design/round2/status.md` | feat(bench): backtrack_check (rbench's backtracking model against a counting build of v2); table_digest counts chained edges and hashes Edge::tail where it is not 0 (as used for B1) |
| `2c92baae3` | 2026-09-30 | `design/round2/status.md` | docs(design): target (a) rule 2 holds on L, C2's H7 check passes, B1 and B1' not adopted in WSL (revision logs); tools count chain nodes (B1') |
| `4907be158` | 2026-09-30 | `design/round2/status.md` | feat(bench): the third L slot's job: rule (b) part 1 on L for C2, B1 and both B1' builds, one arm set with gin |
| `376c71dc4` | 2026-09-30 | `design/round2/minimal-server.md`; `design/round2/status.md` | feat(server): the minimal server's HTTP/1.1 layer: parser, responses, HEAD and 405 (tests first) |
| `c892de785` | 2026-09-30 | `design/round2/status.md` | refactor(server): the router interface's result is RegexMatcher v2's Match (the v2 arm fills it with find_into, as the design says); the server takes RegexMatcher from REGEXMATCHER_DIR |
| `ba848296d` | 2026-09-30 | `design/round2/status.md` | feat(server): the minimal server's epoll loop, with loopback tests; 413 for a request larger than a connection's buffer |
| `dedf70356` | 2026-09-30 | `design/round2/status.md` | fix(bench): backtrack_check counts nodes of kind 2 by value, so that it builds against B1 (chained edges) as well as B1' (chain nodes); the third L slot stopped on it |
| `826f8936a` | 2026-09-30 | `design/round2/status.md` | test(server): the count of allocations per request is taken only where the test may define operator new (not under ThreadSanitizer or MemorySanitizer); the tests pass under ASan+UBSan and TSan in WSL (clang 18.1.3, development) |
| `617ee9175` | 2026-09-30 | `design/round2/status.md` | feat(server): the server binary with the v2 and null router arms, and lab/t1's contract test |
| `a79ae4bc2` | 2026-09-30 | `design/round2/status.md` | feat(server): the v1 router arm; v1's pinned fetch shared by rbench and the server |
| `47e699f39` | 2026-09-30 | `design/round2/minimal-server.md`; `design/round2/status.md` | feat(server): the paper's root project builds h6_targets and the server; the arms' agreement on the nine H6 cells |
| `9afb60f5e` | 2026-09-30 | `design/round2/status.md` | docs(design): minimal-server.md revision log: the first implementation and where it differs from the design |
| `6bbdded46` | 2026-09-30 | `design/round2/status.md` | feat(bench): RegexMatcher v2's sanitizer records (sanitize_regexmatcher.sh, regexmatcher_record.py) |
| `0adfba353` | 2026-09-30 | `design/round2/status.md` | docs(design): target (b) decided on L: nothing adopted, the H2 loss at mixed-disjoint m = 10 stands, RegexMatcher back at C2 (revision logs) |
| `1667a4628` | 2026-09-30 | `design/round2/status.md` | feat(bench, t1): the round-2 records and gates for rbench, the server and RegexMatcher; run scripts on RegexMatcher v2 |
| `1ff0457d6` | 2026-09-30 | `design/round2/status.md` | test(bench): the gate tests name their synthetic configuration field neutrally |
| `62b80fd6c` | 2026-09-30 | `design/round2/status.md` | fix(t1): the server's inputs are those of every target it links (a target's hash covers its own translation units only); the RegexMatcher header hash is mserver_arms's, which includes the umbrella header; found by a WSL trial |
| `4c99c142d` | 2026-09-30 | `design/round2/status.md` | docs(design): round 2 status and handover (status.md): commits, adopted and reverted steps, targets and rules with evidence, what remains before the freeze with launch lines, Alex's decisions, caveats |
| `f4f74d38e` | 2026-09-30 | `design/round2/status.md` | docs(design): status.md names no private path |
| `a52aba3e8` | 2026-09-30 | `design/round2/status.md` | feat(bench): sanitize_rbench.sh takes EXTRA_CMAKE (recorded), as the other record scripts do |
| `9ad87ab87` | 2026-09-30 | `design/round2/minimal-server.md`; `design/round2/regexmatcher-v2.md` | feat(bench, t1): record logs kept and packed with their sha256 in the record (keep_record_logs.sh), a record never made again over its logs; the W records script of RegexMatcher (sanitize_regexmatcher.ps1); H6 asks t1.py for at least 6 pairs, as the proposal and D9 require |
| `65817be5b` | 2026-09-30 | `design/round2/status.md` | fix(bench, t1): the record writers read CTest 4's summary; the gates match records by pins |
| `cb04ce7b6` | 2026-09-30 | `design/round2/status.md` | feat(analysis): round 2's analysis end to end: analyse.py, macros from its summary only, H5(b), the ablation arm, the all-arms table (step 3, second part) |
| `0a475cbb0` | 2026-09-30 | `design/round2/status.md` | feat(bench, tools, analysis): ct_cost_run.sh gated and hashed like every measured build (and able to configure); every grid ends by checking on every query each process the agreement budget cut (verified.jsonl), which analyse.py reads; verify_cover.py and jobs/gaps.sh check both on L |
| `3c71533c1` | 2026-09-30 | `hypotheses-round2.md` | chore(bench, analysis): the order seed 20261009 is the default of run_baseline.sh and run_grid.sh (round 1's 20260927 before); the records script shuffles nothing (SEED=none); explore_summary.py reads the run's own verified.jsonl |
| `ed535add4` | 2026-09-30 | `design/round2/status.md` | fix(bench): PCRE2 10.49 (released 2026-09-28) for the r3 arm: PCRE2 is on r3's lookup path in the rest shape (lab evidence 2026-09-30-L-r3-pcre2-path); the sha256 is the release page's; records.sh takes ONLY, gates.sh also gates H7's cost build |
| `82681fe58` | 2026-09-30 | `design/round2/status.md`; `hypotheses-round2.md` | feat(bench, analysis): sixteen distinct table seeds and ring seeds, pair k = (110 + k, 210 + k) (audit M1): kTableSeeds, run_grid.sh, cells.py, 168 new compile-time tables in bench/gen; the bootstrap over table seeds is the one over pairs; cut arms flagged (m19); H6's T0 time from a usable process (m4); H5(b) decided by v2 (m6) |
| `fd29bd110` | 2026-09-30 | `design/round2/status.md` | feat(t1): H6 counts only valid pairs toward its minimum and its stop (t1.py --valid-pairs-only; audit M3); minimal-server.md revision log (M3, m22) |
| `c6722e59e` | 2026-09-30 | `design/round2/hypotheses-v2-proposal.md`; `design/round2/status.md` | feat(bench, analysis): the audit's code fixes before the records (M7, M8, m25, m27, m28, m29) and H7's MSVC cost step (M4) |
| `cff2aa6cf` | 2026-10-01 | `design/round2/status.md` | results: round 2's frozen analysis (main grid with the repeated check, H6, H7's costs) in results/round2; macros carry H1's raw and Holm-adjusted p-values; README with the inputs' sha256, the deviation and Holm's family at mixed-disjoint m = 10 |
| `b1ae4775d` | 2026-10-02 | `hypotheses-round2.md` | results: H7's heap-block follow-up (exploratory), its summary and macros |

Commits of other repositories are cited as well: RegexMatcher's (`d1d73e99b`, the measured v2,
in release 2.1.0.0; `d16f30a8`, v1, tag 2.0.0.1; `00a2053`, the source of
`bench/arms/ablation/route_r1.hpp`; `45ab696`, whose tree equals `d1d73e99b`'s), the Papers
repository's (`8419942`, `cd9e386` and `d30e8e6` as the runs' and records' `papers_head`; `0f90a96`
and `1eaee40c3`, the records and `t1gen` cited by `hypotheses-round2.md`), and the competitors'
pinned commits (`bench/cmake/pins.cmake`, `NOTICE`).
