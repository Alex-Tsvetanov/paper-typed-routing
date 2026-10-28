#!/usr/bin/env python3
"""Round 3's results in the new loop (decision 21 (a), Alex 2026-10-28): the median and standard deviation of
each contestant. Fixed and committed with the plans, before the campaign runs; standard library only.

    rr_results.py RECORD.jsonl [RECORD.jsonl ...] --out RESULT.json [--md RESULT.md]

Inputs: t3/jobs/rr.py's records (aa.jsonl, the A/A run; rr.jsonl, the campaign), of one or both systems, at
most one of each kind per system. A record is refused (exit 2) unless its session line is first and its end
line last with exit 0, it was timed, it ran the committed plan of its system and kind (t3/plans/rr-aa-L.json,
rr-L.json, rr-aa-W.json, rr-W.json, compared without notes), and it holds every planned window once and every
rerun window its rerun lines announce.

Which windows count, per cell and contestant (a contestant is a program and an entry of its arm list):
  - A round that ran again counts as its rerun: the original round's windows are dropped for every
    contestant and the rerun's windows take their place, whatever their verdicts.
  - Within the rounds that count, an invalid window is dropped for its own contestant only. A window counts
    if p2run judged it valid (others at most 10% of one CPU included) and it has p2gen's timed line with at
    least one completed answer.
  - A contestant's windows in a cell count only if the cell's cell_end line says so (windows_count): its
    server became ready, lived through the cell and exited 0 on the stop.
  - A contestant with an overloaded window in a cell (only the error share failed, every error a timeout or
    a lost request) does not sustain the load there (decision 4): it is reported over its valid and
    overloaded windows, flagged, and not ranked.
Per contestant and cell, over its n counted windows (n of R is reported):
    X = completed answers / the window's wall time (req/s), t = 1e9 / X (ns per request);
    the median of X, its sample standard deviation (n - 1; none below n = 2), its least and largest value,
    and the median and sample standard deviation of t.
Per program and cell: the routers (every arm but null) that are ranked, by median X, highest first; each
router's routing cost, per round t_router - t_null over the rounds where both count, as its median and
standard deviation; and for each competitor of v2, the rounds in which v2's X was above the competitor's, of
the rounds where both count. That is a count, not a test: no comparison was named in advance (decision 21).
For a router that does not sustain the load, "count" means its valid and overloaded windows, as in its own
statistics.
A/A record, per program and cell: each entry's statistics as above, and per round r = X_0 / X_1 and
d = t_0 - t_1 (ns), each as a median and a standard deviation over the rounds where both entries count. The
A/A run has 6 servers per cell and the campaign 21 or 22, so it has fewer idle neighbours on the server CPU and
shorter gaps between a contestant's windows; this is reported with it.
Per cell also: the largest other-processes share and the largest single idle server's share of one CPU over
the counted windows (recorded by p2run, never judged here), and each server's peak resident memory (KiB).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

PLANS = Path(__file__).resolve().parent / "plans"
NAMES = {("linux", "aa"): "rr-aa-L.json", ("linux", "rr"): "rr-L.json",
         ("windows", "aa"): "rr-aa-W.json", ("windows", "rr"): "rr-W.json"}
NULL, V2 = "null", "v2"


class RecordError(ValueError):
    """A record the rule does not accept."""


def public(obj):
    """A plan without its notes (keys that start with an underscore), as p2run's session line holds it."""
    if isinstance(obj, dict):
        return {k: public(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [public(v) for v in obj]
    return obj


def kind_of(plan: dict) -> str:
    """aa when every program's arm list is v2 twice, else rr."""
    return "aa" if all(p.get("arms") == [V2, V2] for p in plan.get("programs", [])) else "rr"


def load_record(path: Path, plans: Path = PLANS) -> tuple[str, str, list[dict]]:
    """(system, kind, rows) of one complete timed record of a committed round-robin plan."""
    try:
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError) as e:
        raise RecordError(f"{path}: not readable as JSON lines: {e}") from e
    if not rows or rows[0].get("type") != "session":
        raise RecordError(f"{path}: no session line first")
    session, end = rows[0], rows[-1]
    if end.get("type") != "end" or end.get("exit") != 0:
        raise RecordError(f"{path}: the run did not finish with exit 0 (last line {end.get('type')!r}, "
                          f"exit {end.get('exit')!r})")
    system, plan = session.get("system"), session.get("plan") or {}
    if session.get("mode") != "timed" or system not in ("linux", "windows"):
        raise RecordError(f"{path}: a timed run on linux or windows wanted, got {system!r} {session.get('mode')!r}")
    kind = kind_of(plan)
    committed = json.loads((plans / NAMES[(system, kind)]).read_text(encoding="utf-8"))
    if plan != public(committed):
        raise RecordError(f"{path}: its plan is not the committed {NAMES[(system, kind)]}")
    windows = [r for r in rows if r.get("type") == "window"]
    planned = sorted(w["seq"] for w in windows if not w.get("rerun"))
    reruns = sorted(w["seq"] for w in windows if w.get("rerun"))
    announced = sorted(s for r in rows if r.get("type") == "rerun" for rd in r["rounds"]
                       for s in range(rd["first_seq"], rd["first_seq"] + rd["windows"]))
    if planned != list(range(session["windows"])) or reruns != announced:
        raise RecordError(f"{path}: {len(planned)} planned windows of {session['windows']} and {len(reruns)} rerun "
                          f"windows of {len(announced)}, or a window twice")
    return system, kind, rows


def rate(w: dict) -> float | None:
    g = w.get("generator") or {}
    completed, wall_ns = (g.get("measure") or {}).get("completed"), g.get("measure_wall_ns")
    if not isinstance(completed, int) or completed <= 0 or not isinstance(wall_ns, int) or wall_ns <= 0:
        return None
    return completed / (wall_ns / 1e9)


def spread(values: list[float]) -> dict:
    """median, sample standard deviation (none below two values), least and largest."""
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": statistics.median(values),
            "sd": statistics.stdev(values) if len(values) > 1 else None, "min": min(values), "max": max(values)}


def _max(*values):
    present = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return max(present) if present else None


def counted(rows: list[dict]) -> dict:
    """Per cell: per contestant (program, entry) its arm, its usable windows by round with their verdicts, whether
    it is overloaded there and whether its windows count; and the cell's largest shares. See the docstring."""
    cells: dict = {}
    rerun_rounds = {(r["cell"], rd["round"]) for r in rows if r.get("type") == "rerun" for rd in r["rounds"]}
    for r in rows:
        if r.get("type") == "cell_end":
            c = cells.setdefault(r["cell"], {"m": r["m"], "contestants": {}, "others_max": None, "idle_max": None})
            for s in r["servers"]:
                c["contestants"][(s["program"], s["entry"])] = {
                    "arm": s["arm"], "by_round": {}, "windows_count": s["windows_count"],
                    "reason_codes": s["reason_codes"], "overloaded": False,
                    "peak_resident_kib": (s.get("memory") or {}).get("peak_resident_kib")}
    for w in (r for r in rows if r.get("type") == "window"):
        if bool(w.get("rerun")) != ((w["cell"], w["round"]) in rerun_rounds):
            continue  # an original round that ran again
        c = cells[w["cell"]]
        who = c["contestants"][(w["program"], w["entry"])]
        x = rate(w)
        if w["status"] == "overloaded":
            who["overloaded"] = True
        if w["status"] in ("valid", "overloaded") and x is not None:
            who["by_round"][w["round"]] = (x, w["status"])
            if who["windows_count"]:
                o = w.get("others") or {}
                c["others_max"] = _max(c["others_max"], o.get("sum_pct_of_one_cpu"))
                c["idle_max"] = _max(c["idle_max"], (o.get("idle_servers") or {}).get("max_pct_of_one_cpu"))
    return cells


def contestant_stats(who: dict) -> dict:
    """X and t over the counted windows: the valid ones, or valid and overloaded for an overloaded contestant."""
    keep = {} if not who["windows_count"] else \
        {k: x for k, (x, st) in who["by_round"].items() if st == "valid" or who["overloaded"]}
    xs = [keep[k] for k in sorted(keep)]
    return {"arm": who["arm"], "windows_count": who["windows_count"], "reason_codes": who["reason_codes"],
            "overloaded": who["overloaded"], "rounds": sorted(keep), "req_s": spread(xs),
            "ns_per_request": spread([1e9 / x for x in xs]), "peak_resident_kib": who["peak_resident_kib"], "_x": keep}


def per_round(a: dict, b: dict, f) -> list:
    return [f(a[k], b[k]) for k in sorted(set(a) & set(b))]


def _public_stats(s: dict) -> dict:
    return {k: v for k, v in s.items() if k != "_x"}


def campaign_cell(c: dict, rounds: int) -> dict:
    programs: dict = {}
    for (program, entry), who in sorted(c["contestants"].items()):
        programs.setdefault(program, []).append(contestant_stats(who))
    out = {"m": c["m"], "rounds": rounds, "others_max_pct_of_one_cpu": c["others_max"],
           "idle_server_max_pct_of_one_cpu": c["idle_max"], "programs": {}}
    for program, entries in programs.items():
        by_arm = {s["arm"]: s for s in entries}
        null = by_arm.get(NULL)
        routers = [s for s in entries if s["arm"] != NULL]
        ranked = sorted((s for s in routers if not s["overloaded"] and s["req_s"]["n"]),
                        key=lambda s: (-s["req_s"]["median"], s["arm"]))
        cost = {s["arm"]: spread(per_round(s["_x"], null["_x"], lambda x, y: 1e9 / x - 1e9 / y))
                for s in routers if null is not None}
        ahead = {}
        if V2 in by_arm:
            for s in routers:
                if s["arm"] != V2:
                    both = per_round(by_arm[V2]["_x"], s["_x"], lambda x, y: x > y)
                    ahead[s["arm"]] = {"v2_above": sum(both), "rounds_both_count": len(both)}
        names = [s["arm"] for s in ranked]
        out["programs"][program] = {
            "contestants": [_public_stats(s) for s in entries], "ranking": names,
            "not_ranked": sorted(s["arm"] for s in routers if s["arm"] not in names),
            "routing_cost_ns_per_request": cost, "v2_above_competitor_in_rounds": ahead}
    return out


def aa_cell(c: dict, rounds: int) -> dict:
    stats = {key: contestant_stats(who) for key, who in sorted(c["contestants"].items())}
    out = {"m": c["m"], "rounds": rounds, "others_max_pct_of_one_cpu": c["others_max"],
           "idle_server_max_pct_of_one_cpu": c["idle_max"], "programs": {}}
    for program in sorted({p for p, _ in stats}):
        e0, e1 = stats[(program, 0)], stats[(program, 1)]
        out["programs"][program] = {
            "entries": [_public_stats(e0), _public_stats(e1)],
            "r": spread(per_round(e0["_x"], e1["_x"], lambda x, y: x / y)),
            "d_ns": spread(per_round(e0["_x"], e1["_x"], lambda x, y: 1e9 / x - 1e9 / y))}
    return out


def analyse(rows: list[dict], kind: str) -> dict:
    session = rows[0]
    rounds = session["plan"]["rounds"]
    one = aa_cell if kind == "aa" else campaign_cell
    return {"session": {k: session.get(k) for k in ("host", "os", "cpu_model", "started", "plan_sha256", "runner_sha256")},
            "cells": {name: one(c, rounds) for name, c in counted(rows).items()}}


def _f(v, digits: int) -> str:
    return "" if v is None else f"{v:,.{digits}f}"


def markdown(result: dict) -> str:
    out = ["# Round 3 in the new loop: median and standard deviation per contestant", ""]
    for system, kinds in sorted(result["systems"].items()):
        for kind in ("rr", "aa"):
            for cell, c in (kinds.get(kind) or {}).get("cells", {}).items():
                out += [f"## {system}, {'A/A run' if kind == 'aa' else 'campaign'}, {cell}", "",
                        f"{c['rounds']} rounds. Other processes at most {_f(c['others_max_pct_of_one_cpu'], 2)}% of one "
                        f"CPU; a single idle server at most {_f(c['idle_server_max_pct_of_one_cpu'], 3)}%.", "",
                        "| Program | Arm | n | Median req/s | SD req/s | Median ns/req | SD ns/req | Peak KiB | Note |",
                        "|---|---|---|---|---|---|---|---|---|"]
                for program, p in c["programs"].items():
                    for e, s in enumerate(p.get("contestants") or p.get("entries")):
                        notes = []
                        if kind == "rr" and s["arm"] in p["ranking"]:
                            notes.append(f"rank {p['ranking'].index(s['arm']) + 1}")
                        if kind == "aa":
                            notes.append(f"entry {e}")
                        if s["overloaded"]:
                            notes.append("does not sustain the load")
                        if not s["windows_count"]:
                            notes.append("windows do not count: " + ", ".join(s["reason_codes"]))
                        x, t = s["req_s"], s["ns_per_request"]
                        out.append(f"| {program} | {s['arm']} | {x['n']} | {_f(x.get('median'), 0)} | {_f(x.get('sd'), 0)} "
                                   f"| {_f(t.get('median'), 1)} | {_f(t.get('sd'), 1)} | {_f(s['peak_resident_kib'], 0)} "
                                   f"| {'; '.join(notes)} |")
                out.append("")
    return "\n".join(out) + "\n"


def _clean(obj):
    """JSON without NaN: a value that is not finite is written as null."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return None if isinstance(obj, float) and not math.isfinite(obj) else obj


def main(argv: list[str] | None = None, plans: Path = PLANS) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("records", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--md", type=Path)
    a = ap.parse_args(argv)
    systems: dict = {}
    try:
        for path in a.records:
            system, kind, rows = load_record(path, plans)
            if kind in systems.get(system, {}):
                raise RecordError(f"{path}: a second {kind} record of {system}")
            systems.setdefault(system, {})[kind] = analyse(rows, kind)
    except RecordError as e:
        print(f"rr_results: refused: {e}", file=sys.stderr)
        return 2
    result = _clean({"rule": "t3/rr_results.py's docstring (decision 21 (a))", "systems": systems})
    a.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    if a.md:
        a.md.write_text(markdown(result), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
