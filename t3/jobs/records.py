#!/usr/bin/env python3
"""Round 3's D5 records on either system of the laptop (STATE.md, Laptop requests 0 and 4): t3/sanitize.py
for each sanitizer of the host, in order, one at a time (Linux: asan, tsan, msan; Windows: asan),
each record into OUT_DIR/records/, its logs into ~/lab/records-logs/<record>/ and <record>.tar.gz.
The bring-up job (t3/jobs/bringup.py) comes first: its request sets, P2R3/sets, are the suite's.

    records.py OUT_DIR

A record that is not green, or a run that fails, stops the job (exit 1): nothing after it runs, and
the record is kept as it is, never made again in silence (sanitize.py refuses a record name whose
logs exist). On Linux, after the records: whether any binary of them can use io_uring
(MemorySanitizer cannot see the kernel's writes into an io_uring buffer; the programs use epoll): ldd,
dynamic symbols and strings of each, into OUT_DIR/io_uring.txt. Environment: t3/labsteps.py's,
P2R3 (~/lab/p2r3), WORK (P2R3/san), ONLY (a space-separated subset of the host's sanitizers).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labsteps as L  # noqa: E402

HOST = ("asan",) if L.WINDOWS else ("asan", "tsan", "msan")


def uring_report(work: Path) -> str:
    lines = []
    for san in HOST:
        for b in (work / san / "build" / "server" / "mserver", work / san / "build" / "t3" / "gen" / "p2gen",
                  work / san / "progs" / "mserver-go",
                  work / san / "progs" / "rust" / "x86_64-unknown-linux-gnu" / "release" / "mserver-rs"):
            if not b.is_file():
                lines.append(f"{b}: not built")
                continue
            ldd = subprocess.run(["ldd", str(b)], capture_output=True, text=True).stdout
            nm = subprocess.run(["nm", "-D", str(b)], capture_output=True, text=True).stdout
            strings = subprocess.run(["strings", "-a", str(b)], capture_output=True, text=True).stdout
            lines += [str(b), f"  ldd, lines naming uring: {sum('uring' in l.lower() for l in ldd.splitlines())}",
                      f"  dynamic symbols naming uring: {sum('uring' in l.lower() for l in nm.splitlines())}",
                      f"  strings containing io_uring: {sum('io_uring' in l.lower() for l in strings.splitlines())}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: records.py OUT_DIR", file=sys.stderr)
        return 2
    out = Path(sys.argv[1]).resolve()
    (out / "records").mkdir(parents=True, exist_ok=True)
    p2r3 = Path(os.environ.get("P2R3") or Path.home() / "lab" / "p2r3")
    work = Path(os.environ.get("WORK") or p2r3 / "san")
    only = os.environ.get("ONLY", "").split() or list(HOST)
    print(f"records: paper {L.git('rev-parse', 'HEAD')}, sanitizers {' '.join(only)}", flush=True)
    for san in only:
        print(f"== {san} start", flush=True)
        log = out / f"{san}.log"
        rc = L.run([L.PY, L.T3 / "sanitize.py", san, out / "records", p2r3 / "sets", "--work", work], log, dict(os.environ))
        print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]), flush=True)
        with open(out / "steps.txt", "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{san} {rc}\n")
        if rc != 0:
            print(f"STOPPED: {san} exited {rc} (not green or failed; {log})", flush=True)
            return 1
    if not L.WINDOWS:
        report = uring_report(work)
        (out / "io_uring.txt").write_text(report, encoding="utf-8")
        print(report, flush=True)
    print("records done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
