#!/usr/bin/env python3
"""Tests of t3/rr_records.py on synthetic records: every count and time below is made up for the test and is no result.

    python t3/test_rr_records.py          (or: python -m pytest t3/test_rr_records.py)
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rr_records as RR  # noqa: E402
import rr_results as R  # noqa: E402
from test_rr_results import plan_dict, record  # noqa: E402

T0 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2)))
SLOW = 0.95   # the made-up first stretch completes 5% fewer requests


def timed(rows: list[dict], slow_first: bool = False) -> list[dict]:
    """Give each window a start 2 s after the one before (seq order) and a clock reading; optionally slow the first 30 s."""
    windows = sorted((r for r in rows if r.get("type") == "window"), key=lambda r: r["seq"])
    at = {w["seq"]: T0 + timedelta(seconds=2 * i) for i, w in enumerate(windows)}
    out = []
    for r in rows:
        if r.get("type") == "window":
            r = json.loads(json.dumps(r))
            r["started"] = at[r["seq"]].strftime("%Y-%m-%dT%H:%M:%S%z")
            r["clock"] = {"mhz": 3175.0}
            if slow_first and (at[r["seq"]] - T0).total_seconds() <= RR.START_S:
                r["generator"]["measure"]["completed"] = int(r["generator"]["measure"]["completed"] * SLOW)
        out.append(r)
    return out


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.plans = self.dir / "plans"
        self.plans.mkdir()
        self.rr, self.aa = plan_dict(), plan_dict(("v2", "v2"), ("v2", "v2"))
        for name, plan in (("rr-L.json", self.rr), ("rr-aa-L.json", self.aa)):
            (self.plans / name).write_text(json.dumps(plan))
        self.job = self.dir / "job-l"
        (self.job / "out").mkdir(parents=True)
        (self.job / "record.json").write_text(json.dumps({
            "start_state": {"uptime_s": 123.4}, "command_start": "2026-01-02T03:04:00.000+02:00",
            "command_end": "2026-01-02T03:14:30.500+02:00"}))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_job(self, aa_rows: list[dict], rr_rows: list[dict]) -> Path:
        for name, rows in (("aa.jsonl", aa_rows), ("rr.jsonl", rr_rows)):
            (self.job / "out" / name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        analysis = {"systems": {"linux": {k: R.analyse(rows, k) for k, rows in (("aa", aa_rows), ("rr", rr_rows))}}}
        inputs = [{"system": "linux", "job": "job-l", "file": f"out/{k}.jsonl",
                   "sha256": hashlib.sha256((self.job / "out" / f"{k}.jsonl").read_bytes()).hexdigest()}
                  for k in ("aa", "rr")]
        path = self.dir / "floor-L.json"
        path.write_text(json.dumps({"inputs": inputs, "analysis": analysis}))
        return path

    def build(self, *analysis: Path) -> dict:
        return RR.build(list(analysis), [self.job], self.plans)


class FactsTests(Fixture):
    def test_windows_job_facts_and_the_round_that_sets_the_floor(self) -> None:
        aa = timed(record(self.aa, status={3: "invalid"}, reruns=[("mixed-disjoint/m1000/t111", 2)]))
        result = self.build(self.write_job(aa, timed(record(self.rr))))
        got = {r["kind"]: r for r in result["records"]}
        windows = len([r for r in aa if r.get("type") == "window"])
        self.assertEqual(got["aa"]["windows"]["by_status"], {"invalid": 1, "valid": windows - 1})
        self.assertEqual(got["aa"]["windows"]["rerun_rounds"], 1)
        self.assertEqual(got["aa"]["job_record"], {"uptime_s": 123.4, "duration_s": 630.5})
        best = got["aa"]["floor_rounds"]["mixed-disjoint/m1000/t111"]["mserver"]
        d = R.analyse(aa, "aa")["cells"]["mixed-disjoint/m1000/t111"]["programs"]["mserver"]["d_ns"]
        self.assertAlmostEqual(abs(best["d_ns"]), max(abs(d["min"]), abs(d["max"])))
        self.assertNotIn("floor_rounds", got["rr"])

    def test_the_floors_round_is_the_counted_one_with_the_largest_gap_and_its_start(self) -> None:
        cell = "mixed-disjoint/m1000/t111"
        aa = timed(record(self.aa, reruns=[(cell, 2)]))
        for w in (r for r in aa if r.get("type") == "window" and r["cell"] == cell and r["program"] == "mserver"
                  and r["entry"] == 0):
            if w["round"] == 2 and not w.get("rerun"):     # replaced by the rerun: must be ignored
                w["generator"]["measure"]["completed"] //= 2
            if w["round"] == 3:
                w["generator"]["measure"]["completed"] = int(w["generator"]["measure"]["completed"] * 0.9)
        result = self.build(self.write_job(aa, timed(record(self.rr))))
        best = next(r for r in result["records"] if r["kind"] == "aa")["floor_rounds"][cell]["mserver"]
        self.assertEqual(best["round"], 3)
        pair = [w for w in aa if w.get("type") == "window" and w["cell"] == cell and w["program"] == "mserver"
                and w["round"] == 3]
        t0 = min(RR.started(w) for w in aa if w.get("type") == "window")
        self.assertEqual(best["offset_s"], max((RR.started(w) - t0).total_seconds() for w in pair))

    def test_main_writes_the_records_with_a_plans_folder(self) -> None:
        path = self.write_job(timed(record(self.aa)), timed(record(self.rr)))
        out = self.dir / "records.json"
        rc = RR.main(["--analysis", str(path), "--jobs", str(self.job), "--out", str(out), "--plans", str(self.plans)])
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(out.read_text())["records"]), 2)

    def test_a_missing_lab_record_is_a_refusal(self) -> None:
        path = self.write_job(timed(record(self.aa)), timed(record(self.rr)))
        (self.job / "record.json").unlink()
        with self.assertRaisesRegex(RR.RecordsError, "FileNotFoundError"):
            self.build(path)

    def test_the_start_check_finds_a_slow_first_stretch_against_the_campaign(self) -> None:
        aa = timed(record(self.aa), slow_first=True)
        result = self.build(self.write_job(aa, timed(record(self.rr))))
        start = next(r for r in result["records"] if r["kind"] == "aa")["start"]
        self.assertEqual(start["first_windows"], RR.START_S // 2 + 1)
        lo, hi = start["first_pct"]
        self.assertGreater(lo, 4.5)    # 1 / 0.95 = +5.26%, give or take the made-up counts' 0.3%
        self.assertLess(hi, 6.0)
        self.assertLess(max(map(abs, start["later_pct"])), 1.0)
        self.assertEqual(start["first_clock_mhz"], [3175.0, 3175.0])
        self.assertEqual(start["first_others_max_pct"], 0.5)


class RefusalTests(Fixture):
    def test_a_record_whose_sha256_differs_is_refused(self) -> None:
        path = self.write_job(timed(record(self.aa)), timed(record(self.rr)))
        with (self.job / "out" / "rr.jsonl").open("a") as f:
            f.write("\n")
        with self.assertRaisesRegex(RR.RecordsError, "sha256"):
            self.build(path)
        out = self.dir / "records.json"
        with contextlib.redirect_stderr(io.StringIO()):
            rc = RR.main(["--analysis", str(path), "--jobs", str(self.job), "--out", str(out), "--plans", str(self.plans)])
        self.assertEqual(rc, 2)
        self.assertFalse(out.exists())

    def test_a_record_listed_twice_is_refused(self) -> None:
        path = self.write_job(timed(record(self.aa)), timed(record(self.rr)))
        with self.assertRaisesRegex(RR.RecordsError, "listed twice"):
            self.build(path, path)

    def test_a_floor_that_is_not_the_analysis_files_is_refused(self) -> None:
        path = self.write_job(timed(record(self.aa)), timed(record(self.rr)))
        wrapped = json.loads(path.read_text())
        wrapped["analysis"]["systems"]["linux"]["aa"]["cells"]["mixed-disjoint/m1000/t111"]["programs"]["mserver"][
            "d_ns"]["min"] = -1e6
        path.write_text(json.dumps(wrapped))
        with self.assertRaisesRegex(RR.RecordsError, "largest"):
            self.build(path)

    def test_a_plan_that_is_not_the_committed_one_is_refused(self) -> None:
        path = self.write_job(timed(record(self.aa)), timed(record(self.rr)))
        with self.assertRaisesRegex(RR.RecordsError, "committed"):
            RR.build([path], [self.job])   # the committed plans folder holds no synthetic plan


if __name__ == "__main__":
    unittest.main(verbosity=1)
