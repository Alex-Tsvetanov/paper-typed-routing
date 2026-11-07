#!/usr/bin/env python3
# Copyright 2026 Alex Tsvetanov
# SPDX-License-Identifier: Apache-2.0
"""The analysis of P2's quick campaigns (quick-plan.md, frozen at 0eea7f6): results/quick/macros.tex,
summary.json, report.txt, tables/ and figures/ from the extracted laptop archives.

    python bench/quick/quick_analyse.py JOB_FOLDER [JOB_FOLDER ...] [--out results/quick]

A JOB_FOLDER is one extracted job (the folder that holds out/job.json and build-rel/). The five jobs of
quick-plan.md are required: quick-L-adv, quick-L-abl-s, quick-L-abl-l, quick-L-bnd-10, quick-L-bnd-100.
Every number comes from the archives.

Release only (Papers CLAUDE.md rule 1): a job stops the run unless its CMake build type is Release with
-O3, its compile_commands.json shows every file of bench/ at -O3 and no other level, every unit record
says Release with no sanitizer, its plan's sha256 is the one the job pinned and its rows are the ones
quick_common.plan_rows expands, the job ran at the frozen commit, and its ctests (and, for an rbench
plan, the agreement test) passed. The unit records carry code commit 7a1fef4: the frozen commit
0eea7f6 adds only quick-plan.md to it, which this script checks with git when the repository has both.

Statistics (rule 4, quick-plan.md "What is computed"): descriptive only. A cell's value per round is
one process's median ns per lookup over rbench's epochs; a ratio is formed per round from the processes
of that round (an rbench round shares its table seed and ring seed across arms), and reported as the
median over rounds with the smallest and largest round. No interval, no test, no Holm step. A process
that is not usable (analysis/cells.py) takes no part in its round's ratio and is listed.

- (a) Adversarial: per cell the counts of the counting copy (they must be equal in every round), the
  written bound checks (analysis/adversarial.py's CHECKS), the median ns over rounds with min and max,
  and the time per node entered; per table the miss query over the last-hit query, per round. The bound
  "holds" when every one of the plan's 33 cells has a usable process in every round, every check passes
  and the counts agree; "fails" when any check fails or the counts differ; "undecided" otherwise.
- (b) Ablations: per cell and round each variant over the copy (the control), and in quick-L-abl-s the
  copy over the pinned arm. Beside them, per arm and cell, the median over rounds of instructions per
  lookup (net of null's in the same round in quick-L-abl-s; raw in quick-L-abl-l, which has no null),
  branch misses and allocations per lookup, and each arm's normalized lookup code from the build's
  objdump checks (the ctest log), which must be the same in all five builds.
- (b) Boundary: per cell and round, regexmatcher-v2-capi over each Rust arm and over the fastest of them
  (the Rust arm with the lowest median over rounds); v2's net time over the fastest competitor's net time
  (each net of its own null, analysis/boundary.py's null_of; the fastest is the competitor with the
  lowest median net time over rounds, and an arm whose net time is not positive in some round is left
  out with boundary.py's rule), with the raw times of the same two arms beside; goloop over each Go arm.
  An arm takes part in a cell only if it is usable in every round (review_common.sort_arms with the
  plan's per-round seed pairs); absent and failing arms are listed with the reason.
- A/A: per cell and round of quick-L-abl-s, the A/A process over v2's (the same binary and arguments);
  median, min and max over all cells and rounds, reported once for Linux and never used to tune.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "bench"))
sys.path.insert(0, str(REPO / "analysis"))
import quick_common as Q  # noqa: E402
from adversarial import CHECKS, COUNTS, RESUMPTION_BOUND, why_unusable  # noqa: E402
from adversarial import cell_word as adv_word  # noqa: E402
from boundary import CAPI, CPP, GOLOOP, RUST, V2, net_times  # noqa: E402
from cells import usable  # noqa: E402
from macros_util import (SIZE_WORD, Macros, cell_word, count, fixed, instructions, listing, nanoseconds,  # noqa: E402
                         pair, per_lookup, ratio, tt)
from review_common import ARM_WORD, sort_arms  # noqa: E402

COMMIT = "0eea7f681c6a4ede67fc61774bfb2fc2328debc1"
CODE_COMMIT = "7a1fef456c1156a1bbacc4e87c0b4cdee7ae9172"
PLANS = ("quick-L-adv", "quick-L-abl-s", "quick-L-abl-l", "quick-L-bnd-10", "quick-L-bnd-100")
PLAN_WORD = {"quick-L-adv": "Adv", "quick-L-abl-s": "AblSmall", "quick-L-abl-l": "AblLarge",
             "quick-L-bnd-10": "BndTen", "quick-L-bnd-100": "BndHundred"}
COPY = "regexmatcher-v2-copy"
VARIANTS = ("regexmatcher-v2-ab-noexact", "regexmatcher-v2-ab-bytes", "regexmatcher-v2-ab-heapstack",
            "regexmatcher-v2-ab-strings")
GO = ("gin", "httprouter", "chi")  # nethttp is not run (quick-plan.md, "Not run")
COMPETITORS = RUST + GO + CPP
NULLS = ("null", "null-no405", "capi-null", "rust-null")
BND_ARMS = (V2, CAPI, GOLOOP) + COMPETITORS + NULLS
AA = "aa"
WORD = {**ARM_WORD, "regexmatcher-v2-ab-heapstack": "Heapstack", "regexmatcher-v2-ab-strings": "Strings"}
OBJDUMP_LABEL = {"copy": COPY, "ab_noexact": VARIANTS[0], "ab_bytes": VARIANTS[1], "ab_heapstack": VARIANTS[2],
                 "ab_strings": VARIANTS[3], "ab_linear": "regexmatcher-v2-ab-linear",
                 "ab_hashed": "regexmatcher-v2-ab-hashed"}
OBJDUMP = re.compile(r"^review-[0-9a-f]+-(\w+) \(clang version ([\d.]+); flags ([^)]*)\): functions (\d+) and (\d+), "
                     r"lines (\d+) and (\d+), sha256 ([0-9a-f]+) and ([0-9a-f]+)\s*$")
FAMILY_TEXT = {"two-kinds": "two kinds", "four-kinds": "four kinds"}
PAPER_NAME = {V2: "RegexMatcher v2", COPY: "renamed copy", VARIANTS[0]: "no exact-match table",
              VARIANTS[1]: "segments byte by byte", VARIANTS[2]: "choice stack on the heap",
              VARIANTS[3]: "owned captured values"}
QUERY_TEXT = {"miss": "miss", "last-hit": "last hit"}
HEAD = "% Generated by bench/quick/quick_analyse.py from the quick laptop archives (quick-plan.md). Do not edit.\n"


class AnalysisError(Exception):
    """An archive that does not match its plan or is not a Release build: the analysis stops."""


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def spread(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"n": len(values), "median": statistics.median(values), "min": min(values), "max": max(values)}


def series(num: dict, den: dict) -> dict:
    """Per key (round or seed pair) num / den where both exist, as median, min and max over the keys."""
    keys = sorted(set(num) & set(den))
    vals = [num[k] / den[k] for k in keys if den[k] > 0 and num[k] > 0]
    out = spread(vals) or {"n": 0}
    out["left_out"] = sorted(str(k) for k in set(num) ^ set(den))
    return out


# ------------------------------------------------------------------------------------------- loading

def check_release(folder: Path, job: dict) -> None:
    if job.get("release", {}).get("level") != "-O3":
        raise AnalysisError(f"{folder}: job.json release level {job.get('release')} (rule 1)")
    cache = (folder / "build-rel" / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    if "CMAKE_BUILD_TYPE:STRING=Release" not in cache:
        raise AnalysisError(f"{folder}: CMake build type is not Release (rule 1)")
    flags = re.search(r"^CMAKE_CXX_FLAGS_RELEASE:STRING=(.*)$", cache, re.MULTILINE)
    if not flags or re.findall(r"-O\S*", flags.group(1)) != ["-O3"]:
        raise AnalysisError(f"{folder}: CMAKE_CXX_FLAGS_RELEASE is {flags and flags.group(1)!r} (rule 1)")
    checked = 0
    for e in read_json(folder / "build-rel" / "compile_commands.json"):
        if "/bench/" not in e["file"]:
            continue
        cmd = e.get("command") or " ".join(e.get("arguments", []))
        if sorted(set(re.findall(r"(?<!\S)-O\S*", cmd))) != ["-O3"]:
            raise AnalysisError(f"{folder}: {e['file']} is not built at -O3 alone (rule 1)")
        checked += 1
    if not checked:
        raise AnalysisError(f"{folder}: compile_commands.json names no file of bench/")


def objdump_rows(folder: Path) -> dict:
    """The normalized lookup code of the ablation arms, from the ctest log of the objdump checks."""
    log = folder / "build-rel" / "Testing" / "Temporary" / "LastTest.log"
    out = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = OBJDUMP.match(line.strip())
        if not m:
            continue
        label, clang, flags, f0, f1, l0, l1, h0, h1 = m.groups()
        arm = OBJDUMP_LABEL[label]
        if arm == COPY:
            out[V2] = {"functions": int(f0), "lines": int(l0), "sha": h0}
        out[arm] = {"functions": int(f1), "lines": int(l1), "sha": h1, "identical_to_reference": h0 == h1,
                    "reference": V2 if arm == COPY else COPY, "reference_sha": h0, "clang": clang, "flags": flags}
    if len(out) != len(OBJDUMP_LABEL) + 1:
        raise AnalysisError(f"{folder}: {len(out)} objdump rows in the ctest log, {len(OBJDUMP_LABEL) + 1} expected")
    return out


def toolchain(folder: Path) -> dict:
    cache = (folder / "build-rel" / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    go = re.search(r"^RB_GO:FILEPATH=.*go(\d+\.\d+\.\d+)/bin/go$", cache, re.MULTILINE)
    rust = None
    for info in sorted((folder / "build-rel" / "cargo").rglob(".rustc_info.json")):
        for v in read_json(info).get("outputs", {}).values():
            m = re.match(r"rustc (\d+\.\d+\.\d+)", v.get("stdout", ""))
            if m:
                rust = m.group(1)
                break
        if rust:
            break
    return {"go": go.group(1) if go else None, "rust": rust}


def load_job(folder: Path) -> dict:
    out = folder / "out"
    job = read_json(out / "job.json")
    argv = dict(zip(job["argv"][::2], job["argv"][1::2]))
    plan = argv.get("--plan")
    if plan not in PLANS:
        raise AnalysisError(f"{folder}: plan {plan!r} is not one of quick-plan.md's")
    plan_file = Q.PLANS_DIR / f"{plan}.jsonl"
    if Q.file_sha256(plan_file) != argv.get("--quick"):
        raise AnalysisError(f"{folder}: plan {plan} sha256 is not the job's pinned {argv.get('--quick')}")
    if plan_file.read_bytes().replace(b"\r\n", b"\n").decode("utf-8") != Q.plan_text(plan):
        raise AnalysisError(f"{folder}: {plan_file.name} is not what quick_common.plan_rows expands")
    if argv.get("--commit") != COMMIT:
        raise AnalysisError(f"{folder}: commit {argv.get('--commit')}, not the frozen {COMMIT}")
    check_release(folder, job)
    checks = job.get("checks", {})
    header, rows = Q.plan_rows(plan)
    # As quick_run.py: rbench agree exits 1 when arms disagree, and check_agree.py judges those rows
    # against semantics.json; exit 2 or more is a failure.
    rbench_bad = header["kind"] == "rbench" and (checks.get("agree_exit") not in (0, 1)
                                                 or checks.get("check_agree_exit") != 0)
    if checks.get("ctest_exit") != 0 or rbench_bad:
        raise AnalysisError(f"{folder}: untimed checks did not pass: {checks}")
    if "100% tests passed" not in (out / "checks" / "ctest.txt").read_text(encoding="utf-8", errors="replace"):
        raise AnalysisError(f"{folder}: ctest.txt does not say 100% tests passed")
    ran = job["rounds_run"]
    want = [r for r in rows if r["round"] < ran]
    units = {u["id"]: u for u in job["units"]}
    if sorted(units) != sorted(r["id"] for r in want):
        raise AnalysisError(f"{folder}: the units are not the plan's rows of rounds 0 to {ran - 1}")
    recs, compilers = [], set()
    for row in want:
        r = read_json(out / "units" / f"{row['id']}.json")
        if r.get("build_type") != "Release" or r.get("sanitizer") != "":
            raise AnalysisError(f"{folder}: {row['id']} is {r.get('build_type')} with sanitizer {r.get('sanitizer')!r}")
        if r.get("code_commit") != CODE_COMMIT:
            raise AnalysisError(f"{folder}: {row['id']} has code commit {r.get('code_commit')}")
        compilers.add(r.get("compiler"))
        recs.append({"row": row, "rec": r, "rc": units[row["id"]]["rc"]})
    if len(compilers) != 1:
        raise AnalysisError(f"{folder}: compilers {compilers}")
    return {"folder": str(folder), "plan": plan, "header": header, "rounds_planned": job["rounds_planned"],
            "rounds_run": ran, "cut": job["cut"], "wall_s": job["wall_s"], "started": job["started"],
            "ended": job["ended"], "recs": recs, "compiler": compilers.pop(), "objdump": objdump_rows(folder),
            "toolchain": toolchain(folder), "rc_not_zero": [x["row"]["id"] for x in recs if x["rc"] != 0]}


def commit_gap() -> list[str] | None:
    """Files that differ between the units' code commit and the frozen commit, or None without git."""
    try:
        p = subprocess.run(["git", "-C", str(REPO), "diff", "--name-only", CODE_COMMIT, COMMIT],
                           capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return sorted(x for x in p.stdout.splitlines() if x.strip())


# ------------------------------------------------------------------------------------------- (a)

def adversarial(job: dict) -> dict:
    by_cell: dict[str, list[dict]] = defaultdict(list)
    for x in job["recs"]:
        by_cell[x["row"]["cell"]].append(x["rec"] | {"round": x["row"]["round"]})
    cells, failing, undecided = [], [], []
    for cid in job["header"]["cells"]:
        rows = sorted(by_cell.get(cid, []), key=lambda r: r["round"])
        reasons = [why_unusable(r, Q.RING_ADV) for r in rows]
        ok = [r for r, why in zip(rows, reasons) if not why]
        first = rows[0]
        c = {"cell": cid, **{k: first[k] for k in ("family", "depth", "catch_all", "query", "routes", "table_nodes")},
             **{k: first[k] for k in COUNTS}, "rounds": len(rows), "usable": len(ok),
             "not_usable": [{"round": r["round"], "reason": w} for r, w in zip(rows, reasons) if w],
             "counts_agree": all(all(r[k] == first[k] for k in COUNTS) for r in rows),
             "checks_pass": all(all(r.get(k) is True for k in CHECKS) for r in rows),
             "ns_by_round": {r["round"]: float(r["ns_median"]) for r in ok}}
        s = spread(list(c["ns_by_round"].values()))
        if s:
            c.update({"ns": s, "ns_per_entry": s["median"] / c["entries"]})
        if not (c["counts_agree"] and c["checks_pass"]):
            failing.append(cid)
        elif c["usable"] < job["rounds_run"]:
            undecided.append(cid)
        cells.append(c)
    decision = "fails" if failing else ("undecided" if undecided or len(cells) != len(job["header"]["cells"])
                                        else "holds")
    by = {c["cell"]: c for c in cells}
    tables = []
    for c in cells:
        if c["query"] != "miss" or c["catch_all"]:
            continue
        hit = by[c["cell"].replace("-miss", "-last-hit")]
        tables.append({"family": c["family"], "depth": c["depth"],
                       "miss_over_last_hit": series(c["ns_by_round"], hit["ns_by_round"])})
    most = max(c["popped"] for c in cells)
    per = [c["ns_per_entry"] for c in cells if "ns_per_entry" in c]
    return {"decision": decision, "failing": failing, "undecided": undecided, "cells": cells, "tables": tables,
            "max_backtracks": most, "max_backtracks_cells": [c["cell"] for c in cells if c["popped"] == most],
            "max_entries": max(c["entries"] for c in cells), "max_walked": max(c["walked_nodes"] for c in cells),
            "max_deepest": max(c["deepest_stack"] for c in cells),
            "max_resumptions": max(c["max_resumptions_per_node"] for c in cells),
            "max_entries_per_node": max(c["max_entries_per_node"] for c in cells),
            "max_entries_over_walked": max(c["entries"] / c["walked_nodes"] for c in cells),
            "ns_per_entry": spread(per), "processes": sum(c["rounds"] for c in cells),
            "processes_usable": sum(c["usable"] for c in cells)}


# ------------------------------------------------------------------------------------------- (b)

def rbench_cells(job: dict) -> dict:
    """{(shape, m): {arm label: [record with its round]}}; the A/A process has label "aa"."""
    out: dict = defaultdict(lambda: defaultdict(list))
    for x in job["recs"]:
        row = x["row"]
        out[(row["shape"], row["m"])][AA if row.get("aa") else row["arm"]].append(x["rec"] | {"round": row["round"]})
    return out


def by_round(rows: list[dict], key: str = "ns_median", left_out: list | None = None, arm: str = "") -> dict:
    vals = {}
    for r in rows:
        if usable(r) and isinstance(r.get(key), (int, float)):
            vals[r["round"]] = float(r[key])
        elif left_out is not None:
            left_out.append(f"{arm} round {r['round']}: status {r.get('status')}")
    return vals


def ablation(job: dict) -> dict:
    small = job["plan"] == "quick-L-abl-s"
    cells, left_out = [], []
    for (shape, m), arms in sorted(rbench_cells(job).items(), key=lambda kv: (kv[0][1], Q.SHAPES.index(kv[0][0]))):
        ns = {a: by_round(rows, left_out=left_out, arm=f"{a} {shape} {m}") for a, rows in arms.items()}
        c = {"shape": shape, "m": m, "variants": {a: series(ns[a], ns[COPY]) for a in VARIANTS}, "arms": {}}
        if small:
            c["copy_vs_v2"] = series(ns[COPY], ns[V2])
        null_i = by_round(arms["null"], "instructions") if small else {}
        for a in (V2, COPY) + VARIANTS:
            if a not in arms:
                continue
            ins = by_round(arms[a], "instructions")
            net = {k: v - null_i[k] for k, v in ins.items() if k in null_i} if small else ins
            c["arms"][a] = {"ns": spread(list(ns[a].values())), "instructions": spread(list(net.values())),
                            "instructions_net_of_null": small,
                            "branch_misses": spread(list(by_round(arms[a], "branch_misses").values())),
                            "allocs": spread(list(by_round(arms[a], "allocs_per_lookup").values()))}
        cells.append(c)
    return {"cells": cells, "left_out": left_out}


def aa(job: dict) -> dict:
    vals = []
    for arms in rbench_cells(job).values():
        second, first = by_round(arms[AA]), by_round(arms[V2])
        vals += [second[r] / first[r] for r in sorted(set(second) & set(first))]
    out = spread(vals) or {"n": 0}
    out["cells"] = len(rbench_cells(job))
    return out


def boundary_cells(job: dict) -> dict:
    expected = [(Q.table_seed(job["plan"], r), Q.ring_seed(job["plan"], r)) for r in range(job["rounds_run"])]
    rows = []
    for (shape, m), cell in sorted(rbench_cells(job).items(), key=lambda kv: Q.SHAPES.index(kv[0][0])):
        arms = sort_arms(cell, shape, list(BND_ARMS), expected_pairs=expected)
        ok = arms.ok
        raw = {a: {pair(r): float(r["ns_median"]) for r in ok[a]} for a in ok}
        nulls = {k: v for k, v in ok.items() if k in NULLS}
        nets = {}
        for a in ok:
            if a in NULLS:
                continue
            n = net_times(a, ok[a], nulls)
            if len(n) == len(ok[a]):
                nets[a] = n
        row = {"shape": shape, "m": m, "absent": arms.absent, "failing": arms.failing, "unusable": arms.unusable,
               "arms": {a: {"ns": spread(list(raw[a].values())),
                            "net_ns": spread(list(nets[a].values())) if a in nets else None} for a in ok},
               "capi": {}, "goloop": {}}
        for t in RUST:
            if CAPI in raw and t in raw:
                row["capi"][t] = series(raw[CAPI], raw[t])
        rust = {a: statistics.median(raw[a].values()) for a in RUST if a in raw}
        if CAPI in raw and rust:
            best = min(rust, key=rust.get)
            row["capi"]["fastest"] = series(raw[CAPI], raw[best]) | {"arm": best}
        positive = {a: n for a, n in nets.items() if all(v > 0 for v in n.values())}
        left = {a: ("its net time is not positive in some round" if a in nets else "its null is not usable in every round")
                for a in (V2,) + COMPETITORS if a in ok and a not in positive}
        row["net_left_out"] = left
        comp = {a: positive[a] for a in COMPETITORS if a in positive}
        rawmed = {a: statistics.median(raw[a].values()) for a in COMPETITORS if a in raw}
        lowest = min(rawmed, key=rawmed.get) if rawmed else None
        if V2 not in positive:
            row["net"] = {"status": "not compared", "why": "v2's net time is missing or not positive"}
        elif not comp:
            row["net"] = {"status": "not compared", "why": "no competitor's net time"}
        elif lowest in left:
            row["net"] = {"status": "not compared",
                          "why": f"{lowest} has the lowest raw median of the competitors and is left out ({left[lowest]})"}
        else:
            med = {a: statistics.median(n.values()) for a, n in comp.items()}
            best = min(med, key=med.get)
            row["net"] = series(positive[V2], comp[best]) | {"status": "compared", "arm": best,
                                                             "raw": series(raw[V2], raw[best])}
        for t in GO:
            if GOLOOP in raw and t in raw:
                row["goloop"][t] = series(raw[GOLOOP], raw[t])
        rows.append(row)
    return {"cells": rows}


# ------------------------------------------------------------------------------------------- analyse

def analyse(folders: list[Path]) -> dict:
    jobs = {}
    for f in folders:
        j = load_job(f)
        if j["plan"] in jobs:
            raise AnalysisError(f"two jobs of plan {j['plan']}")
        jobs[j["plan"]] = j
    missing = [p for p in PLANS if p not in jobs]
    if missing:
        raise AnalysisError(f"missing jobs: {missing}")
    code = {json.dumps(j["objdump"], sort_keys=True) for j in jobs.values()}
    if len(code) != 1:
        raise AnalysisError("the normalized lookup code differs between the five builds")
    tools = {json.dumps(j["toolchain"], sort_keys=True) for j in jobs.values()}
    compilers = {j["compiler"] for j in jobs.values()}
    if len(tools) != 1 or len(compilers) != 1:
        raise AnalysisError(f"toolchains differ between the builds: {tools} {compilers}")
    any_rec = jobs["quick-L-abl-s"]["recs"][0]["rec"]
    epochs = {len(x["rec"].get("epoch_ns") or []) for j in jobs.values() for x in j["recs"] if usable(x["rec"])}
    rings = {x["rec"].get("ring_size") for p in PLANS[1:] for x in jobs[p]["recs"] if usable(x["rec"])}
    if len(epochs) != 1 or len(rings) != 1:
        raise AnalysisError(f"epochs {epochs} or rbench rings {rings} differ")
    abl = {"small": ablation(jobs["quick-L-abl-s"]), "large": ablation(jobs["quick-L-abl-l"])}
    return {
        "meta": {"commit": COMMIT, "code_commit": CODE_COMMIT, "commit_gap": commit_gap(),
                 "regexmatcher_commit": any_rec["regexmatcher_commit"], "compiler": compilers.pop(),
                 "target_cpu": any_rec["target_cpu"], "goamd64": any_rec["goamd64"],
                 **json.loads(tools.pop()), "epochs": epochs.pop(), "ring": rings.pop(), "adv_ring": Q.RING_ADV,
                 "cpu": Q.CPU, "budget_s": Q.BUDGET_S},
        "jobs": {p: {k: v for k, v in j.items() if k not in ("recs", "objdump", "header")} |
                 {"processes": len(j["recs"]), "processes_per_round": j["header"]["processes_per_round"],
                  "not_usable": sum(1 for x in j["recs"] if not (usable(x["rec"]) if j["header"]["kind"] == "rbench"
                                                                   else not why_unusable(x["rec"], Q.RING_ADV)))}
                 for p, j in jobs.items()},
        "code": jobs["quick-L-abl-s"]["objdump"],
        "adversarial": adversarial(jobs["quick-L-adv"]),
        "ablation": abl,
        "aa": aa(jobs["quick-L-abl-s"]),
        "boundary": {"ten": boundary_cells(jobs["quick-L-bnd-10"]), "hundred": boundary_cells(jobs["quick-L-bnd-100"])},
    }


# ------------------------------------------------------------------------------------------- macros

def trio(mc: Macros, name: str, s: dict | None, fmt=ratio) -> None:
    if s and s.get("n"):
        mc.add(name + "Ratio" if fmt is ratio else name, fmt(s["median"]))
        mc.add(name + "Min", fmt(s["min"]))
        mc.add(name + "Max", fmt(s["max"]))


def small_value(x: float) -> str:
    return count(x) if float(x).is_integer() else per_lookup(x)


def summary_over_cells(mc: Macros, name: str, cells: list[dict]) -> None:
    meds = [c["median"] for c in cells if c and c.get("n")]
    mc.add(name + "CellMedianMin", ratio(min(meds)))
    mc.add(name + "CellMedianMedian", ratio(statistics.median(meds)))
    mc.add(name + "CellMedianMax", ratio(max(meds)))
    mc.add(name + "CellsAboveOne", count(sum(1 for v in meds if v > 1)))
    mc.add(name + "CellsBelowOne", count(sum(1 for v in meds if v < 1)))
    mc.add(name + "CellsMaxAtLeastOne", count(sum(1 for c in cells if c and c.get("n") and c["max"] >= 1)))
    mc.add(name + "CellsMinAtMostOne", count(sum(1 for c in cells if c and c.get("n") and c["min"] <= 1)))
    mc.add(name + "Cells", count(len(meds)))


def meta_macros(mc: Macros, s: dict) -> None:
    m = s["meta"]
    mc.add("QuickCommit", tt(m["commit"][:7]))
    mc.add("QuickRegexMatcherCommit", tt(m["regexmatcher_commit"][:9]))
    mc.add("QuickClangVersion", m["compiler"].split()[-1])
    mc.add("QuickTargetCpu", m["target_cpu"])
    mc.add("QuickGoVersion", m["go"])
    mc.add("QuickRustVersion", m["rust"])
    mc.add("QuickCpu", count(m["cpu"]))
    mc.add("QuickEpochs", count(m["epochs"]))
    mc.add("QuickRing", count(m["ring"]))
    mc.add("QuickAdvRing", count(m["adv_ring"]))
    mc.add("QuickBudgetS", count(m["budget_s"]))
    mc.add("QuickCampaigns", count(len(s["jobs"])))
    sizes = sorted({c["m"] for part in s["ablation"].values() for c in part["cells"]} |
                   {r["m"] for part in s["boundary"].values() for r in part["cells"]})
    for m_ in sizes:
        mc.add("QuickSize" + SIZE_WORD[m_], count(m_))
    mc.add("QuickShapes", count(len(Q.SHAPES)))
    mc.add("QuickAblVariants", count(len(VARIANTS)))
    mc.add("QuickBndCompetitors", count(len(COMPETITORS)))
    mc.add("QuickBndRustArms", count(len(RUST)))
    mc.add("QuickBndGoArms", count(len(GO)))
    mc.add("QuickBndCppArms", count(len(CPP)))
    mc.add("QuickProcesses", count(sum(j["processes"] for j in s["jobs"].values())))
    mc.add("QuickProcessesNotZeroExit", count(sum(len(j["rc_not_zero"]) for j in s["jobs"].values())))
    mc.add("QuickLongestCampaignS", fixed(max(j["wall_s"] for j in s["jobs"].values()), 0))
    mc.add("QuickTotalCampaignS", fixed(sum(j["wall_s"] for j in s["jobs"].values()), 0))
    for p, j in s["jobs"].items():
        w = "Quick" + PLAN_WORD[p]
        mc.add(w + "RoundsPlanned", count(j["rounds_planned"]))
        mc.add(w + "RoundsRun", count(j["rounds_run"]))
        mc.add(w + "WallS", fixed(j["wall_s"], 0))
        mc.add(w + "Processes", count(j["processes"]))
        mc.add(w + "ProcessesPerRound", count(j["processes_per_round"]))
        mc.add(w + "NotUsable", count(j["not_usable"]))


def adv_macros(mc: Macros, a: dict) -> None:
    mc.add("QuickAdvCells", count(len(a["cells"])))
    mc.add("QuickAdvTables", count(len({(c["family"], c["depth"], c["catch_all"]) for c in a["cells"]})))
    for fam, word in (("two-kinds", "TwoKinds"), ("four-kinds", "FourKinds")):
        depths = sorted({c["depth"] for c in a["cells"] if c["family"] == fam})
        mc.add(f"QuickAdv{word}MaxDepth", count(max(depths)))
        mc.add(f"QuickAdv{word}Depths", listing([count(d) for d in depths]))
    mc.add("QuickAdvBoundDecision", a["decision"])
    mc.add("QuickAdvProcessesUsable", count(a["processes_usable"]))
    mc.add("QuickAdvResumptionBound", count(RESUMPTION_BOUND))
    mc.add("QuickAdvMaxBacktracks", count(a["max_backtracks"]))
    mc.add("QuickAdvMaxEntries", count(a["max_entries"]))
    mc.add("QuickAdvMaxWalkedNodes", count(a["max_walked"]))
    mc.add("QuickAdvMaxDeepest", count(a["max_deepest"]))
    mc.add("QuickAdvMaxResumptions", count(a["max_resumptions"]))
    mc.add("QuickAdvMaxEntriesPerNode", count(a["max_entries_per_node"]))
    mc.add("QuickAdvMaxEntriesOverWalked", ratio(a["max_entries_over_walked"]))
    per = a["ns_per_entry"]
    mc.add("QuickAdvNsPerEntryMin", fixed(per["min"], 2))
    mc.add("QuickAdvNsPerEntryMedian", fixed(per["median"], 2))
    mc.add("QuickAdvNsPerEntryMax", fixed(per["max"], 2))
    for c in a["cells"]:
        w = "QuickAdv" + adv_word(c)
        mc.add(w + "Routes", count(c["routes"]))
        mc.add(w + "Entries", count(c["entries"]))
        mc.add(w + "WalkedNodes", count(c["walked_nodes"]))
        mc.add(w + "Pushed", count(c["pushed"]))
        mc.add(w + "Backtracks", count(c["popped"]))
        mc.add(w + "Deepest", count(c["deepest_stack"]))
        mc.add(w + "MaxResumptions", count(c["max_resumptions_per_node"]))
        mc.add(w + "Rounds", count(c["usable"]))
        trio(mc, w + "Ns", c.get("ns"), nanoseconds)
        mc.add(w + "NsPerEntry", fixed(c["ns_per_entry"], 2))
    for t in a["tables"]:
        w = "QuickAdv" + adv_word({**t, "catch_all": False, "query": "miss"})[:-4] + "MissOverLastHit"
        trio(mc, w, t["miss_over_last_hit"])
    summary_over_cells(mc, "QuickAdvMissOverLastHit", [t["miss_over_last_hit"] for t in a["tables"]])


def abl_macros(mc: Macros, s: dict) -> None:
    allc = s["ablation"]["small"]["cells"] + s["ablation"]["large"]["cells"]
    for c in allc:
        cw = cell_word(c["shape"], c["m"])
        for a in VARIANTS:
            trio(mc, f"QuickAbl{WORD[a]}{cw}", c["variants"][a])
        if "copy_vs_v2" in c:
            trio(mc, f"QuickAblCopyVsVtwo{cw}", c["copy_vs_v2"])
        for a, v in c["arms"].items():
            w = f"QuickAbl{WORD[a]}{cw}"
            mc.add(w + "Ns", nanoseconds(v["ns"]["median"]))
            mc.add(w + ("InstrNet" if v["instructions_net_of_null"] else "Instr"),
                   instructions(v["instructions"]["median"]))
            mc.add(w + "BranchMisses", per_lookup(v["branch_misses"]["median"]))
            mc.add(w + "Allocs", small_value(v["allocs"]["median"]))
    for a in VARIANTS:
        summary_over_cells(mc, f"QuickAbl{WORD[a]}", [c["variants"][a] for c in allc])
        # The static shape is answered by the exact-match table alone and never walks the trie.
        mc_static = [c["variants"][a] for c in allc if c["shape"] == "static"]
        mc_walk = [c["variants"][a] for c in allc if c["shape"] != "static"]
        summary_over_cells(mc, f"QuickAbl{WORD[a]}Static", mc_static)
        summary_over_cells(mc, f"QuickAbl{WORD[a]}NonStatic", mc_walk)
        mx = max(c["arms"][a]["allocs"]["max"] for c in allc)
        mc.add(f"QuickAbl{WORD[a]}AllocsMaxProcess", small_value(mx))
    summary_over_cells(mc, "QuickAblCopyVsVtwo", [c["copy_vs_v2"] for c in s["ablation"]["small"]["cells"]])
    mc.add("QuickAblCopyAllocsMaxProcess", small_value(max(c["arms"][COPY]["allocs"]["max"] for c in allc)))
    mc.add("QuickAblLeftOut", count(len(s["ablation"]["small"]["left_out"]) + len(s["ablation"]["large"]["left_out"])))
    for a, v in s["code"].items():
        mc.add(f"QuickCode{WORD.get(a, a.split('-')[-1].capitalize())}Lines", count(v["lines"]))
        mc.add(f"QuickCode{WORD.get(a, a.split('-')[-1].capitalize())}Functions", count(v["functions"]))


def bnd_macros(mc: Macros, s: dict) -> None:
    cells = s["boundary"]["ten"]["cells"] + s["boundary"]["hundred"]["cells"]
    for r in cells:
        cw = cell_word(r["shape"], r["m"])
        for t, v in r["capi"].items():
            name = f"QuickBnd{cw}CapiVs" + ("Fastest" if t == "fastest" else WORD[t])
            trio(mc, name, v)
            if t == "fastest":
                mc.add(name + "Arm", tt(v["arm"]))
        if r["net"].get("status") == "compared":
            trio(mc, f"QuickBnd{cw}Net", r["net"])
            mc.add(f"QuickBnd{cw}NetArm", tt(r["net"]["arm"]))
            trio(mc, f"QuickBnd{cw}RawVsNetArm", r["net"]["raw"])
        for t, v in r["goloop"].items():
            trio(mc, f"QuickBnd{cw}GoloopVs{WORD[t]}", v)
        for a, v in r["arms"].items():
            mc.add(f"QuickBnd{cw}{WORD[a]}Ns", nanoseconds(v["ns"]["median"]))
            if v["net_ns"]:
                mc.add(f"QuickBnd{cw}{WORD[a]}NetNs", nanoseconds(v["net_ns"]["median"]))
    summary_over_cells(mc, "QuickBndCapiVsFastest", [r["capi"].get("fastest") for r in cells])
    summary_over_cells(mc, "QuickBndNet", [r["net"] for r in cells if r["net"].get("status") == "compared"])
    summary_over_cells(mc, "QuickBndRawVsNetArm", [r["net"]["raw"] for r in cells if r["net"].get("status") == "compared"])
    for t in GO:
        summary_over_cells(mc, f"QuickBndGoloopVs{WORD[t]}", [r["goloop"].get(t) for r in cells])
    mc.add("QuickBndCells", count(len(cells)))
    mc.add("QuickBndNetNotCompared", count(sum(1 for r in cells if r["net"].get("status") != "compared")))
    mc.add("QuickBndNetLeftOutCells", count(sum(1 for r in cells if r["net_left_out"])))
    mc.add("QuickBndAbsentCells", count(sum(1 for r in cells if r["absent"])))
    mc.add("QuickBndFailingCells", count(sum(1 for r in cells if r["failing"])))


def macros(s: dict) -> Macros:
    mc = Macros()
    meta_macros(mc, s)
    adv_macros(mc, s["adversarial"])
    abl_macros(mc, s)
    a = s["aa"]
    mc.add("QuickAaRatio", ratio(a["median"]))
    mc.add("QuickAaMin", ratio(a["min"]))
    mc.add("QuickAaMax", ratio(a["max"]))
    mc.add("QuickAaPairs", count(a["n"]))
    mc.add("QuickAaCells", count(a["cells"]))
    bnd_macros(mc, s)
    return mc


# ------------------------------------------------------------------------------------------- tables

def span(name: str) -> str:
    return f"\\{name}Ratio{{}} [\\{name}Min, \\{name}Max]"


def nspan(name: str) -> str:
    return f"\\{name}{{}} [\\{name}Min, \\{name}Max]"


def shape_m(c: dict) -> str:
    return f"\\texttt{{{c['shape']}}} & {count(c['m'])}"


def tables(s: dict, mc_names: set[str]) -> dict[str, str]:
    def need(text: str) -> str:
        for n in re.findall(r"\\(Quick[A-Za-z]+)", text):
            if n not in mc_names:
                raise AnalysisError(f"a table names \\{n}, which is not a macro")
        return text

    out = {}
    a = s["adversarial"]
    rows = []
    for c in a["cells"]:
        w = "QuickAdv" + adv_word(c)
        rows.append(f"{FAMILY_TEXT[c['family']]} & {count(c['depth'])} & {'yes' if c['catch_all'] else 'no'} & "
                    f"{QUERY_TEXT[c['query']]} & \\{w}Entries & \\{w}WalkedNodes & \\{w}Backtracks & \\{w}Deepest & "
                    f"\\{w}MaxResumptions & {nspan(w + 'Ns')} & \\{w}NsPerEntry \\\\")
    out["adversarial.tex"] = need("\n".join(rows))
    rows = []
    for t in a["tables"]:
        w = "QuickAdv" + adv_word({**t, "catch_all": False, "query": "miss"})[:-4] + "MissOverLastHit"
        rows.append(f"{FAMILY_TEXT[t['family']]} & {count(t['depth'])} & {span(w)} \\\\")
    out["adversarial-miss.tex"] = need("\n".join(rows))
    rows = []
    for c in s["ablation"]["small"]["cells"] + s["ablation"]["large"]["cells"]:
        cw = cell_word(c["shape"], c["m"])
        cvv = span(f"QuickAblCopyVsVtwo{cw}") if "copy_vs_v2" in c else "--"
        rows.append(f"{shape_m(c)} & {cvv} & " + " & ".join(span(f"QuickAbl{WORD[v]}{cw}") for v in VARIANTS) + " \\\\")
    out["ablation.tex"] = need("\n".join(rows))
    rows = []
    for c in s["ablation"]["small"]["cells"] + s["ablation"]["large"]["cells"]:
        cw = cell_word(c["shape"], c["m"])
        suf = "InstrNet" if c["m"] != 10000 else "Instr"
        cells = []
        for v in (COPY,) + VARIANTS:
            cells.append(f"\\QuickAbl{WORD[v]}{cw}{suf} & \\QuickAbl{WORD[v]}{cw}BranchMisses & "
                         f"\\QuickAbl{WORD[v]}{cw}Allocs")
        rows.append(f"{shape_m(c)} & " + " & ".join(cells) + " \\\\")
    out["ablation-counters.tex"] = need("\n".join(rows))
    rows = []
    for a_ in (V2, COPY) + VARIANTS:
        w = WORD[a_]
        same = "--" if a_ == V2 else ("yes" if s["code"][a_]["identical_to_reference"] else "no")
        rows.append(f"{PAPER_NAME[a_]} & \\QuickCode{w}Functions & \\QuickCode{w}Lines & {same} \\\\")
    out["code-size.tex"] = need("\n".join(rows))
    rows, rows_go = [], []
    for r in s["boundary"]["ten"]["cells"] + s["boundary"]["hundred"]["cells"]:
        cw = cell_word(r["shape"], r["m"])
        capi = (f"{span(f'QuickBnd{cw}CapiVsFastest')} (\\QuickBnd{cw}CapiVsFastestArm)"
                if "fastest" in r["capi"] else "--")
        if r["net"].get("status") == "compared":
            net = f"{span(f'QuickBnd{cw}Net')} & {span(f'QuickBnd{cw}RawVsNetArm')} & \\QuickBnd{cw}NetArm"
        else:
            net = "not compared & -- & --"
        rows.append(f"{shape_m(r)} & {capi} & {net} \\\\")
        rows_go.append(f"{shape_m(r)} & " + " & ".join(
            span(f"QuickBnd{cw}GoloopVs{WORD[t]}") if t in r["goloop"] else "--" for t in GO) + " \\\\")
    out["boundary.tex"] = need("\n".join(rows))
    out["boundary-goloop.tex"] = need("\n".join(rows_go))
    out["aa.tex"] = need("Linux & \\QuickAaCells & \\QuickAblSmallRoundsRun & \\QuickAaPairs & "
                         "\\QuickAaRatio{} [\\QuickAaMin, \\QuickAaMax] \\\\")
    return {k: HEAD + v + "\n" for k, v in out.items()}


# ------------------------------------------------------------------------------------------- figures

def figures(s: dict, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out.mkdir(parents=True, exist_ok=True)
    meta = {"CreationDate": None, "ModDate": None}
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8), sharey=True)
    for ax, fam in zip(axes, ("two-kinds", "four-kinds")):
        for (q, ca), (label, marker) in {("miss", False): ("miss", "o"), ("last-hit", False): ("last hit", "s"),
                                         ("miss", True): ("miss, catch-all", "^")}.items():
            cs = sorted((c for c in s["adversarial"]["cells"] if c["family"] == fam and c["query"] == q
                         and c["catch_all"] == ca), key=lambda c: c["depth"])
            x = [c["depth"] for c in cs]
            y = [c["ns"]["median"] for c in cs]
            err = [[c["ns"]["median"] - c["ns"]["min"] for c in cs], [c["ns"]["max"] - c["ns"]["median"] for c in cs]]
            ax.errorbar(x, y, yerr=err, marker=marker, ms=4, lw=1, capsize=2, label=label)
        ax.set_yscale("log")
        ax.set_title(FAMILY_TEXT[fam] + " per node", fontsize=9)
        ax.set_xlabel("depth (segments)", fontsize=8)
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("ns per lookup (median over rounds)", fontsize=8)
    axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(out / "adversarial-depth.pdf", metadata=meta)
    plt.close(fig)

    cells = s["ablation"]["small"]["cells"] + s["ablation"]["large"]["cells"]
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    labels = [f"{c['shape']} {c['m']}" for c in cells]
    for i, v in enumerate(VARIANTS):
        xs = [k + (i - 1.5) * 0.18 for k in range(len(cells))]
        ser = [c["variants"][v] for c in cells]
        ax.errorbar(xs, [x["median"] for x in ser], yerr=[[x["median"] - x["min"] for x in ser],
                                                          [x["max"] - x["median"] for x in ser]],
                    fmt="o", ms=3, lw=0.8, capsize=1.5, label=PAPER_NAME[v])
    ax.axhline(1.0, color="0.5", lw=0.6)
    ax.set_xticks(range(len(cells)))
    ax.set_xticklabels(labels, rotation=70, fontsize=6)
    ax.set_ylabel("variant / renamed copy (ns per lookup)", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.legend(fontsize=7, frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(out / "ablation-ratio.pdf", metadata=meta)
    plt.close(fig)


# ------------------------------------------------------------------------------------------- report

def fmt(s: dict | None) -> str:
    if not s or not s.get("n"):
        return "none"
    return f"{s['median']:.4f} [{s['min']:.4f}, {s['max']:.4f}] (n {s['n']})"


def report(s: dict) -> str:
    m = s["meta"]
    lines = [(f"P2 quick campaigns at {m['commit'][:7]} (units' code {m['code_commit'][:7]}; files between them: "
              f"{m['commit_gap']}), {m['compiler']}, {m['target_cpu']}, Go {m['go']}, Rust {m['rust']}, "
              f"CPU {m['cpu']}, {m['epochs']} epochs, ring {m['ring']} (adversarial {m['adv_ring']})."), ""]
    for p, j in s["jobs"].items():
        lines.append(f"{p}: rounds {j['rounds_run']} of {j['rounds_planned']}, cut {j['cut']}, {j['wall_s']} s, "
                     f"{j['processes']} processes, {j['not_usable']} not usable, exit not 0: {j['rc_not_zero']}")
    a = s["adversarial"]
    lines += ["", (f"(a) adversarial: the written bound {a['decision']}; largest backtracks per query "
                   f"{a['max_backtracks']} ({', '.join(a['max_backtracks_cells'])}); "
                   f"ns per entry {fmt(a['ns_per_entry'])}")]
    for c in a["cells"]:
        lines.append(f"  {c['cell']:<26} entries {c['entries']:>3} walked {c['walked_nodes']:>3} pushed {c['pushed']:>3} "
                     f"popped {c['popped']:>3} deepest {c['deepest_stack']:>2} ns {fmt(c.get('ns'))}")
    for t in a["tables"]:
        lines.append(f"  {t['family']} {t['depth']}: miss / last hit {fmt(t['miss_over_last_hit'])}")
    lines += ["", "(b) ablations: variant / copy per cell (median [min, max] over rounds)"]
    for c in s["ablation"]["small"]["cells"] + s["ablation"]["large"]["cells"]:
        cv = f" copy/v2 {fmt(c['copy_vs_v2'])}" if "copy_vs_v2" in c else ""
        lines.append(f"  {c['shape']} {c['m']}:{cv}")
        for v in VARIANTS:
            ar = c["arms"][v]
            lines.append(f"    {v:<30} {fmt(c['variants'][v])} instr {ar['instructions']['median']:.1f} "
                         f"allocs {ar['allocs']['median']:g}")
    lines.append(f"  left out: {s['ablation']['small']['left_out'] + s['ablation']['large']['left_out']}")
    lines.append("  code: " + "; ".join(f"{k} {v['functions']} functions {v['lines']} lines" for k, v in s["code"].items()))
    lines += ["", f"A/A (v2 twice, Linux): {fmt(s['aa'])} over {s['aa']['cells']} cells", "", "(b) boundary"]
    for r in s["boundary"]["ten"]["cells"] + s["boundary"]["hundred"]["cells"]:
        f_ = r["capi"].get("fastest")
        lines.append(f"  {r['shape']} {r['m']}: capi/fastest Rust ({f_ and f_['arm']}) {fmt(f_)}; net "
                     + (f"v2/{r['net']['arm']} {fmt(r['net'])} raw {fmt(r['net']['raw'])}"
                        if r["net"].get("status") == "compared" else f"not compared: {r['net']['why']}"))
        lines.append("    goloop: " + "; ".join(f"{t} {fmt(v)}" for t, v in r["goloop"].items()))
        for k in ("absent", "failing", "net_left_out"):
            if r[k]:
                lines.append(f"    {k}: {r[k]}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=REPO / "results" / "quick")
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args(argv)
    s = analyse(a.folders)
    mc = macros(s)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "summary.json").write_text(json.dumps(s, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    (a.out / "macros.tex").write_text(HEAD + mc.text(), encoding="utf-8", newline="\n")
    (a.out / "report.txt").write_text(report(s), encoding="utf-8", newline="\n")
    (a.out / "tables").mkdir(exist_ok=True)
    for name, text in tables(s, mc.names).items():
        (a.out / "tables" / name).write_text(text, encoding="utf-8", newline="\n")
    if not a.no_figures:
        figures(s, a.out / "figures")
    print(report(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
