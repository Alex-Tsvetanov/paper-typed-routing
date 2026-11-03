#!/usr/bin/env python3
"""Tests of analysis/adversarial.py on synthetic lines (design/review-runs/adversarial.md).

    python analysis/test_adversarial.py        (or: python -m pytest analysis/test_adversarial.py)

The oracles are computed here by hand:
1. Two cells, three processes each, one of them a crash: the bound holds; the crash is listed, not
   dropped; the median of ns_median and its range are over the usable processes only (5, 6, 7 gives
   6 with 5 and 7); the time per node entered is that median over the entries; the largest
   backtracks name every cell with the most pops.
2. One line with a failed check makes the decision "fails" and names its cell; processes of one
   cell that disagree on a count fail too; a cell planned but with no line with counts leaves the
   decision undecided.
3. The macros are letters only, carry the per-cell names, and round as macros_util does.
4. The run directory form reads cells.jsonl and plan.txt, and the command exits 1 when the bound fails.
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


def line(cell: str, rep: int, ns: float, *, depth: int = 16, query: str = "miss", popped: int = 65535,
         entries: int = 131071, ok: bool = True, **over) -> dict:
    r = {"tool": "adversarial", "cell": cell, "rep": rep, "family": "two-kinds", "depth": depth, "catch_all": False,
         "query": query, "method": "GET", "path": "/a/miss", "routes": 2, "walks": 2, "walked_nodes": 393214,
         "entries": entries, "resumptions": popped, "pushed": popped, "popped": popped, "deepest_stack": depth,
         "max_entries_per_node": 1, "max_resumptions_per_node": 1, "expected_answer": True, "same_answer": True,
         "bound_entries": ok, "bound_resumptions": True, "checks_ok": ok, "status": "ok", "agrees": True,
         "verified_all": True, "ns_median": ns, "epoch_ns": [ns] * 21}
    r.update(over)
    return r


def two_cells() -> list[dict]:
    return [line("two-k16-miss", 0, 7.0), line("two-k16-miss", 1, 5.0), line("two-k16-miss", 2, 6.0),
            line("two-k4-last-hit", 0, 2.0, depth=4, query="last-hit", popped=15, entries=32),
            line("two-k4-last-hit", 1, 3.0, depth=4, query="last-hit", popped=15, entries=32),
            {"cell": "two-k4-last-hit", "rep": 2, "status": "crash", "exit": 139}]


def test_holds_and_reports():
    res = summarize(two_cells())
    s = res["summary"]
    assert s["decision"] == "holds"
    assert s["processes"] == 6 and s["processes_usable"] == 5
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
    bad = two_cells() + [line("two-k16-miss", 3, 6.0, ok=False)]
    s = summarize(bad)["summary"]
    assert s["decision"] == "fails" and s["failing_cells"] == ["two-k16-miss"]
    differ = two_cells() + [line("two-k16-miss", 3, 6.0, popped=65534)]
    assert summarize(differ)["summary"]["decision"] == "fails"
    planned = {"two-k16-miss": 3, "two-k4-last-hit": 3, "four-k8-miss": 3}
    s = summarize(two_cells(), planned)["summary"]
    assert s["decision"] == "undecided" and s["undecided_cells"] == ["four-k8-miss"]
    assert s["processes_planned"] == 9


def test_macros():
    m = macros(summarize(two_cells()))
    text = m.text()
    assert all(name.startswith("Adv") and name.isalpha() for name, _, _ in m.items)
    assert "\\newcommand{\\AdvMaxBacktracks}{65{,}535}" in text
    assert "\\newcommand{\\AdvTwoKindsSixteenMissNs}{6.0}" in text
    assert "\\newcommand{\\AdvTwoKindsFourLastHitBacktracks}{15}" in text
    assert "\\newcommand{\\AdvBoundDecision}{holds}" in text
    assert "\\newcommand{\\AdvMaxBacktracksCells}{\\texttt{two-k16-miss}}" in text


def test_ties_listed():
    # Without the catch-all, miss and other-method walk the same two tries: equal pops, both named.
    lines = [line("two-k16-miss", 0, 6.0), line("two-k16-other-method", 0, 9.0, query="other-method")]
    res = summarize(lines)
    assert res["summary"]["max_backtracks_cells"] == ["two-k16-miss", "two-k16-other-method"]
    assert "{\\texttt{two-k16-miss} and \\texttt{two-k16-other-method}}" in macros(res).text()


def test_command_on_run_dir():
    with tempfile.TemporaryDirectory() as t:
        run = Path(t)
        (run / "cells.jsonl").write_text("\n".join(json.dumps(r) for r in two_cells()) + "\n", encoding="utf-8")
        (run / "plan.txt").write_text("two-k16-miss 0\ntwo-k16-miss 1\ntwo-k16-miss 2\n"
                                      "two-k4-last-hit 0\ntwo-k4-last-hit 1\ntwo-k4-last-hit 2\n", encoding="utf-8")
        cmd = [sys.executable, str(HERE / "adversarial.py"), str(run), "--out", str(run / "s.json"),
               "--macros", str(run / "m.tex")]
        assert subprocess.run(cmd, capture_output=True, text=True).returncode == 0
        s = json.loads((run / "s.json").read_text(encoding="utf-8"))["summary"]
        assert s["processes_planned"] == 6 and s["decision"] == "holds"
        assert "AdvTwoKindsSixteenMissNsPerEntry" in (run / "m.tex").read_text(encoding="utf-8")
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
