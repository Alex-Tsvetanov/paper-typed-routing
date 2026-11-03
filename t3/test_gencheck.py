#!/usr/bin/env python3
"""Tests of the check of p2gen against t1gen: t3/jobs/gencheck.py's mapping of t1gen's result and its
runner, t3/gencheck_analysis.py on synthetic rows, and the plan. Untimed: the generator here is a
stand-in that prints its markers and writes a made-up result; no server runs.

    python t3/test_gencheck.py          (or: python -m pytest t3/test_gencheck.py)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "jobs"))
sys.path.insert(0, str(HERE))
import gencheck  # noqa: E402
import gencheck_analysis as G  # noqa: E402
import p2run  # noqa: E402
from p2run import Reading  # noqa: E402

# t1gen's result line (lab/t1/gen/t1gen.c, print_counters and the fields before it), with made-up counts
T1_LINE = {"tool": "t1gen", "commit": "c0ffee", "mode": "closed", "threads": 12, "connections": 64, "depth": 1,
           "measure_wall_s": 5.000123456,
           "measure": {"completed": 1000, "non_2xx": 1, "timeouts": 2, "eof_inflight": 3, "socket_errors": 4,
                       "protocol_errors": 5, "connect_errors": 6, "dropped": 0, "sock_events": 0, "proto_events": 0,
                       "errors_total": 15, "reconnects": 9, "bytes_read": 0, "offered": 0},
           "thread_failed": 0}

FAKE_T1GEN = textwrap.dedent("""\
    import sys
    out = sys.argv[sys.argv.index("--out") + 1]
    print("MEASURE_START 1", flush=True)
    print("MEASURE_END 2", flush=True)
    open(out, "w").write(%r)
""")


class FakeSampler:
    def begin(self) -> None:
        pass

    def end(self) -> Reading:
        return Reading(5.0, {0: 1.0}, 3000.0)


class MappingTests(unittest.TestCase):
    def test_t1gen_result_carries_every_key_the_verdict_reads(self) -> None:
        g = gencheck.t1_as_p2gen(T1_LINE)
        self.assertEqual(p2run.missing_keys(g, counting=False), [])
        m = g["measure"]
        self.assertEqual((m["completed"], m["errors_total"], m["timeouts"], m["connect_errors"], m["reconnects"]),
                         (1000, 15, 2, 6, 9))
        self.assertEqual((m["errors"]["lost"], m["errors"]["status"], m["errors"]["framing"], m["peer_closes"]), (7, 1, 5, 3))
        self.assertEqual((g["measure_wall_ns"], g["connections"], g["thread_failed"]), (5_000_123_456, 64, 0))


class RunnerTests(unittest.TestCase):
    def runner(self, t1gen: list[str]) -> gencheck.GenCheckRunner:
        plan = p2run.parse_plan({"p2gen": [sys.executable, "p2gen.py"], "data_root": "sets", "shapes": ["static"],
                                 "sizes": [10], "pairs": [[111, 211]],
                                 "cpus": {"server": os.cpu_count() - 1, "generator": "0"},
                                 "programs": [{"name": "mserver", "path": "mserver", "arms": ["null", "null"]}]})
        gencheck.GenCheckRunner.t1gen = t1gen
        return gencheck.GenCheckRunner(plan, Path("w"), None, FakeSampler(), 3000.0)

    def test_entry_1_starts_t1gen_with_p2gens_flags(self) -> None:
        r = self.runner(["/lab/t1gen"])
        r._t1 = False
        p2 = r._generator_cmd(1234, Path("cell"), Path("res.json"))
        r._t1 = True
        t1 = r._generator_cmd(1234, Path("cell"), Path("res.json"))
        self.assertEqual(p2[:2], [sys.executable, "p2gen.py"])
        self.assertEqual(t1, ["/lab/t1gen", *p2[2:]])
        self.assertIn("--warmup", t1)

    def test_a_duration_reaches_t1gen_as_p2run_passes_it(self) -> None:
        # p2run's _run_generator passes duration_s since the round-robin schedule; the override must take it.
        r = self.runner(["/lab/t1gen"])
        r._t1 = True
        cmd = r._generator_cmd(1234, Path("cell"), Path("res.json"), 2.5)
        self.assertEqual(cmd[0], "/lab/t1gen")
        self.assertEqual(cmd[cmd.index("--duration") + 1], "2.5")

    def run_window(self, line) -> dict:
        if os.cpu_count() < 2:
            self.skipTest("needs two CPUs")
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "t1gen.py"
            fake.write_text(FAKE_T1GEN % json.dumps(line), encoding="utf-8")
            r = self.runner([sys.executable, str(fake)])
            r.workdir = Path(tmp)
            row: dict = {}
            window = [w for w in p2run.windows(r.plan) if w.entry == 1][0]
            r._run_generator(window, row, 1, Path(tmp))
        return row

    def test_a_t1gen_window_keeps_its_own_result_and_is_judged_by_the_mapped_one(self) -> None:
        row = self.run_window(T1_LINE)
        self.assertEqual(row["generator_tool"], "t1gen")
        self.assertEqual(row["t1gen"], T1_LINE)
        self.assertEqual(row["generator"], gencheck.t1_as_p2gen(T1_LINE))

    def test_a_window_that_fails_before_its_generator_still_names_it(self) -> None:
        r = self.runner(["/lab/t1gen"])
        failing = lambda w, row: (_ for _ in ()).throw(RuntimeError("no server"))  # noqa: E731
        r._window = failing
        rows = [r.run_window(w) for w in p2run.windows(r.plan)]
        self.assertEqual([(row["entry"], row["generator_tool"], row["status"]) for row in rows],
                         [(0, "p2gen", "invalid"), (1, "t1gen", "invalid"), (1, "t1gen", "invalid"), (0, "p2gen", "invalid")])

    def test_a_t1gen_line_the_mapping_does_not_know_leaves_no_result(self) -> None:
        row = self.run_window({"tool": "t1gen"})
        self.assertNotIn("generator", row)
        self.assertIn("t1gen_schema_error", row)


def window(entry: int, rate: float, pair: int = 111, others: float = 0.5, status: str = "valid") -> dict:
    return {"type": "window", "program": "mserver", "shape": "static", "m": 10, "table_seed": pair, "arm": "null",
            "entry": entry, "generator_tool": G.TOOLS[entry], "status": status, "others": {"sum_pct_of_one_cpu": others},
            "generator": {"measure": {"completed": int(rate * 5)}, "measure_wall_ns": 5_000_000_000}}


def round_of(rate_p2: float, rate_t1: float, pair: int) -> list[dict]:
    return [window(0, rate_p2, pair), window(1, rate_t1, pair), window(1, rate_t1, pair), window(0, rate_p2, pair)]


class AnalysisTests(unittest.TestCase):
    def test_the_median_interval_for_sixteen_pairs(self) -> None:
        k, coverage = G.median_interval(16)
        self.assertEqual((k, round(coverage, 4)), (4, 0.9787))
        self.assertEqual(G.median_interval(5), (0, 0.0))  # too few pairs for a 95% interval

    def test_ratios_per_pair_and_the_report(self) -> None:
        rows = [w for i in range(16) for w in round_of(100_000.0 + i, 100_000.0, 111 + i)]
        bad = round_of(1.0, 1.0, 200)
        bad[0]["generator_tool"] = "t1gen"
        got, dropped = G.ratios([*rows, *bad])
        self.assertEqual((len(got), dict(dropped)), (16, {G.NOT_A_ROUND: 1}))
        rep = G.report([g["q"] for g in got])
        self.assertEqual((rep["pairs"], rep["interval_order_statistics"]), (16, [4, 13]))
        self.assertAlmostEqual(rep["interval"][0], round(100_003 / 100_000, 5))

    def test_a_file_that_is_not_the_committed_plans_run_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "gencheck-L.json").write_text(json.dumps({"g": 1, "_note": "x"}), encoding="utf-8")
            rows = round_of(1.0, 1.0, 111)
            for i, w in enumerate(rows):
                w["seq"] = i
            for plan, code in (({"g": 1}, 0), ({"g": 2}, 2)):
                src = tmp / "g.jsonl"
                head = {"type": "session", "system": "linux", "mode": "timed", "plan": plan, "windows": 4}
                src.write_text("".join(json.dumps(r) + "\n" for r in [head, *rows]), encoding="utf-8")
                self.assertEqual(G.main([str(src), "--out", str(tmp / "r.json")], plans=tmp), code)


class PlanTests(unittest.TestCase):
    def test_the_plan_is_the_null_arm_twice_over_sixteen_pairs(self) -> None:
        plan, _ = p2run.load_plan(HERE / "plans" / "gencheck-L.json")
        self.assertEqual(p2run.total_windows(plan), 64)
        self.assertEqual([p.arms for p in plan.programs], [("null", "null")])
        raw = json.loads((HERE / "plans" / "gencheck-L.json").read_text(encoding="utf-8"))
        probe_plan = json.loads((HERE / "plans" / "probe-L.json").read_text(encoding="utf-8"))
        self.assertTrue(raw["_expect_sha256"].items() <= probe_plan["_expect_sha256"].items())
        self.assertEqual(set(raw["_expect_sha256"]), {raw["p2gen"], raw["programs"][0]["path"]})


if __name__ == "__main__":
    unittest.main(verbosity=1)
