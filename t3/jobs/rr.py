#!/usr/bin/env python3
"""Round 3 in the new loop (decision 21 (a), Alex 2026-10-28), on either system of the laptop: the fixed A/A
run, then the campaign, both round-robin (t3/plans/rr-aa-L.json and rr-L.json, rr-aa-W.json and rr-W.json).

    rr.py AA_PLAN PLAN OUT [--count N]

The same guards as t3/jobs/probe.py, for both plans: it refuses (exit 2) before the first window unless the
clone is clean, no compiled source changed since the plans' _build_commit, each file of _expect_sha256 is the
bring-up's, and both plans name the same build; afterwards each run's session line must name the same
binaries, and they are hashed again. t3/p2run.py runs the A/A plan into OUT/aa.jsonl, then, if that run
finished (exit 0, or 1 in count mode) with the expected binaries, the campaign into OUT/rr.jsonl; every
server log and p2gen result is kept in OUT/aa.work and OUT/rr.work.

OUT/rr-summary.json holds, per run, the windows, warm-ups and servers by verdict, every window that was not
valid, the other processes' and the idle servers' largest share of one CPU, each server's start-up at the
larger size, its peak memory, and the mean seconds from one window's start to the next. It holds no rate and no
count of answers: the medians and spreads come from the two records by t3/rr_results.py.

--count N is for a development run on the desktop only (D7): p2run in count mode, nothing timed.
Exit status: 2 refused (or a binary that changed), else the larger of the two runs' p2run exits.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labsteps as L  # noqa: E402
import probe  # noqa: E402

RUNS = ("aa", "rr")  # the A/A run first, then the campaign


def plan_refusals(aa: dict, rr: dict) -> list:
    out = probe.refusals(aa) + probe.refusals(rr)
    if (aa.get("_build_commit"), aa.get("_expect_sha256")) != (rr.get("_build_commit"), rr.get("_expect_sha256")):
        out.append("the A/A plan and the campaign's plan name different builds")
    if aa.get("schedule") != "round-robin" or rr.get("schedule") != "round-robin":
        out.append("both plans must be round-robin")
    return list(dict.fromkeys(out))


def _tally(rows: list) -> dict:
    out: dict = {}
    for r in rows:
        out[r.get("status", "?")] = out.get(r.get("status", "?"), 0) + 1
    return out


def summarize(rows: list) -> dict:
    """One run's planning summary (see the module docstring): verdicts, faults, shares, start-ups, memory, spacing."""
    kinds: dict = {}
    for r in rows:
        kinds.setdefault(r.get("type"), []).append(r)
    windows, servers = kinds.get("window", []), [s for e in kinds.get("cell_end", []) for s in e.get("servers", [])]
    out = {"windows": len(windows), "by_status": _tally(windows), "reruns": len([w for w in windows if w.get("rerun")]),
           "warmups": _tally(kinds.get("warmup", [])), "server_starts": _tally(kinds.get("server", [])),
           "servers_not_counting": [{k: s.get(k) for k in ("program", "arm", "entry", "reason_codes")}
                                    for s in servers if not s.get("windows_count")],
           "not_valid": [{k: w.get(k) for k in ("seq", "cell", "program", "arm", "entry", "round", "rerun", "status",
                                                "reasons")} for w in windows if w.get("status") != "valid"]}
    others = [w["others"] for w in windows if isinstance(w.get("others"), dict)]
    if others:
        idle = [o["idle_servers"] for o in others if isinstance(o.get("idle_servers"), dict)]
        out["others"] = {"windows_with": len(others), "max_sum_pct_of_one_cpu": max(o["sum_pct_of_one_cpu"] for o in others),
                         "idle_servers_max_sum_pct_of_one_cpu": max((i["sum_pct_of_one_cpu"] for i in idle), default=None),
                         "idle_servers_max_one_pct_of_one_cpu": max((i["max_pct_of_one_cpu"] for i in idle), default=None)}
    big = max((s.get("m", 0) for s in kinds.get("server", [])), default=0)
    out["startup_s_at_largest_m"] = {f"{s['program']}/{s['arm']}/{s['entry']}": s["startup_s"]
                                     for s in kinds.get("server", []) if s.get("m") == big and "startup_s" in s}
    out["peak_resident_kib"] = {f"{e['cell']} {s['program']}/{s['arm']}/{s['entry']}": s["memory"]["peak_resident_kib"]
                                for e in kinds.get("cell_end", []) for s in e.get("servers", []) if "memory" in s}
    timed = [w for w in windows if w.get("started")]
    gaps = [probe.started_s(b) - probe.started_s(a) for a, b in zip(timed, timed[1:]) if a.get("cell") == b.get("cell")]
    if gaps:  # within a cell; the next cell's starts and warm-ups fall between cells
        out["seconds_start_to_start_mean"] = round(statistics.mean(gaps), 3)
    return out


def run_one(name: str, plan_path: Path, out: Path, count: int | None) -> int:
    cmd = [L.PY, L.T3 / "p2run.py", plan_path.resolve(), "--out", out / f"{name}.jsonl", "--workdir", out / f"{name}.work",
           "--keep-logs"]
    if count is not None:
        cmd += ["--count", str(count)]
    return L.run(cmd, out / f"{name}.out", dict(os.environ, PYTHONUTF8="1"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("aa_plan", type=Path)
    ap.add_argument("plan", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--count", type=int, help="desktop development only: p2run count mode, nothing timed")
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plans = {"aa": json.loads(a.aa_plan.read_text(encoding="utf-8")), "rr": json.loads(a.plan.read_text(encoding="utf-8"))}
    refused = plan_refusals(plans["aa"], plans["rr"])
    if refused:
        for r in refused:
            print(f"rr.py: refused: {r}", file=sys.stderr)
        (out / "rr-summary.json").write_text(json.dumps({"refused": refused}, indent=1) + "\n", encoding="utf-8")
        return 2
    want = plans["rr"]["_expect_sha256"]
    print(f"rr.py: the binaries are the bring-up's at {plans['rr']['_build_commit'][:9]}; "
          f"paper {L.git('rev-parse', 'HEAD')}", flush=True)
    summary: dict = {"mode": "timed" if a.count is None else "count", "build_commit": plans["rr"]["_build_commit"],
                     "note": "no rate: the medians and spreads come from aa.jsonl and rr.jsonl by t3/rr_results.py"}
    codes: dict = {}
    for name, path in (("aa", a.aa_plan), ("rr", a.plan)):
        codes[name] = run_one(name, path, out, a.count)
        jsonl = out / f"{name}.jsonl"
        rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()] if jsonl.exists() else []
        session = next((r for r in rows if r.get("type") == "session"), None)
        summary[name] = {"p2run_exit": codes[name], **summarize(rows),
                         "session_binaries_differ": probe.session_differs(session, want) if session else ["no session line"]}
        if codes[name] not in (0, 1) or (codes[name] == 1 and a.count is None) or summary[name]["session_binaries_differ"]:
            break  # the A/A run did not finish, or ran other binaries: the campaign does not start
    summary["binaries_after_run"] = probe.binary_problems(want)
    (out / "rr-summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({name: {k: summary[name].get(k) for k in ("p2run_exit", "windows", "by_status", "servers_not_counting",
                                                               "session_binaries_differ")}
                      for name in RUNS if name in summary}))
    if summary["binaries_after_run"] or any(summary[n]["session_binaries_differ"] for n in RUNS if n in summary):
        return 2
    return max(codes.values())  # the campaign runs only after an A/A exit of 0 (timed) or 0 or 1 (count)


if __name__ == "__main__":
    sys.exit(main())
