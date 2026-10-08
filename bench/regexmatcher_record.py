#!/usr/bin/env python3
"""Write a sanitizer record for RegexMatcher v2's test suite (bench/sanitize_regexmatcher.sh).

The record names the commit, the host, the compiler, the sanitizer and its runtime options, the
CMake arguments, the CTest result, and what the test targets compiled (inputs_hash.py, project
mode, root label regexmatcher): the inputs hash of each target and the hash of its inputs under
regexmatcher/include/, which the records gate matches with the v2 arms' builds.

Green means: the build succeeded, CTest ran and every test passed, the inputs were hashed, and
the build and test output hold no sanitizer report. Reports are copied into the record.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# The first line of every sanitizer report and every SUMMARY line; the same text as the Papers
# repo's lab/bin/sanitize.sh, checked by its lab/bin/test_report_pattern.sh.
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


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for a in ("--record", "--logs", "--repo", "--commit", "--sanitizer", "--options", "--cmake-args", "--host"):
        ap.add_argument(a, required=True)
    for a in ("--build-exit", "--ctest-exit", "--inputs-exit", "--seconds"):
        ap.add_argument(a, type=int, required=True)
    ap.add_argument("--logs-archive", default="", help="the logs packed (bench/keep_record_logs.sh)")
    ap.add_argument("--logs-sha256", default="", help="the sha256 of --logs-archive")
    ap.add_argument("--note", default="", help="what a reader of the record must know")
    args = ap.parse_args()
    logs = Path(args.logs)
    build_log, ctest_log = read(logs / "build.log"), read(logs / "ctest.log")

    blocks = []
    for text in (build_log, ctest_log):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if REPORT.search(line):
                blocks.append("\n".join(lines[i:i + 12]))
    total, failed = ctest_summary(ctest_log) or (0, -1)
    compiler = COMPILER_ID.findall(build_log)
    inputs = json.loads(read(logs / "inputs.json") or "{}")
    targets = next(iter(inputs.get("builds", {}).values()), {}).get("targets", {})
    sums = read(logs / "SHA256SUMS")

    green = (args.build_exit == 0 and args.ctest_exit == 0 and args.inputs_exit == 0 and total > 0 and failed == 0
             and not blocks and bool(targets))
    record = {
        "repo": args.repo,
        "commit": args.commit,
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": args.host,
        "sanitizer": args.sanitizer,
        "sanitizer_options": args.options,
        "compiler": compiler[0] if compiler else None,
        "cmake_args": args.cmake_args,
        "green": green,
        "build_exit": args.build_exit,
        "ctest_exit": args.ctest_exit,
        "tests_total": total,
        "tests_failed": failed,
        "sanitizer_reports": len(blocks),
        "report_blocks": blocks[:20],
        "seconds": args.seconds,
        "inputs_scope": inputs.get("scope"),
        "inputs_hash": {t: v.get("inputs_hash") for t, v in targets.items()},
        "inputs_files": {t: v.get("files") for t, v in targets.items()},
        "prefix_hashes": {t: {p: h.get("hash") for p, h in v.get("prefix_hashes", {}).items()} for t, v in targets.items()},
        "logs": str(logs),
        "logs_sha256": sums.splitlines(),
        "logs_archive": args.logs_archive,
        "logs_archive_sha256": args.logs_sha256,
        "note": args.note,
        "googletest": "https://github.com/google/googletest.git b514bdc898e2951020cbdca1304b75f5950d1f59 (v1.15.2), "
                      "RegexMatcher's external/CMakeLists.txt, unless cmake_args names a local copy",
    }
    Path(args.record).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"{args.record}: {'green' if green else 'RED'} ({total} tests, {failed} failed, {len(blocks)} reports)")
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
