#!/usr/bin/env python3
"""Write the sanitizer record of the paper's minimal server from a t1/sanitize_h6.sh work directory.

The record has the shape of the rbench records (bench/sanitizer_record.py): repo, commit, date,
host, green, compiler, what the build compiled (inputs_hash per target: mserver, the libraries it
links and h6_targets; project mode, RegexMatcher v2 as the dependency root regexmatcher; the
configuration; third_party, each fetched archive's URL and hash as used) with mserver_arms's hash of
its inputs under regexmatcher/include/, the sha256 of the pins.cmake the build used (pins_sha256, which
the gate matches with a measured build's, bench/gate_lib.py), and one preset per step: the
build, the CTest suite, then one per H6 cell and router arm (h6_targets wrote the routes and
targets; mserver answered every target 200 with the fixed body, GET / likewise, the unmatched
path as the arm should, and a pipelined burst in order; the server exited 0 on SIGTERM). Green
means every preset is green and no log or standard error of any step holds a sanitizer report;
reports are copied into the record.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
from gate_lib import file_sha256  # noqa: E402

# The first line of every sanitizer report and every SUMMARY line; the same text as the
# Papers repo's lab/bin/sanitize.sh, checked by its lab/bin/test_report_pattern.sh.
REPORT = re.compile(r"ERROR: (Address|Memory|Leak|Thread)Sanitizer|WARNING: (Memory|Thread)Sanitizer|"
                    r"SUMMARY: [A-Za-z]+Sanitizer|runtime error:")
COMPILER_ID = re.compile(r"^-- The CXX compiler identification is (.+?)\s*$", re.MULTILINE)
# CTest's summary line: "P% tests passed, F tests failed out of T"; CTest 4 writes
# "100% tests passed out of T" when none failed (found on L, CTest 4.4.3, 2026-09-30).
CTEST_LINE = re.compile(r"(\d+)% tests passed(?:, (\d+) tests failed)? out of (\d+)")


def ctest_summary(text: str) -> tuple[int, int] | None:
    """(total, failed) from the last CTest summary line of TEXT (failed 0 when the line has no
    failed clause), or None if there is none."""
    found = CTEST_LINE.findall(text)
    if not found:
        return None
    _, failed, total = found[-1]
    return int(total), int(failed) if failed else 0
CELLS, ARMS = 9, 3


def blocks(text: str) -> list[str]:
    lines = text.splitlines()
    return ["\n".join(lines[i:i + 30]) for i, line in enumerate(lines) if REPORT.search(line)]


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("build", "work", "record", "repo", "commit", "repo-head", "regexmatcher-commit",
              "sanitizer", "cmake-args", "options", "host"):
        ap.add_argument(f"--{k}", required=True)
    for k in ("build-exit", "ctest-exit", "seconds"):
        ap.add_argument(f"--{k}", type=int, required=True)
    ap.add_argument("--pins", required=True, help="the pins.cmake the build used")
    ap.add_argument("--logs-archive", default="", help="the logs packed (bench/keep_record_logs.sh)")
    ap.add_argument("--logs-sha256", default="", help="the sha256 of --logs-archive")
    a = ap.parse_args()
    work = Path(a.work)
    build_log = read(work / "build.log")
    m = COMPILER_ID.search(build_log)
    compiler = m.group(1) if m else "unknown"
    inputs: dict = {"inputs_error": "no inputs.json (the build failed?)"}
    if (work / "build.inputs.json").exists():
        b = json.loads(read(work / "build.inputs.json"))["builds"]["h6"]
        inputs = {"inputs_hash": {t: v["inputs_hash"] for t, v in b["targets"].items()},
                  "inputs_files": {t: v["files"] for t, v in b["targets"].items()},
                  "config": next((v for k, v in b.items() if k == "config" or k.endswith("_config")), None),
                  "dep_roots": b.get("dep_roots"), "third_party": b.get("third_party")}
        if (work / "build.v2-include.json").exists():
            t = json.loads(read(work / "build.v2-include.json"))["builds"]["h6"]["targets"]
            inputs["prefix_hashes"] = {n: {p: h["hash"] for p, h in v.get("prefix_hashes", {}).items()} for n, v in t.items()}

    presets = [{"preset": "build", "status": "green" if a.build_exit == 0 else "red", "detail": f"exit {a.build_exit}",
                "compiler": compiler}]
    total, failed = ctest_summary(read(work / "ctest.log")) or (0, -1)
    presets.append({"preset": "ctest", "status": "green" if a.ctest_exit == 0 and total > 0 and failed == 0 else "red",
                    "detail": f"exit {a.ctest_exit}, {total} tests, {failed} failed"})
    steps = [json.loads(l) for l in read(work / "steps.jsonl").splitlines() if l.strip()]
    for s in steps:
        ex = s.get("exercise") or {}
        ok = s["targets_exit"] == 0 and s["exercise_exit"] == 0 and str(s["server_exit"]) == "0"
        presets.append({"preset": f"cell/{s['cell']}/{s['arm']}", "status": "green" if ok else "red",
                        "detail": f"h6_targets exit {s['targets_exit']}, {ex.get('requests', 0)} requests, "
                                  f"{ex.get('failures', '?')} failed, server exit {s['server_exit']}",
                        "failures": ex.get("first", [])})
    if a.build_exit == 0 and len(steps) != CELLS * ARMS:
        presets.append({"preset": "cells", "status": "red", "detail": f"{len(steps)} of {CELLS * ARMS} cell and arm runs"})
    reports = []
    for f in [work / "build.log", work / "ctest.log", work / "ctest.err", *sorted(work.rglob("*.err"))]:
        reports += [f"{f.relative_to(work)}:\n{b}" for b in blocks(read(f))]
    green = all(p["status"] == "green" for p in presets) and not reports and "inputs_hash" in inputs \
        and bool(inputs.get("prefix_hashes"))
    rec = {"repo": a.repo, "commit": a.commit, "repo_head": a.repo_head,
           "date": datetime.now().astimezone().isoformat(timespec="seconds"), "host": a.host, "green": green,
           "compiler": compiler, **inputs, "pins_sha256": file_sha256(Path(a.pins)), "pins_file": "bench/cmake/pins.cmake",
           "presets": presets, "tool": "mserver", "sanitizer": a.sanitizer,
           "regexmatcher_commit": a.regexmatcher_commit, "cmake_args": a.cmake_args, "sanitizer_options": a.options,
           "build_exit": a.build_exit, "ctest_exit": a.ctest_exit, "seconds": a.seconds,
           "sanitizer_reports": len(reports), "report_blocks": reports[:20],
           "logs_archive": a.logs_archive, "logs_archive_sha256": a.logs_sha256,
           "note": "The paper's minimal server (server/) and t1/h6_targets, built under the sanitizer: the server's "
                   "tests, then each H6 cell served by each router arm (t1/sanitize_h6.sh)."}
    Path(a.record).parent.mkdir(parents=True, exist_ok=True)
    Path(a.record).write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"record": a.record, "green": green, "sanitizer": a.sanitizer, "reports": len(reports)}))
    for p in presets:
        if p["status"] != "green" or not p["preset"].startswith("cell/"):
            print(f"  {p['preset']}: {p['status']} ({p['detail']})")
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
