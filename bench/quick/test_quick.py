"""Tests of P2's quick plans and runner (quick-plan.md). Nothing here times anything.

    python -I -B bench/quick/test_quick.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quick_common as qc  # noqa: E402
import quick_plans  # noqa: E402
import quick_run  # noqa: E402


class Plans(unittest.TestCase):
    def test_plans_on_disk_match(self):
        self.assertEqual(quick_plans.main(["--check"]), 0)

    def test_every_round_runs_every_cell_once_in_a_new_order(self):
        for name in qc.PLANS:
            header, rows = qc.plan_rows(name)
            orders = []
            for rnd in range(header["rounds"]):
                ids = [r["id"].split("-", 1)[1] for r in rows if r["round"] == rnd]
                self.assertEqual(len(ids), len(set(ids)), name)
                self.assertEqual(len(ids), header["processes_per_round"], name)
                orders.append(ids)
            for o in orders[1:]:
                self.assertEqual(sorted(o), sorted(orders[0]), name)
                self.assertNotEqual(o, orders[0], f"{name}: a round repeats the order of round 0")

    def test_new_seeds_are_not_frozen_ones_and_differ(self):
        seeds = []
        for name in qc.PLANS:
            seeds.append(qc.order_seed(name))
            for rnd in range(qc.PLANS[name]["rounds"]):
                seeds += [qc.table_seed(name, rnd), qc.ring_seed(name, rnd)]
        self.assertFalse(set(seeds) & qc.FROZEN_SEEDS)
        self.assertEqual(len(seeds), len(set(seeds)))

    def test_rbench_rounds_fit_the_budget_by_the_named_estimates(self):
        for name, p in qc.PLANS.items():
            header, _ = qc.plan_rows(name)
            if p["kind"] == "rbench":
                self.assertEqual(header["rounds_by_arithmetic"], header["rounds"], name)
                self.assertFalse(qc.rounds_fit(header["round_est_s"], header["rounds"] + 1),
                                 f"{name}: one more round would also fit")
            else:
                self.assertGreaterEqual(header["rounds_by_arithmetic"], 1, name)

    def test_a_round_of_an_rbench_plan_uses_one_table_and_ring_seed(self):
        for name, p in qc.PLANS.items():
            if p["kind"] != "rbench":
                continue
            _, rows = qc.plan_rows(name)
            for rnd in range(p["rounds"]):
                rr = [r for r in rows if r["round"] == rnd]
                self.assertEqual(len({(r["table_seed"], r["ring_seed"]) for r in rr}), 1, name)

    def test_aa_pair_only_in_abl_s(self):
        for name in qc.PLANS:
            _, rows = qc.plan_rows(name)
            aa = [r for r in rows if r.get("aa")]
            if name == "quick-L-abl-s":
                self.assertEqual(len(aa), qc.PLANS[name]["rounds"] * len(qc.SHAPES) * 2)
                self.assertTrue(all(r["arm"] == qc.AA_ARM for r in aa))
            else:
                self.assertFalse(aa, name)

    def test_adversarial_cells_are_the_tools_names(self):
        cells = qc.adversarial_cells()
        self.assertEqual(len(cells), 33)
        self.assertFalse([c for c in cells if "other-method" in c])
        self.assertIn("two-k16-catch-all-miss", cells)

    def test_every_plan_arm_is_in_the_linux_build(self):
        for name, p in qc.PLANS.items():
            for a in p.get("arms", ()):
                self.assertIn(a, qc.LINUX_ARMS, name)
        self.assertNotIn("nethttp", qc.LINUX_ARMS)


class Runner(unittest.TestCase):
    def test_refuses_a_wrong_sha(self):
        with self.assertRaises(quick_run.Refusal):
            quick_run.read_plan("quick-L-abl-s", "0" * 64)

    def test_reads_the_right_sha(self):
        sha = qc.file_sha256(qc.PLANS_DIR / "quick-L-abl-s.jsonl")
        header, rows = quick_run.read_plan("quick-L-abl-s", sha)
        self.assertEqual(header["plan"], "quick-L-abl-s")
        self.assertTrue(rows)

    def test_release_check(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bench = d / "bench"
            bench.mkdir()
            (bench / "main.cpp").write_text("", encoding="utf-8")
            build = d / "build"
            build.mkdir()

            def cc(flags):
                (build / "compile_commands.json").write_text(json.dumps(
                    [{"directory": str(build), "file": str(bench / "main.cpp"), "command": f"clang++ {flags} -c x"},
                     {"directory": str(build), "file": str(d / "dep.cpp"), "command": "clang++ -O2 -c y"}]),
                    encoding="utf-8")

            cc("-O3 -DNDEBUG")
            self.assertEqual(quick_run.check_release(build, bench)["files_checked"], 1)
            cc("-O2")
            with self.assertRaises(quick_run.Refusal):
                quick_run.check_release(build, bench)
            cc("-O3 -O0")
            with self.assertRaises(quick_run.Refusal):
                quick_run.check_release(build, bench)

    def _fake(self, header, rows, walls, budget=qc.BUDGET_S):
        t = [0.0]
        ran = []

        def clock():
            return t[0]

        def runner(cmd, row, out_dir, timeout):
            ran.append(row["id"])
            w = min(walls(row), timeout)
            t[0] += w
            return {"id": row["id"], "rc": 0 if w < timeout else -9, "wall_s": w}

        job = quick_run.run_plan(header, rows, Path("b"), Path("o"), budget, runner, clock)
        return job, ran

    def test_all_rounds_run_when_they_fit(self):
        header, rows = qc.plan_rows("quick-L-abl-s")
        job, ran = self._fake(header, rows, lambda r: 1.0)
        self.assertEqual(job["rounds_run"], header["rounds"])
        self.assertEqual(len(ran), len(rows))
        self.assertIsNone(job["cut"])

    def test_rounds_are_cut_before_the_budget(self):
        header, rows = qc.plan_rows("quick-L-abl-s")
        job, ran = self._fake(header, rows, lambda r: 2.0)  # 224 s a round: two rounds fit
        self.assertEqual(job["rounds_run"], 2)
        self.assertTrue(job["cut"].startswith("before round 2"))
        self.assertLessEqual(len(ran) * 2.0, qc.BUDGET_S)

    def test_a_process_that_would_pass_the_budget_is_not_started(self):
        header, rows = qc.plan_rows("quick-L-adv")
        job, ran = self._fake(header, rows, lambda r: 200.0 if "k16" in r["id"] else 5.0)
        self.assertLessEqual(job["wall_s"], qc.BUDGET_S)
        self.assertTrue(job["cut"])
        self.assertLess(len(ran), len(rows))
        self.assertTrue(any(u["rc"] == -9 for u in job["units"]) or "before process" in job["cut"])

    def test_commands_pin_the_cpu(self):
        header, rows = qc.plan_rows("quick-L-bnd-10")
        cmd = quick_run.command(header, rows[0], Path("/b"))
        self.assertEqual(cmd[:3], ["taskset", "-c", "2"])
        self.assertEqual(Path(cmd[3]).name, "rbench")
        header, rows = qc.plan_rows("quick-L-adv")
        cmd = quick_run.command(header, rows[0], Path("/b"))
        self.assertEqual(Path(cmd[3]).name, "adversarial")
        self.assertIn("--build-reps", cmd)


if __name__ == "__main__":
    unittest.main(verbosity=1)
