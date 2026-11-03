#!/usr/bin/env python3
"""Tests of analysis/adversarial.py on synthetic lines (design/review-runs/adversarial.md).

    python analysis/test_adversarial.py        (or: python -m pytest analysis/test_adversarial.py)

The oracles are computed here by hand. A run is the tool's 44 cells, three processes each:
1. A crash is listed, not dropped; the bound holds; the median of ns_median and its range are over
   the usable processes only (5, 6, 7 gives 6 with 5 and 7); the time per node entered is that median
   over the entries; the largest backtracks name every cell with the most pops.
2. One line with a failed check makes the decision "fails" and names its cell; processes of one
   cell that disagree on a count fail too; a cell with no usable process leaves it undecided.
3. Only the frozen run is usable: 21 epochs, not quick, the run's common ring size, exit 0. A quick,
   short, other-ring, unmarked or nonzero-exit process is listed with its reason and is not counted;
   a run of all quick processes is undecided.
4. The bound holds only when all 44 cells of cells.txt have usable processes: a subset, a missing or
   short cells.txt, or a cell that cells.txt does not list is undecided.
5. The macros are letters only, carry the per-cell names, and round as macros_util does.
6. The run directory form reads cells.jsonl, plan.txt and cells.txt, and the command exits 1 only when
   the bound fails.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from adversarial import macros, summarize  # noqa: E402

RING = 4096
QUERIES = ("miss", "last-hit", "other-method")


def all_cells() -> list[dict]:
    """The tool's 44 cells (adversarial list): every query on 11 tables, miss on the 11 with a catch-all."""
    out = []
    for family, short, depths in (("two-kinds", "two", (1, 2, 4, 8, 12, 16)), ("four-kinds", "four", (1, 2, 4, 6, 8))):
        for k in depths:
            for catch_all in (False, True):
                for q in QUERIES:
                    if not catch_all or q == "miss":
                        out.append({"cell": f"{short}-k{k}" + ("-catch-all" if catch_all else "") + f"-{q}",
                                    "family": family, "depth": k, "catch_all": catch_all, "query": q})
    return out


CELLS = all_cells()
IDS = [c["cell"] for c in CELLS]
META = {c["cell"]: c for c in CELLS}
assert len(IDS) == 44 and len(set(IDS)) == 44


def line(cell: str, rep: int, ns: float, *, popped: int = 15, entries: int = 32, ok: bool = True,
         epochs: int = 21, ring: int = RING, **over) -> dict:
    r = {"tool": "adversarial", **META[cell], "rep": rep, "quick": False, "epochs": epochs, "method": "GET",
         "path": "/a/miss", "routes": 2, "walks": 2, "walks_expected": 2, "walked_nodes": 393214,
         "entries": entries, "resumptions": popped, "pushed": popped, "popped": popped,
         "deepest_stack": META[cell]["depth"], "max_entries_per_node": 1, "max_resumptions_per_node": 1,
         "expected_answer": True, "same_answer": True, "bound_entries": ok, "bound_resumptions": True,
         "counted": True, "pops_resume": True, "entered_once": True, "walks_as_expected": True,
         "checks_ok": ok, "status": "ok", "ring_size": ring, "agrees": True, "verified_all": True,
         "ns_median": ns, "epoch_ns": [ns] * epochs}
    r.update(over)
    return r


# Per cell, the lines of 3 processes: ns 7, 5, 6 for two-k16-miss, the slowest cell, and 0.5, 1, 0.75 for the rest.
SPECIAL = {"two-k16-miss": {"popped": 65535, "entries": 131071}}


def run_lines(reps: int = 3, only: list[str] | None = None) -> list[dict]:
    out = []
    for cid in only or IDS:
        for rep in range(reps):
            ns = (7.0, 5.0, 6.0)[rep % 3] if cid == "two-k16-miss" else (0.5, 1.0, 0.75)[rep % 3]
            if cid == "two-k4-last-hit":
                out.append({"cell": cid, "rep": 2, "status": "crash", "exit": 139} if rep == 2
                           else line(cid, rep, (2.0, 3.0)[rep], **SPECIAL.get(cid, {})))
            else:
                out.append(line(cid, rep, ns, **SPECIAL.get(cid, {})))
    return out


def summary_of(lines: list[dict], **kw) -> dict:
    kw.setdefault("expected_cells", IDS)
    return summarize(lines, **kw)


def replaced(lines: list[dict], cid: str, **over) -> list[dict]:
    """The run with the usable lines of one cell changed by over."""
    return [{**r, **over} if r["cell"] == cid and r.get("status") == "ok" else r for r in lines]


def test_holds_and_reports():
    res = summary_of(run_lines())
    s = res["summary"]
    assert s["decision"] == "holds", s
    assert s["cells"] == 44 and s["expected_cells"] == 44 and s["ring_size"] == RING
    assert s["processes"] == 132 and s["processes_usable"] == 131
    cells = {c["cell"]: c for c in res["cells"]}
    big = cells["two-k16-miss"]
    assert big["ns_median"] == 6.0 and big["ns_min"] == 5.0 and big["ns_max"] == 7.0
    assert abs(big["ns_per_entry"] - 6.0 / 131071) < 1e-15
    small = cells["two-k4-last-hit"]
    assert small["usable"] == 2 and small["ns_median"] == 2.5
    assert small["not_usable"] == [{"rep": 2, "reason": "status crash (exit 139)"}]
    assert s["max_backtracks"] == 65535 and s["max_backtracks_cells"] == ["two-k16-miss"]
    assert s["max_deepest_stack"] == 16 and s["max_entries"] == 131071
    assert s["slowest_cell"] == "two-k16-miss" and s["slowest_ns"] == 6.0


def test_failures_and_undecided():
    bad = run_lines() + [line("two-k16-miss", 3, 6.0, ok=False)]
    s = summary_of(bad)["summary"]
    assert s["decision"] == "fails" and s["failing_cells"] == ["two-k16-miss"]
    differ = run_lines() + [line("two-k16-miss", 3, 6.0, popped=65534)]
    assert summary_of(differ)["summary"]["decision"] == "fails"
    # each guard against a vacuous count fails on its own
    for guard in ("counted", "pops_resume", "entered_once", "walks_as_expected"):
        s = summary_of(replaced(run_lines(), "four-k8-miss", **{guard: False}))["summary"]
        assert s["decision"] == "fails" and s["failing_cells"] == ["four-k8-miss"], guard
    # a cell with no line at all is undecided, and so is one whose only lines crashed
    without = [r for r in run_lines() if r["cell"] != "four-k8-miss"]
    s = summary_of(without, planned={"four-k8-miss": 3})["summary"]
    assert s["decision"] == "undecided" and s["undecided_cells"] == ["four-k8-miss"]
    assert s["processes_planned"] == 132
    crashed = [r if r["cell"] != "four-k8-miss" else {"cell": r["cell"], "rep": r["rep"], "status": "crash", "exit": 1}
               for r in run_lines()]
    s = summary_of(crashed)["summary"]
    assert s["decision"] == "undecided" and s["undecided_cells"] == ["four-k8-miss"]


def test_only_the_frozen_run_is_usable():
    # a quick process: listed with its reason, not usable
    quick = run_lines() + [line("two-k1-miss", 3, 1.0, quick=True, epochs=2, ring=64)]
    res = summary_of(quick)
    assert res["summary"]["decision"] == "holds"
    cell = {c["cell"]: c for c in res["cells"]}["two-k1-miss"]
    assert cell["usable"] == 3 and len(cell["not_usable"]) == 1
    assert "a quick run" in cell["not_usable"][0]["reason"]
    reason = cell["not_usable"][0]["reason"]
    assert "2 epochs, not 21" in reason and "ring size 64, not 4096" in reason
    assert cell["ns_median"] == 0.75  # the quick process (1.0 ns) is not in the median
    # a run of quick processes only is undecided, every process listed
    allquick = [line(cid, k, 1.0, quick=True, epochs=2, ring=64) for cid in IDS for k in range(3)]
    s = summary_of(allquick)["summary"]
    assert s["decision"] == "undecided" and s["processes_usable"] == 0 and len(s["undecided_cells"]) == 44
    assert s["ring_size"] == 64  # the common ring is 64; the quick flag still refuses them
    # 21 epochs, and 21 values
    short = replaced(run_lines(), "four-k8-miss", epochs=20, epoch_ns=[1.0] * 20)
    s = summary_of(short)["summary"]
    assert s["decision"] == "undecided" and s["undecided_cells"] == ["four-k8-miss"]
    lying = replaced(run_lines(), "four-k8-miss", epoch_ns=[1.0] * 20)  # epochs says 21, the values say 20
    assert summary_of(lying)["summary"]["undecided_cells"] == ["four-k8-miss"]
    # the run's ring size: an odd process is listed, a cell of odd processes is undecided
    odd = run_lines() + [line("two-k1-miss", 3, 1.0, ring=1024)]
    cell = {c["cell"]: c for c in summary_of(odd)["cells"]}["two-k1-miss"]
    assert cell["usable"] == 3 and cell["not_usable"][0]["reason"].endswith("ring size 1024, not 4096")
    other_ring = replaced(run_lines(), "four-k8-miss", ring_size=1024)
    assert summary_of(other_ring)["summary"]["undecided_cells"] == ["four-k8-miss"]
    # --ring names the ring: a run all of another ring is refused
    s = summary_of(run_lines(), ring=64)["summary"]
    assert s["decision"] == "undecided" and s["processes_usable"] == 0
    # two sizes in equal numbers have no common ring
    tie = [line("two-k1-miss", 0, 1.0), line("two-k1-miss", 1, 1.0, ring=64)]
    s = summary_of(tie)["summary"]
    assert s["ring_size"] is None and s["processes_usable"] == 0
    # a line from an older tool, without quick and epochs, is not the frozen run
    old = [{k: v for k, v in r.items() if k not in ("quick", "epochs")} for r in run_lines()]
    s = summary_of(old)["summary"]
    assert s["decision"] == "undecided" and s["processes_usable"] == 0
    # a process that exited nonzero is not usable even if it printed an ok line
    exited = replaced(run_lines(), "four-k8-miss", exit=1)
    cell = {c["cell"]: c for c in summary_of(exited)["cells"]}["four-k8-miss"]
    assert cell["usable"] == 0 and cell["not_usable"][0]["reason"] == "exit 1"


def test_all_44_cells_needed():
    # a subset of the cells, as a CELLS run makes: never "holds", although every line passes
    few = run_lines(only=["two-k1-miss", "two-k2-miss", "four-k1-miss"])
    s = summary_of(few)["summary"]
    assert s["decision"] == "undecided" and len(s["undecided_cells"]) == 41
    s = summary_of(few, planned={"two-k1-miss": 3, "two-k2-miss": 3, "four-k1-miss": 3})["summary"]
    assert s["decision"] == "undecided" and s["processes_planned"] == 9
    # without cells.txt, or with a short one, or with a cell it does not list
    assert summarize(run_lines())["summary"]["decision"] == "undecided"
    assert summary_of(run_lines(), expected_cells=IDS[:43])["summary"]["decision"] == "undecided"
    extra = summary_of(run_lines() + [{"cell": "nowhere", "rep": 0, "status": "crash", "exit": 1}])["summary"]
    assert extra["decision"] == "undecided" and extra["unknown_cells"] == ["nowhere"]
    # one usable process per cell is enough to decide, the counts being exact
    assert summary_of(run_lines(reps=1))["summary"]["decision"] == "holds"


def test_macros():
    m = macros(summary_of(run_lines()))
    text = m.text()
    assert all(name.startswith("Adv") and name.isalpha() for name, _, _ in m.items)
    assert "\\newcommand{\\AdvMaxBacktracks}{65{,}535}" in text
    assert "\\newcommand{\\AdvTwoKindsSixteenMissNs}{6.0}" in text
    assert "\\newcommand{\\AdvTwoKindsFourLastHitBacktracks}{15}" in text
    assert "\\newcommand{\\AdvBoundDecision}{holds}" in text
    assert "\\newcommand{\\AdvMaxBacktracksCells}{\\texttt{two-k16-miss}}" in text
    text = macros(summarize(run_lines()[:3]))
    assert "\\newcommand{\\AdvBoundDecision}{undecided}" in text.text()


def test_ties_listed():
    # Without the catch-all, miss and other-method walk the same two tries: equal pops, both named.
    big = {"popped": 65535, "entries": 131071}
    lines = [line(cid, k, 6.0, **(big if cid in ("two-k16-miss", "two-k16-other-method") else {}))
             for cid in IDS for k in range(3)]
    res = summary_of(lines)
    assert res["summary"]["max_backtracks_cells"] == ["two-k16-miss", "two-k16-other-method"]
    assert "{\\texttt{two-k16-miss} and \\texttt{two-k16-other-method}}" in macros(res).text()


def test_command_on_run_dir():
    with tempfile.TemporaryDirectory() as t:
        run = Path(t)
        (run / "cells.jsonl").write_text("\n".join(json.dumps(r) for r in run_lines()) + "\n", encoding="utf-8")
        (run / "plan.txt").write_text("".join(f"{c} {k}\n" for c in IDS for k in range(3)), encoding="utf-8")
        (run / "cells.txt").write_text("".join(f"{c['cell']}\t{c['family']}\t{c['depth']}\t"
                                               f"{'catch-all' if c['catch_all'] else 'none'}\t{c['query']}\n"
                                               for c in CELLS), encoding="utf-8")
        cmd = [sys.executable, str(HERE / "adversarial.py"), str(run), "--out", str(run / "s.json"),
               "--macros", str(run / "m.tex")]
        assert subprocess.run(cmd, capture_output=True, text=True).returncode == 0
        s = json.loads((run / "s.json").read_text(encoding="utf-8"))["summary"]
        assert s["processes_planned"] == 132 and s["decision"] == "holds" and s["expected_cells"] == 44
        assert "AdvTwoKindsSixteenMissNsPerEntry" in (run / "m.tex").read_text(encoding="utf-8")
        # the ring named on the command line must be the run's
        ring = subprocess.run(cmd + ["--ring", str(RING)], capture_output=True, text=True)
        assert ring.returncode == 0 and json.loads((run / "s.json").read_text(encoding="utf-8"))["summary"][
            "decision"] == "holds"
        assert subprocess.run(cmd + ["--ring", "64"], capture_output=True, text=True).returncode == 0
        assert json.loads((run / "s.json").read_text(encoding="utf-8"))["summary"]["decision"] == "undecided"
        # a subset plan is undecided, exit 0
        (run / "plan.txt").write_text("two-k1-miss 0\n", encoding="utf-8")
        assert subprocess.run(cmd, capture_output=True, text=True).returncode == 0
        # without cells.txt: undecided
        (run / "cells.txt").unlink()
        assert subprocess.run(cmd, capture_output=True, text=True).returncode == 0
        assert json.loads((run / "s.json").read_text(encoding="utf-8"))["summary"]["decision"] == "undecided"
        with (run / "cells.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line("two-k16-miss", 3, 6.0, ok=False)) + "\n")
        assert subprocess.run(cmd, capture_output=True, text=True).returncode == 1


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok: {t.__name__}")
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
