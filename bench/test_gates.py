#!/usr/bin/env python3
"""Tests of the round-2 records gates (bench/check_records.py for rbench, t1/check_h6_records.py for
the server, both on bench/gate_lib.py) over synthetic records and inputs files: a covered build
passes; a missing sanitizer, a red record with the same inputs, another compiler, a record not
made on L, RegexMatcher headers without green records, and a red RegexMatcher record each stop
the gate; a gap coverage.json declares is allowed. The pin rule: a build whose bench/cmake/pins.cmake
has one pin changed is refused by records made with the file as it is; so is a build whose records
fetched an archive with another hash, or do not record their pins.

    python3 bench/test_gates.py      (exit 0 when every check passes)
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gate_lib import file_sha256  # noqa: E402

PINS = HERE / "cmake" / "pins.cmake"
PINS_SHA = file_sha256(PINS)
FETCHED = {"rb_crow_src": {"url": "https://codeload.github.com/CrowCpp/Crow/tar.gz/x", "url_hash": "SHA256=aa"},
           "nanobench": {"url": "https://codeload.github.com/martinus/nanobench/tar.gz/y", "url_hash": "SHA256=bb"}}
CHECK = HERE / "check_records.py"
CHECK_H6 = HERE.parent / "t1" / "check_h6_records.py"
COMPILER = "Clang 22.1.8"
PREFIX_HASH = "ab" * 32
failures = 0


def expect(name: str, ok: bool) -> None:
    global failures
    print(("ok: " if ok else "FAIL: ") + name)
    failures += not ok


def write(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj), encoding="utf-8")


def rbench_inputs(d: Path, targets: dict) -> Path:
    write(d / "b.inputs.json", {"builds": {"rbench": {"targets": {t: {"inputs_hash": h, "files": 1} for t, h in targets.items()},
                                                      "build_config": {}, "third_party": {"fetched": FETCHED}}}})
    write(d / "b.v2-include.json", {"builds": {"rbench": {"targets": {
        t: {"prefix_hashes": {"regexmatcher/include/": {"hash": PREFIX_HASH, "files": 10}}}
        for t in targets if t in ("arm_regexmatcher_v2", "arm_regexmatcher_v2_ct")}}}})
    return d / "b.inputs.json"


def h6_inputs(d: Path, targets: dict) -> Path:
    write(d / "h.inputs.json", {"builds": {"h6": {"targets": {t: {"inputs_hash": h, "files": 1} for t, h in targets.items()},
                                                  "config": {}, "third_party": {"fetched": FETCHED}}}})
    write(d / "h.v2-include.json", {"builds": {"h6": {"targets": {
        "mserver_arms": {"prefix_hashes": {"regexmatcher/include/": {"hash": PREFIX_HASH, "files": 10}}}}}}})
    return d / "h.inputs.json"


def record(recs: Path, name: str, san: str, hashes: dict, green: bool = True, compiler: str = COMPILER,
           config_key: str = "build_config", pins: str | None = PINS_SHA, fetched: dict | None = None) -> None:
    r = {"sanitizer": san, "green": green, "compiler": compiler, "inputs_hash": hashes, config_key: {},
         "third_party": {"fetched": FETCHED if fetched is None else fetched}}
    if pins is not None:
        r["pins_sha256"] = pins
    write(recs / name, r)


def rm_record(recs: Path, name: str, san: str, green: bool = True, prefix: str = PREFIX_HASH) -> None:
    write(recs / name, {"sanitizer": san, "green": green, "compiler": COMPILER,
                        "prefix_hashes": {"route_tests": {"regexmatcher/include/": prefix}}})


def run(script: Path, inputs: Path, recs: Path, coverage: Path | None = None, pins: Path = PINS) -> bool:
    cmd = [sys.executable, str(script), "--records", str(recs), "--inputs", str(inputs), "--compiler", COMPILER,
           "--pins", str(pins)]
    if coverage:
        cmd += ["--coverage", str(coverage)]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def rbench_cases(tmp: Path) -> None:
    targets = {"rbench": "r1", "arm_null": "n1", "arm_regexmatcher_v2": "v2", "arm_chi": "c1"}
    cov = tmp / "coverage.json"
    write(cov, {"arm_chi": {"not_covered_by": ["msan"], "reason": "Go"}})

    def fresh(name: str) -> tuple[Path, Path]:
        d = tmp / name
        d.mkdir()
        recs = d / "records"
        recs.mkdir()
        return rbench_inputs(d, targets), recs

    def full(recs: Path, skip: str = "") -> None:
        for s in ("asan", "tsan", "msan"):
            if s != skip:
                hashes = dict(targets) if s != "msan" else {t: h for t, h in targets.items() if t != "arm_chi"}
                record(recs, f"rbench-x-L-{s}.json", s, hashes)
            rm_record(recs, f"regexmatcher-y-L-{s}.json", s)

    inputs, recs = fresh("pass")
    full(recs)
    expect("rbench: a covered build passes (with arm_chi's declared MSan gap)", run(CHECK, inputs, recs, cov))
    inputs, recs = fresh("undeclared")
    full(recs)
    write(tmp / "none.json", {})
    expect("rbench: an MSan gap coverage.json does not declare stops the gate", not run(CHECK, inputs, recs, tmp / "none.json"))
    inputs, recs = fresh("missing")
    full(recs, skip="tsan")
    expect("rbench: a missing TSan record stops the gate", not run(CHECK, inputs, recs, cov))
    inputs, recs = fresh("red")
    full(recs)
    record(recs, "rbench-z-L-asan.json", "asan", {"arm_null": "n1"}, green=False)
    expect("rbench: a red record with the same inputs stops the gate", not run(CHECK, inputs, recs, cov))
    inputs, recs = fresh("compiler")
    full(recs)
    for s in ("asan", "tsan", "msan"):
        record(recs, f"rbench-x-L-{s}.json", s, targets, compiler="Clang 18.1.3")
    expect("rbench: records made with another compiler do not count", not run(CHECK, inputs, recs, cov))
    inputs, recs = fresh("host")
    full(recs)
    (recs / "rbench-x-L-asan.json").rename(recs / "rbench-x-W-asan.json")
    expect("rbench: a record not made on L does not count", not run(CHECK, inputs, recs, cov))
    inputs, recs = fresh("rm-missing")
    full(recs)
    (recs / "regexmatcher-y-L-msan.json").unlink()
    expect("rbench: RegexMatcher headers without a green MSan record stop the gate", not run(CHECK, inputs, recs, cov))
    inputs, recs = fresh("rm-red")
    full(recs)
    rm_record(recs, "regexmatcher-q-L-tsan.json", "tsan", green=False)
    expect("rbench: a red RegexMatcher record with the same headers stops the gate", not run(CHECK, inputs, recs, cov))
    inputs, recs = fresh("rm-other")
    full(recs)
    for s in ("asan", "tsan", "msan"):
        rm_record(recs, f"regexmatcher-y-L-{s}.json", s, prefix="cd" * 32)
    expect("rbench: RegexMatcher records of other headers do not count", not run(CHECK, inputs, recs, cov))

    # The pin rule, with the real pins.cmake and a copy of it with one pin changed.
    changed = tmp / "pins-changed.cmake"
    text = PINS.read_text(encoding="utf-8")
    pin = "set(RB_CROW_SHA256 "
    start = text.index(pin) + len(pin)
    flipped = "0" if text[start] != "0" else "1"
    changed.write_text(text[:start] + flipped + text[start + 1:], encoding="utf-8")
    expect("pins: the changed copy differs from pins.cmake", file_sha256(changed) != PINS_SHA)
    inputs, recs = fresh("pins-same")
    full(recs)
    expect("rbench: records made with the build's pins.cmake pass", run(CHECK, inputs, recs, cov))
    expect("rbench: a build with one pin changed is refused by records made with the file as it is",
           not run(CHECK, inputs, recs, cov, pins=changed))
    inputs, recs = fresh("pins-fetched")
    full(recs)
    other = {k: dict(v) for k, v in FETCHED.items()}
    other["rb_crow_src"]["url_hash"] = "SHA256=cc"
    record(recs, "rbench-x-L-tsan.json", "tsan", targets, fetched=other)
    expect("rbench: a record that fetched an archive with another hash does not count", not run(CHECK, inputs, recs, cov))
    inputs, recs = fresh("pins-none")
    full(recs)
    record(recs, "rbench-x-L-asan.json", "asan", targets, pins=None)
    expect("rbench: a record without its pins does not count", not run(CHECK, inputs, recs, cov))


def h6_cases(tmp: Path) -> None:
    targets = {"mserver": "m1", "h6_targets": "t1"}

    def fresh(name: str) -> tuple[Path, Path]:
        d = tmp / ("h6-" + name)
        d.mkdir()
        recs = d / "records"
        recs.mkdir()
        return h6_inputs(d, targets), recs

    def full(recs: Path, skip: str = "") -> None:
        for s in ("asan", "tsan", "msan"):
            if s != skip:
                record(recs, f"mserver-x-L-{s}.json", s, targets, config_key="config")
            rm_record(recs, f"regexmatcher-y-L-{s}.json", s)

    inputs, recs = fresh("pass")
    full(recs)
    expect("server: a covered build passes", run(CHECK_H6, inputs, recs))
    inputs, recs = fresh("missing")
    full(recs, skip="msan")
    expect("server: a missing MSan record stops the gate (no gap is declared)", not run(CHECK_H6, inputs, recs))
    inputs, recs = fresh("red")
    full(recs)
    record(recs, "mserver-z-L-tsan.json", "tsan", {"mserver": "m1"}, green=False, config_key="config")
    expect("server: a red record with the same inputs stops the gate", not run(CHECK_H6, inputs, recs))
    inputs, recs = fresh("rm")
    full(recs)
    (recs / "regexmatcher-y-L-asan.json").unlink()
    expect("server: RegexMatcher headers without a green ASan record stop the gate", not run(CHECK_H6, inputs, recs))
    changed = tmp / "h6-pins-changed.cmake"
    text = PINS.read_text(encoding="utf-8")
    pin = "set(RB_REGEXMATCHER_SHA256_V1 "
    start = text.index(pin) + len(pin)
    changed.write_text(text[:start] + ("0" if text[start] != "0" else "1") + text[start + 1:], encoding="utf-8")
    inputs, recs = fresh("pins")
    full(recs)
    expect("server: records made with the build's pins.cmake pass", run(CHECK_H6, inputs, recs))
    expect("server: a build with RegexMatcher v1's pin changed is refused", not run(CHECK_H6, inputs, recs, pins=changed))


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        rbench_cases(tmp)
        h6_cases(tmp)
    print(f"{failures} failed" if failures else "all checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
