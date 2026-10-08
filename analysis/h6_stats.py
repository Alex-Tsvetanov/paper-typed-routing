#!/usr/bin/env python3
"""H6 of hypotheses-round2.md from a T1 run of t1/run_h6.sh and the T0 publication run.

    h6_stats.py T1_RUN_DIR --t0 T0_RUN_DIR [--out FILE.csv] [--resamples 10000] [--seed SEED]
                [--min-pairs 6] [--verified FILE]

The paper's minimal server, one binary with three router arms (h6-v1, RegexMatcher v1 behind its
wrapper, the reference; h6-v2; h6-null), in nine cells: the seven shapes at m = 10, and rest and
param-last at m = 10,000 (T1_RUN_DIR/<shape>-<m>/t1/windows.jsonl, lab/t1's rows).

A pair is a round of mirrored windows (v1, v2, null, null, v2, v1). It is used only if all six of
its windows are valid as t1.py marks them; a pair with an invalid window is left out and listed
with the reasons. Per pair, each arm's X is its mean req/s over its two windows; the ratio is
X_v2 / X_v1, and D_meas = 1/X_v1 - 1/X_v2, the measured difference in time per request.
D_T0 = t_v1 - t_v2, the difference of the two arms' median lookup times (ns_median) in the T0
publication run, in the cell of the same shape and size at pair (111, 211), the pair whose table
and ring H6 serves; one value per cell. The carry-over of a pair is D_meas / D_T0 (both in
seconds). Per cell, each statistic is the median over pairs with its two-sided 95% BCa interval
over pairs, computed as for H1 (analysis/stats.py: 10,000 resamples, fixed seed, ties as half,
acceleration from the jackknife over pairs).
  (a) direction: holds in a cell if the lower bound of the ratio's interval is above 1.00; H6(a)
      holds only if it holds in all nine cells.
  (b) carry-over: holds in a cell if the lower bound of the carry-over's interval is at least 0.5
      (and D_T0 is positive: if v2 was not faster at T0 the carry-over has no meaning, and the
      cell does not hold); H6(b) holds only if it holds in all nine cells.
No multiplicity adjustment: each part requires every one of its cells. A cell with fewer than
MIN_PAIRS valid pairs (6, rule D9) cannot hold. Reported beside each cell, not tested: the null
arm's time per request, 1/X_null (median over pairs); the ratio predicted from T0,
P = (1/X_null + t_v1) / (1/X_null + t_v2); the measured ratio over P; and the exact sign test of
each part (the pairs above 1.00, and the pairs whose carry-over is at least 0.5), which decides
nothing. One generator, seeded with SEED, serves the cells in the order below, each drawing the
resamples of (a) then those of (b).
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import numpy as np

from cells import V1, V2, load, pair, usable
from h1_stats import RESAMPLING_SEED, write_csv
from stats import bca, bca_bound, fastest_ratio, sign_p

CELLS = [f"{s}-10" for s in ("static", "param-last", "param-first", "rest", "wild", "mixed-disjoint",
                             "mixed-overlap")] + ["rest-10000", "param-last-10000"]
ARMS = ("h6-v1", "h6-v2", "h6-null")
H6_PAIR = (111, 211)


def pairs_of(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """The used pairs ({arm: mean req/s}) and the rounds left out, with why."""
    by_round: dict[int, list[dict]] = {}
    for r in rows:
        by_round.setdefault(int(r["round"]), []).append(r)
    used, left = [], []
    for k in sorted(by_round):
        rs = by_round[k]
        per = {a: [r for r in rs if r["arm"] == a] for a in ARMS}
        bad = [r for r in rs if not r.get("valid")]
        if bad or any(len(v) != 2 for v in per.values()):
            why = "; ".join(f"{r.get('tag')}: {', '.join(r.get('invalid_reasons') or [])}" for r in bad) \
                or ", ".join(f"{len(v)} {a} windows" for a, v in per.items())
            left.append(f"round {k}: {why}")
            continue
        used.append({a: statistics.fmean(r["rps"] for r in v) for a, v in per.items()})
    return used, left


def t0_times(cells: dict, cell: str) -> tuple[float | None, float | None]:
    """Each arm's ns_median in its process at pair (111, 211) in the T0 cell, if that process is
    usable (ended ok and agreed on every query, analysis/cells.py); else None."""
    shape, m = cell.rsplit("-", 1)
    arms = cells.get((shape, int(m)), {})

    def one(arm: str) -> float | None:
        rs = [r for r in arms.get(arm, []) if pair(r) == H6_PAIR and usable(r)]
        return float(rs[0]["ns_median"]) if len(rs) == 1 else None
    return one(V1), one(V2)


def sign_above(values: list[float], bound: float, strict: bool) -> tuple[int, float]:
    x = sum(1 for v in values if (v > bound if strict else v >= bound))
    return x, float(sign_p(x, len(values)))


def decide(t1: dict[str, list[dict]], t0: dict, *, resamples: int = 10000, seed: int = RESAMPLING_SEED,
           min_pairs: int = 6, carry_bound: float = 0.5) -> tuple[list[dict], dict]:
    rng = np.random.default_rng(seed)
    out = []
    for cell in CELLS:
        used, left = pairs_of(t1.get(cell, []))
        t_v1, t_v2 = t0_times(t0, cell)
        row = {"cell": cell, "pairs": len(used), "left_out": " | ".join(left), "t0_v1_ns": t_v1, "t0_v2_ns": t_v2,
               "a_holds": False, "b_holds": False}
        if t_v1 is None or t_v2 is None:
            row["status"] = "no T0 lookup time at pair (111, 211)"
            out.append(row)
            continue
        d_t0 = (t_v1 - t_v2) * 1e-9
        row["d_t0_ns"] = t_v1 - t_v2
        if len(used) < min_pairs:
            row["status"] = "too few pairs"
            out.append(row)
            continue
        x1 = np.array([u["h6-v1"] for u in used])
        x2 = np.array([u["h6-v2"] for u in used])
        xn = np.array([u["h6-null"] for u in used])
        ratio = bca(x2, x1[None, :], fastest_ratio, None, resamples, rng)
        d_meas = 1 / x1 - 1 / x2
        row.update({"status": "tested", "ratio": ratio.theta, "ratio_ci_low": bca_bound(ratio, 0.025),
                    "ratio_ci_high": bca_bound(ratio, 0.975), "v1_rps": float(np.median(x1)),
                    "v2_rps": float(np.median(x2)), "null_rps": float(np.median(xn)),
                    "d_meas_ns": float(np.median(d_meas)) * 1e9})
        row["a_holds"] = row["ratio_ci_low"] > 1.0
        row["sign_a_x"], row["p_sign_a"] = sign_above(list(x2 / x1), 1.0, strict=True)
        if d_t0 > 0:
            carry = bca(d_meas, np.full((1, len(used)), d_t0), fastest_ratio, None, resamples, rng)
            row.update({"carry": carry.theta, "carry_ci_low": bca_bound(carry, 0.025),
                        "carry_ci_high": bca_bound(carry, 0.975)})
            row["b_holds"] = row["carry_ci_low"] >= carry_bound
            row["sign_b_x"], row["p_sign_b"] = sign_above(list(d_meas / d_t0), carry_bound, strict=False)
        else:
            row["b_status"] = "D_T0 is not positive: v2 was not faster than v1 at T0"
        null_s = float(np.median(1 / xn))
        row["null_us_per_request"] = null_s * 1e6
        row["predicted_ratio"] = (null_s + t_v1 * 1e-9) / (null_s + t_v2 * 1e-9)
        row["measured_over_predicted"] = row["ratio"] / row["predicted_ratio"]
        out.append(row)
    summary = {"cells": len(out), "tested": sum(r["status"] == "tested" for r in out),
               "a_held": sum(r["a_holds"] for r in out), "b_held": sum(r["b_holds"] for r in out)}
    summary["a_holds"] = summary["a_held"] == len(CELLS)
    summary["b_holds"] = summary["b_held"] == len(CELLS)
    return out, summary


def read_t1(run: Path) -> dict[str, list[dict]]:
    t1 = {}
    for cell in CELLS:
        f = run / cell / "t1" / "windows.jsonl"
        t1[cell] = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []
    return t1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--t0", type=Path, required=True, help="the T0 publication run (its cells.jsonl)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--resamples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=RESAMPLING_SEED)
    ap.add_argument("--min-pairs", type=int, default=6)
    ap.add_argument("--verified", type=Path)
    a = ap.parse_args()
    rows, s = decide(read_t1(a.run), load(a.t0, a.verified), resamples=a.resamples, seed=a.seed, min_pairs=a.min_pairs)
    if a.out:
        write_csv(a.out, rows, list(dict.fromkeys(k for r in rows for k in r)))
    for r in rows:
        head = f"{r['cell']:<18} "
        if r["status"] != "tested":
            print(head + f"{r['status']} ({r['pairs']} valid pairs)" + (f"; left out: {r['left_out']}" if r["left_out"] else ""))
            continue
        print(head + f"v2/v1 {r['ratio']:.4f} [{r['ratio_ci_low']:.4f}, {r['ratio_ci_high']:.4f}] "
              f"{'(a) holds' if r['a_holds'] else '(a) does not hold'}; "
              + (f"carry-over {r['carry']:.3f} [{r['carry_ci_low']:.3f}, {r['carry_ci_high']:.3f}] "
                 f"{'(b) holds' if r['b_holds'] else '(b) does not hold'}" if "carry" in r else r.get("b_status", ""))
              + f"; {r['pairs']} pairs; null {r['null_us_per_request']:.2f} us/request, predicted {r['predicted_ratio']:.4f}, "
              f"measured/predicted {r['measured_over_predicted']:.4f}" + (f"; left out: {r['left_out']}" if r["left_out"] else ""))
    print(f"H6(a): {'holds' if s['a_holds'] else 'does not hold'} ({s['a_held']} of {s['cells']} cells); "
          f"H6(b): {'holds' if s['b_holds'] else 'does not hold'} ({s['b_held']} of {s['cells']} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
