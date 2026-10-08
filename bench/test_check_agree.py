#!/usr/bin/env python3
"""Tests of check_agree.py: a declared disagreement passes only in its declared kind.

    python bench/test_check_agree.py      (exit 0 when every check passes)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_agree import cell_passes, load_semantics, row_passes  # noqa: E402

failures = 0


def expect(name: str, ok: bool) -> None:
    global failures
    print(("ok: " if ok else "FAIL: ") + name)
    failures += not ok


def agree(arm: str, shape: str, ids: int, ids_404: int, values: int) -> dict:
    return {"arm": arm, "shape": shape, "m": 10, "status": "disagrees", "wrong": ids + values,
            "id_mismatches": ids, "id_mismatches_404": ids_404, "capture_mismatches": values}


def main() -> int:
    s = load_semantics()
    expect("every committed entry has a kind", all(e["kind"] in ("values", "404") for sh in s.values() for e in sh.values()))
    expect("boost-url, values only: passes", row_passes(agree("boost-url", "mixed-overlap", 0, 0, 387), s))
    expect("boost-url, one wrong route: fails", not row_passes(agree("boost-url", "mixed-overlap", 1, 0, 386), s))
    expect("r3, every wrong answer 404: passes", row_passes(agree("r3", "mixed-overlap", 387, 387, 0), s))
    expect("r3, one wrong route that is not 404: fails", not row_passes(agree("r3", "mixed-overlap", 387, 386, 0), s))
    expect("r3, a wrong value: fails", not row_passes(agree("r3", "mixed-overlap", 386, 386, 1), s))
    expect("gin on a shape not declared: fails", not row_passes(agree("gin", "rest", 5, 5, 0), s))
    old = {"arm": "gin", "shape": "mixed-overlap", "status": "disagrees", "wrong": 97}
    expect("a row without the counts: fails", not row_passes(old, s))
    cell = dict(agree("uwebsockets", "wild", 0, 0, 4096), agrees=False)
    expect("a cell of the declared kind: passes", cell_passes(cell, s))
    expect("a cell of another kind: fails", not cell_passes(dict(cell, id_mismatches=3, id_mismatches_404=3), s))
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "semantics.json"
        bad.write_text(json.dumps({"gin": {"mixed-overlap": "a reason without a kind"}}), encoding="utf-8")
        try:
            load_semantics(bad)
            expect("an entry without a kind is refused", False)
        except ValueError:
            expect("an entry without a kind is refused", True)
    print(f"{failures} failed" if failures else "all checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
