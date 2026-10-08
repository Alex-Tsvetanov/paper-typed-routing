"""Holm's step-down over a fixed family (hypotheses-round2.md, section 3.4).

The family of H1 is the pre-specified 35 cells: a cell that could not be tested (analysis/cells.py
fails it, or no competitor holds its table) stays in the family with p = 1, so it never passes
and never makes the others' adjustment smaller. Each computation (the clustered bootstrap, the
exact sign test) runs its own step-down over the whole family; a cell passes only under both.
Pure Python.
"""

from __future__ import annotations


def holm(pvals: list[float]) -> list[float]:
    """Holm's adjusted p-values, in the order given."""
    k = len(pvals)
    order = sorted(range(k), key=lambda i: pvals[i])
    adj = [0.0] * k
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (k - rank) * pvals[i]))
        adj[i] = running
    return adj


def adjust(rows: list[dict], key: str, alpha: float) -> list[bool]:
    """Holm over every row of the family for the p-values in rows[i][key]; a row whose status is
    not "tested" enters with p = 1. Sets rows[i][key + "_holm"]; returns whether each row passes
    (tested, and adjusted p at most alpha)."""
    p = [float(r[key]) if r.get("status") == "tested" else 1.0 for r in rows]
    out = []
    for r, a in zip(rows, holm(p)):
        r[key + "_holm"] = a
        out.append(r.get("status") == "tested" and a <= alpha)
    return out


def decide_both(rows: list[dict], alpha: float, boot: str, sign: str, verdict: str) -> None:
    """Holm's step-down for each of the two computations over the whole family, and the cell's
    verdict: rows[i][verdict] is true only if both pass. Also sets <verdict>_boot, <verdict>_sign
    and <verdict>_disagree (the two computations disagree: both are reported and the cell does not
    pass)."""
    b = adjust(rows, boot, alpha)
    s = adjust(rows, sign, alpha)
    for r, pb, ps in zip(rows, b, s):
        r[verdict + "_boot"] = pb
        r[verdict + "_sign"] = ps
        r[verdict] = pb and ps
        r[verdict + "_disagree"] = r.get("status") == "tested" and pb != ps
