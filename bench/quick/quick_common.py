"""Shared constants and plan arithmetic of P2's quick runs (quick-plan.md at the repository root).

Every number here is either fixed by quick-plan.md or comes from a named record (see EST_S). Nothing in
this file is a measured result.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = BENCH.parent
PLANS_DIR = HERE / "plans"

BUDGET_S = 600.0  # CLAUDE.md rule 5: a campaign takes at most 10 minutes
FACTOR = 1.10     # planned rounds x round seconds x FACTOR stays within BUDGET_S
CPU = 2           # the measured process's CPU, as run_grid.sh and the earlier lookup grid
RING_ADV = 256    # the adversarial tool's ring (rbench's default 4096 makes the agreement pass dominate)
BUILD_REPS_ADV = 1

# Seconds per process, from named records only (quick-plan.md, "Arithmetic"):
#   small  round 2's 0.995 s per process at m = 10 and 100 (design/review-runs/boundary-arms.md)
#   large  round 2's 4.565 s per process, the main grid's average over every size (ablations.md); used
#          for m = 10,000, which is below the grid's largest size, so it is an average, not a bound
#   adv    the desktop planning run of the adversarial tool: 44 cells, one process each, 542 s in all at
#          ring 4096 (adversarial.md); per cell its mean, 542 / 44, an upper estimate at ring 256
EST_S = {"small": 0.995, "large": 4.565, "adv": 542.0 / 44.0}

SHAPES = ("static", "param-last", "param-first", "rest", "wild", "mixed-disjoint", "mixed-overlap")

# Seeds that earlier runs used or froze; no new seed may equal one of them (test_quick.py checks it).
FROZEN_SEEDS = frozenset([1, 2, 3, 4, 5, 127, 227, 20261009, 20261010, 20261103, 20261104]
                         + list(range(110, 127)) + list(range(210, 227)))

ABLATION_ARMS = ("regexmatcher-v2-copy", "regexmatcher-v2-ab-noexact", "regexmatcher-v2-ab-bytes",
                 "regexmatcher-v2-ab-heapstack", "regexmatcher-v2-ab-strings")
BOUNDARY_ARMS = ("regexmatcher-v2", "null", "null-no405", "regexmatcher-v2-capi", "capi-null", "rust-null",
                 "regexmatcher-v2-goloop", "matchit", "actix-router", "path-tree", "gin", "httprouter", "chi",
                 "uwebsockets", "glaze")
AA_ARM = "regexmatcher-v2"  # the A/A pair: this arm twice, as two processes, in plan quick-L-abl-s

# The arms one Linux build has (the job's -DRB_ARMS): every arm of every Linux plan.
LINUX_ARMS = tuple(dict.fromkeys(("regexmatcher-v2", "null", *ABLATION_ARMS, *BOUNDARY_ARMS)))

# The adversarial cells of the quick plan: every table's miss and last-hit queries and every catch-all
# table's miss query (adversarial list); the other-method queries are left out (their counts equal the
# miss queries' by design, adversarial.md).
ADV_TWO_K = (1, 2, 4, 8, 12, 16)
ADV_FOUR_K = (1, 2, 4, 6, 8)


def adversarial_cells() -> list[str]:
    cells = []
    for fam, ks in (("two", ADV_TWO_K), ("four", ADV_FOUR_K)):
        for k in ks:
            cells += [f"{fam}-k{k}-miss", f"{fam}-k{k}-last-hit"]
    for fam, ks in (("two", ADV_TWO_K), ("four", ADV_FOUR_K)):
        for k in ks:
            cells.append(f"{fam}-k{k}-catch-all-miss")
    return cells


# The plans: name, system, kind, cells, arms, rounds (quick-plan.md, "Design").
PLANS = {
    "quick-L-adv": {"os": "linux", "kind": "adversarial", "rounds": 3},
    "quick-L-abl-s": {"os": "linux", "kind": "rbench", "rounds": 4, "sizes": (10, 100),
                      "arms": ("regexmatcher-v2", "null", *ABLATION_ARMS), "aa": True, "est": "small"},
    "quick-L-abl-l": {"os": "linux", "kind": "rbench", "rounds": 3, "sizes": (10000,),
                      "arms": ABLATION_ARMS, "aa": False, "est": "large"},
    "quick-L-bnd-10": {"os": "linux", "kind": "rbench", "rounds": 5, "sizes": (10,),
                       "arms": BOUNDARY_ARMS, "aa": False, "est": "small"},
    "quick-L-bnd-100": {"os": "linux", "kind": "rbench", "rounds": 5, "sizes": (100,),
                        "arms": BOUNDARY_ARMS, "aa": False, "est": "small"},
}


def label_seed(label: str) -> int:
    """The first 8 hex digits of sha256(label), as an integer (P1's rule for new seeds)."""
    return int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16)


def table_seed(plan: str, rnd: int) -> int:
    return label_seed(f"P2 quick table {plan} round {rnd}")


def ring_seed(plan: str, rnd: int) -> int:
    return label_seed(f"P2 quick ring {plan} round {rnd}")


def order_seed(plan: str) -> int:
    return label_seed(f"P2 quick order {plan}")


def file_sha256(path: Path) -> str:
    """sha256 of a text file with CRLF read as LF."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def plan_rows(name: str) -> tuple[dict, list[dict]]:
    """The plan's header and rows, fully expanded: one row per process, in run order."""
    p = PLANS[name]
    rng = random.Random(order_seed(name))
    rows: list[dict] = []
    if p["kind"] == "adversarial":
        cells = adversarial_cells()
        for rnd in range(p["rounds"]):
            order = list(cells)
            rng.shuffle(order)
            for cell in order:
                rows.append({"round": rnd, "id": f"r{rnd}-{cell}", "kind": "adversarial", "cell": cell,
                             "arm": "regexmatcher-v2-adversarial", "est_s": round(EST_S["adv"], 3),
                             "args": ["cell", "--cell", cell, "--ring", str(RING_ADV), "--rep", str(rnd),
                                      "--build-reps", str(BUILD_REPS_ADV)]})
    else:
        units = [(arm, shape, m) for m in p["sizes"] for shape in SHAPES for arm in p["arms"]]
        if p["aa"]:
            units += [(AA_ARM + "#aa", shape, m) for m in p["sizes"] for shape in SHAPES]
        for rnd in range(p["rounds"]):
            ts, rs = table_seed(name, rnd), ring_seed(name, rnd)
            order = list(units)
            rng.shuffle(order)
            for arm_label, shape, m in order:
                arm = arm_label.split("#")[0]
                rows.append({"round": rnd, "id": f"r{rnd}-{arm_label.replace('#', '-')}-{shape}-{m}",
                             "kind": "rbench", "arm": arm, "aa": arm_label.endswith("#aa"), "shape": shape,
                             "m": m, "table_seed": ts, "ring_seed": rs, "est_s": EST_S[p["est"]],
                             "args": ["cell", "--arm", arm, "--shape", shape, "--m", str(m), "--seed", str(ts),
                                      "--ring-seed", str(rs)]})
    per_round = sum(r["est_s"] for r in rows) / p["rounds"]
    header = {"plan": name, "os": p["os"], "kind": p["kind"], "rounds": p["rounds"], "cpu": CPU,
              "processes_per_round": len(rows) // p["rounds"], "round_est_s": round(per_round, 3),
              "total_est_s": round(per_round * p["rounds"], 3), "budget_s": BUDGET_S, "factor": FACTOR,
              "rounds_by_arithmetic": max((r for r in range(1, p["rounds"] + 1) if rounds_fit(per_round, r)),
                                          default=0),
              "order_seed": order_seed(name)}
    if p["kind"] == "rbench":
        header["arms"] = list(p["arms"]) + ([AA_ARM + " (A/A, a second process)"] if p["aa"] else [])
        header["sizes"] = list(p["sizes"])
        header["shapes"] = list(SHAPES)
    else:
        header["cells"] = adversarial_cells()
        header["ring"] = RING_ADV
    return header, rows


def plan_text(name: str) -> str:
    header, rows = plan_rows(name)
    return "\n".join(json.dumps(x, sort_keys=True) for x in [header, *rows]) + "\n"


def rounds_fit(round_s: float, rounds: int) -> bool:
    return rounds * round_s * FACTOR <= BUDGET_S
