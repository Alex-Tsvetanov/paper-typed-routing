#!/usr/bin/env python3
"""Tests of t3/jobs/probe.py, the timing probe: the refusals, the session check and the planning
summary, on synthetic rows and files. Untimed: no test runs a server or reads a time of one.

    python t3/test_probe.py          (or: python -m pytest t3/test_probe.py)
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "jobs"))
sys.path.insert(0, str(HERE))
import labsteps  # noqa: E402
import probe  # noqa: E402


def window(seq: int, m: int, started: str | None, status: str = "valid", program: str = "mserver", arm: str = "v2",
           startup: float | None = None) -> dict:
    w = {"type": "window", "seq": seq, "m": m, "shape": "static", "program": program, "arm": arm, "status": status,
         "reasons": [] if status == "valid" else ["error share 0.5 above 0.001"]}
    if started:
        w["started"] = started
    if startup is not None:
        w["startup_s"] = startup
    return w


class SummaryTests(unittest.TestCase):
    def test_timed_summary_has_verdicts_startups_and_spacing_but_no_rate(self) -> None:
        rows = [{"type": "session"},
                dict(window(1, 10, "2026-10-25T10:00:00+0200"), others={"sum_pct_of_one_cpu": 0.5}),
                dict(window(2, 10, "2026-10-25T10:00:06+0200"), others={"sum_pct_of_one_cpu": 2.25}),
                window(3, 100000, "2026-10-25T10:00:12+0200", startup=4.0),
                window(4, 100000, "2026-10-25T10:00:24+0200", status="overloaded", arm="drogon", startup=5.5),
                window(5, 10, "2026-10-25T10:00:36+0200")]
        s = probe.summarize(rows, arms_per_system=2)
        self.assertEqual(s["windows"], 5)
        self.assertEqual(s["by_status"], {"valid": 4, "overloaded": 1})
        self.assertEqual([n["arm"] for n in s["not_valid"]], ["drogon"])
        self.assertEqual(s["startup_s_max_at_m100000"], {"mserver/drogon": 5.5, "mserver/v2": 4.0})
        self.assertEqual(s["seconds_start_to_start_mean"], {"10": 6.0, "100000": 12.0})
        self.assertEqual(s["others"], {"windows_with": 2, "windows_without": 3, "max_sum_pct_of_one_cpu": 2.25,
                                       "max_at": {"seq": 2, "program": "mserver", "arm": "v2", "shape": "static",
                                                  "m": 10}})
        per_size = 2 * 2 * 2 * 16
        self.assertEqual(s["campaign_estimate"]["windows"], per_size * 5)
        self.assertAlmostEqual(s["campaign_estimate"]["hours"], round(per_size * (4 * 6.0 + 12.0) / 3600, 2))
        text = str(s)
        for word in ("completed", "rate", "req/s", "rps"):
            self.assertNotIn(word, text)

    def test_count_mode_summary_has_no_time(self) -> None:
        s = probe.summarize([window(1, 10, None), window(2, 100000, None)], arms_per_system=1)
        self.assertEqual(s["windows"], 2)
        for key in ("startup_s_max_at_m100000", "seconds_start_to_start_mean", "campaign_estimate", "others"):
            self.assertNotIn(key, s)


class RefusalTests(unittest.TestCase):
    def clean(self, porcelain: str = ""):
        """The clone as clean (or as dirty) as the test needs, whatever this checkout's state."""
        real = labsteps.git
        return mock.patch.object(probe.L, "git", side_effect=lambda *a: porcelain if a[0] == "status" else real(*a))

    def test_refuses_a_missing_or_other_binary_and_accepts_the_right_one(self) -> None:
        head = labsteps.git("rev-parse", "HEAD")
        with tempfile.TemporaryDirectory() as tmp, self.clean():
            f = Path(tmp) / "mserver"
            f.write_bytes(b"binary")
            good = hashlib.sha256(b"binary").hexdigest()
            self.assertEqual(probe.refusals({"_build_commit": head, "_expect_sha256": {str(f): good}}), [])
            r = probe.refusals({"_build_commit": head, "_expect_sha256": {str(f): "0" * 64, str(f) + "x": good}})
            self.assertEqual(len(r), 2)
        self.assertEqual(len(probe.refusals({"_build_commit": "", "_expect_sha256": {}})), 1)

    def test_refuses_a_dirty_clone_and_a_commit_git_cannot_find(self) -> None:
        head = labsteps.git("rev-parse", "HEAD")
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "mserver"
            f.write_bytes(b"binary")
            want = {str(f): hashlib.sha256(b"binary").hexdigest()}
            with self.clean(" M STATE.md"):
                self.assertEqual(probe.refusals({"_build_commit": head, "_expect_sha256": want}),
                                 ["the paper clone has local changes"])
            with self.clean():
                r = probe.refusals({"_build_commit": "0" * 40, "_expect_sha256": want})
        self.assertEqual(len(r), 1)
        self.assertIn("git could not compare", r[0])

    def test_a_file_no_build_reads_is_left_out_and_any_other_change_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.clean():
            f = Path(tmp) / "mserver"
            f.write_bytes(b"binary")
            want = {str(f): hashlib.sha256(b"binary").hexdigest()}
            try:  # round 3's bring-up, whose bench/ct_msvc.py 0d6b22f changed
                labsteps.git("cat-file", "-e", "3ff814e50^{commit}")
            except labsteps.StepError:
                self.skipTest("round 3's build commit is not in this clone")
            self.assertEqual(probe.refusals({"_build_commit": "3ff814e50", "_expect_sha256": want}), [])
            last = labsteps.git("rev-list", "-1", "HEAD", "--", "server")  # the parent differs in server/
            r = probe.refusals({"_build_commit": last + "^", "_expect_sha256": want})
        self.assertEqual(len(r), 1)
        self.assertIn("compiled sources differ", r[0])

    def test_no_cmake_file_names_a_left_out_file(self) -> None:
        root = HERE.parent
        skip = {".git", "_deps"}
        cmake = [p for p in root.rglob("*") if p.is_file() and (p.name == "CMakeLists.txt" or p.suffix == ".cmake")
                 and not skip.intersection(p.relative_to(root).parts)
                 and not p.relative_to(root).parts[0].startswith(("build", "out"))]
        self.assertTrue(cmake)
        for left_out in probe.NOT_COMPILED:
            self.assertTrue((root / left_out).is_file(), left_out)
            self.assertTrue(any(left_out == c or left_out.startswith(c + "/") for c in probe.COMPILED), left_out)
            for p in cmake:
                self.assertNotIn(Path(left_out).name, p.read_text(encoding="utf-8", errors="replace"), str(p))

    def test_the_session_must_name_the_same_binaries(self) -> None:
        session = {"p2gen": {"argv": ["/b/p2gen"], "sha256": "a"},
                   "programs": [{"argv": ["/b/mserver"], "sha256": "b"}]}
        self.assertEqual(probe.session_differs(session, {"/b/p2gen": "a", "/b/mserver": "b"}), [])
        self.assertEqual(len(probe.session_differs(session, {"/b/p2gen": "a", "/b/mserver": "c"})), 1)
        unexpected = probe.session_differs(session, {"/b/p2gen": "a"})  # a binary the plan does not pin
        self.assertEqual(len(unexpected), 1)
        self.assertIn("not in the plan", unexpected[0])
        self.assertEqual(probe.session_differs(session, {"/b/./p2gen": "a", "/b/mserver": "b", "/b/p2v2.dll": "d"}), [])


class PlanTests(unittest.TestCase):
    def test_the_probe_plans_are_runner_plans_of_the_right_size(self) -> None:
        import p2run
        for name, windows in (("probe-L.json", 176), ("probe-W.json", 168)):
            plan, _ = p2run.load_plan(HERE / "plans" / name)
            self.assertEqual(p2run.total_windows(plan), windows)
            self.assertEqual(list(plan.sizes), [10, 100000])
            raw = json.loads((HERE / "plans" / name).read_text(encoding="utf-8"))
            pinned = raw["_expect_sha256"]
            for path in (raw["p2gen"], *(p["path"] for p in raw["programs"])):
                self.assertIn(path, pinned, f"{name}: {path} has no sha256 to check")
            self.assertTrue(all(len(s) == 64 and int(s, 16) >= 0 for s in pinned.values()))


if __name__ == "__main__":
    unittest.main(verbosity=1)
