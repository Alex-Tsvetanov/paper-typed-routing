#!/usr/bin/env python3
"""Round 3's A/A pilot (STATE.md, Laptop request 7), on either system of the laptop: v2 against v2 in
each of the three programs, one mirrored round of four windows at every cell of H8 (t3/plans/pilot-L.json,
pilot-W.json), timed, with the campaign draft's window values.

    pilot.py PLAN OUT [--count N]

The same guards as t3/jobs/probe.py: it refuses (exit 2) before the first window unless the clone is
clean, no compiled source changed since the plan's _build_commit, and each file of _expect_sha256 is the
bring-up's; afterwards the runner's session line must name the same binaries, and they are hashed again.
t3/p2run.py runs the plan, every server log and p2gen result kept in OUT/pilot.work, its lines in
OUT/pilot.jsonl.

OUT/pilot-summary.json holds the windows by verdict, every window that was not valid, the other
processes' largest share, and the mean spacing of the windows by size. It holds no rate, no count of
answers and no ratio: delta (H8), the minimum D_T0 (H9) and the ns margin (H10) come from pilot.jsonl
by t3/pilot_analysis.py, under the rule fixed in hypotheses-round3.md before the pilot runs.

--count N is for a development run on the desktop only (D7): p2run in count mode, nothing timed.
Exit status: 2 refused, else p2run's (0: every window ran).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labsteps as L  # noqa: E402
import probe  # noqa: E402


def summarize(rows: list) -> dict:
    """The probe's planning summary without its campaign estimate (the pilot is not the campaign)."""
    out = probe.summarize(rows, arms_per_system=0)
    out.pop("campaign_estimate", None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--count", type=int, help="desktop development only: p2run count mode, nothing timed")
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    refused = probe.refusals(plan)
    if refused:
        for r in refused:
            print(f"pilot.py: refused: {r}", file=sys.stderr)
        (out / "pilot-summary.json").write_text(json.dumps({"refused": refused}, indent=1) + "\n", encoding="utf-8")
        return 2
    print(f"pilot.py: the binaries are the bring-up's at {plan['_build_commit'][:9]}; "
          f"paper {L.git('rev-parse', 'HEAD')}", flush=True)
    cmd = [L.PY, L.T3 / "p2run.py", a.plan.resolve(), "--out", out / "pilot.jsonl", "--workdir", out / "pilot.work",
           "--keep-logs"]
    if a.count is not None:
        cmd += ["--count", str(a.count)]
    rc = L.run(cmd, out / "pilot.out", dict(os.environ, PYTHONUTF8="1"))
    jsonl = out / "pilot.jsonl"
    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()] if jsonl.exists() else []
    summary = {"p2run_exit": rc, "mode": "timed" if a.count is None else "count", "build_commit": plan["_build_commit"],
               "note": "A/A only: v2 against v2; delta, D_T0's minimum and H10's margin come from pilot.jsonl by "
                       "t3/pilot_analysis.py, not from this summary",
               **summarize(rows)}
    session = next((r for r in rows if r.get("type") == "session"), None)
    summary["session_binaries_differ"] = probe.session_differs(session, plan["_expect_sha256"]) if session else ["no session line"]
    summary["binaries_after_run"] = probe.binary_problems(plan["_expect_sha256"])
    (out / "pilot-summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: summary.get(k) for k in ("p2run_exit", "windows", "by_status", "session_binaries_differ",
                                                  "binaries_after_run")}))
    return 2 if summary["session_binaries_differ"] or summary["binaries_after_run"] else rc


if __name__ == "__main__":
    sys.exit(main())
