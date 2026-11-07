#!/usr/bin/env python3
"""Write a sanitizer record for rbench from a sanitizer build and its run_grid.sh output.

The record has the shape of the Papers repo's lab/bin/sanitize.sh records (repo, commit,
date, host, green, compiler, presets[]) plus what the build compiled, from build.sh's
inputs.json: inputs_hash per target (rbench and each arm_*; first-party files only, RegexMatcher
v2's included), the configuration, the dependency roots and third_party (each fetched archive's URL
and hash as used), and the sha256 of the pins.cmake the build used (pins_sha256), which the gate
matches with a measured build's (bench/gate_lib.py). One preset per step: build, agree, probes, and the
quick cells of each arm; and, when the build has the adversarial tool (a target "adversarial" in
inputs.json), its unit test, its self-test and its quick cells (sanitize_rbench.sh's out/adversarial*); and,
when the build has the ablation arms of design/review-runs/ablations.md, their answers test (test_ablation,
out/ablation-test.txt).

Green means: the build succeeded; every agreement row agrees, is refused by design, or
disagrees where semantics.json declares the arm's semantics, in the declared kind
(check_agree.py); every probe ran; every cell ended with status ok or refused, or disagrees as
declared; the grid script
exited 0; the adversarial tool, if the build has it, passed its unit test and its self-test over all 66
queries of its 22 tables, and each of its 44 cells ended with status ok and its checks passed; the
ablation copies' answers test, if the build has those arms, passed over all 112 tables and 2,293,760 lookups
and reached a 404, a 405 and an answer with captures; and the standard error of all runs holds no sanitizer
report. Reports are copied into the record.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from check_agree import fits, load_semantics, row_passes
from gate_lib import file_sha256

# The first line of every sanitizer report and every SUMMARY line; the same text as the
# Papers repo's lab/bin/sanitize.sh, checked by its lab/bin/test_report_pattern.sh.
REPORT = re.compile(r"ERROR: (Address|Memory|Leak|Thread)Sanitizer|WARNING: (Memory|Thread)Sanitizer|"
                    r"SUMMARY: [A-Za-z]+Sanitizer|runtime error:")
COMPILER_ID = re.compile(r"^-- The CXX compiler identification is (.+?)\s*$", re.MULTILINE)


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# The adversarial tool's plan (design/review-runs/adversarial.md): 22 tables (11 and the same with a
# catch-all) with three queries each in the self-test, and 44 cells. A record whose self-test or quick cells
# cover fewer is red.
ADV_TABLES = 22
ADV_QUERIES = 66
ADV_CELLS = 44


def tool_presets(out: Path, has_tool: bool, compiler: str) -> list[dict]:
    """The adversarial tool's presets (sanitize_rbench.sh): none for a build without it; red ones
    for a build with it whose outputs are missing."""
    if not has_tool:
        return []

    def text(name: str) -> str:
        return (out / name).read_text(encoding="utf-8", errors="replace") if (out / name).exists() else ""

    exits = dict(kv.split("=", 1) for kv in text("adversarial-exit.txt").split() if "=" in kv)
    self_text = text("adversarial-selftest.txt")
    unit_ok = exits.get("test_exit") == "0" and "test_adversarial: ok" in text("adversarial-test.txt")
    self_ok = exits.get("selftest_exit") == "0" and re.search(
        rf"^self-test: {ADV_QUERIES} queries on {ADV_TABLES} tables, 0 failing$", self_text, re.MULTILINE) is not None
    rows = jsonl(out / "adversarial.jsonl")
    bad = [r for r in rows if r.get("status") != "ok" or r.get("checks_ok") is not True or r.get("agrees") is not True]
    planned = int(exits.get("cells", "0") or 0)
    cells_ok = planned == ADV_CELLS and len(rows) == ADV_CELLS and not bad
    return [{"preset": "adversarial/unit-test", "status": "green" if unit_ok else "red",
             "detail": f"exit {exits.get('test_exit', 'none')}", "compiler": compiler},
            {"preset": "adversarial/self-test", "status": "green" if self_ok else "red",
             "detail": (self_text.strip().splitlines() or ["no output"])[-1], "compiler": compiler},
            {"preset": "adversarial/cells", "status": "green" if cells_ok else "red",
             "detail": f"{len(rows)} of {planned} cells",
             "failures": [f"{r.get('cell')}: {r.get('status')} {r.get('exit', '')}".strip() for r in bad][:20],
             "compiler": compiler}]


# The ablation answers test (bench/tools/test_ablation.cpp) builds 7 shapes x 4 sizes x 2 seeds x 2 method
# counts = 112 tables and compares 112 x 7 variants x 512 queries x 8 methods = 3,211,264 lookups. A record
# whose test saw other numbers, fewer or more, is red.
ABL_TABLES = 112
ABL_LOOKUPS = 3211264


def review_presets(out: Path, has_review: bool, compiler: str) -> list[dict]:
    """The review arms' answers test (sanitize_rbench.sh's out/ablation-test.txt and ablation-exit.txt): none
    for a build without the ablation arms; red when its output is missing or reports a failure."""
    if not has_review:
        return []
    def text_of(name: str) -> str:
        return (out / name).read_text(encoding="utf-8", errors="replace") if (out / name).exists() else ""

    text = text_of("ablation-test.txt")
    exit_text = text_of("ablation-exit.txt")
    ok = "test_exit=0" in exit_text.split() and re.search(
        rf"^test_ablation: ok \({ABL_TABLES} tables, {ABL_LOOKUPS} lookups compared, 0 failing\)$", text,
        re.MULTILINE) is not None
    return [{"preset": "review/ablation-answers", "status": "green" if ok else "red",
             "detail": (text.strip().splitlines() or ["no output"])[-1], "compiler": compiler}]


def report_blocks(text: str) -> tuple[int, list[str]]:
    findings = [line for line in text.splitlines() if REPORT.search(line)]
    blocks, current = [], []
    for line in text.splitlines():
        if REPORT.search(line) or (current and line.strip() and not line.startswith("## cell")):
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return len(findings), blocks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", type=Path, required=True, help="the sanitizer build directory")
    ap.add_argument("--out-dir", type=Path, required=True, help="run_grid.sh output directory")
    ap.add_argument("--record", type=Path, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--commit", required=True, help="rbench code commit")
    ap.add_argument("--repo-head", required=True)
    ap.add_argument("--regexmatcher-commit", required=True, help="the RegexMatcher v2 commit the build compiled")
    ap.add_argument("--sanitizer", required=True)
    ap.add_argument("--cmake-args", default="")
    ap.add_argument("--options", default="")
    ap.add_argument("--note", default="", help="what a reader of the record must know (a suppression, a rerun)")
    ap.add_argument("--build-exit", type=int, required=True)
    ap.add_argument("--grid-exit", type=int, required=True)
    ap.add_argument("--seconds", type=int, required=True)
    ap.add_argument("--host", default=socket.gethostname())
    ap.add_argument("--pins", type=Path, required=True, help="the pins.cmake the build used")
    ap.add_argument("--logs-archive", default="", help="the logs packed (bench/keep_record_logs.sh)")
    ap.add_argument("--logs-sha256", default="", help="the sha256 of --logs-archive")
    args = ap.parse_args()

    log = Path(f"{args.build}.log")
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    m = COMPILER_ID.search(log_text)
    compiler = m.group(1) if m else ""
    inputs_path = Path(f"{args.build}.inputs.json")
    inputs: dict = {"inputs_error": "no inputs.json (the build failed?)"}
    if inputs_path.exists():
        b = json.loads(inputs_path.read_text(encoding="utf-8"))["builds"]["rbench"]
        inputs = {"inputs_hash": {t: v["inputs_hash"] for t, v in b["targets"].items()},
                  "inputs_files": {t: v["files"] for t, v in b["targets"].items()},
                  "config": next((v for k, v in b.items() if k == "config" or k.endswith("_config")), None),
                  "dep_roots": b.get("dep_roots"), "third_party": b["third_party"]}

    out = args.out_dir
    presets = [{"preset": "build", "status": "green" if args.build_exit == 0 else "red",
                "detail": f"exit {args.build_exit}", "compiler": compiler}]
    semantics = load_semantics()
    agree = jsonl(out / "agree.jsonl")
    bad_agree = [r for r in agree if not row_passes(r, semantics)]
    presets.append({"preset": "agree", "status": "green" if agree and not bad_agree else "red",
                    "detail": f"{len(agree)} rows, {len(bad_agree)} not agreeing",
                    "failures": [f"{r['arm']} {r['shape']} {r['m']}: {r.get('status')}" for r in bad_agree][:20],
                    "compiler": compiler})
    probes = jsonl(out / "probes.jsonl")
    exit_txt = (out / "exit.txt").read_text(encoding="utf-8") if (out / "exit.txt").exists() else ""
    probe_ok = bool(probes) and "probe_exit=0" in exit_txt
    presets.append({"preset": "probes", "status": "green" if probe_ok else "red",
                    "detail": f"{len(probes)} probe lookups ran", "compiler": compiler})
    by_arm = defaultdict(list)
    for r in jsonl(out / "cells.jsonl"):
        by_arm[r["arm"]].append(r)
    planned = defaultdict(int)
    for line in (out / "plan.txt").read_text(encoding="utf-8").splitlines() if (out / "plan.txt").exists() else []:
        planned[line.split()[0]] += 1
    for arm in sorted(planned):
        rows = by_arm.get(arm, [])
        bad = [r for r in rows if r.get("status") not in ("ok", "refused")
               and not (r.get("status") == "disagrees" and fits(semantics, r))]
        green = len(rows) == planned[arm] and not bad
        presets.append({"preset": f"cells/{arm}", "status": "green" if green else "red",
                        "detail": f"{len(rows)} of {planned[arm]} cells, "
                                  f"{sum(r.get('status') == 'refused' for r in rows)} refused",
                        "failures": [f"{r['shape']} {r['m']}: {r.get('status')} {r.get('reason', r.get('exit', ''))}"
                                     for r in bad][:20],
                        "compiler": compiler})
    has_tool = "adversarial" in (inputs.get("inputs_hash") or {})
    presets += tool_presets(out, has_tool, compiler)
    has_review = any(t.startswith("arm_regexmatcher_v2_ab_") or t == "arm_regexmatcher_v2_copy"
                     for t in (inputs.get("inputs_hash") or {}))
    presets += review_presets(out, has_review, compiler)
    stderr = (out / "stderr.log").read_text(encoding="utf-8", errors="replace") if (out / "stderr.log").exists() else ""
    reports, blocks = report_blocks(stderr)
    green = (args.build_exit == 0 and args.grid_exit == 0 and reports == 0
             and all(p["status"] == "green" for p in presets))
    record = {"repo": args.repo, "commit": args.commit, "extra_cmake_args": args.cmake_args,
              "date": datetime.now().astimezone().isoformat(timespec="seconds"), "host": args.host,
              "green": green, "compiler": compiler, **inputs, "pins_sha256": file_sha256(args.pins),
              "pins_file": "bench/cmake/pins.cmake", "presets": presets,
              "artifact": "rbench", "arms": sorted(planned), "tools": ["adversarial"] if has_tool else [],
              "sanitizer": args.sanitizer,
              "repo_head": args.repo_head, "regexmatcher_commit": args.regexmatcher_commit,
              "sanitizer_options": args.options,
              "build_exit": args.build_exit, "grid_exit": args.grid_exit, "grid_summary": exit_txt.strip(),
              "seconds": args.seconds, "sanitizer_reports": reports, "report_blocks": blocks[:50],
              "note": args.note, "logs_archive": args.logs_archive, "logs_archive_sha256": args.logs_sha256}
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(record) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("commit", "sanitizer", "compiler", "green", "sanitizer_reports")}))
    for p in presets:
        print(f"  {p['preset']}: {p['status']} ({p['detail']})")
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
