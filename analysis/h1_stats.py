#!/usr/bin/env python3
"""H1 of hypotheses-round2.md from a publication run: per cell, RegexMatcher v2's lookup time
against the fastest competitor's, paired by seed pair; the BCa bootstrap over table seeds and the
exact sign test, each with Holm's step-down over the family; a cell passes only under both.

    h1_stats.py RUN_DIR [--out results/h1.csv] [--margin 1.02] [--cap 1.10] [--alpha 0.025]
                [--need 32] [--resamples 10000] [--seed SEED] [--family h1|all] [--any-pairs]
                [--verified FILE]

Data: cells.jsonl of run_grid.sh, R = 16 processes per cell, process k with the k-th (table seed,
ring seed) pair (analysis/cells.py's design_pairs: sixteen table seeds and sixteen ring seeds, one
pair each). The arm under test is regexmatcher-v2. Which competitors take part in a cell, and
which cells cannot pass, is decided by analysis/cells.py: nothing is dropped in silence, and every
absent competitor is printed. A cell whose v2 pairs are not the design's cannot pass (--any-pairs
lifts this, for development grids only).

The statistic of a cell on a set of pairs I: the fastest competitor c* is the one with the lowest
median time over I, and theta(I) = the median over i in I of v2_i / c*_i (analysis/stats.py).

1. The BCa bootstrap (analysis/stats.py), clustered by table seed: 10,000 resamples of the table
   seeds, each keeping its pairs together (in the design, one pair each, so this is the bootstrap
   over pairs); c* chosen again in every resample; z0 with ties as half; the acceleration from
   the jackknife over table seeds. The two-sided interval at 1 - 2 alpha (95%) is reported for
   every cell, unadjusted. The one-sided p-value of H0 "theta >= margin" inverts the upper bound.
2. The exact sign test against c* (chosen on all pairs): X, the pairs whose ratio is below the
   margin (a ratio equal to it is not below); p = P(X >= x), X binomial with 16 and 1/2 (the
   pairs share no seed, so they are independent).
Each runs Holm's step-down over the family's 35 cells at family-wise alpha, one-sided; a cell
that cannot be tested enters both with p = 1. A cell passes only if it passes under both; if the
two disagree, both are reported and the cell does not pass. H1 holds if at least NEED cells pass
and the upper bound is at most CAP in every tested cell. Superiority (margin 1.00) is decided the
same way, Holm-adjusted over the family on its own; it decides nothing about H1. Reported beside,
deciding nothing: the largest per-pair ratio, the medians of v2 and of c*, and whether a timed
pass of v2 or of c* ran on a prefix of the ring (cut_v2, cut_fastest).

One generator, seeded with SEED, serves every tested cell in the family's order (each shape in
turn, and within it the sizes in increasing order), each drawing its resamples once.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

from cells import H1_SHAPES, H1_SIZES, V2, by_pair, cut, design_pairs, load, sort_cell
from holm import decide_both
from stats import bca, bca_bound, fastest_ratio, p_value, sign_test

RESAMPLING_SEED = 20261010  # proposed in hypotheses-round2.md, fixed at the freeze
FIELDS = ["shape", "m", "status", "fastest", "competitors", "absent", "failures", "pairs", "v2_ns", "fastest_ns",
          "ratio", "ci_low", "ci_high", "z0", "a", "p_boot", "p_boot_holm", "sign_x", "max_pair_ratio", "p_sign",
          "p_sign_holm", "passes_boot", "passes_sign", "passes_disagree", "passes",
          "p_boot_sup", "p_boot_sup_holm", "sign_x_sup", "p_sign_sup", "p_sign_sup_holm", "superior_boot",
          "superior_sign", "superior_disagree", "superior", "cut_v2", "cut_fastest"]


def arrays(v2_rows: list[dict], rivals: dict[str, list[dict]]) -> tuple[np.ndarray, np.ndarray, list[str], list[tuple]]:
    v = by_pair(v2_rows, "ns_median")
    pairs = sorted(v)
    names = sorted(rivals)
    riv = np.array([[by_pair(rivals[n], "ns_median")[k] for k in pairs] for n in names])
    return np.array([v[k] for k in pairs]), riv, names, pairs


def compute_cell(v2: np.ndarray, riv: np.ndarray, names: list[str], pairs: list[tuple], margin: float, alpha: float,
              resamples: int, rng: np.random.Generator) -> dict:
    """Both computations for one cell (before Holm)."""
    seeds = [p[0] for p in pairs]
    clustered = bca(v2, riv, fastest_ratio, seeds, resamples, rng)
    best = int(np.argmin(np.median(riv, axis=-1)))
    ratios = v2 / riv[best]
    x, p_sign = sign_test(list(ratios), margin)
    x_sup, p_sign_sup = sign_test(list(ratios), 1.0)
    return {"status": "tested", "fastest": names[best], "pairs": len(pairs), "ratio": clustered.theta,
            "ci_low": bca_bound(clustered, alpha), "ci_high": bca_bound(clustered, 1 - alpha),
            "z0": clustered.z0, "a": clustered.a, "p_boot": p_value(clustered, margin),
            "p_boot_sup": p_value(clustered, 1.0), "sign_x": x, "p_sign": p_sign, "sign_x_sup": x_sup,
            "p_sign_sup": p_sign_sup, "max_pair_ratio": float(np.max(ratios)),
            "v2_ns": float(np.median(v2)), "fastest_ns": float(np.median(riv[best]))}


def decide(cells: dict, *, keys: list[tuple] | None = None, margin: float = 1.02, cap: float = 1.10,
           alpha: float = 0.025, need: int = 32, resamples: int = 10000, seed: int = RESAMPLING_SEED,
           expected_pairs: list[tuple] | None = None, v2: str = V2) -> tuple[list[dict], dict]:
    keys = keys if keys is not None else [(s, m) for s in H1_SHAPES for m in H1_SIZES]
    rng = np.random.default_rng(seed)
    rows = []
    for shape, m in keys:
        srt = sort_cell(cells.get((shape, m), {}), shape, v2=v2, expected_pairs=expected_pairs)
        row = {"shape": shape, "m": m, "competitors": " ".join(sorted(srt.included)),
               "absent": "; ".join(f"{a}: {w}" for a, w in sorted(srt.absent.items())),
               "failures": "; ".join(srt.failures)}
        if srt.failures or srt.v2 is None:
            row["status"] = "fails"
        elif not srt.included:
            row["status"] = "no competitor holds the table"
        else:
            row.update(compute_cell(*arrays(srt.v2, srt.included), margin, alpha, resamples, rng))
            row["cut_v2"] = cut(srt.v2)
            row["cut_fastest"] = cut(srt.included[row["fastest"]])
        rows.append(row)
    decide_both(rows, alpha, "p_boot", "p_sign", "passes")
    decide_both(rows, alpha, "p_boot_sup", "p_sign_sup", "superior")
    tested = [r for r in rows if r["status"] == "tested"]
    passed = sum(r["passes"] for r in rows)
    over_cap = sum(r["ci_high"] > cap for r in tested)
    summary = {"cells": len(rows), "tested": len(tested), "passed": passed,
               "passed_boot": sum(r["passes_boot"] for r in rows), "passed_sign": sum(r["passes_sign"] for r in rows),
               "disagree": sum(r["passes_disagree"] for r in rows), "superior": sum(r["superior"] for r in rows),
               "over_cap": over_cap, "fails": sum(r["status"] == "fails" for r in rows),
               "largest_ci_high": max((r["ci_high"] for r in tested), default=None),
               "holds": passed >= need and over_cap == 0, "need": need, "cap": cap, "margin": margin}
    return rows, summary


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def report(rows: list[dict], s: dict, alpha: float) -> None:
    level = math.floor((1 - 2 * alpha) * 100)
    print(f"H1: {s['cells']} cells, {s['tested']} tested, {s['passed']} pass under both (bootstrap {s['passed_boot']}, "
          f"sign test {s['passed_sign']}, {s['disagree']} disagree), {s['over_cap']} above the cap {s['cap']}, "
          f"{s['fails']} fail; H1 {'holds' if s['holds'] else 'does not hold'} (needs {s['need']}); "
          f"superior in {s['superior']}")
    for r in rows:
        head = f"  {r['shape']:<14} {r['m']:>7}  "
        if r["status"] != "tested":
            print(head + r["status"] + (f": {r['failures']}" if r.get("failures") else ""))
        else:
            print(head + f"ratio {r['ratio']:.4f}  {level}% clustered BCa [{r['ci_low']:.4f}, {r['ci_high']:.4f}] "
                  f"Holm p {r['p_boot_holm']:.2e}; sign {r['sign_x']}/{r['pairs']} Holm p {r['p_sign_holm']:.2e}; "
                  f"{'pass' if r['passes'] else 'FAIL'}{' (the two disagree)' if r['passes_disagree'] else ''}  "
                  f"vs {r['fastest']}")
        if r.get("absent"):
            print(f"      absent: {r['absent']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--margin", type=float, default=1.02)
    ap.add_argument("--cap", type=float, default=1.10)
    ap.add_argument("--alpha", type=float, default=0.025, help="one-sided, family-wise")
    ap.add_argument("--need", type=int, default=32, help="cells that must pass")
    ap.add_argument("--resamples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=RESAMPLING_SEED)
    ap.add_argument("--family", choices=["h1", "all"], default="h1",
                    help="h1: the 35 cells; all: every cell of the run (exploratory runs), same computations")
    ap.add_argument("--any-pairs", action="store_true", help="do not require the design's 16 pairs (development)")
    ap.add_argument("--verified", type=Path, help="tools/verify_unverified.py's checks (see cells.load)")
    a = ap.parse_args()
    cells = load(a.run, a.verified)
    keys = None if a.family == "h1" else sorted(cells)
    rows, s = decide(cells, keys=keys, margin=a.margin, cap=a.cap, alpha=a.alpha, need=a.need,
                     resamples=a.resamples, seed=a.seed, expected_pairs=None if a.any_pairs else design_pairs())
    if a.out:
        write_csv(a.out, rows, FIELDS)
    report(rows, s, a.alpha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
