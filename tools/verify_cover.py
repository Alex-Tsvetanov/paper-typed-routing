#!/usr/bin/env python3
"""Does tools/verify_answers cover every arm, and how long does a check on every query take?

    verify_cover.py VERIFY_ANSWERS RBENCH --out FILE.jsonl [--jobs N] [--pair T:R] [--timeout S]

For every arm of RBENCH (`rbench list`, the two null arms left out) and every cell of the main grid
that the arm runs in (the seven shapes at m = 10 to 100,000; std-regex and regexmatcher-v1 up to
10,000, their scope in bench/run_grid.sh), VERIFY_ANSWERS (tools/build_verify.py, linked from
RBENCH's own build) builds the arm on the table of seed T and checks every query of the ring of
seed R, untimed; its wall time is taken here. Each check is classed: "agrees" (every query),
"declared" (disagrees where bench/semantics.json declares the arm's semantics), "not built"
(the arm threw while building the table: in the grid such an arm is refused and absent, so no
check is needed; the reason is kept), or "failure" (a disagreement nobody declared, a timeout,
or no result). Writes one JSON
line per check and prints a summary: the arms covered, the failures, and every check that took
longer than 120 s (the agreement budget of a measured process, so the processes of that arm and
cell will be checked again at the end of a grid). Development evidence: engineering seeds only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bench"))
from check_agree import declared, load_semantics  # noqa: E402

SHAPES = ["static", "param-last", "param-first", "rest", "wild", "mixed-disjoint", "mixed-overlap"]
SIZES = [10, 100, 1000, 10000, 100000]
SCOPE = {"std-regex": 10000, "regexmatcher-v1": 10000}
BUDGET_S = 120.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verify", type=Path)
    ap.add_argument("rbench", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--pair", default="1:2")
    ap.add_argument("--timeout", type=float, default=3600.0)
    a = ap.parse_args()
    seed, ring = a.pair.split(":")
    listing = subprocess.run([str(a.rbench), "list"], capture_output=True, text=True, check=True).stdout
    arms = [l.split("\t")[0] for l in listing.splitlines() if l and not l.startswith("#") and l.split("\t")[0] not in ("null", "null-no405")]
    semantics = load_semantics()
    todo = [(arm, s, m) for m in SIZES for s in SHAPES for arm in arms if m <= SCOPE.get(arm, 10 ** 9)]
    # the slowest first, so the pool is not left waiting on one long check at the end
    todo.sort(key=lambda x: (-x[2], x[0] not in SCOPE))

    def check(arm: str, shape: str, m: int) -> dict:
        cmd = [str(a.verify), "--arm", arm, "--shape", shape, "--m", str(m), "--seed", seed, "--ring-seed", ring]
        t0 = time.monotonic()
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout)
            out = json.loads(p.stdout.strip().splitlines()[-1])
        except subprocess.TimeoutExpired:
            out = {"status": "timeout"}
        except (IndexError, json.JSONDecodeError):
            out = {"status": "error", "reason": "no result line"}
        out.update({"arm": arm, "shape": shape, "m": m, "seconds": round(time.monotonic() - t0, 3)})
        if out.get("status") == "checked" and out.get("agrees_all") is True:
            out["class"] = "agrees"
        elif out.get("status") == "checked" and declared(semantics, arm, shape):
            out["class"] = "declared"
        elif out.get("status") == "error" and out.get("reason"):
            out["class"] = "not built"
        else:
            out["class"] = "failure"
        return out

    rows = []
    with a.out.open("w", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=a.jobs) as pool:
        for fut in as_completed([pool.submit(check, *t) for t in todo]):
            r = fut.result()
            rows.append(r)
            f.write(json.dumps(r) + "\n")
            f.flush()
    covered = sorted({r["arm"] for r in rows if r["class"] in ("agrees", "declared")})
    failures = [r for r in rows if r["class"] == "failure"]
    slow = sorted((r for r in rows if r["seconds"] > BUDGET_S), key=lambda r: -r["seconds"])
    print(f"{len(rows)} checks, {len(arms)} arms, {len(covered)} covered by at least one check that agrees or "
          f"disagrees as declared; {len(failures)} failures; {sum(r['class'] == 'not built' for r in rows)} not built")
    for reason in sorted({f"{r['arm']}: {r.get('reason')}" for r in rows if r["class"] == "not built"}):
        print(f"  not built: {reason}")
    for r in failures:
        print(f"  FAILURE {r['arm']} {r['shape']} {r['m']}: {r.get('status')} {r.get('reason', '')}"
              f" {r.get('id_mismatches', '')} {r.get('capture_mismatches', '')}")
    print(f"checks above the {BUDGET_S:.0f} s agreement budget: {len(slow)}")
    for r in slow:
        print(f"  {r['arm']:<16} {r['shape']:<14} {r['m']:>7}  {r['seconds']:9.1f} s  {r['class']}")
    return 1 if failures or len(covered) != len(arms) else 0


if __name__ == "__main__":
    raise SystemExit(main())
