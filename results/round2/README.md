# Round 2 results

The files here are written by `analysis/analyse.py` (and `macros.tex` by `analysis/macros.py`) from
the publication runs of round 2, as `hypotheses-round2.md` (frozen at 9d7e8fe) pre-specifies them.
Nothing here is edited by hand. The paper's numbers come from `macros.tex` only.

The commits that the files here name (9d7e8fe, the head the runs were built at; 90beca488 and
4cc42bf11, the code of the harness and of the server; 35554b3, the heap-block arm) are in the
repository's earlier history, which is archived privately. `../PROVENANCE.md` maps them to this
history's root commit, f626955, and shows that the files the builds compiled are the same.

## Inputs

| Run | Archive (`D:\Archive\p2-raw\` and `~/lab` on L) | sha256 |
|---|---|---|
| main grid | `p2-raw-2026-09-30-L-publication.tar.gz` | efc3b2fc6c74bc21d8ac7a152abfb6704345b309352b2971d219c4612601e8a6 |
| its repeated check on every query | `p2-raw-2026-09-30-L-publication-verify-repeat.tar.gz` | 19600f543dfd56d3bc548d959d550fbc136ec6262088abc223246b2c01ff4420 |
| H7's costs on L | `p2-raw-2026-09-30-L-publication-ct.tar.gz` | d88b08c2de346e8defd136c7c317baf9ed4eadf736deffeb2d10f53e04f61744 |
| H6 at T1 | `p2-raw-2026-09-30-L-h6.tar.gz` | effe075b696c916ac83391fa58d627d5e8729c874a2be693b1571e28f7c90da7 |
| H7's MSVC costs on W | `p2-raw-2026-10-01-W-ct-msvc.tar.gz` | 1e32cfbffc60a9f099cf026c32bd23681e57fb220ce261334fc75e404ab5d06a |
| H7's heap-block follow-up (exploratory) | `p2-raw-2026-10-02-L-exploratory-ct-heap.tar.gz` | ee2571a8f29ea55e549fe647726933122194d2050219b0823daf18313fc72912 |

The command (on W, NumPy, from the unpacked archives):

```
python analysis/analyse.py RUNS/2026-09-30-L-publication \
  --verified RUNS/2026-09-30-L-publication/verified-repeat.jsonl \
  --t1 RUNS/2026-09-30-L-h6 --ct-costs RUNS/2026-09-30-L-publication-ct \
  --out-dir results/round2 --macros results/round2/macros.tex
```

`launch.md` named `results/` as the output directory; `results/round2/` keeps round 1's files in
`results/` apart. The MSVC costs are reported from their `tables.jsonl`
(`lab/evidence/2026-10-01-W-ct-msvc`) as they are.

The exploratory runs decide nothing. `explore_<run>.csv` is `analysis/explore_summary.py` over each
(with its own `verified.jsonl`); their archives, `p2-raw-2026-09-30-L-exploratory-<run>.tar.gz`, and
sha256 are in `lab/evidence/2026-10-01-L-exploratory`.

## The deviation

The main grid's check on every query was repeated with 4 checks at once, after the kernel's
out-of-memory killer had stopped 79 of the 115 checks run 16 at once (revision log of
`hypotheses-round2.md`, 2026-10-01, approved before the repeat). The repeat checks answers only; no
timing was re-measured or replaced. All 115 processes agreed on every query. The analysis reads the
repeat's `verified-repeat.jsonl`; the first check's `verified.jsonl` stays in the run.

## Holm's family and mixed-disjoint, m = 10

H1's cell at mixed-disjoint, m = 10 passes in this analysis and did not pass in the analysis of the
run before the repeat. Its data are the same; what changed is the family Holm's step-down adjusts it
in. The paper must say so.

- Before the repeat, the six cells at m = 100,000 with actix-router could not be tested (79
  processes not verified on every query). Each entered Holm with p = 1, as the frozen text
  prescribes. With those six at the bottom of the order, mixed-disjoint m = 10 was 28th of 35 by
  its sign-test p, so its multiplier was 35 - 28 + 1 = 8.
- After the repeat the six cells are tested and their p-values are small, so the cell is 34th of
  35, and its multiplier is 2.
- Its raw sign-test p is the same in both: 13 of 16 pairs below 1.02, p = 0.0106
  (`\HOnePSignRawMixedDisjointTen`). Holm-adjusted it was 0.085 before and is 0.021 now
  (`\HOnePSignHolmMixedDisjointTen`), below the family-wise 0.025.
- Its bootstrap p moved too, from 0.0042 to 0.0024 raw (Holm-adjusted 0.033 and 0.0047,
  `\HOnePBootRawMixedDisjointTen`, `\HOnePBootHolmMixedDisjointTen`). One generator serves the
  tested cells in the family's order, so testing six more cells changes the draws every later
  cell gets. Its ratio (0.973) and interval ([0.953, 1.016]) do not depend on the family and are
  the same in both analyses.
- The cell passes non-inferiority at 1.02 only; it does not pass superiority.

## The paper's second macro file

`macros.tex` carries the decisions and the per-cell statistics that `summary.json` holds, as the
frozen text's section 9 sets it. The paper also states numbers that `summary.json` does not carry:
the rows of its per-cell tables, H7's costs, the exploratory runs, the ablation arm, the design's
constants, the tool versions and the archives. `macros-paper.tex` holds them, written by
`analysis/paper_macros.py` from the files here, the runs' evidence and records in the Papers
repository, the unpacked main grid (`toolchain.txt`, `cells.jsonl`, `verified*.jsonl`) and the
constants of the frozen text, each named in the script. It decides nothing and changes no file
above:

```
python analysis/paper_macros.py --results results/round2 \
  --run D:/Archive/p2-raw/runs/2026-09-30-L-publication --out results/round2/macros-paper.tex
```

## H7's heap-block follow-up (exploratory)

The last item of the frozen text's section 7: if an H7 cell shows a table seed apart from the
others, that cell again, with the compile-time table copied into a heap block in the same binary
(`design/round2/engineering.md`, 3.4). In the main grid, H7's cell param-last m = 1,000 had table
seed 124 at 1.1595 (`\HSevenLostMaxPair`) with equal instructions. The follow-up ran on L on
2026-10-02 and decides nothing.

- The arm. `regexmatcher-v2-ct-heap` (paper 35554b3, `bench/arms/regexmatcher_v2_ct_heap.cpp`)
  finds the compile-time table as the compile-time arm does and copies its bytes, in their own
  layout, into one heap block aligned to a page. It shares the adapter and `find_v2` with the
  other two arms. It is built only when `RB_ARMS` names it; no file the measured arms compile
  changed.
- The gate. Three new records cover the new arm, `rbench-35554b313-L-{asan,tsan,msan}-ctheap`
  (the three v2 arms; all green, no sanitizer report; Papers `lab/sanitizer-records`). The
  existing records cover every other target. One binary held every arm of the main grid and the
  new arm, linked last, and passed the gate. The section 7 runs used the main grid's build; this
  one cannot, since that build has no such arm.
- The run. The three v2 arms at param-last m = 1,000, the sixteen pairs of H7, order seed
  20261009, the check on every query 4 at once. All 48 processes ran, agreed and were verified on
  every query. Evidence: `lab/evidence/2026-10-02-L-exploratory-ct-heap`.
- The summary is `explore_ct_heap.csv`; the paper's numbers are the `\ExCtHeap*` macros of
  `macros-paper.tex`.

What it shows:
- Table seed 124: heap copy over run-time table 0.9950; compile-time over run-time table 1.0126 in
  this binary, against 1.1595 in the main grid. The three arms run 516.4 instructions per lookup.
  L1d misses per lookup: 4.07 (run-time), 1.06 (compile-time), 4.06 (heap copy). L1 dTLB misses
  per lookup: 0.0194, 0.0195, 0.0192.
- The other fifteen seeds: heap copy over run-time from 0.9117 (seed 122) to 1.0685 (seed 125),
  median 0.9939; compile-time over run-time from 0.9011 (seed 122) to 1.1512 (seed 114), median
  1.0014. Over all sixteen pairs the medians are 0.9945 and 1.0038.
- Seed 124 did not stand apart in this binary. The slowest process of each arm ran the same
  instructions as the other arms in its pair: the compile-time table at seed 114, 191.5 cycles per
  lookup (the arm's median 165.8); the run-time table at seed 122, 183.3 (165.6); the heap copy at
  seed 125, 186.6 (165.0).
- The heap copy has the run-time table's L1d misses, not the compile-time table's, in every pair.
  Medians per lookup: heap copy 4.07, run-time 4.06, compile-time 1.06. dTLB misses are alike in
  the three arms: run-time 0.0189, compile-time 0.0191, heap copy 0.0190.
- Placement. Against the main grid's binary, every C++ function kept its address modulo 64,
  `find_v2` and both H7 arms' timed loops included; each compile-time table lies nine pages
  further, at the same page offset. The heap copy's timed loop starts at 48 modulo 64, the other
  two arms' at 32 (`layout.txt` in the evidence).

The commands (on W, from the unpacked archives):

```
python analysis/ct_heap_summary.py RUNS/2026-10-02-L-exploratory-ct-heap \
  --frozen RUNS/2026-09-30-L-publication --out results/round2/explore_ct_heap.csv
python analysis/paper_macros.py --results results/round2 \
  --run RUNS/2026-09-30-L-publication --out results/round2/macros-paper.tex
```
