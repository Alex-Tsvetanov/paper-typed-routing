#!/usr/bin/env python3
"""Round 3's bring-up on either system of the laptop (STATE.md, Laptop requests 0, 2 and 3): the
Release builds of the three programs, the request sets, the functional suite, the runner's tests and
one pass of the runner in count mode. Untimed: nothing here reads a time, a rate or a latency of
any program; count mode reads none.

    bringup.py OUT_DIR

Steps, in order; the first that fails stops the job (exit 1), and OUT_DIR/steps.txt says which:
  toolchains  the compiler (clang on Linux, clang-cl on Windows), Go and Rust must be the pinned
              ones (EXPECT_CLANG 22.1.8, EXPECT_GO go1.27.3, EXPECT_RUST 1.99.0); every version goes
              to OUT_DIR/versions.json; the paper clone must have no local changes;
  build       the paper's root project, Release, all targets, in P2R3/build-<commit, 9 characters>
              (a fresh folder: the job stops if it exists);
  ctest       its whole CTest suite;
  inputs      what each measured target compiled (t3/labsteps.py, lab/bin/inputs_hash.py), for D5's
              gate (t3/check_records.py) to match with the records;
  programs    the Go and Rust programs against that build's v2 library (t3/build_programs.py), in
              P2R3/progs-<commit>;
  sets        the request sets in P2R3/sets: made by that build's e2e_requests unless they exist,
              then all 160 cells checked against t3/requests-manifest.tsv;
  suite       t3/run_checks.py over the three programs, every arm;
  runner      t3/test_p2run.py and t3/test_records.py;
  count       t3/p2run.py in count mode over every arm of the three programs, both shapes, m = 10
              and 1,000, the pair (111, 211), 20,000 requests a window, pinned as the campaign is.
OUT_DIR gets the logs and JSON (versions.json, build.log, build.inputs.json, build-info.json,
suite.jsonl, count.jsonl); the build trees stay in P2R3 (default ~/lab/p2r3), outside the job's
folder. Environment: t3/labsteps.py's (toolchain locations, INPUTS_HASH_PY or LAB_TOOLS), P2R3,
JOBS, P2_CPU_SERVER, P2_CPU_GEN, P2_CPU_HOUSE. Downloads as t3/sanitize.py's: FetchContent archives
checked against their sha256 pins, Go modules against go.sum, crates against Cargo.lock.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labsteps as L  # noqa: E402

GO_ARMS = ["v2", "httprouter", "gin", "nethttp", "chi", "null"]
RUST_ARMS = ["v2", "matchit", "path-tree", "actix-router", "null"]


def tail(p: Path) -> str:
    lines = p.read_text(encoding="utf-8", errors="replace").strip().splitlines() if p.exists() else []
    return lines[-1] if lines else ""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: bringup.py OUT_DIR", file=sys.stderr)
        return 2
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    p2r3 = Path(os.environ.get("P2R3") or Path.home() / "lab" / "p2r3")
    jobs = int(os.environ.get("JOBS") or os.cpu_count() or 4)
    steps = out / "steps.txt"

    def ok(name: str, detail: str = "") -> None:
        with open(steps, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{name} 0 {detail}\n")
        print(f"== {name} done {detail}", flush=True)

    def fail(name: str, detail: str) -> int:
        with open(steps, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{name} 1 {detail}\n")
        print(f"STOPPED at {name}: {detail}", flush=True)
        return 1

    try:
        ih = L.inputs_hash_py()
        if L.git("status", "--porcelain"):
            return fail("toolchains", "the paper clone has local changes")
        env = L.tool_env()
        versions = L.versions(env)
    except L.StepError as e:
        return fail("toolchains", str(e))
    head = L.git("rev-parse", "HEAD")
    (out / "versions.json").write_text(json.dumps(dict(versions, paper=head), indent=1) + "\n", encoding="utf-8")
    print(f"bringup: paper {head}, {versions['compiler']}, {versions['go']}, {versions['rustc']}", flush=True)
    ok("toolchains")

    build, progs = p2r3 / f"build-{head[:9]}", p2r3 / f"progs-{head[:9]}"
    if build.exists() or progs.exists():
        return fail("build", f"{build} or {progs} exists; a bring-up build is never made again over one")
    p2r3.mkdir(parents=True, exist_ok=True)
    rc, _ = L.configure(build, "none", out / "build.log", env, jobs, extra=[f"-DP2GEN_COMMIT={head}"])
    if rc != 0:
        return fail("build", "see build.log")
    m = re.search(r"^-- mserver: external arms (.*)$", (out / "build.log").read_text(errors="replace"), re.MULTILINE)
    ok("build", m.group(1).strip() if m else "")

    if L.run([L.ctest_exe(), "--output-on-failure"], out / "ctest.log", env, cwd=build) != 0:
        return fail("ctest", "see ctest.log")
    ok("ctest", next((l for l in reversed((out / "ctest.log").read_text(errors="replace").splitlines())
                      if "tests passed" in l), ""))

    mserver = L.exe(build / "server" / "mserver")
    L.run([mserver, "--router", "??"], out / "router-releases.txt", env)
    try:
        arms = [a for a in L.mserver_arms(build, env) if a != "v1"]
        ok("inputs", f"{L.inputs(build, out / 'build', env, ih)} targets")
    except L.StepError as e:
        return fail("inputs", str(e))

    if L.run([L.PY, L.T3 / "build_programs.py", "--cxx-build", build, "--out", progs, "-j", str(jobs)],
             out / "programs.log", env) != 0:
        return fail("programs", "see programs.log")
    shutil.copyfile(progs / "build-info.json", out / "build-info.json")
    info = json.loads((progs / "build-info.json").read_text(encoding="utf-8"))
    go_bin, rust_bin = info["go"]["binary"], info["rust"]["binary"]
    ok("programs")

    sets = p2r3 / "sets"
    if not (sets / "manifest.tsv").exists():
        if L.run([L.PY, L.T3 / "make_requests.py", "--bin", L.exe(build / "e2e_requests"), "--out", sets],
                 out / "sets.log", env) != 0:
            return fail("sets", "make_requests.py failed; see sets.log")
    if L.run([L.PY, L.T3 / "make_requests.py", "--verify", sets, "--manifest", L.T3 / "requests-manifest.tsv",
              "--complete"], out / "sets.log", env, append=True) != 0:
        return fail("sets", "the request sets differ from the manifest; see sets.log")
    ok("sets", tail(out / "sets.log"))

    if L.run([L.PY, L.T3 / "run_checks.py", "--data", sets, "--mserver", mserver, "--go", go_bin, "--rust", rust_bin,
              "--out", out / "suite.jsonl"], out / "suite.out", env) != 0:
        return fail("suite", tail(out / "suite.out"))
    ok("suite", tail(out / "suite.out"))

    for test in ("test_p2run.py", "test_records.py"):
        if L.run([L.PY, L.T3 / test], out / f"{Path(test).stem}.log", env) != 0:
            return fail("runner", f"{test}; see {Path(test).stem}.log")
    ok("runner", "test_p2run.py, test_records.py")

    L.load_plan(out / "count-plan.json", L.exe(build / "t3" / "gen" / "p2gen"), sets,
                [("mserver", mserver, arms, None), ("mserver-go", go_bin, GO_ARMS, None),
                 ("mserver-rs", rust_bin, RUST_ARMS, None)], [10, 1000],
                "t3/jobs/bringup.py's count step: count mode, untimed")
    if L.run([L.PY, L.T3 / "p2run.py", out / "count-plan.json", "--out", out / "count.jsonl", "--count", "20000",
              "--workdir", p2r3 / f"count-{head[:9]}.work"], out / "count.out", env) != 0:
        return fail("count", tail(out / "count.out"))
    ok("count", tail(out / "count.out"))
    print(f"bringup done: build {build}, programs {progs}, sets {sets}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
