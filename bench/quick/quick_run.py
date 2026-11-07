"""Runs one P2 quick plan on the laptop (quick-plan.md). Release builds only; one campaign of at most 600 s.

    quick_run.py --plan NAME --quick SHA256 --commit SHA --build-dir DIR --out-dir DIR [--dry-run]

Before anything is timed it refuses (exit 2) unless: the plan file bench/quick/plans/NAME.jsonl has the
sha256 given (CRLF read as LF); HEAD is --commit; the plan's system is this one; the build's
compile_commands.json shows every C and C++ file of bench/ built at -O3 and at no other level (rule 1); the
binaries exist; and the untimed correctness checks pass: every ctest of the build, and for an rbench plan
the agreement test of the plan's arms on its shapes, sizes and table seeds (rbench agree, judged by
check_agree.py against semantics.json, with a row for every arm that has a router) and every arm's probes.
Sanitizers are not run here (CLAUDE.md rule 2): they prove correctness on the workstation and gate nothing.

It then runs the rows in the plan's order, each process alone on CPU 2 (taskset), and keeps every process:
units/<id>.json (the process's one JSON line), units/<id>.err (its standard error). Before each round after
the first it stops when the time used plus the mean round so far would pass 600 s; before each process it
stops when the time used plus that process's estimate (the longest the same cell took so far, else the
plan's estimate) would pass 600 s, and a process still running when the 600 s end is stopped (exit -9, its
output kept). Each cut is recorded. A process that fails or times out is recorded
with its exit code and not rerun. job.json holds the plan header, the checks, every process's exit code and
wall seconds, the rounds run and the cut. Exit 0 when every process exited 0, 3 when one did not (its data
is kept), 2 for a refusal before anything is timed. --dry-run checks the plan and prints the commands.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quick_common as qc  # noqa: E402

NO_ROUTER = {"null", "null-no405", "capi-null", "rust-null"}  # rbench agree has no row for them
OTHER_LEVELS = ("-O0", "-O1", "-O2", "-Os", "-Oz", "-Og", "-Ofast")


class Refusal(Exception):
    pass


def this_os() -> str:
    return "windows" if platform.system() == "Windows" else "linux"


def read_plan(name: str, sha: str, plans_dir: Path = qc.PLANS_DIR) -> tuple[dict, list[dict]]:
    path = plans_dir / f"{name}.jsonl"
    if path.parent.resolve() != plans_dir.resolve() or not path.is_file():
        raise Refusal(f"no plan {name} in {plans_dir}")
    got = qc.file_sha256(path)
    if got != sha:
        raise Refusal(f"plan {name} has sha256 {got}, not {sha}")
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    rows = [json.loads(x) for x in lines[1:] if x.strip()]
    if header.get("plan") != name or not rows:
        raise Refusal(f"plan {name}: header or rows missing")
    return header, rows


def git(*args: str, cwd: Path = qc.REPO) -> subprocess.CompletedProcess:
    exe = os.environ.get("LAB_GIT", "git")
    return subprocess.run([exe, "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)


def check_code(commit: str) -> None:
    head = git("rev-parse", "HEAD")
    if head.returncode != 0 or head.stdout.strip() != commit:
        raise Refusal(f"HEAD is {head.stdout.strip() or head.stderr.strip()}, not {commit}")


def check_release(build_dir: Path, bench: Path = qc.BENCH) -> dict:
    """Rule 1: every C and C++ file of bench/ at -O3 and at no other optimization level."""
    cc = build_dir / "compile_commands.json"
    if not cc.is_file():
        raise Refusal(f"no {cc}: configure with -DCMAKE_EXPORT_COMPILE_COMMANDS=ON")
    root = bench.resolve()
    checked = 0
    for e in json.loads(cc.read_text(encoding="utf-8")):
        f = Path(e.get("directory", "."), e.get("file", ""))
        try:
            f.resolve().relative_to(root)
        except ValueError:
            continue  # a fetched dependency's file
        words = shlex.split(e.get("command") or "") or e.get("arguments", [])
        if "-O3" not in words:
            raise Refusal(f"{e.get('file')} is not built with -O3")
        other = [w for w in words if w in OTHER_LEVELS]
        if other:
            raise Refusal(f"{e.get('file')} carries another optimization level {other}")
        checked += 1
    if checked == 0:
        raise Refusal("compile_commands.json names no file of bench/")
    return {"files_checked": checked, "level": "-O3"}


def run_check(cmd: list[str], out: Path, cwd: Path | None = None, timeout: float = 3600) -> int:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    out.write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    return p.returncode


def correctness(header: dict, rows: list[dict], build_dir: Path, out_dir: Path) -> dict:
    """The untimed checks before any timing; a failure is a refusal."""
    chk = out_dir / "checks"
    chk.mkdir(parents=True, exist_ok=True)
    rec: dict = {}
    rc = run_check(["ctest", "--test-dir", str(build_dir), "--output-on-failure"], chk / "ctest.txt")
    rec["ctest_exit"] = rc
    if rc != 0:
        raise Refusal(f"ctest failed (exit {rc}, checks/ctest.txt); nothing timed")
    if header["kind"] != "rbench":
        return rec
    rbench = str(build_dir / "rbench")
    arms = sorted({r["arm"] for r in rows})
    routed = [a for a in arms if a not in NO_ROUTER]
    seeds = sorted({r["table_seed"] for r in rows})
    agree = chk / "agree.jsonl"
    p = subprocess.run([rbench, "agree", "--arms", ",".join(routed), "--shapes", ",".join(header["shapes"]),
                        "--sizes", ",".join(str(m) for m in header["sizes"]), "--seeds", ",".join(map(str, seeds))],
                       capture_output=True, text=True, timeout=3600)
    agree.write_text(p.stdout, encoding="utf-8")
    (chk / "agree-stderr.log").write_text(p.stderr, encoding="utf-8")
    rec["agree_exit"] = p.returncode
    if p.returncode > 1 or any(x.startswith("rbench: ") for x in p.stderr.splitlines()):
        raise Refusal(f"rbench agree failed (exit {p.returncode}, checks/agree-stderr.log); nothing timed")
    rc = run_check([sys.executable, "-I", "-B", str(qc.BENCH / "check_agree.py"), str(agree)], chk / "check_agree.txt")
    rec["check_agree_exit"] = rc
    if rc != 0:
        raise Refusal("the agreement test failed (check_agree.py, checks/check_agree.txt); nothing timed")
    seen = {json.loads(x).get("arm") for x in p.stdout.splitlines() if x.strip()}
    missing = [a for a in routed if a not in seen]
    if missing:
        raise Refusal(f"no agreement row for {missing}; nothing timed")
    probes = []
    for a in routed:
        q = subprocess.run([rbench, "probe", "--arm", a], capture_output=True, text=True, timeout=600)
        (chk / f"probe-{a}.jsonl").write_text(q.stdout + q.stderr, encoding="utf-8")
        if q.returncode != 0 or not q.stdout.strip():
            raise Refusal(f"the probe of {a} failed (exit {q.returncode}); nothing timed")
        probes.append(a)
    rec["agree_rows"] = len([x for x in p.stdout.splitlines() if x.strip()])
    rec["probed"] = probes
    return rec


def command(header: dict, row: dict, build_dir: Path) -> list[str]:
    exe = build_dir / ("rbench" if row["kind"] == "rbench" else "adversarial")
    return ["taskset", "-c", str(header["cpu"]), str(exe), *row["args"]]


def run_row(cmd: list[str], row: dict, out_dir: Path, timeout_s: float) -> dict:
    units = out_dir / "units"
    units.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        rc, out, err = p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired as e:
        rc, out, err = -9, "", f"timeout after {timeout_s:.0f} s: {e}"
    (units / f"{row['id']}.json").write_text(out, encoding="utf-8")
    (units / f"{row['id']}.err").write_text(err, encoding="utf-8")
    return {"id": row["id"], "rc": rc, "wall_s": round(time.monotonic() - t0, 3)}


def cell_key(row: dict) -> str:
    return row.get("cell") or f"{row['arm']}|{row['shape']}|{row['m']}"


def run_plan(header: dict, rows: list[dict], build_dir: Path, out_dir: Path, budget_s: float = qc.BUDGET_S,
             runner=run_row, clock=time.monotonic) -> dict:
    job: dict = {"plan": header["plan"], "rounds_planned": header["rounds"], "rounds_run": 0, "cut": None,
                 "units": []}
    t_start = clock()
    round_walls: list[float] = []
    longest: dict[str, float] = {}
    try:
        for rnd in range(header["rounds"]):
            elapsed = clock() - t_start
            if round_walls and elapsed + sum(round_walls) / len(round_walls) > budget_s:
                job["cut"] = f"before round {rnd} of {header['rounds']}: {elapsed:.1f} s used"
                break
            r0 = clock()
            done_round = True
            for row in (r for r in rows if r["round"] == rnd):
                elapsed = clock() - t_start
                est = longest.get(cell_key(row), row["est_s"])
                if elapsed + est > budget_s:
                    job["cut"] = f"before process {row['id']} (round {rnd}): {elapsed:.1f} s used, estimate {est:.1f} s"
                    done_round = False
                    break
                # The budget is a hard bound: a process still running when it ends is stopped (exit -9, kept).
                timeout = max(1.0, min(10 * row["est_s"] + 60, budget_s - elapsed))
                u = runner(command(header, row, build_dir), row, out_dir, timeout)
                longest[cell_key(row)] = max(longest.get(cell_key(row), 0.0), u["wall_s"])
                job["units"].append(dict(u, round=rnd))
            if not done_round:
                break
            round_walls.append(clock() - r0)
            job["rounds_run"] = rnd + 1
    except Exception as e:  # kept with what ran so far
        job["error"] = f"{type(e).__name__}: {e}"
    job["wall_s"] = round(clock() - t_start, 3)
    return job


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run one P2 quick plan (quick-plan.md).")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--quick", required=True, help="the plan file's sha256")
    ap.add_argument("--commit", required=True)
    ap.add_argument("--build-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    job: dict = {"argv": sys.argv[1:], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    try:
        header, rows = read_plan(a.plan, a.quick)
        job["header"] = header
        if header["os"] != this_os():
            raise Refusal(f"plan {a.plan} is for {header['os']}, this is {this_os()}")
        if a.dry_run:
            for r in rows:
                print(" ".join(command(header, r, a.build_dir)))
            print(f"dry run: {len(rows)} processes, {header['rounds']} rounds, nothing run")
            return 0
        check_code(a.commit)
        job["release"] = check_release(a.build_dir)
        for exe in ("rbench", "adversarial"):
            if not (a.build_dir / exe).is_file():
                raise Refusal(f"no {a.build_dir / exe}")
        job["checks"] = correctness(header, rows, a.build_dir, a.out_dir)
    except Refusal as e:
        job["refused"] = str(e)
        (a.out_dir / "job.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
        print(f"quick_run: refused: {e}", file=sys.stderr)
        return 2
    print(f"quick_run: checks passed; timing {len(rows)} planned processes of {a.plan}", flush=True)
    job.update(run_plan(header, rows, a.build_dir, a.out_dir))
    job["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (a.out_dir / "job.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    failed = [u["id"] for u in job["units"] if u["rc"] != 0]
    print(f"quick_run: {len(job['units'])} processes, {job['rounds_run']} rounds, {len(failed)} failed, "
          f"cut: {job['cut']}, {job['wall_s']} s", flush=True)
    return 3 if failed or job.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
