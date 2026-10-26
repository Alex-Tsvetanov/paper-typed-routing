#!/usr/bin/env python3
"""Round 3's timing probe before the freeze (STATE.md, Laptop request 5), on either system of the
laptop: one mirrored round of every arm at m = 10 and 100,000 on both shapes, the pair (111, 211),
timed, with the campaign draft's values (t3/plans/probe-L.json, probe-W.json).

    probe.py PLAN OUT [--count N]

Before the first window it refuses (exit 2) unless the binaries are the bring-up's: each file of
the plan's _expect_sha256 has that sha256 (the bring-up's p2run session line and build-info.json),
and no compiled source changed between the plan's _build_commit and this checkout (the build trees'
inputs were gated green against the D5 records at that commit). Then t3/p2run.py runs the plan,
every server log and p2gen result kept in OUT/probe.work, its lines in OUT/probe.jsonl, and its
session line must name the same sha256s.

OUT/probe-summary.json is for planning only: the windows by verdict, every window that was not
valid with its reasons, each arm's start-up seconds at m = 100,000, the mean seconds from one
window's start to the next by size, and from those an estimate of the campaign's hours; and the
largest share of the other processes around a window (p2run's "others", recorded, judged by no
rule yet: the frozen text decides whether and where it makes a window invalid). It holds no
rate and no count of answers, and compares no arm with another: the probe's windows are pre-freeze,
never analysed for H8 to H10 and never cited.

--count N is for a development run on the desktop only (D7): p2run in count mode, nothing timed,
and the summary holds no time. Exit status: 2 refused, else p2run's (0: every window ran).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labsteps as L  # noqa: E402

COMPILED = ("CMakeLists.txt", "server", "bench", "t1/h6_targets.cpp", "t3/gen", "t3/e2e_requests.cpp")
CAMPAIGN = {"sizes": (10, 100, 1000, 10000, 100000), "shapes": 2, "pairs": 16, "windows_per_arm": 2}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def binary_problems(want: dict) -> list:
    """Each file of _expect_sha256 that is missing or has another sha256, or []."""
    out = []
    for path, sha in want.items():
        f = Path(path)
        if not f.is_file():
            out.append(f"{path} is missing")
        elif (got := sha256(f)) != sha:
            out.append(f"{path} is not the bring-up's binary (sha256 {got[:12]}, want {sha[:12]})")
    return out


def refusals(plan: dict) -> list:
    """Why the probe must not time these binaries, or []."""
    commit = plan.get("_build_commit", "")
    want = plan.get("_expect_sha256") or {}
    if not commit or not want:
        return ["the plan names no _build_commit or _expect_sha256"]
    out = ["the paper clone has local changes"] if L.git("status", "--porcelain") else []
    p = subprocess.run(["git", "-C", str(L.ROOT), "diff", "--quiet", commit, "HEAD", "--", *COMPILED])
    if p.returncode == 1:
        out.append(f"compiled sources differ between {commit[:9]} and this checkout")
    elif p.returncode != 0:
        out.append(f"git could not compare {commit[:9]} with this checkout (git diff exit {p.returncode})")
    return out + binary_problems(want)


def same_file(path: str) -> str:
    """A path as p2run records it (resolved), in one case on Windows."""
    return os.path.normcase(str(Path(path).resolve()))


def session_differs(session: dict, want: dict) -> list:
    """Binaries the runner's session line names that the plan does not expect, or names with another sha256."""
    named = {same_file(session.get("p2gen", {}).get("argv", [""])[0]): session.get("p2gen", {}).get("sha256")}
    for prog in session.get("programs", []):
        named[same_file((prog.get("argv") or [prog.get("path", "")])[0])] = prog.get("sha256")
    expected = {same_file(p): sha for p, sha in want.items()}
    return ([f"{path}: session {sha}, want {expected[path]}" for path, sha in named.items()
             if path in expected and sha != expected[path]]
            + [f"{path}: in the session, not in the plan's _expect_sha256" for path in named if path not in expected])


def started_s(row: dict) -> float | None:
    s = row.get("started")
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").timestamp() if s else None


def summarize(rows: list, arms_per_system: int) -> dict:
    """The planning summary of a probe's window rows (see the module docstring)."""
    windows = [r for r in rows if r.get("type") == "window"]
    by_status: dict = {}
    for w in windows:
        by_status[w.get("status", "?")] = by_status.get(w.get("status", "?"), 0) + 1
    out = {"windows": len(windows), "by_status": by_status,
           "not_valid": [{k: w.get(k) for k in ("seq", "program", "arm", "entry", "shape", "m", "table_seed", "status",
                                                "reasons")}
                         for w in windows if w.get("status") != "valid"]}
    startup: dict = {}
    for w in windows:
        if w.get("m") == 100000 and w.get("startup_s") is not None:
            key = f"{w['program']}/{w['arm']}"
            startup[key] = max(startup.get(key, 0.0), float(w["startup_s"]))
    gaps: dict = {}
    timed = [w for w in windows if started_s(w) is not None]
    others = [w for w in windows if isinstance(w.get("others"), dict)]
    for a, b in zip(timed, timed[1:]):
        gaps.setdefault(a["m"], []).append(started_s(b) - started_s(a))
    if timed:
        out["startup_s_max_at_m100000"] = dict(sorted(startup.items()))
        out["seconds_start_to_start_mean"] = {str(m): round(statistics.mean(v), 2) for m, v in sorted(gaps.items())}
        busiest = max(others, key=lambda w: w["others"]["sum_pct_of_one_cpu"], default=None)
        out["others"] = {"windows_with": len(others), "windows_without": len(windows) - len(others),
                         "max_sum_pct_of_one_cpu": busiest and busiest["others"]["sum_pct_of_one_cpu"],
                         "max_at": busiest and {k: busiest.get(k) for k in ("seq", "program", "arm", "shape", "m")}}
        means = {m: statistics.mean(v) for m, v in gaps.items()}
        if 10 in means and 100000 in means:
            per_size = arms_per_system * CAMPAIGN["windows_per_arm"] * CAMPAIGN["shapes"] * CAMPAIGN["pairs"]
            seconds = per_size * (means[10] * (len(CAMPAIGN["sizes"]) - 1) + means[100000])
            out["campaign_estimate"] = {
                "windows": per_size * len(CAMPAIGN["sizes"]), "hours": round(seconds / 3600, 2),
                "basis": "this probe's mean seconds from one window's start to the next: m = 10's for the four "
                         "smaller sizes, m = 100,000's for 100,000; the A/A pilot and the start-up checks are not in it"}
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
    refused = refusals(plan)
    if refused:
        for r in refused:
            print(f"probe.py: refused: {r}", file=sys.stderr)
        (out / "probe-summary.json").write_text(json.dumps({"refused": refused}, indent=1) + "\n", encoding="utf-8")
        return 2
    print(f"probe.py: the binaries are the bring-up's at {plan['_build_commit'][:9]}; "
          f"paper {L.git('rev-parse', 'HEAD')}", flush=True)
    cmd = [L.PY, L.T3 / "p2run.py", a.plan.resolve(), "--out", out / "probe.jsonl", "--workdir", out / "probe.work",
           "--keep-logs"]
    if a.count is not None:
        cmd += ["--count", str(a.count)]
    rc = L.run(cmd, out / "probe.out", dict(os.environ, PYTHONUTF8="1"))
    jsonl = out / "probe.jsonl"
    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()] if jsonl.exists() else []
    summary = {"p2run_exit": rc, "mode": "timed" if a.count is None else "count", "build_commit": plan["_build_commit"],
               "note": "planning only: pre-freeze probe windows, never analysed for H8 to H10 and never cited",
               **summarize(rows, sum(len(p["arms"]) for p in plan["programs"]))}
    session = next((r for r in rows if r.get("type") == "session"), None)
    summary["session_binaries_differ"] = session_differs(session, plan["_expect_sha256"]) if session else ["no session line"]
    summary["binaries_after_run"] = binary_problems(plan["_expect_sha256"])  # p2v2.dll too, which no session line names
    (out / "probe-summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: summary.get(k) for k in ("p2run_exit", "windows", "by_status", "session_binaries_differ",
                                                  "binaries_after_run")}))
    return 2 if summary["session_binaries_differ"] or summary["binaries_after_run"] else rc


if __name__ == "__main__":
    sys.exit(main())
