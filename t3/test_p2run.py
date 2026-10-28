#!/usr/bin/env python3
"""Tests of t3/p2run.py. Untimed: nothing here runs the runner's timed mode, and no assertion or
printout looks at a time, a rate or a latency of any program.

    python t3/test_p2run.py          (or: python -m pytest t3/test_p2run.py)

Pure parts (mirrored order, window sequence, plan parsing, validity rules on synthetic values,
the parsers of /proc/stat, /proc/cpuinfo and the Windows per-CPU counters) are tested directly.
The orchestration (spawn with affinity, the probe, the stop, the rows, the preflight) runs in
count mode against two small stand-in programs written to a temporary folder: a server that
answers GET / with the 13 bytes, and a generator that writes a count-mode result. The sampler
tests only check the structure of what the host returns, on the host they run on.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import p2run  # noqa: E402
from p2run import Observed, PlanError, Reading, Thresholds, judge  # noqa: E402

TH = Thresholds()


def plan_dict(**over) -> dict:
    base = {"p2gen": "p2gen", "data_root": "sets", "shapes": ["mixed-disjoint"], "sizes": [10],
            "pairs": [[111, 211]], "cpus": {"server": 14, "generator": "2-13"},
            "programs": [{"name": "mserver", "path": "mserver", "arms": ["v2", "null"]}]}
    base.update(over)
    return base


# ---------------------------------------------------------------- CPU lists, plan, sequence


class CpuListTests(unittest.TestCase):
    def test_forms(self) -> None:
        self.assertEqual(p2run.parse_cpu_list(14), (14,))
        self.assertEqual(p2run.parse_cpu_list("2-5"), (2, 3, 4, 5))
        self.assertEqual(p2run.parse_cpu_list("0,2-3,9"), (0, 2, 3, 9))
        self.assertEqual(p2run.parse_cpu_list([4, "1-2"]), (4, 1, 2))

    def test_bad(self) -> None:
        for bad in ("", "a", "2-", "-3", [], [1, 1], "1,1", -1, True, 1.5, None):
            with self.assertRaises(PlanError, msg=repr(bad)):
                p2run.parse_cpu_list(bad)

    def test_masks(self) -> None:
        self.assertEqual(p2run.cpus_to_mask((0, 2, 14)), 0b100000000000101)
        self.assertEqual(p2run.mask_to_cpus(0b100000000000101), (0, 2, 14))
        self.assertEqual(p2run.mask_to_cpus(0), ())


class PlanTests(unittest.TestCase):
    def test_defaults(self) -> None:
        p = p2run.parse_plan(plan_dict())
        self.assertEqual((p.connections, p.warmup_s, p.window_s, p.ready_timeout_s), (64, 1.0, 5.0, 60.0))
        self.assertEqual(p.thresholds, Thresholds(0.001, 90.0, 0.02))
        self.assertEqual((p.server_cpu, p.generator_cpus), (14, tuple(range(2, 14))))
        self.assertEqual(p.generator_threads, 12)
        self.assertIsNone(p.session_clock_mhz)
        self.assertEqual(p.programs[0].version, "router-list")  # the stem is mserver

    def test_versions_by_stem_and_override(self) -> None:
        p = p2run.parse_plan(plan_dict(programs=[
            {"path": "/x/mserver-go", "arms": ["gin"]}, {"path": ["python", "s.py"], "name": "fake", "arms": ["a"],
                                                           "version": "startup-line"}]))
        self.assertEqual([x.version for x in p.programs], ["startup-line", "startup-line"])
        self.assertEqual(p.programs[0].name, "mserver-go")
        self.assertEqual(p.programs[1].argv, ("python", "s.py"))

    def test_the_others_guard_and_reruns_are_off_unless_the_plan_sets_them(self) -> None:
        p = p2run.parse_plan(plan_dict())
        self.assertEqual((p.thresholds.others_max_pct, p.rerun_host_faults), (None, False))
        p = p2run.parse_plan(plan_dict(others_max_pct=10, rerun_host_faults=True))
        self.assertEqual((p.thresholds.others_max_pct, p.rerun_host_faults), (10.0, True))
        self.assertIn("others_max_pct", p2run.TIME_KEYS)  # a timed-mode threshold, left out of a count-mode session

    def test_the_round_robin_schedule_and_its_keys(self) -> None:
        p = p2run.parse_plan(plan_dict())
        self.assertEqual((p.schedule, p.round_robin, p.rounds, p.server_warmup_s), ("mirrored", False, 0, 1.0))
        p = p2run.parse_plan(plan_dict(schedule="round-robin", rounds=7, order_seed=2026, server_warmup_s=0.5))
        self.assertEqual((p.schedule, p.round_robin, p.rounds, p.order_seed, p.server_warmup_s),
                         ("round-robin", True, 7, 2026, 0.5))
        self.assertIn("server_warmup_s", p2run.TIME_KEYS)
        for bad in (dict(schedule="interleaved"), dict(rounds=7), dict(order_seed=1),  # mirrored plans name neither
                    dict(schedule="round-robin", rounds=7), dict(schedule="round-robin", order_seed=1),
                    dict(schedule="round-robin", rounds=0, order_seed=1), dict(schedule="round-robin", rounds=2.5, order_seed=1),
                    dict(schedule="round-robin", rounds=7, order_seed=True), dict(schedule="round-robin", rounds=7, order_seed="1"),
                    dict(server_warmup_s=0), dict(server_warmup_s=4000)):
            with self.assertRaises(PlanError, msg=repr(bad)):
                p2run.parse_plan(plan_dict(**bad))

    def test_housekeeping(self) -> None:
        self.assertEqual(p2run.parse_plan(plan_dict()).housekeeping_cpus, ())
        self.assertEqual(p2run.parse_plan(plan_dict(housekeeping_cpus="0-1")).housekeeping_cpus, (0, 1))

    def test_paths_become_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "prog.py").write_text("")
            (Path(tmp) / "lib.dll").write_text("")
            here = os.getcwd()
            os.chdir(tmp)
            try:
                p = p2run.parse_plan(plan_dict(
                    data_root="rel/sets", p2gen="./gen",
                    programs=[{"name": "f", "path": ["python", "prog.py"], "arms": ["a"], "env": {"LIB": "lib.dll", "X": "1"}}]))
            finally:
                os.chdir(here)
            self.assertTrue(Path(p.data_root).is_absolute())
            self.assertTrue(Path(p.p2gen[0]).is_absolute())
            self.assertEqual(p.programs[0].argv, ("python", str((Path(tmp) / "prog.py").resolve())))
            self.assertEqual(p.programs[0].binary, str((Path(tmp) / "prog.py").resolve()))
            self.assertEqual(dict(p.programs[0].env), {"LIB": str((Path(tmp) / "lib.dll").resolve()), "X": "1"})

    def test_underscore_keys_ignored(self) -> None:
        d = plan_dict(_comment="x")
        d["programs"][0]["_why"] = "y"
        p2run.parse_plan(d)

    def test_rejects(self) -> None:
        bad = [
            plan_dict(typo=1),
            {k: v for k, v in plan_dict().items() if k != "sizes"},
            plan_dict(sizes=[]), plan_dict(sizes=[10, 10]), plan_dict(sizes=[0]),
            plan_dict(shapes=[]), plan_dict(pairs=[111]), plan_dict(pairs=[[111, 211], [111, 211]]),
            plan_dict(pairs=[[111]]), plan_dict(connections=0), plan_dict(connections=1.5),
            plan_dict(window_s=0), plan_dict(warmup_s=-1), plan_dict(verify_sets="yes"),
            plan_dict(cpus={"server": 2, "generator": "2-13"}),
            plan_dict(cpus={"server": [1, 2], "generator": "3"}),
            plan_dict(cpus={"server": 1}),
            plan_dict(housekeeping_cpus="2"), plan_dict(housekeeping_cpus=14), plan_dict(housekeeping_cpus=[]),
            plan_dict(pairs=[[111, 211], [111, 212]]),  # a cell is named by its table seed
            plan_dict(cpus={"server": 1, "generator": "5-3"}),
            plan_dict(connections=4), plan_dict(threads=65), plan_dict(timeout_ms=700_000), plan_dict(window_s=4000),
            plan_dict(warmup_s=float("inf")), plan_dict(error_share_max=float("nan")),
            plan_dict(abort_after_consecutive=-1),
            plan_dict(others_max_pct=-1), plan_dict(others_max_pct="10"), plan_dict(others_max_pct=True),
            plan_dict(rerun_host_faults=1), plan_dict(rerun_host_faults="yes"),
            plan_dict(programs=[{"path": "/b1/mserver", "arms": ["a"], "name": "x"},
                                {"path": "/b2/mserver", "arms": ["b"], "name": "y"}]),  # two binaries, one program
            plan_dict(programs=[{"path": "/b1/mserver", "arms": ["a"], "name": "x"},
                                {"path": "/b1/mserver", "arms": ["b"], "name": "y"}]),  # one binary twice
            plan_dict(programs=[{"path": "/b/mserver", "arms": [{"name": "v2", "path": "/other/mserver"}]}]),
            plan_dict(programs=[]),
            plan_dict(programs=[{"path": "a", "arms": []}]),
            plan_dict(programs=[{"path": "a", "arms": ["x", "x", "x"]}]),  # one name twice only (A/A)
            plan_dict(programs=[{"path": "a", "arms": ["x"], "extra": 1}]),
            plan_dict(programs=[{"path": "a", "arms": ["x"], "env": {"A": 1}}]),
            plan_dict(programs=[{"path": "a", "arms": ["x"], "version": "?"}]),
            plan_dict(programs=[{"path": "a", "arms": ["x"]}, {"path": "b/a", "arms": ["y"]}]),
            [], "text",
        ]
        for d in bad:
            with self.assertRaises(PlanError, msg=repr(d)[:120]):
                p2run.parse_plan(d)

    def test_example_plan(self) -> None:
        plan, _ = p2run.load_plan(HERE / "plans" / "example.json")
        self.assertEqual(p2run.total_windows(plan), 2 * 5 * 16 * (2 * 11 + 2 * 6 + 2 * 5))
        self.assertEqual(sum(1 for _ in p2run.windows(plan)), p2run.total_windows(plan))
        self.assertEqual((plan.server_cpu, plan.generator_cpus), (14, tuple(range(2, 14))))


class SequenceTests(unittest.TestCase):
    def test_mirrored(self) -> None:
        self.assertEqual(p2run.mirrored(["a", "b", "c"]), ("a", "b", "c", "c", "b", "a"))
        self.assertEqual(p2run.mirrored(["a"]), ("a", "a"))
        with self.assertRaises(PlanError):
            p2run.mirrored([])

    def test_an_aa_round_holds_one_arm_twice_and_names_its_entries(self) -> None:
        plan = p2run.parse_plan(plan_dict(programs=[{"name": "p", "path": "p", "arms": ["v2", "v2"]}]))
        ws = list(p2run.windows(plan))
        self.assertEqual([(w.arm, w.index, w.entry) for w in ws], [("v2", 0, 0), ("v2", 1, 1), ("v2", 2, 1), ("v2", 3, 0)])
        for arms in (["v2", "v2", "v2"], ["v2", "crow", "v2"], ["v2", "crow", "crow"]):
            with self.assertRaisesRegex(PlanError, "one name twice"):
                p2run.parse_plan(plan_dict(programs=[{"name": "p", "path": "p", "arms": arms}]))

    def test_entries_of_distinct_arms_are_their_positions(self) -> None:
        plan = p2run.parse_plan(plan_dict(programs=[{"name": "p", "path": "p", "arms": ["a", "b", "c"]}]))
        self.assertEqual([(w.arm, w.entry) for w in p2run.windows(plan)],
                         [("a", 0), ("b", 1), ("c", 2), ("c", 2), ("b", 1), ("a", 0)])

    def test_order_and_count(self) -> None:
        plan = p2run.parse_plan(plan_dict(
            shapes=["s1", "s2"], sizes=[10, 100], pairs=[[1, 101], [2, 102]],
            programs=[{"name": "p", "path": "p", "arms": ["a", "b"]}, {"name": "q", "path": "q", "arms": ["x"]}]))
        ws = list(p2run.windows(plan))
        self.assertEqual(len(ws), p2run.total_windows(plan))
        self.assertEqual(len(ws), 2 * 2 * 2 * (4 + 2))
        self.assertEqual([w.seq for w in ws], list(range(len(ws))))
        first_cell = [(w.program, w.arm, w.index, w.half) for w in ws[:6]]
        self.assertEqual(first_cell, [("p", "a", 0, 1), ("p", "b", 1, 1), ("p", "b", 2, 2), ("p", "a", 3, 2),
                                      ("q", "x", 0, 1), ("q", "x", 1, 2)])
        cells = []
        for w in ws:
            if not cells or cells[-1] != (w.shape, w.m, w.table_seed):
                cells.append((w.shape, w.m, w.table_seed))
        # shape outermost, then size, then pair; every cell once
        self.assertEqual(cells, [(s, m, t) for s in ("s1", "s2") for m in (10, 100) for t in (1, 2)])
        self.assertEqual(ws[0].ring_seed, 101)
        self.assertEqual(ws[0].cell, "s1/m10/t1")

    def test_every_arm_twice_per_round(self) -> None:
        plan = p2run.parse_plan(plan_dict(programs=[{"name": "p", "path": "p", "arms": ["a", "b", "c"]}]))
        arms = [w.arm for w in p2run.windows(plan)]
        self.assertEqual(sorted(arms), ["a", "a", "b", "b", "c", "c"])
        self.assertEqual(arms, arms[::-1])  # a mirrored round reads the same both ways


# ---------------------------------------------------------------- validity


def gen_line(completed=100_000, status=0, body=0, framing=0, lost=0, unsolicited=0, timeouts=0, connect=0, failed=0,
             reconnects=None, peer_closes=0):
    """p2gen's timed line. By default its reconnects are exactly what its own timeouts, connect errors and
    lost requests cause (one each)."""
    return {"measure": {"completed": completed, "errors_total": status + body + framing + lost + unsolicited + timeouts,
                        "errors": {"status": status, "body": body, "framing": framing, "lost": lost,
                                   "unsolicited": unsolicited},
                        "timeouts": timeouts, "connect_errors": connect, "peer_closes": peer_closes,
                        "reconnects": timeouts + connect + lost if reconnects is None else reconnects},
            "thread_failed": failed, "measure_wall_ns": 5_000_000_000, "connections": 64}


PROBE_OK = {"status": 200, "body_ok": True}


_DEFAULT = object()


def obs(generator=_DEFAULT, **over) -> Observed:
    """A clean timed observation; generator=None means p2gen produced no result."""
    base = dict(ready=True, probe=PROBE_OK, generator=gen_line() if generator is _DEFAULT else generator,
                generator_exit=0, server_alive_at_end=True, server_exit=0, generator_busy_pct=40.0,
                clock_mhz=3000.0, session_mhz=3000.0)
    base.update(over)
    return Observed(**base)


def codes(v) -> list[str]:
    return [c for c, _ in v.reasons]


class TimedJudgeTests(unittest.TestCase):
    def test_clean_window_is_valid(self) -> None:
        v = judge(obs(), TH)
        self.assertEqual((v.status, v.reasons, v.valid), ("valid", (), True))

    def test_error_share_boundary(self) -> None:
        # 100 of 100,000 attempts is exactly 0.1%: not above the limit
        self.assertEqual(judge(obs(gen_line(completed=99_900, timeouts=100)), TH).status, "valid")
        v = judge(obs(gen_line(completed=99_899, timeouts=101)), TH)
        self.assertEqual((v.status, codes(v)), ("overloaded", ["error_share"]))

    def test_overload_needs_only_timeouts_and_lost(self) -> None:
        self.assertEqual(judge(obs(gen_line(completed=1000, lost=50, timeouts=50)), TH).status, "overloaded")
        for kw in ({"status": 5}, {"body": 5}, {"framing": 5}, {"unsolicited": 5}):
            v = judge(obs(gen_line(completed=1000, timeouts=50, **kw)), TH)
            self.assertEqual((v.status, codes(v)), ("invalid", ["error_share"]), kw)

    def test_overload_is_not_given_when_another_rule_fails(self) -> None:
        g = gen_line(completed=1000, timeouts=50)
        for over, code in (({"generator_busy_pct": 95.0}, "generator_busy"), ({"clock_mhz": 2900.0}, "clock_drift"),
                           ({"server_exit": 3}, "server_exit")):
            v = judge(obs(g, **over), TH)
            self.assertEqual(v.status, "invalid", over)
            self.assertEqual(codes(v), ["error_share", code])

    def test_zero_completions_is_invalid_not_overloaded(self) -> None:
        v = judge(obs(gen_line(completed=0, timeouts=64)), TH)
        self.assertEqual((v.status, codes(v)), ("invalid", ["no_answers", "error_share"]))

    def test_a_crashed_server_is_not_overloaded(self) -> None:
        v = judge(obs(gen_line(completed=500, lost=64), server_alive_at_end=False, server_exit=1), TH)
        self.assertEqual((v.status, codes(v)), ("invalid", ["error_share", "server_died"]))

    def test_server_exit_code_after_the_stop(self) -> None:
        v = judge(obs(server_exit=-9), TH)
        self.assertEqual((v.status, codes(v)), ("invalid", ["server_exit"]))

    def test_closes_the_generator_did_not_make(self) -> None:
        self.assertEqual(codes(judge(obs(gen_line(peer_closes=1)), TH)), ["peer_closes"])
        self.assertEqual(codes(judge(obs(gen_line(reconnects=3)), TH)), ["reconnects"])
        # its own timeouts and connect errors each make one reconnect and do not count against the window
        self.assertEqual(judge(obs(gen_line(completed=100_000, timeouts=0, connect=0, reconnects=0)), TH).status, "valid")

    def test_reconnects_follow_timeouts_so_overload_survives_them(self) -> None:
        v = judge(obs(gen_line(completed=1000, timeouts=50)), TH)  # 50 reconnects, all explained
        self.assertEqual((v.status, codes(v)), ("overloaded", ["error_share"]))
        # a retry can fall across the window's edge from its timeout: up to one per connection more is allowed
        for extra in (2, 64):
            v = judge(obs(gen_line(completed=1000, timeouts=50, reconnects=50 + extra)), TH)
            self.assertEqual((v.status, codes(v)), ("overloaded", ["error_share"]), extra)
        v = judge(obs(gen_line(completed=1000, timeouts=50, reconnects=50 + 65)), TH)
        self.assertEqual((v.status, codes(v)), ("invalid", ["error_share", "reconnects"]))
        # with no error at all there is nothing to explain a reconnect, and no slack
        self.assertEqual(codes(judge(obs(gen_line(reconnects=1)), TH)), ["reconnects"])

    def test_a_line_that_lacks_a_key_is_not_read_as_zero(self) -> None:
        for path in ("measure.completed", "measure.errors_total", "measure.timeouts", "measure.connect_errors",
                     "measure.peer_closes", "measure.reconnects", "measure.errors.lost", "measure_wall_ns",
                     "thread_failed", "connections"):
            g = gen_line()
            node = g
            *parents, leaf = path.split(".")
            for k in parents:
                node = node[k]
            del node[leaf]
            v = judge(obs(g), TH)
            self.assertEqual((v.status, codes(v)), ("invalid", ["generator_schema"]), path)
        self.assertEqual(codes(judge(obs({"thread_failed": 0}), TH)), ["generator_schema"])
        for key in ("completed", "resolved", "errors_total", "thread_failed"):
            g = count_line()
            del g[key]
            v = judge(obs(g, generator_busy_pct=None, clock_mhz=None, session_mhz=None), TH, 20_000)
            self.assertEqual(codes(v), ["generator_schema"], key)

    def test_a_server_that_closes_connections_is_not_overload(self) -> None:
        v = judge(obs(gen_line(completed=1000, lost=50, peer_closes=50)), TH)
        self.assertEqual((v.status, codes(v)), ("invalid", ["error_share", "peer_closes"]))

    def test_sample_span_must_match_the_window(self) -> None:
        self.assertEqual(judge(obs(span_s=5.0), TH).status, "valid")
        self.assertEqual(judge(obs(span_s=5.05), TH).status, "valid")
        self.assertEqual(codes(judge(obs(span_s=5.06), TH)), ["sampler"])
        self.assertEqual(codes(judge(obs(span_s=4.9), TH)), ["sampler"])

    def test_generator_busy_boundary(self) -> None:
        self.assertEqual(judge(obs(generator_busy_pct=90.0), TH).status, "valid")
        self.assertEqual(codes(judge(obs(generator_busy_pct=90.01), TH)), ["generator_busy"])

    def test_clock_drift_boundary(self) -> None:
        self.assertEqual(judge(obs(clock_mhz=3060.0), TH).status, "valid")
        self.assertEqual(judge(obs(clock_mhz=2940.0), TH).status, "valid")
        self.assertEqual(codes(judge(obs(clock_mhz=3061.0), TH)), ["clock_drift"])
        self.assertEqual(codes(judge(obs(clock_mhz=2939.0), TH)), ["clock_drift"])

    def test_missing_samples_are_invalid(self) -> None:
        for over in ({"generator_busy_pct": None}, {"clock_mhz": None}, {"session_mhz": None}):
            self.assertEqual(codes(judge(obs(**over), TH)), ["sampler"], over)

    def test_busy_share_is_compared_unrounded(self) -> None:
        r = Reading(10.0, {2: 9.0004, 3: 9.0004}, 3000.0)  # 90.004 percent: rounds to 90.0, is above the limit
        self.assertEqual(round(p2run.generator_busy_pct(r, (2, 3)), 2), 90.0)
        self.assertEqual(codes(judge(obs(generator_busy_pct=p2run.generator_busy_pct(r, (2, 3))), TH)), ["generator_busy"])

    def test_probe(self) -> None:
        for probe in ({"status": 404, "body_ok": True}, {"status": 200, "body_ok": False}, {"status": 0, "body_ok": False}):
            v = judge(obs(probe=probe, generator=None, generator_exit=None), TH)
            self.assertEqual((v.status, codes(v)), ("invalid", ["probe"]), probe)

    def test_not_ready(self) -> None:
        v = judge(obs(ready=False, probe=None, generator=None, generator_exit=None, server_exit=2,
                      server_alive_at_end=False), TH)
        self.assertEqual((v.status, codes(v)), ("invalid", ["not_ready"]))

    def test_no_result(self) -> None:
        v = judge(obs(generator=None, generator_exit=1), TH)
        self.assertEqual((v.status, codes(v)), ("invalid", ["no_result"]))

    def test_connect_errors_and_failed_threads(self) -> None:
        self.assertEqual(codes(judge(obs(gen_line(connect=1)), TH)), ["connect_errors"])
        self.assertEqual(codes(judge(obs(gen_line(failed=1)), TH)), ["generator_failed"])
        self.assertEqual(codes(judge(obs(generator_exit=1), TH)), ["generator_failed"])

    def test_thresholds_come_from_the_plan(self) -> None:
        th = Thresholds(error_share_max=0.5, generator_busy_max_pct=99.0, clock_drift_max=0.1)
        v = judge(obs(gen_line(completed=100, timeouts=50), generator_busy_pct=95.0, clock_mhz=3200.0), th)
        self.assertEqual(v.status, "valid")

    def test_other_processes_are_judged_only_under_the_plans_share(self) -> None:
        self.assertEqual(judge(obs(others_pct=50.0), TH).status, "valid")
        self.assertEqual(judge(obs(others_pct=None), TH).status, "valid")
        th = Thresholds(others_max_pct=10.0)
        self.assertEqual(judge(obs(others_pct=10.0), th).status, "valid")
        self.assertEqual(judge(obs(others_pct=0.0), Thresholds(others_max_pct=0.0)).status, "valid")
        self.assertEqual(codes(judge(obs(others_pct=0.01), Thresholds(others_max_pct=0.0))), ["others"])
        self.assertEqual(codes(judge(obs(others_pct=10.01), th)), ["others"])
        for bad in (float("nan"), float("inf")):
            self.assertEqual(codes(judge(obs(others_pct=bad), th)), ["others"], bad)
        self.assertEqual(codes(judge(obs(others_pct=None), th)), ["others"])  # no record of them
        # count mode judges no sample and no other process
        v = judge(obs(count_line(), generator_busy_pct=None, clock_mhz=None, session_mhz=None, others_pct=None), th, 20_000)
        self.assertEqual(v.status, "valid")
        # the guard is checked even when the window has no CPU or clock sample
        self.assertEqual(codes(judge(obs(others_pct=None, generator_busy_pct=None), th)), ["others", "sampler"])
        # an overloaded arm in a busy host is invalid, not overloaded
        v = judge(obs(gen_line(completed=1000, timeouts=10), others_pct=20.0), th)
        self.assertEqual((v.status, codes(v)), ("invalid", ["error_share", "others"]))
        self.assertTrue({"others", "sampler"} <= p2run.SYSTEMATIC and p2run.RERUN_CODES == {"others", "sampler"})


def count_line(n=20_000, completed=None, resolved=None, errors_total=0, failed=0) -> dict:
    return {"count": n, "completed": n if completed is None else completed, "resolved": n if resolved is None else resolved,
            "errors_total": errors_total, "thread_failed": failed}


class CountJudgeTests(unittest.TestCase):
    def go(self, **over):
        generator = over.pop("generator", count_line())
        return judge(obs(generator, generator_busy_pct=None, clock_mhz=None, session_mhz=None, **over), TH, 20_000)

    def test_pass(self) -> None:
        self.assertEqual(self.go().status, "valid")

    def test_every_deviation_fails(self) -> None:
        for kw in ({"generator": count_line(completed=19_999)}, {"generator": count_line(resolved=19_999)},
                   {"generator": count_line(errors_total=1)}, {"generator": count_line(failed=1)},
                   {"generator_exit": 1}, {"server_exit": 1}, {"server_alive_at_end": False},
                   {"probe": {"status": 500, "body_ok": True}}, {"generator": None, "generator_exit": None}):
            v = self.go(**kw)
            self.assertEqual(v.status, "invalid", kw)

    def test_no_tolerance_and_no_overloaded_label(self) -> None:
        v = self.go(generator=count_line(completed=19_999, resolved=20_000, errors_total=1))
        self.assertEqual(v.status, "invalid")


# ---------------------------------------------------------------- parsers and samples


class ParserTests(unittest.TestCase):
    def test_proc_stat(self) -> None:
        text = "cpu  999 0 999 9999 0 0 0 0 0 0\ncpu0 100 10 50 1000 77 5 5 2 0 0\ncpu1 0 0 0 500 0 0 0 0 0 0\nintr 1\n"
        got = p2run.parse_proc_stat(text, 100)
        self.assertEqual(sorted(got), [0, 1])
        self.assertAlmostEqual(got[0], (100 + 10 + 50 + 5 + 5 + 2) / 100)  # not idle (1000), not iowait (77)
        self.assertEqual(got[1], 0.0)

    def test_cpuinfo(self) -> None:
        text = "processor\t: 0\ncpu MHz\t\t: 3000.5\n\nprocessor\t: 1\ncpu MHz\t\t: 3100.0\n\nprocessor\t: 2\ncpu MHz\t\t: 1.0\n"
        self.assertEqual(p2run.parse_cpuinfo_mhz(text, [0, 1]), [3000.5, 3100.0])
        self.assertEqual(p2run.parse_cpuinfo_mhz(text, [7]), [])

    def test_processor_performance(self) -> None:
        def entry(idle, kernel, user):  # kernel includes idle
            return struct.pack("<5qIi", idle, kernel, user, 0, 0, 0, 0)

        raw = entry(8 * 10**7, 10 * 10**7, 3 * 10**7) + entry(10**7, 10**7, 0)
        self.assertEqual(len(raw), 96)
        got = p2run.parse_processor_performance(raw, 2)
        self.assertAlmostEqual(got[0], 5.0)  # (10 + 3 - 8) s
        self.assertAlmostEqual(got[1], 0.0)

    def test_cpu_metrics(self) -> None:
        r = Reading(span_s=2.0, busy_s={14: 1.9, 2: 0.2, 3: 1.0}, mhz=3000.0)
        m = p2run.cpu_metrics(r, 14, (2, 3))
        self.assertEqual(m["server_busy_pct"], 95.0)
        self.assertEqual(m["generator_busy_pct"], 30.0)
        self.assertEqual(m["generator_busy_max_cpu_pct"], 50.0)
        self.assertEqual(m["busy_pct_by_cpu"], {"2": 10.0, "3": 50.0, "14": 95.0})


class SamplerStructureTests(unittest.TestCase):
    """Structure only: the values are never printed or compared with a limit."""

    def check(self, sampler, cpus) -> None:
        sampler.begin()
        time.sleep(0.3)  # PDH's rate counters need an interval; the length is not examined
        r = sampler.end()
        self.assertEqual(sorted(r.busy_s), sorted(cpus))
        self.assertTrue(all(isinstance(v, float) and v >= 0.0 for v in r.busy_s.values()))
        self.assertIsInstance(r.mhz, float)
        self.assertGreater(r.mhz, 0.0)
        self.assertGreater(r.span_s, 0.0)
        with mock.patch.object(p2run, "SESSION_CLOCK_SAMPLES", 1), mock.patch.object(p2run, "SESSION_CLOCK_GAP_S", 0.05), \
                mock.patch.object(p2run, "SESSION_CLOCK_PDH_S", 0.3):
            session = sampler.session_mhz()
        self.assertEqual(len(session), 1)
        self.assertGreater(session[0], 0.0)
        if p2run.IS_WINDOWS:  # how many measured CPUs had PDH data, and over how long
            self.assertTrue(1 <= sampler.session_counted <= len(cpus))
            self.assertGreater(sampler.session_interval_s, 0.0)
        sampler.close()

    def test_this_host(self) -> None:
        if os.cpu_count() < 2:
            self.skipTest("needs two CPUs")
        try:
            sampler = p2run.HOST.make_sampler((0, 1))
        except OSError as e:  # a host without the counters (a container without /proc/cpuinfo MHz)
            self.skipTest(f"no counters here: {e}")
        self.check(sampler, (0, 1))


# ---------------------------------------------------------------- marker reader, commands


class MarkerReaderTests(unittest.TestCase):
    def test_hooks_run_in_order_and_lines_are_kept(self) -> None:
        events: list[str] = []
        script = ("print('MEASURE_START 1', flush=True); print('midway', flush=True); "
                  "print('MEASURE_END 2', flush=True); print('{}', flush=True)")
        proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE)
        reader = p2run.MarkerReader(proc.stdout, lambda: events.append("start"), lambda: events.append("end"))
        reader.start()
        proc.wait(timeout=60)
        reader.join(10)
        proc.stdout.close()
        self.assertEqual(events, ["start", "end"])
        self.assertEqual(reader.lines, ["MEASURE_START 1", "midway", "MEASURE_END 2", "{}"])
        self.assertEqual(reader.errors, [])

    def test_a_failing_hook_is_recorded_and_the_pipe_is_still_drained(self) -> None:
        def boom() -> None:
            raise RuntimeError("no counters")

        proc = subprocess.Popen([sys.executable, "-c", "print('MEASURE_START 1', flush=True); print('after')"],
                                stdout=subprocess.PIPE)
        reader = p2run.MarkerReader(proc.stdout, boom, None)
        reader.start()
        proc.wait(timeout=60)
        reader.join(10)
        proc.stdout.close()
        self.assertEqual(reader.lines, ["MEASURE_START 1", "after"])
        self.assertEqual(len(reader.errors), 1)
        self.assertIn("MEASURE_START", reader.errors[0])


class CommandTests(unittest.TestCase):
    def runner(self, count):
        plan = p2run.parse_plan(plan_dict(p2gen="/bin/p2gen", warmup_s=1, window_s=5, timeout_ms=800, connections=64))
        return p2run.Runner(plan, Path("w"), count, None, None)

    def test_timed_command(self) -> None:
        cmd = self.runner(None)._generator_cmd(5555, Path("cell"), Path("r.json"))
        self.assertEqual(cmd[0], str(Path("/bin/p2gen").resolve()))
        for pair in (("--port", "5555"), ("--paths", str(Path("cell") / "ring.txt")), ("--connections", "64"),
                     ("--threads", "12"), ("--cpus", "2,3,4,5,6,7,8,9,10,11,12,13"), ("--timeout-ms", "800"),
                     ("--warmup", "1.0"), ("--duration", "5.0"), ("--out", "r.json")):
            i = cmd.index(pair[0])
            self.assertEqual(cmd[i + 1], pair[1])
        self.assertNotIn("--count", cmd)

    def test_count_command_has_no_window(self) -> None:
        cmd = self.runner(20000)._generator_cmd(5555, Path("cell"), Path("r.json"))
        self.assertEqual(cmd[cmd.index("--count") + 1], "20000")
        self.assertNotIn("--warmup", cmd)
        self.assertNotIn("--duration", cmd)


class FakeSampler:
    def begin(self) -> None:
        pass

    def end(self) -> Reading:
        return Reading(5.0, {0: 1.0}, 3000.0)


class FakeLabrec:
    """lab/laptop's labrec, as far as p2run uses it: the excluded ids are left out, as labrec does."""
    SVC = {"name": "svc", "pid": 40, "cpu_percent": 3.5, "how": "both"}
    UPD = {"name": "upd", "pid": 41, "cpu_percent": 1.25, "how": "started"}

    def __init__(self) -> None:
        self.excluded: list = []

    def processes(self) -> list:
        return [{"pid": 1}]

    def process_shares(self, start: list, end: list, wall_s: float, exclude_pids=()) -> dict:
        self.excluded.append(exclude_pids)
        me = {"name": "me", "pid": os.getpid(), "cpu_percent": 9.0, "how": "both"}
        idle = {"name": "quiet", "pid": 42, "cpu_percent": 0.0, "how": "both"}
        return {"judged": [p for p in (me, self.SVC, self.UPD, idle) if p["pid"] not in exclude_pids],
                "unattributed": [{"name": "gone", "pid": 43, "how": "gone"}]}


class TimedPartsTests(unittest.TestCase):
    """The timed mode's pieces, one by one on synthetic values. No timed window runs here."""

    def runner(self, session=3000.0):
        return p2run.Runner(p2run.parse_plan(plan_dict()), Path("w"), None, None, session)

    def test_a_reading_becomes_cpu_and_clock_fields(self) -> None:
        row: dict = {}
        reading = Reading(5.0, {14: 4.9, **{c: 1.0 for c in range(2, 14)}}, 3030.0)
        o = self.runner()._observed(True, PROBE_OK, gen_line(), 0, True, 0, reading, row)
        self.assertEqual(o.generator_busy_pct, 20.0)
        self.assertEqual(row["cpu"]["server_busy_pct"], 98.0)
        self.assertEqual(row["clock"], {"mhz": 3030.0, "session_mhz": 3000.0, "drift": 0.01})
        self.assertEqual(judge(o, TH).status, "valid")

    def test_the_others_record_reaches_the_verdict(self) -> None:
        for row, want in (({"others": {"sum_pct_of_one_cpu": 12.5}}, 12.5), ({"others_errors": ["x"]}, None),
                          ({"others": {"sum_pct_of_one_cpu": True}}, None)):
            reading = Reading(5.0, {c: 1.0 for c in range(2, 15)}, 3000.0)
            o = self.runner()._observed(True, PROBE_OK, gen_line(), 0, True, 0, reading, row)
            self.assertEqual(o.others_pct, want, row)

    def test_a_failed_sampler_hook_leaves_no_sample(self) -> None:
        class Broken:
            def begin(self):
                raise OSError("no counters")

            def end(self):
                raise RuntimeError("never")

        with tempfile.TemporaryDirectory() as tmp:
            if os.cpu_count() < 2:
                self.skipTest("needs two CPUs")
            plan = p2run.parse_plan(plan_dict(cpus={"server": os.cpu_count() - 1, "generator": "0"}))
            runner = p2run.Runner(plan, Path(tmp), None, Broken(), 3000.0)
            row: dict = {}
            window = next(p2run.windows(plan))
            out = Path(tmp) / "r.json"
            out.write_text("{}")
            # the generator stand-in prints the markers and exits; both hooks fail; the window has no sample
            with mock.patch.object(runner, "_generator_cmd", return_value=[sys.executable, "-c",
                                   "print('MEASURE_START 1', flush=True); print('MEASURE_END 2', flush=True)"]):
                cell = Path(tmp)
                parsed, code, reading = runner._run_generator(window, row, 1, cell)
        self.assertIsNone(reading)
        self.assertEqual(len(row["sampler_errors"]), 2)

    def generator_run(self, runner: Any) -> dict:
        """_run_generator with a stand-in p2gen that prints its markers and exits."""
        with tempfile.TemporaryDirectory() as tmp:
            runner.workdir = Path(tmp)
            row: dict = {}
            with mock.patch.object(runner, "_generator_cmd", return_value=[sys.executable, "-c",
                                   "print('MEASURE_START 1', flush=True); print('MEASURE_END 2', flush=True)"]):
                runner._run_generator(next(p2run.windows(runner.plan)), row, 1, Path(tmp))
        return row

    def test_others_holds_every_other_process_but_the_runners_own(self) -> None:
        if os.cpu_count() < 2:
            self.skipTest("needs two CPUs")
        lab = FakeLabrec()
        plan = p2run.parse_plan(plan_dict(cpus={"server": os.cpu_count() - 1, "generator": "0"}))
        row = self.generator_run(p2run.Runner(plan, Path("w"), None, FakeSampler(), 3000.0, lab))
        excluded = lab.excluded[0]
        self.assertEqual((len(lab.excluded), excluded[0], len(excluded)), (1, os.getpid(), 2))  # the runner, p2gen
        others = row["others"]
        self.assertEqual({k: v for k, v in others.items() if k != "wall_s"},
                         {"sum_pct_of_one_cpu": 4.75, "judged": 3, "unattributed": 1,
                          "top": [FakeLabrec.SVC, FakeLabrec.UPD], "started": [FakeLabrec.UPD]})

    def test_idle_servers_are_kept_apart_from_the_others(self) -> None:
        idle = {40: {"program": "mserver", "arm": "crow", "entry": 1}, 77: {"program": "mserver", "arm": "null", "entry": 2}}
        row = p2run.others_row(FakeLabrec(), [], [], 5.0, (os.getpid(),), idle)
        self.assertEqual((row["sum_pct_of_one_cpu"], row["judged"], row["top"]), (1.25, 2, [FakeLabrec.UPD]))
        self.assertEqual(row["idle_servers"], {"sum_pct_of_one_cpu": 3.5, "max_pct_of_one_cpu": 3.5,
                                               "servers": [{**idle[40], "cpu_percent": 3.5}], "missing": [idle[77]]})
        self.assertNotIn("idle_servers", p2run.others_row(FakeLabrec(), [], [], 5.0, (os.getpid(),)))

    def test_a_failed_others_record_leaves_the_window_as_it_was(self) -> None:
        if os.cpu_count() < 2:
            self.skipTest("needs two CPUs")
        lab = FakeLabrec()
        lab.process_shares = mock.Mock(side_effect=KeyError("how"))
        plan = p2run.parse_plan(plan_dict(cpus={"server": os.cpu_count() - 1, "generator": "0"}))
        row = self.generator_run(p2run.Runner(plan, Path("w"), None, FakeSampler(), 3000.0, lab))
        self.assertNotIn("others", row)
        self.assertEqual((row["others_errors"], row["generator_exit"]), (["KeyError('how')"], 0))

    def test_others_is_left_out_in_count_mode_and_a_failed_snapshot_is_kept(self) -> None:
        plan = p2run.parse_plan(plan_dict())
        self.assertIsNone(p2run.Runner(plan, Path("w"), 100, None, None, FakeLabrec())._processes({}))
        self.assertIsNone(p2run.Runner(plan, Path("w"), None, None, 3000.0)._processes({}))
        lab, row = FakeLabrec(), {}
        lab.processes = mock.Mock(side_effect=OSError("denied"))
        self.assertIsNone(p2run.Runner(plan, Path("w"), None, None, 3000.0, lab)._processes(row))
        self.assertEqual(row, {"others_errors": ["OSError('denied')"]})

    def test_labrec_comes_from_lab_tools_or_the_timed_run_is_refused(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "LAB_TOOLS"}
        with mock.patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(PlanError, "LAB_TOOLS"):
            p2run.load_labrec()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"LAB_TOOLS": tmp}):
            with self.assertRaisesRegex(PlanError, "LAB_TOOLS"):
                p2run.load_labrec()
            lab = Path(tmp) / "labrec.py"
            lab.write_text("raise ImportError('broken')\n")
            with self.assertRaisesRegex(PlanError, "does not import"):
                p2run.load_labrec()
            lab.write_text("def processes():\n    return []\n")
            with self.assertRaisesRegex(PlanError, "process_shares"):
                p2run.load_labrec()
            lab.write_text("def processes():\n    return []\n\n\ndef process_shares(*a, **k):\n    return {}\n")
            self.assertEqual(p2run.load_labrec().processes(), [])

    def test_the_session_line_names_the_lab_job_and_labrec(self) -> None:
        plan = p2run.parse_plan(plan_dict(programs=[
            {"name": "p", "path": [sys.executable, "-c", "pass"], "arms": ["a"], "version": "startup-line"}]))
        smoke = {"p": [{"arm": "a", "lines": ["up"], "ready": True}]}
        lab = mock.Mock(__file__=str(Path(p2run.__file__)))
        with mock.patch.dict(os.environ, {"LAB_JOB_ID": "j1", "LAB_QUIET": "passed:j1"}):
            line = p2run.session_line(plan, json.dumps(plan_dict()).encode(), None, {"session_mhz": 1.0}, smoke, lab)
        self.assertEqual(line["lab"], {"job_id": "j1", "quiet": "passed:j1",
                                       "labrec_sha256": p2run.sha256_file(Path(p2run.__file__))})

    def test_samplers_forget_a_start_that_failed(self) -> None:
        if os.cpu_count() < 2:
            self.skipTest("needs two CPUs")
        s = p2run.HOST.make_sampler((0, 1))
        with self.assertRaises(RuntimeError):
            s.end()
        s.begin()
        if p2run.IS_WINDOWS:
            try:
                s.end()
            except OSError as e:  # a span this short can hold no PDH clock data at all (pdh_mean_mhz)
                self.assertIn("no measured CPU", str(e))
        else:
            s.end()
        with self.assertRaises(RuntimeError):  # a second end() would reuse the first window's start
            s.end()
        s.close()

    def test_pdh_clock_leaves_out_cpus_without_data(self) -> None:
        perf = {"0,2": 99.2, "0,3": 0.0, "0,4": 99.2, "0,14": 99.2}
        freq = {"0,2": 3201.0, "0,3": 3201.0, "0,4": 0.0, "0,14": 3201.0}
        mhz, counted = p2run.pdh_mean_mhz(perf, freq, (2, 3, 4, 14))
        self.assertEqual((round(mhz, 1), counted), (3175.4, 2))
        with self.assertRaisesRegex(OSError, "no measured CPU"):
            p2run.pdh_mean_mhz({"0,2": 0.0}, {"0,2": 3201.0}, (2,))
        with self.assertRaisesRegex(OSError, "no % Processor Performance"):
            p2run.pdh_mean_mhz(perf, freq, (2, 5))

    def test_the_counted_cpus_go_into_the_window_and_the_session(self) -> None:
        row: dict = {}
        reading = Reading(5.0, {14: 4.9, **{c: 1.0 for c in range(2, 14)}}, 3175.4, 13)
        self.runner(3175.0)._observed(True, PROBE_OK, gen_line(), 0, True, 0, reading, row)
        self.assertEqual(row["clock"]["cpus_counted"], 13)

        class Fake:
            session_counted, session_interval_s = 11, 10.0004

            def session_mhz(self):
                return [3175.0]

        got = p2run.session_clock(p2run.parse_plan(plan_dict()), Fake())
        self.assertEqual((got["session_mhz"], got["cpus_counted"], got["interval_s"]), (3175.0, 11, 10.0))

    def test_no_reading_is_a_sampler_failure(self) -> None:
        row: dict = {}
        o = self.runner()._observed(True, PROBE_OK, gen_line(), 0, True, 0, None, row)
        self.assertNotIn("cpu", row)
        self.assertEqual(codes(judge(o, TH)), ["sampler"])

    def test_session_clock_from_the_plan_or_from_samples(self) -> None:
        fixed = p2run.parse_plan(plan_dict(session_clock_mhz=3176.0))
        self.assertEqual(p2run.session_clock(fixed, None), {"session_mhz": 3176.0, "source": "plan"})

        class Fake:
            def session_mhz(self):
                return [3000.0, 3010.0, 2990.0, 3000.0]

        got = p2run.session_clock(p2run.parse_plan(plan_dict()), Fake())
        self.assertEqual((got["session_mhz"], got["source"]), (3000.0, "sampled at the session start"))
        self.assertEqual(got["samples_mhz"], [3000.0, 3010.0, 2990.0, 3000.0])

    def test_timed_session_line_carries_the_clock_and_the_start(self) -> None:
        plan = p2run.parse_plan(plan_dict(programs=[
            {"name": "p", "path": [sys.executable, "-c", "pass"], "arms": ["a"], "version": "startup-line"}]))
        text = json.dumps(plan_dict(_note="x")).encode()
        smoke = {"p": [{"arm": "a", "lines": ["start 12:30:45 up", "go1.27"], "ready": True}]}
        timed = p2run.session_line(plan, text, None, {"session_mhz": 3000.0, "source": "plan"}, smoke)
        counted = p2run.session_line(plan, text, 100, None, smoke)
        self.assertEqual(timed["programs"][0]["startup_lines"], ["start 12:30:45 up", "go1.27"])
        self.assertEqual(counted["programs"][0]["startup_lines"], [p2run.WITHHELD, "go1.27"])
        self.assertNotIn("_note", timed["plan"])
        self.assertEqual((timed["mode"], timed["clock"]["session_mhz"]), ("timed", 3000.0))
        self.assertIn("started", timed)
        self.assertEqual((counted["mode"], counted["count"]), ("count", 100))
        self.assertNotIn("started", counted)
        self.assertNotIn("clock", counted)


# ---------------------------------------------------------------- reruns (decision 18)


class ScriptedRunner:
    """Runner.run_window's rows without a process: each seq's status and reason codes come from a script."""

    def __init__(self, script: dict[int, tuple[str, list[str]]], count: int | None = None) -> None:
        self.script, self.count, self.seen = script, count, []

    def run_window(self, w) -> dict:
        self.seen.append(w)
        status, codes_ = self.script.get(w.seq, ("valid", []))
        if w.rerun:
            status, codes_ = self.script.get(("rerun", w.index), ("valid", []))
        row = {"type": "window", "seq": w.seq, "shape": w.shape, "m": w.m, "table_seed": w.table_seed,
               "program": w.program, "arm": w.arm, "entry": w.entry, "index": w.index, "status": status,
               "reasons": [f"why {c}" for c in codes_], "reason_codes": codes_}
        if w.rerun:
            row["rerun"] = True
        return row


class RerunTests(unittest.TestCase):
    """Two sizes, two pairs, programs of 2 and 3 arms: rounds of 4 and 6 windows, 40 windows."""

    def plan(self, **over):
        return p2run.parse_plan(plan_dict(
            sizes=[10, 100], pairs=[[111, 211], [112, 212]],
            programs=[{"name": "mserver", "path": "mserver", "arms": ["v2", "null"]},
                      {"name": "mserver-go", "path": "mserver-go", "arms": ["v2", "gin", "null"]}], **over))

    def run_loop(self, plan, script, count=None) -> tuple[int, list[dict], ScriptedRunner]:
        sink, runner = io.StringIO(), ScriptedRunner(script, count)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = p2run._run_windows(plan, runner, sink)
        return rc, [json.loads(line) for line in sink.getvalue().splitlines()], runner

    def test_host_faults_only_and_never_an_arms(self) -> None:
        self.assertEqual(p2run.host_faults({"status": "invalid", "reason_codes": ["sampler"]}), ["sampler"])
        self.assertEqual(p2run.host_faults({"status": "invalid", "reason_codes": ["sampler", "others"]}), ["others", "sampler"])
        # a window that also failed for an arm's reason is the arm's (a crashed server's error reporter is a process)
        self.assertEqual(p2run.host_faults({"status": "invalid", "reason_codes": ["server_died", "others"]}), [])
        self.assertEqual(p2run.host_faults({"status": "invalid", "reason_codes": ["error_share", "sampler"]}), [])
        self.assertEqual(p2run.host_faults({"status": "overloaded", "reason_codes": ["error_share"]}), [])
        self.assertEqual(p2run.host_faults({"status": "invalid", "reason_codes": []}), [])
        self.assertEqual(p2run.host_faults({"status": "valid", "reason_codes": []}), [])

    def test_the_window_sequence_is_unchanged(self) -> None:
        plan = p2run.parse_plan(plan_dict(sizes=[10], programs=[
            {"name": "mserver", "path": "mserver", "arms": ["v2", "null"]},
            {"name": "mserver-go", "path": "mserver-go", "arms": ["v2", "v2"]}]))
        got = [(w.seq, w.program, w.arm, w.index, w.half, w.entry, w.round_length, w.rerun) for w in p2run.windows(plan)]
        self.assertEqual(got, [(0, "mserver", "v2", 0, 1, 0, 4, False), (1, "mserver", "null", 1, 1, 1, 4, False),
                               (2, "mserver", "null", 2, 2, 1, 4, False), (3, "mserver", "v2", 3, 2, 0, 4, False),
                               (4, "mserver-go", "v2", 0, 1, 0, 4, False), (5, "mserver-go", "v2", 1, 1, 1, 4, False),
                               (6, "mserver-go", "v2", 2, 2, 1, 4, False), (7, "mserver-go", "v2", 3, 2, 0, 4, False)])

    def test_no_rerun_unless_the_plan_asks(self) -> None:
        rc, rows, _ = self.run_loop(self.plan(), {5: ("invalid", ["sampler"])})
        self.assertEqual((rc, len(rows)), (0, 41))
        self.assertEqual(rows[-1], {"type": "end", "exit": 0, "planned": {"windows": 40, "windows_run": 40,
                                                                          "by_status": {"valid": 39, "invalid": 1}}})

    def test_rounds_with_a_host_fault_run_once_more_whole_and_in_order(self) -> None:
        plan = self.plan(rerun_host_faults=True)
        windows = list(p2run.windows(plan))
        self.assertEqual(len(windows), 40)
        # seq 1 in the first C++ round (seqs 0 to 3): a host fault. Seq 5 and 8 in the first Go round (4 to 9): a
        # host fault, and an overload during a burst, which is the arm's. Seq 21 in the second size's first C++
        # round (20 to 23): an arm's fault only. Seq 36 in the last Go round (34 to 39): a host fault.
        script = {1: ("invalid", ["sampler"]), 5: ("invalid", ["sampler"]), 8: ("invalid", ["error_share", "others"]),
                  21: ("invalid", ["error_share"]), 36: ("invalid", ["others"]),
                  ("rerun", 2): ("invalid", ["sampler"])}  # a host fault in a rerun is not rerun again
        rc, rows, runner = self.run_loop(plan, script)
        self.assertEqual(rc, 0)
        line, reruns, end = rows[40], rows[41:-1], rows[-1]
        self.assertEqual(line["type"], "rerun")
        self.assertEqual([(r["program"], r["m"], r["table_seed"], r["seqs"], r["codes"], r["first_seq"], r["windows"])
                          for r in line["rounds"]],
                         [("mserver", 10, 111, [1], ["sampler"], 40, 4),
                          ("mserver-go", 10, 111, [5], ["sampler"], 44, 6),
                          ("mserver-go", 100, 112, [36], ["others"], 50, 6)])
        self.assertEqual([r["arm_faults"] for r in line["rounds"]],
                         [[], [{"seq": 8, "status": "invalid", "codes": ["error_share", "others"]}], []])
        self.assertEqual((line["windows"], len(reruns)), (16, 16))
        self.assertTrue(all(r["type"] == "window" and r["rerun"] for r in reruns))
        self.assertEqual([r["seq"] for r in reruns], list(range(40, 56)))
        self.assertEqual([r["arm"] for r in reruns[:4]], ["v2", "null", "null", "v2"])
        self.assertEqual([r["arm"] for r in reruns[4:10]], ["v2", "gin", "null", "null", "gin", "v2"])
        self.assertEqual([r["entry"] for r in reruns[4:10]], [0, 1, 2, 2, 1, 0])
        self.assertEqual([(w.ring_seed, w.round_length) for w in runner.seen[40:]],
                         [(211, 4)] * 4 + [(211, 6)] * 6 + [(212, 6)] * 6)
        self.assertEqual(end, {"type": "end", "exit": 0,
                               "rerun": {"rounds": 3, "windows_run": 16, "by_status": {"valid": 13, "invalid": 3},
                                         "rounds_with_host_faults": 3},
                               "planned": {"windows": 40, "windows_run": 40, "by_status": {"valid": 35, "invalid": 5}}})

    def test_an_aa_round_reruns_with_both_entries(self) -> None:
        plan = p2run.parse_plan(plan_dict(rerun_host_faults=True,
                                          programs=[{"name": "mserver", "path": "mserver", "arms": ["v2", "v2"]}]))
        rc, rows, _ = self.run_loop(plan, {2: ("invalid", ["others"])})
        self.assertEqual([(r["arm"], r["entry"], r["seq"]) for r in rows[5:9]],
                         [("v2", 0, 4), ("v2", 1, 5), ("v2", 1, 6), ("v2", 0, 7)])

    def test_a_stopped_run_has_no_reruns(self) -> None:
        plan = self.plan(rerun_host_faults=True, abort_after_consecutive=3)
        rc, rows, _ = self.run_loop(plan, {i: ("invalid", ["sampler"]) for i in range(3)})
        self.assertEqual((rc, len(rows), rows[-1]["exit"], "rerun" in rows[-1]), (3, 4, 3, False))

    def test_the_consecutive_fault_rule_holds_in_the_reruns(self) -> None:
        plan = self.plan(rerun_host_faults=True, abort_after_consecutive=3)
        script = {0: ("invalid", ["sampler"]), **{("rerun", i): ("invalid", ["sampler"]) for i in range(4)}}
        rc, rows, _ = self.run_loop(plan, script)
        self.assertEqual((rc, rows[40]["windows"], len(rows), rows[-1]["exit"]), (3, 4, 45, 3))
        self.assertEqual(rows[-1]["rerun"]["windows_run"], 3)

    def test_the_rerun_pass_counts_consecutive_faults_from_zero(self) -> None:
        plan = self.plan(rerun_host_faults=True, abort_after_consecutive=3)
        # the last two planned windows and the first rerun window fail with one systematic reason
        rc, rows, _ = self.run_loop(plan, {38: ("invalid", ["sampler"]), 39: ("invalid", ["sampler"]),
                                           ("rerun", 0): ("invalid", ["sampler"])})
        self.assertEqual((rc, rows[40]["windows"], rows[-1]["rerun"]["windows_run"]), (0, 6, 6))

    def test_count_mode_records_an_empty_rerun_pass(self) -> None:
        rc, rows, _ = self.run_loop(self.plan(rerun_host_faults=True), {}, count=100)
        self.assertEqual((rc, rows[-2]), (0, {"type": "rerun", "rounds": [], "windows": 0}))
        self.assertEqual(rows[-1]["rerun"], {"rounds": 0, "windows_run": 0, "by_status": {}, "rounds_with_host_faults": 0})


# ---------------------------------------------------------------- round-robin (decision 21)


def rr_plan(**over):
    """Two sizes, one pair, programs of 2 and 3 arms: 5 contestants, R = 3, 15 windows per cell, 30 in all."""
    d = dict(schedule="round-robin", rounds=3, order_seed=2026, sizes=[10, 100],
             programs=[{"name": "mserver", "path": "mserver", "arms": ["v2", "null"]},
                       {"name": "mserver-go", "path": "mserver-go", "arms": ["v2", "gin", "null"]}])
    d.update(over)
    return p2run.parse_plan(plan_dict(**d))


class RoundRobinSequenceTests(unittest.TestCase):
    def test_contestants_are_the_entries_of_every_program(self) -> None:
        got = [(c.program, c.arm, c.entry) for c in p2run.contestants(rr_plan())]
        self.assertEqual(got, [("mserver", "v2", 0), ("mserver", "null", 1), ("mserver-go", "v2", 0),
                               ("mserver-go", "gin", 1), ("mserver-go", "null", 2)])
        aa = rr_plan(programs=[{"name": "mserver", "path": "mserver", "arms": ["v2", "v2"]}])
        self.assertEqual([(c.arm, c.entry) for c in p2run.contestants(aa)], [("v2", 0), ("v2", 1)])

    def test_every_contestant_once_per_round_in_orders_the_plan_fixes(self) -> None:
        plan = rr_plan()
        everyone = set(p2run.contestants(plan))
        orders = p2run.round_orders(plan, "mixed-disjoint", 10, 111)
        self.assertEqual(len(orders), 3)
        self.assertTrue(all(len(o) == 5 and set(o) == everyone for o in orders))
        self.assertEqual(orders, p2run.round_orders(rr_plan(), "mixed-disjoint", 10, 111))  # the plan alone fixes them
        self.assertNotEqual(orders, p2run.round_orders(rr_plan(order_seed=2027), "mixed-disjoint", 10, 111))
        self.assertNotEqual(orders, p2run.round_orders(plan, "mixed-disjoint", 100, 111))  # each cell draws its own
        many = p2run.round_orders(rr_plan(rounds=20), "mixed-disjoint", 10, 111)
        self.assertGreater(len(set(many)), 1)  # the rounds differ
        self.assertEqual(many[:3], orders)  # round k's order does not depend on R

    def test_the_orders_are_those_of_a_text_seeded_generator(self) -> None:
        # random.seed of a text is the same in every Python 3: the laptop's Python draws these orders too
        rng = __import__("random").Random("2026:mixed-disjoint:10:111")
        want = list(p2run.contestants(rr_plan()))
        rng.shuffle(want)
        self.assertEqual(p2run.round_orders(rr_plan(), "mixed-disjoint", 10, 111)[0], tuple(want))

    def test_the_window_sequence(self) -> None:
        plan = rr_plan()
        ws = list(p2run.windows(plan))
        self.assertEqual((len(ws), p2run.total_windows(plan)), (30, 30))
        self.assertEqual([w.seq for w in ws], list(range(30)))
        first = p2run.round_orders(plan, "mixed-disjoint", 10, 111)[0]
        self.assertEqual([(w.program, w.arm, w.entry) for w in ws[:5]], [(c.program, c.arm, c.entry) for c in first])
        self.assertEqual({(w.round_no, w.m) for w in ws}, {(r, m) for r in (1, 2, 3) for m in (10, 100)})
        self.assertEqual([w.index for w in ws[:5]], [0, 1, 2, 3, 4])
        self.assertTrue(all(w.round_length == 5 and w.ring_seed == 211 and not w.rerun for w in ws))


class WarmupJudgeTests(unittest.TestCase):
    def obs(self, **over):
        base = dict(ready=True, probe=PROBE_OK, generator=gen_line(timeouts=5, status=200), generator_exit=0,
                    server_alive_at_end=True, server_exit=None)
        base.update(over)
        return Observed(**base)

    def test_errors_are_not_judged_and_nothing_is_sampled(self) -> None:
        self.assertEqual(p2run.judge_warmup(self.obs()).status, "valid")

    def test_what_fails_a_warmup(self) -> None:
        cases = {"not_ready": self.obs(ready=False), "probe": self.obs(probe={"status": 500, "body_ok": False}),
                 "server_died": self.obs(server_alive_at_end=False, server_exit=1),
                 "generator_failed": self.obs(generator_exit=1), "no_answers": self.obs(generator=gen_line(completed=0)),
                 "no_result": self.obs(generator=None)}
        for code, o in cases.items():
            v = p2run.judge_warmup(o)
            self.assertEqual(v.status, "invalid", code)
            self.assertIn(code, [c for c, _ in v.reasons], code)

    def test_count_mode_uses_the_count_rules(self) -> None:
        line = {"completed": 100, "resolved": 100, "errors_total": 0, "thread_failed": 0}
        self.assertEqual(p2run.judge_warmup(self.obs(generator=line), 100).status, "valid")
        self.assertEqual(p2run.judge_warmup(self.obs(generator={**line, "completed": 99}), 100).status, "invalid")


class SettleTests(unittest.TestCase):
    """The settle step on a stand-in CPU clock: each read of a pid's CPU time returns the next value of a script.
    Nothing here looks at how long it waited."""

    def runner(self, count=100):
        return p2run.Runner(rr_plan(), Path("w"), count, None, None)

    def cpu(self, script: list[float]):
        values = iter(script)
        last = [0.0]

        def read(pid):
            last[0] = next(values, last[0])
            return last[0]
        return mock.patch.object(p2run.HOST, "process_cpu_s", side_effect=read, create=True)

    def test_quiet_servers_settle_at_once_and_count_mode_keeps_no_time(self) -> None:
        r = self.runner()
        with self.cpu([1.0, 1.0, 1.0]):
            r.mark_cpu([7])
            self.assertEqual(r.settle([7]), {"quiet": True})

    def test_a_busy_server_is_waited_for(self) -> None:
        r = self.runner()
        with self.cpu([0.0, 5.0, 10.0, 10.0, 10.0]) as read:  # busy from the mark to two polls, then idle
            r.mark_cpu([7])
            self.assertEqual(r.settle([7]), {"quiet": True})
        self.assertGreaterEqual(read.call_count, 4)

    def test_servers_that_never_settle_fail_after_the_limit(self) -> None:
        r = self.runner()
        with self.cpu([float(i) for i in range(10_000)]), mock.patch.object(p2run, "SETTLE_LIMIT_S", 0.3):
            self.assertEqual(r.settle([7]), {"quiet": False})

    def test_a_server_that_exits_is_left_out(self) -> None:
        r = self.runner()

        def read(pid):
            if pid == 8:
                raise OSError("gone")
            return 2.0
        with mock.patch.object(p2run.HOST, "process_cpu_s", side_effect=read, create=True):
            r.mark_cpu([7, 8])
            self.assertEqual(r.settle([7, 8]), {"quiet": True})

    def test_this_hosts_process_cpu_time(self) -> None:
        child = subprocess.Popen([sys.executable, "-c", "import time; sum(range(10**6)); time.sleep(5)"])
        try:
            v = p2run.HOST.process_cpu_s(child.pid)
            self.assertIsInstance(v, float)
            self.assertGreaterEqual(v, 0.0)
        finally:
            child.kill()
            child.wait()


class ScriptedRoundRobin:
    """The runner's round-robin parts without a process: each window's status and reason codes come from a
    script keyed by seq, or by ("rerun", seq) for a rerun window. Every call is logged in order."""

    def __init__(self, script: dict, count: int | None = None, dead: frozenset = frozenset()) -> None:
        self.script, self.count, self.dead, self.log = script, count, dead, []

    def new_slot(self, c, cell):
        return p2run.Slot(c, cell, Path("."), 1000 + c.entry, Path("x.log"), None, True)

    def start_server(self, slot):
        self.log.append(("start", p2run.cell_name(slot.cell), slot.contestant.program, slot.contestant.entry))
        return {"type": "server", "cell": p2run.cell_name(slot.cell), **slot.who(), "status": "valid", "reason_codes": []}

    def mark_cpu(self, pids):
        pass

    def warm_up(self, slot, pids=()):
        self.log.append(("warmup", p2run.cell_name(slot.cell), slot.contestant.program, slot.contestant.entry))
        return {"type": "warmup", **slot.who(), "status": "valid", "reasons": [], "reason_codes": []}

    def run_window(self, w, slot, idle):
        self.log.append(("window", w.seq, w.rerun))
        status, codes_ = self.script.get(("rerun", w.seq) if w.rerun else w.seq, ("valid", []))
        row = {"type": "window", "seq": w.seq, "cell": w.cell, "program": w.program, "arm": w.arm, "entry": w.entry,
               "round": w.round_no, "position": w.index, "status": status, "reasons": [f"why {c}" for c in codes_],
               "reason_codes": codes_}
        if w.rerun:
            row["rerun"] = True
        return row

    def stop_servers(self, slots, cell):
        self.log.append(("stop", p2run.cell_name(cell)))
        servers = [{**s.who(), "windows_count": (s.contestant.program, s.contestant.entry) not in self.dead,
                    "reason_codes": []} for s in slots]
        return {"type": "cell_end", "cell": p2run.cell_name(cell), "servers": servers}


class RoundRobinLoopTests(unittest.TestCase):
    def run_loop(self, plan, script, count=None, dead=frozenset()):
        sink, runner = io.StringIO(), ScriptedRoundRobin(script, count, dead)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = p2run._run_round_robin(plan, runner, sink)
        return rc, [json.loads(line) for line in sink.getvalue().splitlines()], runner

    def test_a_cell_starts_its_servers_warms_them_runs_its_rounds_then_stops_them(self) -> None:
        rc, rows, runner = self.run_loop(rr_plan(), {})
        self.assertEqual(rc, 0)
        kinds = [r["type"] for r in rows]
        self.assertEqual(kinds, (["server"] * 5 + ["warmup"] * 5 + ["window"] * 15 + ["cell_end"]) * 2 + ["end"])
        self.assertEqual([e[0] for e in runner.log[:11]], ["start"] * 5 + ["warmup"] * 5 + ["window"])
        self.assertEqual(rows[-1], {"type": "end", "exit": 0, "planned": {"windows": 30, "windows_run": 30,
                                                                         "by_status": {"valid": 30}},
                                    "warmups": {"by_status": {"valid": 10}}, "servers_not_counting": 0})

    def test_a_round_with_a_host_fault_reruns_in_its_cell_before_the_stop(self) -> None:
        plan = rr_plan(rerun_host_faults=True)
        # cell m10: round 2 (seqs 5 to 9) has a host fault at 6 and an arm's fault at 8; round 3 (10 to 14) an arm's
        # fault only. Cell m100: round 1 (15 to 19) a host fault at 19, spoiled again in its rerun.
        script = {6: ("invalid", ["sampler"]), 8: ("overloaded", ["error_share"]), 12: ("invalid", ["error_share"]),
                  19: ("invalid", ["others"]), ("rerun", 35): ("invalid", ["others"])}
        rc, rows, runner = self.run_loop(plan, script)
        self.assertEqual(rc, 0)
        kinds = [r["type"] for r in rows]
        self.assertEqual(kinds[:31], ["server"] * 5 + ["warmup"] * 5 + ["window"] * 15 + ["rerun"] + ["window"] * 5)
        first = rows[25]
        self.assertEqual(first, {"type": "rerun", "cell": "mixed-disjoint/m10/t111", "windows": 5, "rounds": [
            {"round": 2, "seqs": [6], "codes": ["sampler"], "first_seq": 30, "windows": 5,
             "arm_faults": [{"seq": 8, "status": "overloaded", "codes": ["error_share"]}]}]})
        reruns = rows[26:31]
        order = p2run.round_orders(plan, "mixed-disjoint", 10, 111)[1]
        self.assertEqual([(r["program"], r["entry"]) for r in reruns], [(c.program, c.entry) for c in order])
        self.assertEqual([(r["seq"], r["round"], r["rerun"]) for r in reruns], [(s, 2, True) for s in range(30, 35)])
        self.assertEqual(rows[31]["type"], "cell_end")  # the servers ran through the rerun
        second = next(r for r in rows[32:] if r["type"] == "rerun")
        self.assertEqual((second["cell"], [r["round"] for r in second["rounds"]], second["rounds"][0]["first_seq"]),
                         ("mixed-disjoint/m100/t111", [1], 35))
        self.assertEqual(rows[-1]["rerun"], {"rounds": 2, "windows_run": 10, "by_status": {"valid": 9, "invalid": 1},
                                             "rounds_with_host_faults": 1})

    def test_the_consecutive_fault_rule_stops_the_run_and_the_servers_are_stopped(self) -> None:
        plan = rr_plan(abort_after_consecutive=3)
        rc, rows, runner = self.run_loop(plan, {i: ("invalid", ["sampler"]) for i in range(4, 7)})
        self.assertEqual(rc, 3)
        self.assertEqual([r["type"] for r in rows][-3:], ["window", "cell_end", "end"])
        self.assertEqual((rows[-1]["exit"], rows[-1]["planned"]["windows_run"]), (3, 7))
        self.assertEqual(runner.log[-1], ("stop", "mixed-disjoint/m10/t111"))

    def test_a_rerun_pass_stopped_by_the_rule_keeps_its_tally_in_the_end_line(self) -> None:
        plan = rr_plan(rerun_host_faults=True, abort_after_consecutive=2)
        rc, rows, runner = self.run_loop(plan, {6: ("invalid", ["sampler"]), ("rerun", 30): ("invalid", ["sampler"]),
                                                ("rerun", 31): ("invalid", ["sampler"])})
        self.assertEqual(rc, 3)
        self.assertEqual(rows[-1]["rerun"], {"rounds": 1, "windows_run": 2, "by_status": {"invalid": 2},
                                             "rounds_with_host_faults": 1})
        self.assertEqual(runner.log[-1], ("stop", "mixed-disjoint/m10/t111"))

    def test_the_streak_runs_across_cells(self) -> None:
        rc, _, _ = self.run_loop(rr_plan(abort_after_consecutive=3), {13: ("invalid", ["sampler"]), 14: ("invalid", ["sampler"]),
                                                                      15: ("invalid", ["sampler"])})
        self.assertEqual(rc, 3)

    def test_count_mode_fails_on_a_server_whose_windows_do_not_count(self) -> None:
        rc, rows, _ = self.run_loop(rr_plan(), {}, count=100, dead=frozenset({("mserver-go", 1)}))
        self.assertEqual((rc, rows[-1]["servers_not_counting"]), (1, 2))
        rc, _, _ = self.run_loop(rr_plan(), {}, count=100)
        self.assertEqual(rc, 0)


# ---------------------------------------------------------------- orchestration in count mode

FAKE_SERVER = textwrap.dedent('''
    import os, signal, socket, sys, threading
    argv = sys.argv[1:]
    opt = {a: argv[i + 1] for i, a in enumerate(argv) if a.startswith("--") and a != "--check" and i + 1 < len(argv)}
    print("fake-server: start", file=sys.stderr, flush=True)
    mode = os.environ.get("FAKE_SERVER", "ok")
    if not os.path.exists(opt.get("--routes", "")):
        sys.exit(2)
    smoke = "smoke" in os.path.basename(opt["--routes"])  # the preflight start; modes without _all spare it
    if opt.get("--router") not in ("a", "b"):
        print("fake-server: no such arm", file=sys.stderr, flush=True)
        sys.exit(2)
    if mode == "refuse_all" or (mode == "refuse" and not smoke):
        print("fake-server: refuses the table", file=sys.stderr, flush=True)
        sys.exit(3)
    stop_code = 3 if mode == "badexit_all" or (mode == "badexit" and not smoke) else 0
    stopping = threading.Event()
    def stop(*_):
        stopping.set()
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", int(opt["--port"])))
    srv.listen(16)
    srv.settimeout(0.05)
    def serve(c):
        with c:
            buf = b""
            while True:
                while b"\\r\\n\\r\\n" not in buf:
                    d = c.recv(4096)
                    if not d:
                        return
                    buf += d
                _, _, buf = buf.partition(b"\\r\\n\\r\\n")
                c.sendall(b"HTTP/1.1 200 OK\\r\\nContent-Length: 13\\r\\n\\r\\nHello, World!")
    while not stopping.is_set():
        try:
            c, _ = srv.accept()
        except socket.timeout:
            continue
        threading.Thread(target=serve, args=(c,), daemon=True).start()
    os._exit(stop_code)
''')

FAKE_GEN = textwrap.dedent('''
    import json, os, sys
    argv = sys.argv[1:]
    if "--help" in argv:
        print("usage: fake p2gen", file=sys.stderr)
        sys.exit(0)
    opt = {a: argv[i + 1] for i, a in enumerate(argv) if a.startswith("--") and i + 1 < len(argv)}
    if not os.path.exists(opt["--paths"]):
        sys.exit(2)
    mode = os.environ.get("FAKE_GEN", "ok")
    if mode == "crash":
        sys.exit(1)
    n = int(opt["--count"])
    done = n - 1 if mode == "short" else n
    line = {"tool": "p2gen", "mode": "count", "port": int(opt["--port"]), "count": n, "threads": int(opt["--threads"]),
            "connections": int(opt["--connections"]), "resolved": done, "completed": done,
            "errors": {"status": 0, "body": 0, "framing": 0, "lost": 0, "unsolicited": 0}, "timeouts": 0,
            "errors_total": 0, "connect_errors": 0, "resets": 0, "peer_closes": 0, "reconnects": 0, "thread_failed": 0}
    text = json.dumps(line)
    print(text, flush=True)
    open(opt["--out"], "w").write(text + "\\n")
    sys.exit(0 if done == n else 1)
''')

TIMEISH = re.compile(r"(_s|_ms|_us|_ns|_mhz)$|^(started|startup_s|clock|wall|latency|rate|elapsed|duration)", re.I)


def walk(obj, path=""):
    """Every (key path, value) of a JSON value; list items share their list's path."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, path)
    else:
        yield path, obj


class OrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.cpu_count() < 2:
            raise unittest.SkipTest("needs two CPUs")
        cls.tmp = tempfile.TemporaryDirectory(prefix="p2run-test-")
        root = Path(cls.tmp.name)
        (root / "server.py").write_text(FAKE_SERVER)
        (root / "gen.py").write_text(FAKE_GEN)
        cls.root = root
        cls.sets = root / "sets"
        rows = ["shape\tm\ttable_seed\tring_seed\troutes_sha256\tring_sha256"]
        for m in (10, 100):
            d = cls.sets / "mixed-disjoint" / f"m{m}" / "t111"
            d.mkdir(parents=True)
            (d / "routes.txt").write_text("GET /a/{p0}\nGET /b\n")
            (d / "ring.txt").write_text("/a/1\n/b\n")
            h = lambda name, d=d: hashlib.sha256((d / name).read_bytes()).hexdigest()  # noqa: E731
            rows.append(f"mixed-disjoint\t{m}\t111\t211\t{h('routes.txt')}\t{h('ring.txt')}")
        (cls.sets / "manifest.tsv").write_text("\n".join(rows) + "\n")
        cls.cpus = {"server": os.cpu_count() - 1, "generator": "0"}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def plan(self, name: str, **over) -> Path:
        d = {"p2gen": [sys.executable, str(self.root / "gen.py")], "data_root": str(self.sets),
             "shapes": ["mixed-disjoint"], "sizes": [10, 100], "pairs": [[111, 211]], "cpus": self.cpus,
             "warmup_s": 1.0, "window_s": 5.0, "timeout_ms": 777, "error_share_max": 0.001,
             "programs": [{"name": "fake", "path": [sys.executable, str(self.root / "server.py")],
                           "arms": ["a", "b"], "version": "startup-line"}]}
        d.update(over)
        path = self.root / f"{name}.plan.json"
        path.write_text(json.dumps(d))
        return path

    def run_main(self, plan: Path, name: str, env: dict | None = None, extra=()) -> tuple[int, list[dict], str]:
        out = self.root / f"{name}.jsonl"
        out.unlink(missing_ok=True)
        err = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), contextlib.redirect_stderr(err):
            rc = p2run.main([str(plan), "--out", str(out), "--count", "100", *extra])
        rows = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
        self.end = rows.pop() if rows and rows[-1].get("type") == "end" else None  # every finished run has one
        self.assertEqual(self.end is not None, rc in (0, 1, 3), (rc, self.end))
        return rc, rows, err.getvalue()

    def test_all_windows_pass_and_the_record_holds_no_time(self) -> None:
        extra = {"housekeeping_cpus": "1"} if os.cpu_count() >= 3 else {}
        try:
            rc, rows, err = self.run_main(self.plan("ok", **extra), "ok")
        finally:
            if extra:  # run_all pinned this thread
                p2run.HOST.pin_thread(range(os.cpu_count()))
        self.assertEqual(rc, 0, err)
        session, windows = rows[0], rows[1:]
        self.assertEqual(session["type"], "session")
        self.assertEqual((session["mode"], session["count"], session["windows"]), ("count", 100, 8))
        self.assertEqual(len(windows), 8)
        self.assertTrue(all(w["status"] == "valid" and w["reasons"] == [] for w in windows), err)
        self.assertEqual([w["arm"] for w in windows[:4]], ["a", "b", "b", "a"])
        server, gens = (self.cpus["server"],), tuple(p2run.parse_cpu_list(self.cpus["generator"]))
        for w in windows:
            self.assertEqual(tuple(w["server_affinity"]), server)
            self.assertEqual(tuple(w["generator_affinity"]), gens)
            self.assertEqual(w["server_exit"], 0)
            self.assertIn(w["stop_method"], ("sigterm", "ctrl_break"))
            self.assertEqual((w["generator"]["completed"], w["generator_exit"]), (100, 0))
            self.assertEqual(len(w["routes_sha256"]), 64)
            self.assertNotIn("sampler_errors", w)
        self.assertEqual(self.end, {"type": "end", "exit": 0,
                                    "planned": {"windows": 8, "windows_run": 8, "by_status": {"valid": 8}}})
        # count mode: no key that names a time, no clock or CPU sample, no float anywhere
        for row in [*rows, self.end]:
            for path, value in walk(row):
                leaf = path.split(".")[-1]
                self.assertIsNone(TIMEISH.search(leaf), path)
                self.assertNotIsInstance(value, float, path)
        self.assertNotIn("started", session)
        self.assertNotIn("clock", session)
        for key in p2run.TIME_KEYS:
            self.assertNotIn(key, session["plan"])
        for w in windows:
            self.assertFalse({"startup_s", "cpu", "clock", "started"} & set(w))
        program = session["programs"][0]
        self.assertEqual(program["startup_lines"], ["fake-server: start"])
        self.assertEqual(program["startup_arm"], "a")
        self.assertEqual([s["arm"] for s in program["starts"]], ["a", "b"])
        self.assertTrue(all(s["ready"] and s["probe_ok"] and s["exit"] == 0 for s in program["starts"]))
        self.assertEqual(program["sha256"], hashlib.sha256((self.root / "server.py").read_bytes()).hexdigest())
        self.assertEqual(program["binary"], str(self.root / "server.py"))
        self.assertEqual(session["plan_sha256"], hashlib.sha256((self.root / "ok.plan.json").read_bytes()).hexdigest())

    def test_a_server_that_refuses_the_table_is_invalid_with_its_log(self) -> None:
        plan = self.plan("refuse", sizes=[10], abort_after_consecutive=0)
        rc, rows, _ = self.run_main(plan, "refuse", {"FAKE_SERVER": "refuse"})
        self.assertEqual(rc, 1)
        self.assertEqual(len(rows) - 1, 4)
        for w in rows[1:]:
            self.assertEqual((w["status"], w["reason_codes"], w["server_exit"]), ("invalid", ["not_ready"], 3))
            self.assertIn("refuses the table", w["server_log_tail"])
            self.assertNotIn("generator", w)

    def test_the_run_stops_when_one_systematic_fault_repeats(self) -> None:
        plan = self.plan("breaker", sizes=[10, 100], abort_after_consecutive=3)
        rc, rows, err = self.run_main(plan, "breaker", {"FAKE_SERVER": "refuse"})
        self.assertEqual(rc, 3, err)
        self.assertEqual(len(rows) - 1, 3)  # of 8 windows
        self.assertIn("in a row failed with 'not_ready'", err)
        self.assertEqual((self.end["exit"], self.end["planned"]), (3, {"windows": 8, "windows_run": 3,
                                                                       "by_status": {"invalid": 3}}))

    def test_overload_and_other_measurement_outcomes_do_not_stop_the_run(self) -> None:
        self.assertNotIn("error_share", p2run.SYSTEMATIC)
        self.assertNotIn("no_answers", p2run.SYSTEMATIC)

    def test_a_server_that_exits_nonzero_after_the_stop_is_invalid(self) -> None:
        plan = self.plan("badexit", sizes=[10], abort_after_consecutive=0)
        rc, rows, _ = self.run_main(plan, "badexit", {"FAKE_SERVER": "badexit"})
        self.assertEqual(rc, 1)
        self.assertEqual({tuple(w["reason_codes"]) for w in rows[1:]}, {("server_exit",)})

    def test_preflight_starts_every_arm_and_names_the_one_that_fails(self) -> None:
        rc, rows, err = self.run_main(self.plan("arms", programs=[{"name": "fake", "arms": ["a", "zzz"], "version": "startup-line",
                                      "path": [sys.executable, str(self.root / "server.py")]}]), "arms")
        self.assertEqual((rc, rows), (2, []))
        self.assertIn("fake zzz: did not start (exit 2): fake-server: no such arm", err)
        rc, rows, err = self.run_main(self.plan("refuse-all", sizes=[10]), "refuse-all", {"FAKE_SERVER": "refuse_all"})
        self.assertEqual((rc, rows), (2, []))
        self.assertIn("did not start (exit 3)", err)
        rc, rows, err = self.run_main(self.plan("badexit-all", sizes=[10]), "badexit-all", {"FAKE_SERVER": "badexit_all"})
        self.assertEqual((rc, rows), (2, []))
        self.assertIn("exit code 3 after the stop signal", err)

    def test_preflight_refuses_a_generator_that_will_not_start(self) -> None:
        rc, rows, err = self.run_main(self.plan("gen-dead", p2gen=[sys.executable, "-c", "import sys; sys.exit(7)"]), "gen-dead")
        self.assertEqual((rc, rows), (2, []))
        self.assertIn("p2gen --help exited with 7", err)

    def test_timed_mode_needs_housekeeping_cpus(self) -> None:
        err = io.StringIO()
        out = self.root / "nohk.jsonl"
        with contextlib.redirect_stderr(err):
            rc = p2run.main([str(self.plan("nohk", sizes=[10])), "--out", str(out)])  # no --count
        self.assertEqual((rc, out.exists()), (2, False))
        self.assertIn("housekeeping_cpus", err.getvalue())

    def test_an_aa_round_runs_its_one_arm_in_four_windows(self) -> None:
        programs = [{"name": "fake", "path": [sys.executable, str(self.root / "server.py")], "arms": ["a", "a"],
                     "version": "startup-line"}]
        rc, rows, err = self.run_main(self.plan("aa", sizes=[10], programs=programs), "aa")
        self.assertEqual(rc, 0, err)
        self.assertEqual([(w["arm"], w["entry"], w["status"]) for w in rows[1:]],
                         [("a", 0, "valid"), ("a", 1, "valid"), ("a", 1, "valid"), ("a", 0, "valid")])
        self.assertEqual([s["arm"] for s in rows[0]["programs"][0]["starts"]], ["a"])  # started once in the preflight

    def test_timed_mode_needs_the_labs_labrec(self) -> None:
        err = io.StringIO()
        out = self.root / "nolab.jsonl"
        env = {k: v for k, v in os.environ.items() if k != "LAB_TOOLS"}
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stderr(err):
            plan = self.plan("nolab", sizes=[10], cpus={"server": 2, "generator": "3"}, housekeeping_cpus="0")
            rc = p2run.main([str(plan), "--out", str(out)])
        self.assertEqual((rc, out.exists()), (2, False))
        self.assertIn("LAB_TOOLS", err.getvalue())

    def test_a_binary_that_changes_makes_the_window_a_fault(self) -> None:
        script = self.root / "changing.py"
        script.write_text(FAKE_SERVER)
        plan = p2run.parse_plan(json.loads(self.plan("chg", programs=[
            {"name": "fake", "arms": ["a"], "version": "startup-line", "path": [sys.executable, str(script)]}]).read_text()))
        runner = p2run.Runner(plan, self.root, 100, None, None)
        script.write_text(FAKE_SERVER + "\n# a different binary\n")
        row = runner.run_window(next(p2run.windows(plan)))
        self.assertEqual((row["status"], row["reason_codes"]), ("invalid", ["driver"]))
        self.assertIn("binary changed", row["reasons"][0])

    def test_a_rerun_window_runs_like_any_other_and_says_so(self) -> None:
        plan = p2run.parse_plan(json.loads(self.plan("rr", sizes=[10]).read_text()))
        runner = p2run.Runner(plan, self.root, 100, None, None)
        w = next(p2run.rerun_windows(plan, [("mixed-disjoint", 10, 111, "fake")], 4))
        row = runner.run_window(w)
        self.assertEqual((row["seq"], row["rerun"], row["status"], row["arm"], row["ring_seed"]), (4, True, "valid", "a", 211))
        self.assertFalse(list(self.root.glob("000004.*")))  # a valid window's work files are removed
        with mock.patch.object(runner, "_window", side_effect=RuntimeError("boom")):
            row = runner.run_window(w)
        self.assertEqual((row["rerun"], row["reason_codes"]), (True, ["driver"]))

    def test_a_short_generator_run_is_invalid(self) -> None:
        rc, rows, _ = self.run_main(self.plan("short", sizes=[10]), "short", {"FAKE_GEN": "short"})
        self.assertEqual(rc, 1)
        self.assertEqual({tuple(w["reason_codes"]) for w in rows[1:]}, {("generator_failed", "count")})

    def test_a_generator_that_writes_nothing_is_invalid(self) -> None:
        rc, rows, _ = self.run_main(self.plan("crash", sizes=[10]), "crash", {"FAKE_GEN": "crash"})
        self.assertEqual(rc, 1)
        self.assertEqual({tuple(w["reason_codes"]) for w in rows[1:]}, {("no_result",)})

    def test_preflight_refusals_exit_2(self) -> None:
        missing_cpu = self.plan("cpu", cpus={"server": os.cpu_count() + 3, "generator": "0"})
        bad_sets = self.plan("sets", sizes=[1000])
        no_program = self.plan("prog", programs=[{"path": "/no/such/prog", "arms": ["a"]}])
        for name, plan in (("cpu", missing_cpu), ("sets", bad_sets), ("prog", no_program)):
            rc, rows, err = self.run_main(plan, name)
            self.assertEqual((rc, rows), (2, []), (name, err))
            self.assertIn("preflight", err)

    def test_preflight_names_a_changed_set(self) -> None:
        d = self.sets / "mixed-disjoint" / "m100" / "t111"
        original = (d / "ring.txt").read_text()
        try:
            (d / "ring.txt").write_text("/a/2\n/b\n")
            p2run.cell_digests.cache_clear()
            rc, rows, err = self.run_main(self.plan("changed", sizes=[100]), "changed")
            self.assertEqual((rc, rows), (2, []))
            self.assertIn("ring.txt differ from the manifest", err)
        finally:
            (d / "ring.txt").write_text(original)
            p2run.cell_digests.cache_clear()

    def test_a_relative_out_path_works(self) -> None:
        here = os.getcwd()
        os.chdir(self.root)
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = p2run.main([str(self.plan("rel", sizes=[10])), "--out", "sub/rel-out.jsonl", "--count", "100"])
        finally:
            os.chdir(here)
        self.assertEqual(rc, 0, err.getvalue())
        rows = [json.loads(line) for line in (self.root / "sub" / "rel-out.jsonl").read_text().splitlines()]
        self.assertEqual({w["status"] for w in rows[1:-1]}, {"valid"})
        self.assertEqual(rows[-1]["type"], "end")

    def test_the_record_is_not_overwritten(self) -> None:
        plan = self.plan("again", sizes=[10])
        out = self.root / "again.jsonl"
        out.write_text("keep\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = p2run.main([str(plan), "--out", str(out), "--count", "100"])
        self.assertEqual(rc, 2)
        self.assertEqual(out.read_text(), "keep\n")

    def test_verification_can_be_switched_off(self) -> None:
        rc, rows, err = self.run_main(self.plan("noverify", sizes=[10], verify_sets=False, data_root=str(self.sets)), "noverify")
        self.assertEqual(rc, 0, err)

    # ------------------------------------------------ round-robin (decision 21), count mode

    RR = {"schedule": "round-robin", "rounds": 2, "order_seed": 7, "server_warmup_s": 1.0}

    def by_type(self, rows: list[dict]) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in rows[1:]:
            out.setdefault(r["type"], []).append(r)
        return out

    def test_round_robin_keeps_each_server_for_its_cell_and_records_no_time(self) -> None:
        rc, rows, err = self.run_main(self.plan("rr-ok", **self.RR), "rr-ok")
        self.assertEqual(rc, 0, err)
        session, t = rows[0], self.by_type(rows)
        self.assertEqual([r["type"] for r in rows[1:]],
                         (["server"] * 2 + ["warmup"] * 2 + ["window"] * 4 + ["cell_end"]) * 2)
        self.assertEqual((session["windows"], len(t["window"])), (8, 8))
        self.assertTrue(all(r["status"] == "valid" for r in t["server"] + t["warmup"] + t["window"]), err)
        ports = {(r["cell"], r["entry"]): r["port"] for r in t["server"]}
        self.assertEqual(len(set(ports.values())), 4)
        for w in t["window"]:
            self.assertEqual(w["port"], ports[(w["cell"], w["entry"])])  # the same server through the cell
            self.assertEqual((w["generator"]["completed"], w["generator_exit"]), (100, 0))
            self.assertNotIn("server_exit", w)
        for cell in ("mixed-disjoint/m10/t111", "mixed-disjoint/m100/t111"):
            for r in (1, 2):
                self.assertEqual(sorted(w["arm"] for w in t["window"] if w["cell"] == cell and w["round"] == r), ["a", "b"])
        orders = session["round_robin"]["orders"]
        names = [c["arm"] for c in session["round_robin"]["contestants"]]
        self.assertEqual([w["arm"] for w in t["window"][:4]], [names[i] for rnd in orders["mixed-disjoint/m10/t111"] for i in rnd])
        for end in t["cell_end"]:
            for s in end["servers"]:
                self.assertEqual((s["windows_count"], s["reason_codes"], s["exit"]), (True, [], 0))
                self.assertTrue(isinstance(s["memory"]["peak_resident_kib"], int) and s["memory"]["peak_resident_kib"] > 0)
                self.assertIsInstance(s["memory"]["resident_kib"], int)
        self.assertEqual(self.end, {"type": "end", "exit": 0,
                                    "planned": {"windows": 8, "windows_run": 8, "by_status": {"valid": 8}},
                                    "warmups": {"by_status": {"valid": 4}}, "servers_not_counting": 0})
        for row in [*rows, self.end]:
            for path, value in walk(row):
                self.assertIsNone(TIMEISH.search(path.split(".")[-1]), path)
                self.assertNotIsInstance(value, float, path)
        self.assertNotIn("server_warmup_s", session["plan"])
        self.assertFalse(list(self.root.glob("rr-ok.jsonl.work/*.server.log")))  # logs of servers that passed are removed

    def test_round_robin_aa_runs_two_servers_of_one_arm(self) -> None:
        programs = [{"name": "fake", "path": [sys.executable, str(self.root / "server.py")], "arms": ["a", "a"],
                     "version": "startup-line"}]
        rc, rows, err = self.run_main(self.plan("rr-aa", sizes=[10], programs=programs, **self.RR), "rr-aa")
        self.assertEqual(rc, 0, err)
        t = self.by_type(rows)
        self.assertEqual([(r["arm"], r["entry"]) for r in t["server"]], [("a", 0), ("a", 1)])
        self.assertNotEqual(t["server"][0]["port"], t["server"][1]["port"])
        self.assertEqual(sorted((w["round"], w["entry"]) for w in t["window"]), [(1, 0), (1, 1), (2, 0), (2, 1)])

    def test_a_server_that_dies_mid_cell_spoils_only_its_own_windows_there(self) -> None:
        original = p2run.Runner.run_window

        def kill_b_first(runner, w, slot=None, idle=None):
            if slot is not None and w.m == 10 and w.arm == "b" and w.round_no == 1 and slot.alive():
                p2run.HOST.kill(slot.server)
            return original(runner, w, slot, idle)

        with mock.patch.object(p2run.Runner, "run_window", kill_b_first):
            rc, rows, err = self.run_main(self.plan("rr-die", abort_after_consecutive=0, **self.RR), "rr-die")
        self.assertEqual(rc, 1, err)
        t = self.by_type(rows)
        got = {(w["m"], w["arm"], w["round"]): (w["status"], w["reason_codes"]) for w in t["window"]}
        for r in (1, 2):
            self.assertEqual(got[(10, "b", r)], ("invalid", ["server_died"]))
            self.assertEqual(got[(10, "a", r)], ("valid", []))
            self.assertEqual(got[(100, "b", r)], ("valid", []))  # a new server in the next cell
        m10 = {s["arm"]: s for s in t["cell_end"][0]["servers"]}
        self.assertEqual((m10["b"]["windows_count"], m10["b"]["reason_codes"], "memory" in m10["b"]), (False, ["server_died"], False))
        self.assertEqual((m10["a"]["windows_count"], m10["a"]["reason_codes"]), (True, []))
        self.assertIn("fake-server: start", m10["b"]["server_log_tail"])
        self.assertTrue(all(s["windows_count"] for s in t["cell_end"][1]["servers"]))
        self.assertEqual(self.end["servers_not_counting"], 1)

    def test_a_window_whose_servers_do_not_settle_runs_nothing(self) -> None:
        original = p2run.Runner.settle

        def never_for_b_in_round_2(runner, pids):
            out = original(runner, pids)
            return {**out, "quiet": False} if never_for_b_in_round_2.next_is_b else out

        def run_window(runner, w, slot=None, idle=None):
            never_for_b_in_round_2.next_is_b = w.arm == "b" and w.round_no == 2
            return p2run.Runner.run_window.__wrapped__(runner, w, slot, idle)

        never_for_b_in_round_2.next_is_b = False
        run_window.__wrapped__ = p2run.Runner.run_window
        with mock.patch.object(p2run.Runner, "settle", never_for_b_in_round_2), \
                mock.patch.object(p2run.Runner, "run_window", run_window):
            rc, rows, err = self.run_main(self.plan("rr-unsettled", sizes=[10], abort_after_consecutive=0, **self.RR),
                                          "rr-unsettled")
        self.assertEqual(rc, 1, err)
        t = self.by_type(rows)
        got = {(w["arm"], w["round"]): (w["reason_codes"], w["settle"]["quiet"], "generator" in w) for w in t["window"]}
        self.assertEqual(got[("b", 2)], (["unsettled"], False, False))
        self.assertEqual(got[("a", 2)], ([], True, True))
        self.assertTrue(all("settle" in r and r["settle"] == {"quiet": True} for r in t["warmup"]))
        self.assertNotIn("unsettled", p2run.RERUN_CODES | p2run.SYSTEMATIC)

    def test_a_server_that_exits_nonzero_on_the_cell_stop_does_not_count(self) -> None:
        rc, rows, err = self.run_main(self.plan("rr-badexit", sizes=[10], **self.RR), "rr-badexit", {"FAKE_SERVER": "badexit"})
        self.assertEqual(rc, 1, err)
        t = self.by_type(rows)
        self.assertTrue(all(w["status"] == "valid" for w in t["window"]))
        self.assertEqual({(s["exit"], s["windows_count"], tuple(s["reason_codes"])) for s in t["cell_end"][0]["servers"]},
                         {(3, False, ("server_exit",))})

    def test_an_interrupt_during_a_start_still_stops_that_server(self) -> None:
        calls, original = [], p2run.wait_ready

        def interrupt_the_fourth(proc, port, timeout_s, poll_s=0.01):
            calls.append(port)  # the preflight starts a and b, then the cell starts a, then b: interrupted
            if len(calls) == 4:
                raise KeyboardInterrupt
            return original(proc, port, timeout_s, poll_s)

        with mock.patch.object(p2run, "wait_ready", interrupt_the_fourth):
            rc, rows, err = self.run_main(self.plan("rr-int", sizes=[10], **self.RR), "rr-int")
        self.assertEqual((rc, self.end), (130, None), err)
        end = rows[-1]
        self.assertEqual(end["type"], "cell_end")
        self.assertEqual([(s["arm"], s["reason_codes"]) for s in end["servers"]], [("a", []), ("b", ["not_ready"])])
        self.assertTrue(all(s["exit"] is not None for s in end["servers"]))  # both were stopped
        for port in (s["port"] for s in end["servers"]):
            with socket.socket() as s:
                s.settimeout(0.5)
                self.assertNotEqual(s.connect_ex(("127.0.0.1", port)), 0)

    def test_a_server_that_never_starts_runs_no_window(self) -> None:
        rc, rows, err = self.run_main(self.plan("rr-refuse", sizes=[10], abort_after_consecutive=0, **self.RR), "rr-refuse",
                                      {"FAKE_SERVER": "refuse"})
        self.assertEqual(rc, 1, err)
        t = self.by_type(rows)
        self.assertEqual({(r["status"], tuple(r["reason_codes"])) for r in t["server"]}, {("invalid", ("not_ready",))})
        self.assertIn("refuses the table", t["server"][0]["server_log_tail"])
        self.assertEqual({tuple(r["reason_codes"]) for r in t["warmup"] + t["window"]}, {("not_ready",)})
        self.assertTrue(all("generator" not in r for r in t["warmup"] + t["window"]))
        self.assertEqual({tuple(s["reason_codes"]) for s in t["cell_end"][0]["servers"]}, {("not_ready",)})


class OrphanTests(unittest.TestCase):
    """A child must not outlive a runner that is killed. The runner stand-in spawns a child that holds a
    connection to this test, then dies without cleaning up; the connection must end."""

    def test_children_die_with_the_runner(self) -> None:
        if os.cpu_count() < 2:
            self.skipTest("needs two CPUs")
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(30)
        port = listener.getsockname()[1]
        child = f"import socket, time; s = socket.create_connection(('127.0.0.1', {port})); time.sleep(300)"
        runner = (f"import os, subprocess, sys; sys.path.insert(0, {str(HERE)!r}); import p2run; p2run.HOST.prepare(); "
                  f"print(p2run.HOST.job is not None if p2run.IS_WINDOWS else True, flush=True); "
                  f"p2run.HOST.spawn([sys.executable, '-c', {child!r}], (os.cpu_count() - 1,), env=os.environ, cwd='.', "
                  f"stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); import time; time.sleep(1); os._exit(0)")
        started = subprocess.Popen([sys.executable, "-c", runner], stdout=subprocess.PIPE)
        conn, _ = listener.accept()
        has_job = started.stdout.readline().strip() == b"True"
        started.wait(timeout=60)
        started.stdout.close()
        if not has_job:
            conn.close()
            listener.close()
            self.skipTest("no job object here (the test host forbids nesting)")
        conn.settimeout(30)
        try:
            self.assertEqual(conn.recv(1), b"")  # the child is gone: its end of the connection closed
        except ConnectionResetError:
            pass
        finally:
            conn.close()
            listener.close()


class WindowsLayoutTests(unittest.TestCase):
    @unittest.skipUnless(p2run.IS_WINDOWS, "Windows only")
    def test_job_struct_matches_the_documented_size(self) -> None:
        import ctypes
        self.assertEqual(ctypes.sizeof(p2run._JobExtended), 144)


class MainTests(unittest.TestCase):
    def test_dry_run_prints_the_sequence(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = p2run.main([str(HERE / "plans" / "example.json"), "--dry-run"])
        lines = buf.getvalue().splitlines()
        self.assertEqual(rc, 0)
        self.assertEqual(lines[-1], "windows: 7040")
        self.assertEqual(len(lines), 7041)
        self.assertIn("mixed-disjoint/m10/t111 mserver v2 1/22", lines[0])

    def test_bad_command_lines_exit_2(self) -> None:
        ex = str(HERE / "plans" / "example.json")
        for argv in ([ex], [ex, "--count", "0", "--out", "x.jsonl"], ["/no/such/plan.json", "--dry-run"]):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(p2run.main(argv), 2, argv)

    def test_the_module_has_no_dash_characters(self) -> None:
        for name in ("p2run.py", "test_p2run.py", "plans/example.json"):
            text = (HERE / name).read_text(encoding="utf-8")
            self.assertNotIn(chr(0x2013), text, name)
            self.assertNotIn(chr(0x2014), text, name)


if __name__ == "__main__":
    unittest.main(verbosity=1)
