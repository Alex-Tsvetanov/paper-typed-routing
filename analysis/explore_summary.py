#!/usr/bin/env python3
"""The headline of an exploratory run (hypotheses-round2.md, section 3.6: miss-heavy rings, the GitHub
table, the long vocabulary, the Zipf ring, mixed-overlap without decoys): per cell, RegexMatcher
v2 against the fastest competitor, as H1 and H2 compare them, without intervals or decisions.

    explore_summary.py RUN_DIR [--verified FILE] [--out FILE.csv]

Per cell (shape, size), with the arms analysis/cells.py lets take part: the median over the
seed pairs of regexmatcher-v2's time over the fastest competitor's (the lowest median), the
two medians, and the net instructions per lookup of both (each process's count minus that
of its loop's null, as analysis/h2_stats.py does). Arms left out are listed with the reason. The run's
own check on every query (RUN_DIR/verified.jsonl, bench/run_grid.sh) is read when --verified is not given.
Pure Python (no NumPy or SciPy). Exploratory: no interval and no decision.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from cells import V2, by_pair, load, sort_cell
from h2_stats import med, net, nulls_of


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--verified", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    verified = a.verified or (a.run / "verified.jsonl" if (a.run / "verified.jsonl").exists() else None)
    cells = load(a.run, verified)
    rows = []
    for (shape, m) in sorted(cells, key=lambda k: (k[0], k[1])):
        arms = cells[(shape, m)]
        srt = sort_cell(arms, shape)
        row = {"shape": shape, "m": m, "competitors": " ".join(sorted(srt.included)),
               "absent": "; ".join(f"{x}: {w}" for x, w in sorted(srt.absent.items())),
               "failures": "; ".join(srt.failures)}
        if srt.v2 is None or not srt.included or srt.failures:
            row["status"] = "fails" if srt.v2 is None or srt.failures else "no competitor"
            rows.append(row)
            print(f"{shape:<14} {m:>8}  {row['status']}: {row['failures'] or row['absent']}")
            continue
        v2 = by_pair(srt.v2, "ns_median")
        comp = {c: by_pair(rs, "ns_median") for c, rs in srt.included.items()}
        fastest = min(comp, key=lambda c: statistics.median(comp[c].values()))
        pairs = sorted(set(v2) & set(comp[fastest]))
        ratio = statistics.median(v2[k] / comp[fastest][k] for k in pairs)
        nulls = nulls_of(arms)
        v2_net = med([net(r, nulls) for r in srt.v2])
        f_net = med([net(r, nulls) for r in srt.included[fastest]])
        row.update({"status": "compared", "pairs": len(pairs), "fastest": fastest, "ratio": ratio,
                    "v2_ns": statistics.median(v2.values()), "fastest_ns": statistics.median(comp[fastest].values()),
                    "v2_net": v2_net, "fastest_net": f_net})
        rows.append(row)
        print(f"{shape:<14} {m:>8}  v2/fastest {ratio:.4f} ({len(pairs)} pairs)  v2 {row['v2_ns']:.1f} ns, "
              f"{fastest} {row['fastest_ns']:.1f} ns  net {v2_net if v2_net is None else round(v2_net, 1)} vs "
              f"{f_net if f_net is None else round(f_net, 1)}" + (f"  absent: {row['absent']}" if row["absent"] else ""))
    compared = [r for r in rows if r.get("status") == "compared"]
    if compared:
        rs = [r["ratio"] for r in compared]
        print(f"{len(compared)} of {len(rows)} cells compared; v2/fastest from {min(rs):.4f} to {max(rs):.4f}; "
              f"{sum(r > 1 for r in rs)} above 1; net instructions above the fastest's in "
              f"{sum(1 for r in compared if r['v2_net'] is not None and r['fastest_net'] is not None and r['v2_net'] > r['fastest_net'])}")
    if a.out:
        keys: list[str] = []
        for r in rows:
            keys += [k for k in r if k not in keys]
        with a.out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
