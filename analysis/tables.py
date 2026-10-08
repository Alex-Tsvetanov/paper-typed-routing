#!/usr/bin/env python3
"""Every arm in every cell of a round-2 run, as a table (the paper's supplementary table).

    tables.py RUN_DIR [--out FILE.csv] [--verified FILE]

One row per (arm, shape, size): the number of processes, their statuses, and the median over the
processes of each measure rbench records (ns per lookup, instructions and their net count against
the null of the same pair or the arm's own null pass, branch misses, cycles, L1d, L2 and L1 DTLB
misses, allocations per lookup, build time, bytes allocated by the build, heap bytes held, latency
percentiles, and for the Go arms the time of a call across cgo). A median is left empty when a
process lacks the measure or did not end ok. The arm's role (hypotheses-round2.md, section 3.1)
and whether analysis/cells.py lets it take part are in the row. Descriptive: no test.
"""

from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

from cells import ABLATION, COMPETITORS, CT, NULLS, REFERENCE, V2, classify, load, load_semantics
from h1_stats import write_csv
from h2_stats import net, nulls_of

MEASURES = ["ns_median", "instructions", "branch_misses", "cycles", "l1d_misses", "l2_misses", "dtlb_misses",
            "allocs_per_lookup", "build_s_median", "build_alloc_bytes", "table_bytes", "lat_p50_ns", "lat_p99_ns",
            "ffi_call_ns"]


def role(arm: str) -> str:
    if arm == V2:
        return "under test (H1 to H4)"
    if arm == CT:
        return "under test (H7)"
    if arm == ABLATION:
        return "ablation (exploratory)"
    if arm in COMPETITORS:
        return "competitor"
    if arm in REFERENCE:
        return "reference"
    return "null" if arm in NULLS else "other"


def all_arms(cells: dict) -> list[dict]:
    semantics = load_semantics()
    out = []
    for (shape, m) in sorted(cells, key=lambda k: (k[0], k[1])):
        arms = cells[(shape, m)]
        nulls = nulls_of(arms)
        for arm in sorted(arms):
            rows = arms[arm]
            ok = [r for r in rows if r.get("status") == "ok"]
            kind, why = classify(arm, shape, rows, semantics)
            row = {"arm": arm, "role": role(arm), "shape": shape, "m": m, "processes": len(rows),
                   "statuses": "; ".join(f"{s} {n}" for s, n in sorted(Counter(str(r.get("status")) for r in rows).items())),
                   "takes_part": kind == "ok", "why_not": why}
            for key in MEASURES:
                vals = [r.get(key) for r in ok]
                if ok and len(ok) == len(rows) and all(isinstance(v, (int, float)) for v in vals):
                    row[key] = statistics.median(vals)
            nets = [net(r, nulls) for r in ok]
            if ok and len(ok) == len(rows) and all(v is not None for v in nets):
                row["instructions_net"] = statistics.median(nets)
            out.append(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--verified", type=Path)
    a = ap.parse_args()
    rows = all_arms(load(a.run, a.verified))
    if a.out:
        write_csv(a.out, rows, ["arm", "role", "shape", "m", "processes", "statuses", "takes_part", "why_not",
                                *MEASURES[:2], "instructions_net", *MEASURES[2:]])
    print(f"{len(rows)} arm and cell rows, {sum(r['takes_part'] for r in rows)} taking part")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
