#!/usr/bin/env python3
"""The request sets of a round-robin plan's seed pair on either system of the laptop, added beside round 3's (the
floor rerun, design/review-runs/floor-rerun.md: the pair (127, 227) of t3/plans/rr2-*.json). Untimed: nothing here
reads a time, a rate or a latency of any program.

    sets.py PLAN BIN OUT

PLAN is a committed plan (t3/plans/rr2-L.json or rr2-W.json); its shapes, sizes, pairs and data_root name the cells.
BIN is the bring-up's e2e_requests (P2R3/build-3ff814e50/e2e_requests, .exe on Windows), built from
t3/e2e_requests.cpp, which no commit since has changed (t3/jobs/probe.py's COMPILED). Steps, in order; the first that
fails stops the job (exit 1) and OUT/steps.txt says which; OUT/sets-summary.json holds each cell's outcome:
  make     t3/make_requests.py --pair-list into OUT/sets: the plan's cells, all.txt at every size, as the desktop
           made them for t3/requests-manifest.tsv and as round 3's pair (111, 211) has them; OUT/make.log;
  check    every generated row is a row of t3/requests-manifest.tsv, and each of the plan's cells was generated once;
  install  each cell copied into DATA_ROOT/<shape>/m<m>/t<table seed>/ and its row added to DATA_ROOT/manifest.tsv,
           which t3/p2run.py's verify_sets reads. Nothing is overwritten: a cell already there must hash to its
           committed row and is left as it is, a row already there for the cell must be the committed row, else the
           job stops before it changes anything. DATA_ROOT and its manifest.tsv must exist (round 3's bring-up made
           them, with round 3's 160 cells);
  recheck  every file of the plan's cells in DATA_ROOT hashed against its committed row (routes.txt, ring.txt,
           ring.expect, all.txt, all.expect), then DATA_ROOT/manifest.tsv against the committed manifest with
           --complete (every committed cell, round 3's and the new pair's).
Cross-platform identity: the committed rows were made on the desktop (Windows); this job makes the sets again on each
system of the laptop and checks them against those rows, so a set that differs on a system stops its job here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

T3 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(T3))
import make_requests  # noqa: E402

MANIFEST = T3 / "requests-manifest.tsv"
FILES = {"routes.txt": "routes_sha256", "ring.txt": "ring_sha256", "ring.expect": "ring_expect_sha256",
         "all.txt": "all_sha256", "all.expect": "all_expect_sha256"}  # a digest of "-": the file is not made


class SetsError(Exception):
    """A refusal: the step stops the job."""


def read_manifest(path: Path) -> tuple[str, dict[tuple[str, int, int], str]]:
    """(header, {(shape, m, table seed): row}) of a manifest.tsv; a cell twice is refused."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise SetsError(f"{path} is empty")
    keys, rows = lines[0].split("\t"), {}
    for line in lines[1:]:
        r = dict(zip(keys, line.split("\t")))
        cell = (r["shape"], int(r["m"]), int(r["table_seed"]))
        if cell in rows:
            raise SetsError(f"{path}: {cell} twice")
        rows[cell] = line
    return lines[0], rows


def cells_of(plan: dict) -> list[tuple[str, int, int]]:
    return [(shape, m, table) for shape in plan["shapes"] for m in plan["sizes"] for table, _ in plan["pairs"]]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cell_problems(folder: Path, header: str, row: str) -> list[str]:
    """Each file of a cell folder whose sha256 is not its row's (or that is there when the row says "-")."""
    r = dict(zip(header.split("\t"), row.split("\t")))
    out = []
    for name, key in FILES.items():
        f = folder / name
        if r[key] == "-":
            if f.exists():
                out.append(f"{f}: there, but the manifest has no digest for it")
        elif not f.is_file():
            out.append(f"{f}: missing")
        elif sha256(f) != r[key]:
            out.append(f"{f}: sha256 is not the manifest's")
    return out


def check(generated: Path, committed: Path, cells: list) -> None:
    """Every generated row is a committed row, and each cell was generated once."""
    g_header, g_rows = read_manifest(generated)
    c_header, c_rows = read_manifest(committed)
    if g_header != c_header:
        raise SetsError("the generated manifest's columns are not the committed manifest's")
    if sorted(g_rows) != sorted(cells):
        raise SetsError(f"generated cells {sorted(g_rows)}, the plan's are {sorted(cells)}")
    wrong = [cell for cell, row in g_rows.items() if c_rows.get(cell) != row]
    if wrong:
        raise SetsError(f"generated rows that are not the committed rows: {wrong}")


def install(generated_dir: Path, data_root: Path, committed: Path, cells: list) -> dict:
    """Copy each cell into data_root and add its row to data_root/manifest.tsv (see the docstring); returns each
    cell's outcome. Every refusal comes before the first change."""
    c_header, c_rows = read_manifest(committed)
    target = data_root / "manifest.tsv"
    if not target.is_file():
        raise SetsError(f"{target} is missing: round 3's bring-up makes it")
    t_header, t_rows = read_manifest(target)
    if t_header != c_header:
        raise SetsError(f"{target}'s columns are not the committed manifest's")
    plan: dict = {}
    for cell in cells:
        shape, m, table = cell
        dst = make_requests.cell_dir(data_root, shape, m, table)
        if cell in t_rows and t_rows[cell] != c_rows[cell]:
            raise SetsError(f"{target} has another row for {cell}")
        if dst.exists():
            problems = cell_problems(dst, c_header, c_rows[cell])
            if problems:
                raise SetsError(f"{dst} is there and differs from the committed row: {problems}")
        plan[cell] = {"cell": "present" if dst.exists() else "copied",
                      "row": "present" if cell in t_rows else "added"}
    for cell, what in plan.items():
        if what["cell"] == "copied":
            dst = make_requests.cell_dir(data_root, *cell)
            part = dst.with_name(dst.name + ".part")
            if part.exists():
                shutil.rmtree(part)
            shutil.copytree(make_requests.cell_dir(generated_dir, *cell), part)
            os.replace(part, dst)
    added = [c_rows[cell] for cell, what in plan.items() if what["row"] == "added"]
    if added:
        text = target.read_text(encoding="utf-8")
        part = target.with_name("manifest.tsv.part")
        part.write_text(text + ("" if text.endswith("\n") else "\n") + "\n".join(added) + "\n",
                        encoding="utf-8", newline="\n")
        os.replace(part, target)
    return {"/".join(map(str, cell)): what for cell, what in plan.items()}


def recheck(data_root: Path, committed: Path, cells: list) -> None:
    c_header, c_rows = read_manifest(committed)
    problems = [p for cell in cells for p in cell_problems(make_requests.cell_dir(data_root, *cell), c_header, c_rows[cell])]
    if problems:
        raise SetsError(f"installed cells differ from the committed rows: {problems}")
    if make_requests.verify(data_root, committed, complete=True) != 0:
        raise SetsError(f"{data_root}/manifest.tsv is not the committed manifest, every cell")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", type=Path)
    ap.add_argument("bin", type=Path)
    ap.add_argument("out", type=Path)
    a = ap.parse_args(argv)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    steps, summary = out / "steps.txt", {"plan": a.plan.name, "bin": str(a.bin)}

    def step(name: str, code: int, detail: str = "") -> None:
        with open(steps, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{name} {code} {detail}\n")
        print(f"== {name} {'done' if code == 0 else 'STOPPED'} {detail}", flush=True)
        summary.setdefault("steps", []).append({"step": name, "exit": code, "detail": detail})
        (out / "sets-summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")

    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    cells, data_root, generated = cells_of(plan), Path(plan["data_root"]), out / "sets"
    pair_list = ",".join(f"{t}:{r}" for t, r in plan["pairs"])
    cmd = [sys.executable, str(T3 / "make_requests.py"), "--bin", str(a.bin), "--out", str(generated),
           "--shapes", ",".join(plan["shapes"]), "--sizes", ",".join(map(str, plan["sizes"])), "--pair-list", pair_list]
    with open(out / "make.log", "w", encoding="utf-8") as log:
        code = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
    if code != 0:
        step("make", 1, f"make_requests.py exit {code}; see make.log")
        return 1
    step("make", 0, f"{len(cells)} cells, pairs {pair_list}")
    try:
        check(generated / "manifest.tsv", MANIFEST, cells)
        step("check", 0, f"{len(cells)} rows are committed rows")
        summary["cells"] = install(generated, data_root, MANIFEST, cells)
        step("install", 0, f"into {data_root}")
        recheck(data_root, MANIFEST, cells)
        step("recheck", 0, f"{data_root}/manifest.tsv holds every committed cell")
    except (SetsError, OSError, KeyError, ValueError) as e:
        step(next(s for s in ("check", "install", "recheck") if s not in {x["step"] for x in summary["steps"]}), 1,
             f"{type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
