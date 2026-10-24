#!/usr/bin/env python3
"""The functional suite of round 3 (design/round3/end-to-end.md, section 5): every server arm on
every size, untimed.

    run_checks.py --data DIR [--mserver BIN] [--go BIN] [--rust BIN] --out FILE.jsonl [--logs DIR]

For each program given, each of its arms (the C++ server lists its own with --router '?') and
each shape under DIR (DIR/<shape>/m<m>/t<seed>, t3/make_requests.py's layout):
  - pair (111, 211) at every size: every route (all.txt) and the T0 ring (ring.txt), then the
    fixed body in measured mode;
  - pairs 112 to 126 at m = 1,000: the T0 ring.
At m = 100,000 the arms that scan their routes linearly get the ring only. In round 2's grid one
lookup took them, on mixed-disjoint, 0.96 ms (cpp-httplib), 3.95 ms (Oat++), 7.80 ms (Drogon) and
30.1 ms (actix-router), and on static 0.64 ms (cpp-httplib), 1.03 ms (actix-router) and 2.49 ms
(Oat++) (results/round2/all_arms.csv), so every route would take minutes to hours. Each result
line of check_server.py goes to FILE.jsonl; a table is printed. With --logs, every server's output
goes to DIR/<program>-<arm>.log (D5's records scan them for sanitizer reports).
Exits 0 only if every check passed. Measures nothing.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIZES = (10, 100, 1000, 10000, 100000)
RING_PAIRS = tuple(range(112, 127))
LINEAR_AT_100K = {"mixed-disjoint": {"cpp-httplib", "oatpp", "drogon", "actix-router"},
                  "static": {"cpp-httplib", "oatpp", "actix-router"}}
GO_ARMS = ("v2", "httprouter", "gin", "nethttp", "chi", "null")
RUST_ARMS = ("v2", "matchit", "path-tree", "actix-router", "null")


def mserver_arms(binary: str) -> list:
    p = subprocess.run([binary, "--router", "?"], capture_output=True, text=True)
    line = (p.stderr or p.stdout).strip()
    if not line.startswith("router arms:"):
        raise RuntimeError(f"{binary} --router ? printed {line!r}")
    return [a for a in line.split(":", 1)[1].split() if a != "v1"]


def jobs(data: Path, program: str, arms):
    shapes = [s for s in LINEAR_AT_100K if (data / s).is_dir()]
    for shape in shapes:
        for arm in arms:
            for m in SIZES:
                sets = "ring" if m == 100000 and arm in LINEAR_AT_100K[shape] else "both"
                yield program, arm, data / shape / f"m{m}" / "t111", sets, True
            for t in RING_PAIRS:
                yield program, arm, data / shape / "m1000" / f"t{t}", "ring", False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--mserver")
    ap.add_argument("--go")
    ap.add_argument("--rust")
    ap.add_argument("--no-v2", action="store_true", help="leave out the Go and Rust programs' v2 arm")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--logs", type=Path, help="a folder for each server's output, one file per program and arm")
    ap.add_argument("--io-timeout", type=float, default=30.0, help="check_server.py --io-timeout")
    a = ap.parse_args()
    if a.logs:
        a.logs.mkdir(parents=True, exist_ok=True)
    programs = []
    keep = (lambda arms: [x for x in arms if x != "v2"]) if a.no_v2 else list
    if a.mserver:
        programs.append((a.mserver, mserver_arms(a.mserver)))
    if a.go:
        programs.append((a.go, keep(GO_ARMS)))
    if a.rust:
        programs.append((a.rust, keep(RUST_ARMS)))
    if not programs:
        ap.error("give at least one of --mserver, --go, --rust")
    failed = 0
    table = {}
    with open(a.out, "w", newline="\n") as out:
        for program, arms in programs:
            for prog, arm, cell, sets, measured in jobs(a.data, program, arms):
                cmd = [sys.executable, str(HERE / "check_server.py"), "--program", prog, "--router", arm,
                       "--cell", str(cell), "--set", sets, "--ready-timeout", "300", "--io-timeout", str(a.io_timeout)]
                if measured:
                    cmd.append("--measured")
                if a.logs:
                    cmd += ["--server-log", str(a.logs / f"{Path(prog).stem}-{arm}.log")]
                p = subprocess.run(cmd, capture_output=True, text=True)
                line = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else json.dumps(
                    {"program": Path(prog).name, "router": arm, "cell": str(cell), "ok": False,
                     "failures": [p.stderr.strip()[-500:]]})
                out.write(line + "\n")
                out.flush()
                r = json.loads(line)
                key = (Path(prog).name, arm)
                ok, total = table.get(key, (0, 0))
                table[key] = (ok + (1 if r["ok"] else 0), total + 1)
                if not r["ok"]:
                    failed += 1
                    print(f"FAIL {key[0]} {arm} {cell.parent.parent.name}/{cell.parent.name}/{cell.name} {sets}: "
                          f"{r['failures'][:3]}")
    for (prog, arm), (ok, total) in table.items():
        print(f"{prog:16s} {arm:14s} {ok}/{total} ok")
    print(f"run_checks: {sum(t for _, t in table.values())} checks, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
