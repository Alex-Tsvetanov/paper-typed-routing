#!/usr/bin/env python3
"""Judge rbench's agreement rows, or its cells, against the declared path semantics
(semantics.json).

    check_agree.py AGREE_JSONL [--semantics semantics.json]
    check_agree.py --cells CELLS_JSONL [--semantics semantics.json]

An agreement row passes if it agrees, if the arm refused the table, or if it disagrees on a
shape where semantics.json declares that the arm answers differently, and only in the kind
declared: "values" (the right route on every query, other captured values on some) or "404"
(no route on every query it gets wrong, and the right values wherever the route is right).
The kind is read from the row's counts (id_mismatches, id_mismatches_404,
capture_mismatches); a row without them does not pass. A cell passes if it ended ok, refused,
or out of the time budget ("timeout", or "skipped" by the stopping rule), or if it disagrees
as declared; at every size, not only the agreement test's. Any other row fails: an error, a
crash, a disagreement nobody declared, or one of another kind. Exits 1 if a row fails, and
prints them. Used by sanitizer_record.py and by run_grid.sh (the grid's
agreement and cells exit codes).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


KINDS = ("values", "404")
Semantics = dict[str, dict[str, dict]]


def load_semantics(path: Path | None = None) -> Semantics:
    data = json.loads((path or HERE / "semantics.json").read_text(encoding="utf-8"))
    out = {arm: shapes for arm, shapes in data.items() if arm != "about"}
    for arm, shapes in out.items():
        for shape, entry in shapes.items():
            if not isinstance(entry, dict) or entry.get("kind") not in KINDS or not entry.get("why"):
                raise ValueError(f"semantics.json: {arm} {shape} needs a kind ({' or '.join(KINDS)}) and a why")
    return out


def declared(semantics: Semantics, arm: str, shape: str) -> bool:
    return shape in semantics.get(arm, {})


def of_kind(kind: str, row: dict) -> bool:
    """Whether a disagreeing row's wrong answers are all of KIND."""
    ids, ids_404, values = (row.get(k) for k in ("id_mismatches", "id_mismatches_404", "capture_mismatches"))
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (ids, ids_404, values)):
        return False
    if kind == "values":
        return ids == 0
    return kind == "404" and values == 0 and ids_404 == ids


def fits(semantics: Semantics, row: dict) -> bool:
    """A disagreement declared for the row's arm and shape, and of the declared kind."""
    entry = semantics.get(row.get("arm", ""), {}).get(row.get("shape", ""))
    return entry is not None and of_kind(entry["kind"], row)


def row_passes(row: dict, semantics: Semantics) -> bool:
    status = row.get("status")
    if status in ("agrees", "refused"):
        return True
    return status == "disagrees" and fits(semantics, row)


def cell_passes(row: dict, semantics: Semantics) -> bool:
    status = row.get("status")
    if status in ("ok", "refused", "timeout", "skipped"):
        return status != "ok" or bool(row.get("agrees", True))
    return status == "disagrees" and fits(semantics, row)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agree", type=Path, nargs="?")
    ap.add_argument("--cells", type=Path)
    ap.add_argument("--semantics", type=Path, default=HERE / "semantics.json")
    args = ap.parse_args()
    semantics = load_semantics(args.semantics)
    path = args.cells or args.agree
    if path is None:
        ap.error("an agreement file or --cells is required")
    judge = cell_passes if args.cells else row_passes
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bad = [r for r in rows if not judge(r, semantics)]
    for r in bad:
        print(f"{r.get('arm')} {r.get('shape')} m={r.get('m')} seed={r.get('table_seed')}: {r.get('status')} "
              f"{r.get('reason') or r.get('first_wrong') or ''}", file=sys.stderr)
    if not rows:
        print("no rows in " + str(path), file=sys.stderr)
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
