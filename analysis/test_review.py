#!/usr/bin/env python3
"""Tests of analysis/ablations.py and analysis/boundary.py on synthetic runs (design/review-runs/ablations.md,
boundary-arms.md).

    python analysis/test_review.py        (or: python -m pytest analysis/test_review.py)

The oracles are set by construction: every process's time is a known multiple of another arm's in the same
seed pair, times a small noise factor shared by the arms of a pair, so every per-pair ratio, and with it the
median over the pairs, is exact.
1. Ablations: the copy over the pinned arm is 1; ab-linear over the copy 1.25 and over the pinned arm 1.25;
   the interval holds the ratio; net instructions are the arm's minus the null's of its pair; the code
   lines come from code-size.tsv; a variant with one disagreeing process is failing in its cell, its
   comparisons there are not made and say why, and the process is listed; the 35 cells are all reported.
2. Boundary: the symmetric ratio of the C-interface arm to each Rust arm and to the fastest of them; v2's
   net time against the fastest competitor's net time, which is not the fastest on raw times; the nets use
   capi-null, rust-null, the Go arms' own null pass and the loop null of v2 and of the C++ competitors; an
   arm whose net time is not positive is listed and left out; gin absent where its answers differ as
   declared; v2 in a Go loop over each Go arm; the 14 cells are all reported.
3. The design's sixteen seed pairs are required: two arms with nine pairs each, overlapping on two, are not
   compared (neither through the analyses nor through ratio_ci), an arm with a pair twice and another missing
   is failing, and sixteen full pairs are compared and the comparison says it is over sixteen.
4. The macros are letters only, defined once, and carry the values above as macros_util rounds them.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ablations  # noqa: E402
import boundary  # noqa: E402
import numpy as np  # noqa: E402
import review_common  # noqa: E402
from cells import H1_SHAPES, H1_SIZES, design_pairs, load  # noqa: E402

failures = 0


def expect(ok: bool, what: str) -> None:
    global failures
    print(("ok: " if ok else "FAIL: ") + what)
    failures += 0 if ok else 1


def close(x: float | None, y: float, tol: float = 1e-9) -> bool:
    return x is not None and abs(x - y) <= tol * max(1.0, abs(y))


def line(arm: str, shape: str, m: int, pair: tuple, ns: float, **extra) -> dict:
    r = {"arm": arm, "shape": shape, "m": m, "table_seed": pair[0], "ring_seed": pair[1], "status": "ok",
         "agrees": True, "verified_all": True, "ns_median": ns, "ring_size": 4096, "lookups_per_pass": 4096}
    r.update(extra)
    return r


def noise(k: int) -> float:
    return 1.0 + 0.01 * ((k * 7) % 5)


def ablation_lines() -> list[dict]:
    out = []
    for shape in H1_SHAPES:
        for m in H1_SIZES:
            for k, p in enumerate(design_pairs()):
                f = noise(k)
                base = 100.0 * f
                ins = {"loop_null": "null", "throughput_loop": "harness", "branch_misses": 0.5}
                out.append(line("null", shape, m, p, 5.0 * f, instructions=20.0, null_arm=True, loop_null=""))
                out.append(line("regexmatcher-v2", shape, m, p, base, instructions=500.0, **ins))
                out.append(line("regexmatcher-v2-copy", shape, m, p, base, instructions=500.0, **ins))
                out.append(line("regexmatcher-v2-ab-linear", shape, m, p, 1.25 * base, instructions=620.0, **ins))
                out.append(line("regexmatcher-v2-ab-hashed", shape, m, p, 0.8 * base, instructions=480.0, **ins))
                out.append(line("regexmatcher-v2-ab-noexact", shape, m, p, 1.1 * base, instructions=550.0, **ins))
                bad = shape == "rest" and m == 1000 and k == 3
                out.append(line("regexmatcher-v2-ab-bytes", shape, m, p, 1.05 * base, instructions=530.0,
                                **({**ins, "status": "disagrees", "agrees": False, "answers_differ": 2} if bad else ins)))
    return out


def boundary_lines() -> list[dict]:
    out = []
    for shape in H1_SHAPES:
        for m in (10, 100):
            for k, p in enumerate(design_pairs()):
                f = noise(k)
                harness = {"throughput_loop": "harness"}
                go = {"throughput_loop": "arm", "loop_null": "own"}
                out.append(line("null", shape, m, p, 3.0 * f, null_arm=True, loop_null="", **harness))
                out.append(line("null-no405", shape, m, p, 3.0 * f, null_arm=True, loop_null="", **harness))
                out.append(line("capi-null", shape, m, p, 4.0 * f, null_arm=True, loop_null="", **harness))
                rust_null = 30.0 if (shape, m) == ("static", 100) else 5.0  # matchit's net is then not positive
                out.append(line("rust-null", shape, m, p, rust_null * f, null_arm=True, loop_null="", **harness))
                out.append(line("regexmatcher-v2", shape, m, p, 13.0 * f, loop_null="null", **harness))
                out.append(line("regexmatcher-v2-capi", shape, m, p, 22.0 * f, loop_null="null-no405", **harness))
                out.append(line("regexmatcher-v2-goloop", shape, m, p, 60.0 * f, null_ns=2.0 * f, **go))
                out.append(line("matchit", shape, m, p, 25.0 * f, loop_null="null-no405", **harness))   # net 20
                out.append(line("actix-router", shape, m, p, 55.0 * f, loop_null="null-no405", **harness))  # net 50
                pt = 4.0 if (shape, m) == ("static", 10) else 45.0  # net -1 (not positive) or 40
                out.append(line("path-tree", shape, m, p, pt * f, loop_null="null-no405", **harness))
                gin = ({"status": "disagrees", "agrees": False, "answers_differ": 300, "id_mismatches": 300,
                        "id_mismatches_404": 300, "capture_mismatches": 0} if shape == "mixed-overlap" else {})
                out.append(line("gin", shape, m, p, 30.0 * f, null_ns=2.0 * f, **{**go, **gin}))  # net 28
                out.append(line("httprouter", shape, m, p, 40.0 * f, null_ns=2.0 * f, **go))
                out.append(line("nethttp", shape, m, p, 120.0 * f, null_ns=2.0 * f, **go))
                out.append(line("chi", shape, m, p, 150.0 * f, null_ns=2.0 * f, **go))
                out.append(line("uwebsockets", shape, m, p, 24.0 * f, loop_null="null-no405", **harness))  # net 21
                out.append(line("glaze", shape, m, p, 33.0 * f, loop_null="null-no405", **harness))  # net 30
    return out


def write_run(d: Path, lines: list[dict]) -> Path:
    d.mkdir(parents=True)
    (d / "cells.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines), encoding="utf-8")
    return d


def macro_values(text: str) -> dict[str, str]:
    names = re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{([^\n]*)\}", text)
    return dict(names)


def check_ablations(tmp: Path) -> None:
    run = write_run(tmp / "abl", ablation_lines())
    code = tmp / "code-size.tsv"
    code.write_text("arm\tlines\tfunctions\tsha256\nregexmatcher-v2\t892\t4\tx\nregexmatcher-v2-copy\t892\t4\tx\n"
                    "regexmatcher-v2-ab-bytes\t866\t4\ty\n", encoding="utf-8")
    s = ablations.summarize(load(run), ablations.read_code_size(code), resamples=400)
    expect(len(s["cells"]) == 35, "ablations: the 35 cells are all reported")
    cell = next(r for r in s["cells"] if (r["shape"], r["m"]) == ("static", 10))
    comp = {(c["arm"], c["reference"]): c for c in cell["comparisons"]}
    c = comp[("regexmatcher-v2-copy", "regexmatcher-v2")]
    expect(c["status"] == "compared" and close(c["ratio"], 1.0) and c["pairs"] == 16, "ablations: copy / pinned is 1")
    c = comp[("regexmatcher-v2-ab-linear", "regexmatcher-v2-copy")]
    expect(close(c["ratio"], 1.25) and c["low"] <= c["ratio"] <= c["high"],
           "ablations: ab-linear / copy is 1.25, inside its interval")
    expect(close(comp[("regexmatcher-v2-ab-hashed", "regexmatcher-v2")]["ratio"], 0.8),
           "ablations: ab-hashed / pinned is 0.8")
    expect(close(cell["arms"]["regexmatcher-v2-ab-linear"]["net_instructions"], 600.0),
           "ablations: net instructions are the arm's less the null's (620 - 20)")
    expect(close(cell["arms"]["regexmatcher-v2"]["branch_misses"], 0.5), "ablations: branch misses, raw")
    expect(s["code_lines"]["regexmatcher-v2-ab-bytes"] == 866 and s["code_lines"]["regexmatcher-v2-ab-linear"] is None,
           "ablations: code lines from code-size.tsv, none where it has no row")
    bad = next(r for r in s["cells"] if (r["shape"], r["m"]) == ("rest", 1000))
    bcomp = [c for c in bad["comparisons"] if c["arm"] == "regexmatcher-v2-ab-bytes"]
    expect("regexmatcher-v2-ab-bytes" in bad["failing"] and all(c["status"] == "not compared" for c in bcomp)
           and all("ab-bytes" in c["why"] for c in bcomp), "ablations: a disagreeing variant is failing, not compared")
    expect(any("regexmatcher-v2-ab-bytes" in u and "disagrees" in u for u in bad["unusable"]),
           "ablations: the disagreeing process is listed")
    t = s["totals"]["regexmatcher-v2-ab-bytes / regexmatcher-v2-copy"]
    expect(t["cells"] == 34 and close(t["ratio_min"], 1.05), "ablations: the totals count the cells compared")
    text = ablations.macros(s)
    v = macro_values(text)
    expect(text.count("\\newcommand") == len(v), "ablations: every macro is defined once")
    expect(v.get("AblLinearVsCopyStaticTenRatio") == "1.2500" and v.get("AblCopyVsVtwoStaticTenRatio") == "1.0000",
           "ablations: ratio macros")
    expect(v.get("AblBytesCodeLines") == "866" and "AblLinearCodeLines" not in v, "ablations: code-line macros")
    expect(v.get("AblLinearStaticTenNetInstructions") == "600.0", "ablations: net instruction macros")
    expect("AblBytesVsCopyRestThousandRatio" not in v, "ablations: no macro where no comparison was made")


def check_boundary(tmp: Path) -> None:
    run = write_run(tmp / "bnd", boundary_lines())
    s = boundary.summarize(load(run), resamples=400)
    expect(len(s["cells"]) == 14, "boundary: the 14 cells are all reported")
    cell = next(r for r in s["cells"] if (r["shape"], r["m"]) == ("param-last", 10))
    sym = {c["against"]: c for c in cell["symmetric"]}
    expect(close(sym["matchit"]["ratio"], 22 / 25) and close(sym["actix-router"]["ratio"], 22 / 55),
           "boundary: capi / each Rust arm, raw")
    expect(sym["fastest"]["fastest"] == "matchit" and close(sym["fastest"]["ratio"], 22 / 25),
           "boundary: capi / the fastest Rust arm")
    net = cell["net"]
    expect(net["status"] == "compared" and net["fastest"] == "matchit", "boundary: the fastest net competitor "
           "is matchit (net 20), not uwebsockets, the fastest raw (24)")
    expect(close(net["ratio"], (13 - 3) / (25 - 5), 1e-6) and net["low"] <= net["ratio"] <= net["high"],
           "boundary: v2 net / fastest net = 10 / 20")
    expect(net["raw"]["fastest"] == "uwebsockets" and close(net["raw"]["ratio"], 13 / 24),
           "boundary: beside it, the raw ratio against the fastest raw")
    arms = cell["arms"]
    expect(close(arms["regexmatcher-v2-capi"]["net_ns"], 18 * 1.02, 0.05) and
           close(arms["gin"]["net_ns"], 28 * 1.02, 0.05) and close(arms["glaze"]["net_ns"], 30 * 1.02, 0.05),
           "boundary: nets through capi-null, the Go null pass and null-no405")
    expect(close(arms["regexmatcher-v2-goloop"]["net_ns"], 58 * 1.02, 0.05), "boundary: goloop net of its Go null pass")
    gl = {c["against"]: c for c in cell["goloop"]}
    expect(close(gl["gin"]["ratio"], 2.0) and close(gl["chi"]["ratio"], 0.4), "boundary: goloop / each Go arm")
    st = next(r for r in s["cells"] if (r["shape"], r["m"]) == ("static", 10))
    expect(st["net_not_positive"] == ["path-tree"] and list(st["net_left_out"]) == ["path-tree"],
           "boundary: an arm with a net time not positive is listed, per cell, as left out")
    expect(st["net"]["status"] == "not compared" and st["net"]["pairs"] == 0 and "ratio" not in st["net"]
           and "path-tree" in st["net"]["why"] and "lowest raw median" in st["net"]["why"],
           "boundary: the arm left out has the lowest raw median (4 against 24): the net ratio is not computed")
    sh = next(r for r in s["cells"] if (r["shape"], r["m"]) == ("static", 100))
    expect(list(sh["net_left_out"]) == ["matchit"] and sh["net_not_positive"] == ["matchit"]
           and sh["net"]["status"] == "compared" and sh["net"]["fastest"] == "path-tree",
           "boundary: an arm left out that is not the lowest on raw times (25 against 24): the ratio is computed "
           "against the fastest net of the others (path-tree, 15)")
    expect(close(sh["net"]["ratio"], (13 - 3) / (45 - 30), 1e-6), "boundary: that ratio is 10 / 15")
    nl = next(r for r in s["cells"] if (r["shape"], r["m"]) == ("wild", 10))
    expect(nl["net_left_out"] == {}, "boundary: a cell where every arm is in the net comparison lists none")
    mo = next(r for r in s["cells"] if (r["shape"], r["m"]) == ("mixed-overlap", 100))
    gl = {c["against"]: c for c in mo["goloop"]}
    expect("gin" in mo["absent"] and gl["gin"]["status"] == "not compared" and "gin" in gl["gin"]["why"],
           "boundary: gin is absent where its answers differ as declared, and its comparison says why")
    text = boundary.macros(s)
    v = macro_values(text)
    expect(text.count("\\newcommand") == len(v), "boundary: every macro is defined once")
    expect(s["net_left_out_cells"] == 2 and v.get("BndNetLeftOutCells") == "2",
           "boundary: one macro counts the cells where an arm was left out of the net comparison (static 10 and 100)")
    expect(v.get("BndNetStaticTenRatio") is None and v.get("BndNetStaticHundredRatio") is not None,
           "boundary: no net macro where the ratio is not computed")
    expect(v.get("BndNetParamLastTenRatio") == "0.5000" and v.get("BndNetParamLastTenFastest") == "\\texttt{matchit}",
           "boundary: net macros")
    expect(v.get("BndCapiVsMatchitParamLastTenRatio") == "0.8800" and v.get("BndGoloopVsGinParamLastTenRatio") == "2.0000",
           "boundary: symmetric and Go-loop macros")
    expect(all(re.fullmatch(r"[A-Za-z]+", n) for n in v), "boundary: macro names are letters only")


def check_pairs(tmp: Path) -> None:
    pairs = design_pairs()
    # (static, 10): the copy on the first nine pairs, the pinned arm on the last nine, two in common;
    # (static, 100): both on all sixteen.
    lines = []
    for m, copy_at, pinned_at in ((10, range(0, 9), range(7, 16)), (100, range(16), range(16))):
        for k in copy_at:
            lines.append(line("regexmatcher-v2-copy", "static", m, pairs[k], 100.0 * noise(k)))
        for k in pinned_at:
            lines.append(line("regexmatcher-v2", "static", m, pairs[k], 100.0 * noise(k)))
    # (static, 1000): the copy has pair 3 twice and pair 15 not at all
    for k in [*range(15), 3]:
        lines.append(line("regexmatcher-v2-copy", "static", 1000, pairs[k], 100.0 * noise(k)))
    for k in range(16):
        lines.append(line("regexmatcher-v2", "static", 1000, pairs[k], 100.0 * noise(k)))
    run = write_run(tmp / "pairs", lines)
    keys = [("static", 10), ("static", 100), ("static", 1000)]
    s = ablations.summarize(load(run), {}, resamples=200, keys=keys)
    by_cell = {r["m"]: {(c["arm"], c["reference"]): c for c in r["comparisons"]} for r in s["cells"]}
    c = by_cell[10][("regexmatcher-v2-copy", "regexmatcher-v2")]
    expect(c["status"] == "not compared" and c["pairs"] == 0 and "ratio" not in c,
           "pairs: nine pairs each, two in common, are not compared")
    failing = s["cells"][0]["failing"]
    expect(all("9 processes" in failing.get(a, "") for a in ("regexmatcher-v2-copy", "regexmatcher-v2")),
           "pairs: both arms are failing in that cell, with the reason")
    c = by_cell[100][("regexmatcher-v2-copy", "regexmatcher-v2")]
    expect(c["status"] == "compared" and c["pairs"] == 16 and close(c["ratio"], 1.0),
           "pairs: sixteen full pairs are compared, over 16 pairs")
    c = by_cell[1000][("regexmatcher-v2-copy", "regexmatcher-v2")]
    expect(c["status"] == "not compared" and "distinct pairs" in s["cells"][2]["failing"]["regexmatcher-v2-copy"],
           "pairs: a pair twice and a pair missing is failing, not compared")
    # ratio_ci itself refuses what is not the design's sixteen, whatever the callers did
    rng = np.random.default_rng(1)

    def on(idx, scale=1.0):
        return {pairs[k]: 100.0 * noise(k) * scale for k in idx}

    r = review_common.ratio_ci(on(range(0, 9)), {"den": on(range(7, 16))}, rng, 200)
    expect(r["status"] != "compared" and r["pairs"] == 0 and "ratio" not in r,
           "pairs: ratio_ci refuses nine and nine pairs with two in common")
    r = review_common.ratio_ci(on(range(16)), {"den": on(range(15))}, rng, 200)
    expect(r["status"] != "compared" and "den" in r["why"], "pairs: ratio_ci refuses an arm one pair short")
    r = review_common.ratio_ci({**on(range(15)), (999, 998): 1.0}, {"den": on(range(16))}, rng, 200)
    expect(r["status"] != "compared", "pairs: ratio_ci refuses a pair that is not the design's")
    r = review_common.ratio_ci(on(range(16), 1.5), {"den": on(range(16))}, rng, 200)
    expect(r["status"] == "compared" and r["pairs"] == 16 and close(r["ratio"], 1.5), "pairs: ratio_ci over sixteen")
    # the boundary analysis: a competitor on nine pairs is failing, and its comparison is not made
    bl = [r for r in boundary_lines() if not (r["arm"] == "matchit" and r["shape"] == "param-last" and r["m"] == 10
                                              and (r["table_seed"], r["ring_seed"]) in design_pairs()[9:])]
    b = boundary.summarize(load(write_run(tmp / "pairs-bnd", bl)), resamples=200, keys=[("param-last", 10)])
    cell = b["cells"][0]
    sym = {c["against"]: c for c in cell["symmetric"]}
    expect("matchit" in cell["failing"] and sym["matchit"]["status"] == "not compared" and sym["matchit"]["pairs"] == 0,
           "pairs: boundary: a Rust arm on nine pairs is failing and not compared")
    expect(sym["actix-router"]["status"] == "compared" and sym["actix-router"]["pairs"] == 16,
           "pairs: boundary: the others are compared over sixteen")
    # a null that is on nine pairs only is failing, and the C++ competitors that go through it are left out of
    # the net comparison, the lowest raw median among them (uwebsockets) with them: no net ratio
    nl = [r for r in boundary_lines() if not (r["arm"] == "null-no405" and r["shape"] == "wild" and r["m"] == 10
                                              and (r["table_seed"], r["ring_seed"]) in design_pairs()[9:])]
    b = boundary.summarize(load(write_run(tmp / "pairs-null", nl)), resamples=200, keys=[("wild", 10)])
    cell = b["cells"][0]
    why = cell["net_left_out"]
    expect(sorted(why) == ["glaze", "uwebsockets"] and all("null" in w for w in why.values())
           and cell["net"]["status"] == "not compared" and "uwebsockets" in cell["net"]["why"],
           "net: C++ competitors whose null is not on all sixteen pairs are left out, no net ratio")


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        check_ablations(Path(t))
        check_boundary(Path(t))
        check_pairs(Path(t))
    print(f"{failures} failed" if failures else "all checks passed")
    return 1 if failures else 0


def test_all() -> None:  # pytest entry
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
