#!/usr/bin/env python3
"""Tests of t3/jobs/ctmsvc.py with git and ct_msvc.py stood in for. Untimed: no test compiles anything.

    python t3/test_ctmsvc.py          (or: python -m pytest t3/test_ctmsvc.py)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "jobs"))
sys.path.insert(0, str(HERE))
import ctmsvc as C  # noqa: E402


class CloneTests(unittest.TestCase):
    def test_a_checkout_that_is_not_the_commit_is_refused(self) -> None:
        answers = iter(["", "", "0" * 40, ""])
        with mock.patch.object(C, "git", side_effect=lambda *a: next(answers)):
            with self.assertRaisesRegex(C.Refused, "not a clean"):
                C.clone_at("url", "1" * 40, Path("dest"))

    def test_a_checkout_with_changes_is_refused(self) -> None:
        answers = iter(["", "", "1" * 40, " M file"])
        with mock.patch.object(C, "git", side_effect=lambda *a: next(answers)):
            with self.assertRaisesRegex(C.Refused, "not a clean"):
                C.clone_at("url", "1" * 40, Path("dest"))


class MainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "ct"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_main(self, clean: str = "", rc: int = 0) -> tuple[int, list]:
        calls = []
        with mock.patch.object(sys, "argv", ["ctmsvc.py", str(self.out)]), mock.patch.object(C.os, "name", "nt"), \
                mock.patch.object(C.L, "git", return_value=clean), \
                mock.patch.object(C, "clone_at", side_effect=lambda url, commit, dest: calls.append((commit, dest.name))), \
                mock.patch.object(C.subprocess, "run", return_value=subprocess.CompletedProcess([], rc)) as run:
            code = C.main()
        return code, calls + [run.call_args[0][0] if run.called else None]

    def test_sources_then_ct_msvc_with_the_laptops_compiler(self) -> None:
        code, calls = self.run_main(rc=0)
        self.assertEqual(code, 0)
        self.assertEqual(calls[:2], [(C.RM_COMMIT, "RegexMatcher"), (C.GTEST_COMMIT, "googletest")])
        cmd = calls[2]
        self.assertEqual(cmd[cmd.index("--msvc-version") + 1], C.EXPECT_MSVC)
        self.assertEqual(cmd[cmd.index("--commit") + 1], C.RM_COMMIT)
        self.assertIn("ct: exit 0", (self.out / "steps.txt").read_text())

    def test_ct_msvcs_exit_is_the_jobs(self) -> None:
        self.assertEqual(self.run_main(rc=1)[0], 1)

    def test_a_clone_with_local_changes_stops_before_any_download(self) -> None:
        code, calls = self.run_main(clean=" M t3/rr_results.py")
        self.assertEqual((code, calls), (2, [None]))
        self.assertIn("clean: refused", (self.out / "steps.txt").read_text())

    def test_an_existing_source_folder_is_refused(self) -> None:
        (self.out / "src").mkdir(parents=True)
        code, calls = self.run_main()
        self.assertEqual((code, calls), (2, [None]))
        self.assertIn("sources: refused", (self.out / "steps.txt").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=1)
