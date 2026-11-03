"""What the analyses of the review runs share (design/review-runs/ablations.md, boundary-arms.md): the arms
of a cell sorted out as the earlier campaign's lookup-time analysis sorts them (analysis/cells.py), and the
statistic both plans fix: per cell, the median over the seed pairs of a per-pair ratio, with the 95% BCa
interval over the pairs, computed as analysis/h1_stats.py computes H1's (analysis/stats.py: clustered by
table seed, which in the design is one pair each; 10,000 resamples; the same resampling seed). Exploratory:
no hypothesis, no test, no multiplicity adjustment. Pure Python and NumPy.

The design's sixteen seed pairs (analysis/cells.py's design_pairs: table seeds 111 to 126, ring seeds 211 to
226) are required, not assumed: an arm takes part in a cell only if its processes are exactly those sixteen
pairs, and a ratio is computed only over all sixteen, from arms that each have all of them; otherwise the
comparison is refused with its reason. The pairs two arms happen to share are never used instead.
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cells import classify, design_pairs, pair, usable  # noqa: E402
from check_agree import load_semantics  # noqa: E402
from h1_stats import RESAMPLING_SEED  # noqa: E402
from stats import bca, bca_bound, fastest_ratio  # noqa: E402

RESAMPLES = 10000
ALPHA = 0.025  # each side of the two-sided 95% interval
SEED = RESAMPLING_SEED

ARM_WORD = {
    "regexmatcher-v2": "Vtwo", "regexmatcher-v2-copy": "Copy", "regexmatcher-v2-ab-linear": "Linear",
    "regexmatcher-v2-ab-hashed": "Hashed", "regexmatcher-v2-ab-noexact": "Noexact",
    "regexmatcher-v2-ab-bytes": "Bytes", "null": "Null", "null-no405": "NullNoFourOhFive",
    "regexmatcher-v2-capi": "Capi", "capi-null": "CapiNull", "rust-null": "RustNull",
    "regexmatcher-v2-goloop": "Goloop", "matchit": "Matchit", "actix-router": "ActixRouter",
    "path-tree": "PathTree", "gin": "Gin", "httprouter": "Httprouter", "nethttp": "Nethttp", "chi": "Chi",
    "uwebsockets": "Uwebsockets", "glaze": "Glaze"}


@dataclass
class Arms:
    """One cell's arms: those whose every process is usable, and those absent or failing, with why."""
    ok: dict[str, list[dict]] = field(default_factory=dict)
    absent: dict[str, str] = field(default_factory=dict)
    failing: dict[str, str] = field(default_factory=dict)
    unusable: list[str] = field(default_factory=list)  # every process not usable, with its reason


def why_not(r: dict) -> str:
    """Why one process is not usable (analysis/cells.py's usable)."""
    if r.get("status") != "ok":
        return f"status {r.get('status')}" + (f" ({r.get('reason') or r.get('exit')})" if r.get("reason") or
                                              r.get("exit") is not None else "")
    if not r.get("agrees"):
        return f"disagrees ({r.get('answers_differ')} answers differ)"
    return "not verified on every query"


def not_compared(why: str) -> dict:
    """A comparison that was not made: its status and reason, and no pair used."""
    return {"status": "not compared", "why": why, "pairs": 0}


def sort_arms(cell: dict[str, list[dict]], shape: str, arms: list[str], semantics: dict | None = None,
              expected_pairs: list[tuple] | None = None) -> Arms:
    """The named arms of one cell, each classified as analysis/cells.py classifies a competitor: ok when
    every process is usable and the processes are exactly the design's seed pairs (expected_pairs, default
    the sixteen of analysis/cells.py); absent (refused, over budget, or answers that differ as
    bench/semantics.json declares); failing otherwise. An arm that did not run, or has not all of the
    pairs, is failing. Nothing is dropped in silence."""
    semantics = semantics if semantics is not None else load_semantics()
    expected = sorted(expected_pairs if expected_pairs is not None else design_pairs())
    out = Arms()
    for arm in arms:
        rows = cell.get(arm, [])
        kind, why = classify(arm, shape, rows, semantics)
        have = sorted(pair(r) for r in rows)
        if kind == "ok" and have != expected:
            kind, why = "failure", (f"{arm}: seed pairs are not the design's ({len(rows)} processes, "
                                    f"{len(set(have))} distinct pairs, {len(expected)} expected)")
        if kind == "ok":
            out.ok[arm] = rows
        elif kind == "absent":
            out.absent[arm] = why
        else:
            out.failing[arm] = why
        out.unusable += [f"{arm} pair {pair(r)}: {why_not(r)}" for r in rows if not usable(r)]
    return out


def values(rows: list[dict], value) -> dict[tuple, float]:
    """Each process's value (a key, or a function of the process), by seed pair; None values left out."""
    out = {}
    for r in rows:
        v = r.get(value) if isinstance(value, str) else value(r)
        if isinstance(v, (int, float)):
            out[pair(r)] = float(v)
    return out


def ratio_ci(num: dict[tuple, float], dens: dict[str, dict[tuple, float]], rng: np.random.Generator,
             resamples: int = RESAMPLES, expected_pairs: list[tuple] | None = None) -> dict:
    """The median over the design's pairs (expected_pairs, default the sixteen of analysis/cells.py) of the
    per-pair ratio num / den, where den is the arm of dens with the lowest median over those pairs, chosen
    again in every resample (one arm: that arm), and the 95% BCa interval over the pairs, clustered by table
    seed (analysis/stats.py, as analysis/h1_stats.py). num and every den must have a value for each of the
    pairs and for no other: if not, nothing is computed and the status says which arm lacks what (the pairs
    the arms share are never used instead). "pairs" is the number of pairs the ratio is over."""
    expected = sorted(expected_pairs if expected_pairs is not None else design_pairs())
    names = sorted(dens)
    out: dict = {"pairs": 0}
    if not names:
        out["status"] = "no arm to compare with"
        return out
    wrong = [f"{who}: {len(d)} pairs, {len(set(d) & set(expected))} of the design's {len(expected)}"
             for who, d in (("the numerator", num), *((n, dens[n]) for n in names)) if sorted(d) != expected]
    if wrong or len(expected) < 2:
        out["status"] = "not the design's pairs"
        out["why"] = "; ".join(wrong) or f"the design has {len(expected)} pairs"
        return out
    pairs = expected
    x = np.array([num[p] for p in pairs])
    riv = np.array([[dens[n][p] for p in pairs] for n in names])
    if np.any(riv <= 0) or np.any(x <= 0):
        out["status"] = "a value is not positive"
        return out
    boot = bca(x, riv, fastest_ratio, [p[0] for p in pairs], resamples, rng)
    best = int(np.argmin(np.median(riv, axis=-1)))
    per_pair = x / riv[best]
    out.update({"status": "compared", "pairs": len(pairs), "ratio": boot.theta, "low": bca_bound(boot, ALPHA),
                "high": bca_bound(boot, 1 - ALPHA), "fastest": names[best], "min_pair": float(np.min(per_pair)),
                "max_pair": float(np.max(per_pair))})
    return out


def median_of(rows: list[dict], value) -> float | None:
    vals = list(values(rows, value).values())
    return statistics.median(vals) if vals and len(vals) == len(rows) else None
