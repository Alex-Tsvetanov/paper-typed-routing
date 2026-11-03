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
4. bench/sanitizer_record.py's presets of the adversarial tool: none without the tool; three green
   ones from passing outputs; red ones when its outputs are missing, a cell crashed, ran out of time or
   failed a check, a cell is missing, fewer than the plan's 44 cells ran, or the self-test reports a
   failure or covers fewer than its 66 queries on 22 tables.
5. Its preset of the ablation copies' answers test (test_ablation): none without the ablation arms;
   green from a passing output; red when the output is missing, reports a failure or the test exited
   other than 0.
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


def adversarial_presets(tmp: Path) -> None:
    m = module(HERE / "sanitizer_record.py")
    good = {"cell": "two-k1-miss", "status": "ok", "checks_ok": True, "agrees": True}
    all44 = [{**good, "cell": f"c{i}"} for i in range(44)]

    def out(cells: list[dict], planned: int = 44, selftest: str = "self-test: 66 queries on 22 tables, 0 failing",
            exits: str = "test_exit=0 selftest_exit=0") -> Path:
        d = tmp / f"adv-{next(runs)}"
        d.mkdir()
        (d / "adversarial-exit.txt").write_text(f"{exits} cells={planned} failed_cells=0\n", encoding="utf-8")
        (d / "adversarial-test.txt").write_text("test_adversarial: ok (0 failing)\n", encoding="utf-8")
        (d / "adversarial-selftest.txt").write_text(selftest + "\n", encoding="utf-8")
        (d / "adversarial.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cells), encoding="utf-8")
        return d

    def green(d: Path) -> list[bool]:
        return [p["status"] == "green" for p in m.tool_presets(d, True, "Clang 22.1.8")]

    expect("sanitizer_record.py: no tool, no preset", m.tool_presets(out(all44), False, "c") == [])
    expect("sanitizer_record.py: the tool's passing outputs make three green presets", green(out(all44)) == [True] * 3)
    expect("sanitizer_record.py: missing outputs are red", green(tmp / "nowhere") == [False] * 3)
    crashed = {"cell": "x", "status": "crash", "exit": 139}
    expect("sanitizer_record.py: a crashed cell is red", green(out(all44[:43] + [crashed]))[2] is False)
    timed_out = {"cell": "x", "status": "timeout", "exit": 124}
    expect("sanitizer_record.py: a cell that ran out of time is red", green(out(all44[:43] + [timed_out]))[2] is False)
    expect("sanitizer_record.py: a cell that fails a check is red",
           green(out(all44[:43] + [{**good, "checks_ok": False}]))[2] is False)
    expect("sanitizer_record.py: a missing cell is red", green(out(all44[:43]))[2] is False)
    expect("sanitizer_record.py: fewer cells than the plan's 44 are red, even all run",
           green(out(all44[:43], planned=43))[2] is False)
    expect("sanitizer_record.py: a self-test with a failure is red",
           green(out(all44, selftest="self-test: 66 queries on 22 tables, 1 failing"))[1] is False)
    expect("sanitizer_record.py: a self-test over fewer than 66 queries is red",
           green(out(all44, selftest="self-test: 63 queries on 21 tables, 0 failing"))[1] is False)
    expect("sanitizer_record.py: a unit test that exited 1 is red",
           green(out(all44, exits="test_exit=1 selftest_exit=0"))[0] is False)


def review_presets(tmp: Path) -> None:
    m = module(HERE / "sanitizer_record.py")

    def out(text: str | None, rc: int = 0) -> Path:
        d = tmp / f"review-{next(runs)}"
        d.mkdir()
        if text is not None:
            (d / "ablation-test.txt").write_text(text + "\n", encoding="utf-8")
            (d / "ablation-exit.txt").write_text(f"test_exit={rc}\n", encoding="utf-8")
        return d

    def green(d: Path, has: bool = True) -> list[bool]:
        return [p["status"] == "green" for p in m.review_presets(d, has, "Clang 22.1.8")]

    passing = "test_ablation: ok (112 tables, 2293760 lookups compared, 0 failing)"
    expect("sanitizer_record.py: no ablation arms, no review preset", green(out(passing), has=False) == [])
    expect("sanitizer_record.py: a passing answers test is green", green(out(passing)) == [True])
    expect("sanitizer_record.py: a missing answers test is red", green(out(None)) == [False])
    expect("sanitizer_record.py: an answers test with a failure is red",
           green(out("test_ablation: FAILED (112 tables, 2293760 lookups compared, 3 failing)", rc=1)) == [False])
    expect("sanitizer_record.py: an answers test that exited 124 is red", green(out(passing, rc=124)) == [False])
    for what, text in (("fewer tables", "test_ablation: ok (111 tables, 2293760 lookups compared, 0 failing)"),
                       ("more tables", "test_ablation: ok (113 tables, 2293760 lookups compared, 0 failing)"),
                       ("one lookup fewer", "test_ablation: ok (112 tables, 2293759 lookups compared, 0 failing)"),
                       ("one lookup more", "test_ablation: ok (112 tables, 2293761 lookups compared, 0 failing)"),
                       ("no lookups", "test_ablation: ok (112 tables, 0 lookups compared, 0 failing)"),
                       ("no tables", "test_ablation: ok (0 tables, 0 lookups compared, 0 failing)")):
        expect(f"sanitizer_record.py: an answers test with {what} is red", green(out(text)) == [False])


def main() -> int:
    parsers()
    with tempfile.TemporaryDirectory() as t:
        end_to_end(Path(t))
        adversarial_presets(Path(t))
        review_presets(Path(t))
    print(f"{failures} failed" if failures else "all checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
