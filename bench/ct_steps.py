#!/usr/bin/env python3
"""The constant-evaluation budget each compile-time table needs with clang (reported with H7).

    ct_steps.py BUILD_DIR [--tables static_1000_s1,github_203] [--out FILE.jsonl]

For each generated table of bench/gen, the compile command of its object from BUILD_DIR's
compile_commands.json is run again with -fconstexpr-steps=N in place of the build's value,
N = 1,048,576 (clang's default) times 4^k, k = 0, 1, ..., until it compiles; then the
factor of 4 between the last N that failed and the first that compiled is halved once. The
result is the smallest N that compiled, the largest that failed (the need lies between),
and the compile time at the smallest passing N. One JSON object per table. Compiles run
one at a time; run it under lab/bin/lablock.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

DEFAULT = 1 << 20
STEPS = re.compile(r"-fconstexpr-steps=\d+")


def compile_with(cmd: list[str], steps: int, out: Path, cwd: str) -> tuple[bool, float, str]:
    args = [STEPS.sub(f"-fconstexpr-steps={steps}", a) for a in cmd]
    if not any(a.startswith("-fconstexpr-steps=") for a in args):
        args.insert(1, f"-fconstexpr-steps={steps}")
    i = args.index("-o")
    args[i + 1] = str(out)
    t0 = time.monotonic()
    p = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    return p.returncode == 0, time.monotonic() - t0, p.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build", type=Path)
    ap.add_argument("--tables", default="")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    commands = json.loads((args.build / "compile_commands.json").read_text(encoding="utf-8"))
    by_table = {}
    for e in commands:
        m = re.search(r"/gen/ct_([a-z0-9_]+)\.cpp$", e["file"])
        if m:
            by_table[m.group(1)] = (e["directory"], shlex.split(e["command"]))
    wanted = [t for t in args.tables.split(",") if t] or sorted(by_table)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "t.o"
        for name in wanted:
            directory, cmd = by_table[name]
            failed, passed, seconds, why = 0, 0, 0.0, ""
            steps = DEFAULT
            while steps <= DEFAULT << 16:
                ok, secs, err = compile_with(cmd, steps, obj, directory)
                if ok:
                    passed, seconds = steps, secs
                    break
                failed = steps
                why = next((line for line in err.splitlines() if "constexpr" in line or "error" in line), "")[:200]
                steps *= 4
            if passed and failed and passed // failed == 4:
                mid = failed * 2
                ok, secs, err = compile_with(cmd, mid, obj, directory)
                if ok:
                    passed, seconds = mid, secs
                else:
                    failed = mid
            row = {"table": name, "steps_min_passed": passed or None, "steps_max_failed": failed or None,
                   "compile_s_at_min": round(seconds, 3), "compiler": cmd[0], "first_error": why}
            rows.append(row)
            print(json.dumps(row), flush=True)
    if args.out:
        args.out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
