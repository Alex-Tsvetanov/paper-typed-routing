#!/usr/bin/env python3
"""Exercise a running mserver for its sanitizer record (t1/sanitize_h6.sh): every target of a
targets file once, over one keep-alive HTTP/1.1 connection; then GET / and one path no route
matches; then one pipelined burst of up to 32 targets in a single send, whose answers must come
back in order (design/round2/minimal-server.md, section 7).

    h6_exercise.py --port P --targets FILE [--wait 60] [--unmatched-status 404]

Waits up to --wait seconds for the server to answer GET /. Every target must be answered 200 with
the body "Hello, World!", GET / likewise, and the unmatched path with --unmatched-status (the null
router arm answers every path with its route 0, so 200 for it). Prints one JSON object (requests,
failures with the first few of them); exits 0 only if nothing failed.
"""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import sys
import time

BODY = b"Hello, World!"
UNMATCHED = "/h6-exercise/no/route/here"


def pipelined(port: int, targets: list[str]) -> list[str]:
    """Sends the requests in one write and reads the answers in order; the failures."""
    raw = "".join(f"GET {t} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n" for t in targets).encode()
    fails = []
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(raw)
        f = s.makefile("rb")
        for t in targets:
            status = f.readline().decode(errors="replace").strip()
            length = None
            while True:
                line = f.readline().decode(errors="replace").strip()
                if not line:
                    break
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":", 1)[1])
            body = f.read(length or 0)
            if status != "HTTP/1.1 200 OK" or body != BODY:
                fails.append(f"pipelined {t}: {status} {body[:40]!r}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--wait", type=float, default=60.0)
    ap.add_argument("--unmatched-status", type=int, default=404)
    a = ap.parse_args()
    targets = [l.strip() for l in open(a.targets, encoding="utf-8") if l.strip()]

    deadline = time.monotonic() + a.wait
    while True:
        try:
            c = http.client.HTTPConnection("127.0.0.1", a.port, timeout=10)
            c.request("GET", "/")
            r = c.getresponse()
            r.read()
            break
        except OSError:
            if time.monotonic() > deadline:
                print(json.dumps({"requests": 0, "failures": 1, "first": ["the server never answered GET /"]}))
                return 1
            time.sleep(0.2)

    fails: list[str] = []
    requests = 0
    c = http.client.HTTPConnection("127.0.0.1", a.port, timeout=30)
    for path, want in [(t, 200) for t in targets] + [("/", 200), (UNMATCHED, a.unmatched_status)]:
        requests += 1
        try:
            c.request("GET", path)
            r = c.getresponse()
            body = r.read()
        except OSError as e:
            fails.append(f"{path}: {e}")
            c = http.client.HTTPConnection("127.0.0.1", a.port, timeout=30)
            continue
        if r.status != want or (want == 200 and body != BODY):
            fails.append(f"{path}: {r.status} {body[:40]!r}")
    burst = targets[:32]
    requests += len(burst)
    try:
        fails += pipelined(a.port, burst)
    except OSError as e:
        fails.append(f"pipelined burst: {e}")
    print(json.dumps({"requests": requests, "failures": len(fails), "first": fails[:10]}))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
