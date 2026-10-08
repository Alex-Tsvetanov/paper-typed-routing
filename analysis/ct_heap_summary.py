#!/usr/bin/env python3
"""The exploratory follow-up of H7 (hypotheses-round2.md, section 7, last item;
design/round2/engineering.md, 3.4): H7's cell param-last m = 1,000 again, with the compile-time
table copied into a heap block in the same binary (the arm regexmatcher-v2-ct-heap), beside the
run-time table (regexmatcher-v2) and the compile-time table (regexmatcher-v2-ct).

    ct_heap_summary.py RUN_DIR [--verified FILE] [--frozen MAIN_GRID_RUN] [--out FILE.csv]

Per seed pair, from RUN_DIR/cells.jsonl: each arm's median ns per lookup, the ratios heap copy
over run-time table and compile-time over run-time table, and each arm's instructions, cycles,
L1d misses and L1 dTLB misses per lookup (raw: the three arms share one loop and one null). The
three arms' recorded page offsets (table_layout) must be equal in every pair, and every process
usable (analysis/cells.py: status ok, agreeing, verified on every query, by the run's own
verified.jsonl where the agreement pass was cut); otherwise the script stops. With --frozen (the
unpacked main grid), each pair also gets the frozen run's compile-time over run-time ratio, which
names the table seed that stood apart there. Pure Python. Exploratory: no interval, no decision.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

from cells import CT, V2, load, pair, usable

HEAP = "regexmatcher-v2-ct-heap"
CELL = ("param-last", 1000)
ARMS = {"rt": V2, "ct": CT, "heap": HEAP}
COUNTERS = {"ns": "ns_median", "insn": "instructions", "cycles": "cycles", "l1d": "l1d_misses", "dtlb": "dtlb_misses"}


def per_pair(rows: list[dict], arm: str) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for r in rows:
        if not usable(r):
            raise SystemExit(f"ct_heap_summary: {arm} at pair {pair(r)} is not usable: status {r.get('status')}, "
                             f"agrees {r.get('agrees')}, verified_all {r.get('verified_all')}")
        if pair(r) in out:
            raise SystemExit(f"ct_heap_summary: {arm} ran pair {pair(r)} twice")
        out[pair(r)] = r
    return out


def frozen_ratios(run: Path) -> dict[tuple, float]:
    """The main grid's compile-time over run-time ratio per pair, at the same cell."""
    rows: dict[str, dict[tuple, float]] = {V2: {}, CT: {}}
    with (run / "cells.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if '"param-last"' not in line or '"regexmatcher-v2' not in line:
                continue
            r = json.loads(line)
            if (r["shape"], int(r["m"])) == CELL and r["arm"] in rows and r.get("status") == "ok":
                rows[r["arm"]][pair(r)] = float(r["ns_median"])
    return {k: rows[CT][k] / rows[V2][k] for k in rows[V2] if k in rows[CT]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--verified", type=Path)
    ap.add_argument("--frozen", type=Path, help="the unpacked main grid, for its ratio per pair")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    verified = a.verified or (a.run / "verified.jsonl" if (a.run / "verified.jsonl").exists() else None)
    cells = load(a.run, verified)
    if set(cells) != {CELL}:
        raise SystemExit(f"ct_heap_summary: the run holds {sorted(cells)}, not only {CELL}")
    arms = cells[CELL]
    if set(arms) != set(ARMS.values()):
        raise SystemExit(f"ct_heap_summary: the run's arms are {sorted(arms)}, not {sorted(ARMS.values())}")
    by = {k: per_pair(arms[name], name) for k, name in ARMS.items()}
    pairs = sorted(by["rt"])
    if any(sorted(by[k]) != pairs for k in ARMS) or len(pairs) != 16:
        raise SystemExit("ct_heap_summary: the three arms did not run the same sixteen pairs")
    frozen = frozen_ratios(a.frozen) if a.frozen else {}
    rows = []
    for p in pairs:
        layouts = {k: json.dumps(by[k][p].get("table_layout"), sort_keys=True) for k in ARMS}
        if len(set(layouts.values())) != 1:
            raise SystemExit(f"ct_heap_summary: the page offsets differ at pair {p}: {layouts}")
        row: dict = {"table_seed": p[0], "ring_seed": p[1]}
        for c, key in COUNTERS.items():
            for k in ARMS:
                row[f"{k}_{c}"] = float(by[k][p][key])
        row["heap_rt"] = row["heap_ns"] / row["rt_ns"]
        row["ct_rt"] = row["ct_ns"] / row["rt_ns"]
        row["heap_ct"] = row["heap_ns"] / row["ct_ns"]
        row["table_layout"] = layouts["rt"]
        if frozen:
            row["frozen_ct_rt"] = frozen[p]
        rows.append(row)
    for r in rows:
        print(f"{r['table_seed']}:{r['ring_seed']}  heap/rt {r['heap_rt']:.4f}  ct/rt {r['ct_rt']:.4f}"
              + (f" (frozen {r['frozen_ct_rt']:.4f})" if frozen else "")
              + f"  insn rt {r['rt_insn']:.1f} ct {r['ct_insn']:.1f} heap {r['heap_insn']:.1f}"
              f"  l1d {r['rt_l1d']:.3f} {r['ct_l1d']:.3f} {r['heap_l1d']:.3f}"
              f"  dtlb {r['rt_dtlb']:.4f} {r['ct_dtlb']:.4f} {r['heap_dtlb']:.4f}"
              f"  cycles {r['rt_cycles']:.1f} {r['ct_cycles']:.1f} {r['heap_cycles']:.1f}")
    for key in ("heap_rt", "ct_rt"):
        vals = [r[key] for r in rows]
        print(f"{key}: median {statistics.median(vals):.4f} over {len(vals)} pairs, from {min(vals):.4f} to {max(vals):.4f}")
    if a.out:
        with a.out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
