#!/usr/bin/env python3
"""T1 driver: paired, interleaved arms on loopback, disjoint physical cores, sequential stopping.

One call of run_cell() measures one cell (a server core count, a pipelining depth and a
load mode) for two or more arms. The first arm is the reference. Arms run in mirrored
rounds, A B C .. C B A, so each arm's two windows in a round are centred on the same
instant and a linear drift cancels in the ratio of their means. For two arms a round is
exactly ABBA. One round is one pair.

Window: the server starts fresh on its cores and is probed with one raw request (status,
header and body bytes recorded); the generator runs a 1 s warm-up and a 5 s measured
window; the server is snapshotted (/proc schedstat, status, and perf stat through a
control fifo) at the generator's MEASURE_START and MEASURE_END markers; the server stops.

Req/s is always completed 2xx responses over the measured wall time, both raw numbers
from the generator. No tool's own rate line is read.

Stopping (closed-loop cells): after --min-pairs rounds, stop when, for every
non-reference arm, the 95 percent bootstrap CI of the paired throughput ratio lies
wholly outside [0.98, 1.02] or has half-width below 1 percent; otherwise continue to
--max-pairs (rounds). With --valid-pairs-only only rounds whose windows are all valid count
toward the minimum and the stop; without it (the default, as P1 ran) every round with req/s
counts. The paired ratio of a round is mean(req/s of the arm) / mean(req/s of the
reference) over the round; the CI is a percentile bootstrap of the geometric mean of the
per-round ratios. With three pairs the percentile CI is close to the sample range, so
the half-width rule can fire on three close windows; that is the rule as specified.

Validity (rule 4 of the lab): a window is invalid, and listed rather than dropped, if its
error share exceeds 0.1 percent, if the generator used more than 90 percent of its CPUs
on a saturation cell, or if the mean CPU MHz over the server and generator CPUs drifts
more than 2 percent from the session value. Generator CPU percent is its CPU seconds in
the window over (window seconds times the number of generator logical CPUs).

Placement: the physical core holding cpu0 is left to the OS, this driver and perf. The
server gets the highest N physical cores, one logical CPU each (the SMT sibling idles),
and N workers. The generator gets every logical CPU of the remaining physical cores, one
thread per logical CPU. Sibling sets are recorded in every row.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import selectors
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import resource  # Linux only; report.py imports this module on any host
except ImportError:  # pragma: no cover
    resource = None

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
PERF_EVENTS = "instructions,cycles,context-switches,task-clock,raw_syscalls:sys_enter"
EXPECTED_BODY = b"Hello, World!"


class CellError(RuntimeError):
    pass


# ------------------------------------------------------------------ host

def physical_cores() -> list[list[int]]:
    cores: dict[tuple[int, int], list[int]] = {}
    for d in glob.glob("/sys/devices/system/cpu/cpu[0-9]*"):
        cpu = int(os.path.basename(d)[3:])
        online = Path(d, "online")
        if online.exists() and online.read_text().strip() == "0":
            continue
        pkg = int(Path(d, "topology/physical_package_id").read_text())
        core = int(Path(d, "topology/core_id").read_text())
        cores.setdefault((pkg, core), []).append(cpu)
    return sorted((sorted(v) for v in cores.values()), key=lambda c: c[0])


def allocate(server_cores: int) -> dict:
    cores = physical_cores()
    house, rest = cores[0], cores[1:]
    if server_cores >= len(rest):
        raise CellError(
            f"{server_cores} server cores leave no disjoint physical core for the generator "
            f"({len(cores)} physical cores, core {house} reserved for the OS and the driver)")
    srv, gen = rest[-server_cores:], rest[:-server_cores]
    gen_cpus = [c[0] for c in gen] + [cpu for c in gen for cpu in c[1:]]
    return {
        "housekeeping_core": house,
        "server_cores": srv,
        "server_cpus": [c[0] for c in srv],
        "server_idle_siblings": [cpu for c in srv for cpu in c[1:]],
        "generator_cores": gen,
        "generator_cpus": gen_cpus,
        "sibling_sets": cores,
    }


def cpu_mhz(cpus: list[int]) -> float:
    vals, cur = [], None
    with open("/proc/cpuinfo") as f:
        for line in f:
            if line.startswith("processor"):
                cur = int(line.split(":")[1])
            elif line.startswith("cpu MHz") and cur in cpus:
                vals.append(float(line.split(":")[1]))
    return statistics.fmean(vals) if vals else float("nan")


def cpu_times() -> dict[int, list[int]]:
    """Per-CPU /proc/stat counters (USER_HZ ticks)."""
    out = {}
    with open("/proc/stat") as f:
        for line in f:
            if line.startswith("cpu") and line[3].isdigit():
                parts = line.split()
                out[int(parts[0][3:])] = [int(x) for x in parts[1:]]
    return out


def busy_seconds(t0: dict, t1: dict, cpus: list[int]) -> tuple[float, float]:
    """Non-idle and softirq seconds over a CPU set. The kernel has IRQ time accounting, so
    softirq work (on loopback, the TCP receive path of the peer) never shows up in any
    task's runtime; only these counters see it."""
    hz = os.sysconf("SC_CLK_TCK")
    busy = soft = 0
    for c in cpus:
        d = [b - a for a, b in zip(t0[c], t1[c])]
        busy += d[0] + d[1] + d[2] + d[5] + d[6] + d[7]
        soft += d[6]
    return busy / hz, soft / hz


def pin_fingerprint() -> dict:
    p = subprocess.run(["bash", str(LAB / "bin" / "pin.sh")], capture_output=True, text=True)
    try:
        fp = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise CellError(f"pin.sh printed no fingerprint: {p.stdout!r} {p.stderr!r}")
    fp["pin_exit"] = p.returncode
    return fp


def raise_nofile() -> None:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < hard:
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))


# ------------------------------------------------------------------ server

def load_arms(path: Path) -> dict:
    return {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")}


def fill(template: str, **kw) -> str:
    return template.format(**kw)


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def start_server(arm: dict, build: Path, workers: int, port: int, cpus: list[int], log: Path):
    cmd = [fill(a, build=build, workers=workers, port=port) for a in arm["cmd"]]
    env = dict(os.environ)
    env.update({k: fill(v, build=build, workers=workers, port=port) for k, v in arm.get("env", {}).items()})
    taskset = ["taskset", "-c", ",".join(map(str, cpus))]
    out = open(log, "wb")
    # The window's own directory as working directory: Drogon creates an uploads tree in
    # whatever directory it starts in.
    proc = subprocess.Popen(taskset + cmd, stdout=out, stderr=subprocess.STDOUT, env=env,
                            start_new_session=True, cwd=log.parent)
    out.close()
    return proc, cmd


def wait_ready(proc, port: int, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        with socket.socket() as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.05)
    return False


def probe(port: int) -> dict:
    """One raw request; returns status, header and body bytes and the header names."""
    req = f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode()
    with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
        s.sendall(req)
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
            headers[k.decode().strip().lower()] = v.decode().strip()
        clen = int(headers.get("content-length", "-1"))
        while clen >= 0 and len(rest) < clen:
            chunk = s.recv(65536)
            if not chunk:
                break
            rest += chunk
    body = rest[:clen] if clen >= 0 else rest
    return {
        "status": status,
        "header_bytes": len(head) + 4,
        "body_bytes": len(body),
        "body_ok": body == EXPECTED_BODY,
        "headers": [ln.decode(errors="replace") for ln in lines],
    }


def stop_process(proc, grace: float = 3.0) -> int | None:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    return proc.returncode


def proc_snapshot(pid: int) -> dict:
    snap = {"t": time.monotonic(), "run_ns": 0, "ctx_vol": 0, "ctx_invol": 0, "threads": 0}
    stat = Path(f"/proc/{pid}/stat").read_text()
    fields = stat[stat.rindex(")") + 2:].split()
    snap["cpu_ticks"] = int(fields[11]) + int(fields[12])
    for task in glob.glob(f"/proc/{pid}/task/*"):
        try:
            snap["run_ns"] += int(Path(task, "schedstat").read_text().split()[0])
            for line in Path(task, "status").read_text().splitlines():
                if line.startswith("voluntary_ctxt_switches"):
                    snap["ctx_vol"] += int(line.split()[1])
                elif line.startswith("nonvoluntary_ctxt_switches"):
                    snap["ctx_invol"] += int(line.split()[1])
            snap["threads"] += 1
        except (FileNotFoundError, ProcessLookupError, IndexError, ValueError):
            pass
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith(("VmHWM", "VmRSS")):
            snap[line.split(":")[0]] = int(line.split()[1])
    return snap


# ------------------------------------------------------------------ perf

class Perf:
    """perf stat -p PID, counting only between enable() and disable() (control fifo)."""

    def __init__(self, pid: int, workdir: Path):
        self.dir = Path(tempfile.mkdtemp(prefix="t1perf.", dir=workdir))
        self.ctl, self.ack, self.out = self.dir / "ctl", self.dir / "ack", self.dir / "perf.csv"
        os.mkfifo(self.ctl)
        os.mkfifo(self.ack)
        self.proc = subprocess.Popen(
            ["sudo", "-n", "perf", "stat", "-p", str(pid), "-e", PERF_EVENTS, "-x", ",",
             "-o", str(self.out), "--control", f"fifo:{self.ctl},{self.ack}", "-D", "-1"],
            stdout=subprocess.DEVNULL, stderr=open(self.dir / "perf.err", "wb"))
        self.ctl_fd = self._open(self.ctl, os.O_WRONLY)
        self.ack_fd = self._open(self.ack, os.O_RDONLY) if self.ctl_fd is not None else None

    def _open(self, path: Path, flags: int, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return None
            try:
                return os.open(path, flags | os.O_NONBLOCK)
            except OSError:
                time.sleep(0.02)
        return None

    @property
    def ok(self) -> bool:
        return self.ctl_fd is not None and self.ack_fd is not None

    def _cmd(self, word: str) -> None:
        if not self.ok:
            return
        os.write(self.ctl_fd, (word + "\n").encode())
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                if os.read(self.ack_fd, 64):
                    return
            except BlockingIOError:
                pass
            time.sleep(0.001)

    def enable(self) -> None:
        self._cmd("enable")

    def disable(self) -> None:
        self._cmd("disable")

    def finish(self, timeout: float = 10.0) -> dict:
        """Call after the target has exited: perf then writes its counts and exits."""
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for fd in (self.ctl_fd, self.ack_fd):
            if fd is not None:
                os.close(fd)
        counts = {}
        if self.out.exists():
            for line in self.out.read_text().splitlines():
                parts = line.split(",")
                if len(parts) < 3 or line.startswith("#"):
                    continue
                try:
                    counts[parts[2]] = float(parts[0])
                except ValueError:
                    counts[parts[2]] = None
        return counts


# ------------------------------------------------------------------ generators

def read_markers(proc, timeout: float, on_start, on_end) -> list[str]:
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    lines, deadline = [], time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not sel.select(timeout=0.5):
            if proc.poll() is not None:
                break
            continue
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line.rstrip())
        if line.startswith("MEASURE_START"):
            on_start()
        elif line.startswith("MEASURE_END"):
            on_end()
    sel.close()
    return lines


def wait_rusage(proc, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid, status, ru = os.wait4(proc.pid, os.WNOHANG)
        if pid:
            proc.returncode = os.waitstatus_to_exitcode(status)
            return ru
        time.sleep(0.02)
    proc.kill()
    _, status, ru = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(status)
    return ru


def run_t1gen(cfg: dict, port: int, alloc: dict, raw: Path, snap) -> dict:
    gen_cpus = alloc["generator_cpus"]
    out = raw.with_suffix(".t1gen.json")
    cmd = ["taskset", "-c", ",".join(map(str, gen_cpus)), str(cfg["build"] / "t1gen"),
           "--port", str(port), "--threads", str(len(gen_cpus)), "--cpus", ",".join(map(str, gen_cpus)),
           "--connections", str(cfg["connections"]), "--depth", str(cfg["depth"]),
           "--warmup", str(cfg["warmup"]), "--duration", str(cfg["duration"]),
           "--timeout-ms", str(cfg["timeout_ms"]), "--out", str(out)]
    if cfg["rate"]:
        cmd += ["--rate", str(cfg["rate"])]
    if cfg.get("paths"):
        cmd += ["--paths", str(cfg["paths"])]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = read_markers(proc, cfg["warmup"] + cfg["duration"] + 30, snap["start"], snap["end"])
    ru = wait_rusage(proc, 30)
    err = proc.stderr.read()
    if proc.returncode != 0 or not out.exists():
        return {"ok": False, "reason": f"t1gen exit {proc.returncode}: {err.strip()[:300]}", "lines": lines}
    g = json.loads(out.read_text())
    m = g["measure"]
    wall = g["measure_wall_s"]
    cpu = g["cpu"]["user_s"] + g["cpu"]["sys_s"]
    lat = g["latency_ns"]
    attempts = m["completed"] + m["errors_total"]
    res = {
        "ok": True, "tool": "t1gen", "tool_commit": g["commit"],
        "completed": m["completed"], "wall_s": wall, "errors": m["errors_total"],
        "error_detail": {k: m[k] for k in ("non_2xx", "timeouts", "eof_inflight", "socket_errors",
                                           "protocol_errors", "connect_errors", "dropped_slots",
                                           "socket_error_events", "protocol_error_events", "reconnects")},
        "error_share": (m["errors_total"] / attempts) if attempts else 1.0,
        "gen_cpu_s": cpu, "gen_cpu_pct": 100.0 * cpu / (wall * len(gen_cpus)),
        "p50_us": lat["p50"] / 1e3, "p99_us": lat["p99"] / 1e3, "p999_us": lat["p999"] / 1e3,
        "mean_us": lat["mean"] / 1e3, "max_us": lat["max"] / 1e3,
        "request_bytes": g["request_bytes"], "response_bytes_read": m["bytes_read"],
    }
    if cfg["rate"]:
        res["offered"] = m["offered"]
        res["achieved_share"] = m["completed"] / m["offered"] if m["offered"] else 0.0
        res["issue_lag_p99_us"] = g["issue_lag_ns"]["p99"] / 1e3
    res["_rusage_total_s"] = ru.ru_utime + ru.ru_stime
    return res


def run_wrk(cfg: dict, port: int, alloc: dict, raw: Path, snap) -> dict:
    gen_cpus = alloc["generator_cpus"]
    out = raw.with_suffix(".wrk.json")
    env = dict(os.environ, T1_WRK_DEPTH=str(cfg["depth"]))
    base = ["taskset", "-c", ",".join(map(str, gen_cpus)), "wrk", "-t", str(len(gen_cpus)),
            "-c", str(cfg["connections"]), "-s", str(HERE / "xcheck" / "wrk_t1.lua"),
            "--timeout", f"{max(1, cfg['timeout_ms'] // 1000)}s"]
    url = f"http://127.0.0.1:{port}/"
    # wrk and h2load parse whole seconds only.
    subprocess.run(base + ["-d", f"{max(1, round(cfg['warmup']))}s", url], env=env, capture_output=True)
    env["T1_WRK_OUT"] = str(out)
    snap["start"]()
    t0 = time.monotonic()
    proc = subprocess.Popen(base + ["-d", f"{max(1, round(cfg['duration']))}s", url], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ru = wait_rusage(proc, cfg["duration"] + 30)
    wall_proc = time.monotonic() - t0
    snap["end"]()
    if proc.returncode != 0 or not out.exists():
        return {"ok": False, "reason": f"wrk exit {proc.returncode}"}
    w = json.loads(out.read_text())
    e = w["errors"]
    lost = e["connect"] + e["read"] + e["write"] + e["timeout"]
    completed = w["requests"] - e["status"]
    wall = w["duration_us"] / 1e6
    cpu = ru.ru_utime + ru.ru_stime
    return {
        "ok": True, "tool": "wrk", "completed": completed, "wall_s": wall,
        "errors": lost + e["status"], "error_detail": e,
        "error_share": (lost + e["status"]) / max(1, w["requests"] + lost),
        "gen_cpu_s": cpu, "gen_cpu_pct": 100.0 * cpu / (wall_proc * len(gen_cpus)),
        "p50_us": w["latency_us"]["p50"], "p99_us": w["latency_us"]["p99"],
        "p999_us": w["latency_us"]["p999"], "mean_us": w["latency_us"]["mean"],
        "max_us": w["latency_us"]["max"],
    }


def run_h2load(cfg: dict, port: int, alloc: dict, raw: Path, snap) -> dict:
    gen_cpus = alloc["generator_cpus"]
    log = Path(tempfile.mkstemp(prefix="t1h2.", suffix=".log", dir="/tmp")[1])
    cmd = ["taskset", "-c", ",".join(map(str, gen_cpus)), "h2load", "--h1", "-t", str(len(gen_cpus)),
           "-c", str(cfg["connections"]), "-m", str(cfg["depth"]), "-D", str(max(1, round(cfg["duration"]))),
           "--warm-up-time", str(round(cfg["warmup"])), "-N", str(max(1, cfg["timeout_ms"] // 1000)),
           "--log-file", str(log), f"http://127.0.0.1:{port}/"]
    t0 = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # h2load prints no window markers: snapshot the server after the nominal warm-up and
    # at exit. Server figures from these rows are approximate and flagged as such.
    time.sleep(cfg["warmup"] + 0.1)
    snap["start"]()
    ru = wait_rusage(proc, cfg["duration"] + 30)
    snap["end"]()
    wall_proc = time.monotonic() - t0
    text = proc.stdout.read()
    raw.with_suffix(".h2load.txt").write_text(text)
    counts = {}
    for line in text.splitlines():
        if line.startswith("requests:"):
            for part in line.split(":", 1)[1].split(","):
                n, _, name = part.strip().partition(" ")
                counts[name] = int(n)
    # The rate comes from the per-request log (start us, status, duration us): h2load's
    # "requests" block excludes the warm-up but its "finished in" line includes it.
    lat, first, last, n_ok, n_all = [], None, None, 0, 0
    with open(log) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 3:
                continue
            start, status, dur = int(parts[0]), int(parts[1]), int(parts[2])
            n_all += 1
            first = start if first is None or start < first else first
            last = start + dur if last is None or start + dur > last else last
            if 200 <= status < 300:
                n_ok += 1
                lat.append(dur)
    log.unlink()
    if proc.returncode != 0:
        return {"ok": False, "reason": f"h2load exit {proc.returncode}, {n_all} logged requests"}
    # h2load logs only completed exchanges. With none logged the server failed every
    # request; the window is kept as a measured failure over the nominal duration.
    wall = (last - first) / 1e6 if n_all else float(max(1, round(cfg["duration"])))
    lat.sort()
    q = lambda p: lat[min(len(lat) - 1, int(math.ceil(p * len(lat))) - 1)] if lat else 0
    # "failed" already includes the "errored" and "timeout" requests (h2load counts them
    # as subsets), so only the logged non-2xx exchanges are added to it.
    errors = counts.get("failed", 0) + (n_all - n_ok)
    cpu = ru.ru_utime + ru.ru_stime
    return {
        "ok": True, "tool": "h2load", "completed": n_ok, "wall_s": wall, "errors": errors,
        "error_detail": counts, "error_share": errors / max(1, n_all + counts.get("failed", 0)),
        "gen_cpu_s": cpu,
        "gen_cpu_pct": 100.0 * cpu / (wall_proc * len(gen_cpus)),
        "gen_cpu_note": "whole process incl. warm-up and log writing",
        "server_metrics_note": "approximate: snapshots at nominal warm-up end and at h2load exit",
        "p50_us": q(0.5), "p99_us": q(0.99), "p999_us": q(0.999),
        "mean_us": statistics.fmean(lat) if lat else 0, "max_us": lat[-1] if lat else 0,
    }


TOOLS = {"t1gen": run_t1gen, "wrk": run_wrk, "h2load": run_h2load}


# ------------------------------------------------------------------ window

def citability(arm: dict, tool: str, gen_commit: str | None) -> dict:
    reasons = []
    records = LAB / "sanitizer-records"

    def state(name: str) -> str:
        try:
            return "green" if json.loads((records / name).read_text()).get("green") is True else "red"
        except (OSError, json.JSONDecodeError):
            return "missing"

    def green(name: str) -> bool:
        return state(name) == "green"

    if arm.get("self_written_cpp"):
        recs = arm.get("sanitizer_record") or []
        recs = [recs] if isinstance(recs, str) else recs
        recs = [f"t1gen-{(gen_commit or 'unknown')[:9]}.json" if r == "t1gen" else r for r in recs]
        if not recs:
            reasons.append("server has no sanitizer record")
        for rec in recs:
            if not green(rec):
                reasons.append(f"server record {rec} is {state(rec)}")
    if tool == "t1gen":
        rec = f"t1gen-{(gen_commit or 'unknown')[:9]}.json"
        if not green(rec):
            reasons.append(f"generator record {rec} is {state(rec)}")
    return {"citable": not reasons, "not_citable_because": reasons}


def run_window(cfg: dict, arm_name: str, alloc: dict, port: int, session: dict, tag: str) -> dict:
    """One window; a driver fault becomes an invalid row instead of ending the campaign."""
    try:
        return _run_window(cfg, arm_name, alloc, port, session, tag)
    except Exception as e:  # noqa: BLE001 - recorded, never swallowed silently
        return {"session": session["id"], "cell": cfg["cell"], "tag": tag, "arm": arm_name,
                "tool": cfg["tool"], "server_cores": cfg["server_cores"], "depth": cfg["depth"],
                "valid": False, "invalid_reasons": [f"driver error: {e!r}"], "citable": False}


def _run_window(cfg: dict, arm_name: str, alloc: dict, port: int, session: dict, tag: str) -> dict:
    arm = cfg["arms"][arm_name]
    raw = cfg["out"] / "raw" / tag
    raw.parent.mkdir(parents=True, exist_ok=True)
    n = cfg["server_cores"]
    row = {
        "session": session["id"], "cell": cfg["cell"], "tag": tag, "arm": arm_name, "label": arm["label"],
        "tool": cfg["tool"], "mode": "open" if cfg["rate"] else "closed", "server_cores": n,
        "workers": n, "depth": cfg["depth"], "connections": cfg["connections"], "rate": cfg["rate"],
        "warmup_s": cfg["warmup"], "duration_s": cfg["duration"], "port": port,
        "server_cpus": alloc["server_cpus"], "server_idle_siblings": alloc["server_idle_siblings"],
        "generator_cpus": alloc["generator_cpus"], "housekeeping_core": alloc["housekeeping_core"],
        "sibling_sets": alloc["sibling_sets"], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if not port_free(port):
        row.update(valid=False, invalid_reasons=[f"port {port} busy"])
        return row
    proc, cmd = start_server(arm, cfg["build"], n, port, alloc["server_cpus"], raw.with_suffix(".server.log"))
    row["server_cmd"] = cmd
    try:
        if not wait_ready(proc, port):
            log = raw.with_suffix(".server.log").read_text(errors="replace")[-400:]
            row.update(valid=False, invalid_reasons=[f"server did not start: {log}"])
            return row
        try:
            row["probe"] = probe(port)
        except OSError as e:
            row.update(valid=False, invalid_reasons=[f"probe failed: {e}"])
            return row
        perf = Perf(proc.pid, raw.parent) if cfg["perf"] else None
        snaps, mhz = {}, []
        all_cpus = alloc["server_cpus"] + alloc["generator_cpus"]

        def on_start():
            snaps["s0"] = proc_snapshot(proc.pid)
            snaps["stat0"] = cpu_times()
            mhz.append(cpu_mhz(all_cpus))
            if perf:
                perf.enable()

        def on_end():
            if perf:
                perf.disable()
            snaps["s1"] = proc_snapshot(proc.pid)
            snaps["stat1"] = cpu_times()
            mhz.append(cpu_mhz(all_cpus))

        res = TOOLS[cfg["tool"]](cfg, port, alloc, raw, {"start": on_start, "end": on_end})
    finally:
        row["server_exit"] = stop_process(proc)
    perf_counts = perf.finish() if cfg["perf"] and perf else {}
    if cfg["perf"] and perf and not perf.ok:
        row["perf_error"] = (perf.dir / "perf.err").read_text(errors="replace")[-300:]
    return finish_row(row, res, snaps, mhz, perf_counts, session, cfg)


def finish_row(row, res, snaps, mhz, perf_counts, session, cfg) -> dict:
    reasons = []
    if not res.get("ok"):
        row.update(valid=False, invalid_reasons=[res.get("reason", "generator failed")])
        return row
    row.update({k: v for k, v in res.items() if not k.startswith("_") and k != "ok"})
    completed, wall = res["completed"], res["wall_s"]
    row["rps"] = completed / wall if wall > 0 else 0.0
    row["rps_per_core"] = row["rps"] / row["server_cores"]
    if "s0" in snaps and "s1" in snaps:
        s0, s1 = snaps["s0"], snaps["s1"]
        run_s = (s1["run_ns"] - s0["run_ns"]) / 1e9
        row["server_cpu_s"] = run_s
        row["server_cpu_ticks_s"] = (s1["cpu_ticks"] - s0["cpu_ticks"]) / os.sysconf("SC_CLK_TCK")
        row["server_cpu_util"] = run_s / (s1["t"] - s0["t"]) / row["server_cores"]
        row["cpu_us_per_req"] = 1e6 * run_s / completed if completed else None
        row["peak_rss_kb"] = s1.get("VmHWM")
        row["rss_kb"] = s1.get("VmRSS")
        row["server_threads"] = s1["threads"]
        cs = (s1["ctx_vol"] - s0["ctx_vol"]) + (s1["ctx_invol"] - s0["ctx_invol"])
        row["ctx_switches_proc"] = cs
        row["ctx_involuntary_proc"] = s1["ctx_invol"] - s0["ctx_invol"]
        row["ctx_per_req_proc"] = cs / completed if completed else None
        span = s1["t"] - s0["t"]
        st0, st1 = snaps["stat0"], snaps["stat1"]
        busy, soft = busy_seconds(st0, st1, row["server_cpus"])
        row["server_cores_busy"] = busy / (span * row["server_cores"])
        row["server_cores_softirq_s"] = soft
        row["core_us_per_req"] = 1e6 * busy / completed if completed else None
        sib, _ = busy_seconds(st0, st1, row["server_idle_siblings"])
        row["server_siblings_busy"] = sib / (span * max(1, len(row["server_idle_siblings"])))
        gbusy, _ = busy_seconds(st0, st1, row["generator_cpus"])
        row["gen_cpus_busy_pct"] = 100.0 * gbusy / (span * len(row["generator_cpus"]))
        hk, _ = busy_seconds(st0, st1, row["housekeeping_core"])
        row["housekeeping_busy"] = hk / (span * len(row["housekeeping_core"]))
    if perf_counts:
        row["perf"] = perf_counts
        for key, name in (("instructions", "instr_per_req"), ("raw_syscalls:sys_enter", "syscalls_per_req"),
                          ("context-switches", "ctx_per_req"), ("cycles", "cycles_per_req")):
            v = perf_counts.get(key)
            row[name] = v / completed if v is not None and completed else None
    if len(mhz) == 2:
        row["mhz_window"] = statistics.fmean(mhz)
        row["mhz_drift"] = abs(row["mhz_window"] - session["mhz"]) / session["mhz"]
    probe_ = row.get("probe", {})
    if probe_ and (probe_.get("status") != 200 or not probe_.get("body_ok")):
        reasons.append(f"probe returned status {probe_.get('status')} body_ok={probe_.get('body_ok')}")
    if completed == 0:
        reasons.append("no completed requests")
    if res["error_share"] > 0.001:
        reasons.append(f"errors {100 * res['error_share']:.3f}% > 0.1%")
    # The rule uses the larger of the generator's own CPU time and the busy share of its
    # CPUs, which also carries the softirq work done there.
    row["gen_cpu_pct_rule"] = max(res["gen_cpu_pct"], row.get("gen_cpus_busy_pct") or 0.0)
    if not cfg["rate"] and row["gen_cpu_pct_rule"] > 90.0:
        reasons.append(f"generator CPU {row['gen_cpu_pct_rule']:.1f}% > 90% on a saturation cell")
    if row.get("mhz_drift") is not None and row["mhz_drift"] > 0.02:
        reasons.append(f"CPU MHz drift {100 * row['mhz_drift']:.2f}% > 2%")
    if cfg["rate"] and res.get("achieved_share", 1.0) < 0.99:
        row["note"] = f"offered load not achieved ({100 * res['achieved_share']:.1f}%)"
    row["valid"] = not reasons
    row["invalid_reasons"] = reasons
    row.update(citability(cfg["arms"][row["arm"]], row["tool"], res.get("tool_commit")))
    if not row["valid"]:
        row["citable"] = False
    return row


# ------------------------------------------------------------------ statistics

def geo_mean(xs):
    return math.exp(statistics.fmean(math.log(x) for x in xs))


def bootstrap_ci(ratios, n_boot=10000, seed=12345):
    rng = random.Random(seed)
    logs = [math.log(r) for r in ratios]
    means = sorted(statistics.fmean(rng.choices(logs, k=len(logs))) for _ in range(n_boot))
    lo, hi = means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]
    return math.exp(lo), math.exp(hi)


def valid_rounds(rows) -> set:
    """The rounds every one of whose windows is valid."""
    bad, seen = set(), set()
    for r in rows:
        seen.add(r["round"])
        if not r.get("valid"):
            bad.add(r["round"])
    return seen - bad


def pair_ratios(rows, ref, arm, valid_only=False):
    """Per round: mean req/s of arm over mean req/s of ref, rounds where both ran. With
    valid_only, only rounds whose windows are all valid (valid_rounds) count."""
    keep = valid_rounds(rows) if valid_only else None
    rounds = {}
    for r in rows:
        if r.get("rps") is None or (keep is not None and r["round"] not in keep):
            continue
        rounds.setdefault(r["round"], {}).setdefault(r["arm"], []).append(r["rps"])
    out = []
    for k in sorted(rounds):
        a, b = rounds[k].get(ref), rounds[k].get(arm)
        if a and b and statistics.fmean(a) > 0 and statistics.fmean(b) > 0:
            out.append(statistics.fmean(b) / statistics.fmean(a))
    return out


def decide(ratios, min_pairs, lo_band=0.98, hi_band=1.02, half_width=0.01):
    if len(ratios) < min_pairs:
        return {"n_pairs": len(ratios), "decided": False}
    point = geo_mean(ratios)
    lo, hi = bootstrap_ci(ratios)
    hw = (hi - lo) / 2 / point
    excl = hi < lo_band or lo > hi_band
    return {"n_pairs": len(ratios), "ratio": point, "ci95": [lo, hi], "half_width": hw,
            "excludes_band": excl, "narrow": hw < half_width, "decided": excl or hw < half_width}


def stop_verdicts(rows, arms, cfg) -> dict:
    """The stopping rule after a round: every non-reference arm against the first, over the rounds
    so far (only the rounds whose windows are all valid, with cfg["valid_pairs_only"])."""
    ref = arms[0]
    return {a: decide(pair_ratios(rows, ref, a, cfg.get("valid_pairs_only", False)), cfg["min_pairs"])
            for a in arms[1:]}


# ------------------------------------------------------------------ cell

def run_cell(cfg: dict, session: dict, rows_path: Path, port_base: list[int]) -> dict:
    alloc = allocate(cfg["server_cores"])
    arms = cfg["arm_list"]
    ref = arms[0]
    order = arms + arms[::-1]
    rows, verdicts, stop = [], {}, "max pairs reached"
    for rnd in range(1, cfg["max_pairs"] + 1):
        for pos, arm in enumerate(order):
            port_base[0] += 1
            tag = f"{cfg['cell']}-r{rnd:02d}-p{pos:02d}-{arm}"
            row = run_window(cfg, arm, alloc, port_base[0], session, tag)
            row["round"], row["position"] = rnd, pos
            rows.append(row)
            with open(rows_path, "a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"  {tag}: rps={row.get('rps', 0):.0f} valid={row.get('valid')} "
                  f"{'; '.join(row.get('invalid_reasons', []))}", flush=True)
        if cfg["fixed_pairs"]:
            if rnd >= cfg["fixed_pairs"]:
                stop = f"fixed {cfg['fixed_pairs']} pairs"
                break
            continue
        verdicts = stop_verdicts(rows, arms, cfg)
        if all(v["decided"] for v in verdicts.values()):
            stop = "every ratio decided"
            break
    verdicts = {a: decide(pair_ratios(rows, ref, a, cfg.get("valid_pairs_only", False)), 1) for a in arms[1:]}
    return {"cell": cfg["cell"], "reference": ref, "arms": arms, "rounds": rnd, "stop": stop,
            "allocation": alloc, "verdicts": verdicts, "per_arm": summarise(rows, arms)}


def summarise(rows, arms) -> dict:
    out = {}
    for a in arms:
        mine = [r for r in rows if r["arm"] == a]
        ok = [r for r in mine if r.get("valid")]

        def med(key, src=ok):
            vals = [r[key] for r in src if r.get(key) is not None]
            return statistics.median(vals) if vals else None

        out[a] = {
            "windows": len(mine), "valid_windows": len(ok),
            "rps_median": med("rps"), "rps_min": min((r["rps"] for r in ok), default=None),
            "rps_max": max((r["rps"] for r in ok), default=None),
            "rps_median_all_windows": med("rps", mine),
            "rps_per_core_median": med("rps_per_core"), "cpu_us_per_req_median": med("cpu_us_per_req"),
            "peak_rss_kb_max": max((r["peak_rss_kb"] for r in ok if r.get("peak_rss_kb")), default=None),
            "p50_us_median": med("p50_us"), "p99_us_median": med("p99_us"), "p999_us_median": med("p999_us"),
            "syscalls_per_req_median": med("syscalls_per_req"), "instr_per_req_median": med("instr_per_req"),
            "ctx_per_req_median": med("ctx_per_req"), "gen_cpu_pct_max": max(
                (r["gen_cpu_pct_rule"] for r in mine if r.get("gen_cpu_pct_rule") is not None), default=None),
            "core_us_per_req_median": med("core_us_per_req"), "server_cores_busy_median": med("server_cores_busy"),
            "error_share_max": max((r["error_share"] for r in mine if r.get("error_share") is not None),
                                   default=None),
            "server_cpu_util_median": med("server_cpu_util"),
            "citable": bool(ok) and all(r.get("citable") for r in ok),
            "invalid": [{"tag": r["tag"], "reasons": r.get("invalid_reasons")} for r in mine if not r.get("valid")],
            "probe": next((r["probe"] for r in mine if r.get("probe")), None),
        }
    return out


# ------------------------------------------------------------------ session

def open_session(out: Path, all_cpus: list[int]) -> dict:
    raise_nofile()
    fp = pin_fingerprint()
    if not fp.get("pinned"):
        raise CellError(f"host not in the pinned state: {fp}")
    session = {"id": time.strftime("%Y%m%dT%H%M%S"), "fingerprint": fp,
               "mhz": fp["mean_mhz"], "mhz_source": "lab/bin/pin.sh mean_mhz at session start",
               "mhz_idle_sample_measured_cpus": cpu_mhz(all_cpus),
               "sibling_sets": physical_cores(), "uname": " ".join(os.uname()),
               "nofile": resource.getrlimit(resource.RLIMIT_NOFILE)}
    out.mkdir(parents=True, exist_ok=True)
    (out / "session.json").write_text(json.dumps(session, indent=1))
    return session


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arms", required=True, help="comma list, first is the reference")
    ap.add_argument("--arms-file", type=Path, default=HERE / "arms.json")
    ap.add_argument("--build", type=Path, default=Path.home() / "lab" / "t1-build")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cores", type=int, default=1)
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--connections", type=int, default=0, help="default 64 per server core")
    ap.add_argument("--rate", type=float, default=0.0, help="open loop req/s; 0 = closed loop")
    ap.add_argument("--tool", choices=sorted(TOOLS), default="t1gen")
    ap.add_argument("--warmup", type=float, default=1.0)
    ap.add_argument("--duration", type=float, default=5.0)
    ap.add_argument("--timeout-ms", type=int, default=1000)
    ap.add_argument("--min-pairs", type=int, default=3)
    ap.add_argument("--max-pairs", type=int, default=10)
    ap.add_argument("--fixed-pairs", type=int, default=0)
    ap.add_argument("--valid-pairs-only", action="store_true",
                    help="only rounds whose windows are all valid count toward --min-pairs and the stop")
    ap.add_argument("--no-perf", action="store_true")
    ap.add_argument("--paths", type=Path, help="t1gen --paths: a file of request targets, one per line")
    a = ap.parse_args(argv)
    if a.paths and a.tool != "t1gen":
        ap.error("--paths needs --tool t1gen")
    arms = load_arms(a.arms_file)
    arm_list = a.arms.split(",")
    for x in arm_list:
        if x not in arms:
            ap.error(f"unknown arm {x}")
    alloc = allocate(a.cores)
    session = open_session(a.out, alloc["server_cpus"] + alloc["generator_cpus"])
    cfg = {"arms": arms, "arm_list": arm_list, "build": a.build, "out": a.out, "server_cores": a.cores,
           "depth": a.depth, "connections": a.connections or 64 * a.cores, "rate": a.rate, "tool": a.tool,
           "warmup": a.warmup, "duration": a.duration, "timeout_ms": a.timeout_ms, "min_pairs": a.min_pairs,
           "max_pairs": a.max_pairs, "fixed_pairs": a.fixed_pairs, "perf": not a.no_perf,
           "valid_pairs_only": a.valid_pairs_only,
           "paths": str(a.paths.resolve()) if a.paths else "",
           "cell": f"c{a.cores}-d{a.depth}-{'open' + str(int(a.rate)) if a.rate else 'sat'}-{a.tool}"}
    summary = run_cell(cfg, session, a.out / "windows.jsonl", [20000])
    (a.out / f"summary-{cfg['cell']}.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: summary[k] for k in ("cell", "rounds", "stop", "verdicts")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
