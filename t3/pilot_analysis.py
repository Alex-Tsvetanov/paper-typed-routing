#!/usr/bin/env python3
"""The A/A pilot's analysis (hypotheses-round3.md, section 3a; STATE.md, Laptop request 7): delta for
H8, and the A/A noise in time per request from which H9's minimum D_T0 and H10's margin are fixed
before the freeze. Fixed with the pilot's rule, before the pilot runs; standard library only.

    pilot_analysis.py PILOT.jsonl [PILOT.jsonl ...] --out RESULT.json

Each file is one system's t3/jobs/pilot.py output (p2run's rows of A/A rounds: one arm, "v2", twice).
A window counts if p2run judged it valid and, under the other-processes rule (OTHERS_MAX_PCT), other
processes took no more than that share of one CPU over it. A replicate is one round: (system, program,
shape, m, pair). It counts only if all four of its windows count. For a replicate,
    X_e = the mean over entry e's two windows of completed answers / window wall time (req/s),
    r   = X_0 / X_1                         (H8's ratio, v2 against itself),
    d   = 1e9 / X_0 - 1e9 / X_1             (the difference in time per request, ns).
delta = the largest of DELTA_FLOOR, the 97.5th percentile of r and that of 1/r (DELTA_READING "a"),
or the larger of DELTA_FLOOR and the 97.5th percentile of max(r, 1/r) (reading "b"), over every
counted replicate of every file. Percentiles by linear interpolation between order statistics
(Hyndman and Fan's type 7, numpy's default). The noise table gives, per system and program, the
number of replicates and the median and 97.5th percentile of |d|. No arm is compared with another.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

DELTA_FLOOR = 1.02  # decision 7 (b)
DELTA_READING = "a"  # decision 15, its recommended option until Alex answers
OTHERS_MAX_PCT: float | None = 10.0  # decision 16 (a), its recommended option until Alex answers; None: no rule
AA_ARM = "v2"


def quantile(values: list[float], p: float) -> float:
    """Type 7: linear interpolation between the order statistics at (n - 1) p."""
    if not values or not 0.0 <= p <= 1.0:
        raise ValueError("a quantile needs values and 0 <= p <= 1")
    x = sorted(values)
    h = (len(x) - 1) * p
    lo = math.floor(h)
    return x[lo] if lo + 1 >= len(x) else x[lo] + (h - lo) * (x[lo + 1] - x[lo])


def window_rate(row: dict) -> float | None:
    """Completed answers per second over the measured window, or None without p2gen's timed line."""
    g = row.get("generator") or {}
    completed, wall_ns = (g.get("measure") or {}).get("completed"), g.get("measure_wall_ns")
    if not isinstance(completed, int) or not isinstance(wall_ns, int) or wall_ns <= 0:
        return None
    return completed / (wall_ns / 1e9)


def window_fault(row: dict, others_max: float | None) -> str | None:
    """Why a window does not count, or None."""
    if row.get("status") != "valid":
        return f"status {row.get('status')}"
    if window_rate(row) is None:
        return "no timed generator line"
    if others_max is not None:
        others = row.get("others")
        if not isinstance(others, dict):
            return "no record of other processes"
        if others.get("sum_pct_of_one_cpu", 0.0) > others_max:
            return f"other processes above {others_max:g}% of one CPU"
    return None


def replicates(rows: list[dict], others_max: float | None = OTHERS_MAX_PCT) -> tuple[list[dict], Counter]:
    """One system's counted A/A replicates, and the reasons rounds were dropped."""
    session = next((r for r in rows if r.get("type") == "session"), {})
    system = session.get("system", "?")
    rounds: dict[tuple, list[dict]] = {}
    for w in rows:
        if w.get("type") == "window":
            rounds.setdefault((w["program"], w["shape"], w["m"], w["table_seed"]), []).append(w)
    out, dropped = [], Counter()
    for (program, shape, m, pair), ws in sorted(rounds.items()):
        if len(ws) != 4 or {w["arm"] for w in ws} != {AA_ARM} or sorted(w["entry"] for w in ws) != [0, 0, 1, 1]:
            dropped["not an A/A round of four windows"] += 1
            continue
        faults = [f for f in (window_fault(w, others_max) for w in ws) if f]
        if faults:
            dropped[faults[0]] += 1
            continue
        x = [sum(window_rate(w) for w in ws if w["entry"] == e) / 2 for e in (0, 1)]
        out.append({"system": system, "program": program, "shape": shape, "m": m, "pair": pair,
                    "r": x[0] / x[1], "d_ns": 1e9 / x[0] - 1e9 / x[1]})
    return out, dropped


def delta(rs: list[float], reading: str = DELTA_READING) -> float:
    if reading == "a":
        return max(DELTA_FLOOR, quantile(rs, 0.975), quantile([1 / r for r in rs], 0.975))
    if reading == "b":
        return max(DELTA_FLOOR, quantile([max(r, 1 / r) for r in rs], 0.975))
    raise ValueError(f"reading is a or b, not {reading!r}")


def noise_table(reps: list[dict]) -> list[dict]:
    by: dict[tuple, list[float]] = {}
    for r in reps:
        by.setdefault((r["system"], r["program"]), []).append(abs(r["d_ns"]))
    return [{"system": s, "program": p, "replicates": len(v), "abs_d_ns_median": round(quantile(v, 0.5), 1),
             "abs_d_ns_p975": round(quantile(v, 0.975), 1)} for (s, p), v in sorted(by.items())]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pilots", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    reps, dropped = [], {}
    for path in a.pilots:
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        got, lost = replicates(rows)
        reps += got
        dropped[str(path)] = dict(lost)
    if not reps:
        print("pilot_analysis: no counted replicate", file=sys.stderr)
        return 1
    result = {"rule": {"delta_floor": DELTA_FLOOR, "delta_reading": DELTA_READING, "others_max_pct": OTHERS_MAX_PCT,
                       "percentile": "type 7 (linear interpolation)"},
              "replicates": len(reps), "dropped": dropped,
              "delta": round(delta([r["r"] for r in reps]), 4), "noise": noise_table(reps)}
    a.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
