# Round 2: launch lines for the publication runs (draft)

Status: draft for review, with `hypotheses-round2.md`. Nothing here runs before Alex freezes that
file. These are operational notes, not part of the frozen text: a path may change; what is
measured and how is fixed by `hypotheses-round2.md`.

Every job on L runs under `~/lab/Papers/lab/bin/lablock`, with a pid file and a done file, from a
fresh clone of the Papers repository at the commit that holds the frozen file, with this
repository as its submodule (the scripts find `lab/bin` and `lab/sanitizer-records` at `../../..`).
Each run refuses to measure if its gate fails (records, pins, RegexMatcher's headers), and never
overwrites a run directory.

Rules for every run (`hypotheses-round2.md`, section 4):
- No package update and no reboot on L from the first record of round 2's final set to the end of
  the last run. L runs kernel 7.2.3 with 7.2.6 installed, so a reboot would change the kernel.
- A run that stops early is archived, reported in the journal, and not used. It is started again
  in full, under a new name, with the same seeds.
- Measured traffic stays on L (rbench in one process; H6 over loopback). Control traffic is ssh to
  L's wired interface, enp2s0: `alex@10.10.10.2` once W has an address on 10.10.10.0/24, else
  `alex@192.168.1.62`, the same interface. Never `192.168.1.9`, L's Wi-Fi (rule D7). On
  2026-09-30 W had no address on 10.10.10.0/24, so ssh used 192.168.1.62.

Order (the coordinator's): the main grid (section 1), H7's costs on L (2), H6 at T1 (3), H7's MSVC
costs on W (2b), then the exploratory runs (4).

## 0. The clone and the measured commit

```
mkdir -p ~/lab/p2/pub2 && cd ~/lab/p2/pub2
git clone -q git@github.com:Alex-Tsvetanov/Papers.git Papers
git -C Papers checkout -q <Papers commit with the frozen hypotheses-round2.md>
git -C Papers submodule update -q --init papers/typed-routing
P=~/lab/p2/pub2/Papers/papers/typed-routing
C=d1d73e99b7b26f54ba75354f4880780ece32e8ed
S=~/lab/p2/r2/rm-src-$C-full          # git archive of $C (exists on L; its tree equals 45ab696's)
D=$(date +%Y-%m-%d)
```

## 1. The main grid (H1 to H4, H5(b), H7; the ablation arm)

Builds rbench with every arm, gates it, runs the agreement test, the probes and the 13,048
processes in the order of seed 20261009, then checks on every query each process the agreement
budget cut (`verified.jsonl`). Estimate: 20 h 29 min, plus the build and gate and the re-check
(`hypotheses-round2.md`, section 10).

```
cd ~/lab/p2/pub2
REGEXMATCHER_DIR=$S REGEXMATCHER_COMMIT=$C SEED=20261009 RUN_NAME=$D-L-publication \
  nohup ~/lab/Papers/lab/bin/lablock bash -c "bash $P/bench/run_baseline.sh; echo \"\$(date -Is) exit \$?\" > ~/lab/p2/pub2/pub.done" \
  > ~/lab/p2/pub2/pub.log 2>&1 &
echo $! > ~/lab/p2/pub2/pub.pid
```

The run directory is `$P/results/raw/$D-L-publication` (gate.json, provenance.txt with the pins'
sha256, inputs.json, symbols.tsv, rb_isa.h, cells.jsonl, probes.jsonl, agree.jsonl, verified.jsonl,
exit.txt). Its `exit.txt` must read `agree_exit=0 probe_exit=0 failed_cells=0 cells_exit=0 ...
verify_exit=0` (`rbench_agree_exit=1` is expected: declared disagreements). Then the archive:

```
cd $P/results/raw && tar -czf ~/lab/p2-raw-$D-L-publication.tar.gz --exclude='*/verify/verify_answers' \
  --exclude='*/verify/*.o' $D-L-publication && (cd ~/lab && sha256sum p2-raw-$D-L-publication.tar.gz \
  > p2-raw-$D-L-publication.tar.gz.sha256)
```

## 2. H7's costs on L

After the main grid, from the same clone. Gated (the compile-time arm's build against the records
and pins), then -j1 over the 358 tables of `bench/gen`, then clang's budget search over the 22
tables of table seed 111 and the GitHub table. Estimate: about 1 h 13 min (round 1's 26 min 4 s
for 127 tables, 12.3 s per table, times 358).

```
REGEXMATCHER_DIR=$S REGEXMATCHER_COMMIT=$C \
  nohup ~/lab/Papers/lab/bin/lablock bash -c "bash $P/bench/ct_cost_run.sh $P/results/raw/$D-L-publication-ct; echo \"\$(date -Is) exit \$?\" > ~/lab/p2/pub2/ct.done" \
  > ~/lab/p2/pub2/ct.log 2>&1 &
echo $! > ~/lab/p2/pub2/ct.pid
```

## 2b. H7's MSVC costs on W

On W, with nothing else compiling, from a checkout of this repository at the frozen commit and
RegexMatcher's checkout at `$C` (clean). `bench/ct_msvc.py` configures RegexMatcher in Release with
the W record's options and no sanitizer, and takes `route_ct_table_tests`' flags. It checks that cl
is MSVC 19.51.36246, then compiles the 22 tables one at a time. Each gets the budget search, then
one compile at 33,554,432 for peak memory (Job Object), wall time and object size. Estimate: 15 to
20 min (round 1's 65 compiles of 22 tables took 14 min 54 s; a development compile of one
1,000-route table took 2 min 48 s over its five compiles on 2026-09-30).

```
python bench/ct_msvc.py --rm-dir D:\Dev\GitHub\RegexMatcher --commit d1d73e99b7b26f54ba75354f4880780ece32e8ed ^
  --googletest C:/Users/alext/lab/src/googletest-b514bdc89 --out <run dir>\ct-msvc-W
```

The flags are RegexMatcher's test target's, with no `/arch` option: these compiles measure the
compiler, and nothing they produce runs on L. The run directory keeps `tables.jsonl`, `logs/` (each compile's command and output, `steps.jsonl`,
process snapshots), `env.cmd`, `configure.log` and `rm-release/compile_commands.json`; it is
archived with its sha256 like the L runs.

## 3. H6 at T1

After the main grid and H7's costs: the confirmatory runs first, the exploratory runs last. The T1
run does not use T0; only the analysis of H6(b) reads the main grid's T0 times at pair (111, 211).
Builds the minimal server and t1gen, gates both (the server's records and pins; t1gen's own
record), then the nine cells, three arms in mirrored rounds, 6 to 20 valid pairs each.
Estimate: 36 min to 1 h 59 min.

```
REGEXMATCHER_DIR=$S REGEXMATCHER_COMMIT=$C \
  nohup ~/lab/Papers/lab/bin/lablock bash -c "bash $P/t1/run_h6.sh $P/results/raw/$D-L-h6; echo \"\$(date -Is) exit \$?\" > ~/lab/p2/pub2/h6.done" \
  > ~/lab/p2/pub2/h6.log 2>&1 &
echo $! > ~/lab/p2/pub2/h6.pid
```

A `CHECK_ONLY=1` run of `ct_cost_run.sh`, `run_h6.sh` or `run_baseline.sh` (into a scratch
directory) builds and gates without measuring.

## 4. The exploratory runs

From the gated build of the main grid (`$P/bench/build-publication`), after it; each ends with its
own check on every query. R and the estimates as `hypotheses-round2.md`, sections 7 and 10.

```
B=$P/bench/build-publication/rbench; R=$P/results/raw
cd ~/lab/p2/pub2
cat > explore.sh <<EOF
set -u
one() { name=\$1; shift; env SEED=20261009 "\$@" bash $P/bench/run_grid.sh $B $R/$D-L-exploratory-\$name > $R/$D-L-exploratory-\$name.out 2>&1; echo "\$name exit \$? \$(date -Is)" >> ~/lab/p2/pub2/explore.progress; }
one github SHAPES=github SIZES=203
one no-decoy NO_DECOY=1 SHAPES=mixed-overlap
one miss MISS=500 REPS=3
one vocab-long VOCAB=long SIZES="10000 100000" REPS=3
one zipf ZIPF=1 SIZES="10000 100000" REPS=3
EOF
nohup ~/lab/Papers/lab/bin/lablock bash -c "bash explore.sh; echo \"\$(date -Is) done\" > ~/lab/p2/pub2/explore.done" \
  > ~/lab/p2/pub2/explore.log 2>&1 &
echo $! > ~/lab/p2/pub2/explore.pid
```

## 5. The analysis

On W (NumPy) or on L under lablock, from the runs above:

```
python3 $P/analysis/analyse.py $P/results/raw/$D-L-publication --out-dir $P/results \
  --t1 $P/results/raw/$D-L-h6 --ct-costs $P/results/raw/$D-L-publication-ct --macros $P/results/macros.tex
for x in github no-decoy miss vocab-long zipf; do
  python3 $P/analysis/explore_summary.py $P/results/raw/$D-L-exploratory-$x --verified $P/results/raw/$D-L-exploratory-$x/verified.jsonl \
    --out $P/results/explore_$x.csv
done
```

(`--verified` only where the run wrote `verified.jsonl`.) The MSVC costs of section 2b are reported
from their `tables.jsonl` as they are.
