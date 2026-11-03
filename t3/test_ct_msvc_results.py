#!/usr/bin/env python3
"""Tests of t3/ct_msvc_results.py on a made-up job folder (no result).

    python t3/test_ct_msvc_results.py          (or: python -m pytest t3/test_ct_msvc_results.py)
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ct_msvc_results as C  # noqa: E402


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.archive = d / "job.tar.gz"
        self.archive.write_bytes(b"archive")
        (d / "job.tar.gz.sha256").write_text(hashlib.sha256(b"archive").hexdigest() + " *job.tar.gz\n")
        self.job = d / "p2r3-ct-msvc-w"
        (self.job / "out" / "ct" / "ct").mkdir(parents=True)
        (self.job / "out" / "ct" / "steps.txt").write_text("\n".join(C.STEPS_OK) + "\n")
        (self.job / "spec.json").write_text(json.dumps({"commit": "c0ffee"}))
        self.write([{"table": t, "harness_compile": "ok", "compiler": "MSVC 1.2.3.0"} for t in C.ct_msvc.TABLES])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, rows: list[dict]) -> None:
        (self.job / C.TABLES_FILE).write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def test_a_complete_run_is_wrapped_with_its_inputs(self) -> None:
        out = C.build(self.archive, self.job)
        self.assertEqual(len(out["tables"]), len(C.ct_msvc.TABLES))
        self.assertEqual((out["inputs"]["job"], out["inputs"]["commit"]), ("p2r3-ct-msvc-w", "c0ffee"))
        self.assertEqual(out["inputs"]["archive_sha256"], hashlib.sha256(b"archive").hexdigest())

    def test_refusals(self) -> None:
        self.archive.write_bytes(b"other")
        with self.assertRaisesRegex(C.ResultsError, "sha256"):
            C.build(self.archive, self.job)
        self.archive.write_bytes(b"archive")
        self.write([{"table": t, "harness_compile": "ok", "compiler": "MSVC 1.2.3.0"} for t in C.ct_msvc.TABLES[1:]])
        with self.assertRaisesRegex(C.ResultsError, "TABLES"):
            C.build(self.archive, self.job)
        self.write([{"table": t, "harness_compile": "ok", "compiler": f"MSVC {i}"} for i, t in enumerate(C.ct_msvc.TABLES)])
        with self.assertRaisesRegex(C.ResultsError, "compilers"):
            C.build(self.archive, self.job)
        (self.job / "out" / "ct" / "steps.txt").write_text("clean: ok\nsources: ok\nct: exit 1\n")
        with self.assertRaisesRegex(C.ResultsError, "steps"):
            C.build(self.archive, self.job)


if __name__ == "__main__":
    unittest.main(verbosity=1)
