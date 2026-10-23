#!/usr/bin/env python3
"""Functional check of one round-3 server arm on one cell (design/round3/end-to-end.md, section 5).

Starts PROGRAM --port P --workers 1 --routes CELL/routes.txt --router NAME --check, waits until it
accepts, and checks over keep-alive connections:
  - GET / answers route m (the number of routes) with no captured value, for every router: the
    server answers the probe itself, and no router holds it;
  - the null router answers route 0 for every other path, a miss included;
  - every target of CELL/<set>.txt answers 200 with its line of CELL/<set>.expect;
  - a path no route matches answers 404.
Then it stops the server (SIGTERM on Linux, Ctrl-Break on Windows) and requires exit code 0. With
--measured it starts the server a second time without --check and requires the fixed 13-byte body
for the first targets. Untimed: it measures nothing.

    check_server.py --program BIN --router NAME --cell DIR [--set all|ring|both] [--measured]

Prints one JSON line and exits 0 only if every check passed.
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

BODY = b"Hello, World!"
MISS = "/p2-no-such-route/x/y/z/w"
PIPELINE = 64


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(program: str, router: str, routes: Path, port: int, check: bool) -> subprocess.Popen:
    cmd = [program, "--port", str(port), "--workers", "1", "--routes", str(routes), "--router", router]
    if check:
        cmd.append("--check")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)


def wait_ready(proc: subprocess.Popen, port: int, timeout: float) -> None:
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


def stop(proc: subprocess.Popen, timeout: float = 20.0) -> int:
    if proc.poll() is None:
        proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return -999
    return proc.returncode


class Conn:
    """One keep-alive HTTP/1.1 connection that reads responses framed by Content-Length."""

    def __init__(self, port: int):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=30)
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.buf = b""

    def close(self) -> None:
        self.s.close()

    def _fill(self) -> None:
        chunk = self.s.recv(1 << 16)
        if not chunk:
            raise RuntimeError("the server closed the connection")
        self.buf += chunk

    def response(self) -> tuple:
        while b"\r\n\r\n" not in self.buf:
            self._fill()
        head, _, rest = self.buf.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        status = int(lines[0].split()[1])
        length = 0
        for line in lines[1:]:
            k, _, v = line.partition(b":")
            if k.strip().lower() == b"content-length":
                length = int(v.strip())
        while len(rest) < length:
            self.buf = head + b"\r\n\r\n" + rest
            self._fill()
            head, _, rest = self.buf.partition(b"\r\n\r\n")
        self.buf = rest[length:]
        return status, rest[:length]

    def get_many(self, paths) -> list:
        """GETs pipelined PIPELINE at a time; returns (status, body) per path, in order."""
        out = []
        for i in range(0, len(paths), PIPELINE):
            batch = paths[i : i + PIPELINE]
            self.s.sendall(b"".join(b"GET " + p.encode() + b" HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n" for p in batch))
            out.extend(self.response() for _ in batch)
        return out


def read_lines(path: Path) -> list:
    return [line for line in path.read_text(encoding="utf-8").split("\n") if line != ""]


def check_set(conn: Conn, cell: Path, name: str, failures: list, null: bool) -> int:
    paths = read_lines(cell / f"{name}.txt")
    expect = ["0"] * len(paths) if null else read_lines(cell / f"{name}.expect")
    if len(paths) != len(expect):
        failures.append(f"{name}: {len(paths)} paths but {len(expect)} expected answers")
        return 0
    got = conn.get_many(paths)
    for path, want, (status, body) in zip(paths, expect, got):
        if status != 200 or body != (want + "\n").encode():
            if len(failures) < 20:
                failures.append(f"{name}: GET {path}: want 200 {want!r}, got {status} {body!r}")
            else:
                failures.append("...")
                break
    return len(paths)


def run(a) -> dict:
    cell = Path(a.cell)
    routes = cell / "routes.txt"
    m = len(read_lines(routes))
    # The null arm answers route 0 for every request without reading the path.
    null = a.router == "null"
    failures = []
    checked = 0
    port = free_port()
    proc = start(a.program, a.router, routes, port, check=True)
    try:
        wait_ready(proc, port, a.ready_timeout)
        conn = Conn(port)
        root = m  # every server answers the probe itself, the null arm too
        (status, body), = conn.get_many(["/"])
        if status != 200 or body != f"{root}\n".encode():
            failures.append(f"GET /: want 200 {root!r}, got {status} {body!r}")
        sets = ["all", "ring"] if a.set == "both" else [a.set]
        for name in sets:
            checked += check_set(conn, cell, name, failures, null)
        (status, body), = conn.get_many([MISS])
        if (status, body) != ((200, b"0\n") if null else (404, b"")):
            failures.append(f"GET {MISS}: want {'200 0' if null else '404'}, got {status} {body!r}")
        conn.close()
    finally:
        rc = stop(proc)
    if rc != 0:
        failures.append(f"check mode: exit code {rc} after the stop signal")
    if a.measured:
        port = free_port()
        proc = start(a.program, a.router, routes, port, check=False)
        try:
            wait_ready(proc, port, a.ready_timeout)
            conn = Conn(port)
            paths = read_lines(cell / "ring.txt")[:256] + ["/"]
            for path, (status, body) in zip(paths, conn.get_many(paths)):
                if status != 200 or body != BODY:
                    failures.append(f"measured: GET {path}: want 200 {BODY!r}, got {status} {body!r}")
                    break
            conn.close()
        finally:
            rc = stop(proc)
        if rc != 0:
            failures.append(f"measured mode: exit code {rc} after the stop signal")
    return {"program": Path(a.program).name, "router": a.router, "cell": str(cell), "m": m, "set": a.set,
            "checked": checked, "ok": not failures, "failures": failures}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--router", required=True)
    ap.add_argument("--cell", required=True)
    ap.add_argument("--set", choices=["all", "ring", "both"], default="both")
    ap.add_argument("--measured", action="store_true")
    ap.add_argument("--ready-timeout", type=float, default=120.0)
    a = ap.parse_args()
    try:
        result = run(a)
    except Exception as e:  # noqa: BLE001 - any failure is reported in the result line
        result = {"program": Path(a.program).name, "router": a.router, "cell": a.cell, "ok": False,
                  "failures": [f"{type(e).__name__}: {e}"]}
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
