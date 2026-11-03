#!/usr/bin/env python3
"""Round 3's check of p2gen against t1gen (STATE.md, Laptop request 8; Alex's decision 17: reported
only), on the laptop's Arch: the C++ server's null arm in an A/A round of four windows per pair, entry
0 driven by p2gen (windows 1 and 4) and entry 1 by lab/t1's t1gen (windows 2 and 3), static m = 10,
sixteen pairs (t3/plans/gencheck-L.json), timed by t3/p2run.py with every one of its window rules.

    gencheck.py PLAN OUT

Steps; the first that fails stops the job (exit 2, OUT/gencheck-summary.json says why):
  guards   t3/jobs/probe.py's: a clean clone, no compiled source changed since the plan's
           _build_commit, each file of _expect_sha256 the bring-up's;
  t1gen    lab/t1/gen of the lab's tools clone (LAB_TOOLS's grandparent) must equal 1eaee40c3's, the
           commit of its green sanitizer records (lab/sanitizer-records/t1gen-1eaee40c3.json, clang
           22.1.8 on this laptop); built plain Release with clang 22.1.8 (its CMakeLists' measured
           build), T1GEN_COMMIT the tools clone's HEAD; its CTest self-tests must pass;
  run      p2run with each entry-1 window's generator command started from t1gen instead of p2gen
           (the flags are the same) and t1gen's JSON result mapped onto the keys of p2gen's line that
           the verdict reads (t1_as_p2gen); t1gen's own result is kept in the row ("t1gen").
OUT/gencheck-summary.json holds the windows by verdict and generator, t1gen's commit and sha256, and the
binary checks; no rate. The ratio of p2gen's to t1gen's req/s per pair and its interval come from
OUT/gencheck.jsonl by t3/gencheck_analysis.py. Exit status: 2 refused, else p2run's (0: every window ran).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labsteps as L  # noqa: E402
import p2run  # noqa: E402
import probe  # noqa: E402

T1GEN_RECORDED = "1eaee40c3da652a1ec7a3d77e37c2c0f6c35e66e"  # lab/sanitizer-records/t1gen-1eaee40c3.json
T1_ENTRY = 1


def t1_as_p2gen(t1: dict) -> dict:
    """t1gen's result under the keys of p2gen's timed line that p2run's verdict reads. At depth 1 a
    server close with a request in flight is t1gen's eof_inflight, which p2gen counts as a peer close and
    a lost request; a close of an idle connection t1gen does not count, but it makes a reconnect that no
    timeout explains, which the runner's reconnect rule sees."""
    m = t1["measure"]
    return {"tool": "t1gen", "commit": t1.get("commit"), "connections": t1["connections"],
            "thread_failed": t1["thread_failed"], "measure_wall_ns": round(t1["measure_wall_s"] * 1e9),
            "measure": {"completed": m["completed"], "errors_total": m["errors_total"], "timeouts": m["timeouts"],
                        "connect_errors": m["connect_errors"], "reconnects": m["reconnects"],
                        "peer_closes": m["eof_inflight"],
                        "errors": {"status": m["non_2xx"], "framing": m["protocol_errors"],
                                   "lost": m["eof_inflight"] + m["socket_errors"]}}}


class GenCheckRunner(p2run.Runner):
    """p2run's runner, with the windows of entry T1_ENTRY driven by t1gen."""
    t1gen: list[str] = []

    # The overrides take every argument of p2run's methods and pass it on, so a change of p2run's signatures
    # (the round-robin schedule added slot, idle, duration_s and the warm-up's keywords) cannot break them.
    def run_window(self, w, *args, **kwargs):
        row = super().run_window(w, *args, **kwargs)  # a window that failed before its generator ran still names it
        row.setdefault("generator_tool", "t1gen" if w.entry == T1_ENTRY else "p2gen")
        return row

    def _run_generator(self, w, row, port, cell, **kwargs):
        self._t1 = w is not None and w.entry == T1_ENTRY  # no window: a round-robin warm-up, run by p2gen
        row["generator_tool"] = "t1gen" if self._t1 else "p2gen"
        parsed, code, reading = super()._run_generator(w, row, port, cell, **kwargs)
        if self._t1 and parsed is not None:
            row["t1gen"] = parsed
            try:
                parsed = t1_as_p2gen(parsed)
                row["generator"] = parsed
            except (KeyError, TypeError) as e:  # a t1gen line the mapping does not know: no result to judge
                row["t1gen_schema_error"] = repr(e)
                row.pop("generator", None)
                parsed = None
        return parsed, code, reading

    def _generator_cmd(self, port, cell, result, *args, **kwargs):
        cmd = super()._generator_cmd(port, cell, result, *args, **kwargs)
        return [*self.t1gen, *cmd[len(self.plan.p2gen):]] if getattr(self, "_t1", False) else cmd


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_t1gen(tools: Path, out: Path, env: dict) -> tuple[Path, str]:
    """t1gen's Release build from the tools clone, or a StepError."""
    src = tools / "lab" / "t1" / "gen"
    if subprocess.run(["git", "-C", str(tools), "diff", "--quiet", T1GEN_RECORDED, "HEAD", "--", "lab/t1/gen"]).returncode:
        raise L.StepError(f"lab/t1/gen differs from {T1GEN_RECORDED[:9]}, which its green records cover")
    commit = subprocess.run(["git", "-C", str(tools), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    build, log = out / "t1gen-build", out / "t1gen-build.log"
    rc = L.run([L.cmake_exe(), "-S", src, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                f"-DCMAKE_MAKE_PROGRAM={L.ninja_exe()}", "-DCMAKE_C_COMPILER=clang", f"-DT1GEN_COMMIT={commit}"], log, env)
    if rc == 0:
        rc = L.run([L.cmake_exe(), "--build", build], log, env, append=True)
    if rc == 0:
        rc = L.run([L.ctest_exe(), "--output-on-failure"], log, env, cwd=build, append=True)
    if rc != 0:
        raise L.StepError(f"t1gen's build or self-tests failed; see {log.name}")
    return build / "t1gen", commit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", type=Path)
    ap.add_argument("out", type=Path)
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "gencheck-summary.json"
    plan = json.loads(a.plan.read_text(encoding="utf-8"))

    def refuse(why: list) -> int:
        for r in why:
            print(f"gencheck.py: refused: {r}", file=sys.stderr)
        summary_path.write_text(json.dumps({"refused": why}, indent=1) + "\n", encoding="utf-8")
        return 2

    if L.WINDOWS or not os.environ.get("LAB_TOOLS"):
        return refuse(["t1gen is Linux only, and its sources come from the lab's tools clone (LAB_TOOLS)"])
    refused = probe.refusals(plan)
    if refused:
        return refuse(refused)
    env = L.tool_env()
    try:
        compiler = (L.output(["clang", "--version"], env).splitlines() or [""])[0]  # t1gen is C, built by clang
        want = os.environ.get("EXPECT_CLANG") or L.EXPECT["EXPECT_CLANG"]
        if f"clang version {want}" not in compiler:
            raise L.StepError(f"clang is not {want}, the compiler of t1gen's records: {compiler}")
        t1gen, tools_commit = build_t1gen(Path(os.environ["LAB_TOOLS"]).resolve().parent.parent, out, env)
    except L.StepError as e:
        return refuse([str(e)])
    t1gen_sha = sha256(t1gen)
    print(f"gencheck.py: t1gen {t1gen_sha[:12]} from tools {tools_commit[:9]}, {compiler}", flush=True)

    GenCheckRunner.t1gen = [str(t1gen)]
    p2run.Runner = GenCheckRunner  # run_all builds its runner by this name
    rc = p2run.main([str(a.plan.resolve()), "--out", str(out / "gencheck.jsonl"), "--workdir",
                     str(out / "gencheck.work"), "--keep-logs"])
    jsonl = out / "gencheck.jsonl"
    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()] if jsonl.exists() else []
    windows = [r for r in rows if r.get("type") == "window"]
    by = {}
    for w in windows:
        key = f"{w.get('generator_tool')}/{w.get('status')}"
        by[key] = by.get(key, 0) + 1
    session = next((r for r in rows if r.get("type") == "session"), None)
    summary = {"p2run_exit": rc, "windows": len(windows), "by_generator_and_status": by,
               "t1gen": {"path": str(t1gen), "sha256": t1gen_sha, "tools_commit": tools_commit,
                         "sources_equal": T1GEN_RECORDED, "compiler": compiler,
                         "sha256_after_run_equal": t1gen.is_file() and sha256(t1gen) == t1gen_sha},
               "not_valid": [{k: w.get(k) for k in ("seq", "generator_tool", "entry", "table_seed", "status", "reasons")}
                             for w in windows if w.get("status") != "valid"],
               "session_binaries_differ": probe.session_differs(session, plan["_expect_sha256"]) if session else ["no session line"],
               "binaries_after_run": probe.binary_problems(plan["_expect_sha256"])}
    summary_path.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("p2run_exit", "windows", "by_generator_and_status", "binaries_after_run")}))
    bad = summary["session_binaries_differ"] or summary["binaries_after_run"] or not summary["t1gen"]["sha256_after_run_equal"]
    return 2 if bad else rc


if __name__ == "__main__":
    sys.exit(main())
