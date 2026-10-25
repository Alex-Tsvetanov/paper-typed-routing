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
            plan_dict(programs=[{"path": "/b1/mserver", "arms": ["a"], "name": "x"},
                                {"path": "/b2/mserver", "arms": ["b"], "name": "y"}]),  # two binaries, one program
            plan_dict(programs=[{"path": "/b1/mserver", "arms": ["a"], "name": "x"},
                                {"path": "/b1/mserver", "arms": ["b"], "name": "y"}]),  # one binary twice
            plan_dict(programs=[{"path": "/b/mserver", "arms": [{"name": "v2", "path": "/other/mserver"}]}]),
            plan_dict(programs=[]),
            plan_dict(programs=[{"path": "a", "arms": []}]),
            plan_dict(programs=[{"path": "a", "arms": ["x", "x"]}]),
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
        with mock.patch.object(p2run, "SESSION_CLOCK_SAMPLES", 1), mock.patch.object(p2run, "SESSION_CLOCK_GAP_S", 0.05):
            session = sampler.session_mhz()
        self.assertEqual(len(session), 1)
        self.assertGreater(session[0], 0.0)
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
                         {"sum_pct_of_one_cpu": 4.75, "unattributed": 1,
                          "top": [FakeLabrec.SVC, FakeLabrec.UPD], "started": [FakeLabrec.UPD]})

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
        s.end()
        with self.assertRaises(RuntimeError):  # a second end() would reuse the first window's start
            s.end()
        s.close()

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
        # count mode: no key that names a time, no clock or CPU sample, no float anywhere
        for row in rows:
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
        self.assertEqual({w["status"] for w in rows[1:]}, {"valid"})

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
