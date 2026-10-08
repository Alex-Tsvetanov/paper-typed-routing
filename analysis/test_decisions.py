#!/usr/bin/env python3
"""Tests of round 2's decision rules (hypotheses-round2.md), on synthetic cells.

    python analysis/test_decisions.py        (or: python -m pytest analysis/test_decisions.py)

1. The design: sixteen pairs that share no table seed and no ring seed, the same list as
   bench/run_grid.sh's default PAIRS, and rbench's table seeds (bench/main.cpp) holding them all.
2. cells.py: an unverified process fails its arm's cell; a check of every query restores it; v2
   must be verified itself; a competitor's pairs must equal v2's; v2's pairs must be the design's
   when it is given; refused, incomparable and over-budget arms are absent with their reason; the
   reference arms and the ablation arm are never competitors.
3. Holm keeps the whole family, an untested cell entering with p = 1; a cell passes only under
   both computations, and a disagreement is flagged and does not pass.
4. H1 on synthetic grids: a clear win passes in all 35 cells; two pairs above the margin in 12
   cells fail those cells by the sign test while the bootstrap passes them; an upper bound above
   the cap stops H1 even with 32 cells passing.
5. H2: strict net against net (equal holds, 0.1 more loses), the Go arms' own null pass, the C++
   null of the same pair and the same 405 rule (null for v2, null-no405 for a competitor the
   harness's 405 rule applies to); branch misses against the median competitor.
6. H3 and H4 per cell; H7 needs 13 of 16 pairs below 1.02 and the clustered upper bound at most 1.02.
7. H6: pairs with an invalid window are left out; fewer than 6 valid pairs cannot pass; (a) needs
   every lower bound above 1.00; (b) the carry-over against the T0 difference at (111, 211), with
   times per request in seconds and lookups in nanoseconds.
Pure NumPy and the standard library.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import h1_stats  # noqa: E402
import h2_stats  # noqa: E402
import h347_stats  # noqa: E402
import h6_stats  # noqa: E402
from cells import ABLATION, COMPETITORS, CT, REFERENCE, V1, V2, design_pairs, load, sort_cell  # noqa: E402
from holm import adjust, decide_both  # noqa: E402
from synth import cell_rows, cells_of, grid_rows, row, write_run  # noqa: E402

B = 2000  # resamples in these tests (the analysis uses 10,000)
PAIRS = design_pairs()


# 1 ---------------------------------------------------------------------------------------- design
def test_design_pairs():
    assert len(set(PAIRS)) == 16
    # sixteen table seeds and sixteen ring seeds, each in one pair only: pair k is (110 + k, 210 + k)
    assert sorted(p[0] for p in PAIRS) == list(range(111, 127))
    assert sorted(p[1] for p in PAIRS) == list(range(211, 227))
    assert PAIRS[0] == (111, 211)  # H6's pair, and the first of the reference arms' three
    main_cpp = (HERE.parent / "bench" / "main.cpp").read_text(encoding="utf-8")
    seeds = re.search(r'kTableSeeds = "([^"]*)"', main_cpp).group(1).split(",")
    assert seeds == ["1"] + [str(s) for s in range(111, 127)]
    script = (HERE.parent / "bench" / "run_grid.sh").read_text(encoding="utf-8")
    default = re.search(r"pairs=\$\{PAIRS:-([^}]*)\}", script).group(1).split()
    assert [tuple(int(x) for x in p.split(":")) for p in default] == PAIRS


# 2 ----------------------------------------------------------------------------------------- cells
def small(arm, ok=True, **kw):
    return [row(arm, "rest", 100000, p, 10.0, **kw) for p in PAIRS[:3]]


def test_unverified_arm_fails_the_cell():
    with tempfile.TemporaryDirectory() as t:
        rows = small(V2) + small("gin") + [row("actix-router", "rest", 100000, p, 10.0, verified_all=(p != PAIRS[1]))
                                             for p in PAIRS[:3]]
        srt = sort_cell(load(write_run(Path(t), rows))[("rest", 100000)], "rest")
        assert "actix-router" not in srt.included
        assert any("actix-router: 1 of 3 processes not verified on every query" in f for f in srt.failures)


def test_a_check_of_every_query_restores_the_arm():
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        write_run(d, small(V2) + small("gin") + small("actix-router", verified_all=False))
        good = [{"arm": "actix-router", "shape": "rest", "m": 100000, "table_seed": p[0], "ring_seed": p[1],
                 "digests_match": True, "agrees_all": True} for p in PAIRS[:3]]
        (d / "ok.jsonl").write_text("".join(json.dumps(c) + "\n" for c in good))
        srt = sort_cell(load(d, d / "ok.jsonl")[("rest", 100000)], "rest")
        assert "actix-router" in srt.included and not srt.failures
        bad = [dict(good[0], digests_match=False), dict(good[1], agrees_all=False), good[2]]
        (d / "bad.jsonl").write_text("".join(json.dumps(c) + "\n" for c in bad))
        srt = sort_cell(load(d, d / "bad.jsonl")[("rest", 100000)], "rest")
        assert any("2 of 3 processes not verified" in f for f in srt.failures)


def test_v2_itself_must_be_verified_and_on_the_design_pairs():
    cells = cells_of([row(V2, "rest", 10, p, 1.0, verified_all=(p != PAIRS[0])) for p in PAIRS]
                     + [row("gin", "rest", 10, p, 1.0) for p in PAIRS])
    srt = sort_cell(cells[("rest", 10)], "rest")
    assert srt.v2 is None and srt.failures
    cells = cells_of([row(V2, "rest", 10, p, 1.0) for p in PAIRS[:15]] + [row("gin", "rest", 10, p, 1.0) for p in PAIRS[:15]])
    assert not sort_cell(cells[("rest", 10)], "rest").failures
    srt = sort_cell(cells[("rest", 10)], "rest", expected_pairs=PAIRS)
    assert any("not the design's" in f for f in srt.failures)


def test_competitor_pairs_must_equal_v2s():
    cells = cells_of([row(V2, "rest", 10, p, 1.0) for p in PAIRS] + [row("gin", "rest", 10, p, 1.0) for p in PAIRS[1:]])
    srt = sort_cell(cells[("rest", 10)], "rest")
    assert "gin" not in srt.included and any("seed pairs differ" in f for f in srt.failures)


def test_absent_arms_and_roles():
    rows = [row(V2, "wild", 10, p, 1.0) for p in PAIRS]
    rows += [row("uwebsockets", "wild", 10, p, 1.0, status="disagrees", answers_differ=4096, id_mismatches=0,
                 id_mismatches_404=0, capture_mismatches=4096) for p in PAIRS]
    rows += [row("cpp-httplib", "wild", 10, p, 1.0, status="refused", reason="refused at insert") for p in PAIRS]
    rows += [row("actix-router", "wild", 10, PAIRS[0], 1.0, status="timeout")]
    rows += [row("actix-router", "wild", 10, p, 1.0, status="skipped") for p in PAIRS[1:]]
    for arm in sorted(REFERENCE) + [ABLATION, CT]:
        rows += [row(arm, "wild", 10, p, 0.1) for p in PAIRS]
    rows += [row("gin", "wild", 10, p, 2.0) for p in PAIRS]
    srt = sort_cell(cells_of(rows)[("wild", 10)], "wild")
    assert srt.absent["uwebsockets"].startswith("incomparable: 4,096 of 4,096")
    assert srt.absent["cpp-httplib"] == "refused: refused at insert"
    assert srt.absent["actix-router"] == "exceeds budget"
    assert set(srt.included) == {"gin"} and not srt.failures
    assert not (REFERENCE | {ABLATION, CT, V2, V1}) & COMPETITORS
    assert len(COMPETITORS) == 16


def test_declared_disagreement_must_be_of_its_kind():
    """semantics.json: uWebSockets on wild may differ in values only (kind "values"), gin on
    mixed-overlap may answer 404 only (kind "404"); any other wrong answer fails the cell."""
    def cell(arm, shape, **counts):
        rows = [row(V2, shape, 10, p, 1.0) for p in PAIRS]
        rows += [row(arm, shape, 10, p, 1.0, status="disagrees", answers_differ=100, **counts) for p in PAIRS]
        return sort_cell(cells_of(rows)[(shape, 10)], shape)
    srt = cell("uwebsockets", "wild", id_mismatches=0, id_mismatches_404=0, capture_mismatches=100)
    assert "uwebsockets" in srt.absent and not srt.failures
    srt = cell("uwebsockets", "wild", id_mismatches=1, id_mismatches_404=1, capture_mismatches=99)
    assert "uwebsockets" not in srt.absent and any("not of its declared kind" in f for f in srt.failures)
    srt = cell("gin", "mixed-overlap", id_mismatches=100, id_mismatches_404=100, capture_mismatches=0)
    assert "gin" in srt.absent and not srt.failures
    srt = cell("gin", "mixed-overlap", id_mismatches=100, id_mismatches_404=99, capture_mismatches=0)
    assert srt.failures and "gin" not in srt.absent
    srt = cell("gin", "mixed-overlap", id_mismatches=99, id_mismatches_404=99, capture_mismatches=1)
    assert srt.failures
    srt = cell("gin", "mixed-overlap")  # a row without the counts
    assert srt.failures
    srt = cell("gin", "wild", id_mismatches=100, id_mismatches_404=100, capture_mismatches=0)  # not declared
    assert srt.failures


# 3 ------------------------------------------------------------------------------------------ Holm
def test_holm_keeps_the_whole_family():
    rows = [{"status": "tested", "p": 0.0005} for _ in range(34)] + [{"status": "fails"}]
    passes = adjust(rows, "p", 0.025)
    assert passes[-1] is False and rows[-1]["p_holm"] == 1.0
    assert abs(rows[0]["p_holm"] - 35 * 0.0005) < 1e-12 and all(passes[:34])
    rows = [{"status": "tested", "p": 0.0007} for _ in range(35)]
    assert all(adjust(rows, "p", 0.025))
    rows += [{"status": "no competitor holds the table"}]
    assert not any(adjust(rows, "p", 0.025))


def test_a_cell_passes_only_under_both():
    rows = [{"status": "tested", "pb": 1e-5, "ps": 1e-5},
            {"status": "tested", "pb": 1e-5, "ps": 0.5},
            {"status": "tested", "pb": 0.5, "ps": 1e-5},
            {"status": "fails"}]
    decide_both(rows, 0.025, "pb", "ps", "passes")
    assert [r["passes"] for r in rows] == [True, False, False, False]
    assert [r["passes_disagree"] for r in rows] == [False, True, True, False]


# 4 -------------------------------------------------------------------------------------------- H1
def test_h1_clear_win_passes_everywhere():
    rows, s = h1_stats.decide(cells_of(grid_rows(0.8)), resamples=B, seed=1, expected_pairs=PAIRS)
    assert s["tested"] == 35 and s["passed"] == 35 and s["holds"], s
    assert all(r["fastest"] == "gin" for r in rows)
    assert all(r["sign_x"] == 16 for r in rows)


def test_h1_sign_test_fails_what_the_bootstrap_passes():
    rng = np.random.default_rng(4)
    rows = []
    for i, (s, m) in enumerate((s, m) for s in h1_stats.H1_SHAPES for m in h1_stats.H1_SIZES):
        rs = [0.8] * 16 if i >= 12 else [0.8] * 14 + [1.05, 1.05]
        rows += cell_rows(s, m, rs, rng=rng)
    out, s = h1_stats.decide(cells_of(rows), resamples=B, seed=2, expected_pairs=PAIRS)
    lost = [r for r in out if not r["passes"]]
    assert len(lost) == 12 and all(r["passes_boot"] and not r["passes_sign"] and r["passes_disagree"] for r in lost)
    assert s["passed"] == 23 and not s["holds"]


def test_h1_cap_stops_it():
    rng = np.random.default_rng(5)
    rows = []
    for i, (s, m) in enumerate((s, m) for s in h1_stats.H1_SHAPES for m in h1_stats.H1_SIZES):
        rs = list(0.8 * (1 + 0.01 * rng.standard_normal(16))) if i >= 2 else list(1.2 + 0.05 * rng.standard_normal(16))
        rows += cell_rows(s, m, rs, rng=rng)
    out, s = h1_stats.decide(cells_of(rows), resamples=B, seed=3, expected_pairs=PAIRS)
    assert s["passed"] == 33 and s["over_cap"] == 2 and not s["holds"]


def test_h1_untested_cell_counts():
    rows = grid_rows(0.8)
    rows = [r for r in rows if not (r["shape"] == "rest" and r["m"] == 10 and r["arm"] != V2)]
    out, s = h1_stats.decide(cells_of(rows), resamples=B, seed=1, expected_pairs=PAIRS)
    r = next(x for x in out if x["shape"] == "rest" and x["m"] == 10)
    assert r["status"] == "no competitor holds the table" and not r["passes"]
    assert s["passed"] == 34 and s["holds"]


# 5 -------------------------------------------------------------------------------------------- H2
def h2_cell(v2_insn, rival_insn, rival="crow", v2_bm=0.5, rival_bm=0.5, own_null=None, no405=True):
    """v2 (loop null "null", 27 per lookup) against one rival: a C++ or Rust competitor (loop null
    "null-no405", 29 per lookup: the harness's 405 test) or, with own_null, a Go arm."""
    rows = []
    for p in PAIRS:
        rows.append(row("null", "rest", 10, p, 3.0, instructions=27.0))
        if no405:
            rows.append(row("null-no405", "rest", 10, p, 3.2, instructions=29.0))
        rows.append(row(V2, "rest", 10, p, 40.0, instructions=v2_insn + 27.0, branch_misses=v2_bm))
        kw = {"instructions": rival_insn + (own_null if own_null is not None else 29.0), "branch_misses": rival_bm}
        if own_null is not None:
            kw["null_instructions"] = own_null
        rows.append(row(rival, "rest", 10, p, 50.0, **kw))
    return cells_of(rows)


def test_h2_strict_net_against_net():
    out, _ = h2_stats.decide(h2_cell(500.0, 500.0), keys=[("rest", 10)])
    assert out[0]["instructions_hold"] is True
    out, _ = h2_stats.decide(h2_cell(500.1, 500.0), keys=[("rest", 10)])
    assert out[0]["instructions_hold"] is False
    # a Go arm: its own null pass (40 per lookup), not the C++ null (27)
    out, _ = h2_stats.decide(h2_cell(480.0, 500.0, rival="gin", own_null=40.0), keys=[("rest", 10)])
    assert out[0]["fastest_instructions_net"] == 500.0 and out[0]["instructions_hold"] is True
    out, _ = h2_stats.decide(h2_cell(480.0, 500.0, v2_bm=0.6, rival_bm=0.5), keys=[("rest", 10)])
    assert out[0]["branch_misses_hold"] is False


def test_h2_harness_405_test_netted_out():
    # crow's loop null is null-no405 (29), v2's is null (27): equal nets hold, and crow's net is
    # 500, not the 502 that the null arm would give
    out, _ = h2_stats.decide(h2_cell(500.0, 500.0), keys=[("rest", 10)])
    assert out[0]["fastest_loop_null"] == "null-no405" and out[0]["fastest_instructions_net"] == 500.0
    assert out[0]["v2_instructions_net"] == 500.0 and out[0]["instructions_hold"] is True
    # without the null-no405 arm in the cell, crow's net cannot be computed and the cell fails
    out, s = h2_stats.decide(h2_cell(480.0, 500.0, no405=False), keys=[("rest", 10)])
    assert out[0]["status"] == "fails" and "null count is missing for crow" in out[0]["failures"]
    assert not s["holds"]


# 6 ------------------------------------------------------------------------------------ H3, H4, H7
def test_h3():
    rows = grid_rows(0.8)
    out, s = h347_stats.h3(cells_of(rows))
    assert s["holds"]
    rows[next(i for i, r in enumerate(rows) if r["arm"] == V2)]["allocs_per_lookup"] = 0.001
    out, s = h347_stats.h3(cells_of(rows))
    assert not s["holds"] and len(out) == 1


def test_h4_per_cell():
    rows = []
    for p in PAIRS:
        rows.append(row(V2, "static", 100000, p, 1.0, build_s_median=0.5, table_bytes=3000))
        rows.append(row("gin", "static", 100000, p, 1.0, build_s_median=0.4, table_bytes=1000))
        rows.append(row("crow", "static", 100000, p, 1.0, build_s_median=0.6, table_bytes=2000))
        rows.append(row("glaze", "static", 100000, p, 1.0, build_s_median=0.7, table_bytes=4000))
    out, s = h347_stats.h4(cells_of(rows), keys=[("static", 100000)], expected_pairs=PAIRS)
    r = out[0]
    assert r["median_competitor_build_s"] == 0.6 and r["build_holds"] and r["below_1s"]
    assert r["smallest_competitor"] == "gin" and not r["heap_holds"] and not s["holds"]


def test_h7_needs_13_of_16():
    def run(ct):
        rows = cell_rows("rest", 100, [0.8] * 16, ct_ratio=ct)
        return h347_stats.h7(cells_of(rows), resamples=B, seed=1, keys=[("rest", 100)], expected_pairs=PAIRS)
    out, s = run([1.0] * 13 + [1.03] * 3)
    assert out[0]["sign_x"] == 13 and out[0]["holds"], out[0]
    out, s = run([1.0] * 12 + [1.03] * 4)
    assert out[0]["sign_x"] == 12 and not out[0]["holds"] and out[0]["ci_high"] <= 1.02
    out, s = run([1.03] * 16)
    assert not out[0]["holds"] and out[0]["ci_high"] > 1.02


# 7 -------------------------------------------------------------------------------------------- H6
def windows(pairs: int, rps: dict[str, float], invalid_round: int | None = None) -> list[dict]:
    out = []
    order = ["h6-v1", "h6-v2", "h6-null", "h6-null", "h6-v2", "h6-v1"]
    for rnd in range(1, pairs + 1):
        for pos, arm in enumerate(order):
            ok = not (invalid_round == rnd and pos == 2)
            out.append({"round": rnd, "position": pos, "arm": arm, "tag": f"c-r{rnd}-p{pos}-{arm}",
                        "rps": rps[arm] * (1 + 0.0002 * ((rnd * 7 + pos) % 5)), "valid": ok,
                        "invalid_reasons": [] if ok else ["probe failed"]})
    return out


def t0_cells(t_v1_ns: float, t_v2_ns: float) -> dict:
    rows = []
    for cell in h6_stats.CELLS:
        shape, m = cell.rsplit("-", 1)
        rows.append(row(V1, shape, int(m), (111, 211), t_v1_ns))
        rows.append(row(V2, shape, int(m), (111, 211), t_v2_ns))
        rows.append(row(V1, shape, int(m), (112, 212), 9e9))  # another pair: never used
    return cells_of(rows)


def test_h6_units_and_decisions():
    # T0: v1 1,000 ns, v2 50 ns per lookup: D_T0 = 950 ns. T1: null 10 us per request, v1 11 us,
    # v2 10.05 us, so D_meas = 0.95 us = 950 ns: carry-over 1, ratio 11 / 10.05.
    rps = {"h6-null": 1e5, "h6-v1": 1 / 11e-6, "h6-v2": 1 / 10.05e-6}
    t1 = {c: windows(6, rps) for c in h6_stats.CELLS}
    out, s = h6_stats.decide(t1, t0_cells(1000.0, 50.0), resamples=B, seed=1)
    for r in out:
        assert r["status"] == "tested" and r["pairs"] == 6
        assert abs(r["d_t0_ns"] - 950.0) < 1e-9
        assert 0.9 < r["carry"] < 1.1 and r["ratio"] > 1.09
        assert r["a_holds"] and r["b_holds"]
        assert abs(r["null_us_per_request"] - 10.0) < 0.05
        assert abs(r["predicted_ratio"] - (10e-6 + 1000e-9) / (10e-6 + 50e-9)) < 1e-3
    assert s["a_holds"] and s["b_holds"]


def test_h6_left_out_and_too_few():
    rps = {"h6-null": 1e5, "h6-v1": 1 / 11e-6, "h6-v2": 1 / 10.05e-6}
    t1 = {c: windows(7, rps, invalid_round=3) for c in h6_stats.CELLS}
    out, s = h6_stats.decide(t1, t0_cells(1000.0, 50.0), resamples=B, seed=1)
    assert all(r["pairs"] == 6 and "round 3" in r["left_out"] for r in out) and s["a_holds"]
    t1["rest-10000"] = windows(6, rps, invalid_round=3)
    out, s = h6_stats.decide(t1, t0_cells(1000.0, 50.0), resamples=B, seed=1)
    r = next(x for x in out if x["cell"] == "rest-10000")
    assert r["status"] == "too few pairs" and not r["a_holds"] and not s["a_holds"] and not s["b_holds"]


def test_h6_small_carry_over_fails_b():
    # D_meas is a tenth of D_T0: (a) holds, (b) does not.
    rps = {"h6-null": 1e5, "h6-v1": 1 / 10.145e-6, "h6-v2": 1 / 10.05e-6}
    t1 = {c: windows(6, rps) for c in h6_stats.CELLS}
    out, s = h6_stats.decide(t1, t0_cells(1000.0, 50.0), resamples=B, seed=1)
    assert s["a_holds"] and not s["b_holds"]
    assert all(0.05 < r["carry"] < 0.15 for r in out)


def test_h6_t0_process_must_be_usable():
    rps = {"h6-null": 1e5, "h6-v1": 1 / 11e-6, "h6-v2": 1 / 10.05e-6}
    t1 = {c: windows(6, rps) for c in h6_stats.CELLS}
    t0 = t0_cells(1000.0, 50.0)
    t0[("rest", 10)][V2][0]["agrees"] = False  # v2's process at (111, 211) in rest m = 10
    out, s = h6_stats.decide(t1, t0, resamples=B, seed=1)
    r = next(x for x in out if x["cell"] == "rest-10")
    assert r["status"] == "no T0 lookup time at pair (111, 211)" and not r["a_holds"] and not s["b_holds"]


def test_h5b_is_decided_by_v2():
    import h5_stats
    cases = ("static-then-param", "param-then-static", "pchar", "trailing-slash", "method")
    v2_ok = [{"arm": V2, "case": c, "status": "pass"} for c in cases]
    v1_passes = [{"arm": V1, "case": c, "status": "pass"} for c in cases]
    _, s = h5_stats.decide(v2_ok + v1_passes)
    assert s["holds"] and not s["v1_fails_first_two"]
    _, s = h5_stats.decide([dict(v2_ok[0], status="fail")] + v2_ok[1:] + v1_passes)
    assert not s["holds"]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok: {t.__name__}")
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
