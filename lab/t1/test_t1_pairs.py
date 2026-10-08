#!/usr/bin/env python3
"""Tests of t1.py's pairing and stopping rule (no server is started).

    python lab/t1/test_t1_pairs.py      (exit 0 when every check passes)

1. pair_ratios: one ratio per round, the mean of an arm's windows over the reference's; by default
   every round with req/s counts (as P1 ran); with valid_only, a round with any invalid window
   (error share, generator CPU, clock drift, probe) is left out, whatever arm the window belongs to.
2. stop_verdicts: with valid_pairs_only, a cell of six rounds of which one is invalid has five
   valid pairs, so it is not decided at a minimum of six; without it, it is.
3. The three arms of P2's H6 (v1 the reference, v2, null) in mirrored rounds.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import t1  # noqa: E402

failures = 0


def expect(name: str, ok: bool) -> None:
    global failures
    print(("ok: " if ok else "FAIL: ") + name)
    failures += not ok


def rounds(n: int, rps: dict[str, float], invalid: dict[int, str] | None = None) -> list[dict]:
    """n mirrored rounds of the arms in rps (the first the reference); invalid maps a round to the
    arm whose first window in it is invalid."""
    arms = list(rps)
    order = arms + arms[::-1]
    out = []
    for rnd in range(1, n + 1):
        bad = (invalid or {}).get(rnd)
        for pos, arm in enumerate(order):
            ok = not (bad == arm and pos == order.index(arm))
            out.append({"round": rnd, "position": pos, "arm": arm, "rps": rps[arm] * (1 + 0.001 * pos),
                        "valid": ok, "invalid_reasons": [] if ok else ["error share 0.2% > 0.1%"]})
    return out


def main() -> int:
    rps = {"h6-v1": 100000.0, "h6-v2": 110000.0, "h6-null": 120000.0}
    rows = rounds(6, rps, invalid={3: "h6-null"})
    expect("every round with req/s counts by default", len(t1.pair_ratios(rows, "h6-v1", "h6-v2")) == 6)
    expect("valid_only leaves out a round with an invalid window of another arm",
           len(t1.pair_ratios(rows, "h6-v1", "h6-v2", valid_only=True)) == 5)
    expect("valid_rounds", t1.valid_rounds(rows) == {1, 2, 4, 5, 6})
    cfg = {"min_pairs": 6, "valid_pairs_only": True}
    v = t1.stop_verdicts(rows, list(rps), cfg)
    expect("five valid pairs of six rounds: not decided at a minimum of six",
           all(not x["decided"] and x["n_pairs"] == 5 for x in v.values()))
    v = t1.stop_verdicts(rows, list(rps), dict(cfg, valid_pairs_only=False))
    expect("without the flag the six rounds decide (both ratios lie outside [0.98, 1.02])",
           all(x["decided"] and x["n_pairs"] == 6 for x in v.values()))
    rows = rounds(7, rps, invalid={3: "h6-null"})
    v = t1.stop_verdicts(rows, list(rps), cfg)
    expect("a seventh round gives six valid pairs, and the cell decides", all(x["decided"] and x["n_pairs"] == 6
                                                                            for x in v.values()))
    print(f"{failures} failed" if failures else "all checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
