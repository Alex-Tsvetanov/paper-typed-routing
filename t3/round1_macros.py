#!/usr/bin/env python3
"""Macros of the earlier campaign's first round, for the paper's account of that round (Alex, Q20261103-p2-1).

    python t3/round1_macros.py [--results results] [--out results/round3/round1-macros.tex]

Round 1 ran under hypotheses frozen before its run (results/round1-handover.md). Its numbers are not results of the
paper: the paper says what the round was, that its end-to-end hypothesis failed and was turned around, that the
second round's carry-over bound was chosen below what round 1 measured, and which of round 1's outcomes the second
round's changes answered. Every number it prints comes from here, prefix RoundOne, read from round 1's tables in
results/ (the files the round-1 analysis wrote):

  tab_h1.csv   lookup time: cells, cells passing (column passes), pairs per cell (sens_h1.csv's pairs);
  tab_h2.csv   work per lookup: cells, cells holding both counts, the lost cells;
  sens_h4.csv  build and memory: the shape cells, cells whose build time lost against the included competitors;
  tab_h7.csv   the compile-time table: cells, cells holding;
  sens_h7.csv  the same with the bootstrap clustered by table seed, run after the freeze: cells whose upper bound
               exceeds the margin;
  tab_h6.csv   the end-to-end check: its cells, how many held each part, the ratio range at the smallest size, the
               lost cell of part (b), and diff_ratio (the measured difference in time per request over the lookup
               grid's difference) over the comparable cells.

The frozen bounds of round 1's end-to-end hypothesis are constants here (BAND, BOUND, MARGIN, from the frozen text);
each row's holds column of tab_h6.csv must equal what these bounds give, and t3/test_round1_macros.py checks them
against the frozen text when its commit is in the clone.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "analysis"))
from macros_util import Macros, cell_text, count, fixed, is_true, listing, ratio, read_csv  # noqa: E402

FROZEN_COMMIT = "a2db64a"   # round 1's hypotheses, frozen before its run
BAND = (0.98, 1.05)         # part (a): at the smallest size each interval inside this band
BOUND = 2.0                 # part (b): at m = 10,000 each lower bound above this
MARGIN = 1.02               # the compile-time table's non-inferiority margin, as in the second round
SMALL, LARGE = 10, 10000


def h6_rule(row: dict) -> bool:
    """What round 1's frozen end-to-end hypothesis says of one cell."""
    low, high = float(row["ci_low"]), float(row["ci_high"])
    if int(row["m"]) == SMALL:
        return BAND[0] <= low and high <= BAND[1]
    if int(row["m"]) == LARGE:
        return low > BOUND
    raise ValueError(f"tab_h6.csv: a cell at m = {row['m']}, which round 1's end-to-end hypothesis does not have")


def one(values: set, what: str):
    if len(values) != 1:
        raise ValueError(f"{what} differ: {sorted(values)}")
    return next(iter(values))


def lookup(mac: Macros, results: Path) -> None:
    h1 = read_csv(results / "tab_h1.csv")
    mac.add("RoundOneHOneCells", count(len(h1)))
    mac.add("RoundOneHOnePassed", count(sum(is_true(r["passes"]) for r in h1)))
    mac.add("RoundOneReps", count(one({int(r["pairs"]) for r in read_csv(results / "sens_h1.csv")}, "pairs per cell")),
            "seed pairs per cell")
    h2 = read_csv(results / "tab_h2.csv")
    held = [r for r in h2 if is_true(r["instructions_hold"]) and is_true(r["branch_misses_hold"])]
    mac.add("RoundOneHTwoCells", count(len(h2)))
    mac.add("RoundOneHTwoHeld", count(len(held)))
    mac.add("RoundOneHTwoLostCells", listing([cell_text(r["shape"], int(r["m"])) for r in h2 if r not in held]))
    h4 = [r for r in read_csv(results / "sens_h4.csv") if r["shape"] != "all"]
    mac.add("RoundOneHFourCells", count(len(h4)))
    mac.add("RoundOneHFourLostBuild", count(sum(is_true(r["lost_included"]) for r in h4)),
            "build time above the included competitors' median")
    h7 = read_csv(results / "tab_h7.csv")
    mac.add("RoundOneHSevenCells", count(len(h7)))
    mac.add("RoundOneHSevenHeld", count(sum(is_true(r["holds"]) for r in h7)))
    over = [r for r in read_csv(results / "sens_h7.csv") if float(r["cluster_high"]) > MARGIN]
    mac.add("RoundOneHSevenClusterOver", count(len(over)), "clustered upper bound above the margin, after the freeze")
    mac.add("RoundOneHSevenClusterCells", listing([cell_text(r["shape"], int(r["m"])) for r in over]))
    mac.add("RoundOneHSevenClusterHigh", ratio(max((float(r["cluster_high"]) for r in over), default=0.0)))


def end_to_end(mac: Macros, results: Path) -> None:
    rows = read_csv(results / "tab_h6.csv")
    for r in rows:
        if is_true(r["holds"]) != h6_rule(r):
            raise ValueError(f"tab_h6.csv, {r['shape']} at m = {r['m']}: holds is {r['holds']}, the frozen bounds give "
                             f"{h6_rule(r)}")
    small = [r for r in rows if int(r["m"]) == SMALL]
    large = [r for r in rows if int(r["m"]) == LARGE]
    lost_b = [r for r in large if not h6_rule(r)]
    comparable = [r for r in rows if is_true(r["comparable"])]
    mac.add("RoundOneHSixBandLow", fixed(BAND[0], 2), "frozen, part (a)")
    mac.add("RoundOneHSixBandHigh", fixed(BAND[1], 2))
    mac.add("RoundOneHSixBound", count(BOUND), "frozen, part (b)")
    mac.add("RoundOneHSixSmallCells", count(len(small)))
    mac.add("RoundOneHSixLargeCells", count(len(large)))
    mac.add("RoundOneHSixPairs", count(one({int(r["pairs"]) for r in rows}, "pairs per end-to-end cell")))
    mac.add("RoundOneHSixAHeld", count(sum(h6_rule(r) for r in small)))
    mac.add("RoundOneHSixAboveOne", count(sum(float(r["ci_low"]) > 1 for r in small)),
            "smallest-size cells whose lower bound is above one")
    mac.add("RoundOneHSixRatioLow", ratio(min(float(r["ratio"]) for r in small)))
    mac.add("RoundOneHSixRatioHigh", ratio(max(float(r["ratio"]) for r in small)))
    mac.add("RoundOneHSixBHeld", count(len(large) - len(lost_b)))
    mac.add("RoundOneHSixBLostCells", listing([cell_text(r["shape"], int(r["m"])) for r in lost_b]))
    mac.add("RoundOneHSixBLostLow", listing([ratio(float(r["ci_low"])) for r in lost_b]))
    mac.add("RoundOneHSixComparable", count(len(comparable)))
    mac.add("RoundOneHSixDiffRatioLow", fixed(min(float(r["diff_ratio"]) for r in comparable), 2))
    mac.add("RoundOneHSixDiffRatioHigh", fixed(max(float(r["diff_ratio"]) for r in comparable), 2))


def generate(results: Path) -> str:
    mac = Macros()
    lookup(mac, results)
    end_to_end(mac, results)
    return "% Generated by t3/round1_macros.py from round 1's tables in results/. Do not edit.\n" + mac.text()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path, default=ROOT / "results")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "round3" / "round1-macros.tex")
    a = ap.parse_args(argv)
    a.out.write_text(generate(a.results), encoding="utf-8", newline="\n")
    print(f"round1_macros.py: wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
