#!/usr/bin/env python3
"""Round 3's A/A runs without a campaign (Alex, 2026-10-28, answering the first records), on either system of the
laptop: the A/A run again (t3/plans/rr-aa-W.json, unchanged, at least 15 minutes after boot) and the k-server A/A
run (rr-aak-L.json, rr-aak-W.json: v2 seven times in each program).

    aa.py OUT PLAN [PLAN ...] [--count N]

The guards of t3/jobs/rr.py, for every plan: it refuses (exit 2) before the first window unless the clone is
clean, no compiled source changed since the plans' _build_commit, each file of _expect_sha256 is the bring-up's,
every plan names the same build, is round-robin and is an A/A plan as t3/rr_results.py reads one (v2 twice in
every program, or v2 k > 2 times in every program), and no two plans share a file name. t3/p2run.py then runs the plans in the order given, each into OUT/<plan's stem>.jsonl
with its server logs and p2gen results in OUT/<stem>.work; a run that did not finish (exit 0, or 1 in count mode)
or ran other binaries stops the rest. Afterwards the binaries are hashed again.

OUT/aa-summary.json holds rr.py's planning summary per run, keyed by the plan's stem: verdicts, faults, shares,
start-ups, memory and spacing, no rate. The statistics come from the records by t3/rr_results.py.

--count N is for a development run on the desktop only (D7): p2run in count mode, nothing timed.
Exit status: 2 refused (or a binary that changed), else the largest of the runs' p2run exits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labsteps as L  # noqa: E402
import probe  # noqa: E402
import rr  # noqa: E402
import rr_results  # noqa: E402


def is_aa(plan: dict) -> bool:
    """An A/A plan as t3/rr_results.py reads one: v2 twice in every program, or v2 k > 2 times in every program."""
    return bool(plan.get("programs")) and rr_results.kind_of(plan) in ("aa", "aak")


def plan_refusals(plans: list[tuple[Path, dict]]) -> list:
    out = [r for _, plan in plans for r in probe.refusals(plan)]
    if len({path.stem for path, _ in plans}) != len(plans):
        out.append("two plans share a file name, so their records would share one")
    if len({json.dumps([plan.get("_build_commit"), plan.get("_expect_sha256")], sort_keys=True) for _, plan in plans}) > 1:
        out.append("the plans name different builds")
    for path, plan in plans:
        if plan.get("schedule") != "round-robin":
            out.append(f"{path.name} is not round-robin")
        if not is_aa(plan):
            out.append(f"{path.name} is not an A/A plan (v2 twice, or more than twice, in every program)")
    return list(dict.fromkeys(out))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("plans", type=Path, nargs="+")
    ap.add_argument("--count", type=int, help="desktop development only: p2run count mode, nothing timed")
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plans = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in a.plans]
    refused = plan_refusals(plans)
    if refused:
        for r in refused:
            print(f"aa.py: refused: {r}", file=sys.stderr)
        (out / "aa-summary.json").write_text(json.dumps({"refused": refused}, indent=1) + "\n", encoding="utf-8")
        return 2
    first = plans[0][1]
    want = first["_expect_sha256"]
    print(f"aa.py: the binaries are the bring-up's at {first['_build_commit'][:9]}; paper {L.git('rev-parse', 'HEAD')}",
          flush=True)
    summary: dict = {"mode": "timed" if a.count is None else "count", "build_commit": first["_build_commit"],
                     "runs": [path.stem for path, _ in plans],
                     "note": "no rate: the medians and spreads come from the records by t3/rr_results.py"}
    codes: dict = {}
    for path, _ in plans:
        codes[path.stem], summary[path.stem], go_on = rr.run_and_summarize(path.stem, path, out, a.count, want)
        if not go_on:
            break  # a run did not finish, or ran other binaries: the rest do not start
    summary["binaries_after_run"] = probe.binary_problems(want)
    (out / "aa-summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({name: {k: summary[name].get(k) for k in ("p2run_exit", "windows", "by_status", "servers_not_counting",
                                                               "session_binaries_differ")} for name in codes}))
    if summary["binaries_after_run"] or any(summary[name]["session_binaries_differ"] for name in codes):
        return 2
    return max(codes.values())


if __name__ == "__main__":
    sys.exit(main())
