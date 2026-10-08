#!/usr/bin/env python3
"""End-to-end test of the round-2 analysis on a synthetic run (analysis/analyse.py, macros.py,
ablation.py, tables.py, h5_stats.py).

    python analysis/test_pipeline.py        (or: python -m pytest analysis/test_pipeline.py)

A synthetic publication run (analysis/synth.py: every H1 cell with the design's sixteen pairs,
v2 at 0.8 times the fastest competitor, the compile-time table as fast as the run-time one, the
ablation arm 1.25 times slower than v2, probes for v2 and v1, provenance.txt) and a synthetic T1
run go through analyse.py. Checked: every output file is written; the summary's decisions are
those the inputs imply; every macro of macros.tex comes from summary.json (its value is the
summary's, formatted), and a macro whose source is absent is not written. Pure NumPy and the
standard library.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyse  # noqa: E402
import macros  # noqa: E402
from cells import ABLATION, V1, V2, design_pairs  # noqa: E402
from synth import grid_rows, row, write_run  # noqa: E402
from test_decisions import windows  # noqa: E402

B = 1000


def probes() -> list[dict]:
    out = []
    for case in ("static-then-param", "param-then-static", "pchar", "raw-bytes", "catch-all", "empty-segment",
                 "trailing-slash", "method"):
        out.append({"arm": V2, "case": case, "status": "pass"})
        out.append({"arm": V1, "case": case, "status": "fail" if case in ("param-then-static", "pchar") else "pass"})
    out.append({"arm": "null", "status": "not applicable"})
    return out


def synthetic_run(d: Path) -> Path:
    rows = grid_rows(0.8)
    extra = []
    for r in rows:
        if r["arm"] == V2:
            extra.append(dict(r, arm=ABLATION, ns_median=r["ns_median"] * 1.25, instructions=r["instructions"] * 1.2,
                              build_s_median=r["build_s_median"] * 2.0))
        if r["arm"] == V2 and r["table_seed"] == 111 and r["ring_seed"] == 211 and \
                (r["m"] == 10 or (r["m"] == 10000 and r["shape"] in ("rest", "param-last"))):
            extra.append(row(V1, r["shape"], r["m"], (111, 211), 1000.0))
    write_run(d, rows + extra)
    (d / "probes.jsonl").write_text("".join(json.dumps(p) + "\n" for p in probes()), encoding="utf-8")
    (d / "provenance.txt").write_text("code_commit: a79ae4b0\nregexmatcher_commit: d1d73e99b7b2\n"
                                      "compiler: Clang 22.1.8\npins_sha256: c0857145b690 (x)\nseed: 20261009\n",
                                      encoding="utf-8")
    return d


def synthetic_t1(d: Path, t0_v2_ns: float = 40.0) -> Path:
    # v1 at 1,000 ns and v2 at about 40 ns per lookup at T0 (grid_rows gives v2 about 0.8 x 50);
    # T1: 10 us per request for null, and differences equal to T0's.
    import h6_stats
    for cell in h6_stats.CELLS:
        rps = {"h6-null": 1e5, "h6-v1": 1 / (10e-6 + 1000e-9), "h6-v2": 1 / (10e-6 + t0_v2_ns * 1e-9)}
        f = d / cell / "t1" / "windows.jsonl"
        f.parent.mkdir(parents=True)
        f.write_text("".join(json.dumps(w) + "\n" for w in windows(6, rps)), encoding="utf-8")
    return d


def test_pipeline_end_to_end():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        run = synthetic_run(tmp / "run")
        t1 = synthetic_t1(tmp / "t1")
        out = tmp / "out"
        s = analyse.analyse(run, out, t1=t1, resamples=B)
        for f in ("h1.csv", "h2.csv", "h3.csv", "h4.csv", "h5b.csv", "h6.csv", "h7.csv", "ablation.csv",
                  "all_arms.csv", "summary.json"):
            assert (out / f).exists(), f
        assert s["h1"]["passed"] == 35 and s["h1"]["holds"]
        assert s["h3"]["holds"] and s["h5b"]["holds"] and s["h7"]["held"] == 21
        assert s["h6"]["a_holds"], s["h6"]
        assert s["ablation"]["compared"] == 35
        assert abs(s["ablation"]["time_ratio_min"] - 0.8) < 1e-9 and abs(s["ablation"]["build_ratio_max"] - 0.5) < 1e-9
        text = macros.render(json.loads((out / "summary.json").read_text(encoding="utf-8")))
        defs = dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{([^\n]*)\}", text))
        assert defs["HOnePassed"] == "35" and defs["HOneVerdict"] == "holds"
        assert defs["HSevenHeld"] == "21" and defs["HFiveBVerdict"] == "holds"
        assert defs["RoundTwoOrderSeed"] == "20261009" and defs["RoundTwoReps"] == "16"
        assert defs["HOneFastestRestTen"] == "\\texttt{gin}"
        r = next(x for x in s["h1_cells"] if x["shape"] == "rest" and x["m"] == 10)
        assert defs["HOneRatioRestTen"] == f"{r['ratio']:.4f}"
        # no digit in any macro that the summary does not hold (the commit, compiler and seeds aside)
        assert len(defs) == len(set(defs))
        # without the T1 run, no H6 macro
        s2 = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        s2.pop("h6"), s2.pop("h6_cells")
        assert "HSix" not in macros.render(s2)


def test_pairs_must_be_the_design():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        run = synthetic_run(tmp / "run")
        rows = [json.loads(x) for x in (run / "cells.jsonl").read_text().splitlines()]
        rows = [r for r in rows if (r["table_seed"], r["ring_seed"]) != design_pairs()[5]]
        (run / "cells.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        s = analyse.analyse(run, tmp / "out", resamples=B)
        assert s["h1"]["passed"] == 0 and s["h1"]["fails"] == 35
        s = analyse.analyse(run, tmp / "out2", resamples=B, any_pairs=True)
        assert s["h1"]["passed"] == 35


def test_the_grid_check_on_every_query_is_read():
    # A competitor's process cut by the agreement budget fails its cell unless the run directory
    # holds a check that agreed on every query of the same table and ring (run_grid.sh writes it).
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        run = synthetic_run(tmp / "run")
        rows = [json.loads(x) for x in (run / "cells.jsonl").read_text().splitlines()]
        cut = next(r for r in rows if r["arm"] == "gin" and r["shape"] == "rest" and r["m"] == 100000)
        cut["verified_all"] = False
        cut["table_digest"], cut["ring_digest"] = "t", "r"
        (run / "cells.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        s = analyse.analyse(run, tmp / "out", resamples=B)
        cell = next(r for r in s["h1_cells"] if r["shape"] == "rest" and r["m"] == 100000)
        assert cell["status"] == "fails" and "not verified on every query" in cell["failures"]
        assert s["verified"] is None
        check = {"arm": "gin", "shape": "rest", "m": 100000, "table_seed": cut["table_seed"],
                 "ring_seed": cut["ring_seed"], "digests_match": True, "agrees_all": True}
        (run / "verified.jsonl").write_text(json.dumps(check) + "\n")
        s = analyse.analyse(run, tmp / "out2", resamples=B)
        cell = next(r for r in s["h1_cells"] if r["shape"] == "rest" and r["m"] == 100000)
        assert cell["status"] == "tested" and "gin" in cell["competitors"]
        assert s["verified"].endswith("verified.jsonl")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok: {t.__name__}")
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
