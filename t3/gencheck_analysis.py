#!/usr/bin/env python3
"""The report of the check of p2gen against t1gen (STATE.md, Laptop request 8; decision 17: reported only,
no pass rule). Fixed before the check runs; standard library only.

    gencheck_analysis.py GENCHECK.jsonl --out RESULT.json

The file must be one complete timed run of the committed t3/plans/gencheck-L.json on Linux
(pilot_analysis.load_pilot's guards). A window counts by pilot_analysis's rule (valid, a completed
answer, other processes at most OTHERS_MAX_PCT of one CPU). A pair counts only if its four windows
count. Per pair, the ratio q = X_p2gen / X_t1gen, each X the mean req/s of that generator's two windows
(entry 0 is p2gen, entry 1 t1gen, as t3/jobs/gencheck.py runs them). Reported: the pairs counted, the
median of q, and the distribution-free interval for that median from the order statistics
(q_(k), q_(n+1-k)), k the largest with P(B < k) <= 0.025 for B binomial(n, 1/2); its coverage is
given (for n = 16: q_(4) and q_(13), 97.87%). No pass rule, and no router arm.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

import pilot_analysis as A

NAMES = {"linux": "gencheck-L.json"}
ARM = "null"
TOOLS = {0: "p2gen", 1: "t1gen"}
NOT_A_ROUND = "not a round of four windows, p2gen as entry 0 and t1gen as entry 1"


def median_interval(n: int) -> tuple[int, float]:
    """k (1-based) of the interval (x_(k), x_(n+1-k)) for the median, and its coverage; (0, 0) if none."""
    def below(k: int) -> float:  # P(B < k)
        return sum(math.comb(n, i) for i in range(k)) / 2 ** n
    k = max((k for k in range(1, n // 2 + 1) if below(k) <= 0.025), default=0)
    return k, (1 - 2 * below(k)) if k else 0.0


def ratios(rows: list[dict]) -> tuple[list[dict], Counter]:
    """Per pair, q = X_p2gen / X_t1gen, and the reasons pairs were dropped."""
    pairs: dict[int, list[dict]] = {}
    for w in rows:
        if w.get("type") == "window":
            pairs.setdefault(w["table_seed"], []).append(w)
    out, dropped = [], Counter()
    for pair, ws in sorted(pairs.items()):
        if len(ws) != 4 or {w["arm"] for w in ws} != {ARM} or sorted(w["entry"] for w in ws) != [0, 0, 1, 1] \
                or any(w.get("generator_tool") != TOOLS.get(w.get("entry")) for w in ws):
            dropped[NOT_A_ROUND] += 1
            continue
        faults = [f for f in (A.window_fault(w, A.OTHERS_MAX_PCT) for w in ws) if f]
        if faults:
            dropped[faults[0]] += 1
            continue
        x = [sum(A.window_rate(w) for w in ws if w["entry"] == e) / 2 for e in (0, 1)]
        out.append({"pair": pair, "q": x[0] / x[1]})
    return out, dropped


def report(qs: list[float]) -> dict:
    n = len(qs)
    k, coverage = median_interval(n)
    s = sorted(qs)
    return {"pairs": n, "median_q": round(statistics.median(s), 5),
            "interval": [round(s[k - 1], 5), round(s[n - k], 5)] if k else None,
            "interval_order_statistics": [k, n + 1 - k] if k else None, "coverage": round(coverage, 4)}


def main(argv: list[str] | None = None, plans: Path = A.PLANS) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gencheck", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        _, rows = A.load_pilot(a.gencheck, plans, NAMES)
    except A.PilotError as e:
        print(f"gencheck_analysis: refused: {e}", file=sys.stderr)
        return 2
    got, dropped = ratios(rows)
    if not got:
        print("gencheck_analysis: no counted pair", file=sys.stderr)
        return 1
    result = {"rule": {"q": "X_p2gen / X_t1gen per pair", "others_max_pct": A.OTHERS_MAX_PCT, "pass_rule": None},
              "dropped": dict(dropped), **report([g["q"] for g in got])}
    a.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
