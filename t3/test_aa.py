#!/usr/bin/env python3
"""Tests of t3/jobs/aa.py, the A/A runs without a campaign: the refusals and the order and stop of the runs, with
p2run and the binary checks stood in for. Untimed: no test runs a server or reads a time of one.

    python t3/test_aa.py          (or: python -m pytest t3/test_aa.py)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "jobs"))
sys.path.insert(0, str(HERE))
import aa  # noqa: E402
import rr  # noqa: E402

BUILD = {"_build_commit": "3ff814e50", "_expect_sha256": {"/b/mserver": "ab"}, "schedule": "round-robin"}


def plan(arms=("v2", "v2"), **over) -> dict:
    return {**BUILD, "programs": [{"name": "mserver", "path": "/b/mserver", "arms": list(arms)}], **over}


class RefusalTests(unittest.TestCase):
    def refusals(self, *named) -> list:
        with mock.patch.object(aa.probe, "refusals", return_value=[]):
            return aa.plan_refusals([(Path(name), p) for name, p in named])

    def test_an_aa_plan_and_a_k_server_plan_of_one_build_pass(self) -> None:
        self.assertEqual(self.refusals(("rr-aa-W.json", plan()), ("rr-aak-W.json", plan(["v2"] * 7))), [])

    def test_refusals(self) -> None:
        self.assertIn("rr-W.json is not an A/A plan (one arm repeated in every program)",
                      self.refusals(("rr-W.json", plan(["v2", "crow"]))))
        self.assertIn("x.json is not an A/A plan (one arm repeated in every program)", self.refusals(("x.json", plan(["v2"]))))
        self.assertIn("x.json is not round-robin", self.refusals(("x.json", plan(schedule="mirrored"))))
        self.assertIn("the plans name different builds",
                      self.refusals(("a.json", plan()), ("b.json", plan(_build_commit="other"))))
        self.assertIn("two plans share a file name, so their records would share one",
                      self.refusals(("one/a.json", plan()), ("two/a.json", plan())))

    def test_the_build_guards_are_probes(self) -> None:
        with mock.patch.object(aa.probe, "refusals", return_value=["the paper clone has local changes"]):
            self.assertEqual(aa.plan_refusals([(Path("a.json"), plan())]), ["the paper clone has local changes"])


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.paths = []
        for name, p in (("rr-aa-W.json", plan()), ("rr-aak-W.json", plan(["v2"] * 7))):
            path = self.dir / name
            path.write_text(json.dumps(p))
            self.paths.append(path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def main(self, results, *extra) -> tuple[int, list, dict]:
        calls = []

        def fake(name, path, out, count, want):
            calls.append((name, Path(path).name, count))
            return results[len(calls) - 1]
        argv = ["aa.py", str(self.dir / "out"), *map(str, self.paths), *extra]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(aa.probe, "refusals", return_value=[]), \
                mock.patch.object(aa.probe, "binary_problems", return_value=[]), \
                mock.patch.object(aa.L, "git", return_value="HEAD"), mock.patch.object(rr, "run_and_summarize", fake):
            rc = aa.main()
        return rc, calls, json.loads((self.dir / "out" / "aa-summary.json").read_text())

    def test_the_plans_run_in_order_into_records_named_by_their_stems(self) -> None:
        ok = (0, {"p2run_exit": 0, "session_binaries_differ": []}, True)
        rc, calls, summary = self.main([ok, ok])
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [("rr-aa-W", "rr-aa-W.json", None), ("rr-aak-W", "rr-aak-W.json", None)])
        self.assertEqual((summary["mode"], summary["runs"]), ("timed", ["rr-aa-W", "rr-aak-W"]))

    def test_a_run_that_did_not_finish_stops_the_rest(self) -> None:
        rc, calls, summary = self.main([(3, {"p2run_exit": 3, "session_binaries_differ": []}, False)])
        self.assertEqual((rc, len(calls)), (3, 1))
        self.assertNotIn("rr-aak-W", summary)

    def test_other_binaries_in_a_session_give_exit_2(self) -> None:
        rc, calls, _ = self.main([(0, {"p2run_exit": 0, "session_binaries_differ": ["/b/mserver"]}, False)], "--count", "5")
        self.assertEqual((rc, calls[0][2]), (2, 5))

    def test_a_refused_plan_runs_nothing(self) -> None:
        self.paths[1].write_text(json.dumps(plan(["v2", "crow"])))
        rc, calls, summary = self.main([])
        self.assertEqual((rc, calls), (2, []))
        self.assertIn("rr-aak-W.json is not an A/A plan (one arm repeated in every program)", summary["refused"])


class RunAndSummarizeTests(unittest.TestCase):
    def test_finished_means_exit_0_or_count_mode_1_with_the_expected_binaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "x.jsonl").write_text(json.dumps({"type": "session"}) + "\n")
            for code, count, differ, want in ((0, None, [], True), (1, None, [], False), (1, 5, [], True),
                                              (2, 5, [], False), (0, None, ["/b/mserver"], False)):
                with mock.patch.object(rr, "run_one", return_value=code), \
                        mock.patch.object(rr.probe, "session_differs", return_value=differ):
                    got = rr.run_and_summarize("x", out / "x.json", out, count, {})
                self.assertEqual((got[0], got[2]), (code, want), (code, count, differ))
                self.assertEqual(got[1]["p2run_exit"], code)


if __name__ == "__main__":
    unittest.main(verbosity=1)
