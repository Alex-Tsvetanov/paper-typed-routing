#!/usr/bin/env python3
"""Functional tests of p2gen in count mode (design/round3/end-to-end.md, section 8).

Untimed: every run of p2gen here that can connect carries --count, so no window is marked, no clock is read for any
output, and nothing in this file looks at a time, a rate or a latency. It checks counts and exit
codes only.

    count_checks.py edge   --p2gen BIN
        A scripted server answers in every way p2gen must handle: lower-case and mixed-case
        Content-Length, answers split across reads, wrong status, wrong body, chunked, garbage,
        bytes after an answer, Connection: close, a hung request (timeout), a reset, a close
        without an answer, a late server (refused connections), slow answers that must not time
        out, the walk over the targets, and the command lines that must exit 2.

    count_checks.py server --p2gen BIN --program BIN --router NAME --routes FILE --paths FILE
                           [--count N] [--connections C] [--threads T] [--check]
        Starts a server program (mserver, mserver-go, mserver-rs: the contract of
        design/round3/end-to-end.md, section 5), runs p2gen --count against it, and requires
        completed == N and no error, exit 0. With --check the server answers a route id, not the
        13 bytes, so p2gen must count N body errors, complete none, and exit 1.

Prints one JSON line per scenario (counts only) and exits 0 only if every check passed.
"""
import argparse
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

OK = b"HTTP/1.1 200 OK\r\ncontent-length: 13\r\n\r\nHello, World!"
RUN_LIMIT = 120  # seconds a single p2gen run may take before it counts as hung

# What a count-mode line must not hold: anything that is, or looks like, a time or a rate.
TIME_WORDS = ("_ns", "_ms", "latency", "wall", "MEASURE", "rate", "warmup", "duration", "t0", "t1", "p50", "p99")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---- running p2gen ----------------------------------------------------------------------------

def run_p2gen(p2gen, port, paths, count, connections=4, threads=1, timeout_ms=None, extra=()):
    """Returns (returncode, stdout, stderr, parsed JSON or None). Always count mode."""
    cmd = [p2gen, "--port", str(port), "--paths", str(paths), "--count", str(count),
           "--connections", str(connections), "--threads", str(threads)]
    if timeout_ms is not None:
        cmd += ["--timeout-ms", str(timeout_ms)]
    cmd += list(extra)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=RUN_LIMIT)
    except subprocess.TimeoutExpired:
        return 124, "", "p2gen did not finish", None
    out = r.stdout.decode(errors="replace")
    js = None
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) == 1:
        try:
            js = json.loads(lines[0])
        except ValueError:
            js = None
    return r.returncode, out, r.stderr.decode(errors="replace"), js


def hygiene(rc, out, js, failures):
    """Count mode prints one JSON line, with no time in it."""
    if js is None:
        failures.append(f"stdout is not one JSON line: {out!r}")
        return
    for word in TIME_WORDS:
        if word in out:
            failures.append(f"the count line holds {word!r}: {out.strip()}")
    if js.get("mode") != "count":
        failures.append(f"mode is {js.get('mode')!r}")


def flat(js):
    e = js["errors"]
    return {"completed": js["completed"], "status": e["status"], "body": e["body"], "framing": e["framing"],
            "lost": e["lost"], "unsolicited": e["unsolicited"], "timeouts": js["timeouts"],
            "connect_errors": js["connect_errors"], "resets": js["resets"], "peer_closes": js["peer_closes"],
            "reconnects": js["reconnects"], "reconnected": js["reconnected"], "resolved": js["resolved"]}


def counts_line(name, js, rc, failures):
    c = flat(js) if js else {}
    return json.dumps({"scenario": name, "rc": rc, "ok": not failures, "counts": c, "failures": failures})


# ---- the scripted server ----------------------------------------------------------------------

def reset_close(c):
    """Close with a reset instead of a FIN."""
    c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    c.close()


class Fake:
    """Accepts connections and calls behavior(fake, n, path, conn) for each request, n counting
    requests over all connections. behavior writes the answer itself and returns "stop" to end the
    connection. It records, per connection, the targets requested in order."""

    def __init__(self, behavior, port=0):
        self.behavior = behavior
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(128)
        self.port = self.sock.getsockname()[1]
        self.lock = threading.Lock()
        self.count = 0
        self.conns = []
        self.heads = []
        self.stopping = False
        self.thread = threading.Thread(target=self._accept_loop, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.stopping = True
        self.sock.close()

    def _accept_loop(self):
        self.sock.settimeout(0.1)
        while not self.stopping:
            try:
                c, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        seq = []
        with self.lock:
            self.conns.append(seq)
        buf = b""
        try:
            while True:
                while b"\r\n\r\n" not in buf:
                    chunk = c.recv(65536)
                    if not chunk:
                        return
                    buf += chunk
                head, _, buf = buf.partition(b"\r\n\r\n")
                path = head.split(b"\r\n")[0].split()[1].decode()
                with self.lock:
                    n = self.count
                    self.count += 1
                    seq.append(path)
                    self.heads.append(head)
                if self.behavior(self, n, path, c) == "stop":
                    return
        except OSError:
            pass
        finally:
            try:
                c.close()
            except OSError:
                pass


def send_pieces(c, data, cuts, pause=0.002):
    last = 0
    for cut in list(cuts) + [len(data)]:
        c.sendall(data[last:cut])
        last = cut
        time.sleep(pause)


# ---- the scenarios ----------------------------------------------------------------------------

def b_ok(f, n, path, c):
    c.sendall(OK)


def b_mixed_case(f, n, path, c):
    c.sendall(b"HTTP/1.1 200 OK\r\nDate: Fri, 23 Oct 2026 10:00:00 GMT\r\nContent-Type: text/plain\r\n"
              b"Connection: keep-alive\r\nCoNtEnT-LeNgTh:  13 \r\n\r\nHello, World!")


def b_split(f, n, path, c):
    # In the head, inside the empty line, and in the body.
    send_pieces(c, OK, (20, OK.index(b"\r\n\r\n") + 2, len(OK) - 4))


def b_bytewise(f, n, path, c):
    send_pieces(c, OK, range(1, len(OK)), pause=0.0)


def b_404(f, n, path, c):
    c.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")


def b_500_with_body(f, n, path, c):
    c.sendall(b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 4\r\n\r\noops")


def b_wrong_body(f, n, path, c):
    if n % 2 == 0:
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\nHello, Worlds")  # 13 bytes, not the 13
    else:
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nHello")


def b_big_body(f, n, path, c):
    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 200000\r\n\r\n" + b"a" * 200000)


def b_chunked(f, n, path, c):
    c.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nd\r\nHello, World!\r\n0\r\n\r\n")


def b_garbage(f, n, path, c):
    c.sendall(b"BLAH BLAH\r\n\r\n")


def b_no_length(f, n, path, c):
    c.sendall(b"HTTP/1.1 200 OK\r\nServer: x\r\n\r\nHello, World!")


def b_extra_bytes(f, n, path, c):
    c.sendall(OK + b"EXTRA")


def b_close_each(f, n, path, c):
    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 13\r\nConnection: close\r\n\r\nHello, World!")
    return "stop"  # the server closes after the answer


def b_hang(f, n, path, c):
    if n % 5 != 4:
        c.sendall(OK)  # every fifth request gets no answer


def b_reset(f, n, path, c):
    if n % 6 == 5:
        reset_close(c)
        return "stop"
    c.sendall(OK)


def b_eof_no_reply(f, n, path, c):
    if n % 6 == 5:
        c.shutdown(socket.SHUT_RDWR)
        return "stop"
    c.sendall(OK)


def b_slow(f, n, path, c):
    time.sleep(0.05)
    c.sendall(OK)


def b_trickle(f, n, path, c):
    # Slower in all than --timeout-ms, but with progress inside it: not a timeout.
    send_pieces(c, OK, (20, 40), pause=0.15)


SCENARIOS = [
    # name, behavior, N, C, T, timeout_ms, exit code, expected counts (others must be 0)
    ("lowercase_length", b_ok, 40, 4, 2, None, 0, {"completed": 40}),
    ("mixed_case_headers", b_mixed_case, 40, 4, 2, None, 0, {"completed": 40}),
    ("answers_in_pieces", b_split, 40, 4, 2, None, 0, {"completed": 40}),
    ("answers_bytewise", b_bytewise, 12, 4, 1, None, 0, {"completed": 12}),
    ("status_404", b_404, 40, 4, 2, None, 1, {"status": 40}),
    ("status_500_with_body", b_500_with_body, 40, 4, 2, None, 1, {"status": 40}),
    ("wrong_body", b_wrong_body, 40, 4, 2, None, 1, {"body": 40}),
    ("big_body_streamed", b_big_body, 8, 4, 2, None, 1, {"body": 8}),
    ("chunked", b_chunked, 20, 4, 2, None, 1, {"framing": 20}),
    ("garbage", b_garbage, 20, 4, 2, None, 1, {"framing": 20}),
    ("no_content_length", b_no_length, 20, 4, 2, None, 1, {"framing": 20}),
    ("bytes_after_answer", b_extra_bytes, 20, 4, 2, None, 1, {"completed": 20, "unsolicited": 20}),
    ("connection_close", b_close_each, 40, 4, 2, None, 0, {"completed": 40}),
    ("hung_request", b_hang, 40, 4, 2, 300, 1, {"completed": 32, "timeouts": 8}),
    ("reset", b_reset, 36, 4, 2, None, 1, {"completed": 30, "lost": 6, "resets": 6}),
    ("close_without_answer", b_eof_no_reply, 36, 4, 2, None, 1, {"completed": 30, "lost": 6, "peer_closes": 6}),
    ("slow_answers_do_not_time_out", b_slow, 20, 4, 2, 1000, 0, {"completed": 20}),
    ("progress_resets_the_timeout", b_trickle, 4, 4, 1, 250, 0, {"completed": 4}),
]


def run_scenario(p2gen, tmp, name, behavior, count, conns, threads, timeout_ms, want_rc, want):
    failures = []
    fake = Fake(behavior)
    fake.start()
    paths = tmp / f"{name}.txt"
    paths.write_text("".join(f"/t{i}\n" for i in range(10)))
    try:
        rc, out, err, js = run_p2gen(p2gen, fake.port, paths, count, conns, threads, timeout_ms)
    finally:
        time.sleep(0.2)  # let the server accept what p2gen last connected
        fake.close()
    hygiene(rc, out, js, failures)
    if rc != want_rc:
        failures.append(f"exit code {rc}, want {want_rc}: {err.strip()}")
    if js is not None:
        got = flat(js)
        for key, value in got.items():
            if key in ("reconnects", "reconnected", "connect_errors", "resolved", "resets", "peer_closes"):
                continue
            if value != want.get(key, 0):
                failures.append(f"{key} is {value}, want {want.get(key, 0)}")
        for key in ("resets", "peer_closes"):
            if key in want and got[key] != want[key]:
                failures.append(f"{key} is {got[key]}, want {want[key]}")
        if got["resolved"] != count:
            failures.append(f"resolved is {got['resolved']}, want {count}")
        if js["count"] != count:
            failures.append(f"count is {js['count']}")
        # reconnects counts attempts, as t1gen does; reconnected, the ones that came up.
        if got["reconnects"] < got["reconnected"]:
            failures.append(f"reconnects {got['reconnects']} is below reconnected {got['reconnected']}")
        if name == "connection_close" and not (count - conns <= got["reconnected"] <= count):
            failures.append(f"reconnected {got['reconnected']} is not within [{count - conns}, {count}]")
        if name in ("reset", "close_without_answer", "hung_request") and got["reconnected"] < 1:
            failures.append("a lost connection was never made again")
        # Every connection p2gen made, the first C and each reconnection, reached the server. A
        # thread that has no request left stops with its last reconnections unfinished: the server
        # may have accepted up to C more than p2gen counted.
        accepted = len(fake.conns)
        if not (conns + got["reconnected"] <= accepted <= 2 * conns + got["reconnected"]):
            failures.append(f"the server accepted {accepted} connections, want {conns} + {got['reconnected']}"
                            f" up to {conns} more")
    return counts_line(name, js, rc, failures), failures


def scenario_refused_start(p2gen, tmp):
    """p2gen starts before the server listens: refused connections are counted and retried."""
    failures = []
    port = free_port()
    paths = tmp / "refused.txt"
    paths.write_text("/a\n/b\n")
    box = {}

    def late():
        time.sleep(0.5)
        box["fake"] = Fake(b_ok, port)
        box["fake"].start()

    t = threading.Thread(target=late)
    t.start()
    rc, out, err, js = run_p2gen(p2gen, port, paths, 20, 4, 2, 500)
    t.join()
    if "fake" in box:
        box["fake"].close()
    hygiene(rc, out, js, failures)
    if rc != 0:
        failures.append(f"exit code {rc}: {err.strip()}")
    if js is not None:
        c = flat(js)
        if c["completed"] != 20 or c["connect_errors"] < 1:
            failures.append(f"completed {c['completed']}, connect_errors {c['connect_errors']}: want 20 and at least 1")
        if c["reconnects"] != 0 or c["reconnected"] != 0:
            failures.append("a connection that was never open is not a reconnection")
    return counts_line("refused_start", js, rc, failures), failures


def scenario_walk(p2gen, tmp):
    """Connection i of C starts at target i*K/C and walks the K targets cyclically; the request
    line and the Host header are what the spec says."""
    failures = []
    k, c_total, n = 10, 4, 40
    fake = Fake(b_ok)
    fake.start()
    paths = tmp / "walk.txt"
    paths.write_text("".join(f"/t{i}\n" for i in range(k)) + "\n")  # a blank line is no target
    try:
        rc, out, err, js = run_p2gen(p2gen, fake.port, paths, n, c_total, 2)
    finally:
        fake.close()
    hygiene(rc, out, js, failures)
    if rc != 0:
        failures.append(f"exit code {rc}: {err.strip()}")
    starts = sorted(int(seq[0][2:]) for seq in fake.conns if seq)
    want = sorted(i * k // c_total for i in range(c_total))
    if starts != want:
        failures.append(f"first targets {starts}, want {want}")
    if len(fake.conns) != c_total:
        failures.append(f"{len(fake.conns)} connections, want {c_total}")
    for seq in fake.conns:
        for a, b in zip(seq, seq[1:]):
            if (int(a[2:]) + 1) % k != int(b[2:]):
                failures.append(f"a connection went from {a} to {b}")
                break
    if sum(len(s) for s in fake.conns) != n:
        failures.append(f"the server saw {sum(len(s) for s in fake.conns)} requests, want {n}")
    for head in fake.heads:
        lines = head.split(b"\r\n")
        if not lines[0].startswith(b"GET /t") or not lines[0].endswith(b" HTTP/1.1"):
            failures.append(f"bad request line {lines[0]!r}")
            break
        if lines[1:] != [f"Host: 127.0.0.1:{fake.port}".encode()]:
            failures.append(f"bad headers {lines[1:]!r}")
            break
    return counts_line("walk_and_request_format", js, rc, failures), failures


def scenario_pinning(p2gen, tmp):
    """--cpus pins the threads. CPU 0 exists everywhere, and a list shorter than the thread count is
    used cyclically. A CPU that does not exist stops the run: exit 1, no request sent."""
    failures = []
    fake = Fake(b_ok)
    fake.start()
    paths = tmp / "pin.txt"
    paths.write_text("/a\n/b\n")
    try:
        rc, out, err, js = run_p2gen(p2gen, fake.port, paths, 20, 4, 2, extra=("--cpus", "0"))
        hygiene(rc, out, js, failures)
        if rc != 0 or js is None or flat(js)["completed"] != 20:
            failures.append(f"pinned to CPU 0: exit code {rc}, {out.strip()!r}, {err.strip()!r}")
        missing = "62" if os.name == "nt" else "1000"
        rc2, out2, err2, js2 = run_p2gen(p2gen, fake.port, paths, 20, 4, 2, extra=("--cpus", missing))
        hygiene(rc2, out2, js2, failures)
        if rc2 != 1 or "cannot pin" not in err2 or js2 is None or js2["thread_failed"] != 1 or flat(js2)["completed"] != 0:
            failures.append(f"pinned to CPU {missing}: exit code {rc2}, {out2.strip()!r}, {err2.strip()!r}")
    finally:
        fake.close()
    return counts_line("pinning", js, rc, failures), failures


def scenario_bad_command_lines(p2gen, tmp):
    """Each of these must exit 2 before any connection, with nothing on stdout. Every call carries
    --count, as every call on the development machine does."""
    failures = []
    good = tmp / "good.txt"
    good.write_text("/a\n")
    empty = tmp / "empty.txt"
    empty.write_text("\n\n")
    bad_target = tmp / "bad_target.txt"
    bad_target.write_text("a\n")
    spaced = tmp / "spaced.txt"
    spaced.write_text("/a b\n")
    # A listener that must see no connection.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    probe.listen(8)
    probe.settimeout(0.3)
    port = probe.getsockname()[1]
    base = ["--port", str(port), "--paths", str(good), "--count", "5"]
    cases = {
        "no port": ["--paths", str(good), "--count", "5"],
        "no paths": ["--port", str(port), "--count", "5"],
        "missing file": ["--port", str(port), "--paths", str(tmp / "nope.txt"), "--count", "5"],
        "no targets": ["--port", str(port), "--paths", str(empty), "--count", "5"],
        "target without slash": ["--port", str(port), "--paths", str(bad_target), "--count", "5"],
        "target with space": ["--port", str(port), "--paths", str(spaced), "--count", "5"],
        "host name, not a literal": base + ["--host", "localhost"],
        "bad cpus": base + ["--cpus", "a,b"],
        "zero connections": base + ["--connections", "0"],
        "zero count": base + ["--count", "0"],
        "depth": base + ["--depth", "1"],
        "open loop": base + ["--rate", "100"],
        "unknown option": base + ["--bogus", "1"],
        "missing value": base + ["--duration"],
        "unwritable out": base + ["--out", str(tmp / "no" / "such" / "dir" / "r.json")],
    }
    for name, args in cases.items():
        r = subprocess.run([p2gen] + args, capture_output=True, timeout=30)
        if r.returncode != 2:
            failures.append(f"{name}: exit code {r.returncode}, want 2")
        if r.stdout:
            failures.append(f"{name}: stdout is not empty: {r.stdout!r}")
    try:
        probe.accept()
        failures.append("a bad command line connected")
    except socket.timeout:
        pass
    probe.close()
    r = subprocess.run([p2gen, "--help"], capture_output=True, timeout=30)
    if r.returncode != 0:
        failures.append(f"--help: exit code {r.returncode}")
    return json.dumps({"scenario": "bad_command_lines", "ok": not failures, "failures": failures}), failures


def scenario_out_file(p2gen, tmp):
    """--out gets the same line as stdout."""
    failures = []
    fake = Fake(b_ok)
    fake.start()
    paths = tmp / "out.txt"
    paths.write_text("/a\n")
    outfile = tmp / "result.json"
    try:
        rc, out, err, js = run_p2gen(p2gen, fake.port, paths, 10, 2, 1, extra=("--out", str(outfile)))
    finally:
        fake.close()
    hygiene(rc, out, js, failures)
    if rc != 0:
        failures.append(f"exit code {rc}: {err.strip()}")
    # (Windows ends the stdout line with CR LF, the file with LF.)
    if not outfile.exists() or outfile.read_text().strip() != out.strip():
        failures.append("the --out file differs from stdout")
    return counts_line("out_file", js, rc, failures), failures


def cmd_edge(a):
    ok = True
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        results = []
        for name, behavior, count, conns, threads, timeout_ms, want_rc, want in SCENARIOS:
            results.append(run_scenario(a.p2gen, tmp, name, behavior, count, conns, threads, timeout_ms, want_rc, want))
        results.append(scenario_refused_start(a.p2gen, tmp))
        results.append(scenario_walk(a.p2gen, tmp))
        results.append(scenario_out_file(a.p2gen, tmp))
        results.append(scenario_pinning(a.p2gen, tmp))
        results.append(scenario_bad_command_lines(a.p2gen, tmp))
        for line, failures in results:
            print(line)
            ok = ok and not failures
    return 0 if ok else 1


# ---- real servers -----------------------------------------------------------------------------

def start(program, router, routes, port, check):
    cmd = [program, "--port", str(port), "--workers", "1", "--routes", str(routes), "--router", router]
    if check:
        cmd.append("--check")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)


def wait_ready(proc, port, timeout=60.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            raise RuntimeError(f"server exited with {proc.returncode} before it was ready: {out.strip()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"server not ready after {timeout} s")


def stop(proc, timeout=20.0):
    if proc.poll() is None:
        proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return -999
    return proc.returncode


def cmd_server(a):
    failures = []
    port = free_port()
    proc = start(a.program, a.router, a.routes, port, a.check)
    js = None
    rc = -1
    try:
        wait_ready(proc, port)
        rc, out, err, js = run_p2gen(a.p2gen, port, a.paths, a.count, a.connections, a.threads)
        hygiene(rc, out, js, failures)
    except RuntimeError as e:
        failures.append(str(e))
    finally:
        server_rc = stop(proc)
    if server_rc != 0:
        failures.append(f"the server exited with {server_rc}")
    if js is not None:
        c = flat(js)
        if a.check:
            want_rc, want = 1, {"body": a.count}
        else:
            want_rc, want = 0, {"completed": a.count}
        if rc != want_rc:
            failures.append(f"p2gen exit code {rc}, want {want_rc}")
        for key in ("completed", "status", "body", "framing", "lost", "unsolicited", "timeouts"):
            if c[key] != want.get(key, 0):
                failures.append(f"{key} is {c[key]}, want {want.get(key, 0)}")
        if c["resolved"] != a.count:
            failures.append(f"resolved is {c['resolved']}, want {a.count}")
    name = f"{Path(a.program).stem}:{a.router}{':check' if a.check else ''}"
    print(counts_line(name, js, rc, failures))
    return 0 if not failures else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("edge")
    e.add_argument("--p2gen", required=True)
    s = sub.add_parser("server")
    s.add_argument("--p2gen", required=True)
    s.add_argument("--program", required=True)
    s.add_argument("--router", required=True)
    s.add_argument("--routes", required=True)
    s.add_argument("--paths", required=True)
    s.add_argument("--count", type=int, default=100000)
    s.add_argument("--connections", type=int, default=64)
    s.add_argument("--threads", type=int, default=4)
    s.add_argument("--check", action="store_true")
    a = ap.parse_args()
    return cmd_edge(a) if a.cmd == "edge" else cmd_server(a)


if __name__ == "__main__":
    sys.exit(main())
