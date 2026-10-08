#!/usr/bin/env python3
"""H2 of hypotheses-round2.md from a publication run: instructions and branch misses per lookup.

    h2_stats.py RUN_DIR [--out results/h2.csv] [--family h1|all] [--any-pairs] [--verified FILE]

In every cell, RegexMatcher v2 (regexmatcher-v2) must execute no more instructions per lookup
than the fastest competitor of the cell (the one with the lowest median time, as in H1), and take
no more branch misses per lookup than the median competitor (the median over the included
competitors of each one's median over its processes). Instructions are compared net against net:
each process's count minus that of the null of its own loop, in the same process for an arm with
its own null pass, else in the same cell and seed pair:
- loop_null "null": the C++ null arm (arms/null.cpp), for the arms whose lookups the harness calls
  and that answer 405 themselves (v2);
- loop_null "null-no405": the second C++ null arm (arms/null_no405.cpp), for the arms whose lookups
  the harness calls and to which it applies its 405 rule (the C++ and Rust competitors): the same
  call, plus the harness's test of the answer against "no route", so that test is netted out of
  those arms as it is absent from v2;
- loop_null "own": the arm's own null pass (the Go competitors: the same loop over the same loaded
  data, with a call that reads only the path length instead of the router).
Branch misses are compared raw (not net). The median competitor's branch misses are also reported
over the competitors whose timed passes were not cut to a prefix of the ring (a cut arm repeats a
short prefix, which favours its predictors), deciding nothing; the cut ones are named.
The value of a cell is the median over its 16 processes. The comparison is strict (no tolerance)
and has no interval: the medians are compared as they are, the raw counts and the range of the
net counts over the processes beside them. A loss is reported in the cell where it occurs, with
the memory-side counters (L1d, L2 and L1 DTLB misses per lookup) of v2 and of the fastest
competitor. Which competitors take part, and which cells cannot be judged, is decided by
analysis/cells.py; every absent competitor is printed.
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from cells import H1_SHAPES, H1_SIZES, NULLS, V2, cut, design_pairs, load, pair, sort_cell
from h1_stats import write_csv

FIELDS = ["shape", "m", "status", "fastest", "competitors", "absent", "failures", "v2_instructions_net",
          "fastest_instructions_net", "v2_net_range", "fastest_net_range", "v2_instructions_raw",
          "fastest_instructions_raw", "fastest_loop_null", "instructions_hold", "v2_branch_misses",
          "median_competitor_branch_misses", "branch_misses_hold", "holds", "median_competitor_branch_misses_uncut",
          "cut_competitors", "v2_l1d_misses", "fastest_l1d_misses",
          "v2_l2_misses", "fastest_l2_misses", "v2_dtlb_misses", "fastest_dtlb_misses"]
MEMORY = ("l1d_misses", "l2_misses", "dtlb_misses")


def nulls_of(arms: dict[str, list[dict]]) -> dict[tuple, float]:
    """Each null arm's instructions per lookup in the cell, keyed by (null arm, seed pair)."""
    return {(name, pair(r)): float(r["instructions"]) for name in sorted(NULLS) for r in arms.get(name, [])
            if r.get("status") == "ok" and isinstance(r.get("instructions"), (int, float))}


def net(r: dict, nulls: dict[tuple, float]) -> float | None:
    """One process's instructions per lookup net of its loop's null, or None."""
    if not isinstance(r.get("instructions"), (int, float)):
        return None
    loop = r.get("loop_null", "null" if r.get("throughput_loop") == "harness" else "")
    if loop == "own":
        base = r.get("null_instructions")
    elif loop in NULLS:
        base = nulls.get((loop, pair(r)))
    else:
        base = None
    return None if not isinstance(base, (int, float)) else float(r["instructions"]) - float(base)


def med(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if len(vals) == len(values) and vals else None


def med_key(rows: list[dict], key: str) -> float | None:
    return med([float(r[key]) if isinstance(r.get(key), (int, float)) else None for r in rows])


def span(values: list[float | None]) -> str:
    vals = [v for v in values if v is not None]
    return f"{min(vals):.1f} to {max(vals):.1f}" if vals else ""


def decide(cells: dict, *, keys: list[tuple] | None = None, v2: str = V2,
           expected_pairs: list[tuple] | None = None) -> tuple[list[dict], dict]:
    keys = keys if keys is not None else [(s, m) for s in H1_SHAPES for m in H1_SIZES]
    rows = []
    for shape, m in keys:
        arms = cells.get((shape, m), {})
        srt = sort_cell(arms, shape, v2=v2, expected_pairs=expected_pairs)
        row = {"shape": shape, "m": m, "competitors": " ".join(sorted(srt.included)),
               "absent": "; ".join(f"{a}: {w}" for a, w in sorted(srt.absent.items())),
               "failures": "; ".join(srt.failures), "holds": False}
        if srt.failures or srt.v2 is None or not srt.included:
            row["status"] = "fails" if srt.failures or srt.v2 is None else "no competitor holds the table"
            rows.append(row)
            continue
        nulls = nulls_of(arms)
        fastest = min(srt.included, key=lambda a: statistics.median(r["ns_median"] for r in srt.included[a]))
        v2_nets = [net(r, nulls) for r in srt.v2]
        f_nets = [net(r, nulls) for r in srt.included[fastest]]
        v2_net, f_net = med(v2_nets), med(f_nets)
        if v2_net is None or f_net is None:
            row["status"] = "fails"
            row["failures"] = "a null count is missing for " + (v2 if v2_net is None else fastest)
            rows.append(row)
            continue
        v2_bm = statistics.median(r["branch_misses"] for r in srt.v2)
        comp_bm = statistics.median(statistics.median(r["branch_misses"] for r in rs) for rs in srt.included.values())
        uncut = [rs for rs in srt.included.values() if not cut(rs)]
        comp_bm_uncut = (statistics.median(statistics.median(r["branch_misses"] for r in rs) for rs in uncut)
                         if uncut else None)
        row.update({"status": "judged", "fastest": fastest,
                    "v2_instructions_net": v2_net, "fastest_instructions_net": f_net,
                    "v2_net_range": span(v2_nets), "fastest_net_range": span(f_nets),
                    "v2_instructions_raw": statistics.median(r["instructions"] for r in srt.v2),
                    "fastest_instructions_raw": statistics.median(r["instructions"] for r in srt.included[fastest]),
                    "fastest_loop_null": srt.included[fastest][0].get("loop_null", ""),
                    "instructions_hold": v2_net <= f_net,
                    "v2_branch_misses": v2_bm, "median_competitor_branch_misses": comp_bm,
                    "branch_misses_hold": v2_bm <= comp_bm,
                    "median_competitor_branch_misses_uncut": comp_bm_uncut,
                    "cut_competitors": " ".join(sorted(a for a, rs in srt.included.items() if cut(rs)))})
        row["holds"] = row["instructions_hold"] and row["branch_misses_hold"]
        for k in MEMORY:
            row[f"v2_{k}"] = med_key(srt.v2, k)
            row[f"fastest_{k}"] = med_key(srt.included[fastest], k)
        rows.append(row)
    judged = [r for r in rows if r["status"] == "judged"]
    summary = {"cells": len(rows), "judged": len(judged), "held": sum(r["holds"] for r in judged),
               "lost": [f"{r['shape']} {r['m']}" for r in judged if not r["holds"]],
               "lost_instructions": sum(not r["instructions_hold"] for r in judged),
               "lost_branch_misses": sum(not r["branch_misses_hold"] for r in judged),
               "not_judged": len(rows) - len(judged)}
    summary["holds"] = summary["held"] == len(rows)
    return rows, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--family", choices=["h1", "all"], default="h1")
    ap.add_argument("--any-pairs", action="store_true", help="do not require the design's 16 pairs (development)")
    ap.add_argument("--verified", type=Path, help="tools/verify_unverified.py's checks (see cells.load)")
    a = ap.parse_args()
    cells = load(a.run, a.verified)
    rows, s = decide(cells, keys=None if a.family == "h1" else sorted(cells),
                     expected_pairs=None if a.any_pairs else design_pairs())
    if a.out:
        write_csv(a.out, rows, FIELDS)
    print(f"H2: {s['cells']} cells, {s['judged']} judged, {s['held']} hold, lost in {len(s['lost'])} "
          f"({', '.join(s['lost']) or 'none'}), {s['not_judged']} cannot be judged; "
          f"H2 {'holds' if s['holds'] else 'does not hold'}")
    for r in rows:
        head = f"  {r['shape']:<14} {r['m']:>7}  "
        if r["status"] != "judged":
            print(head + r["status"] + (f": {r['failures']}" if r.get("failures") else ""))
            continue
        print(head + f"instructions net {r['v2_instructions_net']:.1f} vs {r['fastest']} "
              f"{r['fastest_instructions_net']:.1f} [{r['v2_net_range']} vs {r['fastest_net_range']}] "
              f"(raw {r['v2_instructions_raw']:.1f} vs {r['fastest_instructions_raw']:.1f}) "
              f"{'holds' if r['instructions_hold'] else 'LOST'}; branch misses {r['v2_branch_misses']:.2f} vs median "
              f"{r['median_competitor_branch_misses']:.2f} {'holds' if r['branch_misses_hold'] else 'LOST'}")
        if not r["holds"]:
            print("      memory side: " + ", ".join(f"{k} {r[f'v2_{k}']} vs {r[f'fastest_{k}']}" for k in MEMORY))
        if r.get("absent"):
            print(f"      absent: {r['absent']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
