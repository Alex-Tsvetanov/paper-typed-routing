#!/usr/bin/env python3
"""H7's MSVC costs on the laptop's Windows, for round 3's macros: the job's tables.jsonl with its inputs.

    python t3/ct_msvc_results.py --archive ARCHIVE --job DIR [--out results/round3/ct-msvc.json]

ARCHIVE is the job's archive (p2r3-ct-msvc-w.tar.gz, its sha256 file beside it) and DIR the folder it unpacks to, named
by the job. It refuses (exit 2, nothing written) unless the archive's sha256 is the one beside it, the job's
steps.txt says the clean and sources steps passed and bench/ct_msvc.py exited 0, and out/ct/ct/tables.jsonl holds
exactly the tables of bench/ct_msvc.py's TABLES, once each, each compiled at the harness budget, with one compiler.
It writes the rows as tables.jsonl holds them, with the archive's and the file's sha256 and the job's commit;
t3/rr_macros.py turns them into macros. The costs are compiler measurements of code that is never executed (Alex,
2026-11-03: no D5 record needed; t3/coverage.json).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "bench"))
import ct_msvc  # noqa: E402

TABLES_FILE = "out/ct/ct/tables.jsonl"
STEPS_OK = ["clean: ok", "sources: ok", "ct: exit 0"]


class ResultsError(Exception):
    """A refusal: nothing is written."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(archive: Path, job: Path) -> dict:
    side = archive.with_name(archive.name + ".sha256")
    want = side.read_text(encoding="utf-8").split()[0] if side.is_file() else None
    got = sha256(archive)
    if got != want:
        raise ResultsError(f"{archive.name}: sha256 {got} is not the one beside it ({want})")
    steps = (job / "out" / "ct" / "steps.txt").read_text(encoding="utf-8").splitlines()
    if steps != STEPS_OK:
        raise ResultsError(f"steps.txt says {steps}, not {STEPS_OK}")
    path = job / TABLES_FILE
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("{")]
    names = [r["table"] for r in rows]
    if sorted(names) != sorted(ct_msvc.TABLES) or len(set(names)) != len(names):
        raise ResultsError(f"tables.jsonl holds {sorted(names)}, not bench/ct_msvc.py's TABLES once each")
    if any(r.get("harness_compile") != "ok" for r in rows) or len({r["compiler"] for r in rows}) != 1:
        raise ResultsError("a table did not compile at the harness budget, or the compilers differ")
    spec = json.loads((job / "spec.json").read_text(encoding="utf-8"))
    return {"_note": "H7's MSVC costs on the laptop's Windows (t3/jobs/ctmsvc.py, bench/ct_msvc.py); "
                     "written by t3/ct_msvc_results.py; macros by t3/rr_macros.py",
            "inputs": {"job": job.name, "commit": spec["commit"], "archive": archive.name, "archive_sha256": got,
                       "file": TABLES_FILE, "sha256": sha256(path)},
            "tables": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "round3" / "ct-msvc.json")
    a = ap.parse_args(argv)
    try:
        result = build(a.archive, a.job)
    except (ResultsError, OSError, KeyError, ValueError) as e:
        print(f"ct_msvc_results: refused: {e}", file=sys.stderr)
        return 2
    a.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
