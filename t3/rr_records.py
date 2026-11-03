#!/usr/bin/env python3
"""Facts of round 3's records that the analysis files do not hold, for the paper's macros (t3/rr_macros.py).

    python t3/rr_records.py --analysis design/round3/floor-W.json --analysis design/round3/floor-L.json \\
        --analysis design/round3/rr-W.json --jobs DIR [DIR ...] --out results/round3/records.json [--plans DIR]

Each --analysis file is one of t3/rr_results.py's outputs wrapped with its inputs (floor-W.json, floor-L.json,
rr-W.json): its "inputs" name each record by job and file, with the file's sha256. Each --jobs DIR is one job's
unpacked archive, the folder named by the job (the archive's top folder); it holds those files and the lab's
record.json. A missing file, a sha256 that differs, a record rr_results.py refuses or an analysis file without the
parts read here ends the run (exit 2) and writes nothing. --plans is rr_results.py's committed plans folder.

Per record (one per input; a record listed twice is refused) it writes:
- windows: the planned windows, the window lines by verdict (reruns included) and the rounds that ran again;
- job: from the lab's record.json, the system's uptime at the job's start and the command's duration, in s;
- start: the valid windows that began within START_S of the record's first window ("first"), and the later valid
  windows of the same cells ("later"), whether their round counted or was run again: a check of the host, not a
  result. For each window, its ns per request as a percentage above the median of the same contestant (program and
  arm) in the campaign of the analysis file that lists the record; the least and largest of each group, the range
  of the first windows' own clock readings (clock.mhz) and the largest share of other processes among them. Made
  after the floor table and disclosed with no cause claimed (Alex, 2026-10-29). Starts are read to the second;
- floor_rounds, for an A/A record: per cell and program with a floor, the counted round (reruns replace their
  round; valid windows of both entries) with the largest |d| = t(entry 0) - t(entry 1), and its start in s after the
  record's first window (the later of its two windows). The |d| must equal the analysis file's largest |d| for that
  cell and program, else the run refuses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rr_results as R  # noqa: E402

START_S = 30
TOLERANCE_NS = 1e-6


class RecordsError(Exception):
    """A refusal: nothing is written."""


def started(w: dict) -> datetime:
    return datetime.strptime(w["started"], "%Y-%m-%dT%H:%M:%S%z")


def ns(w: dict) -> float | None:
    x = R.rate(w)
    return 1e9 / x if x else None


def campaign_medians(analysis: dict, system: str) -> dict:
    """(cell, program, arm) -> the campaign's median ns per request."""
    cells = analysis["systems"][system]["rr"]["cells"]
    return {(c, p, s["arm"]): s["ns_per_request"]["median"] for c, cell in cells.items()
            for p, prog in cell["programs"].items() for s in prog["contestants"] if s["ns_per_request"]["n"]}


def window_facts(rows: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    for w in (r for r in rows if r.get("type") == "window"):
        by_status[w["status"]] = by_status.get(w["status"], 0) + 1
    rerun_rounds = sum(len(r["rounds"]) for r in rows if r.get("type") == "rerun")
    return {"planned": rows[0]["windows"], "by_status": dict(sorted(by_status.items())), "rerun_rounds": rerun_rounds}


def job_facts(record_json: Path) -> dict:
    r = json.loads(record_json.read_text(encoding="utf-8"))
    start, end = datetime.fromisoformat(r["command_start"]), datetime.fromisoformat(r["command_end"])
    return {"uptime_s": r["start_state"]["uptime_s"], "duration_s": (end - start).total_seconds()}


def _span(values: list[float]) -> list[float] | None:
    return [min(values), max(values)] if values else None


def start_check(rows: list[dict], reference: dict) -> dict:
    ws = [r for r in rows if r.get("type") == "window"]
    t0 = min(started(w) for w in ws)
    valid = [w for w in ws if w["status"] == "valid" and ns(w) and (w["cell"], w["program"], w["arm"]) in reference]
    first = [w for w in valid if (started(w) - t0).total_seconds() <= START_S]
    first_seqs, cells = {w["seq"] for w in first}, {w["cell"] for w in first}
    later = [w for w in valid if w["seq"] not in first_seqs and w["cell"] in cells]

    def above(w: dict) -> float:
        return (ns(w) / reference[(w["cell"], w["program"], w["arm"])] - 1) * 100

    others = [(w.get("others") or {}).get("sum_pct_of_one_cpu") for w in first]
    return {"first_windows": len(first), "first_pct": _span([above(w) for w in first]),
            "later_windows": len(later), "later_pct": _span([above(w) for w in later]),
            "first_clock_mhz": _span([w["clock"]["mhz"] for w in first if (w.get("clock") or {}).get("mhz")]),
            "first_others_max_pct": max((o for o in others if o is not None), default=None)}


def floor_rounds(rows: list[dict], aa_cells: dict) -> dict:
    ws = [r for r in rows if r.get("type") == "window"]
    t0 = min(started(w) for w in ws)
    rerun = {(r["cell"], rd["round"]) for r in rows if r.get("type") == "rerun" for rd in r["rounds"]}
    by: dict = {}
    for w in ws:
        if bool(w.get("rerun")) != ((w["cell"], w["round"]) in rerun) or w["status"] != "valid" or not ns(w):
            continue
        by.setdefault((w["cell"], w["program"], w["round"]), {})[w["entry"]] = (ns(w), started(w))
    out: dict = {}
    for (cell, program, rnd), e in sorted(by.items()):
        d_ns = aa_cells[cell]["programs"][program]["d_ns"]
        if 0 not in e or 1 not in e or not d_ns.get("n"):
            continue   # no floor for this program here: an entry's windows do not count
        d = e[0][0] - e[1][0]
        best = out.setdefault(cell, {}).get(program)
        if best is None or abs(d) > abs(best["d_ns"]):
            out[cell][program] = {"round": rnd, "d_ns": d, "offset_s": (max(e[0][1], e[1][1]) - t0).total_seconds()}
    for cell, programs in out.items():
        for program, best in programs.items():
            d = aa_cells[cell]["programs"][program]["d_ns"]
            if abs(abs(best["d_ns"]) - max(abs(d["min"]), abs(d["max"]))) > TOLERANCE_NS:
                raise RecordsError(f"{cell} {program}: largest |d| {best['d_ns']} is not the analysis file's")
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one_record(item: dict, analysis: dict, name: str, jobs: dict[str, Path], plans: Path) -> dict:
    job_dir = jobs.get(item["job"])
    if job_dir is None:
        raise RecordsError(f"{name}: no --jobs folder named {item['job']}")
    path = job_dir / item["file"]
    if not path.is_file() or sha256(path) != item["sha256"]:
        raise RecordsError(f"{name}: {item['job']}/{item['file']} is missing or its sha256 is not {item['sha256']}")
    try:
        system, kind, rows = R.load_record(path, plans)
        out = {"analysis": name, "job": item["job"], "file": item["file"], "sha256": item["sha256"], "system": system,
               "kind": kind, "windows": window_facts(rows), "job_record": job_facts(job_dir / "record.json"),
               "start": start_check(rows, campaign_medians(analysis, system))}
        if kind == "aa":
            out["floor_rounds"] = floor_rounds(rows, analysis["systems"][system]["aa"]["cells"])
    except R.RecordError as e:
        raise RecordsError(str(e)) from e
    except (KeyError, OSError, ValueError) as e:
        raise RecordsError(f"{name}: {item['job']}/{item['file']}: {type(e).__name__}: {e}") from e
    return out


def build(analysis_paths: list[Path], job_dirs: list[Path], plans: Path = R.PLANS) -> dict:
    jobs = {d.name: d for d in job_dirs}
    records, seen = [], set()
    for path in analysis_paths:
        wrapped = json.loads(path.read_text(encoding="utf-8"))
        for item in wrapped["inputs"]:
            if (item["job"], item["file"]) in seen:
                raise RecordsError(f"{item['job']}/{item['file']} is listed twice")
            seen.add((item["job"], item["file"]))
            records.append(one_record(item, wrapped["analysis"], path.name, jobs, plans))
    return {"rule": "t3/rr_records.py's docstring", "start_s": START_S, "records": records}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", type=Path, action="append", required=True)
    ap.add_argument("--jobs", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--plans", type=Path, default=R.PLANS)
    a = ap.parse_args(argv)
    try:
        result = build(a.analysis, a.jobs, a.plans)
    except (RecordsError, KeyError, OSError, ValueError) as e:
        print(f"rr_records: refused: {e}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
