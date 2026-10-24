#!/usr/bin/env python3
"""Tests of round 3's D5 tools: t3/record.py (the record writer), t3/check_records.py (the gate) and
t3/source_hash.py, on synthetic work directories and records. Untimed.

    python t3/test_records.py          (or: python -m pytest t3/test_records.py)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_records  # noqa: E402
import record  # noqa: E402
import source_hash  # noqa: E402

ARMS = ["v2", "null", "crow"]
TARGETS = {"mserver": "a" * 64, "mserver_arms": "b" * 64, "p2v2_c": "c" * 64, "arm_crow": "d" * 64}
GO_HASH, RUST_HASH = "e" * 64, "f" * 64
GO_TC = {"go": "go version go1.27.3 linux/amd64", "GOAMD64": "v3"}
RUST_TC = {"rustc": "rustc 1.99.0 (b940084d7 2026-09-28)"}
LAPTOP_CPU = "AMD Ryzen 7 5800H with Radeon Graphics"


def check_records_host(tag: str) -> str:
    import labsteps
    return labsteps.LAPTOP[tag]["host"]
COMPILER = "Clang 22.1.8"


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def inputs_json(targets: dict) -> str:
    return json.dumps({"builds": {"p2r3": {"targets": {t: {"inputs_hash": h, "files": 3} for t, h in targets.items()},
                                           "config": {"CMAKE_BUILD_TYPE": "Release"},
                                           "third_party": {"fetched": {"crow": {"url": "u", "url_hash": "h"}}}}}})


def work_dir(root: Path, programs: dict) -> Path:
    """A green ASan work directory of t3/sanitize.py, with PROGRAMS {"go": ..., "rust": ...} built."""
    w = root / "work"
    write(w / "build.log", f"-- The CXX compiler identification is {COMPILER}\n")
    write(w / "ctest.log", "100% tests passed out of 9\n")
    write(w / "build.inputs.json", inputs_json(TARGETS))
    write(w / "build.v2-include.json", json.dumps({"builds": {"p2r3": {"targets": {
        "mserver_arms": {"prefix_hashes": {"regexmatcher/include/": {"hash": "1" * 64, "files": 40}}}}}}}))
    info = {}
    if "go" in programs:
        info["go"] = {"binary": "progs/mserver-go", "sanitizer": programs["go"],
                      "source": {"inputs_hash": GO_HASH, "files": 14}}
    if "rust" in programs:
        info["rust"] = {"binary": "progs/rust/mserver-rs", "sanitizer": programs["rust"],
                        "source": {"inputs_hash": RUST_HASH, "files": 12}}
    write(w / "progs" / "build-info.json", json.dumps(info))
    steps = [{"step": s, "exit": 0, "detail": ""} for s in record.STEPS]
    steps[record.STEPS.index("suite")]["mserver_arms"] = ARMS
    write(w / "steps.jsonl", "".join(json.dumps(s) + "\n" for s in steps))
    suite, load = [], [{"type": "session"}]
    want = [("mserver", a) for a in ARMS]
    if "go" in programs:
        want += [("mserver-go", a) for a in record.GO_ARMS]
    if "rust" in programs:
        want += [("mserver-rs", a) for a in record.RUST_ARMS]
    for prog, arm in want:
        suite.append({"program": prog, "router": arm, "ok": True})
        load.append({"type": "window", "program": prog, "arm": arm, "status": "valid"})
    write(w / "suite.jsonl", "".join(json.dumps(r) + "\n" for r in suite))
    write(w / "load.jsonl", "".join(json.dumps(r) + "\n" for r in load))
    write(w / "suite-logs" / "mserver-v2.log", "== mserver --port 1\nmserver: ready\n")
    return w


def run_record(w: Path, out: Path, sanitizer: str = "asan", host: str = "L", seconds: int = 10) -> tuple[int, dict]:
    pins = HERE.parent / "bench" / "cmake" / "pins.cmake"
    argv = ["record.py", "--work", str(w), "--record", str(out), "--repo", "r", "--commit", "c" * 40,
            "--repo-head", "c" * 40, "--sanitizer", sanitizer, "--host-tag", host, "--host", "h", "--cmake-args", "x",
            "--options", "y", "--seconds", str(seconds), "--regexmatcher-commit", "d" * 40, "--pins", str(pins),
            "--pins", str(HERE.parent / "server" / "cmake" / "pins-round3.cmake"),
            "--logs-archive", "x.tar.gz", "--logs-sha256", "0" * 64]
    old = sys.argv
    sys.argv = argv
    try:
        rc = record.main()
    finally:
        sys.argv = old
    return rc, json.loads(out.read_text(encoding="utf-8"))


class RecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_green_asan_record_carries_program_hashes(self) -> None:
        w = work_dir(self.root, {"go": "asan", "rust": "asan"})
        rc, r = run_record(w, self.root / "rec.json")
        self.assertEqual(rc, 0, [p for p in r["presets"] if p["status"] != "green"])
        self.assertTrue(r["green"])
        self.assertEqual(r["inputs_hash"]["mserver-go"], GO_HASH)
        self.assertEqual(r["inputs_hash"]["mserver-rs"], RUST_HASH)
        self.assertFalse(r["desktop_development"])
        self.assertEqual(r["coverage_gaps"], {})

    def test_a_report_in_a_server_log_makes_it_red(self) -> None:
        w = work_dir(self.root, {"go": "asan", "rust": "asan"})
        write(w / "load.work" / "000003.server.log", "==1==ERROR: AddressSanitizer: heap-use-after-free\n")
        rc, r = run_record(w, self.root / "rec.json")
        self.assertEqual(rc, 1)
        self.assertFalse(r["green"])
        self.assertEqual(r["sanitizer_reports"], 1)
        self.assertIn("load.work/000003.server.log", r["report_blocks"][0])

    def test_a_go_race_report_makes_it_red(self) -> None:
        w = work_dir(self.root, {"go": "race"})
        write(w / "suite-logs" / "mserver-go-gin.log", "WARNING: DATA RACE\nRead at 0x00c000\n")
        rc, r = run_record(w, self.root / "rec.json", sanitizer="tsan")
        self.assertEqual(rc, 1)
        self.assertEqual(r["sanitizer_reports"], 1)

    def test_build_trees_are_not_scanned(self) -> None:
        w = work_dir(self.root, {"go": "asan", "rust": "asan"})
        write(w / "build" / "deps" / "x.log", "SUMMARY: AddressSanitizer: in a fetched project's own test log\n")
        rc, r = run_record(w, self.root / "rec.json")
        self.assertEqual(rc, 0)

    def test_tsan_on_l_needs_go_only_and_msan_neither(self) -> None:
        w = work_dir(self.root, {"go": "race"})
        rc, r = run_record(w, self.root / "rec.json", sanitizer="tsan")
        self.assertEqual(rc, 0, [p for p in r["presets"] if p["status"] != "green"])
        self.assertIn("mserver-rs", r["coverage_gaps"])
        self.assertNotIn("mserver-rs", r["inputs_hash"])
        w2 = work_dir(self.root / "m", {})
        rc, r = run_record(w2, self.root / "rec2.json", sanitizer="msan")
        self.assertEqual(rc, 0, [p for p in r["presets"] if p["status"] != "green"])
        self.assertEqual(sorted(r["coverage_gaps"]), ["mserver-go", "mserver-rs"])

    def test_a_missing_arm_or_step_makes_it_red(self) -> None:
        w = work_dir(self.root, {"go": "asan", "rust": "asan"})
        rows = [r for r in record.jsonl(w / "suite.jsonl") if r["router"] != "crow"]
        write(w / "suite.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
        rc, r = run_record(w, self.root / "rec.json")
        self.assertEqual(rc, 1)
        self.assertIn("suite/mserver/crow", [p["preset"] for p in r["presets"] if p["status"] == "red"])
        w2 = work_dir(self.root / "b", {"go": "asan", "rust": "asan"})
        steps = [s for s in record.jsonl(w2 / "steps.jsonl") if s["step"] != "sets"]
        write(w2 / "steps.jsonl", "".join(json.dumps(s) + "\n" for s in steps))
        rc, r = run_record(w2, self.root / "rec2.json")
        self.assertEqual(rc, 1)

    def test_a_program_built_without_its_sanitizer_is_red(self) -> None:
        w = work_dir(self.root, {"go": "none", "rust": "asan"})
        rc, r = run_record(w, self.root / "rec.json")
        self.assertEqual(rc, 1)
        self.assertIn("programs/mserver-go", [p["preset"] for p in r["presets"] if p["status"] == "red"])

    def test_a_record_without_kept_logs_is_red(self) -> None:
        w = work_dir(self.root, {"go": "asan", "rust": "asan"})
        old = sys.argv
        argv = ["record.py", "--work", str(w), "--record", str(self.root / "r.json"), "--repo", "r", "--commit", "c",
                "--repo-head", "c", "--sanitizer", "asan", "--host-tag", "L", "--host", "h", "--cmake-args", "x",
                "--options", "y", "--seconds", "10", "--regexmatcher-commit", "d",
                "--pins", str(HERE.parent / "bench" / "cmake" / "pins.cmake")]
        sys.argv = argv
        try:
            rc = record.main()
        finally:
            sys.argv = old
        r = json.loads((self.root / "r.json").read_text(encoding="utf-8"))
        self.assertEqual(rc, 1)
        self.assertIn("logs", [p["preset"] for p in r["presets"] if p["status"] == "red"])

    def test_a_desktop_run_says_so(self) -> None:
        w = work_dir(self.root, {"go": "asan", "rust": "asan"})
        _, r = run_record(w, self.root / "rec.json", seconds=-1)
        self.assertTrue(r["desktop_development"])


def measured(root: Path, host: str = "L") -> Path:
    out = root / "measured"
    write(out / "build.inputs.json", inputs_json(TARGETS))
    write(out / "build.log", f"-- The CXX compiler identification is {COMPILER}\n")
    write(out / "build-info.json", json.dumps({"go": {"sanitizer": "none", "source": {"inputs_hash": GO_HASH}, **GO_TC},
                                               "rust": {"sanitizer": "none", "source": {"inputs_hash": RUST_HASH}, **RUST_TC}}))
    return out


def good_record(san: str, host: str = "L", **over) -> dict:
    pins = {p: check_records.sha256_lf(check_records.ROOT / p) for p in check_records.PINS}
    hashes = dict(TARGETS)
    gaps = (json.loads((HERE / "coverage.json").read_text(encoding="utf-8")).get(host) or {})
    for prog, h in (("mserver-go", GO_HASH), ("mserver-rs", RUST_HASH)):
        if san not in (gaps.get(prog) or {}).get("not_covered_by", []):
            hashes[prog] = h
    tag = over.pop("host_tag", host)
    r = {"tool": "p2r3", "sanitizer": san, "host_tag": tag, "host": check_records_host(tag), "cpu": LAPTOP_CPU,
         "programs": {"mserver-go": dict(GO_TC), "mserver-rs": dict(RUST_TC)}, "green": True, "compiler": COMPILER,
         "config": {"CMAKE_BUILD_TYPE": "Release"}, "pins_sha256": pins, "inputs_hash": hashes,
         "third_party": {"fetched": {"crow": {"url": "u", "url_hash": "h"}}}, "desktop_development": False}
    r.update(over)
    return r


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.records = self.root / "records"
        self.records.mkdir()
        self.coverage = json.loads((HERE / "coverage.json").read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def put(self, name: str, r: dict) -> None:
        write(self.records / name, json.dumps(r))

    def run_gate(self, host: str = "L") -> dict:
        return check_records.gate(check_records.build_of(measured(self.root, host)), host, self.records, self.coverage)

    def test_green_with_three_records_and_the_declared_gaps(self) -> None:
        for san in ("asan", "tsan", "msan"):
            self.put(f"p2r3-x-L-{san}.json", good_record(san))
        g = self.run_gate()
        self.assertTrue(g["green"], g["missing"])
        self.assertEqual(g["gaps"]["mserver-rs"]["not_covered_by"], ["tsan", "msan"])
        self.assertEqual(g["gaps"]["mserver-go"]["not_covered_by"], ["msan"])

    def test_a_missing_sanitizer_is_not_green(self) -> None:
        for san in ("asan", "msan"):
            self.put(f"p2r3-x-L-{san}.json", good_record(san))
        g = self.run_gate()
        self.assertFalse(g["green"])
        self.assertTrue(any(m.startswith("mserver (") and "tsan" in m for m in g["missing"]), g["missing"])

    def test_a_red_record_with_the_same_inputs_stops_the_gate(self) -> None:
        self.put("p2r3-x-L-asan.json", good_record("asan", green=False))
        with self.assertRaises(check_records.GateError):
            self.run_gate()

    def test_desktop_other_host_compiler_or_pins_are_left_out(self) -> None:
        self.put("p2r3-a-L-asan-desktop.json", good_record("asan", desktop_development=True))
        self.put("p2r3-b-W-asan.json", good_record("asan", host_tag="W"))
        self.put("p2r3-c-L-asan.json", good_record("asan", compiler="Clang 22.1.0"))
        self.put("p2r3-d-L-asan.json", good_record("asan", pins_sha256={"bench/cmake/pins.cmake": "0"}))
        g = self.run_gate()
        self.assertFalse(g["green"])
        self.assertEqual(len(g["left_out"]), 4)

    def test_a_changed_target_is_not_covered(self) -> None:
        for san in ("asan", "tsan", "msan"):
            r = good_record(san)
            r["inputs_hash"]["arm_crow"] = "9" * 64
            self.put(f"p2r3-x-L-{san}.json", r)
        g = self.run_gate()
        self.assertEqual(g["missing"], [f"arm_crow ({'d' * 12}): no green asan, tsan, msan record"])

    def test_windows_needs_asan_and_lets_go_go(self) -> None:
        self.put("p2r3-x-W-asan.json", good_record("asan", host="W"))
        g = self.run_gate("W")
        self.assertTrue(g["green"], g["missing"])
        self.assertIn("mserver-go", g["gaps"])

    def test_a_record_from_another_host_or_cpu_is_left_out(self) -> None:
        self.put("p2r3-a-L-asan.json", good_record("asan", host="L", **{}) | {"host": "01893c10e426"})
        self.put("p2r3-b-L-tsan.json", good_record("tsan") | {"cpu": "AMD Ryzen 5 3600 6-Core Processor"})
        g = self.run_gate()
        self.assertEqual(len(g["left_out"]), 2, g["left_out"])
        self.assertFalse(g["green"])

    def test_another_go_release_does_not_cover_the_go_program(self) -> None:
        for san in ("asan", "tsan", "msan"):
            r = good_record(san)
            r["programs"]["mserver-go"]["go"] = "go version go1.27.1 linux/amd64"
            self.put(f"p2r3-x-L-{san}.json", r)
        g = self.run_gate()
        self.assertFalse(g["green"])
        self.assertTrue(any(m.startswith("mserver-go (") for m in g["missing"]), g["missing"])
        self.assertNotIn("mserver-go", [m.split(" ")[0] for m in g["missing"] if not m.startswith("mserver-go")])

    def test_a_sanitized_measured_build_is_refused(self) -> None:
        out = measured(self.root)
        write(out / "build-info.json", json.dumps({"go": {"sanitizer": "asan", "source": {"inputs_hash": GO_HASH}}}))
        with self.assertRaises(check_records.GateError):
            check_records.build_of(out)


class LabstepsTests(unittest.TestCase):
    def test_keep_logs_packs_once_and_refuses_again(self) -> None:
        import labsteps
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "work" / "a.log", "one\n")
            write(root / "work" / "sub" / "b.log", "two\n")
            old = os.environ.get("RECORDS_LOGS")
            os.environ["RECORDS_LOGS"] = str(root / "logs")
            try:
                tar, sha = labsteps.keep_logs("p2r3-x-L-asan", [root / "work" / "a.log", root / "work" / "sub"])
                self.assertTrue(Path(tar).is_file())
                self.assertEqual(len(sha), 64)
                sums = (root / "logs" / "p2r3-x-L-asan" / "SHA256SUMS").read_text(encoding="utf-8")
                self.assertIn("./a.log", sums)
                self.assertIn("./sub/b.log", sums)
                with self.assertRaises(labsteps.StepError):
                    labsteps.keep_logs("p2r3-x-L-asan", [root / "work" / "a.log"])
            finally:
                if old is None:
                    os.environ.pop("RECORDS_LOGS", None)
                else:
                    os.environ["RECORDS_LOGS"] = old

    def test_arms_must_be_the_systems(self) -> None:
        import labsteps
        old = os.environ.pop("EXPECT_ARMS", None)
        try:
            want = labsteps.EXPECTED_ARMS[labsteps.host_tag()].split()
            labsteps.check_arms(list(reversed(want)))
            with self.assertRaises(labsteps.StepError):
                labsteps.check_arms([a for a in want if a != "pistache"])
        finally:
            if old is not None:
                os.environ["EXPECT_ARMS"] = old

    def test_the_laptop_is_told_by_host_and_cpu(self) -> None:
        import labsteps
        self.assertTrue(labsteps.on_laptop("W", "desktop-a1rhs5r", LAPTOP_CPU))
        self.assertFalse(labsteps.on_laptop("W", "ALEX-PC", LAPTOP_CPU))
        self.assertFalse(labsteps.on_laptop("L", "alex-laptop", "AMD Ryzen 5 3600 6-Core Processor"))

    def test_the_count_plan_parses_as_a_runner_plan(self) -> None:
        import labsteps
        import p2run
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            labsteps.load_plan(plan, Path("p2gen"), Path("sets"),
                               [("mserver", Path("mserver"), ["v2", "null"], None),
                                ("mserver-go", Path("mserver-go"), ["v2"], {"P2V2_DLL": "x"})], [1000], "test")
            parsed, _ = p2run.load_plan(plan)
            self.assertEqual([p.name for p in parsed.programs], ["mserver", "mserver-go"])


class SourceHashTests(unittest.TestCase):
    def test_line_endings_do_not_change_the_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            write(repo / "server" / "go" / "a.go", "package main\n")
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            h1 = source_hash.folder_hash(repo, "server/go")
            (repo / "server" / "go" / "a.go").write_bytes(b"package main\r\n")
            h2 = source_hash.folder_hash(repo, "server/go")
            self.assertEqual(h1, h2)
            write(repo / "server" / "go" / "a.go", "package other\n")
            self.assertNotEqual(source_hash.folder_hash(repo, "server/go")["inputs_hash"], h1["inputs_hash"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
