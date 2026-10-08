#!/usr/bin/env python3
"""The ablation arm (hypotheses-round2.md, section 3.6; exploratory, decides nothing): what round 2's
engineering contributed, per cell of the main grid.

    ablation.py RUN_DIR [--out FILE.csv] [--verified FILE]

regexmatcher-v2-r1 is the round-1 header renamed and not re-engineered (step E1 of
design/round2/regexmatcher-v2.md). Per (shape, size) cell of the 35, paired by seed pair, the
median over the pairs of v2's value over the ablation arm's, for lookup time (ns_median),
instructions per lookup net of the null of the same pair (analysis/h2_stats.py's net), build time
(build_s_median) and heap bytes held (table_bytes), with the smallest and largest per-pair ratio
beside each. A cell where either arm has a process that is not usable (analysis/cells.py) is
listed with the reason and has no ratio. No interval and no test.
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from cells import ABLATION, H1_SHAPES, H1_SIZES, V2, load, pair, usable
from h1_stats import write_csv
from h2_stats import net, nulls_of

MEASURES = (("time", "ns_median"), ("instructions_net", None), ("build", "build_s_median"), ("heap", "table_bytes"))


def summarize(cells: dict, keys: list[tuple] | None = None) -> tuple[list[dict], dict]:
    keys = keys if keys is not None else [(s, m) for s in H1_SHAPES for m in H1_SIZES]
    rows = []
    for s, m in keys:
        arms = cells.get((s, m), {})
        v2, ab = arms.get(V2, []), arms.get(ABLATION, [])
        row = {"shape": s, "m": m}
        bad = [a for a, rs in ((V2, v2), (ABLATION, ab)) if not rs or not all(usable(r) for r in rs)]
        if bad:
            row["status"] = f"not compared: {', '.join(bad)} not usable in every process"
            rows.append(row)
            continue
        nulls = nulls_of(arms)
        a_by, b_by = {pair(r): r for r in v2}, {pair(r): r for r in ab}
        pairs = sorted(set(a_by) & set(b_by))
        row.update({"status": "compared", "pairs": len(pairs)})
        for name, key in MEASURES:
            ratios = []
            for p in pairs:
                x = net(a_by[p], nulls) if key is None else a_by[p].get(key)
                y = net(b_by[p], nulls) if key is None else b_by[p].get(key)
                if isinstance(x, (int, float)) and isinstance(y, (int, float)) and y:
                    ratios.append(float(x) / float(y))
            if len(ratios) == len(pairs) and ratios:
                row[f"{name}_ratio"] = statistics.median(ratios)
                row[f"{name}_min"], row[f"{name}_max"] = min(ratios), max(ratios)
        rows.append(row)
    done = [r for r in rows if r["status"] == "compared"]
    summary = {"cells": len(rows), "compared": len(done)}
    for name, _ in MEASURES:
        vals = [r[f"{name}_ratio"] for r in done if f"{name}_ratio" in r]
        if vals:
            summary[f"{name}_ratio_min"], summary[f"{name}_ratio_max"] = min(vals), max(vals)
    return rows, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--verified", type=Path)
    a = ap.parse_args()
    rows, s = summarize(load(a.run, a.verified))
    if a.out:
        write_csv(a.out, rows, list(dict.fromkeys(k for r in rows for k in r)))
    for r in rows:
        if r["status"] != "compared":
            print(f"{r['shape']:<14} {r['m']:>7}  {r['status']}")
            continue
        print(f"{r['shape']:<14} {r['m']:>7}  v2 / ablation: time {r.get('time_ratio', float('nan')):.4f}, net "
              f"instructions {r.get('instructions_net_ratio', float('nan')):.4f}, build {r.get('build_ratio', float('nan')):.4f}, "
              f"heap {r.get('heap_ratio', float('nan')):.4f} ({r['pairs']} pairs)")
    print(f"ablation: {s['compared']} of {s['cells']} cells compared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
