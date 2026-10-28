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
to z, or one arm twice for an A/A round (v2, v2, v2, v2: entry 0 first and last). A window is one
entry of one round.

Round-robin ("schedule": "round-robin"; decision 21). A contestant is one entry of a program's arm list
(an A/A plan's ["v2", "v2"] gives two; this schedule also takes one arm k > 2 times, k servers of one
build). For each shape, size and seed pair (a cell): every contestant's server starts once, in plan order,
pinned to the server CPU on a port of its own, and is probed (one {"type": "server", ...} line each); then
each gets one warm-up, p2gen for server_warmup_s with nothing sampled ({"type": "warmup", ...}); then
"rounds" rounds, each giving every contestant one window, in an order drawn for that round:
random.Random seeded with the text "<order_seed>:<shape>:<m>:<table seed>",
shuffled once per round, so the orders follow from the plan alone. The servers not under load sleep on
the server CPU; their CPU over each window comes from the same two process snapshots as "others" and is
kept in others.idle_servers, outside the others sum and never judged. After the cell's last round, with
rerun_host_faults, each round with a window invalid only for host reasons runs once more, whole and in its
order, while the servers still run ({"type": "rerun", ...} for the cell). Then each server's memory is
read and every server is stopped ({"type": "cell_end", ...}: per server its exit code, how it was stopped,
its memory in KiB, and whether its windows in the cell count: not when it never became ready, died, or did
not exit 0 on the stop). A window of a server that never became ready or has died runs nothing and is
invalid (not_ready, server_died). Before each warm-up and window the cell's servers settle: together they use
at most SETTLE_SHARE of one CPU, judged over the span since the last window or warm-up ended and then over
polls, for up to SETTLE_LIMIT_S; a window whose servers do not settle runs nothing and is invalid (unsettled).
An overloaded server keeps working through queued requests after its window, and on the shared server CPU
that work would fall into the next contestant's window. Server, warm-up and cell_end lines are not windows: the session's
"windows" and the end line count windows only, and only windows feed the consecutive-fault rule.
warmup_s is p2gen's lead-in before each window in both schedules.

Modes.
  timed (no --count)  the real runs, on the laptop only. Samples the CPUs and the clock, and
                      needs LAB_TOOLS, the lab job's tools folder (lab/laptop), for its labrec.py.
  --count N           the desktop's functional mode. p2gen runs with --count N. Nothing is
                      sampled and no time, rate, latency, duration or start-up time is read for
                      any output: the output file holds counts, ports, CPU numbers and verdicts
                      (and, round-robin, each server's memory).
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
                   "arms": ["v2", "crow", "null"],   the first half of the mirrored round; distinct,
                                                 or one arm twice (["v2", "v2"]: an A/A round, whose
                                                 rows tell the two apart by "entry"); round-robin also
                                                 takes one arm k > 2 times (k entries)
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
    "others_max_pct" (null: "others" recorded, not judged)  timed mode: a window is invalid when the
                                other processes took more than this share of one CPU, or when it has no
                                record of them (hypotheses-round3.md section 3)
    "rerun_host_faults" (false)  rerun once, after the last window, every round with a window invalid
                                for a host reason (RERUN_CODES); decision 18, see Reruns
    "schedule" ("mirrored")     or "round-robin" (see Round-robin), which also needs "rounds" (R per cell)
                                and "order_seed" (an integer); "server_warmup_s" (1.0) is each server's
                                one warm-up per cell there

Output, JSON lines. The first is {"type": "session", ...}: host, OS, CPU model, versions of the
programs, hashes of the runner, p2gen and the programs, the plan, the lab job's LAB_JOB_ID and
LAB_QUIET, and in timed mode the session's clock and labrec.py's hash. Then one {"type": "window",
...} per window, with the cell, program, arm, order index, port, the CPU masks read back from the
OS, the probe, p2gen's own JSON line, the server's exit code and how it was stopped, the verdict
("status": valid, overloaded or invalid, and the reasons). Timed windows add the start-up seconds
to readiness, the CPU busy shares, the mean clock, and "others": every other process's CPU from
just before p2gen starts to just after it exits (lab/laptop's process_shares, in aa_trial.py's
shape), judged only when the plan sets others_max_pct. Failed windows keep the tail of the server's log.
With rerun_host_faults, a {"type": "rerun", ...} line follows the last planned window: the rounds
rerun, each with the seqs and reason codes of its host faults, the windows of that round that failed
for an arm's reason, and the first seq and the number of its rerun windows. The rerun windows carry
"rerun": true and continue the seq numbers. The session line's "windows" counts the planned windows
only. The last line, {"type": "end", ...}, gives the exit code and the windows run by status (and,
with reruns, the rerun rounds that had a host fault again); a record without it did not finish.

Validity (timed), as lab/t1: the server started and answered the probe with 200 and the 13-byte
body; at least one completed answer; errors at most 0.1% of the answers; the generator CPUs at
most 90% busy; the mean clock within 2% of the session's. Added here: the server is still
running when the window ends and exits 0 after the stop; p2gen reports no failed thread, no connect
error and no connection the server closed (peer_closes); p2gen reconnects only as often as its own
timeouts, connect errors and lost requests explain (each of those makes one reconnect, so a window
with timeouts is not made invalid by them; where there are such errors, as many more reconnects as
there are connections are allowed, for retries that fall across the window's edge); p2gen's line has
every key the verdict reads; the runner's sample span equals p2gen's window to 50 ms; with
others_max_pct, the other processes' record exists and its sum, as recorded (two decimals), is at
most that share of one CPU.
Overload rule (section 9): a window whose only failing rule is the error share,
where every error is a timeout or a request lost to a reset or close, is "overloaded", not
"invalid". A window that also fails another rule stays invalid.

Reruns (rerun_host_faults; decision 18). After the last planned window, each round (one program's
mirrored round at one shape, size and pair) with a window invalid only for host reasons, every reason
code in RERUN_CODES (other processes above others_max_pct or no record of them; no CPU or clock
sample, or a sample span off p2gen's window), runs once more, whole and in the same order, in the
order the rounds first ran. The rerun replaces the round in the analysis; the original rows stay in
the record. A window that also failed for an arm's reason starts no rerun: a server that crashes on
Windows starts its error reporter, which shows as another process, and a rerun would give that arm a
second draw. A round whose invalid windows are all an arm's (error share, overload, a failed server)
is not rerun, and a rerun round is never rerun. No reruns follow a run stopped by the consecutive-fault
rule. The rerun pass counts its own consecutive faults from zero; "others" is one of them, since a
host busy for that many windows in a row is not the quiet host the method states.

Exit codes: 0 done (timed: every window ran, whatever its verdict); 1 count mode with a window, a
warm-up or a server (cell_end) that did not pass; 2 a bad plan, command line or preflight check; 3
stopped by the consecutive-fault rule (the record so far is kept).
"""
from __future__ import annotations

import argparse
import dataclasses
import functools
import hashlib
import importlib.util
import json
import math
import os
import platform
import random
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
                       "count_limit_s", "session_clock_mhz", "error_share_max", "server_warmup_s",
                       "generator_busy_max_pct", "clock_drift_max", "others_max_pct"})
SPAN_TOLERANCE_S = 0.05  # the runner's sample span may differ from p2gen's window by this much
# Reason codes that point at the runner or the host, not at the arm. A run of them across windows
# means the campaign is broken, so the runner stops (abort_after_consecutive).
SYSTEMATIC = frozenset({"driver", "not_ready", "probe", "no_result", "generator_schema", "generator_failed", "sampler",
                        "server_exit", "server_died", "clock_drift", "generator_busy", "others"})
# Reason codes of a host fault that decision 18 reruns once (rerun_host_faults): other processes' CPU, and
# the runner's own sampling. Never an arm's outcome.
RERUN_CODES = frozenset({"others", "sampler"})
TIMESTAMP = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}|\b\d{1,2}:\d{2}:\d{2}")
GENERATOR_GRACE_S = 30.0  # p2gen may overrun warm-up plus window by this long (t1.py's value)
SESSION_CLOCK_SAMPLES = 4  # Linux: /proc/cpuinfo read four times, 0.5 s apart
SESSION_CLOCK_GAP_S = 0.5
SESSION_CLOCK_PDH_S = 10.0  # Windows: one PDH interval, labrec's sample length (WindowsSampler.session_mhz)
OTHERS_TOP = 6  # the busiest other processes a timed window keeps, as lab/laptop/aa_trial.py
# Round-robin's settle step: before a window or warm-up the cell's servers together use at most this share of one
# CPU (the others guard's 10%) over the time since the last window ended, or over one poll; else it waits, up to
# the limit, after which the window is invalid ("unsettled"). An overloaded server keeps working through queued
# requests after its window; on the shared server CPU that work would fall into the next contestant's window.
SETTLE_SHARE = 0.10
SETTLE_POLL_S = 0.1
SETTLE_MIN_S = 0.05  # the shortest span a reading is judged over
SETTLE_LIMIT_S = 30.0


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
    others_max_pct: float | None = None  # None: other processes' CPU is recorded, not judged


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
    rerun_host_faults: bool = False
    schedule: str = "mirrored"  # or "round-robin" (decision 21)
    rounds: int = 0  # round-robin: R per cell
    order_seed: int = 0  # round-robin: the round orders are drawn from it
    server_warmup_s: float = 1.0  # round-robin: each server's one warm-up per cell

    @property
    def generator_threads(self) -> int:
        return self.threads or len(self.generator_cpus)

    @property
    def round_robin(self) -> bool:
        return self.schedule == "round-robin"


_REQUIRED = ("p2gen", "data_root", "shapes", "sizes", "pairs", "programs", "cpus")
_DEFAULTS: Mapping[str, Any] = {
    "connections": 64, "threads": 0, "warmup_s": 1.0, "window_s": 5.0, "timeout_ms": 1000,
    "ready_timeout_s": 60.0, "stop_timeout_s": 20.0, "count_limit_s": 600.0,
    "error_share_max": 0.001, "generator_busy_max_pct": 90.0, "clock_drift_max": 0.02,
    "session_clock_mhz": None, "verify_sets": True, "housekeeping_cpus": None,
    "abort_after_consecutive": 8, "others_max_pct": None, "rerun_host_faults": False,
    "schedule": "mirrored", "rounds": None, "order_seed": None, "server_warmup_s": 1.0,
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
    aa = isinstance(arms, list) and len(arms) >= 2 and all(a == arms[0] for a in arms)  # an A/A round: k entries
    if not isinstance(arms, list) or not arms or not all(isinstance(a, str) and a for a in arms) \
            or (len(set(arms)) != len(arms) and not aa):
        raise PlanError(f"program {argv[0]}: arms want a non-empty list of distinct names, or one name repeated "
                        f"(an A/A round), got {arms!r}")
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
    if d["others_max_pct"] is not None:
        _number(d, "others_max_pct", 0.0)
    if not isinstance(d["rerun_host_faults"], bool):
        raise PlanError(f"rerun_host_faults is true or false, got {d['rerun_host_faults']!r}")
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
    th = Thresholds(float(d["error_share_max"]), float(d["generator_busy_max_pct"]), float(d["clock_drift_max"]),
                    None if d["others_max_pct"] is None else float(d["others_max_pct"]))
    schedule = _schedule(d)
    if schedule[0] == "mirrored" and any(len(p.arms) > 2 and len(set(p.arms)) == 1 for p in programs):
        raise PlanError("a mirrored A/A round holds one name twice; more entries need the round-robin schedule")
    return Plan(_argv(d["p2gen"], "p2gen"), str(Path(d["data_root"]).resolve()), tuple(shapes), tuple(sizes), _pairs(d["pairs"]), programs,
                server[0], generator, d["connections"], d["threads"], float(d["warmup_s"]), float(d["window_s"]),
                d["timeout_ms"], float(d["ready_timeout_s"]), float(d["stop_timeout_s"]), float(d["count_limit_s"]),
                th, None if d["session_clock_mhz"] is None else float(d["session_clock_mhz"]), d["verify_sets"],
                housekeeping, d["abort_after_consecutive"], d["rerun_host_faults"], *schedule)


def _schedule(d: Mapping[str, Any]) -> tuple[str, int, int, float]:
    """schedule, rounds, order_seed and server_warmup_s. rounds and order_seed belong to round-robin only:
    a mirrored plan that names them is refused, so neither is read where it does nothing."""
    schedule = d["schedule"]
    if schedule not in ("mirrored", "round-robin"):
        raise PlanError(f"schedule is mirrored or round-robin, got {schedule!r}")
    _number(d, "server_warmup_s", 0.01)  # p2gen's shortest --duration
    if d["server_warmup_s"] > 3600:
        raise PlanError(f"server_warmup_s: p2gen accepts at most 3600, got {d['server_warmup_s']}")
    if schedule == "mirrored":
        if d["rounds"] is not None or d["order_seed"] is not None:
            raise PlanError("rounds and order_seed belong to the round-robin schedule")
        return schedule, 0, 0, float(d["server_warmup_s"])
    if d["rounds"] is None or d["order_seed"] is None:
        raise PlanError("the round-robin schedule needs rounds and order_seed")
    _number(d, "rounds", 1, integer=True)
    if not isinstance(d["order_seed"], int) or isinstance(d["order_seed"], bool):
        raise PlanError(f"order_seed: want an integer, got {d['order_seed']!r}")
    return schedule, d["rounds"], d["order_seed"], float(d["server_warmup_s"])


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
    rerun: bool = False  # a window of a round run again for a host fault (rerun_host_faults)
    round_no: int = 0  # round-robin: the round in the cell, from 1 (index is then the position in it); 0 if mirrored
    rr_entry: int = 0  # round-robin: the contestant's entry

    @property
    def round_key(self) -> tuple[str, int, int, str]:
        return self.shape, self.m, self.table_seed, self.program

    @property
    def cell(self) -> str:
        return f"{self.shape}/m{self.m}/t{self.table_seed}"

    @property
    def entry(self) -> int:
        """The arm's position in the plan's list: what tells an A/A round's two entries of one arm apart."""
        if self.round_no:
            return self.rr_entry
        return self.index if self.half == 1 else self.round_length - 1 - self.index


def mirrored(arms: Sequence[str]) -> tuple[str, ...]:
    """a, b, ..., z, z, ..., b, a."""
    if not arms:
        raise PlanError("a round needs at least one arm")
    return tuple(arms) + tuple(reversed(arms))


def _round(seq: int, shape: str, m: int, table_seed: int, ring_seed: int, program: Program,
           rerun: bool = False) -> Iterator[Window]:
    order = mirrored(program.arms)
    for index, arm in enumerate(order):
        half = 1 if index < len(program.arms) else 2
        yield Window(seq + index, shape, m, table_seed, ring_seed, program.name, arm, index, half, len(order), rerun)


@dataclasses.dataclass(frozen=True)
class Contestant:
    """Round-robin: one entry of a program's arm list, with a server of its own in each cell."""
    program: str
    arm: str
    entry: int


def contestants(plan: Plan) -> tuple[Contestant, ...]:
    return tuple(Contestant(p.name, arm, e) for p in plan.programs for e, arm in enumerate(p.arms))


Cell = tuple[str, int, int, int]  # shape, m, table seed, ring seed


def cells(plan: Plan) -> Iterator[Cell]:
    for shape in plan.shapes:
        for m in plan.sizes:
            for table_seed, ring_seed in plan.pairs:
                yield shape, m, table_seed, ring_seed


def round_orders(plan: Plan, shape: str, m: int, table_seed: int) -> list[tuple[Contestant, ...]]:
    """The cell's R orders: the contestants shuffled once per round by a generator seeded with a text, which
    random.seed hashes the same way in every Python 3 (version 2 seeding), so the plan alone fixes them."""
    rng = random.Random(f"{plan.order_seed}:{shape}:{m}:{table_seed}")
    out = []
    for _ in range(plan.rounds):
        order = list(contestants(plan))
        rng.shuffle(order)
        out.append(tuple(order))
    return out


def rr_round(seq: int, cell: Cell, round_no: int, order: Sequence[Contestant], rerun: bool = False) -> Iterator[Window]:
    shape, m, table_seed, ring_seed = cell
    for position, c in enumerate(order):
        yield Window(seq + position, shape, m, table_seed, ring_seed, c.program, c.arm, position, 0, len(order), rerun,
                     round_no, c.entry)


def windows(plan: Plan) -> Iterator[Window]:
    seq = 0
    if plan.round_robin:
        for cell in cells(plan):
            for round_no, order in enumerate(round_orders(plan, *cell[:3]), 1):
                yield from rr_round(seq, cell, round_no, order)
                seq += len(order)
        return
    for shape in plan.shapes:
        for m in plan.sizes:
            for table_seed, ring_seed in plan.pairs:
                for program in plan.programs:
                    yield from _round(seq, shape, m, table_seed, ring_seed, program)
                    seq += 2 * len(program.arms)


def rerun_windows(plan: Plan, rounds: Sequence[tuple[str, int, int, str]], first_seq: int) -> Iterator[Window]:
    """The windows of each round in rounds, (shape, m, table seed, program), run again in that order."""
    rings, programs = dict(plan.pairs), {p.name: p for p in plan.programs}
    seq = first_seq
    for shape, m, table_seed, name in rounds:
        yield from _round(seq, shape, m, table_seed, rings[table_seed], programs[name], rerun=True)
        seq += 2 * len(programs[name].arms)


def total_windows(plan: Plan) -> int:
    per_cell = plan.rounds * len(contestants(plan)) if plan.round_robin else sum(2 * len(p.arms) for p in plan.programs)
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
    others_pct: float | None = None  # other processes' CPU in percent of one CPU, None without a record


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
    if th.others_max_pct is not None:
        if obs.others_pct is None:
            out.append(("others", "no record of the other processes over the window"))
        elif not obs.others_pct <= th.others_max_pct:  # a NaN fails too
            out.append(("others", f"other processes {obs.others_pct:g}% of one CPU > {th.others_max_pct:g}%"))
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


def judge_warmup(obs: Observed, count: int | None = None) -> Verdict:
    """A round-robin warm-up's verdict: the server answered and p2gen ran. Nothing is sampled over a warm-up, and
    its errors are not judged: a server that cannot sustain the load shows that in its windows."""
    if not obs.ready:
        return Verdict("invalid", (("not_ready", "the server did not become ready"),))
    reasons: list[tuple[str, str]] = []
    probe = obs.probe or {}
    if probe.get("status") != 200 or not probe.get("body_ok"):
        reasons.append(("probe", f"probe returned status {probe.get('status')} body_ok {probe.get('body_ok')}"))
    g = obs.generator
    absent = missing_keys(g, count is not None) if g is not None else []
    if g is None:
        if not reasons:
            reasons.append(("no_result", "p2gen wrote no result"))
    elif absent:
        reasons.append(("generator_schema", f"p2gen's line lacks {absent}"))
    elif count is not None:
        reasons.extend(_count_reasons(g, count, obs.generator_exit))
    else:
        if g["measure"]["completed"] == 0:
            reasons.append(("no_answers", "no completed answers"))
        if g["thread_failed"] or obs.generator_exit != 0:
            reasons.append(("generator_failed", f"p2gen exit code {obs.generator_exit}, failed threads {g['thread_failed']}"))
    if not obs.server_alive_at_end:
        reasons.append(("server_died", f"the server had exited (code {obs.server_exit})"))
    return Verdict("invalid" if reasons else "valid", tuple(reasons))


# ---------------------------------------------------------------- samples


@dataclasses.dataclass(frozen=True)
class Reading:
    span_s: float
    busy_s: Mapping[int, float]  # per CPU, over the span
    mhz: float | None
    cpus_counted: int | None = None  # Windows: the measured CPUs with PDH clock data in the span


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


def pdh_mean_mhz(perf: Mapping[str, float], freq: Mapping[str, float], cpus: Sequence[int]) -> tuple[float, int]:
    """The mean clock over one PDH interval of the measured CPUs that have data in it, and how many do.
    Processor Frequency times % Processor Performance is 0 for a CPU without data: over 0.5 s the laptop's
    Windows gave 0 for 5 or 6 of 13 idle CPUs (p2r3-probe-w, 2026-10-25), and averaging those in made the
    session's clock 1,892 MHz against the windows' 3,175. So a 0 is left out, never averaged in."""
    keys = [f"0,{c}" for c in cpus]
    if any(k not in perf or k not in freq for k in keys):
        raise OSError("PDH has no % Processor Performance or Processor Frequency for a measured CPU")
    ran = [v for v in (freq[k] * perf[k] / 100.0 for k in keys) if v > 0]
    if not ran:
        raise OSError("no measured CPU has PDH clock data in the interval")
    return statistics.fmean(ran), len(ran)


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

    def process_cpu_s(self, pid: int) -> float:
        """The process's user and system CPU time in seconds (/proc/PID/stat, fields 14 and 15)."""
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")

    def memory(self, sp: Spawned) -> dict[str, int]:
        """The process's peak and current resident memory in KiB (/proc/PID/status: VmHWM, VmRSS)."""
        names = {"VmHWM": "peak_resident_kib", "VmRSS": "resident_kib"}
        out = {}
        with open(f"/proc/{sp.proc.pid}/status") as f:
            for line in f:
                key, _, value = line.partition(":")
                if key in names:
                    out[names[key]] = int(value.split()[0])
        if len(out) != len(names):
            raise OSError(f"/proc/{sp.proc.pid}/status lacks VmHWM or VmRSS")
        return out


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
        (_k32.K32GetProcessMemoryInfo, [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        (_k32.GetProcessTimes, [wintypes.HANDLE, *[ctypes.POINTER(ctypes.c_uint64)] * 4], wintypes.BOOL),
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

    class _MemoryCounters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS_EX
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    *((n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                      "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                      "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                                                      "PrivateUsage"))]

    _PROCESS_MEMORY_RIGHTS = 0x1000 | 0x0010  # QUERY_LIMITED_INFORMATION, VM_READ

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
        % Processor Performance times Processor Frequency, a mean over the window of the CPUs with
        data (pdh_mean_mhz). The session's clock is one PDH interval of SESSION_CLOCK_PDH_S."""

        def __init__(self, cpus: Sequence[int]) -> None:
            self.cpus = tuple(cpus)
            self._pdh = _Pdh([_PERF, _FREQ])
            self._start: tuple[float, dict[int, float]] | None = None
            self.session_counted: int | None = None
            self.session_interval_s: float | None = None

        def _busy(self) -> dict[int, float]:
            n = _k32.GetActiveProcessorCount(0xFFFF)
            buf = (ctypes.c_byte * (48 * n))()
            got = ctypes.c_ulong()
            status = _nt.NtQuerySystemInformation(8, buf, len(buf), ctypes.byref(got))
            if status != 0:
                raise OSError(f"NtQuerySystemInformation(SystemProcessorPerformanceInformation): {status & 0xFFFFFFFF:#x}")
            return parse_processor_performance(bytes(buf), got.value // 48)

        def _mhz(self) -> tuple[float, int]:
            return pdh_mean_mhz(self._pdh.values(_PERF), self._pdh.values(_FREQ), self.cpus)

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
            mhz, counted = self._mhz()
            t0, busy0 = start
            return Reading(t1 - t0, {c: busy1[c] - busy0[c] for c in self.cpus}, mhz, counted)

        def session_mhz(self) -> list[float]:
            """One interval as long as labrec's: over 10 s no idle CPU of the laptop lacked data (none of
            about 11,000 labrec readings in 10 Windows jobs was 0), over 0.5 s five or six of 13 did."""
            self._pdh.collect()
            t0 = time.monotonic()
            time.sleep(SESSION_CLOCK_PDH_S)
            self._pdh.collect()
            self.session_interval_s = time.monotonic() - t0
            mhz, self.session_counted = self._mhz()
            return [mhz]

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

        def process_cpu_s(self, pid: int) -> float:
            """The process's kernel and user CPU time in seconds (GetProcessTimes, 100 ns units)."""
            handle = _k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                created, exited, kernel, user = (ctypes.c_uint64() for _ in range(4))
                if not _k32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel),
                                            ctypes.byref(user)):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                _k32.CloseHandle(handle)
            return (kernel.value + user.value) / 1e7

        def memory(self, sp: Spawned) -> dict[str, int]:
            """The process's peak and current working set, its private bytes and its peak commit, in KiB."""
            handle = _k32.OpenProcess(_PROCESS_MEMORY_RIGHTS, False, sp.proc.pid)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                c = _MemoryCounters()
                c.cb = ctypes.sizeof(c)
                if not _k32.K32GetProcessMemoryInfo(handle, ctypes.byref(c), c.cb):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                _k32.CloseHandle(handle)
            return {"peak_resident_kib": c.PeakWorkingSetSize // 1024, "resident_kib": c.WorkingSetSize // 1024,
                    "private_kib": c.PrivateUsage // 1024, "peak_commit_kib": c.PeakPagefileUsage // 1024}

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


def load_labrec() -> Any:
    """lab/laptop's labrec.py from LAB_TOOLS, the lab job's tools folder: the lab's own record of the
    other processes around each timed window (lab/laptop/README.md, the procedure per job)."""
    path = Path(os.environ.get("LAB_TOOLS") or "") / "labrec.py"
    if not os.environ.get("LAB_TOOLS") or not path.is_file():
        raise PlanError("timed mode needs LAB_TOOLS, the lab's tools folder with labrec.py (lab/laptop)")
    spec = importlib.util.spec_from_file_location("labrec", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:  # noqa: BLE001 - any import failure refuses the run before its first window
        raise PlanError(f"timed mode: {path} does not import: {e!r}") from e
    for name in ("processes", "process_shares"):
        if not callable(getattr(module, name, None)):
            raise PlanError(f"timed mode: {path} has no {name}()")
    return module


def others_row(labrec: Any, start: list, end: list, wall_s: float, exclude: Sequence[int],
               idle: Mapping[int, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Every other process's CPU between two snapshots, in aa_trial.py's shape: the sum in percent of
    one CPU, the busiest few, and the busiest few that started in between. The verdict reads the sum
    only when the plan sets others_max_pct. Round-robin: idle maps the pid of each server not under load to
    its contestant; those processes go to "idle_servers", outside the sum, the lists and the verdict."""
    shares = labrec.process_shares(start, end, wall_s, exclude_pids=tuple(exclude))
    judged = [p for p in shares["judged"] if p["pid"] not in (idle or {})]
    others = [p for p in judged if p["cpu_percent"] > 0]
    row = {"sum_pct_of_one_cpu": round(sum(p["cpu_percent"] for p in others), 2), "top": others[:OTHERS_TOP],
           "started": [p for p in others if p["how"] == "started"][:OTHERS_TOP],
           "judged": len(judged), "unattributed": len(shares["unattributed"]), "wall_s": round(wall_s, 3)}
    if idle is not None:
        found = {p["pid"]: p["cpu_percent"] for p in shares["judged"] if p["pid"] in idle}
        servers = [{**who, "cpu_percent": found[pid]} for pid, who in idle.items() if pid in found]
        row["idle_servers"] = {"sum_pct_of_one_cpu": round(sum(found.values()), 2),
                               "max_pct_of_one_cpu": round(max(found.values(), default=0.0), 3), "servers": servers,
                               "missing": [dict(who) for pid, who in idle.items() if pid not in found]}
    return row


# ---------------------------------------------------------------- the runner


@dataclasses.dataclass
class Slot:
    """Round-robin: one contestant's server, kept for a whole cell."""
    contestant: Contestant
    cell: Cell
    cell_dir: Path
    port: int
    log: Path
    server: Spawned | None = None
    ready: bool = False

    def alive(self) -> bool:
        return self.server is not None and self.server.proc.poll() is None

    def who(self) -> dict[str, Any]:
        return {"program": self.contestant.program, "arm": self.contestant.arm, "entry": self.contestant.entry}


def cell_name(cell: Cell) -> str:
    return f"{cell[0]}/m{cell[1]}/t{cell[2]}"


class Runner:
    """Runs windows one at a time. In count mode (count is N) it samples nothing and records no time."""

    def __init__(self, plan: Plan, workdir: Path, count: int | None, sampler: Any, session_mhz: float | None,
                 labrec: Any = None) -> None:
        self.plan, self.workdir, self.count = plan, workdir, count
        self.sampler, self.session_mhz, self.labrec = sampler, session_mhz, labrec
        self.programs = {p.name: p for p in plan.programs}
        self._live: list[Spawned] = []
        self._cpu_mark: tuple[float, dict[int, float]] | None = None  # round-robin: servers' CPU when the last window ended
        # Every arm of a program runs from its one binary, and so must every window of the session.
        self._signatures = {b: s for b in (binary_of(plan.p2gen), *(p.binary for p in plan.programs))
                            if (s := file_signature(b)) is not None}

    @property
    def timed(self) -> bool:
        return self.count is None

    def run_window(self, w: Window, slot: Slot | None = None,
                   idle: Mapping[int, Mapping[str, Any]] | None = None) -> dict[str, Any]:
        """One window. Round-robin passes the contestant's running server (slot) and the servers not under
        load (idle: pid to contestant)."""
        row: dict[str, Any] = {"type": "window", "seq": w.seq, "cell": w.cell, "shape": w.shape, "m": w.m,
                               "table_seed": w.table_seed, "ring_seed": w.ring_seed, "program": w.program,
                               "arm": w.arm, "entry": w.entry}
        if w.round_no:
            row.update(round=w.round_no, position=w.index)
        else:
            row.update(index=w.index, half=w.half)
        if w.rerun:
            row["rerun"] = True
        if self.timed:
            row["started"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        try:
            if slot is None:
                self._window(w, row)
            else:
                self._rr_window(w, row, slot, idle or {})
        except Exception as e:  # noqa: BLE001 - a driver fault becomes an invalid row, not the end of the campaign
            row.update(status="invalid", valid=False, reasons=[f"driver error: {e!r}"], reason_codes=["driver"])
        finally:
            for sp in self._live:
                if sp.proc.poll() is None:
                    HOST.kill(sp)
            self._live.clear()
        return row

    def _processes(self, row: dict[str, Any]) -> list | None:
        """A snapshot of every process for "others" (timed mode with labrec only), or None."""
        if not self.timed or self.labrec is None:
            return None
        try:
            return self.labrec.processes()
        except Exception as e:  # noqa: BLE001 - kept in the row; the window has no record of the others
            row.setdefault("others_errors", []).append(repr(e))
            return None

    def _others(self, row: dict[str, Any], before: list, after: list | None, wall_s: float,
                also_mine: Sequence[int] = (), idle: Mapping[int, Mapping[str, Any]] | None = None) -> None:
        """row["others"] from two snapshots; a failure goes to others_errors and leaves no record, which
        makes the window invalid only under others_max_pct. also_mine: round-robin's server under load."""
        if after is None:
            return
        try:
            mine = (os.getpid(), *(sp.proc.pid for sp in self._live), *also_mine)
            row["others"] = others_row(self.labrec, before, after, wall_s, mine, idle)
        except Exception as e:  # noqa: BLE001 - the window keeps p2gen's result and lacks the record
            row.setdefault("others_errors", []).append(repr(e))

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
            if reading.cpus_counted is not None:
                row["clock"]["cpus_counted"] = reading.cpus_counted
        others = (row.get("others") or {}).get("sum_pct_of_one_cpu")
        others = others if isinstance(others, (int, float)) and not isinstance(others, bool) else None
        return Observed(ready, probe, generator, gen_exit, alive, server_exit, busy, clock, self.session_mhz, span,
                        others)

    def _generator_cmd(self, port: int, cell: Path, result: Path, duration_s: float | None = None) -> list[str]:
        p = self.plan
        cmd = [*p.p2gen, "--port", str(port), "--paths", str(cell / "ring.txt"), "--connections", str(p.connections),
               "--threads", str(p.generator_threads), "--cpus", ",".join(map(str, p.generator_cpus)),
               "--timeout-ms", str(p.timeout_ms), "--out", str(result)]
        if self.count is not None:
            return [*cmd, "--count", str(self.count)]
        return [*cmd, "--warmup", str(p.warmup_s), "--duration", str(p.window_s if duration_s is None else duration_s)]

    def _run_generator(self, w: Window | None, row: dict[str, Any], port: int, cell: Path, *, sample: bool = True,
                       also_mine: Sequence[int] = (), idle: Mapping[int, Mapping[str, Any]] | None = None,
                       duration_s: float | None = None, stem: str | None = None):
        """p2gen against the server on port. sample=False (a round-robin warm-up): no CPU, clock or process
        sample. stem names the scratch files when there is no window."""
        plan = self.plan
        stem = stem or f"{w.seq:06d}"
        result = self.workdir / f"{stem}.gen.json"
        errlog = self.workdir / f"{stem}.gen.err"
        taken: dict[str, Reading] = {}
        hooks = ((self.sampler.begin, lambda: taken.__setitem__("r", self.sampler.end())) if self.timed and sample
                 else (None, None))
        before = self._processes(row) if sample else None
        t0 = time.monotonic()
        with open(errlog, "wb") as err:
            gen = HOST.spawn(self._generator_cmd(port, cell, result, duration_s), plan.generator_cpus, env=os.environ,
                             cwd=self.workdir, stdout=subprocess.PIPE, stderr=err)
        self._live.append(gen)
        row["generator_affinity"] = list(gen.affinity)
        pin = (lambda: HOST.pin_thread(plan.housekeeping_cpus)) if plan.housekeeping_cpus else None
        reader = MarkerReader(gen.proc.stdout, *hooks, pin=pin)
        reader.start()
        span = plan.window_s if duration_s is None else duration_s
        limit = plan.count_limit_s if not self.timed else plan.warmup_s + span + GENERATOR_GRACE_S
        try:
            code = gen.proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            HOST.kill(gen)
            code = None
            row["generator_note"] = "p2gen killed at the limit" + ("" if not self.timed else f" of {limit:g} s")
        if before is not None:
            wall = time.monotonic() - t0
            self._others(row, before, self._processes(row), wall, also_mine, idle)
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

    # ------------------------------------------------ round-robin: a cell's servers, warm-ups and windows

    @staticmethod
    def _servers_cpu(pids: Sequence[int]) -> dict[int, float]:
        out = {}
        for pid in pids:
            try:
                out[pid] = HOST.process_cpu_s(pid)
            except (OSError, ValueError, IndexError):  # it has exited; its windows say so
                pass
        return out

    def mark_cpu(self, pids: Sequence[int]) -> None:
        """The cell's servers' CPU now, as a window or warm-up ends: the settle step's first reading."""
        self._cpu_mark = (time.monotonic(), self._servers_cpu(pids))

    def settle(self, pids: Sequence[int]) -> dict[str, Any]:
        """Waits until the cell's live servers (pids) together use at most SETTLE_SHARE of one CPU: judged over the
        span since the last mark, then over polls of SETTLE_POLL_S, for up to SETTLE_LIMIT_S. Count mode keeps only
        whether they settled."""
        t0 = time.monotonic()
        then, before = self._cpu_mark or (t0, self._servers_cpu(pids))
        self._cpu_mark = None
        while True:
            now, after = time.monotonic(), self._servers_cpu(pids)
            span = now - then
            if span < SETTLE_MIN_S:
                time.sleep(SETTLE_MIN_S - span)
                continue
            if sum(after[p] - before[p] for p in after.keys() & before.keys()) <= SETTLE_SHARE * span:
                quiet = True
                break
            if now - t0 >= SETTLE_LIMIT_S:
                quiet = False
                break
            then, before = now, after
            time.sleep(SETTLE_POLL_S)
        out: dict[str, Any] = {"quiet": quiet}
        if self.timed:
            out["settle_s"] = round(time.monotonic() - t0, 3)
        return out

    def _cell_row(self, kind: str, slot: Slot) -> dict[str, Any]:
        shape, m, table_seed, ring_seed = slot.cell
        return {"type": kind, "cell": cell_name(slot.cell), "shape": shape, "m": m, "table_seed": table_seed,
                "ring_seed": ring_seed, **slot.who(), "port": slot.port}

    def new_slot(self, c: Contestant, cell: Cell) -> Slot:
        """The contestant's slot in the cell, with its port, before anything starts: the caller keeps it first, so
        the cell's stop reaches a server whose start an interrupt cuts short."""
        cell_dir = Path(self.plan.data_root) / cell[0] / f"m{cell[1]}" / f"t{cell[2]}"
        return Slot(c, cell, cell_dir, free_port(), self.workdir / f"{cell[0]}-m{cell[1]}-t{cell[2]}-{c.program}-{c.entry}.server.log")

    def start_server(self, slot: Slot) -> dict[str, Any]:
        """Starts the slot's server, pinned, waits for it and probes GET /."""
        plan, c = self.plan, slot.contestant
        program, cell_dir = self.programs[c.program], slot.cell_dir
        row = self._cell_row("server", slot)
        row["server_cpu"] = plan.server_cpu
        cmd = [*program.argv, "--port", str(slot.port), "--workers", "1", "--routes", str(cell_dir / "routes.txt"),
               "--router", c.arm]
        try:
            with open(slot.log, "wb") as out:
                slot.server = HOST.spawn(cmd, (plan.server_cpu,), env=self._server_env(program), cwd=self.workdir,
                                         stdout=out, stderr=subprocess.STDOUT)
            row["server_affinity"] = list(slot.server.affinity)
            slot.ready = wait_ready(slot.server.proc, slot.port, plan.ready_timeout_s)
            if self.timed and slot.ready:
                row["startup_s"] = round(time.monotonic() - slot.server.started_at, 4)
            if slot.ready:
                try:
                    row["probe"] = probe_server(slot.port)
                except (OSError, ValueError) as e:
                    row["probe"] = {"status": 0, "body_ok": False, "error": repr(e)}
        except Exception as e:  # noqa: BLE001 - the contestant's windows in this cell become not_ready
            row["error"] = repr(e)
        if not slot.ready and slot.alive():  # still loading or hung: it must not share the server CPU with the windows
            HOST.kill(slot.server)
        probe = row.get("probe") or {}
        codes = [] if slot.ready and probe.get("status") == 200 and probe.get("body_ok") else \
            ["probe"] if slot.ready else ["not_ready"]
        row.update(ready=slot.ready, status="invalid" if codes else "valid", reason_codes=codes)
        if codes:
            row["server_log_tail"] = scrub(tail(slot.log), self.count is not None)
        return row

    def warm_up(self, slot: Slot, pids: Sequence[int] = ()) -> dict[str, Any]:
        """The server's one warm-up of the cell: p2gen for server_warmup_s, nothing sampled. pids: the cell's live
        servers, which settle first (an unsettled warm-up still runs: nothing is measured over it)."""
        row = self._cell_row("warmup", slot)
        probe = generator = gen_exit = None
        try:
            if slot.alive() and slot.ready:
                row["settle"] = self.settle(pids)
                try:
                    probe = probe_server(slot.port)
                except (OSError, ValueError) as e:
                    probe = {"status": 0, "body_ok": False, "error": repr(e)}
                row["probe"] = probe
                if probe["status"] == 200 and probe["body_ok"]:
                    stem = f"{slot.cell[0]}-m{slot.cell[1]}-t{slot.cell[2]}-{slot.contestant.program}-{slot.contestant.entry}.warmup"
                    generator, gen_exit, _ = self._run_generator(None, row, slot.port, slot.cell_dir, sample=False,
                                                                 duration_s=self.plan.server_warmup_s, stem=stem)
            alive = slot.alive()
            obs = Observed(slot.ready, probe, generator, gen_exit, alive,
                           None if alive or slot.server is None else slot.server.proc.returncode)
            verdict = judge_warmup(obs, self.count)
            row.update(status=verdict.status, reasons=[t for _, t in verdict.reasons],
                       reason_codes=[c for c, _ in verdict.reasons])
        except Exception as e:  # noqa: BLE001 - recorded; the contestant's windows still run if its server lives
            row.update(status="invalid", reasons=[f"driver error: {e!r}"], reason_codes=["driver"])
        finally:
            for sp in self._live:
                if sp.proc.poll() is None:
                    HOST.kill(sp)
            self._live.clear()
            self.mark_cpu(pids)
        return row

    def _rr_window(self, w: Window, row: dict[str, Any], slot: Slot, idle: Mapping[int, Mapping[str, Any]]) -> None:
        """A round-robin window on the contestant's running server; the server is left running."""
        plan = self.plan
        changed = [b for b, s in self._signatures.items() if file_signature(b) != s]
        if changed:
            raise RuntimeError(f"a binary changed since the session started: {changed}")
        row["routes_sha256"], row["ring_sha256"] = cell_digests(str(slot.cell_dir))
        row.update(port=slot.port, server_cpu=plan.server_cpu, generator_cpus=list(plan.generator_cpus))
        pids = [*idle, *([slot.server.proc.pid] if slot.alive() else [])]
        if not slot.ready:
            verdict = Verdict("invalid", (("not_ready", "the server did not become ready at the cell's start"),))
        elif not slot.alive():
            verdict = Verdict("invalid", (("server_died", f"the server had exited (code "
                                                          f"{slot.server.proc.returncode}) before the window"),))
        elif not (settled := self.settle(pids))["quiet"]:
            row["settle"] = settled
            verdict = Verdict("invalid", (("unsettled", f"the cell's servers used more than {100 * SETTLE_SHARE:g}% of "
                                                        f"one CPU for {SETTLE_LIMIT_S:g} s before the window"),))
        else:
            row["settle"] = settled
            row["server_affinity"] = list(slot.server.affinity)
            probe, generator, gen_exit, reading = None, None, None, None
            try:
                probe = probe_server(slot.port)
            except (OSError, ValueError) as e:
                probe = {"status": 0, "body_ok": False, "error": repr(e)}
            row["probe"] = probe
            if probe["status"] == 200 and probe["body_ok"]:
                generator, gen_exit, reading = self._run_generator(w, row, slot.port, slot.cell_dir,
                                                                   also_mine=(slot.server.proc.pid,), idle=idle)
            alive = slot.alive()
            obs = self._observed(True, probe, generator, gen_exit, alive, 0 if alive else slot.server.proc.returncode,
                                 reading, row)
            verdict = judge(obs, plan.thresholds, self.count)
        self.mark_cpu(pids)
        row.update(status=verdict.status, valid=verdict.valid, reasons=[t for _, t in verdict.reasons],
                   reason_codes=[c for c, _ in verdict.reasons])
        if {"server_died", "probe"} & set(row["reason_codes"]):
            row["server_log_tail"] = scrub(tail(slot.log), self.count is not None)

    def stop_servers(self, slots: Sequence[Slot], cell: Cell) -> dict[str, Any]:
        """Each server's memory, then its stop. A server's windows in the cell count only if it became ready,
        lived to the stop and exited 0 on it."""
        servers = []
        for slot in slots:
            rec: dict[str, Any] = {**slot.who(), "port": slot.port}
            codes = [] if slot.ready else ["not_ready"]
            try:
                if slot.server is not None:
                    alive = slot.alive()
                    if alive:
                        try:
                            rec["memory"] = HOST.memory(slot.server)
                        except (OSError, ValueError) as e:
                            rec["memory_error"] = repr(e)
                    rec["exit"], rec["stop_method"] = HOST.stop(slot.server, self.plan.stop_timeout_s)
                    if slot.ready and not alive:
                        codes.append("server_died")
                    elif slot.ready and rec["exit"] != 0:
                        codes.append("server_exit")
            except Exception as e:  # noqa: BLE001 - the other servers must still be stopped
                rec["error"] = repr(e)
                codes.append("driver")
            finally:
                if slot.server is not None and slot.server.proc.poll() is None:
                    HOST.kill(slot.server)
            rec.update(windows_count=not codes, reason_codes=codes)
            if codes:
                rec["server_log_tail"] = scrub(tail(slot.log), self.count is not None)
            else:
                remove(slot.log)
            servers.append(rec)
        return {"type": "cell_end", "cell": cell_name(cell), "shape": cell[0], "m": cell[1], "table_seed": cell[2],
                "servers": servers}


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
            for arm in dict.fromkeys(program.arms):  # an A/A round's one arm is started once
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
                 smoke: Mapping[str, Sequence[Mapping[str, Any]]], labrec: Any = None) -> dict[str, Any]:
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
            "programs": programs,
            # the lab's word that the host was quiet when the job started: "passed:<LAB_JOB_ID>" or absent
            "lab": {"job_id": os.environ.get("LAB_JOB_ID"), "quiet": os.environ.get("LAB_QUIET")}}
    if plan.round_robin:  # the contestants and every cell's round orders, as indices into the contestants
        everyone = contestants(plan)
        line["round_robin"] = {"contestants": [dataclasses.asdict(c) for c in everyone],
                               "orders": {cell_name(cell): [[everyone.index(c) for c in order]
                                                            for order in round_orders(plan, *cell[:3])]
                                          for cell in cells(plan)}}
    if labrec is not None:
        line["lab"]["labrec_sha256"] = sha256_file(Path(labrec.__file__))
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
    out = {"session_mhz": round(statistics.fmean(samples), 1), "samples_mhz": [round(s, 1) for s in samples],
           "source": "sampled at the session start"}
    counted = getattr(sampler, "session_counted", None)
    if isinstance(counted, int):  # Windows: one PDH interval, and how many measured CPUs had data in it
        span = getattr(sampler, "session_interval_s", None)
        out.update(cpus_counted=counted, interval_s=round(span, 3) if isinstance(span, float) else None)
    return out


def dry_run(plan: Plan) -> int:
    try:
        for w in windows(plan):
            where = f"round {w.round_no} {w.index + 1}/{w.round_length}" if w.round_no else f"{w.index + 1}/{w.round_length}"
            print(f"{w.seq + 1:6d} {w.cell} {w.program} {w.arm} {where}")
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


def host_faults(row: Mapping[str, Any]) -> list[str]:
    """The reason codes of an invalid window whose every reason is a host fault (RERUN_CODES), for which
    decision 18 reruns its round; else []. A window that also failed for an arm's reason is the arm's."""
    codes = set(row.get("reason_codes") or [])
    return sorted(codes) if row.get("status") == "invalid" and codes and codes <= RERUN_CODES else []


RoundKey = tuple[str, int, int, str]  # shape, m, table seed, program


def _rerun_line(plan: Plan, failed: Mapping[RoundKey, list[dict[str, Any]]], first_seq: int) -> dict[str, Any]:
    """The rounds to rerun, in the order they first ran: those with a window invalid only for host reasons,
    each with its host faults, its windows that failed for an arm's reason, and its rerun's seqs."""
    lengths = {p.name: 2 * len(p.arms) for p in plan.programs}
    rounds, seq = [], first_seq
    for key, bad in failed.items():
        host = [b for b in bad if b["host"]]
        if not host:
            continue
        rounds.append({"shape": key[0], "m": key[1], "table_seed": key[2], "program": key[3],
                       "seqs": [b["seq"] for b in host], "codes": sorted({c for b in host for c in b["host"]}),
                       "arm_faults": [{k: b[k] for k in ("seq", "status", "codes")} for b in bad if not b["host"]],
                       "first_seq": seq, "windows": lengths[key[3]]})
        seq += lengths[key[3]]
    return {"type": "rerun", "rounds": rounds, "windows": seq - first_seq}


def _run_windows(plan: Plan, runner: Runner, sink: Any) -> int:
    """The window loop, then (rerun_host_faults) one rerun of every round with a host fault, then the end
    line. Returns 0, 1 (count mode: a window did not pass) or 3 (the run was stopped because one systematic
    reason repeated in abort_after_consecutive windows in a row)."""
    # per phase: the windows run by status, and each round's windows that did not pass, in run order
    tallies: dict[str, dict[str, int]] = {"planned": {}, "rerun": {}}
    failed: dict[str, dict[RoundKey, list[dict[str, Any]]]] = {"planned": {}, "rerun": {}}

    def write(line: Mapping[str, Any]) -> None:
        sink.write(json.dumps(line) + "\n")
        sink.flush()

    def run(ws: Iterator[Window], total: int, phase: str) -> bool:
        streak: dict[str, int] = {}  # each phase counts its consecutive faults from zero
        tally = tallies[phase]
        for n, w in enumerate(ws, 1):
            row = runner.run_window(w)
            write(row)
            tally[row["status"]] = tally.get(row["status"], 0) + 1
            print(f"[{'rerun ' if w.rerun else ''}{n}/{total}] {w.cell} {w.program} {w.arm} {row['status']}"
                  + (f": {'; '.join(row['reasons'])}" if row["reasons"] else ""), file=sys.stderr, flush=True)
            if row["status"] != "valid":
                failed[phase].setdefault(w.round_key, []).append(
                    {"seq": w.seq, "status": row["status"], "codes": row["reason_codes"], "host": host_faults(row)})
            failing = set(row["reason_codes"]) & SYSTEMATIC if row["status"] == "invalid" else set()
            streak = {c: streak.get(c, 0) + 1 for c in failing}
            worst = max(streak, key=streak.get, default=None)
            if plan.abort_after and worst and streak[worst] >= plan.abort_after:
                print(f"p2run: stopped: {streak[worst]} windows in a row failed with {worst!r}; the record so far "
                      f"is kept", file=sys.stderr)
                return False
        return True

    planned = total_windows(plan)
    code = 0 if run(windows(plan), planned, "planned") else 3
    end: dict[str, Any] = {"type": "end"}
    if code == 0 and plan.rerun_host_faults:
        line = _rerun_line(plan, failed["planned"], planned)
        write(line)
        keys = [(r["shape"], r["m"], r["table_seed"], r["program"]) for r in line["rounds"]]
        print(f"p2run: rerunning {len(keys)} rounds with a host fault, {line['windows']} windows", file=sys.stderr)
        code = 0 if run(rerun_windows(plan, keys, planned), line["windows"], "rerun") else 3
        again = sum(any(b["host"] for b in bad) for bad in failed["rerun"].values())
        end["rerun"] = {"rounds": len(keys), "windows_run": sum(tallies["rerun"].values()),
                        "by_status": tallies["rerun"], "rounds_with_host_faults": again}
    everything = {k: tallies["planned"].get(k, 0) + tallies["rerun"].get(k, 0) for k in {*tallies["planned"], *tallies["rerun"]}}
    print(f"p2run: {sum(everything.values())} windows, " + ", ".join(f"{k} {v}" for k, v in sorted(everything.items())),
          file=sys.stderr)
    if code == 0 and runner.count is not None and set(everything) - {"valid"}:
        code = 1
    write({**end, "exit": code, "planned": {"windows": planned, "windows_run": sum(tallies["planned"].values()),
                                            "by_status": tallies["planned"]}})
    return code


class _Streak:
    """The consecutive-fault rule: one systematic reason failing abort_after windows in a row stops the run."""

    def __init__(self, abort_after: int) -> None:
        self.abort_after, self.counts = abort_after, {}

    def hit(self, row: Mapping[str, Any]) -> str | None:
        failing = set(row["reason_codes"]) & SYSTEMATIC if row["status"] == "invalid" else set()
        self.counts = {c: self.counts.get(c, 0) + 1 for c in failing}
        worst = max(self.counts, key=self.counts.get, default=None)
        return worst if self.abort_after and worst and self.counts[worst] >= self.abort_after else None


def _run_round_robin(plan: Plan, runner: Runner, sink: Any) -> int:
    """Round-robin: per cell the servers' starts, their warm-ups, the R rounds, the cell's reruns and the
    stops (see Round-robin). Returns 0, 1 (count mode: a window, a warm-up or a server did not pass) or 3
    (the consecutive-fault rule; the planned windows' streak runs across cells, each cell's rerun pass
    counts from zero)."""
    tallies: dict[str, dict[str, int]] = {"planned": {}, "rerun": {}, "warmup": {}}
    rerun_rounds = rerun_again = servers_failed = 0
    planned, seq = total_windows(plan), 0
    rerun_seq = planned
    streak = _Streak(plan.abort_after)

    def write(line: Mapping[str, Any]) -> None:
        sink.write(json.dumps(line) + "\n")
        sink.flush()

    def run(ws: Iterator[Window], slots: Mapping[tuple[str, int], Slot], phase: str, st: _Streak,
            failed: dict[int, list[dict[str, Any]]]) -> bool:
        for w in ws:
            slot = slots[(w.program, w.entry)]
            idle = {s.server.proc.pid: s.who() for s in slots.values() if s is not slot and s.alive()}
            row = runner.run_window(w, slot, idle)
            write(row)
            tallies[phase][row["status"]] = tallies[phase].get(row["status"], 0) + 1
            print(f"[{'rerun ' if w.rerun else ''}{w.cell} round {w.round_no} {w.index + 1}/{w.round_length}] "
                  f"{w.program} {w.arm} {row['status']}" + (f": {'; '.join(row['reasons'])}" if row["reasons"] else ""),
                  file=sys.stderr, flush=True)
            if row["status"] != "valid":
                failed.setdefault(w.round_no, []).append(
                    {"seq": w.seq, "status": row["status"], "codes": row["reason_codes"], "host": host_faults(row)})
            worst = st.hit(row)
            if worst:
                print(f"p2run: stopped: {st.counts[worst]} windows in a row failed with {worst!r}; the record so far "
                      f"is kept", file=sys.stderr)
                return False
        return True

    code, stopped_planned = 0, False
    for cell in cells(plan):
        slots: dict[tuple[str, int], Slot] = {}
        try:
            for c in contestants(plan):
                slot = slots[(c.program, c.entry)] = runner.new_slot(c, cell)
                write(runner.start_server(slot))

            def live() -> list[int]:
                return [s.server.proc.pid for s in slots.values() if s.alive()]

            runner.mark_cpu(live())  # the first warm-up's settle starts from here, not from the last cell
            for slot in slots.values():
                row = runner.warm_up(slot, live())
                write(row)
                tallies["warmup"][row["status"]] = tallies["warmup"].get(row["status"], 0) + 1
            orders = round_orders(plan, *cell[:3])
            failed: dict[int, list[dict[str, Any]]] = {}
            for round_no, order in enumerate(orders, 1):
                if not run(rr_round(seq, cell, round_no, order), slots, "planned", streak, failed):
                    code, stopped_planned = 3, True
                    break
                seq += len(order)
            if code == 0 and plan.rerun_host_faults:
                rounds, first = [], rerun_seq
                for round_no, bad in sorted(failed.items()):
                    host = [b for b in bad if b["host"]]
                    if host:
                        rounds.append({"round": round_no, "seqs": [b["seq"] for b in host],
                                       "codes": sorted({c for b in host for c in b["host"]}),
                                       "arm_faults": [{k: b[k] for k in ("seq", "status", "codes")} for b in bad if not b["host"]],
                                       "first_seq": first, "windows": len(orders[round_no - 1])})
                        first += len(orders[round_no - 1])
                write({"type": "rerun", "cell": cell_name(cell), "rounds": rounds, "windows": first - rerun_seq})
                again: dict[int, list[dict[str, Any]]] = {}
                rerun_streak = _Streak(plan.abort_after)
                for r in rounds:
                    rerun_rounds += 1
                    ok = run(rr_round(rerun_seq, cell, r["round"], orders[r["round"] - 1], rerun=True), slots, "rerun",
                             rerun_streak, again)
                    rerun_seq += r["windows"]
                    if not ok:
                        code = 3
                        break
                rerun_again += sum(any(b["host"] for b in bad) for bad in again.values())
        finally:
            line = runner.stop_servers(list(slots.values()), cell)
            write(line)
            servers_failed += sum(not s["windows_count"] for s in line["servers"])
        if code:
            break
    end: dict[str, Any] = {"type": "end"}
    if plan.rerun_host_faults and not stopped_planned:  # as mirrored: kept when a rerun pass was stopped
        end["rerun"] = {"rounds": rerun_rounds, "windows_run": sum(tallies["rerun"].values()),
                        "by_status": tallies["rerun"], "rounds_with_host_faults": rerun_again}
    windows_all = {k: tallies["planned"].get(k, 0) + tallies["rerun"].get(k, 0) for k in {*tallies["planned"], *tallies["rerun"]}}
    print(f"p2run: {sum(windows_all.values())} windows, " + ", ".join(f"{k} {v}" for k, v in sorted(windows_all.items()))
          + f"; servers whose windows do not count: {servers_failed}", file=sys.stderr)
    not_passed = (set(windows_all) | set(tallies["warmup"])) - {"valid"}
    if code == 0 and runner.count is not None and (not_passed or servers_failed):
        code = 1
    write({**end, "exit": code, "planned": {"windows": planned, "windows_run": sum(tallies["planned"].values()),
                                            "by_status": tallies["planned"]},
           "warmups": {"by_status": tallies["warmup"]}, "servers_not_counting": servers_failed})
    return code


def run_all(plan: Plan, plan_text: bytes, out: Path, count: int | None, workdir: Path) -> int:
    if count is None and not plan.housekeeping_cpus:
        raise PlanError("timed mode needs housekeeping_cpus: the runner must not run on a server or generator CPU")
    labrec = None if count is not None else load_labrec()
    if out.exists():
        raise PlanError(f"{out} exists; this runner does not append to or overwrite a record")
    HOST.prepare()
    workdir.mkdir(parents=True, exist_ok=True)
    smoke = preflight(plan, workdir, count is not None)
    sampler = None if count is not None else HOST.make_sampler((plan.server_cpu, *plan.generator_cpus))
    saved = _install_stop_handlers()
    try:
        try:
            clock = session_clock(plan, sampler) if sampler else None
        except OSError as e:  # no clock to compare the windows with: refused before the first window
            raise PlanError(f"the session clock: {e}") from e
        session = session_line(plan, plan_text, count, clock, smoke, labrec)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            sink = open(out, "x", encoding="utf-8", newline="\n")
        except FileExistsError as e:
            raise PlanError(f"{out} exists; this runner does not append to or overwrite a record") from e
        with sink:
            sink.write(json.dumps(session) + "\n")
            runner = Runner(plan, workdir, count, sampler, clock["session_mhz"] if clock else None, labrec)
            return (_run_round_robin if plan.round_robin else _run_windows)(plan, runner, sink)
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
