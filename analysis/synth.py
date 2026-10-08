"""Synthetic runs for the tests of the round-2 analysis (test_decisions.py, test_pipeline.py).

Rows have the fields rbench's cells.jsonl gives the analysis (bench/main.cpp): arm, shape, m,
table_seed, ring_seed, status, agrees, verified_all, ns_median, instructions, branch_misses,
allocs_per_lookup, build_s_median, table_bytes, build_alloc_bytes, loop_null (null_instructions
for an arm with its own null pass). Values are chosen by the tests; nothing here is a result.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from cells import COMPETITORS, CT, H1_SHAPES, H1_SIZES, H7_SIZES, NULL, NULL_NO405, NULLS, V2, design_pairs

GO_ARMS = {"gin", "httprouter", "nethttp", "chi"}


def loop_null(arm: str) -> str:
    """As rbench writes it: the Go arms their own null pass, the null arms none, the other
    competitors (none with a 405 of its own here) null-no405, v2 and the rest null."""
    if arm in GO_ARMS:
        return "own"
    if arm in NULLS:
        return ""
    return NULL_NO405 if arm in COMPETITORS else NULL


def row(arm: str, shape: str, m: int, p: tuple, ns: float, **kw) -> dict:
    r = {"arm": arm, "shape": shape, "m": m, "table_seed": p[0], "ring_seed": p[1], "status": "ok",
         "agrees": True, "verified_all": True, "ns_median": float(ns), "instructions": 100.0 + ns,
         "branch_misses": 0.5, "allocs_per_lookup": 0, "build_s_median": 1e-4 * m / 10,
         "table_bytes": 64 * m, "build_alloc_bytes": 64 * m, "ring_size": 4096,
         "loop_null": loop_null(arm)}
    if arm in GO_ARMS:
        r["null_instructions"] = 40.0
    r.update(kw)
    return r


def cell_rows(shape: str, m: int, ratio_by_pair: list[float], rivals: dict[str, float] | None = None,
              pairs: list[tuple] | None = None, rng: np.random.Generator | None = None, ct_ratio=None) -> list[dict]:
    """One cell: v2's time per pair is ratio_by_pair[i] times the fastest rival's; rivals maps a
    competitor to its time relative to the fastest (1.0 for the fastest). ct_ratio: per pair,
    the compile-time table's time over v2's (H7 cells only)."""
    pairs = pairs or design_pairs()
    rivals = rivals or {"gin": 1.0, "crow": 1.3, "glaze": 1.6}
    rng = rng or np.random.default_rng(0)
    rows = []
    for i, p in enumerate(pairs):
        base = 50.0 * (1 + 0.02 * rng.standard_normal())
        rows.append(row(NULL, shape, m, p, 3.0, instructions=27.0))
        rows.append(row(NULL_NO405, shape, m, p, 3.2, instructions=29.0))
        for arm, rel in rivals.items():
            rows.append(row(arm, shape, m, p, base * rel))
        rows.append(row(V2, shape, m, p, base * ratio_by_pair[i]))
        if ct_ratio is not None:
            rows.append(row(CT, shape, m, p, base * ratio_by_pair[i] * ct_ratio[i]))
    return rows


def grid_rows(ratio: float = 0.8, spread: float = 0.01, seed: int = 0, ct: float = 1.0) -> list[dict]:
    """Every H1 cell with v2 at about `ratio` times the fastest competitor, and the compile-time
    table at about `ct` times v2 in the H7 cells."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in H1_SHAPES:
        for m in H1_SIZES:
            rs = list(ratio * (1 + spread * rng.standard_normal(16)))
            ctr = list(ct * (1 + 0.001 * rng.standard_normal(16))) if m in H7_SIZES else None
            rows += cell_rows(s, m, rs, rng=rng, ct_ratio=ctr)
    return rows


def write_run(d: Path, rows: list[dict]) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "cells.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return d


def cells_of(rows: list[dict]) -> dict:
    cells: dict = {}
    for r in rows:
        cells.setdefault((r["shape"], int(r["m"])), {}).setdefault(r["arm"], []).append(r)
    return cells


assert all(a in COMPETITORS for a in ("gin", "crow", "glaze"))
