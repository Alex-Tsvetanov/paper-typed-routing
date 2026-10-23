#!/usr/bin/env python3
"""p2run: the window runner of P2's end-to-end block (design/round3/end-to-end.md, sections 3, 5, 8, 9).

    p2run.py PLAN.json --out FILE.jsonl [--count N] [--workdir DIR] [--keep-logs]
    p2run.py PLAN.json --dry-run

It reimplements, for the frozen design only, what lab/t1/t1.py does for H6: a fresh server per
window, pinned to the server CPU; one probe of GET /; p2gen pinned to the generator CPUs; the
per-CPU busy time and the clock sampled over the measured window; the server stopped; one JSON
line per window. Python standard library only, plus ctypes on Windows.

Paths in a plan, and --out and --workdir, are made absolute against the directory the runner is
started in, because the programs run in the work directory.

Sequence. For each shape, for each size, for each seed pair, for each program: one mirrored round
over the program's arms (a, b, ..., z, z, ..., b, a). A plan lists the arms once, in the order a
to z. A window is one arm of one round.

Modes.
  timed (no --count)  the real runs, on the laptop only. Samples the CPUs and the clock.
  --count N           the desktop's functional mode. p2gen runs with --count N. Nothing is
                      sampled and no time, rate, latency, duration or start-up time is read for
                      any output: the output file holds counts, ports, CPU numbers and verdicts.
                      A window passes only if p2gen exits 0 (N answers, no error of any kind),
                      the probe answered, and the server exited 0 after the stop.
  --dry-run           prints the window sequence and the number of windows. Runs nothing.

Before the first window (both modes) a preflight checks the CPUs exist, the programs and every cell's
routes.txt and ring.txt are there (and equal the manifest's hashes), p2gen starts, and then it starts
every arm of every program once on a two-route table, pinned, probes GET /, and stops it: a program
or arm that does not start, does not answer, or does not stop on its stop signal fails the run here,
not in window 3,000. Those starts also give the session line each program's start-up lines (for the
Go and Rust programs their Go version or target CPU and a "v2 library ...: <build info>" line).
A program is one binary: every arm runs from it, the session line holds its sha256, a plan that
names one binary twice is refused, and a binary that changes during the run makes the window a fault.

Plan (JSON; keys starting with "_" are ignored; any other unknown key is an error).
  required
    "p2gen"      path of p2gen, or a list of strings (a command prefix)
    "data_root"  request sets, <shape>/m<m>/t<table seed>/ with routes.txt and ring.txt
    "shapes"     ["mixed-disjoint", ...]
    "sizes"      [10, 1000, ...]
    "pairs"      [[111, 211], ...] explicit [table seed, ring seed]
    "programs"   [{"name": "mserver",            default: the file stem of "path"
                   "path": "BIN",                a string, or a list (command prefix)
                   "arms": ["v2", "crow", "null"],   the first half of the mirrored round
                   "env": {"P2V2_DLL": "..."},   optional, added to the environment
                   "version": "router-list" | "startup-line"}]
                 version: router-list also records BIN --router ?? (the C++ server lists its external
                 arms' releases). startup-line: nothing more. Every program's start-up lines come
                 from the preflight starts. Default: router-list if the file stem is mserver.
    "cpus"       {"server": 14, "generator": "2-13"}   a number, a list or a range text
  optional (default)
    "housekeeping_cpus" (null)  the CPUs the runner's own threads pin themselves to, like lab/laptop's
                                core 0 ("0-1"), so the runner never runs on a server or generator CPU.
                                Required in timed mode.
    "abort_after_consecutive" (8)  the run stops (exit 3) when one systematic reason (a fault of the
                                runner or host, not an arm's overload) fails this many windows in a row
    "connections" (64)  "threads" (0 = one per generator CPU)  "warmup_s" (1.0)  "window_s" (5.0)
    "timeout_ms" (1000, p2gen's stall limit)  "ready_timeout_s" (60)  "stop_timeout_s" (20)
    "count_limit_s" (600, count mode: longest a p2gen run may take)
    "error_share_max" (0.001)  "generator_busy_max_pct" (90)  "clock_drift_max" (0.02)
    "session_clock_mhz" (null: sampled at the session start)  "verify_sets" (true: every cell's
    routes.txt and ring.txt are checked against data_root/manifest.tsv before the first window)

Output, JSON lines. The first is {"type": "session", ...}: host, OS, CPU model, versions of the
programs, hashes of the runner, p2gen and the programs, the plan, and in timed mode the session's
clock. Then one {"type": "window", ...} per window, with the cell, program, arm, order index,
port, the CPU masks read back from the OS, the probe, p2gen's own JSON line, the server's exit
code and how it was stopped, the verdict ("status": valid, overloaded or invalid, and the
reasons). Timed windows add the start-up seconds to readiness, the CPU busy shares and the mean
clock. Failed windows keep the tail of the server's log.

Validity (timed), as lab/t1: the server started and answered the probe with 200 and the 13-byte
body; at least one completed answer; errors at most 0.1% of the answers; the generator CPUs at
most 90% busy; the mean clock within 2% of the session's. Added here: the server is still
running when the window ends and exits 0 after the stop; p2gen reports no failed thread, no connect
error and no connection the server closed (peer_closes); p2gen reconnects only as often as its own
timeouts, connect errors and lost requests explain (each of those makes one reconnect, so a window
with timeouts is not made invalid by them; where there are such errors, as many more reconnects as
there are connections are allowed, for retries that fall across the window's edge); p2gen's line has
every key the verdict reads; the runner's sample span equals p2gen's window to 50 ms.
Overload rule (section 9): a window whose only failing rule is the error share,
where every error is a timeout or a request lost to a reset or close, is "overloaded", not
"invalid". A window that also fails another rule stays invalid.

Exit codes: 0 done (timed: every window ran, whatever its verdict); 1 count mode with a window
that did not pass; 2 a bad plan, command line or preflight check; 3 stopped by the consecutive-fault
rule (the record so far is kept).
"""
from __future__ import annotations

import argparse
import dataclasses
import functools
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

IS_WINDOWS = sys.platform == "win32"
BODY = b"Hello, World!"
MARKER_START = b"MEASURE_START"
MARKER_END = b"MEASURE_END"
SEED_PAIRS_HELP = "[[111, 211], ...]"
# Plan keys that are times or time limits. A count-mode session line does not echo them.
TIME_KEYS = frozenset({"warmup_s", "window_s", "timeout_ms", "ready_timeout_s", "stop_timeout_s",
                       "count_limit_s", "session_clock_mhz", "error_share_max",
                       "generator_busy_max_pct", "clock_drift_max"})
SPAN_TOLERANCE_S = 0.05  # the runner's sample span may differ from p2gen's window by this much
# Reason codes that point at the runner or the host, not at the arm. A run of them across windows
# means the campaign is broken, so the runner stops (abort_after_consecutive).
SYSTEMATIC = frozenset({"driver", "not_ready", "probe", "no_result", "generator_schema", "generator_failed", "sampler",
                        "server_exit", "server_died", "clock_drift", "generator_busy"})
TIMESTAMP = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}|\b\d{1,2}:\d{2}:\d{2}")
GENERATOR_GRACE_S = 30.0  # p2gen may overrun warm-up plus window by this long (t1.py's value)
SESSION_CLOCK_SAMPLES = 4
SESSION_CLOCK_GAP_S = 0.5


class PlanError(ValueError):
    """A plan, command line or preflight check that cannot run."""


# ---------------------------------------------------------------- CPU lists and masks


def parse_cpu_list(value: Any) -> tuple[int, ...]:
    """4, [2, 3], "2-13" or "0,2-3" as a tuple of distinct non-negative CPU numbers, in order."""
    if isinstance(value, bool):
        raise PlanError(f"not a CPU list: {value!r}")
    if isinstance(value, int):
        parts: list[int] = [value]
    elif isinstance(value, list):
        parts = [c for item in value for c in parse_cpu_list(item)]
    elif isinstance(value, str):
        parts = []
        for token in value.split(","):
            lo, dash, hi = token.strip().partition("-")
            if not lo.isdigit() or (dash and not hi.isdigit()):
                raise PlanError(f"not a CPU list: {value!r}")
            if dash and int(hi) < int(lo):
                raise PlanError(f"not a CPU list (a range runs upward): {value!r}")
            parts.extend(range(int(lo), int(hi) + 1) if dash else [int(lo)])
    else:
        raise PlanError(f"not a CPU list: {value!r}")
    if not parts or any(c < 0 for c in parts) or len(set(parts)) != len(parts):
        raise PlanError(f"a CPU list needs distinct non-negative numbers: {value!r}")
    return tuple(parts)


def cpus_to_mask(cpus: Sequence[int]) -> int:
    mask = 0
    for c in cpus:
        mask |= 1 << c
    return mask


def mask_to_cpus(mask: int) -> tuple[int, ...]:
    return tuple(i for i in range(mask.bit_length()) if (mask >> i) & 1)


# ---------------------------------------------------------------- plan


def binary_of(argv: Sequence[str]) -> str:
    """The file whose bytes are the program: the last argv element that is an existing file (the script of
    an interpreter-plus-script command), else argv[0]."""
    return next((a for a in reversed(argv) if Path(a).is_file()), argv[0])


@dataclasses.dataclass(frozen=True)
class Program:
    name: str
    argv: tuple[str, ...]
    arms: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    version: str  # "router-list" or "startup-line"

    @property
    def binary(self) -> str:
        return binary_of(self.argv)


@dataclasses.dataclass(frozen=True)
class Thresholds:
    error_share_max: float = 0.001
    generator_busy_max_pct: float = 90.0
    clock_drift_max: float = 0.02


@dataclasses.dataclass(frozen=True)
class Plan:
    p2gen: tuple[str, ...]
    data_root: str
    shapes: tuple[str, ...]
    sizes: tuple[int, ...]
    pairs: tuple[tuple[int, int], ...]
    programs: tuple[Program, ...]
    server_cpu: int
    generator_cpus: tuple[int, ...]
    connections: int
    threads: int
    warmup_s: float
    window_s: float
    timeout_ms: int
    ready_timeout_s: float
    stop_timeout_s: float
    count_limit_s: float
    thresholds: Thresholds
    session_clock_mhz: float | None
    verify_sets: bool
    housekeeping_cpus: tuple[int, ...]
    abort_after: int

    @property
    def generator_threads(self) -> int:
        return self.threads or len(self.generator_cpus)


_REQUIRED = ("p2gen", "data_root", "shapes", "sizes", "pairs", "programs", "cpus")
_DEFAULTS: Mapping[str, Any] = {
    "connections": 64, "threads": 0, "warmup_s": 1.0, "window_s": 5.0, "timeout_ms": 1000,
    "ready_timeout_s": 60.0, "stop_timeout_s": 20.0, "count_limit_s": 600.0,
    "error_share_max": 0.001, "generator_busy_max_pct": 90.0, "clock_drift_max": 0.02,
    "session_clock_mhz": None, "verify_sets": True, "housekeeping_cpus": None,
    "abort_after_consecutive": 8,
}


def _resolve(value: str) -> str:
    """The absolute form of a path the plan names (relative to the runner's directory). Children run in
    the work directory, so a relative path would mean another file to them. A bare command name such as
    python is left for the PATH lookup."""
    p = Path(value)
    return str(p.resolve()) if p.is_absolute() or "/" in value or os.sep in value or p.exists() else value


def _argv(value: Any, what: str) -> tuple[str, ...]:
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not items or not all(isinstance(s, str) and s for s in items):
        raise PlanError(f"{what}: want a path or a list of strings")
    return (_resolve(items[0]), *(_resolve(s) if Path(s).exists() else s for s in items[1:]))


def _number(d: Mapping[str, Any], key: str, lo: float, integer: bool = False) -> Any:
    v = d[key]
    ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= lo
    if integer:
        ok = ok and isinstance(v, int)
    if not ok:
        raise PlanError(f"{key}: want {'an integer' if integer else 'a number'} of at least {lo}, got {v!r}")
    return v


def _program(raw: Any) -> Program:
    if not isinstance(raw, dict):
        raise PlanError(f"a program is an object: {raw!r}")
    unknown = sorted(k for k in raw if not k.startswith("_") and k not in ("name", "path", "arms", "env", "version"))
    if unknown or "path" not in raw or "arms" not in raw:
        raise PlanError(f"program {raw.get('name', raw.get('path'))!r}: needs path and arms, and no other key than "
                        f"name, env, version (got {unknown}). A program is one binary and an arm is only a name")
    argv = _argv(raw["path"], "program path")
    arms = raw["arms"]
    if not isinstance(arms, list) or not arms or not all(isinstance(a, str) and a for a in arms) \
            or len(set(arms)) != len(arms):
        raise PlanError(f"program {argv[0]}: arms want a non-empty list of distinct names, got {arms!r}")
    env = raw.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise PlanError(f"program {argv[0]}: env wants an object of strings")
    name = raw.get("name") or Path(argv[0]).stem
    stem = Path(argv[0]).stem
    version = raw.get("version", "router-list" if stem == "mserver" else "startup-line")
    if version not in ("router-list", "startup-line"):
        raise PlanError(f"program {name}: version is router-list or startup-line, got {version!r}")
    env = {k: _resolve(v) if Path(v).exists() else v for k, v in env.items()}
    return Program(name, argv, tuple(arms), tuple(sorted(env.items())), version)


def _pairs(raw: Any) -> tuple[tuple[int, int], ...]:
    ok = isinstance(raw, list) and raw and all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(s, int) and not isinstance(s, bool) and s > 0 for s in p)
        for p in raw)
    if not ok or len({p[0] for p in raw}) != len(raw):
        raise PlanError(f"pairs want [table seed, ring seed] entries with distinct table seeds (a cell is named by "
                        f"its table seed), like {SEED_PAIRS_HELP}")
    return tuple((p[0], p[1]) for p in raw)


def parse_plan(raw: Any) -> Plan:
    if not isinstance(raw, dict):
        raise PlanError("a plan is a JSON object")
    known = set(_REQUIRED) | set(_DEFAULTS)
    unknown = sorted(k for k in raw if not k.startswith("_") and k not in known)
    missing = [k for k in _REQUIRED if k not in raw]
    if unknown or missing:
        raise PlanError(f"plan keys: unknown {unknown}, missing {missing}")
    d = {**_DEFAULTS, **{k: v for k, v in raw.items() if not k.startswith("_")}}
    shapes, sizes = d["shapes"], d["sizes"]
    if not isinstance(shapes, list) or not shapes or not all(isinstance(s, str) and s for s in shapes) \
            or len(set(shapes)) != len(shapes):
        raise PlanError(f"shapes want a non-empty list of distinct names, got {shapes!r}")
    if not isinstance(sizes, list) or not sizes or not all(isinstance(s, int) and not isinstance(s, bool) and s > 0
                                                          for s in sizes) or len(set(sizes)) != len(sizes):
        raise PlanError(f"sizes want a non-empty list of distinct positive integers, got {sizes!r}")
    if not isinstance(d["programs"], list) or not d["programs"]:
        raise PlanError("programs want a non-empty list")
    programs = tuple(_program(p) for p in d["programs"])
    if len({p.name for p in programs}) != len(programs):
        raise PlanError("program names must be distinct")
    identities = [Path(p.binary).stem for p in programs]
    if len(set(identities)) != len(identities) or len({p.binary for p in programs}) != len(programs):
        raise PlanError("two entries name one program (or one binary): a program is one binary, and every arm of "
                        "it runs from that binary")
    cpus = d["cpus"]
    if not isinstance(cpus, dict) or sorted(cpus) != ["generator", "server"]:
        raise PlanError('cpus wants {"server": N, "generator": LIST}')
    server = parse_cpu_list(cpus["server"])
    generator = parse_cpu_list(cpus["generator"])
    if len(server) != 1 or set(server) & set(generator):
        raise PlanError("cpus: one server CPU, and the generator CPUs must not include it")
    if d["session_clock_mhz"] is not None:
        _number(d, "session_clock_mhz", 1.0)
    for key, lo in (("warmup_s", 0.0), ("window_s", 0.01), ("ready_timeout_s", 0.1), ("stop_timeout_s", 0.1),
                    ("count_limit_s", 1.0), ("error_share_max", 0.0), ("generator_busy_max_pct", 0.0),
                    ("clock_drift_max", 0.0)):
        _number(d, key, lo)
    for key, lo in (("connections", 1), ("threads", 0), ("timeout_ms", 1), ("abort_after_consecutive", 0)):
        _number(d, key, lo, integer=True)
    for key, hi in (("threads", 1024), ("timeout_ms", 600_000), ("warmup_s", 3600), ("window_s", 3600)):
        if d[key] > hi:  # p2gen refuses more
            raise PlanError(f"{key}: p2gen accepts at most {hi}, got {d[key]}")
    if (d["threads"] or len(generator)) > d["connections"]:
        raise PlanError("more generator threads than connections: p2gen would run fewer threads than CPUs")
    if not isinstance(d["verify_sets"], bool) or not isinstance(d["data_root"], str) or not d["data_root"]:
        raise PlanError("verify_sets is true or false, data_root is a path")
    housekeeping = () if d["housekeeping_cpus"] is None else parse_cpu_list(d["housekeeping_cpus"])
    if set(housekeeping) & (set(server) | set(generator)):
        raise PlanError("housekeeping_cpus must not include a server or generator CPU")
    th = Thresholds(float(d["error_share_max"]), float(d["generator_busy_max_pct"]), float(d["clock_drift_max"]))
    return Plan(_argv(d["p2gen"], "p2gen"), str(Path(d["data_root"]).resolve()), tuple(shapes), tuple(sizes), _pairs(d["pairs"]), programs,
                server[0], generator, d["connections"], d["threads"], float(d["warmup_s"]), float(d["window_s"]),
                d["timeout_ms"], float(d["ready_timeout_s"]), float(d["stop_timeout_s"]), float(d["count_limit_s"]),
                th, None if d["session_clock_mhz"] is None else float(d["session_clock_mhz"]), d["verify_sets"],
                housekeeping, d["abort_after_consecutive"])


def load_plan(path: Path) -> tuple[Plan, bytes]:
    try:
        text = path.read_bytes()
        return parse_plan(json.loads(text)), text
    except OSError as e:
        raise PlanError(f"cannot read {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise PlanError(f"{path}: not JSON: {e}") from e


# ---------------------------------------------------------------- the window sequence


@dataclasses.dataclass(frozen=True)
class Window:
    seq: int
    shape: str
    m: int
    table_seed: int
    ring_seed: int
    program: str
    arm: str
    index: int  # position in the mirrored round, from 0
    half: int  # 1 for the first pass over the arms, 2 for the second
    round_length: int

    @property
    def cell(self) -> str:
        return f"{self.shape}/m{self.m}/t{self.table_seed}"


def mirrored(arms: Sequence[str]) -> tuple[str, ...]:
    """a, b, ..., z, z, ..., b, a."""
    if not arms:
        raise PlanError("a round needs at least one arm")
    return tuple(arms) + tuple(reversed(arms))


def windows(plan: Plan) -> Iterator[Window]:
    seq = 0
    for shape in plan.shapes:
        for m in plan.sizes:
            for table_seed, ring_seed in plan.pairs:
                for program in plan.programs:
                    order = mirrored(program.arms)
                    for index, arm in enumerate(order):
                        half = 1 if index < len(program.arms) else 2
                        yield Window(seq, shape, m, table_seed, ring_seed, program.name, arm, index, half, len(order))
                        seq += 1


def total_windows(plan: Plan) -> int:
    per_cell = sum(2 * len(p.arms) for p in plan.programs)
    return len(plan.shapes) * len(plan.sizes) * len(plan.pairs) * per_cell


# ---------------------------------------------------------------- validity


@dataclasses.dataclass(frozen=True)
class Observed:
    """Everything the verdict of one window rests on."""
    ready: bool
    probe: Mapping[str, Any] | None
    generator: Mapping[str, Any] | None  # p2gen's JSON line
    generator_exit: int | None
    server_alive_at_end: bool
    server_exit: int | None
    generator_busy_pct: float | None = None
    clock_mhz: float | None = None
    session_mhz: float | None = None
    span_s: float | None = None  # the runner's sample span over the window


@dataclasses.dataclass(frozen=True)
class Verdict:
    status: str  # valid, overloaded or invalid
    reasons: tuple[tuple[str, str], ...]  # (code, text)

    @property
    def valid(self) -> bool:
        return self.status == "valid"


_COUNT_KEYS = ("completed", "resolved", "errors_total", "thread_failed")
_MEASURE_KEYS = ("completed", "errors_total", "timeouts", "connect_errors", "peer_closes", "reconnects")


def missing_keys(g: Mapping[str, Any], counting: bool) -> list[str]:
    """The keys of p2gen's line a verdict needs. A key that is absent (an older or changed p2gen) would
    otherwise read as 0 and let a rule pass in silence."""
    if counting:
        return [k for k in _COUNT_KEYS if k not in g]
    m = g.get("measure")
    if not isinstance(m, dict):
        return ["measure"]
    lost = isinstance(m.get("errors"), dict) and "lost" in m["errors"]
    return ([f"measure.{k}" for k in _MEASURE_KEYS if k not in m] + ([] if lost else ["measure.errors.lost"])
            + [k for k in ("measure_wall_ns", "thread_failed", "connections") if k not in g])


def _count_reasons(g: Mapping[str, Any], n: int, exit_code: int | None) -> list[tuple[str, str]]:
    out = []
    if exit_code != 0:
        out.append(("generator_failed", f"p2gen exit code {exit_code}"))
    if g["completed"] != n or g["resolved"] != n or g["errors_total"] != 0 or g["thread_failed"]:
        out.append(("count", f"completed {g['completed']} of {n}, resolved {g['resolved']}, "
                             f"errors {g['errors_total']}, failed threads {g['thread_failed']}"))
    return out


def _timed_reasons(g: Mapping[str, Any], obs: Observed, th: Thresholds) -> list[tuple[str, str]]:
    out = []
    m = g["measure"]
    completed, errors = m["completed"], m["errors_total"]
    if completed == 0:
        out.append(("no_answers", "no completed answers"))
    attempts = completed + errors
    share = errors / attempts if attempts else 1.0
    if share > th.error_share_max:
        out.append(("error_share", f"errors {100 * share:.3f}% > {100 * th.error_share_max:g}%"))
    if m["connect_errors"] > 0:
        out.append(("connect_errors", f"{m['connect_errors']} connect errors in the window"))
    # A connection the server closed leaves the window with fewer than C connections, unseen by the error
    # rule unless a request was in flight. The generator's own timeouts and connect failures, and the
    # requests it lost, each cause one reconnect; more than that is a close it did not make. A retry can
    # fall on the other side of the window's edge from the timeout that caused it (counters go to the phase
    # the batch started in), by at most one per connection: so where there are errors at all, that many more
    # reconnects than errors are allowed. A window with no error allows none.
    if m["peer_closes"] > 0:
        out.append(("peer_closes", f"{m['peer_closes']} connections closed by the server"))
    explained = m["timeouts"] + m["connect_errors"] + m["errors"]["lost"]
    allowed = explained + (g["connections"] if explained else 0)
    if m["reconnects"] > allowed:
        out.append(("reconnects", f"{m['reconnects']} reconnects, {explained} explained by timeouts, connect "
                                  f"errors and lost requests"))
    if g["thread_failed"] or obs.generator_exit != 0:
        out.append(("generator_failed", f"p2gen exit code {obs.generator_exit}, failed threads {g['thread_failed']}"))
    if obs.generator_busy_pct is None or obs.clock_mhz is None or not obs.session_mhz:
        out.append(("sampler", "no CPU or clock sample over the window"))
        return out
    if obs.generator_busy_pct > th.generator_busy_max_pct:
        out.append(("generator_busy", f"generator CPUs {obs.generator_busy_pct:.1f}% busy > "
                                      f"{th.generator_busy_max_pct:g}%"))
    drift = abs(obs.clock_mhz - obs.session_mhz) / obs.session_mhz
    if drift > th.clock_drift_max:
        out.append(("clock_drift", f"mean clock {100 * drift:.2f}% from the session's > {100 * th.clock_drift_max:g}%"))
    wall = g["measure_wall_ns"]
    if obs.span_s is not None and wall and abs(obs.span_s - wall / 1e9) > SPAN_TOLERANCE_S:
        out.append(("sampler", f"the samples span {obs.span_s:.3f} s, p2gen's window {wall / 1e9:.3f} s"))
    return out


def _overloaded(g: Mapping[str, Any] | None) -> bool:
    """Only the error share failed, and every error is a timeout or a request lost to a reset or close."""
    m = (g or {}).get("measure") or {}
    errors = m.get("errors_total", 0)
    return errors > 0 and m.get("timeouts", 0) + (m.get("errors") or {}).get("lost", 0) == errors


def judge(obs: Observed, th: Thresholds, count: int | None = None) -> Verdict:
    """The verdict of one window. count is N in count mode, None in timed mode."""
    if not obs.ready:
        return Verdict("invalid", (("not_ready", "the server did not become ready"),))
    reasons: list[tuple[str, str]] = []
    probe = obs.probe or {}
    if probe.get("status") != 200 or not probe.get("body_ok"):
        reasons.append(("probe", f"probe returned status {probe.get('status')} body_ok {probe.get('body_ok')}"))
    absent = missing_keys(obs.generator, count is not None) if obs.generator is not None else []
    if obs.generator is None:
        if obs.probe is not None and not reasons:
            reasons.append(("no_result", "p2gen wrote no result"))
    elif absent:
        reasons.append(("generator_schema", f"p2gen's line lacks {absent}"))
    elif count is not None:
        reasons.extend(_count_reasons(obs.generator, count, obs.generator_exit))
    else:
        reasons.extend(_timed_reasons(obs.generator, obs, th))
    if not obs.server_alive_at_end:
        reasons.append(("server_died", f"the server had exited (code {obs.server_exit}) before the stop"))
    elif obs.server_exit != 0:
        reasons.append(("server_exit", f"server exit code {obs.server_exit} after the stop"))
    if not reasons:
        return Verdict("valid", ())
    only_errors = count is None and [c for c, _ in reasons] == ["error_share"] and _overloaded(obs.generator)
    return Verdict("overloaded" if only_errors else "invalid", tuple(reasons))


# ---------------------------------------------------------------- samples


@dataclasses.dataclass(frozen=True)
class Reading:
    span_s: float
    busy_s: Mapping[int, float]  # per CPU, over the span
    mhz: float | None


def generator_busy_pct(r: Reading, generator_cpus: Sequence[int]) -> float:
    """The generator CPUs' busy share in percent of their span: the figure the 90% rule compares."""
    return statistics.fmean(100.0 * r.busy_s[c] / r.span_s for c in generator_cpus)


def cpu_metrics(r: Reading, server_cpu: int, generator_cpus: Sequence[int]) -> dict[str, Any]:
    """Busy shares in percent of one CPU's span, rounded for the record."""
    pct = {c: 100.0 * b / r.span_s for c, b in r.busy_s.items()}
    gen = [pct[c] for c in generator_cpus]
    return {"span_s": round(r.span_s, 6), "busy_pct_by_cpu": {str(c): round(v, 2) for c, v in sorted(pct.items())},
            "server_busy_pct": round(pct[server_cpu], 2), "generator_busy_pct": round(generator_busy_pct(r, generator_cpus), 2),
            "generator_busy_max_cpu_pct": round(max(gen), 2)}


def parse_proc_stat(text: str, hz: int) -> dict[int, float]:
    """Busy seconds per CPU from /proc/stat: everything but idle and iowait (t1.py's rule)."""
    out = {}
    for line in text.splitlines():
        if line.startswith("cpu") and line[3:4].isdigit():
            f = line.split()
            d = [int(x) for x in f[1:]] + [0] * 8
            out[int(f[0][3:])] = (d[0] + d[1] + d[2] + d[5] + d[6] + d[7]) / hz
    return out


def parse_cpuinfo_mhz(text: str, cpus: Sequence[int]) -> list[float]:
    vals, current = [], None
    for line in text.splitlines():
        if line.startswith("processor"):
            current = int(line.split(":")[1])
        elif line.startswith("cpu MHz") and current in cpus:
            vals.append(float(line.split(":")[1]))
    return vals


def parse_processor_performance(raw: bytes, count: int) -> dict[int, float]:
    """Busy seconds per CPU from NtQuerySystemInformation(SystemProcessorPerformanceInformation).
    48 bytes per CPU: Idle, Kernel, User, Dpc, Interrupt (100 ns, 8 bytes each), count, padding.
    KernelTime includes the idle time, the DPC time and the interrupt time."""
    out = {}
    for c in range(count):
        idle, kernel, user = (int.from_bytes(raw[48 * c + 8 * k:48 * c + 8 * k + 8], "little", signed=True)
                              for k in range(3))
        out[c] = (kernel + user - idle) / 1e7
    return out


class LinuxSampler:
    """Per-CPU busy time from /proc/stat and the clock from /proc/cpuinfo, as t1.py."""

    def __init__(self, cpus: Sequence[int]) -> None:
        self.cpus = tuple(cpus)
        self._hz = os.sysconf("SC_CLK_TCK")
        self._start: tuple[float, dict[int, float], float] | None = None

    def _busy(self) -> dict[int, float]:
        with open("/proc/stat") as f:
            return parse_proc_stat(f.read(), self._hz)

    def _mhz(self) -> float:
        with open("/proc/cpuinfo") as f:
            vals = parse_cpuinfo_mhz(f.read(), self.cpus)
        if not vals:
            raise OSError("no cpu MHz for the measured CPUs in /proc/cpuinfo")
        return statistics.fmean(vals)

    def begin(self) -> None:
        self._start = None
        mhz = self._mhz()  # read before the window's first instant, not inside it
        busy = self._busy()
        self._start = (time.monotonic(), busy, mhz)

    def end(self) -> Reading:
        start, self._start = self._start, None
        if start is None:
            raise RuntimeError("end() without a successful begin()")
        t1 = time.monotonic()
        busy1 = self._busy()
        mhz1 = self._mhz()
        t0, busy0, mhz0 = start
        return Reading(t1 - t0, {c: busy1[c] - busy0[c] for c in self.cpus}, statistics.fmean((mhz0, mhz1)))

    def session_mhz(self) -> list[float]:
        out = []
        for _ in range(SESSION_CLOCK_SAMPLES):
            out.append(self._mhz())
            time.sleep(SESSION_CLOCK_GAP_S)
        return out

    def close(self) -> None:
        pass


@dataclasses.dataclass
class Spawned:
    proc: subprocess.Popen
    affinity: tuple[int, ...]  # the mask the OS reports, read back
    started_at: float  # time.monotonic() when the program was released to run


try:  # Linux only: a child that outlives a killed runner would hold its CPU and port
    import ctypes as _ct
    _PRCTL = _ct.CDLL(None, use_errno=True).prctl if sys.platform.startswith("linux") else None
except (ImportError, OSError, AttributeError):
    _PRCTL = None
_PR_SET_PDEATHSIG = 1


def _child_setup(wanted: set[int]) -> None:
    """Runs in the child between fork and exec: its CPU mask, and SIGKILL if the runner dies."""
    os.sched_setaffinity(0, wanted)
    if _PRCTL is not None:
        _PRCTL(_PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0)


class LinuxHost:
    name = "linux"

    def prepare(self) -> None:
        pass

    def cpu_count(self) -> int:
        return os.cpu_count() or 1

    def pin_thread(self, cpus: Sequence[int]) -> None:
        """Pins the calling thread (threads it creates later inherit the mask)."""
        os.sched_setaffinity(0, set(cpus))

    def cpu_model(self) -> str:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
        return platform.processor()

    def spawn(self, argv: Sequence[str], cpus: Sequence[int], *, env: Mapping[str, str], cwd: Path,
              stdout: Any, stderr: Any) -> Spawned:
        """Starts argv pinned to cpus from its first instruction (the child sets its own mask before
        exec). preexec_fn is safe here: this runner has no other thread alive at a spawn."""
        wanted = set(cpus)
        proc = subprocess.Popen(list(argv), env=dict(env), cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout,
                                stderr=stderr, start_new_session=True,
                                preexec_fn=lambda: _child_setup(wanted))
        started = time.monotonic()
        affinity = tuple(sorted(os.sched_getaffinity(proc.pid)))
        if set(affinity) != wanted:
            self.kill(Spawned(proc, affinity, started))
            raise RuntimeError(f"affinity of {argv[0]} reads back as {affinity}, wanted {sorted(wanted)}")
        return Spawned(proc, affinity, started)

    def stop(self, sp: Spawned, timeout_s: float) -> tuple[int | None, str]:
        """SIGTERM, then SIGKILL of the process group after timeout_s. Returns (exit code, method)."""
        p = sp.proc
        if p.poll() is not None:
            return p.returncode, "already_exited"
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=timeout_s)
            return p.returncode, "sigterm"
        except subprocess.TimeoutExpired:
            self.kill(sp)
            return p.returncode, "killed"
        except ProcessLookupError:
            p.wait()
            return p.returncode, "already_exited"

    def kill(self, sp: Spawned) -> None:
        try:
            os.killpg(sp.proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        sp.proc.kill()
        sp.proc.wait()

    def make_sampler(self, cpus: Sequence[int]) -> LinuxSampler:
        return LinuxSampler(cpus)


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _CREATE_SUSPENDED = 0x00000004
    # TERMINATE and SET_QUOTA (to join a job), SET_INFORMATION (affinity), QUERY_INFORMATION, SUSPEND_RESUME
    _PROCESS_RIGHTS = 0x0001 | 0x0100 | 0x0200 | 0x0400 | 0x0800
    _PDH_MORE_DATA = 0x800007D2
    _PDH_FMT_DOUBLE_NOCAP100 = 0x200 | 0x8000
    _PERF = "\\Processor Information(*)\\% Processor Performance"
    _FREQ = "\\Processor Information(*)\\Processor Frequency"

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _nt = ctypes.WinDLL("ntdll")
    _pdh = ctypes.WinDLL("pdh")
    for _fn, _args, _res in (
        (_k32.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        (_k32.CloseHandle, [wintypes.HANDLE], wintypes.BOOL),
        (_k32.SetProcessAffinityMask, [wintypes.HANDLE, ctypes.c_size_t], wintypes.BOOL),
        (_k32.GetProcessAffinityMask, [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t),
                                       ctypes.POINTER(ctypes.c_size_t)], wintypes.BOOL),
        (_k32.GetConsoleWindow, [], wintypes.HANDLE),
        (_k32.GetCurrentThread, [], wintypes.HANDLE),
        (_k32.CreateJobObjectW, [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        (_k32.SetInformationJobObject, [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        (_k32.AssignProcessToJobObject, [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        (_k32.SetThreadAffinityMask, [wintypes.HANDLE, ctypes.c_size_t], ctypes.c_size_t),
        (_k32.AllocConsole, [], wintypes.BOOL),
        (_k32.GetActiveProcessorCount, [wintypes.WORD], wintypes.DWORD),
        (_nt.NtResumeProcess, [wintypes.HANDLE], ctypes.c_long),
        (_nt.NtQuerySystemInformation, [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                        ctypes.POINTER(ctypes.c_ulong)], ctypes.c_long),
        (_pdh.PdhOpenQueryW, [wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)], wintypes.DWORD),
        (_pdh.PdhAddEnglishCounterW, [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_size_t,
                                      ctypes.POINTER(wintypes.HANDLE)], wintypes.DWORD),
        (_pdh.PdhCollectQueryData, [wintypes.HANDLE], wintypes.DWORD),
        (_pdh.PdhGetFormattedCounterArrayW, [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                             ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p], wintypes.DWORD),
        (_pdh.PdhCloseQuery, [wintypes.HANDLE], wintypes.DWORD),
    ):
        _fn.argtypes, _fn.restype = _args, _res

    _JOB_KILL_ON_CLOSE = 0x2000
    _JOB_EXTENDED_LIMIT_INFORMATION = 9

    class _JobBasic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _JobIo(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes",
                                                  "OtherBytes")]

    class _JobExtended(ctypes.Structure):
        _fields_ = [("Basic", _JobBasic), ("Io", _JobIo), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _FmtValue(ctypes.Structure):
        _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]

    class _FmtItem(ctypes.Structure):
        _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _FmtValue)]

    def _pdh_check(status: int, what: str) -> None:
        if status != 0:
            raise OSError(f"{what}: PDH status {status & 0xFFFFFFFF:#x}")

    class _Pdh:
        """One PDH query with wildcard-instance counters. Rate counters are means over the interval
        between two collections, so collect() at one instant and values() at the next gives the
        mean over the interval between them."""

        def __init__(self, paths: Sequence[str]) -> None:
            self.h = wintypes.HANDLE()
            _pdh_check(_pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.h)), "PdhOpenQueryW")
            self.counters: dict[str, Any] = {}
            for p in paths:
                c = wintypes.HANDLE()
                _pdh_check(_pdh.PdhAddEnglishCounterW(self.h, p, 0, ctypes.byref(c)), f"PdhAddEnglishCounterW {p}")
                self.counters[p] = c
            self.collect()

        def collect(self) -> None:
            _pdh_check(_pdh.PdhCollectQueryData(self.h), "PdhCollectQueryData")

        def values(self, path: str) -> dict[str, float]:
            c = self.counters[path]
            size, count = wintypes.DWORD(0), wintypes.DWORD(0)
            st = _pdh.PdhGetFormattedCounterArrayW(c, _PDH_FMT_DOUBLE_NOCAP100, ctypes.byref(size),
                                                   ctypes.byref(count), None)
            if st != _PDH_MORE_DATA:
                raise OSError(f"PdhGetFormattedCounterArrayW size query: PDH status {st:#x}")
            buf = (ctypes.c_byte * size.value)()
            _pdh_check(_pdh.PdhGetFormattedCounterArrayW(c, _PDH_FMT_DOUBLE_NOCAP100, ctypes.byref(size),
                                                         ctypes.byref(count), buf), "PdhGetFormattedCounterArrayW")
            items = ctypes.cast(buf, ctypes.POINTER(_FmtItem))
            return {items[i].szName: items[i].FmtValue.doubleValue for i in range(count.value)
                    if items[i].FmtValue.CStatus in (0, 1)}

        def close(self) -> None:
            _pdh.PdhCloseQuery(self.h)

    class WindowsSampler:
        """Per-CPU busy time from NtQuerySystemInformation and the clock from PDH's
        % Processor Performance times Processor Frequency, a mean over the window."""

        def __init__(self, cpus: Sequence[int]) -> None:
            self.cpus = tuple(cpus)
            self._pdh = _Pdh([_PERF, _FREQ])
            self._start: tuple[float, dict[int, float]] | None = None

        def _busy(self) -> dict[int, float]:
            n = _k32.GetActiveProcessorCount(0xFFFF)
            buf = (ctypes.c_byte * (48 * n))()
            got = ctypes.c_ulong()
            status = _nt.NtQuerySystemInformation(8, buf, len(buf), ctypes.byref(got))
            if status != 0:
                raise OSError(f"NtQuerySystemInformation(SystemProcessorPerformanceInformation): {status & 0xFFFFFFFF:#x}")
            return parse_processor_performance(bytes(buf), got.value // 48)

        def _mhz(self) -> float:
            perf, freq = self._pdh.values(_PERF), self._pdh.values(_FREQ)
            vals = [freq[f"0,{c}"] * perf[f"0,{c}"] / 100.0 for c in self.cpus if f"0,{c}" in perf and f"0,{c}" in freq]
            if len(vals) != len(self.cpus):
                raise OSError("PDH has no % Processor Performance or Processor Frequency for a measured CPU")
            return statistics.fmean(vals)

        def begin(self) -> None:
            self._start = None
            self._pdh.collect()
            busy = self._busy()
            self._start = (time.monotonic(), busy)

        def end(self) -> Reading:
            start, self._start = self._start, None
            if start is None:
                raise RuntimeError("end() without a successful begin()")
            t1 = time.monotonic()
            busy1 = self._busy()
            self._pdh.collect()
            mhz = self._mhz()
            t0, busy0 = start
            return Reading(t1 - t0, {c: busy1[c] - busy0[c] for c in self.cpus}, mhz)

        def session_mhz(self) -> list[float]:
            out = []
            self._pdh.collect()
            for _ in range(SESSION_CLOCK_SAMPLES):
                time.sleep(SESSION_CLOCK_GAP_S)
                self._pdh.collect()
                out.append(self._mhz())
            return out

        def close(self) -> None:
            self._pdh.close()

    class WindowsHost:
        name = "windows"

        def __init__(self) -> None:
            self.job = None

        def prepare(self) -> None:
            """Ctrl-Break reaches a child only through a console. A runner started without one (by a
            service or WMI) makes one, so the children it starts inherit it. Also a job object that kills
            every child when the runner's last handle to it closes, however the runner ends: no server is
            left holding its CPU and port. Best effort; a runner inside a job that forbids nesting goes
            without."""
            if not _k32.GetConsoleWindow():
                _k32.AllocConsole()
            if self.job:
                _k32.CloseHandle(self.job)
                self.job = None
            handle = _k32.CreateJobObjectW(None, None)
            if not handle:
                return
            info = _JobExtended()
            info.Basic.LimitFlags = _JOB_KILL_ON_CLOSE
            if _k32.SetInformationJobObject(handle, _JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                                            ctypes.sizeof(info)):
                self.job = handle
            else:
                _k32.CloseHandle(handle)

        def cpu_count(self) -> int:
            return os.cpu_count() or 1

        def pin_thread(self, cpus: Sequence[int]) -> None:
            """Pins the calling thread only: a new thread starts with the process's mask, so every
            thread of the runner calls this for itself."""
            if not _k32.SetThreadAffinityMask(_k32.GetCurrentThread(), cpus_to_mask(cpus)):
                raise ctypes.WinError(ctypes.get_last_error())

        def cpu_model(self) -> str:
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                    return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
            except OSError:
                return platform.processor()

        def spawn(self, argv: Sequence[str], cpus: Sequence[int], *, env: Mapping[str, str], cwd: Path,
                  stdout: Any, stderr: Any) -> Spawned:
            """Starts argv suspended, in its own process group, sets its affinity mask through its
            handle, reads the mask back, then resumes it: pinned from its first instruction."""
            proc = subprocess.Popen(list(argv), env=dict(env), cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout,
                                    stderr=stderr,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_SUSPENDED)
            handle = None
            try:
                handle = _k32.OpenProcess(_PROCESS_RIGHTS, False, proc.pid)
                if not handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                if not _k32.SetProcessAffinityMask(handle, cpus_to_mask(cpus)):
                    raise ctypes.WinError(ctypes.get_last_error())
                mine, system = ctypes.c_size_t(), ctypes.c_size_t()
                if not _k32.GetProcessAffinityMask(handle, ctypes.byref(mine), ctypes.byref(system)):
                    raise ctypes.WinError(ctypes.get_last_error())
                affinity = mask_to_cpus(mine.value)
                if set(affinity) != set(cpus):
                    raise RuntimeError(f"affinity of {argv[0]} reads back as {affinity}, wanted {sorted(cpus)}")
                if self.job:
                    _k32.AssignProcessToJobObject(self.job, handle)
                status = _nt.NtResumeProcess(handle)
                if status != 0:
                    raise OSError(f"NtResumeProcess: {status & 0xFFFFFFFF:#x}")
            except BaseException:
                proc.kill()  # never leave a suspended process holding a port
                proc.wait()
                raise
            finally:
                if handle:
                    _k32.CloseHandle(handle)
            return Spawned(proc, affinity, time.monotonic())

        def stop(self, sp: Spawned, timeout_s: float) -> tuple[int | None, str]:
            """Ctrl-Break to the child's process group, then TerminateProcess after timeout_s."""
            p = sp.proc
            if p.poll() is not None:
                return p.returncode, "already_exited"
            try:
                p.send_signal(signal.CTRL_BREAK_EVENT)
                p.wait(timeout=timeout_s)
                return p.returncode, "ctrl_break"
            except (subprocess.TimeoutExpired, OSError):
                p.kill()
                p.wait()
                return p.returncode, "killed"

        def kill(self, sp: Spawned) -> None:
            sp.proc.kill()
            sp.proc.wait()

        def make_sampler(self, cpus: Sequence[int]) -> WindowsSampler:
            return WindowsSampler(cpus)

    HOST: LinuxHost | WindowsHost = WindowsHost()
else:
    HOST = LinuxHost()


# ---------------------------------------------------------------- servers, probe, generator


def free_port() -> int:
    """A port the OS has just handed out, so no bound or lingering socket of this host holds it.
    The laptop's Windows has almost every port in its dynamic range, so a fixed range could clash."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(proc: subprocess.Popen, port: int, timeout_s: float, poll_s: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        with socket.socket() as s:
            s.settimeout(0.2)
            # A connect from the port to itself also succeeds (the OS may pick the very port as the source
            # when nothing listens); it is not the server.
            if s.connect_ex(("127.0.0.1", port)) == 0 and s.getsockname() != s.getpeername():
                return True
        time.sleep(poll_s)
    return False


def probe_server(port: int) -> dict[str, Any]:
    """One raw GET /, as t1.py: the status, the sizes and whether the body is the 13 bytes."""
    request = f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode()
    with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
        s.sendall(request)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        status = int(lines[0].split()[1]) if len(lines[0].split()) > 1 else 0
        headers = {}
        for line in lines[1:]:
            k, _, v = line.partition(b":")
            headers[k.decode(errors="replace").strip().lower()] = v.decode(errors="replace").strip()
        length = int(headers["content-length"]) if headers.get("content-length", "").isdigit() else -1
        while 0 <= length and len(rest) < length:
            chunk = s.recv(65536)
            if not chunk:
                break
            rest += chunk
    body = rest[:length] if length >= 0 else rest
    return {"status": status, "header_bytes": len(head) + 4, "body_bytes": len(body), "body_ok": body == BODY}


class MarkerReader(threading.Thread):
    """Reads p2gen's stdout. When a MEASURE_START or MEASURE_END line arrives it calls the hook at
    once, so the CPU and clock samples sit at the window's edges. A pipe cannot be polled with
    select on Windows, hence a thread. Joined before the next process is spawned."""

    def __init__(self, stream: Any, on_start: Callable[[], None] | None = None,
                 on_end: Callable[[], None] | None = None, pin: Callable[[], None] | None = None) -> None:
        super().__init__(daemon=True)
        self.stream, self.on_start, self.on_end, self.pin = stream, on_start, on_end, pin
        self.lines: list[str] = []
        self.errors: list[str] = []

    def run(self) -> None:
        if self.pin is not None:
            try:
                self.pin()
            except Exception as e:  # noqa: BLE001 - recorded; the markers must still be read
                self.errors.append(f"pin: {e!r}")
        for raw in iter(self.stream.readline, b""):
            self.lines.append(raw.decode(errors="replace").rstrip("\r\n"))
            hook = self.on_start if raw.startswith(MARKER_START) else self.on_end if raw.startswith(MARKER_END) else None
            if hook is None:
                continue
            try:
                hook()
            except Exception as e:  # noqa: BLE001 - recorded in the row; the pipe must still be drained
                self.errors.append(f"{raw.split()[0].decode()}: {e!r}")


@functools.cache
def cell_digests(cell: str) -> tuple[str, str]:
    """sha256 of the cell's routes.txt and ring.txt, hashed once per cell."""
    return sha256_file(Path(cell) / "routes.txt"), sha256_file(Path(cell) / "ring.txt")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tail(path: Path, n: int = 400) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - n))
            return f.read().decode(errors="replace")
    except OSError:
        return ""


KEEP_LOGS = False  # --keep-logs: D5's records keep every server log and p2gen output to scan them


def remove(path: Path) -> None:
    """Deletes scratch. A scanner may hold the file on Windows; that must not turn a window into a fault."""
    if KEEP_LOGS:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


WITHHELD = "<line withheld in count mode: it holds a date or time>"


def scrub(text: str, counting: bool) -> str:
    """Free text from a program (a log, a start-up line) can hold a time stamp. Count mode records none."""
    if not counting:
        return text
    return "\n".join(WITHHELD if TIMESTAMP.search(line) else line for line in text.splitlines())


def file_signature(path: str) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns
    except OSError:
        return None


# ---------------------------------------------------------------- the runner


class Runner:
    """Runs windows one at a time. In count mode (count is N) it samples nothing and records no time."""

    def __init__(self, plan: Plan, workdir: Path, count: int | None, sampler: Any, session_mhz: float | None) -> None:
        self.plan, self.workdir, self.count = plan, workdir, count
        self.sampler, self.session_mhz = sampler, session_mhz
        self.programs = {p.name: p for p in plan.programs}
        self._live: list[Spawned] = []
        # Every arm of a program runs from its one binary, and so must every window of the session.
        self._signatures = {b: s for b in (binary_of(plan.p2gen), *(p.binary for p in plan.programs))
                            if (s := file_signature(b)) is not None}

    @property
    def timed(self) -> bool:
        return self.count is None

    def run_window(self, w: Window) -> dict[str, Any]:
        row: dict[str, Any] = {"type": "window", "seq": w.seq, "cell": w.cell, "shape": w.shape, "m": w.m,
                               "table_seed": w.table_seed, "ring_seed": w.ring_seed, "program": w.program,
                               "arm": w.arm, "index": w.index, "half": w.half}
        if self.timed:
            row["started"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        try:
            self._window(w, row)
        except Exception as e:  # noqa: BLE001 - a driver fault becomes an invalid row, not the end of the campaign
            row.update(status="invalid", valid=False, reasons=[f"driver error: {e!r}"], reason_codes=["driver"])
        finally:
            for sp in self._live:
                if sp.proc.poll() is None:
                    HOST.kill(sp)
            self._live.clear()
        return row

    def _server_env(self, program: Program) -> dict[str, str]:
        return {**os.environ, **dict(program.env)}

    def _window(self, w: Window, row: dict[str, Any]) -> None:
        plan, program = self.plan, self.programs[w.program]
        changed = [b for b, s in self._signatures.items() if file_signature(b) != s]
        if changed:
            raise RuntimeError(f"a binary changed since the session started: {changed}")
        cell = Path(plan.data_root) / w.shape / f"m{w.m}" / f"t{w.table_seed}"
        row["routes_sha256"], row["ring_sha256"] = cell_digests(str(cell))
        port = free_port()
        row.update(port=port, server_cpu=plan.server_cpu, generator_cpus=list(plan.generator_cpus))
        log = self.workdir / f"{w.seq:06d}.server.log"
        cmd = [*program.argv, "--port", str(port), "--workers", "1", "--routes", str(cell / "routes.txt"),
               "--router", w.arm]
        with open(log, "wb") as out:
            server = HOST.spawn(cmd, (plan.server_cpu,), env=self._server_env(program), cwd=self.workdir,
                                stdout=out, stderr=subprocess.STDOUT)
        self._live.append(server)
        row["server_affinity"] = list(server.affinity)
        ready = wait_ready(server.proc, port, plan.ready_timeout_s)
        if self.timed and ready:
            row["startup_s"] = round(time.monotonic() - server.started_at, 4)
        probe, generator, gen_exit, reading = None, None, None, None
        if ready:
            try:
                probe = probe_server(port)
            except (OSError, ValueError) as e:
                probe = {"status": 0, "body_ok": False, "error": repr(e)}
            row["probe"] = probe
        if probe and probe["status"] == 200 and probe["body_ok"]:
            generator, gen_exit, reading = self._run_generator(w, row, port, cell)
        alive = server.proc.poll() is None
        server_exit, how = HOST.stop(server, plan.stop_timeout_s)
        row.update(server_exit=server_exit, stop_method=how)
        obs = self._observed(ready, probe, generator, gen_exit, alive, server_exit, reading, row)
        verdict = judge(obs, plan.thresholds, self.count)
        row.update(status=verdict.status, valid=verdict.valid, reasons=[t for _, t in verdict.reasons],
                   reason_codes=[c for c, _ in verdict.reasons])
        if verdict.status == "valid" and server_exit == 0:
            remove(log)
        else:
            row["server_log_tail"] = scrub(tail(log), self.count is not None)

    def _observed(self, ready: bool, probe: Any, generator: Any, gen_exit: int | None, alive: bool,
                  server_exit: int | None, reading: Reading | None, row: dict[str, Any]) -> Observed:
        busy = clock = span = None
        if reading is not None:
            busy = generator_busy_pct(reading, self.plan.generator_cpus)
            clock, span = reading.mhz, reading.span_s
            row["cpu"] = cpu_metrics(reading, self.plan.server_cpu, self.plan.generator_cpus)
            drift = abs(clock - self.session_mhz) / self.session_mhz if clock and self.session_mhz else None
            row["clock"] = {"mhz": None if clock is None else round(clock, 1), "session_mhz": self.session_mhz,
                            "drift": None if drift is None else round(drift, 5)}
        return Observed(ready, probe, generator, gen_exit, alive, server_exit, busy, clock, self.session_mhz, span)

    def _generator_cmd(self, port: int, cell: Path, result: Path) -> list[str]:
        p = self.plan
        cmd = [*p.p2gen, "--port", str(port), "--paths", str(cell / "ring.txt"), "--connections", str(p.connections),
               "--threads", str(p.generator_threads), "--cpus", ",".join(map(str, p.generator_cpus)),
               "--timeout-ms", str(p.timeout_ms), "--out", str(result)]
        if self.count is not None:
            return [*cmd, "--count", str(self.count)]
        return [*cmd, "--warmup", str(p.warmup_s), "--duration", str(p.window_s)]

    def _run_generator(self, w: Window, row: dict[str, Any], port: int, cell: Path):
        plan = self.plan
        result = self.workdir / f"{w.seq:06d}.gen.json"
        errlog = self.workdir / f"{w.seq:06d}.gen.err"
        taken: dict[str, Reading] = {}
        hooks = (self.sampler.begin, lambda: taken.__setitem__("r", self.sampler.end())) if self.timed else (None, None)
        with open(errlog, "wb") as err:
            gen = HOST.spawn(self._generator_cmd(port, cell, result), plan.generator_cpus, env=os.environ,
                             cwd=self.workdir, stdout=subprocess.PIPE, stderr=err)
        self._live.append(gen)
        row["generator_affinity"] = list(gen.affinity)
        pin = (lambda: HOST.pin_thread(plan.housekeeping_cpus)) if plan.housekeeping_cpus else None
        reader = MarkerReader(gen.proc.stdout, *hooks, pin=pin)
        reader.start()
        limit = plan.count_limit_s if not self.timed else plan.warmup_s + plan.window_s + GENERATOR_GRACE_S
        try:
            code = gen.proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            HOST.kill(gen)
            code = None
            row["generator_note"] = "p2gen killed at the limit" + ("" if not self.timed else f" of {limit:g} s")
        reader.join(10)
        if not reader.is_alive():
            gen.proc.stdout.close()
        reading = taken.get("r")
        if reader.errors:  # a hook that failed or did not run: the window has no sample
            row["sampler_errors"] = reader.errors
            reading = None
        parsed = None
        try:
            parsed = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            row["generator_stderr"] = scrub(tail(errlog), not self.timed)
        row["generator_exit"] = code
        if parsed is not None:
            row["generator"] = parsed
            remove(result)
        remove(errlog)
        return parsed, code, reading


# ---------------------------------------------------------------- session, preflight, main


SMOKE_ROUTES = "GET /a\nGET /b/{p0}\n"


def program_version(program: Program, env: Mapping[str, str]) -> dict[str, Any] | None:
    """What the C++ server lists for its external arms (--router ??). The other programs state their
    versions in their start-up lines, which the preflight start of each arm records."""
    if program.version != "router-list":
        return None
    try:
        p = subprocess.run([*program.argv, "--router", "??"], capture_output=True, timeout=30, env=dict(env),
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": repr(e)}
    return {"source": "--router ??", "lines": p.stdout.decode(errors="replace").strip().splitlines(), "exit": p.returncode}


def read_manifest(path: Path) -> dict[tuple[str, int, int], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    rows = (dict(zip(header, line.split("\t"), strict=True)) for line in lines[1:] if line.strip())
    return {(r["shape"], int(r["m"]), int(r["table_seed"])): r for r in rows}


def _check_cell(plan: Plan, manifest: Any, shape: str, m: int, table: int, ring: int) -> list[str]:
    cell = Path(plan.data_root) / shape / f"m{m}" / f"t{table}"
    if not (cell / "routes.txt").is_file() or not (cell / "ring.txt").is_file():
        return [f"{cell}: routes.txt or ring.txt is missing"]
    if manifest is None:
        return []
    row = manifest.get((shape, m, table))
    if row is None:
        return [f"{shape} m{m} t{table}: not in the manifest"]
    routes, ring_sha = cell_digests(str(cell))
    wrong = [k for k, ok in (("ring seed", row.get("ring_seed") == str(ring)), ("routes.txt", row.get("routes_sha256") == routes),
                             ("ring.txt", row.get("ring_sha256") == ring_sha)) if not ok]
    return [f"{cell}: {', '.join(wrong)} differ from the manifest"] if wrong else []


def static_problems(plan: Plan) -> list[str]:
    """Checks that start nothing: the CPUs exist, the programs and request sets are there and are the
    ones the manifest names."""
    problems: list[str] = []
    n = HOST.cpu_count()
    bad = [c for c in (plan.server_cpu, *plan.generator_cpus, *plan.housekeeping_cpus) if c >= n or (IS_WINDOWS and c > 63)]
    if bad:
        problems.append(f"CPUs {bad} do not exist on this host ({n} logical CPUs)")
    for argv in (plan.p2gen, *(p.argv for p in plan.programs)):
        for item in {argv[0], binary_of(argv)}:
            if not Path(item).is_file() and not shutil.which(item):
                problems.append(f"no such program: {item}")
    manifest = None
    if plan.verify_sets:
        try:
            manifest = read_manifest(Path(plan.data_root) / "manifest.tsv")
        except (OSError, ValueError, KeyError, IndexError) as e:
            problems.append(f"cannot read {plan.data_root}/manifest.tsv: {e!r} (or set verify_sets to false)")
    if not problems:
        for shape in plan.shapes:
            for m in plan.sizes:
                for table, ring in plan.pairs:
                    problems.extend(_check_cell(plan, manifest, shape, m, table, ring))
    return problems


def smoke_start(plan: Plan, program: Program, arm: str, workdir: Path, counting: bool) -> dict[str, Any]:
    """Starts one arm on a two-route table, pinned as in a window, probes it, stops it. No time is kept."""
    routes = workdir / "smoke-routes.txt"
    routes.write_text(SMOKE_ROUTES, encoding="utf-8", newline="\n")
    port = free_port()
    log = workdir / f"smoke-{program.name}-{arm}.log"
    cmd = [*program.argv, "--port", str(port), "--workers", "1", "--routes", str(routes), "--router", arm]
    with open(log, "wb") as out:
        sp = HOST.spawn(cmd, (plan.server_cpu,), env={**os.environ, **dict(program.env)}, cwd=workdir,
                        stdout=out, stderr=subprocess.STDOUT)
    record: dict[str, Any] = {"arm": arm, "affinity": list(sp.affinity)}
    try:
        record["ready"] = wait_ready(sp.proc, port, plan.ready_timeout_s)
        try:
            probe = probe_server(port) if record["ready"] else None
        except (OSError, ValueError):
            probe = None
        record["probe_ok"] = bool(probe and probe["status"] == 200 and probe["body_ok"])
    finally:
        record["exit"], record["stop_method"] = HOST.stop(sp, plan.stop_timeout_s)
    record["lines"] = scrub(tail(log, 4000), counting).splitlines()
    remove(log)
    return record


def smoke_problems(program: Program, record: Mapping[str, Any]) -> list[str]:
    who = f"{program.name} {record['arm']}"
    if not record["ready"]:
        last = record["lines"][-1] if record["lines"] else "no output"
        return [f"{who}: did not start (exit {record['exit']}): {last}"]
    out = []
    if not record["probe_ok"]:
        out.append(f"{who}: GET / did not answer 200 with the 13 bytes")
    if record["stop_method"] == "killed":
        out.append(f"{who}: did not stop on the stop signal (on Windows: no console to carry Ctrl-Break?)")
    elif record["exit"] != 0:
        out.append(f"{who}: exit code {record['exit']} after the stop signal")
    return out


def generator_problems(plan: Plan, workdir: Path) -> list[str]:
    """p2gen starts, pinned to the generator CPUs, and prints its usage."""
    with open(workdir / "p2gen-help.log", "wb") as out:
        sp = HOST.spawn([*plan.p2gen, "--help"], plan.generator_cpus, env=os.environ, cwd=workdir, stdout=out,
                        stderr=subprocess.STDOUT)
    try:
        code = sp.proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        HOST.kill(sp)
        code = None
    remove(workdir / "p2gen-help.log")
    return [] if code == 0 else [f"p2gen --help exited with {code}"]


def preflight(plan: Plan, workdir: Path, counting: bool) -> dict[str, list[dict[str, Any]]]:
    """Everything a long run must not discover in its last window: then every (program, arm) is started
    once, pinned, probed and stopped. Raises PlanError. Returns the start records by program."""
    problems = static_problems(plan)
    smoke: dict[str, list[dict[str, Any]]] = {}
    if not problems:
        if plan.housekeeping_cpus:
            HOST.pin_thread(plan.housekeeping_cpus)
        problems.extend(generator_problems(plan, workdir))
        for program in plan.programs:
            smoke[program.name] = []
            for arm in program.arms:
                record = smoke_start(plan, program, arm, workdir, counting)
                smoke[program.name].append(record)
                problems.extend(smoke_problems(program, record))
    if problems:
        more = f"; and {len(problems) - 12} more" if len(problems) > 12 else ""
        raise PlanError("preflight: " + "; ".join(problems[:12]) + more)
    return smoke


def _public(obj: Any) -> Any:
    """The plan as given, without its notes (keys that start with an underscore)."""
    if isinstance(obj, dict):
        return {k: _public(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_public(v) for v in obj]
    return obj


def session_line(plan: Plan, plan_text: bytes, count: int | None, clock: Mapping[str, Any] | None,
                 smoke: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    counting = count is not None
    plan_json = _public(json.loads(plan_text))
    if counting:
        plan_json = {k: v for k, v in plan_json.items() if k not in TIME_KEYS}
    programs = []
    for p in plan.programs:
        arms = list(smoke[p.name])
        started = next((a for a in arms if a["arm"] == "v2"), arms[0])  # the arm whose start-up names its library
        version = program_version(p, {**os.environ, **dict(p.env)})
        if version and counting:
            version["lines"] = scrub("\n".join(version.get("lines", [])), True).splitlines()

        def clean(lines: Sequence[str]) -> list[str]:
            return scrub("\n".join(lines), counting).splitlines()

        programs.append({"name": p.name, "argv": list(p.argv), "binary": p.binary, "arms": list(p.arms),
                         "env": dict(p.env), "sha256": sha256_file(Path(p.binary)) if Path(p.binary).is_file() else None,
                         "version": version, "startup_arm": started["arm"], "startup_lines": clean(started["lines"]),
                         "starts": [{**a, "lines": clean(a["lines"])} for a in arms]})
    gen_binary = binary_of(plan.p2gen)
    line = {"type": "session", "runner": "p2run.py", "runner_sha256": sha256_file(Path(__file__)),
            "mode": "count" if counting else "timed", "count": count, "python": platform.python_version(),
            "system": HOST.name, "os": platform.platform(), "host": platform.node(), "cpu_model": HOST.cpu_model(),
            "logical_cpus": HOST.cpu_count(), "windows": total_windows(plan), "plan": plan_json,
            "plan_sha256": hashlib.sha256(plan_text).hexdigest(),
            "p2gen": {"argv": list(plan.p2gen), "sha256": sha256_file(Path(gen_binary)) if Path(gen_binary).is_file() else None},
            "programs": programs}
    if clock is not None:
        line["clock"] = dict(clock)
        line["started"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return line


def session_clock(plan: Plan, sampler: Any) -> dict[str, Any]:
    """The clock the windows are compared with. From the plan when it names one (say, from the lab's
    pinned-state fingerprint); else sampled at the session start, which is right only on a host whose
    governor or power plan holds the clock fixed, as the lab's pinned state does."""
    if plan.session_clock_mhz is not None:
        return {"session_mhz": plan.session_clock_mhz, "source": "plan"}
    samples = sampler.session_mhz()
    return {"session_mhz": round(statistics.fmean(samples), 1), "samples_mhz": [round(s, 1) for s in samples],
            "source": "sampled at the session start"}


def dry_run(plan: Plan) -> int:
    try:
        for w in windows(plan):
            print(f"{w.seq + 1:6d} {w.cell} {w.program} {w.arm} {w.index + 1}/{w.round_length}")
        print(f"windows: {total_windows(plan)}")
        sys.stdout.flush()
    except BrokenPipeError:  # the reader (head, a pager) closed early
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


def _install_stop_handlers() -> dict[int, Any]:
    """A runner that is told to stop (SIGTERM, SIGHUP, Ctrl-Break) unwinds, so its children are killed."""
    def stop(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    saved: dict[int, Any] = {}
    for name in ("SIGTERM", "SIGHUP", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                saved[sig] = signal.signal(sig, stop)
            except (ValueError, OSError):  # not the main thread
                pass
    return saved


def _run_windows(plan: Plan, runner: Runner, sink: Any) -> int:
    """The window loop. Returns 0, 1 (count mode: a window did not pass) or 3 (the run was stopped because
    one systematic reason repeated in abort_after_consecutive windows in a row)."""
    tally: dict[str, int] = {}
    streak: dict[str, int] = {}
    total = total_windows(plan)
    code = 0
    for w in windows(plan):
        row = runner.run_window(w)
        sink.write(json.dumps(row) + "\n")
        sink.flush()
        tally[row["status"]] = tally.get(row["status"], 0) + 1
        print(f"[{w.seq + 1}/{total}] {w.cell} {w.program} {w.arm} {row['status']}"
              + (f": {'; '.join(row['reasons'])}" if row["reasons"] else ""), file=sys.stderr, flush=True)
        failing = set(row["reason_codes"]) & SYSTEMATIC if row["status"] == "invalid" else set()
        streak = {c: streak.get(c, 0) + 1 for c in failing}
        worst = max(streak, key=streak.get, default=None)
        if plan.abort_after and worst and streak[worst] >= plan.abort_after:
            print(f"p2run: stopped: {streak[worst]} windows in a row failed with {worst!r}; the record so far is kept",
                  file=sys.stderr)
            code = 3
            break
    print(f"p2run: {sum(tally.values())} windows, " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())), file=sys.stderr)
    if code == 0 and runner.count is not None and set(tally) - {"valid"}:
        code = 1
    return code


def run_all(plan: Plan, plan_text: bytes, out: Path, count: int | None, workdir: Path) -> int:
    if count is None and not plan.housekeeping_cpus:
        raise PlanError("timed mode needs housekeeping_cpus: the runner must not run on a server or generator CPU")
    if out.exists():
        raise PlanError(f"{out} exists; this runner does not append to or overwrite a record")
    HOST.prepare()
    workdir.mkdir(parents=True, exist_ok=True)
    smoke = preflight(plan, workdir, count is not None)
    sampler = None if count is not None else HOST.make_sampler((plan.server_cpu, *plan.generator_cpus))
    saved = _install_stop_handlers()
    try:
        clock = session_clock(plan, sampler) if sampler else None
        session = session_line(plan, plan_text, count, clock, smoke)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            sink = open(out, "x", encoding="utf-8", newline="\n")
        except FileExistsError as e:
            raise PlanError(f"{out} exists; this runner does not append to or overwrite a record") from e
        with sink:
            sink.write(json.dumps(session) + "\n")
            runner = Runner(plan, workdir, count, sampler, clock["session_mhz"] if clock else None)
            return _run_windows(plan, runner, sink)
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler if handler is not None else signal.SIG_DFL)
        if sampler:
            sampler.close()


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Window runner of P2's end-to-end block (see the module docstring).")
    ap.add_argument("plan", type=Path)
    ap.add_argument("--out", type=Path, help="the JSON lines file (must not exist)")
    ap.add_argument("--count", type=int, metavar="N", help="functional mode: p2gen --count N, nothing sampled or timed")
    ap.add_argument("--dry-run", action="store_true", help="print the window sequence and its length")
    ap.add_argument("--workdir", type=Path, help="server logs and p2gen results (default: OUT.work)")
    ap.add_argument("--keep-logs", action="store_true",
                    help="keep every server log and p2gen output in the work directory (D5's records)")
    a = ap.parse_args(argv)
    global KEEP_LOGS
    KEEP_LOGS = a.keep_logs
    try:
        if a.count is not None and not 1 <= a.count <= 1_000_000_000_000:
            raise PlanError("--count wants a number from 1 to 1000000000000")
        plan, text = load_plan(a.plan)
        if a.dry_run:
            return dry_run(plan)
        if a.out is None:
            raise PlanError("--out is required")
        out = a.out.resolve()  # children run in the work directory, so every path must be absolute
        return run_all(plan, text, out, a.count, (a.workdir or out.with_name(out.name + ".work")).resolve())
    except PlanError as e:
        print(f"p2run: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("p2run: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
