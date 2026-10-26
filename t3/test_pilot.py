#!/usr/bin/env python3
"""Tests of the A/A pilot: t3/pilot_analysis.py on synthetic rows, the pilot plans, and t3/jobs/pilot.py's
summary. Untimed: no test runs a server, and every rate here is made up.

    python t3/test_pilot.py          (or: python -m pytest t3/test_pilot.py)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "jobs"))
sys.path.insert(0, str(HERE))
import p2run  # noqa: E402
import pilot  # noqa: E402
import pilot_analysis as A  # noqa: E402


def window(entry: int, rate: float, status: str = "valid", others: float | None = 0.5, program: str = "mserver",
           m: int = 10, pair: int = 111, arm: str = "v2") -> dict:
    w = {"type": "window", "program": program, "shape": "static", "m": m, "table_seed": pair, "arm": arm,
         "entry": entry, "status": status,
         "generator": {"measure": {"completed": int(rate * 5)}, "measure_wall_ns": 5_000_000_000}}
    if others is not None:
        w["others"] = {"sum_pct_of_one_cpu": others}
    return w


def aa_round(rate0: float, rate1: float, **kw) -> list[dict]:
    """Entry 0's windows 1 and 4, entry 1's 2 and 3, as p2run orders an A/A round."""
    return [window(0, rate0, **kw), window(1, rate1, **kw), window(1, rate1, **kw), window(0, rate0, **kw)]


SESSION = {"type": "session", "system": "linux"}


class QuantileTests(unittest.TestCase):
    def test_type_7_as_numpy(self) -> None:
        self.assertAlmostEqual(A.quantile([1, 2, 3, 4], 0.975), 3.925)
        self.assertAlmostEqual(A.quantile([4, 1, 3, 2], 0.5), 2.5)
        self.assertEqual(A.quantile([7.0], 0.975), 7.0)
        with self.assertRaises(ValueError):
            A.quantile([], 0.5)


class ReplicateTests(unittest.TestCase):
    def test_a_round_gives_the_ratio_and_the_time_difference(self) -> None:
        reps, dropped = A.replicates([SESSION, *aa_round(100_000.0, 80_000.0)])
        self.assertEqual(dropped, {})
        self.assertEqual(len(reps), 1)
        self.assertAlmostEqual(reps[0]["r"], 1.25)
        self.assertAlmostEqual(reps[0]["d_ns"], 1e9 / 100_000 - 1e9 / 80_000)
        self.assertEqual(reps[0]["system"], "linux")

    def test_a_round_with_a_window_that_does_not_count_is_dropped(self) -> None:
        bad = aa_round(100_000.0, 100_000.0)
        bad[2]["status"] = "overloaded"
        busy = aa_round(100_000.0, 100_000.0, pair=112)
        busy[0]["others"]["sum_pct_of_one_cpu"] = 23.6
        blind = aa_round(100_000.0, 100_000.0, pair=113, others=None)
        reps, dropped = A.replicates([SESSION, *bad, *busy, *blind])
        self.assertEqual(reps, [])
        self.assertEqual(dropped, {"status overloaded": 1, "other processes above 10% of one CPU": 1,
                                   "no record of other processes": 1})
        reps, _ = A.replicates([SESSION, *busy, *blind], others_max=None)  # no rule: both count
        self.assertEqual(len(reps), 2)

    def test_only_an_aa_round_of_four_windows_counts(self) -> None:
        mixed = aa_round(1.0, 1.0)
        mixed[1]["arm"] = "crow"
        short = aa_round(1.0, 1.0, pair=112)[:3]
        reps, dropped = A.replicates([SESSION, *mixed, *short])
        self.assertEqual((reps, dict(dropped)), ([], {"not an A/A round of four windows": 2}))


class DeltaTests(unittest.TestCase):
    def test_the_floor_holds_for_quiet_data(self) -> None:
        self.assertEqual(A.delta([1.0, 1.001, 0.999] * 20), 1.02)

    def test_reading_a_takes_either_direction_and_b_folds(self) -> None:
        rs = [1.0] * 36 + [1.05, 1.06, 0.9, 0.92]
        a = A.delta(rs, "a")
        self.assertAlmostEqual(a, max(A.quantile(rs, 0.975), A.quantile([1 / r for r in rs], 0.975)))
        self.assertAlmostEqual(A.delta(rs, "b"), A.quantile([max(r, 1 / r) for r in rs], 0.975))
        self.assertGreater(a, 1.02)
        with self.assertRaises(ValueError):
            A.delta(rs, "c")

    def test_delta_is_rounded_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            got = run_files(Path(tmp), {"linux": [aa_round(100_000.0, 97_000.0)], "windows": [aa_round(1.0, 1.0)]})
        self.assertEqual(got[0], 0)
        exact = A.delta([100_000.0 / 97_000.0, 1.0])
        self.assertGreaterEqual(got[1]["delta"], exact)
        self.assertLess(got[1]["delta"] - exact, 1e-4)


def pilot_file(system: str, rounds: list[list[dict]], **session) -> list[dict]:
    """A complete synthetic pilot file of one system: its session line, then its rounds' windows in order."""
    windows = [dict(w, seq=i) for i, w in enumerate(w for r in rounds for w in r)]
    head = {"type": "session", "system": system, "mode": "timed", "plan": {"pilot": system}, "windows": len(windows)}
    return [dict(head, **session), *windows]


def run_files(tmp: Path, by_system: dict, **session) -> tuple[int, dict | None]:
    """Writes synthetic pilot files and plans into tmp, runs main, returns its exit and result."""
    plans = tmp / "plans"
    plans.mkdir(exist_ok=True)
    for system, name in A.SYSTEMS.items():
        (plans / name).write_text(json.dumps({"pilot": system, "_comment": "x"}), encoding="utf-8")
    files = []
    for i, (system, rounds) in enumerate(by_system.items()):
        rows = rounds if rounds and isinstance(rounds[0], dict) else pilot_file(system, rounds, **session)
        files.append(tmp / f"{i}-{system}.jsonl")
        files[-1].write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    out = tmp / "r.json"
    rc = A.main([*map(str, files), "--out", str(out)], plans=plans)
    return rc, json.loads(out.read_text(encoding="utf-8")) if out.exists() else None


class FileTests(unittest.TestCase):
    def test_both_systems_give_delta_and_the_noise_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc, got = run_files(Path(tmp), {"linux": [aa_round(100_000.0, 99_000.0), aa_round(1.0, 1.0, pair=112)],
                                            "windows": [aa_round(90_000.0, 91_000.0, program="mserver-go")]})
        self.assertEqual(rc, 0)
        self.assertEqual((got["replicates"], got["rule"]["delta_reading"]), (3, A.DELTA_READING))
        self.assertEqual([(n["system"], n["program"], n["replicates"]) for n in got["noise"]],
                         [("linux", "mserver", 2), ("windows", "mserver-go", 1)])

    def test_files_the_rule_does_not_accept_are_refused(self) -> None:
        good = [aa_round(1.0, 1.0)]
        cases = {
            "one system": {"linux": good},
            "count mode": {"linux": good, "windows": good, "_session": {"mode": "count"}},
            "another plan": {"linux": good, "windows": good, "_session": {"plan": {"pilot": "other"}}},
            "a window short": {"linux": pilot_file("linux", good)[:-1], "windows": good},
            "a window twice": {"linux": [*pilot_file("linux", good), pilot_file("linux", good)[1]], "windows": good},
            "no session": {"linux": pilot_file("linux", good)[1:], "windows": good},
        }
        for name, case in cases.items():
            session = case.pop("_session", {})
            with tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(run_files(Path(tmp), case, **session), (2, None), name)

    def test_a_second_file_of_one_system_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rc, _ = run_files(tmp, {"linux": [aa_round(1.0, 1.0)], "windows": [aa_round(1.0, 1.0)]})
            self.assertEqual(rc, 0)
            plans, files = tmp / "plans", sorted(tmp.glob("*.jsonl"))
            self.assertEqual(A.main([*map(str, files), str(files[0]), "--out", str(tmp / "x.json")], plans=plans), 2)

    def test_a_window_without_others_or_answers_does_not_count(self) -> None:
        blind = aa_round(1.0, 1.0)
        blind[1]["others"] = {}
        empty = aa_round(1.0, 1.0, pair=112)
        empty[3]["generator"]["measure"]["completed"] = 0
        reps, dropped = A.replicates([SESSION, *blind, *empty])
        self.assertEqual((reps, dict(dropped)), ([], {"no record of other processes": 1,
                                                      "no timed generator line with a completed answer": 1}))


class PlanTests(unittest.TestCase):
    def test_the_pilot_plans_are_aa_rounds_at_every_cell_of_h8(self) -> None:
        for name in ("pilot-L.json", "pilot-W.json"):
            plan, _ = p2run.load_plan(HERE / "plans" / name)
            self.assertEqual(p2run.total_windows(plan), 1920)
            self.assertEqual((list(plan.sizes), len(plan.pairs), len(plan.shapes)), ([10, 100, 1000, 10000, 100000], 16, 2))
            self.assertTrue(all(p.arms == ("v2", "v2") for p in plan.programs))
            raw = json.loads((HERE / "plans" / name).read_text(encoding="utf-8"))
            probe_plan = json.loads((HERE / "plans" / name.replace("pilot", "probe")).read_text(encoding="utf-8"))
            self.assertEqual((raw["_build_commit"], raw["_expect_sha256"]),
                             (probe_plan["_build_commit"], probe_plan["_expect_sha256"]))

    def test_the_job_summary_holds_no_campaign_estimate(self) -> None:
        rows = [{"type": "session"}, {"type": "window", "seq": 0, "m": 10, "status": "valid", "program": "mserver",
                                      "arm": "v2", "started": "2026-10-26T10:00:00+0200"},
                {"type": "window", "seq": 1, "m": 10, "status": "valid", "program": "mserver", "arm": "v2",
                 "started": "2026-10-26T10:00:06+0200"}]
        s = pilot.summarize(rows)
        self.assertNotIn("campaign_estimate", s)
        self.assertEqual(s["windows"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
