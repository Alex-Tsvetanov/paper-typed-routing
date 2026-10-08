#!/usr/bin/env python3
"""H3, H4 and H7 of hypotheses-round2.md from a publication run, and H7's costs.

    h347_stats.py RUN_DIR [--out-dir DIR] [--resamples 10000] [--seed SEED] [--any-pairs]
                  [--verified FILE] [--ct-costs CT_DIR]

H3: allocations per lookup (allocs_per_lookup, counted in the allocation pass) of RegexMatcher v2
(regexmatcher-v2) in every process of every cell of the 35; H3 holds if every cell has all its
processes ok and every value is 0. The compile-time arm and the ablation arm are reported beside.

H4, per (shape, size) cell against the competitors included in that cell (analysis/cells.py), on
the cells' medians over processes: v2's build time (build_s_median, the median over processes)
against the median of the included competitors' build times; at m = 100,000 the build time
against 1 s; the heap bytes v2's table holds (table_bytes: malloc's live bytes after the build,
and for the Go arms the Go heap's live bytes after a collection, as rbench records them) against
twice the smallest included competitor's. H4 holds if all three hold in every cell.

H7, per cell at m <= 1,000 (21 cells): the ratio regexmatcher-v2-ct / regexmatcher-v2 of ns per
lookup, paired by seed pair; the median of the per-pair ratios. A cell holds only if both hold at
one-sided alpha = 0.025, per cell (no multiplicity adjustment; H7 requires every cell): the upper
bound of the two-sided 95% clustered BCa interval (table seeds resampled, analysis/stats.py) is at
most 1.02, and the exact sign test (13 of 16 pairs below 1.02). The interval over pairs is reported
beside. One generator, seeded with SEED, serves the cells in order (shapes, then sizes), each
cell drawing the clustered resamples, then those over pairs.

H7's costs (--ct-costs, bench/ct_cost_run.sh's output directory): per compile-time table, the
compile time of its translation unit at -j1, the object size as the sum of its loadable ELF
sections (text, rodata, data, bss; bench/ct_costs.py's loadable_bytes), and the object file's
size beside it with the part of the file that is not loadable (ELF header, symbol and string
tables, relocations, and the padding of sections to their alignment); and clang's
constant-evaluation budget from bench/ct_steps.py.

Writes h3.csv, h4.csv, h7.csv (and h7_costs.csv) and prints every cell.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import numpy as np

from cells import ABLATION, CT, H1_SHAPES, H1_SIZES, H7_SIZES, V2, design_pairs, load, paired, sort_cell, usable
from h1_stats import RESAMPLING_SEED, write_csv
from stats import bca, bca_bound, fastest_ratio, sign_test


def med(rows: list[dict], key: str) -> float | None:
    vals = [float(r[key]) for r in rows if isinstance(r.get(key), (int, float))]
    return statistics.median(vals) if vals and len(vals) == len(rows) else None


def h1_keys() -> list[tuple]:
    return [(s, m) for s in H1_SHAPES for m in H1_SIZES]


def h3(cells: dict, keys: list[tuple] | None = None) -> tuple[list[dict], dict]:
    keys = keys if keys is not None else h1_keys()
    nonzero, per_arm = [], {}
    for arm in (V2, CT, ABLATION):
        worst, n, missing = 0.0, 0, []
        for k in keys:
            rows = cells.get(k, {}).get(arm, [])
            if arm == CT and k[1] not in H7_SIZES:
                continue
            ok = [r for r in rows if r.get("status") == "ok"]
            if not rows or len(ok) != len(rows):
                missing.append(f"{k[0]} {k[1]}")
            for r in ok:
                v = r.get("allocs_per_lookup")
                n += 1
                if not isinstance(v, (int, float)):
                    missing.append(f"{k[0]} {k[1]} (no count)")
                    continue
                worst = max(worst, float(v))
                if v != 0:
                    nonzero.append({"arm": arm, "shape": k[0], "m": k[1], "table_seed": r.get("table_seed"),
                                    "ring_seed": r.get("ring_seed"), "allocs_per_lookup": v})
        per_arm[arm] = {"processes": n, "largest": worst, "not_measured": missing}
    v = per_arm[V2]
    summary = {"arms": per_arm, "holds": v["largest"] == 0 and not v["not_measured"] and v["processes"] > 0}
    return nonzero, summary


def h4(cells: dict, keys: list[tuple] | None = None, expected_pairs: list[tuple] | None = None,
       v2: str = V2) -> tuple[list[dict], dict]:
    keys = keys if keys is not None else h1_keys()
    rows, lost = [], []
    for s, m in keys:
        arms = cells.get((s, m), {})
        srt = sort_cell(arms, s, v2=v2, expected_pairs=expected_pairs)
        if srt.failures or srt.v2 is None or not srt.included:
            rows.append({"shape": s, "m": m, "status": "fails" if srt.failures or srt.v2 is None else "no competitor",
                         "failures": "; ".join(srt.failures), "holds": False})
            lost.append(f"{s} {m} (not judged)")
            continue
        b, tb = med(srt.v2, "build_s_median"), med(srt.v2, "table_bytes")
        comp_b = {c: med(rs, "build_s_median") for c, rs in srt.included.items()}
        comp_t = {c: med(rs, "table_bytes") for c, rs in srt.included.items()}
        comp_b = {c: x for c, x in comp_b.items() if x is not None}
        comp_t = {c: x for c, x in comp_t.items() if x is not None}
        if b is None or tb is None or not comp_b or not comp_t:
            rows.append({"shape": s, "m": m, "status": "fails", "failures": "a build time or heap size is missing",
                         "holds": False})
            lost.append(f"{s} {m} (not judged)")
            continue
        median_b = statistics.median(comp_b.values())
        smallest = min(comp_t, key=comp_t.get)
        ok_build, ok_1s, ok_heap = b <= median_b, (m != 100000 or b < 1.0), tb <= 2 * comp_t[smallest]
        row = {"shape": s, "m": m, "status": "judged", "build_s": b, "median_competitor_build_s": median_b,
               "build_holds": ok_build, "below_1s": ok_1s if m == 100000 else "", "table_bytes": tb,
               "smallest_competitor": smallest, "smallest_competitor_bytes": comp_t[smallest], "heap_holds": ok_heap,
               "build_alloc_bytes": med(srt.v2, "build_alloc_bytes"), "competitors": " ".join(sorted(srt.included)),
               "absent": "; ".join(f"{a}: {w}" for a, w in sorted(srt.absent.items())),
               "holds": ok_build and ok_1s and ok_heap}
        rows.append(row)
        if not row["holds"]:
            lost.append(f"{s} {m}")
    judged = [r for r in rows if r["status"] == "judged"]
    summary = {"cells": len(rows), "judged": len(judged), "lost": lost,
               "lost_build": sum(not r["build_holds"] for r in judged),
               "lost_1s": sum(r["below_1s"] is False for r in judged),
               "lost_heap": sum(not r["heap_holds"] for r in judged), "holds": not lost}
    return rows, summary


def h7(cells: dict, *, keys: list[tuple] | None = None, resamples: int = 10000, seed: int = RESAMPLING_SEED,
       margin: float = 1.02, alpha: float = 0.025, expected_pairs: list[tuple] | None = None) -> tuple[list[dict], dict]:
    keys = keys if keys is not None else [(s, m) for s in H1_SHAPES for m in H7_SIZES]
    rng = np.random.default_rng(seed)
    rows = []
    for s, m in keys:
        arms = cells.get((s, m), {})
        ct_all, rt_all = arms.get(CT, []), arms.get(V2, [])
        ct = [r for r in ct_all if usable(r)]
        rt = [r for r in rt_all if usable(r)]
        why = ""
        if not ct_all or len(ct) != len(ct_all) or not rt_all or len(rt) != len(rt_all):
            why = "a process of either arm is not ok, or not verified on every query"
        pairs, ctv, rtv = paired(ct, rt, "ns_median")
        if not why and (len(pairs) != len(ct) or len(pairs) != len(rt)):
            why = "the two arms ran different seed pairs"
        if not why and expected_pairs is not None and pairs != sorted(expected_pairs):
            why = "the seed pairs are not the design's"
        if why:
            rows.append({"shape": s, "m": m, "status": "fails", "failures": why, "holds": False})
            continue
        ctv, rtv = np.array(ctv), np.array([rtv])
        clustered = bca(ctv, rtv, fastest_ratio, [p[0] for p in pairs], resamples, rng)
        ratios = list(ctv / rtv[0])
        x, p = sign_test(ratios, margin)
        hi = bca_bound(clustered, 1 - alpha)
        row = {"shape": s, "m": m, "status": "tested", "pairs": len(pairs), "ratio": clustered.theta,
               "ci_low": bca_bound(clustered, alpha), "ci_high": hi, "boot_holds": hi <= margin,
               "sign_x": x, "p_sign": p, "sign_holds": p <= alpha, "max_pair_ratio": max(ratios),
               "ct_ns": float(np.median(ctv)), "rt_ns": float(np.median(rtv))}
        row["holds"] = row["boot_holds"] and row["sign_holds"]
        row["disagree"] = row["boot_holds"] != row["sign_holds"]
        rows.append(row)
    tested = [r for r in rows if r["status"] == "tested"]
    summary = {"cells": len(rows), "tested": len(tested), "held": sum(r["holds"] for r in rows),
               "held_boot": sum(r.get("boot_holds", False) for r in rows),
               "held_sign": sum(r.get("sign_holds", False) for r in rows),
               "disagree": sum(r.get("disagree", False) for r in rows),
               "largest_ci_high": max((r["ci_high"] for r in tested), default=None),
               "fewest_below": min((r["sign_x"] for r in tested), default=None)}
    summary["holds"] = summary["held"] == len(rows)
    return rows, summary


def h7_costs(ct_dir: Path) -> list[dict]:
    """bench/ct_cost_run.sh's ct_costs.jsonl and ct_steps.jsonl, one row per table."""
    def jl(p: Path) -> list[dict]:
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
    steps = {r["table"]: r for r in jl(ct_dir / "ct_steps.jsonl")}
    rows = []
    for r in jl(ct_dir / "ct_costs.jsonl"):
        name = f"{r['shape'].replace('-', '_')}_{r['m']}" + (f"_s{r['table_seed']}" if r.get("table_seed") else "")
        st = steps.get(name, {})
        obj, load_b = r.get("object_bytes"), r.get("loadable_bytes")
        rows.append({"table": name, "shape": r["shape"], "m": r["m"], "table_seed": r.get("table_seed"),
                     "compile_s": r.get("compile_s"), "loadable_bytes": load_b, "text_bytes": r.get("text_bytes"),
                     "rodata_bytes": r.get("rodata_bytes"), "data_bytes": r.get("data_bytes"),
                     "bss_bytes": r.get("bss_bytes"), "object_bytes": obj,
                     "object_not_loadable_bytes": obj - load_b if isinstance(obj, int) and isinstance(load_b, int) else None,
                     "steps_min_passed": st.get("steps_min_passed"), "steps_max_failed": st.get("steps_max_failed")})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--resamples", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=RESAMPLING_SEED)
    ap.add_argument("--any-pairs", action="store_true", help="do not require the design's 16 pairs (development)")
    ap.add_argument("--verified", type=Path, help="tools/verify_unverified.py's checks (see cells.load)")
    ap.add_argument("--ct-costs", type=Path, help="bench/ct_cost_run.sh's output directory")
    a = ap.parse_args()
    out = a.out_dir or a.run
    out.mkdir(parents=True, exist_ok=True)
    cells = load(a.run, a.verified)
    pairs = None if a.any_pairs else design_pairs()

    nonzero, s3 = h3(cells)
    write_csv(out / "h3.csv", nonzero or [{"arm": "", "allocs_per_lookup": "none above 0"}],
              ["arm", "shape", "m", "table_seed", "ring_seed", "allocs_per_lookup"])
    for arm, v in s3["arms"].items():
        print(f"H3 {arm}: {v['processes']} processes, largest allocations per lookup {v['largest']}"
              + (f", not measured in {', '.join(v['not_measured'])}" if v["not_measured"] else ""))
    print(f"H3: {'holds' if s3['holds'] else 'does not hold'}")

    rows4, s4 = h4(cells, expected_pairs=pairs)
    write_csv(out / "h4.csv", rows4, list(dict.fromkeys(k for r in rows4 for k in r)))
    for r in rows4:
        if r["status"] != "judged":
            print(f"H4 {r['shape']:<14} {r['m']:>7}  {r['status']}: {r.get('failures', '')}")
            continue
        print(f"H4 {r['shape']:<14} {r['m']:>7}  build {r['build_s'] * 1e3:9.3f} ms vs median competitor "
              f"{r['median_competitor_build_s'] * 1e3:9.3f} ms {'holds' if r['build_holds'] else 'LOST'}"
              + (f", below 1 s {'yes' if r['below_1s'] else 'NO'}" if r["m"] == 100000 else "")
              + f"; heap {r['table_bytes']:,.0f} B vs 2 x {r['smallest_competitor']} "
              f"{r['smallest_competitor_bytes']:,.0f} B {'holds' if r['heap_holds'] else 'LOST'}")
    print(f"H4: {'holds' if s4['holds'] else 'does not hold'}" + (f" (lost: {', '.join(s4['lost'])})" if s4["lost"] else ""))

    rows7, s7 = h7(cells, resamples=a.resamples, seed=a.seed, expected_pairs=pairs)
    write_csv(out / "h7.csv", rows7, list(dict.fromkeys(k for r in rows7 for k in r)))
    for r in rows7:
        if r["status"] != "tested":
            print(f"H7 {r['shape']:<14} {r['m']:>5}  fails: {r['failures']}")
            continue
        print(f"H7 {r['shape']:<14} {r['m']:>5}  ratio {r['ratio']:.4f}  95% clustered BCa [{r['ci_low']:.4f}, "
              f"{r['ci_high']:.4f}]  sign {r['sign_x']}/{r['pairs']} (p {r['p_sign']:.2e})  "
              f"{'holds' if r['holds'] else 'LOST'}  ["
              f"largest pair {r['max_pair_ratio']:.4f}]")
    print(f"H7: {s7['held']} of {s7['cells']} cells hold (bootstrap {s7['held_boot']}, sign {s7['held_sign']}); "
          f"H7 {'holds' if s7['holds'] else 'does not hold'}")
    if a.ct_costs:
        costs = h7_costs(a.ct_costs)
        write_csv(out / "h7_costs.csv", costs, list(dict.fromkeys(k for r in costs for k in r)))
        print(f"H7 costs: {len(costs)} tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
