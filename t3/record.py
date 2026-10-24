#!/usr/bin/env python3
"""Write one D5 sanitizer record of round 3 from the work directory of t3/sanitize.py (either
system of the laptop).

The record has the shape of round 2's records (t1/h6_record.py, bench/sanitizer_record.py): repo,
commit, date, host, green, compiler, what the build compiled, presets, the reports. What it covers:
  - the C++ targets of the paper's root project built under the sanitizer: the server mserver with
    every router arm the build has (mserver, mserver_arms, mserver_http1, mserver_loop,
    mserver_external, mserver_v1 on Linux, one arm_<name> object library per external arm), v2's C
    interface (p2v2_c, p2v2), the load generator (p2gen, p2gen_core, p2gen_net) and the request-set
    generator (e2e_requests): inputs_hash per target from the Papers repo's lab/bin/inputs_hash.py
    in project mode, RegexMatcher v2 as the dependency root "regexmatcher", with the hash of
    mserver_arms's and p2v2_c's inputs under regexmatcher/include/ (prefix_hashes);
  - the Go and Rust programs where their toolchains can instrument them: inputs_hash per program
    from t3/source_hash.py (keys mserver-go and mserver-rs), and how each was built;
  - the steps the script ran, one preset each, every one of which must exit 0: build, ctest (the
    whole CTest suite), inputs, programs, sets (e2e_requests under the sanitizer, its cells
    checked against the committed manifest), suite (t3/run_checks.py over every program built,
    every arm, every size, untimed), load (t3/p2run.py in count mode: p2gen under the sanitizer
    against every arm of every program, untimed).
Green means: every required step is there and exited 0; CTest ran tests and none failed; every
suite line passed and covered every arm of every program the record must cover; every load window
is valid; the inputs are recorded; and no log, standard error or server log under the work
directory holds a sanitizer report (the shared pattern below), nor, for Go, a race report. The
programs a record need not cover are the declared gaps of t3/coverage.json for its host and
sanitizer; the record copies them with their reasons.

    record.py --work DIR --record FILE --repo URL --commit SHA --repo-head SHA --sanitizer asan
              --host-tag L --host NAME --cmake-args TEXT --options TEXT --seconds N
              --regexmatcher-commit SHA --pins FILE [--pins FILE] [--coverage t3/coverage.json]
              [--logs-archive FILE --logs-sha256 SHA] [--note TEXT]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The first line of every sanitizer report and every SUMMARY line; the same text as the
# Papers repo's lab/bin/sanitize.sh, checked by its lab/bin/test_report_pattern.sh.
REPORT = re.compile(r"ERROR: (Address|Memory|Leak|Thread)Sanitizer|WARNING: (Memory|Thread)Sanitizer|"
                    r"SUMMARY: [A-Za-z]+Sanitizer|runtime error:")
# Go's race detector prints its own header, not ThreadSanitizer's.
GO_RACE = re.compile(r"WARNING: DATA RACE")
COMPILER_ID = re.compile(r"^-- The CXX compiler identification is (.+?)\s*$", re.MULTILINE)
CTEST_LINE = re.compile(r"(\d+)% tests passed(?:, (\d+) tests failed)? out of (\d+)")
STEPS = ("build", "ctest", "inputs", "programs", "sets", "suite", "load")
PROGRAMS = ("mserver-go", "mserver-rs")
GO_ARMS = ("v2", "httprouter", "gin", "nethttp", "chi", "null")
RUST_ARMS = ("v2", "matchit", "path-tree", "actix-router", "null")
SCANNED = (".log", ".err", ".out")
NOT_SCANNED_DIRS = {"build", "capi-plain", "progs", "gocache", "sets-check"}


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def jsonl(p: Path) -> list:
    return [json.loads(line) for line in read(p).splitlines() if line.strip()]


def sha256_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def ctest_summary(text: str):
    found = CTEST_LINE.findall(text)
    if not found:
        return None
    _, failed, total = found[-1]
    return int(total), int(failed) if failed else 0


def scanned_files(work: Path) -> list:
    out = []
    for f in sorted(work.rglob("*")):
        rel = f.relative_to(work)
        if f.is_file() and f.suffix in SCANNED and not (set(rel.parts[:-1]) & NOT_SCANNED_DIRS):
            out.append(f)
    return out


def report_blocks(work: Path) -> list:
    blocks = []
    for f in scanned_files(work):
        lines = read(f).splitlines()
        for i, line in enumerate(lines):
            if REPORT.search(line) or GO_RACE.search(line):
                blocks.append(f"{f.relative_to(work).as_posix()}:{i + 1}:\n" + "\n".join(lines[i:i + 30]))
    return blocks


def gaps_of(coverage: Path, host_tag: str, sanitizer: str) -> dict:
    data = json.loads(read(coverage)) if coverage.exists() else {}
    return {p: g["reason"] for p, g in (data.get(host_tag) or {}).items()
            if sanitizer in g.get("not_covered_by", [])}


def inputs_of(work: Path) -> dict:
    p = work / "build.inputs.json"
    if not p.exists():
        return {"inputs_error": "no build.inputs.json (the build or inputs step failed?)"}
    b = next(iter(json.loads(read(p))["builds"].values()))
    out = {"inputs_hash": {t: v["inputs_hash"] for t, v in b["targets"].items()},
           "inputs_files": {t: v["files"] for t, v in b["targets"].items()},
           "config": next((v for k, v in b.items() if k == "config" or k.endswith("_config")), None),
           "dep_roots": b.get("dep_roots"), "third_party": b.get("third_party")}
    v2 = work / "build.v2-include.json"
    if v2.exists():
        t = next(iter(json.loads(read(v2))["builds"].values()))["targets"]
        out["prefix_hashes"] = {n: {k: h["hash"] for k, h in v.get("prefix_hashes", {}).items()} for n, v in t.items()}
    return out


def programs_of(work: Path) -> dict:
    p = work / "progs" / "build-info.json"
    if not p.exists():
        return {}
    info = json.loads(read(p))
    out = {}
    for key, name in (("go", "mserver-go"), ("rust", "mserver-rs")):
        if key in info:
            out[name] = {k: v for k, v in info[key].items() if k != "cargo_config"}
    out["v2_library"] = info.get("v2_library")
    return out


def suite_presets(work: Path, mserver_arms: list, programs: list) -> list:
    covered: dict = {}
    for r in jsonl(work / "suite.jsonl"):
        prog = Path(r.get("program", "?")).stem
        covered.setdefault(prog, {}).setdefault(r.get("router"), []).append(bool(r.get("ok")))
    want = {"mserver": mserver_arms}
    for p in programs:
        want[p] = list(GO_ARMS if p == "mserver-go" else RUST_ARMS)
    presets = []
    for prog, arms in want.items():
        for arm in arms:
            oks = covered.get(prog, {}).get(arm, [])
            presets.append({"preset": f"suite/{prog}/{arm}", "status": "green" if oks and all(oks) else "red",
                            "detail": f"{sum(oks)} of {len(oks)} checks passed" if oks else "not run"})
    return presets


def load_presets(work: Path, mserver_arms: list, programs: list) -> list:
    rows = jsonl(work / "load.jsonl")
    if not any(r.get("type") == "session" for r in rows):
        return [{"preset": "load", "status": "red", "detail": "no session line"}]
    by_arm: dict = {}
    for w in rows:
        if w.get("type") == "window":
            by_arm.setdefault((w.get("program"), w.get("arm")), []).append(w)
    want = [("mserver", a) for a in mserver_arms]
    for p in programs:
        want += [(p, a) for a in (GO_ARMS if p == "mserver-go" else RUST_ARMS)]
    presets = []
    for key in want:
        ws = by_arm.get(key, [])
        bad = [w for w in ws if w.get("status") != "valid"]
        presets.append({"preset": f"load/{key[0]}/{key[1]}", "status": "green" if ws and not bad else "red",
                        "detail": (f"{len(ws) - len(bad)} of {len(ws)} windows valid" if ws else "not run")
                                  + (f"; {bad[0].get('reasons', [])[:3]}" if bad else "")})
    return presets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("work", "record", "repo", "commit", "repo-head", "sanitizer", "host-tag", "host", "cmake-args",
              "options", "regexmatcher-commit"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--seconds", type=int, required=True)
    ap.add_argument("--cpu", default="unknown", help="the host's CPU model (t3/labsteps.cpu_model)")
    ap.add_argument("--pins", action="append", required=True, help="a pins file the build used (repeatable)")
    ap.add_argument("--coverage", default=str(HERE / "coverage.json"))
    ap.add_argument("--logs-archive", default="")
    ap.add_argument("--logs-sha256", default="")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    work = Path(a.work)
    root = HERE.parent

    m = COMPILER_ID.search(read(work / "build.log"))
    compiler = m.group(1) if m else "unknown"
    steps = {s["step"]: s for s in jsonl(work / "steps.jsonl")}
    gaps = gaps_of(Path(a.coverage), a.host_tag, a.sanitizer)
    programs = [p for p in PROGRAMS if p not in gaps]
    inputs = inputs_of(work)
    built = programs_of(work)
    for p in programs:
        if p in built and "source" in built[p]:
            inputs.setdefault("inputs_hash", {})[p] = built[p]["source"]["inputs_hash"]
            inputs.setdefault("inputs_files", {})[p] = built[p]["source"]["files"]

    presets = []
    for name in STEPS:
        if name == "programs" and not programs:
            continue
        s = steps.get(name)
        presets.append({"preset": name, "status": "green" if s is not None and s.get("exit") == 0 else "red",
                        "detail": "not run" if s is None else f"exit {s.get('exit')}; {s.get('detail', '')}".rstrip("; ")})
    total, failed = ctest_summary(read(work / "ctest.log")) or (0, -1)
    presets.append({"preset": "ctest/summary", "status": "green" if total > 0 and failed == 0 else "red",
                    "detail": f"{total} tests, {failed} failed"})
    for p in programs:
        ok = p in built and built[p].get("sanitizer") not in (None, "none")
        presets.append({"preset": f"programs/{p}", "status": "green" if ok else "red",
                        "detail": f"built with sanitizer {built[p].get('sanitizer')}" if p in built else "not built"})
    mserver_arms = list((steps.get("suite") or {}).get("mserver_arms", []))
    if not mserver_arms:
        presets.append({"preset": "suite/mserver", "status": "red", "detail": "the suite step names no mserver arm"})
    presets += suite_presets(work, mserver_arms, programs)
    presets += load_presets(work, mserver_arms, programs)
    if a.seconds >= 0 and not (a.logs_archive and a.logs_sha256):
        presets.append({"preset": "logs", "status": "red", "detail": "the logs were not kept (D5: archived with a sha256)"})
    reports = report_blocks(work)
    green = (all(p["status"] == "green" for p in presets) and not reports and bool(inputs.get("inputs_hash"))
             and bool(inputs.get("prefix_hashes")))
    rec = {"repo": a.repo, "commit": a.commit, "repo_head": a.repo_head,
           "date": datetime.now().astimezone().isoformat(timespec="seconds"), "host": a.host, "host_tag": a.host_tag,
           "cpu": a.cpu,
           "green": green, "compiler": compiler, **inputs, "programs": built,
           "pins_sha256": {Path(f).resolve().relative_to(root).as_posix(): sha256_lf(Path(f)) for f in a.pins},
           "presets": presets, "tool": "p2r3", "sanitizer": a.sanitizer, "regexmatcher_commit": a.regexmatcher_commit,
           "cmake_args": a.cmake_args, "sanitizer_options": a.options, "seconds": a.seconds,
           # seconds -1: a development run on the desktop (P2_DESKTOP=1), never a record (D5, D7)
           "desktop_development": a.seconds < 0,
           "coverage_gaps": gaps, "sanitizer_reports": len(reports), "report_blocks": reports[:20],
           "logs_archive": a.logs_archive, "logs_archive_sha256": a.logs_sha256,
           "note": a.note or ("Round 3's programs under the sanitizer (t3/sanitize.py): the C++ "
                              "server with every arm, v2's C interface, p2gen and e2e_requests with the CTest suite; "
                              "the functional suite over every program built; p2gen against every arm in count mode.")}
    Path(a.record).parent.mkdir(parents=True, exist_ok=True)
    Path(a.record).write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"record": a.record, "green": green, "sanitizer": a.sanitizer, "reports": len(reports)}))
    for p in presets:
        if p["status"] != "green":
            print(f"  {p['preset']}: {p['status']} ({p['detail']})")
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
