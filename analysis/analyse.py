#!/usr/bin/env python3
"""The whole round-2 analysis of a publication run (hypotheses-round2.md), in one place.

    analyse.py RUN_DIR --out-dir DIR [--t1 T1_RUN_DIR] [--ct-costs CT_DIR] [--verified FILE]
               [--resamples 10000] [--seed SEED] [--any-pairs] [--macros FILE]

RUN_DIR is run_baseline.sh's run (cells.jsonl, probes.jsonl, provenance.txt); T1_RUN_DIR is
t1/run_h6.sh's; CT_DIR is bench/ct_cost_run.sh's; FILE of --verified is tools/verify_unverified.py's
check on every query of the processes the agreement budget cut, which bench/run_grid.sh writes
as RUN_DIR/verified.jsonl at the end of the grid (the default when that file exists). Writes into DIR: h1.csv, h2.csv, h3.csv,
h4.csv, h5b.csv, h7.csv (h7_costs.csv with --ct-costs), h6.csv (with --t1), ablation.csv,
all_arms.csv, and summary.json, every decision and count the scripts computed with the run's
provenance; then analysis/macros.py writes the macros from summary.json alone (--macros, default
DIR/macros.tex). Each hypothesis's bootstrap has its own generator, seeded with SEED (H1: the
cells in family order; H7: likewise; H6: the nine cells in order).
--any-pairs lifts the check that v2's pairs are the design's sixteen: development grids only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import ablation
import h1_stats
import h2_stats
import h347_stats
import h5_stats
import h6_stats
import macros
import tables
from cells import R, design_pairs, load
from h1_stats import RESAMPLING_SEED, write_csv


def key_values(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition(": ")
            if sep:
                out[k.strip()] = v.strip()
    return out


def fields(rows: list[dict]) -> list[str]:
    return list(dict.fromkeys(k for r in rows for k in r))


def analyse(run: Path, out: Path, *, t1: Path | None = None, ct_costs: Path | None = None, verified: Path | None = None,
            resamples: int = 10000, seed: int = RESAMPLING_SEED, any_pairs: bool = False) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if verified is None and (run / "verified.jsonl").exists():
        verified = run / "verified.jsonl"
    cells = load(run, verified)
    pairs = None if any_pairs else design_pairs()
    summary: dict = {"run": str(run), "verified": str(verified) if verified else None,
                     "provenance": key_values(run / "provenance.txt"),
                     "env": key_values(run / "env.txt"), "resamples": resamples, "resampling_seed": seed,
                     "design_pairs_required": pairs is not None, "reps": R}

    rows, s = h1_stats.decide(cells, resamples=resamples, seed=seed, expected_pairs=pairs)
    write_csv(out / "h1.csv", rows, h1_stats.FIELDS)
    summary["h1"], summary["h1_cells"] = s, rows
    rows, s = h2_stats.decide(cells, expected_pairs=pairs)
    write_csv(out / "h2.csv", rows, h2_stats.FIELDS)
    summary["h2"] = s
    rows, s = h347_stats.h3(cells)
    write_csv(out / "h3.csv", rows or [{"arm": "", "allocs_per_lookup": "none above 0"}],
              ["arm", "shape", "m", "table_seed", "ring_seed", "allocs_per_lookup"])
    summary["h3"] = s
    rows, s = h347_stats.h4(cells, expected_pairs=pairs)
    write_csv(out / "h4.csv", rows, fields(rows))
    summary["h4"] = s
    rows, s = h347_stats.h7(cells, resamples=resamples, seed=seed, expected_pairs=pairs)
    write_csv(out / "h7.csv", rows, fields(rows))
    summary["h7"], summary["h7_cells"] = s, rows
    if ct_costs is not None:
        costs = h347_stats.h7_costs(ct_costs)
        write_csv(out / "h7_costs.csv", costs, fields(costs))
        summary["h7_costs"] = {"tables": len(costs), "provenance": key_values(ct_costs / "ct-provenance.txt")}
    probes_file = run / "probes.jsonl"
    probes = [json.loads(x) for x in probes_file.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if probes_file.exists() else []
    rows, s = h5_stats.decide(probes)
    write_csv(out / "h5b.csv", rows, ["arm", "case", "passed", "failed"])
    summary["h5b"] = s
    if t1 is not None:
        rows, s = h6_stats.decide(h6_stats.read_t1(t1), cells, resamples=resamples, seed=seed)
        write_csv(out / "h6.csv", rows, fields(rows))
        summary["h6"], summary["h6_cells"] = s, rows
        summary["h6_provenance"] = key_values(t1 / "provenance.txt")
    rows, s = ablation.summarize(cells)
    write_csv(out / "ablation.csv", rows, fields(rows))
    summary["ablation"] = s
    rows = tables.all_arms(cells)
    write_csv(out / "all_arms.csv", rows, fields(rows))
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--t1", type=Path)
    ap.add_argument("--ct-costs", type=Path)
    ap.add_argument("--verified", type=Path)
    ap.add_argument("--resamples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=RESAMPLING_SEED)
    ap.add_argument("--any-pairs", action="store_true")
    ap.add_argument("--macros", type=Path)
    a = ap.parse_args()
    s = analyse(a.run, a.out_dir, t1=a.t1, ct_costs=a.ct_costs, verified=a.verified, resamples=a.resamples,
                seed=a.seed, any_pairs=a.any_pairs)
    target = a.macros or a.out_dir / "macros.tex"
    target.write_text(macros.render(s), encoding="utf-8")
    h1, h2, h7 = s["h1"], s["h2"], s["h7"]
    print(f"H1 {h1['passed']} of {h1['cells']} pass ({'holds' if h1['holds'] else 'does not hold'}); "
          f"H2 {h2['held']} of {h2['cells']} ({'holds' if h2['holds'] else 'does not hold'}); "
          f"H3 {'holds' if s['h3']['holds'] else 'does not hold'}; H4 {'holds' if s['h4']['holds'] else 'does not hold'}; "
          f"H5(b) {'holds' if s['h5b']['holds'] else 'does not hold'}; "
          f"H7 {h7['held']} of {h7['cells']} ({'holds' if h7['holds'] else 'does not hold'})"
          + (f"; H6(a) {s['h6']['a_held']} of 9, H6(b) {s['h6']['b_held']} of 9" if "h6" in s else ""))
    print(f"wrote {a.out_dir} and {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
