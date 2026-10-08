#!/usr/bin/env python3
"""Check the answers of every process of a run whose agreement pass stopped at its budget.

    verify_unverified.py RUN_DIR --bin VERIFY_ANSWERS --out FILE.jsonl [--jobs N]

The processes are the rows of RUN_DIR/cells.jsonl that ended ok, belong to an arm with a
router, and have verified_all false (the cell's agreement pass stopped at its 120 s budget).
Each is checked again on every query of its ring by tools/verify_answers (linked from the run's
own build, tools/build_verify.py: every arm of round 2 is in that one binary), with the same
arm, table, table seed, ring seed and ring options. A check counts only if its table and ring
digests equal the process's. Writes one JSON line per process: the process's key, how many
queries the run verified, and the check's result, with the check's wall time. The checks time
nothing that is reported, so --jobs of them run at once; bench/run_grid.sh runs this at the
end of every grid, after the last measured cell. Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--bin", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=1)
    a = ap.parse_args()
    rows = [json.loads(l) for l in (a.run / "cells.jsonl").read_text().splitlines() if l.startswith("{")]
    todo = [r for r in rows if r.get("status") == "ok" and not r.get("null_arm") and r.get("verified_all") is False]
    # The slowest first: a process whose 120 s pass reached fewer queries takes longer to check, so
    # starting those first keeps the wall time near max(the longest check, the total / jobs).
    todo.sort(key=lambda r: (r.get("verified") or 0) / max(1, r.get("ring_size") or 4096))
    print(f"{len(todo)} processes to check", file=sys.stderr)

    def check(r: dict) -> tuple[dict, dict]:
        cmd = [str(a.bin), "--arm", r["arm"], "--shape", r["shape"], "--m", str(r["m"]), "--seed",
               str(r["table_seed"]), "--ring-seed", str(r["ring_seed"]), "--ring", str(r.get("ring_size", 4096))]
        # The ring and table options of an exploratory run, as the process's row records them.
        if r.get("miss_permille"):
            cmd += ["--miss", str(r["miss_permille"])]
        if r.get("zipf"):
            cmd += ["--zipf", str(r["zipf"])]
        if r.get("vocabulary") == "long":
            cmd += ["--vocab", "long"]
        if r.get("decoys") is False:
            cmd += ["--no-decoy", "1"]
        t0 = time.monotonic()
        p = subprocess.run(cmd, capture_output=True, text=True)
        seconds = round(time.monotonic() - t0, 3)
        try:
            return r, dict(json.loads(p.stdout.strip().splitlines()[-1]), seconds=seconds)
        except (IndexError, json.JSONDecodeError):
            return r, {"status": "error", "reason": f"exit {p.returncode}: {p.stderr.strip()[:200]}", "seconds": seconds}

    bad = 0
    with a.out.open("w", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        for fut in as_completed([pool.submit(check, r) for r in todo]):
            r, c = fut.result()
            digests = c.get("table_digest") == r.get("table_digest") and c.get("ring_digest") == r.get("ring_digest")
            ok = c.get("status") == "checked" and c.get("agrees_all") is True and digests
            bad += not ok
            out = {"arm": r["arm"], "shape": r["shape"], "m": r["m"], "table_seed": r["table_seed"],
                   "ring_seed": r["ring_seed"], "run_verified": r.get("verified"), "queries": r.get("ring_size"),
                   "digests_match": digests, "agrees_all": ok, "check": c}
            f.write(json.dumps(out) + "\n")
            f.flush()
            print(f"{r['arm']} {r['shape']} {r['m']} ({r['table_seed']}, {r['ring_seed']}): run verified "
                  f"{r.get('verified')}, check {'agrees on every query' if ok else 'FAILS'}", file=sys.stderr)
    print(json.dumps({"processes": len(todo), "failing": bad}))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
