# Round 1 of P2: handover

Round 1 measured router v2 of the round-1 server library (commit 6d28e3610) against eleven
competitors, with the library's pre-v2 router (commit 9b8aaf452) as a reference arm, under the
hypotheses frozen at paper commit a2db64a (Papers a2c86dc). Round 2 re-runs P2 on its own
public implementation with a new pre-specification. Round 1's numbers do not carry over; its
harness, gate and procedures do. This note says where every round-1 archive, record and
script lives, and what round 2 must know.

The round-1 library's arms carry its name in the raw data and in `bench/`. Here they are the
table arm (H1, H2), the Router arm, the compile-time arm (H7) and the pre-v2 arm.

## Archives

Raw data is not in git. Each archive is in `D:\Archive\p2-raw\` on W and in `~/lab/` on L
(the MSVC one on W only), with a `.sha256` file next to it. The copies on W were checked
against their sha256.

| Archive | Contents | sha256 |
|---|---|---|
| p2-raw-2026-09-26-L-baseline-4a501c4.tar.gz | pre-v2 baseline: rbench 4a501c4, the library at 9b8aaf452, 13 arms, one process per cell (325); source of results/baseline.md and baseline_cells.csv | 3e55f7bdfa46494811d306fc6447ecf93828cbdd5f57b0cadf2f943d554d0807 |
| p2-raw-2026-09-27-L-v2-gated-21d737c.tar.gz | development: a gated grid of an earlier router v2 (library 991461c0b, rbench 21d737c), 25 cells | 75228e69d3c0edc39dd0ba9970a908402e240225a7ce9f6281eb40037c9b2ab0 |
| p2-raw-2026-09-27-L-publication.tar.gz | main grid (H1 to H4, H7): 20 arms, 6,202 processes | 1aed9e0d86495cf50ad7e286f2aaefdcf0dedc1a719dcaffc9e12beea71bba10 |
| p2-raw-2026-09-27-L-publication-verify.tar.gz | re-check on every query of the 76 main-grid processes the 120 s budget cut short; decisions with it | e4a6d8de8eeee54968a1040b90ea71720530cff2ef12d5db1aa67a42542ba9e0 |
| p2-raw-2026-09-27-L-publication-ct.tar.gz | H7's costs on L (ct_cost_run, clang) | a45d1a59913f0ce7539d76aed99792643104242b71ebbce208d6e3936d2a596e |
| p2-msvc-ct-W-2026-09-28.tar.gz | H7's MSVC budgets and compile memory, single compiles on W | 1d91ed7b0140a4bef12528bcb8dc0c8e77bec25b001e923042d1f68fa585dd6c |
| p2-raw-2026-09-28-L-h6.tar.gz | H6: T1 run, nine cells | 80a6bbfedc65452c5af2ad23b2c2b710a9f556be9b4c44543a787f4db4b8b2a3 |
| p2-raw-2026-09-27-L-exploratory-github.tar.gz | exploratory: GitHub API table (203 routes) | 44c4e76c2581f27d41300782815d037d621966c4ca546a9f4a4d12860f6cf318 |
| p2-raw-2026-09-27-L-exploratory-miss.tar.gz | exploratory: miss-heavy rings (MISS=500) | 35378695168efdaa8eb7356212544b5bd8c97cc695147034328b0cbf852c1bc1 |
| p2-raw-2026-09-27-L-exploratory-ring-4096.tar.gz | exploratory: ring of 4,096 queries, m = 10,000 and 100,000 | a0e00b1b06c63a6825c5cd82d28b939bcf7e5d1af9d3ce70c252bafa220501f7 |
| p2-raw-2026-09-27-L-exploratory-ring-65536.tar.gz | exploratory: ring of 65,536 | 7355be7f96d0df554342e65196ffd4f2c344aeaeb8e2081e2d33855307cd0b52 |
| p2-raw-2026-09-27-L-exploratory-ring-1048576.tar.gz | exploratory: ring of 1,048,576 | 3ebb31b92db48af82d8a79947e22da71d1a0b703ced038f1a7cc42235dc92cff |
| p2-raw-2026-09-27-L-exploratory-vocab-long.tar.gz | exploratory: 12 to 24 letter literals (VOCAB=long) | aca4256a027fafea36ab6003cb6ea82f738cdada208c009929878133249eb984 |
| p2-raw-2026-09-27-L-exploratory-zipf.tar.gz | exploratory: Zipf ring (ZIPF=1) | b52f6d8a6490d9cb8981bfb7bea90ac7c704e90610955c5dd9245d247066ccd8 |

Not run: the ring-layout grid (RING_LAYOUT=queries), mixed-overlap without decoys
(NO_DECOY=1) and the re-check of the exploratory runs. They were cancelled because round 2
supersedes round 1's exploratory set (lab journal, 2026-09-30). All exploratory runs are
development data only.

## Records

In the Papers repo, `lab/sanitizer-records/`, committed. The sha256 is of the committed file.
The gate matches a record to a build by what it compiled (inputs hash), not by commit. The
library's records have its name as a file prefix; they are listed here by commit.

| Record | Covers | sha256 |
|---|---|---|
| rbench-e7e4305c6-L-asan.json | main rbench binary, every arm, ASan+UBSan | 2571dac59ffcf62a353686677df1ddeace1e18404c5d181c83500438f7b693a4 |
| rbench-e7e4305c6-L-tsan.json | the same, TSan | 62b07cc1420a10775619376f7108ede197578b7201da3a48bdbc008c5d069c8a |
| rbench-e7e4305c6-L-msan.json | the same, MSan; the five Go and Rust arms are a declared gap (bench/coverage.json) | 869ade34aa04d71e0c2be31dd4a0960ed22b2694c13e0d9602a281c1c6ae0e13 |
| rbench-e7e4305c6-L-asan-v1.json | pre-v2 rbench binary, ASan+UBSan | f4234fda97aa4fb5f512978b64da7a9223164b26f497588988a69559a9dd622c |
| rbench-e7e4305c6-L-tsan-v1.json | the same, TSan | b1639784f2a59b09443d41c00b91a44931b93aaaf8e5dc1b6c1561d6eee67222 |
| rbench-e7e4305c6-L-msan-v1.json | the same, MSan | 5f93de282beec0b416d0e27802d1c589db24116d98b0865e3448b5a3ba4ab158 |
| rbench-941cec85e-L-asan.json | the library's inputs in the main binary (with e7e4305c6), ASan+UBSan | 00ed5b81607a92492db850c23c8a707492c2aac0fa39c055ce8c4bd1a6c6b4a0 |
| rbench-941cec85e-L-tsan.json | the same, TSan | 72ec0b4ccfdc71098a8c352d6dc27abd6ca8b7ba1a5a536511f398cf94e2b583 |
| rbench-941cec85e-L-msan.json | the same, MSan | a7ef100af4f899222c5c5aecbd15af6082bc606a72dfc9995258b4f5d08328ce |
| (library) 6d28e3610-bench.json | the library's test suite at 6d28e3610, bench options, L | d1a45694ec00ed740286fad80a80f90e97a1d3a8746f7799c458950fd9a09386 |
| (library) 6d28e3610-W-asan-windows-bench.json | the same, W, MSVC ASan | 9863597f2b32db82b83716a95314d9d59b83eec578de71e5e661dbedecde41f4 |
| (library) 34397cd59-bench.json | the library's test suite, bench options, L; its library inputs hash equals the 9b8aaf452 build's | 8ca29213a94001a9cbdcad382aa53ecd174d9a0b9a3d194600c69f8fd3b57557 |
| (library) 9b8aaf452-W-asan-windows-bench.json | the library at 9b8aaf452, W, MSVC ASan | 64761381eb198123f52a19c7331492e99e290ca66b1cb48abbb184aa5b1006a5 |
| t1gen-1eaee40c3.json | the T1 load generator | 91207feb965323784647de804a999a9fab0f41d5aed3c8cbe463ed3810712b84 |
| h6-d11216d28-L-asan.json | H6 server and targets on router v2, ASan+UBSan | 34c04ce8b4812f739af079955fc44f4ba788601305c4bc99ae96b440c2d3dfcf |
| h6-d11216d28-L-tsan.json | the same, TSan | f14965b22e1fc3125b1fdb0bc08cc9b2d8de5d4869a0474fb859969e0cf558fb |
| h6-d11216d28-L-msan.json | the same, MSan | 819a4d5cd2e31f8b0f27aa051511fd448536f02bfa682a47537313f59fce60f8 |
| h6-d11216d28-L-asan-v1.json | H6 server on the pre-v2 router, ASan+UBSan | 53f2f3f3f2de6c8569ff5765f2339c1c3a8c63f6c2667bc10e347fe7fcb37c4c |
| h6-d11216d28-L-tsan-v1.json | the same, TSan | 2bd37371ca694a869012505b00f0a28a26d4a3a5776df893465373b0813c61a2 |
| h6-d11216d28-L-msan-v1.json | the same, MSan | 8828344b5503677303bdca36a81eea6d744459536d52cd81e9c89887732f0e23 |
| (library) ea4112b36-W-asan-windows-http2.json | H5(c) HTTP/2 HEAD test, W, HTTP/2 on | b1294fb378289ac5e3dbe2ba4ab8e3e88a650ea8ff1a99a46bad5bbaa515ba5f |
| (library) f3c247833-W-asan-windows-http2.json | ea4112b36 with the HTTP/2 read buffer value-initialised, W | 42b008ead4dd1222810fd97b1e1d5de12cf1ce626c8094ec4b89caba884d52f2 |
| (library) d26c4a972-W-asan-windows-bench.json | rejected path-compression commit; gates nothing | aa446aa43e5c7850085b72859976d26cb1345bb73d5aefa97522e5590ae511e5 |

Older rbench records gated the baseline and iteration runs: rbench-00624f3a7-L-{asan,tsan,msan},
rbench-44e815ea3-L-{asan,tsan,msan}, rbench-21d737c50-L-{asan,tsan,msan} and
rbench-4a501c417-L-msan. Some also appear in the publication run's gate for the pre-v2
binary, always beside an e7e4305c6 record that covers the same inputs. Their logs are gone
(sanitizer gate audit, lab journal 2026-09-28).

Not committed, on L only: the red L record of ea4112b36 with HTTP/2 on and its logs, in
`~/lab/p2/h6/Papers/lab/sanitizer-records/`. The L records of f3c247833 were cancelled before
they started (lab journal, 2026-09-29), so H5(c) over HTTP/2 has no green Linux record.

## Scripts and code

Paper repo (`paper-typed-routing`). Its last round-1 commit is ed4f2c2; round 2 starts at
ce20fe5. The publication run used a2db64a.
- `bench/`: the harness (rbench): arms, table and ring generator, runner, `run_grid.sh`,
  `run_baseline.sh` (build, gate, run), `build.sh`, `check_records.py`, `check_agree.py`,
  `sanitize_rbench.sh`, `sanitizer_record.py`, `ct_cost_run.sh`, `ct_steps.py`,
  `ct_costs.py`, `semantics.json` (declared disagreements), `coverage.json` (declared gaps).
- `analysis/`: `cells.py`, `holm.py`, `h1_stats.py`, `h2_stats.py`, `h347_stats.py`,
  `h6_stats.py`, `summarize.py`, `explore_summary.py`, `layout_compare.py`,
  `test_decisions.py`.
- `tools/`: `verify_answers.cpp`, `build_verify.py`, `verify_unverified.py` (the re-check on
  every query, linked from a run's own rbench objects).
- `t1/` and the root `CMakeLists.txt`: the H6 tools (`h6_targets.cpp`, `h6_server.cpp`,
  `build_h6.sh`, `sanitize_h6.sh`, `h6_record.py`, `check_h6_records.py`, `run_h6.sh`,
  `h6_exercise.py`).
- `hypotheses.md` (frozen; every deviation and the design note's errata are in its revision
  log), `design/router-v2.md` (frozen), `results/README.md` (the run, procedural notes,
  independent verification, H7's costs, H6, H5(c) over HTTP/2), `results/ct_msvc_W.*`.

Papers repo: `lab/bin/` (lablock, pin.sh, inputs_hash.py, sanitize.sh, sanitize.ps1),
`lab/t1/` (t1.py; t1gen in gen/), `lab/journal.jsonl`, and `lab/evidence/2026-09-27-L-path-compression`,
`-bca-scipy-check`, `-dispatch-stall-validation`, `-backtracking-model-check`.

L, `~/lab/p2/`: the queue drivers (`pub-run.sh`, `pub-analysis.sh`, `pub-verify.sh`,
`pub-ct.sh`, `h6-records.sh`, `pub-h6.sh`, `pub-chain.sh`, `pub-explore.sh`,
`pub-explore2.sh`, `explore-guard2.sh`) with their progress, pid and done files;
`stop-pid-tree.sh`; the publication clone `pub/` (Papers a2c86dc, paper a2db64a, the library
at 6d28e3610 and 9b8aaf452); the H6 clone `h6/`. Cancelled jobs are in
`cancelled-2026-09-29/` and `cancelled-2026-09-30/`. The second holds `pub-explore3.sh` and
`pub-explore3-inner.sh`, which ran zipf and held ring-layout and no-decoy, with
`explore-verify.sh` and `pub-chain4.sh`, the re-check of the exploratory runs.

## Caveats for round 2

- **Every query.** A cell's agreement pass stops after 120 s, so a slow arm may be checked on
  part of the ring (verified_all false). `analysis/cells.py` fails such an arm unless a
  re-check on every query agreed. In the main grid 76 processes needed it; all agreed. The
  exploratory runs were never re-checked. Processes left unverified: miss 76, ring-4096 27,
  ring-65536 77, ring-1048576 135, vocab-long 76, github 0, zipf 75. Budget the
  re-check, or a larger verify budget, into the plan.
- **Timed passes over a slow arm run on a prefix of the ring** (0.25 s per pass, at least 16
  queries; `MeasureOptions::pass_budget_s`). In the main grid it cut three competitors and the
  reference arms, never an arm of router v2 and never the fastest competitor of an H1 cell.
  The frozen text did not mention it. Declare it.
- **`rbench_agree_exit=1` is expected** in every run with mixed-overlap, because of declared
  disagreements. The verdict is `agree_exit`, checked row by row against `semantics.json`.
- **Statistics.** Holm's family is fixed at the pre-specified size; an untested cell enters
  with p = 1 (`analysis/holm.py`). With the median of ten pairs the BCa acceleration is zero,
  so the intervals are bias-corrected percentile intervals. H7's lower bound at wild m = 10
  moved between 0.9997 and 1.0016 over 40 resampling seeds.
- **A/B iteration grids.** Build both binaries with the same arms: with a different arm set
  even the null arm moved about 2.5%. At two processes per cell an unchanged cell moved by
  -7% to +11%, so a 2% rule cannot be judged on time there; instruction counts can.
- **Go arms.** Their measuring thread ran below 3.10 GHz in 180 processes, with up to 27%
  spread over epochs (the collector on other threads). Report their clock and spread.
- **Sanitizers.** MemorySanitizer cannot see io_uring's kernel writes: value-initialise every
  buffer an io_uring read fills. The report pattern of the record scripts was widened
  (Papers 26ae0a3, paper 7a57151); the audit changed no record's status. Keep every record's
  logs under `~/lab/records-logs/<record-name>/`, archived with a sha256, never in /tmp.
- **The round-1 server library** answers a second pipelined HTTP/1.1 request with 400, so T1
  ran one request in flight per connection. H6's server stopped through App::stop() on
  SIGTERM so sanitizer builds ran their exit checks. Both H6 arms ran `--io-backend io_uring`
  and `--max-requests 0`, which the frozen text did not fix.
- **L.** The login shell is zsh: run loops from bash script files, and stop a job tree with
  `~/lab/p2/stop-pid-tree.sh PID`, never pgrep or pkill -f. Kernel 7.2.6 is installed but
  7.2.3 runs: a reboot changes the kernel. `/tmp` is a 7.6 GB tmpfs. `~/lab/Papers` is
  another agent's tree; use a fresh clone.
- **Round-1 outcomes, as development knowledge only.** H1 35 of 35 cells; H2 34 of 35 (lost
  at mixed-disjoint m = 10); H3 held; H4 failed on build time (20 of 35 cells lost); H7 21 of
  21; H6 failed both parts (no m = 10 interval inside [0.98, 1.05]; at m = 10,000 rest passed
  and param-last did not). Path compression was tried and rejected (lab journal 2026-09-27;
  lab/evidence/2026-09-27-L-path-compression).
