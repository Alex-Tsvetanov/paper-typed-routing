#!/usr/bin/env python3
"""Tests of t3/rr_results.py on synthetic records: every count below is made up for the test and is no result.

    python t3/test_rr_results.py          (or: python -m pytest t3/test_rr_results.py)
"""
from __future__ import annotations

import contextlib
import io
import json
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import p2run  # noqa: E402
import rr_results as R  # noqa: E402

WALL_NS = 1_500_000_000


def plan_dict(arms_cpp=("v2", "crow", "null"), arms_go=("v2", "gin", "null"), rounds=3) -> dict:
    return {"_comment": "test", "p2gen": "p2gen", "data_root": "sets", "shapes": ["mixed-disjoint"], "sizes": [1000, 100000],
            "pairs": [[111, 211]], "cpus": {"server": 14, "generator": "2-13"}, "schedule": "round-robin",
            "rounds": rounds, "order_seed": 5, "others_max_pct": 10, "rerun_host_faults": True,
            "programs": [{"name": "mserver", "path": "mserver", "arms": list(arms_cpp)},
                         {"name": "mserver-go", "path": "mserver-go", "arms": list(arms_go)}]}


def completed(program: str, arm: str, entry: int, m: int, round_no: int, rerun: bool = False) -> int:
    """A made-up count of answers: distinct per contestant, size and round, so the tests can tell them apart."""
    base = {"v2": 300_000, "crow": 240_000, "gin": 200_000, "null": 330_000}[arm] + 1_000 * entry
    return base - (m // 1000) * 10 + 100 * round_no + (7 if rerun else 0) + (50_000 if program == "mserver" else 0)


def window_row(w, status="valid", rerun=False) -> dict:
    row = {"type": "window", "seq": w.seq, "cell": w.cell, "shape": w.shape, "m": w.m, "program": w.program,
           "arm": w.arm, "entry": w.entry, "round": w.round_no, "position": w.index, "status": status,
           "generator": {"measure": {"completed": completed(w.program, w.arm, w.entry, w.m, w.round_no, rerun)},
                         "measure_wall_ns": WALL_NS},
           "others": {"sum_pct_of_one_cpu": 0.5, "idle_servers": {"max_pct_of_one_cpu": 0.125}}}
    if rerun:
        row["rerun"] = True
    return row


def record(plan: dict, *, status=None, reruns=(), not_counting=(), system="linux", mode="timed", exit_code=0,
           drop_seq=None) -> list[dict]:
    """A record of the plan: status maps seq to a verdict; reruns lists (cell, round) rerun in their cell;
    not_counting lists (cell, program, entry) whose cell_end says its windows do not count."""
    p = p2run.parse_plan(plan)
    rows = [{"type": "session", "system": system, "mode": mode, "windows": p2run.total_windows(p),
             "plan": R.public(plan), "host": "test"}]
    ws = list(p2run.windows(p))
    rerun_seq = len(ws)
    for cell in p2run.cells(p):
        name = p2run.cell_name(cell)
        rows += [window_row(w, (status or {}).get(w.seq, "valid")) for w in ws if w.cell == name and w.seq != drop_seq]
        orders = p2run.round_orders(p, *cell[:3])
        rounds = []
        for cell_name, round_no in reruns:
            if cell_name == name:
                rounds.append({"round": round_no, "seqs": [], "codes": ["others"], "arm_faults": [], "first_seq": rerun_seq,
                               "windows": len(orders[round_no - 1])})
                rerun_seq += len(orders[round_no - 1])
        rows.append({"type": "rerun", "cell": name, "rounds": rounds, "windows": sum(r["windows"] for r in rounds)})
        for r in rounds:
            rows += [window_row(w, rerun=True)
                     for w in p2run.rr_round(r["first_seq"], cell, r["round"], orders[r["round"] - 1], rerun=True)]
        servers = [{"program": c.program, "arm": c.arm, "entry": c.entry,
                    "windows_count": (name, c.program, c.entry) not in not_counting,
                    "reason_codes": ["server_exit"] if (name, c.program, c.entry) in not_counting else [],
                    "memory": {"peak_resident_kib": 1000 + c.entry}} for c in p2run.contestants(p)]
        rows.append({"type": "cell_end", "cell": name, "shape": cell[0], "m": cell[1], "table_seed": cell[2], "servers": servers})
    rows.append({"type": "end", "exit": exit_code})
    return rows


def x_of(program, arm, entry, m, round_no, rerun=False) -> float:
    return completed(program, arm, entry, m, round_no, rerun) / (WALL_NS / 1e9)


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.plans = self.dir / "plans"
        self.plans.mkdir()
        self.rr, self.aa = plan_dict(), plan_dict(("v2", "v2"), ("v2", "v2"))
        self.aak = plan_dict(("v2",) * 4, ("v2",) * 4)
        for name, plan in (("rr-L.json", self.rr), ("rr-aa-L.json", self.aa), ("rr-W.json", self.rr), ("rr-aa-W.json", self.aa),
                           ("rr-aak-L.json", self.aak), ("rr-aak-W.json", self.aak)):
            (self.plans / name).write_text(json.dumps(plan))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, name: str, rows: list[dict]) -> Path:
        path = self.dir / name
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return path

    def run_main(self, *paths: Path) -> tuple[int, dict, str]:
        out, md, err = self.dir / "out.json", self.dir / "out.md", io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = R.main([*map(str, paths), "--out", str(out), "--md", str(md)], plans=self.plans)
        return rc, (json.loads(out.read_text()) if rc == 0 else {}), err.getvalue()

    def cell(self, result, kind="rr", cell="mixed-disjoint/m1000/t111", system="linux"):
        return result["systems"][system][kind]["cells"][cell]

    def contestant(self, cell, program, arm):
        return next(s for s in cell["programs"][program]["contestants"] if s["arm"] == arm)


class StatisticsTests(Fixture):
    def test_median_and_sample_spread_per_contestant(self) -> None:
        rc, res, err = self.run_main(self.write("rr.jsonl", record(self.rr)))
        self.assertEqual(rc, 0, err)
        s = self.contestant(self.cell(res), "mserver", "crow")
        xs = [x_of("mserver", "crow", 1, 1000, k) for k in (1, 2, 3)]
        self.assertEqual(s["rounds"], [1, 2, 3])
        self.assertAlmostEqual(s["req_s"]["median"], statistics.median(xs))
        self.assertAlmostEqual(s["req_s"]["sd"], statistics.stdev(xs))
        self.assertAlmostEqual(s["ns_per_request"]["median"], statistics.median([1e9 / x for x in xs]))
        self.assertEqual((s["req_s"]["n"], s["peak_resident_kib"], s["windows_count"]), (3, 1001, True))
        self.assertEqual(self.cell(res)["idle_server_max_pct_of_one_cpu"], 0.125)

    def test_a_rerun_replaces_its_round_for_every_contestant(self) -> None:
        cell = "mixed-disjoint/m1000/t111"
        rc, res, err = self.run_main(self.write("rr.jsonl", record(self.rr, reruns=[(cell, 2)])))
        self.assertEqual(rc, 0, err)
        for program, arm, entry in (("mserver", "crow", 1), ("mserver-go", "v2", 0)):
            s = self.contestant(self.cell(res), program, arm)
            xs = sorted([x_of(program, arm, entry, 1000, 1), x_of(program, arm, entry, 1000, 2, rerun=True),
                         x_of(program, arm, entry, 1000, 3)])
            self.assertAlmostEqual(s["req_s"]["median"], xs[1])
            self.assertAlmostEqual(s["req_s"]["min"], xs[0])

    def test_an_invalid_window_is_dropped_for_its_own_contestant_only(self) -> None:
        p = p2run.parse_plan(self.rr)
        w = next(w for w in p2run.windows(p) if w.m == 1000 and w.round_no == 2 and w.arm == "crow")
        rc, res, err = self.run_main(self.write("rr.jsonl", record(self.rr, status={w.seq: "invalid"})))
        self.assertEqual(rc, 0, err)
        cell = self.cell(res)
        self.assertEqual(self.contestant(cell, "mserver", "crow")["rounds"], [1, 3])
        self.assertEqual(self.contestant(cell, "mserver", "v2")["rounds"], [1, 2, 3])

    def test_an_overloaded_contestant_is_reported_over_both_kinds_and_not_ranked(self) -> None:
        p = p2run.parse_plan(self.rr)
        w = next(w for w in p2run.windows(p) if w.m == 1000 and w.round_no == 1 and w.arm == "gin")
        rc, res, err = self.run_main(self.write("rr.jsonl", record(self.rr, status={w.seq: "overloaded"})))
        self.assertEqual(rc, 0, err)
        go = self.cell(res)["programs"]["mserver-go"]
        gin = self.contestant(self.cell(res), "mserver-go", "gin")
        self.assertEqual((gin["overloaded"], gin["rounds"]), (True, [1, 2, 3]))
        self.assertEqual((go["ranking"], go["not_ranked"]), (["v2"], ["gin"]))

    def test_a_server_whose_windows_do_not_count(self) -> None:
        rc, res, err = self.run_main(self.write("rr.jsonl", record(
            self.rr, not_counting=[("mixed-disjoint/m1000/t111", "mserver", 1)])))
        self.assertEqual(rc, 0, err)
        crow = self.contestant(self.cell(res), "mserver", "crow")
        self.assertEqual((crow["req_s"], crow["windows_count"], crow["reason_codes"]), ({"n": 0}, False, ["server_exit"]))
        self.assertEqual(self.cell(res)["programs"]["mserver"]["not_ranked"], ["crow"])
        self.assertEqual(self.cell(res)["programs"]["mserver"]["v2_above_competitor_in_rounds"]["crow"],
                         {"v2_above": 0, "rounds_both_count": 0})

    def test_ranking_routing_cost_and_rounds_ahead(self) -> None:
        rc, res, err = self.run_main(self.write("rr.jsonl", record(self.rr)))
        self.assertEqual(rc, 0, err)
        cpp = self.cell(res)["programs"]["mserver"]
        self.assertEqual(cpp["ranking"], ["v2", "crow"])  # null is the reference, never ranked
        cost = [1e9 / x_of("mserver", "crow", 1, 1000, k) - 1e9 / x_of("mserver", "null", 2, 1000, k) for k in (1, 2, 3)]
        self.assertAlmostEqual(cpp["routing_cost_ns_per_request"]["crow"]["median"], statistics.median(cost))
        self.assertAlmostEqual(cpp["routing_cost_ns_per_request"]["crow"]["sd"], statistics.stdev(cost))
        self.assertEqual(cpp["v2_above_competitor_in_rounds"], {"crow": {"v2_above": 3, "rounds_both_count": 3}})

    def test_the_aa_run_gives_each_entry_and_their_round_differences(self) -> None:
        rc, res, err = self.run_main(self.write("aa.jsonl", record(self.aa)))
        self.assertEqual(rc, 0, err)
        go = self.cell(res, "aa", "mixed-disjoint/m100000/t111")["programs"]["mserver-go"]
        self.assertEqual([e["req_s"]["n"] for e in go["entries"]], [3, 3])
        r = [x_of("mserver-go", "v2", 0, 100000, k) / x_of("mserver-go", "v2", 1, 100000, k) for k in (1, 2, 3)]
        d = [1e9 / x_of("mserver-go", "v2", 0, 100000, k) - 1e9 / x_of("mserver-go", "v2", 1, 100000, k) for k in (1, 2, 3)]
        self.assertAlmostEqual(go["r"]["median"], statistics.median(r))
        self.assertAlmostEqual(go["d_ns"]["sd"], statistics.stdev(d))

    def test_the_k_server_aa_run_gives_the_spread_between_processes(self) -> None:
        rc, res, err = self.run_main(self.write("aak.jsonl", record(self.aak)))
        self.assertEqual(rc, 0, err)
        go = self.cell(res, "aak", "mixed-disjoint/m1000/t111")["programs"]["mserver-go"]
        t = {e: [1e9 / x_of("mserver-go", "v2", e, 1000, k) for k in (1, 2, 3)] for e in range(4)}
        medians = [statistics.median(t[e]) for e in range(4)]
        self.assertEqual([e["req_s"]["n"] for e in go["entries"]], [3, 3, 3, 3])
        self.assertAlmostEqual(go["medians_ns"]["range"], max(medians) - min(medians))
        self.assertAlmostEqual(go["medians_ns"]["sd"], statistics.stdev(medians))
        pooled = (sum(2 * statistics.variance(t[e]) for e in range(4)) / 8) ** 0.5
        self.assertAlmostEqual(go["within_process_sd_ns"], pooled)
        self.assertEqual(go["entry0_rank"], 4)  # the made-up counts rise with the entry: entry 0 is the slowest
        self.assertEqual(sorted(go["pairs_d_ns"]), ["0-1", "0-2", "0-3", "1-2", "1-3", "2-3"])
        self.assertAlmostEqual(go["pairs_d_ns"]["1-3"]["median"], statistics.median(
            [a - b for a, b in zip(t[1], t[3])]))
        self.assertNotIn("floor", res["systems"]["linux"])
        md = (self.dir / "out.md").read_text()
        self.assertIn("k-server A/A run", md)
        self.assertIn("entry 0 ranks 4.", md)

    def test_the_floor_is_the_aa_runs_largest_gap_against_the_rankings_neighbours(self) -> None:
        rc, res, err = self.run_main(self.write("rr.jsonl", record(self.rr)), self.write("aa.jsonl", record(self.aa)))
        self.assertEqual(rc, 0, err)
        f = res["systems"]["linux"]["floor"]["mixed-disjoint/m100000/t111"]["mserver-go"]
        d = [1e9 / x_of("mserver-go", "v2", 0, 100000, k) - 1e9 / x_of("mserver-go", "v2", 1, 100000, k) for k in (1, 2, 3)]
        self.assertAlmostEqual(f["aa_largest_abs_d_ns"], max(abs(v) for v in d))
        gin = statistics.median([1e9 / x_of("mserver-go", "gin", 1, 100000, k) for k in (1, 2, 3)])
        v2 = statistics.median([1e9 / x_of("mserver-go", "v2", 0, 100000, k) for k in (1, 2, 3)])
        self.assertEqual([(n["ahead"], n["behind"], n["clears"]) for n in f["neighbours"]], [("v2", "gin", True)])
        self.assertAlmostEqual(f["neighbours"][0]["gap_ns"], gin - v2)
        self.assertIn("| mixed-disjoint/m100000/t111 | mserver-go | v2 | gin |", (self.dir / "out.md").read_text())

    def test_a_gap_at_or_below_the_floor_does_not_clear_it(self) -> None:
        aa = {"cells": {"c": {"programs": {"p": {"d_ns": {"n": 3, "min": -50.0, "max": 20.0}}}}}}
        rr = {"cells": {"c": {"programs": {"p": {"ranking": ["v2", "x", "y"], "contestants": [
            {"arm": "v2", "ns_per_request": {"median": 1000.0}}, {"arm": "x", "ns_per_request": {"median": 1050.0}},
            {"arm": "y", "ns_per_request": {"median": 1100.5}}]}}}}}
        f = R.floor(aa, rr)["c"]["p"]
        self.assertEqual(f["aa_largest_abs_d_ns"], 50.0)
        self.assertEqual([n["clears"] for n in f["neighbours"]], [False, True])
        none = R.floor({"cells": {}}, rr)["c"]["p"]
        self.assertEqual((none["aa_largest_abs_d_ns"], [n["clears"] for n in none["neighbours"]]), (None, [False, False]))

    def test_both_kinds_and_both_systems_in_one_result_and_its_table(self) -> None:
        paths = [self.write("rr-l.jsonl", record(self.rr)), self.write("aa-l.jsonl", record(self.aa)),
                 self.write("rr-w.jsonl", record(self.rr, system="windows"))]
        rc, res, err = self.run_main(*paths)
        self.assertEqual(rc, 0, err)
        self.assertEqual({s: sorted(k) for s, k in res["systems"].items()}, {"linux": ["aa", "floor", "rr"], "windows": ["rr"]})
        md = (self.dir / "out.md").read_text()
        self.assertIn("| mserver | crow | 3 |", md)
        self.assertIn("rank 1", md)
        self.assertIn("entry 1", md)
        for ch in (chr(0x2013), chr(0x2014)):
            self.assertNotIn(ch, md)


class RefusalTests(Fixture):
    def refused(self, rows, *more) -> str:
        rc, _, err = self.run_main(self.write("bad.jsonl", rows), *more)
        self.assertEqual(rc, 2, err)
        return err

    def test_refusals(self) -> None:
        self.assertIn("timed run", self.refused(record(self.rr, mode="count")))
        self.assertIn("exit 0", self.refused(record(self.rr, exit_code=3)))
        self.assertIn("exit 0", self.refused(record(self.rr)[:-1]))
        self.assertIn("not the committed rr-L.json", self.refused(record({**self.rr, "window_s": 2.0})))
        self.assertIn("or a window twice", self.refused(record(self.rr, drop_seq=4)))
        self.assertIn("second rr record", self.refused(record(self.rr), self.write("again.jsonl", record(self.rr))))
        self.assertIn("second aak record", self.refused(record(self.aak), self.write("again.jsonl", record(self.aak))))
        self.assertIn("not the committed rr-aak-W.json",
                      self.refused(record({**self.aak, "rounds": 4}, system="windows")))
        self.assertIn("no session line", self.refused(record(self.rr)[1:]))

    def test_the_committed_plans_are_round_robin_and_the_files_have_no_dashes(self) -> None:
        for name in R.NAMES.values():
            plan = json.loads((HERE / "plans" / name).read_text(encoding="utf-8"))
            p = p2run.parse_plan(plan)
            self.assertTrue(p.round_robin, name)
            self.assertEqual((p.rounds, p.window_s, p.warmup_s, p.sizes, p.shapes),
                             (7, 1.5, 0.1, (1000, 100000), ("mixed-disjoint",)), name)
            self.assertEqual(R.kind_of(plan), "aak" if "-aak-" in name else "aa" if "-aa-" in name else "rr")
        self.assertEqual(R.kind_of(plan_dict(("v2",) * 3, ("v2", "v2"))), "rr")  # every list longer than two, or none
        for name in ("rr_results.py", "test_rr_results.py", "jobs/rr.py", "jobs/aa.py",
                     *(f"plans/{n}" for n in R.NAMES.values())):
            text = (HERE / name).read_text(encoding="utf-8")
            self.assertNotIn(chr(0x2013), text, name)
            self.assertNotIn(chr(0x2014), text, name)


if __name__ == "__main__":
    unittest.main(verbosity=1)
