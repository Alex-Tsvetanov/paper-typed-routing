#!/usr/bin/env python3
"""One D5 sanitizer record of round 3, on either system of the laptop (STATE.md, Laptop requests 0
and 4; design/round3/end-to-end.md, section 8).

    sanitize.py asan|tsan|msan RECORDS_DIR SETS_DIR [--work DIR] [--desktop]

Linux (host L) records asan (ASan+UBSan), tsan and msan; Windows (host W) asan, with clang-cl. The
steps, each a line of WORK/steps.jsonl; a failed step does not stop the later ones, and the record
says which failed (t3/record.py):
  build     the paper's root project (mserver with every external arm the build has, v2's C
            interface, p2gen, e2e_requests, the tests), Release, under the sanitizer (labsteps.py);
  ctest     its whole CTest suite, every test's output kept (ctest -V);
  inputs    what each measured target compiled (labsteps.inputs, lab/bin/inputs_hash.py);
  programs  the Go and Rust programs where their toolchains can instrument them
            (t3/build_programs.py --sanitizer; the gaps are t3/coverage.json's): L asan, Go -asan
            and Rust -Zsanitizer=address against this tree's libp2v2_c.a; L tsan, Go -race
            against an uninstrumented libp2v2_c.a (WORK/capi-plain: the race runtime and clang's
            ThreadSanitizer runtime cannot share a process); L msan, neither; W asan, Rust
            -Zsanitizer=address against this tree's p2v2_c.lib;
  sets      this tree's e2e_requests writes twelve cells (both shapes; m = 10, 1,000, 10,000; the
            first two seed pairs), checked against t3/requests-manifest.tsv;
  suite     t3/run_checks.py over this tree's mserver, every arm, and the programs built, on
            SETS_DIR (the bring-up job's request sets), every server's output kept;
  load      t3/p2run.py in count mode with this tree's p2gen against every arm of every program
            built, both shapes at m = 1,000, the pair (111, 211), 20,000 requests a window, every
            log kept. Count mode reads no time.
Then the logs (WORK without its build trees and binaries) go to RECORDS_LOGS/<name>/ and
<name>.tar.gz (labsteps.keep_logs, which refuses an existing name), and t3/record.py writes
RECORDS_DIR/<name>.json, <name> being p2r3-<code commit, 9 characters>-<L|W>-<sanitizer>. The code
commit is the last commit that changed the sources below, which must have no local changes. With
--desktop (a development run on the desktop, D7) no time is read, the record's seconds are -1 and its
name ends in -desktop: it never passes for a record and never goes to lab/sanitizer-records.
Exit status: record.py's (0 green), 2 when the run could not start.

Without --desktop it runs only on the laptop (labsteps.LAPTOP: host name and CPU), and the record
names both. mserver's arms must be the system's (labsteps.EXPECTED_ARMS), so a missing tool tree
fails the run instead of leaving an arm out.

Environment: labsteps.py's (toolchain locations, INPUTS_HASH_PY or LAB_TOOLS, RECORDS_LOGS), JOBS
(default the CPU count), P2_CPU_SERVER, P2_CPU_GEN, P2_CPU_HOUSE (14, 2-13, 0-1). Downloads: the
CMake FetchContent archives, each checked against its sha256 (bench/cmake/pins.cmake,
server/cmake/pins-round3.cmake), except RapidJSON v1.1.0, which Pistache's CMake fetches on Linux by
git tag when the system has none, as in round 2 (the record lists it under third_party.fetched);
Go modules against go.sum; crates against Cargo.lock (--locked).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labsteps as L  # noqa: E402

SOURCES = ("CMakeLists.txt", "server", "t3", "bench/core", "bench/arms", "bench/cmake", "t1/h6_targets.cpp")
HOST_SANITIZERS = {"L": ("asan", "tsan", "msan"), "W": ("asan",)}
GO_ARMS = ["v2", "httprouter", "gin", "nethttp", "chi", "null"]
RUST_ARMS = ["v2", "matchit", "path-tree", "actix-router", "null"]
NOT_KEPT = {"build", "capi-plain", "progs", "gocache", "sets-check"}


class Steps:
    def __init__(self, path: Path) -> None:
        self.path = path

    def add(self, name: str, rc: int, detail: str = "", **extra) -> None:
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"step": name, "exit": rc, "detail": detail, **extra}) + "\n")
        print(f"== {name} exit {rc} {detail}", flush=True)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def last_line(p: Path) -> str:
    lines = read(p).strip().splitlines()
    return lines[-1] if lines else ""


def external_arms(log: Path) -> str:
    m = re.search(r"^-- mserver: external arms (.*)$", read(log), re.MULTILINE)
    return m.group(1).strip() if m else ""


def program_steps(san: str, work: Path, build: Path, env: dict, jobs: int, steps: Steps) -> tuple:
    """Builds the programs this record covers; returns (go binary or "", rust binary or "")."""
    if L.WINDOWS:
        flags = ["--sanitizer", "asan", "--no-go"]
    else:
        flags = {"asan": ["--sanitizer", "asan"], "tsan": ["--sanitizer", "race", "--no-rust"], "msan": []}[san]
    if not flags:
        return "", ""
    cxx = build
    rc = 0
    if san == "tsan":
        cxx = work / "capi-plain"
        rc, _ = L.configure(cxx, "none", work / "capi-plain.log", env, jobs, extra=["-DMSERVER_EXTERNALS="],
                            targets=["p2v2_c"])
    if rc == 0:
        penv = dict(env, GOCACHE=str(work / "gocache"))
        rc = L.run([L.PY, L.T3 / "build_programs.py", "--cxx-build", cxx, "--out", work / "progs", "-j", str(jobs), *flags],
                   work / "programs.log", penv)
    info_path = work / "progs" / "build-info.json"
    if info_path.exists():
        shutil.copyfile(info_path, work / "programs-build-info.json")
    steps.add("programs", rc, "build_programs.py " + " ".join(flags))
    if rc != 0:
        return "", ""
    info = json.loads(info_path.read_text(encoding="utf-8"))
    return info.get("go", {}).get("binary", ""), info.get("rust", {}).get("binary", "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sanitizer", choices=("asan", "tsan", "msan"))
    ap.add_argument("records", type=Path)
    ap.add_argument("sets", type=Path)
    ap.add_argument("--work", type=Path, help="default: ~/lab/p2r3/san (the work directory is WORK/<sanitizer>)")
    ap.add_argument("--desktop", action="store_true", help="a development run on the desktop: no time, never a record")
    a = ap.parse_args()
    host_tag = L.host_tag()
    san = a.sanitizer
    host, cpu = socket.gethostname(), L.cpu_model()
    try:
        if san not in HOST_SANITIZERS[host_tag]:
            raise L.StepError(f"host {host_tag} records {', '.join(HOST_SANITIZERS[host_tag])}, not {san}")
        if not a.desktop and not L.on_laptop(host_tag, host, cpu):
            raise L.StepError(f"records are made on the laptop only ({L.LAPTOP[host_tag]['host']}), not on {host} "
                              f"({cpu}); a development run here takes --desktop")
        if not (a.sets / "manifest.tsv").is_file():
            raise L.StepError(f"no request sets at {a.sets} (the bring-up job makes them)")
        ih = L.inputs_hash_py()
        code = L.git("log", "-1", "--format=%H", "--", *SOURCES)
        if L.git("status", "--porcelain", "--", *SOURCES):
            raise L.StepError("the sources have local changes; a record must name committed code")
        name = f"p2r3-{code[:9]}-{host_tag}-{san}" + ("-desktop" if a.desktop else "")
        L.check_logs(name)
        env = L.tool_env(san)
        versions = L.versions(env, check=not a.desktop)
    except L.StepError as e:
        print(f"sanitize.py: {e}", file=sys.stderr)
        return 2
    sets = a.sets.resolve()
    records = a.records.resolve()
    records.mkdir(parents=True, exist_ok=True)
    work = ((a.work or Path.home() / "lab" / "p2r3" / "san") / san).resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / "versions.json").write_text(json.dumps(versions, indent=1) + "\n", encoding="utf-8")
    jobs = int(os.environ.get("JOBS") or os.cpu_count() or 4)
    start = None if a.desktop else time.monotonic()
    steps = Steps(work / "steps.jsonl")
    print(f"sanitize.py {san}: {name}, {versions['compiler']}, host {socket.gethostname()}", flush=True)

    build = work / "build"
    rc, args = L.configure(build, san, work / "build.log", env, jobs)
    steps.add("build", rc, external_arms(work / "build.log"))
    if rc == 0:
        rc = L.run([L.ctest_exe(), "-V"], work / "ctest.log", env, cwd=build)
        steps.add("ctest", rc, next((l for l in reversed(read(work / "ctest.log").splitlines()) if "tests passed" in l), ""))
        arms: list = []
        try:
            listed = L.mserver_arms(build, env, work / "arms.log")
            L.check_arms(listed)
            arms = [x for x in listed if x != "v1"]
            steps.add("inputs", 0, f"{L.inputs(build, work / 'build', env, ih)} targets")
        except L.StepError as e:
            steps.add("inputs", 1, str(e))
        go_bin, rust_bin = program_steps(san, work, build, env, jobs, steps)
        rc = L.run([L.PY, L.T3 / "make_requests.py", "--bin", L.exe(build / "e2e_requests"), "--out", work / "sets-check",
                    "--sizes", "10,1000,10000", "--pairs", "2"], work / "sets.log", env)
        if rc == 0:
            rc = L.run([L.PY, L.T3 / "make_requests.py", "--verify", work / "sets-check", "--manifest",
                        L.T3 / "requests-manifest.tsv"], work / "sets.log", env, append=True)
        steps.add("sets", rc, last_line(work / "sets.log"))
        mserver = L.exe(build / "server" / "mserver")
        suite = ["--mserver", mserver] + (["--go", go_bin] if go_bin else []) + (["--rust", rust_bin] if rust_bin else [])
        # Under a sanitizer one pipelined batch of a linear-scan arm at m = 100,000 can take minutes.
        rc = L.run([L.PY, L.T3 / "run_checks.py", "--data", sets, *suite, "--out", work / "suite.jsonl", "--logs",
                    work / "suite-logs", "--io-timeout", "900"], work / "suite.out", env)
        steps.add("suite", rc, last_line(work / "suite.out"), mserver_arms=arms)
        programs = [("mserver", mserver, arms, None)]
        if go_bin:
            programs.append(("mserver-go", go_bin, GO_ARMS, None))
        if rust_bin:
            programs.append(("mserver-rs", rust_bin, RUST_ARMS, None))
        L.load_plan(work / "load-plan.json", L.exe(build / "t3" / "gen" / "p2gen"), sets, programs, [1000],
                    "t3/sanitize.py's load step: count mode, untimed")
        rc = L.run([L.PY, L.T3 / "p2run.py", work / "load-plan.json", "--out", work / "load.jsonl", "--count", "20000",
                    "--workdir", work / "load.work", "--keep-logs"], work / "load.out", env)
        steps.add("load", rc, last_line(work / "load.out"))

    seconds = -1 if start is None else int(time.monotonic() - start)
    try:
        archive, sha = L.keep_logs(name, [p for p in sorted(work.iterdir()) if p.name not in NOT_KEPT])
    except (L.StepError, OSError) as e:
        print(f"sanitize.py: the logs were not kept: {e}", file=sys.stderr)
        archive, sha = "", ""
    pins = (L.ROOT / "bench" / "cmake" / "pins.cmake").read_text(encoding="utf-8")
    rm_commit = re.search(r"^set\(RB_REGEXMATCHER_V2_COMMIT ([0-9a-f]+)\)", pins, re.MULTILINE).group(1)
    options = ";".join(f"{k}={v}" for k, v in (L.SANITIZER_ENV_W if L.WINDOWS else L.SANITIZER_ENV)[san].items())
    rc = L.run([L.PY, L.T3 / "record.py", "--work", work, "--record", records / f"{name}.json", "--repo", L.REPO_URL,
                "--commit", code, "--repo-head", L.git("rev-parse", "HEAD"), "--sanitizer", san, "--host-tag", host_tag,
                "--host", host, "--cpu", cpu, f"--cmake-args={' '.join(args)}", f"--options={options}",
                "--seconds", str(seconds), "--regexmatcher-commit", rm_commit,
                "--pins", L.ROOT / "bench" / "cmake" / "pins.cmake", "--pins", L.ROOT / "server" / "cmake" / "pins-round3.cmake",
                "--logs-archive", archive, "--logs-sha256", sha], work / "record.out", env)
    print(read(work / "record.out").strip())
    return rc


if __name__ == "__main__":
    sys.exit(main())
