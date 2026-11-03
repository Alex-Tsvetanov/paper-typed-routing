#!/usr/bin/env python3
"""The adversarial benchmark of RegexMatcher v2's backtracking (design/review-runs/adversarial.md): one
run's lines (bench/jobs/adversarial.sh, cells.jsonl; one JSON line per process) to a summary and the
paper's macros.

    adversarial.py RUN [--out summary.json] [--macros adversarial.tex]

RUN is the run directory (its cells.jsonl, and plan.txt for the processes planned) or a .jsonl file.

Decided, deterministically: the written bound holds when every line that has the counting copy's
counts passes all four checks (the pinned code answers as expected, the copy answers the same, node
entries at most the nodes of the tries walked, at most four resumptions of a node), and every cell has
such a line; it fails when any line fails a check; it is undecided otherwise. The counts are exact, so
the processes of a cell must agree on them; a cell where they do not is listed and counts as failing.

Reported, descriptive, per cell: the counts (walks, nodes walked, entries, pushes, pops, which are the
backtracks, deepest choice stack, most resumptions and entries of one node), the processes planned,
seen and usable, every process that is not usable with its reason (nothing is dropped), the median
over usable processes of ns_median with the smallest and largest, and the time per node entered
(that median over the entries). Over all cells: the largest number of backtracks per query and the
cells that reach it, the largest of each count, the range of the time per node entered. A process is
usable when its
status is ok, it agrees with the expected answer on every query of its ring, and its checks pass.

Macros (letters only, prefixed Adv): totals and maxima, and per cell Adv<Family><Depth>[CatchAll]<Query>
followed by Ns, NsMin, NsMax, NsPerEntry, Entries, Backtracks and Deepest; for example
\\AdvTwoKindsSixteenOtherMethodBacktracks. Pure Python.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from macros_util import Macros, count, fixed, jsonl, listing, nanoseconds, tt  # noqa: E402

COUNTS = ("walks", "walked_nodes", "entries", "resumptions", "pushed", "popped", "deepest_stack",
          "max_entries_per_node", "max_resumptions_per_node")
CHECKS = ("expected_answer", "same_answer", "bound_entries", "bound_resumptions")
RESUMPTION_BOUND = 4
FAMILY_WORD = {"two-kinds": "TwoKinds", "four-kinds": "FourKinds"}
DEPTH_WORD = {1: "One", 2: "Two", 4: "Four", 6: "Six", 8: "Eight", 12: "Twelve", 16: "Sixteen"}
QUERY_WORD = {"miss": "Miss", "last-hit": "LastHit", "other-method": "OtherMethod"}


def cell_word(r: dict) -> str:
    return (FAMILY_WORD[r["family"]] + DEPTH_WORD[int(r["depth"])] + ("CatchAll" if r["catch_all"] else "")
            + QUERY_WORD[r["query"]])


def has_counts(r: dict) -> bool:
    return all(k in r for k in COUNTS + CHECKS)


def why_unusable(r: dict) -> str:
    """Why a process is not usable, or "" if it is."""
    if r.get("status") != "ok":
        return f"status {r.get('status')}" + (f" (exit {r['exit']})" if "exit" in r else "") + \
            (f": {r['reason']}" if r.get("reason") else "")
    if not has_counts(r):
        return "no counts"
    failed = [k for k in CHECKS if r.get(k) is not True]
    if failed:
        return "check failed: " + ", ".join(failed)
    if r.get("agrees") is not True:
        return "the pinned code disagrees with the expected answer in the timed process"
    if r.get("verified_all") is not True:
        return "not verified on every query of its ring"
    if not isinstance(r.get("ns_median"), (int, float)):
        return "no ns_median"
    return ""


def planned_of(run: Path) -> dict[str, int]:
    plan = run / "plan.txt"
    if not run.is_dir() or not plan.exists():
        return {}
    return dict(Counter(line.split()[0] for line in plan.read_text(encoding="utf-8").splitlines() if line.strip()))


def summarize(lines: list[dict], planned: dict[str, int] | None = None) -> dict:
    planned = planned or {}
    by_cell: dict[str, list[dict]] = defaultdict(list)
    for r in lines:
        by_cell[r["cell"]].append(r)
    cells = []
    for cid in sorted(set(by_cell) | set(planned)):
        rows = by_cell.get(cid, [])
        counted = [r for r in rows if has_counts(r)]
        usable = [r for r in rows if not why_unusable(r)]
        c = {"cell": cid, "planned": planned.get(cid, len(rows)), "processes": len(rows), "usable": len(usable),
             "not_usable": [{"rep": r.get("rep"), "reason": why_unusable(r)} for r in rows if why_unusable(r)]}
        if counted:
            first = counted[0]
            c.update({k: first[k] for k in ("family", "depth", "catch_all", "query", "method", "path", "routes")
                      if k in first})
            c.update({k: first[k] for k in COUNTS})
            c["counts_agree"] = all(all(r[k] == first[k] for k in COUNTS) for r in counted)
            c["checks_pass"] = all(all(r[k] is True for k in CHECKS) for r in counted)
        else:
            c["counts_agree"] = None
            c["checks_pass"] = None
        if usable:
            ns = [float(r["ns_median"]) for r in usable]
            c.update({"ns_median": statistics.median(ns), "ns_min": min(ns), "ns_max": max(ns)})
            if c.get("entries"):
                c["ns_per_entry"] = c["ns_median"] / c["entries"]
        cells.append(c)

    failing = [c["cell"] for c in cells if c["checks_pass"] is False or c["counts_agree"] is False]
    undecided = [c["cell"] for c in cells if c["checks_pass"] is None]
    decision = "fails" if failing else ("undecided" if undecided or not cells else "holds")
    counted = [c for c in cells if c["checks_pass"] is not None]
    timed = [c for c in cells if "ns_per_entry" in c]
    summary = {"decision": decision, "failing_cells": failing, "undecided_cells": undecided,
               "cells": len(cells), "processes_planned": sum(c["planned"] for c in cells),
               "processes": sum(c["processes"] for c in cells), "processes_usable": sum(c["usable"] for c in cells),
               "resumption_bound": RESUMPTION_BOUND}
    if counted:
        most = max(c["popped"] for c in counted)
        summary.update({"max_backtracks": most,
                        "max_backtracks_cells": sorted(c["cell"] for c in counted if c["popped"] == most)})
        for k in ("entries", "walked_nodes", "deepest_stack", "max_resumptions_per_node", "max_entries_per_node"):
            summary[f"max_{k}"] = max(c[k] for c in counted)
    if timed:
        per = [c["ns_per_entry"] for c in timed]
        slowest = max(timed, key=lambda c: (c["ns_median"], c["cell"]))
        summary.update({"ns_per_entry_min": min(per), "ns_per_entry_median": statistics.median(per),
                        "ns_per_entry_max": max(per), "slowest_ns": slowest["ns_median"],
                        "slowest_cell": slowest["cell"]})
    return {"summary": summary, "cells": cells}


def macros(result: dict) -> Macros:
    s = result["summary"]
    m = Macros()
    m.add("AdvCells", count(s["cells"]))
    m.add("AdvProcessesPlanned", count(s["processes_planned"]))
    m.add("AdvProcesses", count(s["processes"]))
    m.add("AdvProcessesUsable", count(s["processes_usable"]))
    m.add("AdvProcessesNotUsable", count(s["processes"] - s["processes_usable"]))
    m.add("AdvBoundDecision", s["decision"], "holds, fails or undecided")
    m.add("AdvResumptionBound", count(s["resumption_bound"]))
    if "max_backtracks" in s:
        m.add("AdvMaxBacktracks", count(s["max_backtracks"]), "pops of choice points in one query")
        m.add("AdvMaxBacktracksCells", listing([tt(c) for c in s["max_backtracks_cells"]]))
        m.add("AdvMaxEntries", count(s["max_entries"]))
        m.add("AdvMaxWalkedNodes", count(s["max_walked_nodes"]))
        m.add("AdvMaxDeepestStack", count(s["max_deepest_stack"]))
        m.add("AdvMaxResumptions", count(s["max_max_resumptions_per_node"]), "of one node in one query")
        m.add("AdvMaxEntriesPerNode", count(s["max_max_entries_per_node"]))
    if "ns_per_entry_min" in s:
        m.add("AdvNsPerEntryMin", fixed(s["ns_per_entry_min"], 2))
        m.add("AdvNsPerEntryMedian", fixed(s["ns_per_entry_median"], 2))
        m.add("AdvNsPerEntryMax", fixed(s["ns_per_entry_max"], 2))
        m.add("AdvSlowestNs", nanoseconds(s["slowest_ns"]))
        m.add("AdvSlowestCell", tt(s["slowest_cell"]))
    for c in result["cells"]:
        if "family" not in c:
            continue
        w = "Adv" + cell_word(c)
        m.add(w + "Entries", count(c["entries"]))
        m.add(w + "Backtracks", count(c["popped"]))
        m.add(w + "Deepest", count(c["deepest_stack"]))
        if "ns_median" in c:
            m.add(w + "Ns", nanoseconds(c["ns_median"]), f"median of {c['usable']} processes")
            m.add(w + "NsMin", nanoseconds(c["ns_min"]))
            m.add(w + "NsMax", nanoseconds(c["ns_max"]))
        if "ns_per_entry" in c:
            m.add(w + "NsPerEntry", fixed(c["ns_per_entry"], 2))
    return m


def load(run: Path) -> tuple[list[dict], dict[str, int]]:
    path = run / "cells.jsonl" if run.is_dir() else run
    return jsonl(path), planned_of(run)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path, help="the summary as JSON")
    ap.add_argument("--macros", type=Path, help="the Adv macros as LaTeX")
    a = ap.parse_args()
    lines, planned = load(a.run)
    result = summarize(lines, planned)
    if a.out:
        a.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    if a.macros:
        a.macros.write_text(macros(result).text(), encoding="utf-8")
    s = result["summary"]
    for c in result["cells"]:
        ns = f"{c['ns_median']:.1f} ns ({c['ns_min']:.1f} to {c['ns_max']:.1f})" if "ns_median" in c else "no time"
        print(f"{c['cell']:<28} {c['usable']}/{c['planned']} usable, entries {c.get('entries', '-')}, "
              f"backtracks {c.get('popped', '-')}, deepest {c.get('deepest_stack', '-')}, {ns}")
        for p in c["not_usable"]:
            print(f"    rep {p['rep']}: {p['reason']}")
    print(f"adversarial: the written bound {s['decision']} ({s['processes_usable']} of {s['processes']} "
          f"processes usable, {s['processes_planned']} planned); largest backtracks per query "
          f"{s.get('max_backtracks', '-')} ({', '.join(s.get('max_backtracks_cells', []))})")
    return 0 if s["decision"] != "fails" else 1


if __name__ == "__main__":
    raise SystemExit(main())
