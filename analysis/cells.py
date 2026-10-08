"""The cells of a round-2 run as the hypotheses judge them (hypotheses-round2.md; shared by every
analysis script).

A cell is a (shape, size). In a cell, each arm has one row per process, keyed by its (table
seed, ring seed) pair. An arm takes part in a cell only if every one of its processes ended ok
and agreed with the ring on every query: a process whose agreement pass stopped at its time
budget (verified_all false) counts only if a separate check of all its queries agreed
(tools/verify_unverified.py, given to load()). The other arms are sorted out here, never
dropped in silence:
- absent: every process refused the table ("refused" or "refused at insert"), or disagreed as
  bench/semantics.json declares for that arm and shape ("incomparable"), or ran out of the time
  budget (the first process "timeout", the others "skipped"). Printed with the reason. A
  declared disagreement must also be of the declared kind in every process (check_agree.fits).
- a failure of the cell: an arm that is ok in some processes and not in others, an arm with a
  process not verified on every query, an arm whose seed pairs differ from RegexMatcher v2's, an
  error or crash, or a disagreement nobody declared; and, when the design's pairs are given, a
  v2 whose pairs are not exactly those. The cell cannot pass then.

The arms of round 2 (hypotheses-round2.md, section 3.1): regexmatcher-v2, the arm of H1 to H4;
regexmatcher-v2-ct, the compile-time table (H7); the sixteen competitors; the reference arms
(regexmatcher-v1, radix, hash, std-regex), never competitors; the two null arms (null, and
null-no405 without a 405 of its own); and the ablation arm regexmatcher-v2-r1, exploratory,
which decides nothing.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bench"))
from check_agree import fits, load_semantics  # noqa: E402

V2 = "regexmatcher-v2"            # H1 to H4
CT = "regexmatcher-v2-ct"         # H7, against V2
ABLATION = "regexmatcher-v2-r1"   # exploratory
V1 = "regexmatcher-v1"            # reference, and H6's reference arm
NULL = "null"                     # the loop null of the arms with a 405 of their own (v2 among them)
NULL_NO405 = "null-no405"         # the loop null of the arms the harness's 405 rule applies to
NULLS = frozenset({NULL, NULL_NO405})
COMPETITORS = frozenset({
    # round 1's eleven
    "crow", "drogon", "oatpp", "pistache", "boost-url", "r3", "matchit", "httprouter", "gin", "nethttp",
    "actix-router",
    # added in round 2
    "uwebsockets", "glaze", "chi", "path-tree", "cpp-httplib"})
REFERENCE = frozenset({V1, "radix", "hash", "std-regex"})
H1_SHAPES = ["static", "param-last", "param-first", "rest", "wild", "mixed-disjoint", "mixed-overlap"]
H1_SIZES = [10, 100, 1000, 10000, 100000]
H7_SIZES = [10, 100, 1000]
R = 16


def design_pairs(r: int = R) -> list[tuple[int, int]]:
    """The seed pairs of processes 1 .. r (hypotheses-round2.md, section 4): pair k is
    (110 + k, 210 + k), so the sixteen pairs share no table seed and no ring seed."""
    return [(110 + k, 210 + k) for k in range(1, r + 1)]


def pair(r: dict) -> tuple:
    return (r.get("table_seed"), r.get("ring_seed"))


def process_key(r: dict) -> tuple:
    return (r["arm"], r["shape"], int(r["m"]), r.get("table_seed"), r.get("ring_seed"))


def load(run: Path, verified: Path | None = None) -> dict[tuple[str, int], dict[str, list[dict]]]:
    """The cells of RUN/cells.jsonl. With VERIFIED (tools/verify_unverified.py's output), a
    process whose agreement pass stopped at its budget and whose separate check agreed on
    every query of the same table and ring is marked verified_all, with verified_by."""
    checked = set()
    if verified is not None:
        for line in verified.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                if c.get("agrees_all") is True and c.get("digests_match") is True:
                    checked.add(process_key(c))
    cells: dict[tuple[str, int], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for line in (run / "cells.jsonl").read_text(encoding="utf-8").splitlines():
        if line.startswith("{"):
            r = json.loads(line)
            if r.get("verified_all") is False and process_key(r) in checked:
                r["verified_all"] = True
                r["verified_by"] = verified.name
            cells[(r["shape"], int(r["m"]))][r["arm"]].append(r)
    return cells


def verified_all(r: dict) -> bool:
    return r.get("verified_all") is True


def usable(r: dict) -> bool:
    return r.get("status") == "ok" and bool(r.get("agrees", False)) and verified_all(r)


@dataclass
class Sorted:
    """One cell's arms, sorted out."""
    v2: list[dict] | None = None             # RegexMatcher v2's processes, if every one is usable
    included: dict[str, list[dict]] = field(default_factory=dict)
    absent: dict[str, str] = field(default_factory=dict)      # arm: why
    failures: list[str] = field(default_factory=list)          # why the cell cannot pass


def classify(arm: str, shape: str, rows: list[dict], semantics: dict) -> tuple[str, str]:
    """("ok" | "absent" | "failure", why) for one arm's processes in a cell."""
    ok = [r for r in rows if usable(r)]
    if rows and len(ok) == len(rows):
        return "ok", ""
    if not rows:
        return "failure", f"{arm} did not run"
    unverified = [r for r in rows if r.get("status") == "ok" and r.get("agrees") and not verified_all(r)]
    if unverified:
        return "failure", f"{arm}: {len(unverified)} of {len(rows)} processes not verified on every query"
    if ok:
        return "failure", f"{arm} is ok in {len(ok)} of {len(rows)} processes"
    statuses = {r.get("status") for r in rows}
    if statuses <= {"refused"}:
        return "absent", "refused: " + (rows[0].get("reason") or "")
    if statuses <= {"timeout", "skipped"}:
        return "absent", "exceeds budget"
    if statuses <= {"disagrees"} and all(fits(semantics, r) for r in rows):
        n = sorted({int(r.get("answers_differ") or 0) for r in rows})
        span = f"{n[0]:,}" if n[0] == n[-1] else f"{n[0]:,} to {n[-1]:,}"
        return "absent", f"incomparable: {span} of {int(rows[0].get('ring_size', 4096)):,} answers differ"
    return "failure", f"{arm}: {', '.join(sorted(str(s) for s in statuses))}" + (
        " (a disagreement not declared in bench/semantics.json, or not of its declared kind)"
        if "disagrees" in statuses else "")


def sort_cell(arms: dict[str, list[dict]], shape: str, semantics: dict | None = None, v2: str = V2,
              expected_pairs: list[tuple] | None = None) -> Sorted:
    """The cell's arms: v2's processes, the competitors that take part, those absent and why,
    and the failures. expected_pairs: the design's seed pairs, which v2's must equal."""
    semantics = semantics if semantics is not None else load_semantics()
    out = Sorted()
    v2_rows = arms.get(v2, [])
    kind, why = classify(v2, shape, v2_rows, semantics)
    if kind == "ok":
        out.v2 = v2_rows
    else:
        out.failures.append(why if kind == "failure" else f"{v2} {why}")
    pairs = [pair(r) for r in v2_rows]
    if expected_pairs is not None and v2_rows and sorted(pairs) != sorted(expected_pairs):
        out.failures.append(f"{v2}'s seed pairs are not the design's ({len(pairs)} processes, "
                            f"{len(set(pairs))} distinct pairs, {len(expected_pairs)} expected)")
    for arm in sorted(a for a in arms if a in COMPETITORS):
        kind, why = classify(arm, shape, arms[arm], semantics)
        if kind == "ok":
            if sorted(pair(r) for r in arms[arm]) != sorted(pairs):
                out.failures.append(f"{arm}'s seed pairs differ from {v2}'s")
                continue
            out.included[arm] = arms[arm]
        elif kind == "absent":
            out.absent[arm] = why
        else:
            out.failures.append(why)
    return out


def cut(rows: list[dict]) -> bool:
    """Whether a timed pass of any of these processes ran on a prefix of its ring only (a slow
    arm's passes are cut to fit 0.25 s, bench/core/runner.hpp; lookups_per_pass says how long)."""
    return any(isinstance(r.get("lookups_per_pass"), (int, float))
               and r["lookups_per_pass"] < int(r.get("ring_size") or 4096) for r in rows)


def by_pair(rows: list[dict], key: str) -> dict[tuple, float]:
    return {pair(r): float(r[key]) for r in rows}


def paired(a_rows: list[dict], b_rows: list[dict], key: str) -> tuple[list[tuple], list[float], list[float]]:
    """The pairs both arms ran, sorted, with each arm's value of KEY."""
    a, b = by_pair(a_rows, key), by_pair(b_rows, key)
    pairs = sorted(set(a) & set(b))
    return pairs, [a[k] for k in pairs], [b[k] for k in pairs]
