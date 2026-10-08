#!/usr/bin/env python3
"""Tests of the record writers that read a CTest summary: bench/regexmatcher_record.py (RegexMatcher
v2's suite) and t1/h6_record.py (the minimal server's suite).

    python bench/test_record_writers.py      (exit 0 when every check passes)

CTest writes its summary as "P% tests passed, F tests failed out of T" up to version 3, and from
version 4 on as "100% tests passed out of T" when no test failed (CTest 4.4.3 on L, 2026-09-30;
the first L record of RegexMatcher went red on it, lab journal). For each writer:
1. its parser reads both forms (failed 0 when the clause is absent) and a summary with failures;
2. the writer run end to end on synthetic logs makes a green record from either passing form, and
   a red one from a summary with a failed test (even with CTest's exit code 0), and from a log
   without a summary;
3. the server's record carries the sha256 of the pins.cmake it was given (the gate's pin rule).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from gate_lib import file_sha256  # noqa: E402

OLD = "100% tests passed, 0 tests failed out of 87"
NEW = "100% tests passed out of 87"
FAILED = "95% tests passed, 4 tests failed out of 87"
failures = 0
runs = iter(range(1000))


def expect(name: str, ok: bool) -> None:
    global failures
    print(("ok: " if ok else "FAIL: ") + name)
    failures += not ok


def module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ctest_log(summary: str) -> str:
    return ("Test project /x/build\n  1/87 Test  #1: a ....   Passed    0.01 sec\n\n" + summary +
            "\n\nTotal Test time (real) =  28.22 sec\n")


def parsers() -> None:
    for path in (HERE / "regexmatcher_record.py", ROOT / "t1" / "h6_record.py"):
        m = module(path)
        name = path.name
        expect(f"{name}: CTest 3 form, none failed", m.ctest_summary(ctest_log(OLD)) == (87, 0))
        expect(f"{name}: CTest 4 form, none failed", m.ctest_summary(ctest_log(NEW)) == (87, 0))
        expect(f"{name}: a summary with failures", m.ctest_summary(ctest_log(FAILED)) == (87, 4))
        expect(f"{name}: no summary", m.ctest_summary("no tests were found\n") is None)
        expect(f"{name}: the last summary counts", m.ctest_summary(ctest_log(NEW) + ctest_log(FAILED)) == (87, 4))


def regexmatcher_record(tmp: Path, summary: str, ctest_exit: int = 0) -> dict:
    logs = tmp / f"rm-{next(runs)}"
    logs.mkdir()
    (logs / "build.log").write_text("-- The CXX compiler identification is Clang 22.1.8\n", encoding="utf-8")
    (logs / "ctest.log").write_text(ctest_log(summary) if summary else "no summary\n", encoding="utf-8")
    (logs / "inputs.json").write_text(json.dumps({"scope": "s", "builds": {"rm": {"targets": {
        "route_tests": {"inputs_hash": "h", "files": 1, "prefix_hashes": {"regexmatcher/include/": {"hash": "p"}}}}}}}),
        encoding="utf-8")
    rec = logs / "record.json"
    cmd = [sys.executable, str(HERE / "regexmatcher_record.py"), "--record", str(rec), "--logs", str(logs),
           "--repo", "r", "--commit", "c", "--sanitizer", "asan", "--options", "o", "--cmake-args", "a", "--host", "h",
           "--build-exit", "0", "--ctest-exit", str(ctest_exit), "--inputs-exit", "0", "--seconds", "1"]
    subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(rec.read_text(encoding="utf-8"))


def h6_record(tmp: Path, summary: str, ctest_exit: int = 0) -> dict:
    work = tmp / f"h6-{next(runs)}"
    (work / "build").mkdir(parents=True)
    (work / "build.log").write_text("-- The CXX compiler identification is Clang 22.1.8\n", encoding="utf-8")
    (work / "ctest.log").write_text(ctest_log(summary) if summary else "no summary\n", encoding="utf-8")
    (work / "build.inputs.json").write_text(json.dumps({"builds": {"h6": {"targets": {
        "mserver": {"inputs_hash": "m", "files": 1}}, "config": {}, "third_party": {"fetched": {}}}}}), encoding="utf-8")
    (work / "build.v2-include.json").write_text(json.dumps({"builds": {"h6": {"targets": {
        "mserver_arms": {"prefix_hashes": {"regexmatcher/include/": {"hash": "p"}}}}}}}), encoding="utf-8")
    steps = [{"cell": f"c{i}", "arm": a, "targets_exit": 0, "exercise_exit": 0, "server_exit": "0",
              "exercise": {"requests": 10, "failures": 0}} for i in range(9) for a in ("v2", "v1", "null")]
    (work / "steps.jsonl").write_text("".join(json.dumps(s) + "\n" for s in steps), encoding="utf-8")
    rec = work / "record.json"
    cmd = [sys.executable, str(ROOT / "t1" / "h6_record.py"), "--build", str(work / "build"), "--work", str(work),
           "--record", str(rec), "--repo", "r", "--commit", "c", "--repo-head", "c", "--regexmatcher-commit", "c",
           "--sanitizer", "asan", "--cmake-args", "a", "--options", "o", "--host", "h", "--build-exit", "0",
           "--ctest-exit", str(ctest_exit), "--seconds", "1", "--pins", str(HERE / "cmake" / "pins.cmake")]
    subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(rec.read_text(encoding="utf-8"))


def end_to_end(tmp: Path) -> None:
    for name, write in (("regexmatcher_record.py", regexmatcher_record), ("h6_record.py", h6_record)):
        expect(f"{name}: green from the CTest 3 form", write(tmp, OLD)["green"] is True)
        expect(f"{name}: green from the CTest 4 form", write(tmp, NEW)["green"] is True)
        expect(f"{name}: red from a summary with a failed test, CTest exit 0", write(tmp, FAILED)["green"] is False)
        expect(f"{name}: red from a summary with a failed test, CTest exit 8", write(tmp, FAILED, 8)["green"] is False)
        expect(f"{name}: red without a summary", write(tmp, "")["green"] is False)
    rec = h6_record(tmp, NEW)
    expect("h6_record.py: the record carries the pins' sha256",
           rec.get("pins_sha256") == file_sha256(HERE / "cmake" / "pins.cmake"))


def main() -> int:
    parsers()
    with tempfile.TemporaryDirectory() as t:
        end_to_end(Path(t))
    print(f"{failures} failed" if failures else "all checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
