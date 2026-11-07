"""Writes, or checks, the expanded plans of P2's quick runs (quick-plan.md) in bench/quick/plans/.

    quick_plans.py            write every plan
    quick_plans.py --check    write nothing; exit 1 if a plan on disk differs (CRLF read as LF)
    quick_plans.py --sha      print each plan's sha256 (the value its laptop job pins with --quick)

A plan is one JSON header line and one line per process, in run order: every round runs every cell once,
in an order shuffled again for each round from the plan's order seed (quick_common.order_seed), so the
sha256 of the file pins the rows, their order and their arguments. The runner never reshuffles.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quick_common as qc  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sha", action="store_true")
    a = ap.parse_args(argv)
    bad = 0
    qc.PLANS_DIR.mkdir(parents=True, exist_ok=True)
    for name in qc.PLANS:
        path = qc.PLANS_DIR / f"{name}.jsonl"
        text = qc.plan_text(name)
        if a.check:
            same = path.is_file() and path.read_bytes().replace(b"\r\n", b"\n") == text.encode("utf-8")
            bad += 0 if same else 1
            print(f"quick_plans: {path.name} {'matches' if same else 'DIFFERS from'} quick_common.py")
        elif a.sha:
            print(f"{name} {qc.file_sha256(path)}")
        else:
            path.write_bytes(text.encode("utf-8"))
            print(f"quick_plans: wrote {path.name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
