#!/usr/bin/env python3
"""H5(b) of hypotheses-round2.md from a run's probes (bench/core/probe.cpp, run_grid.sh's probes.jsonl).

    h5_stats.py RUN_DIR [--out FILE.csv]

H5(b): RegexMatcher v2 (regexmatcher-v2) passes every probe: the most specific route wins in
either registration order (cases static-then-param and param-then-static), every RFC 3986 pchar is
accepted in a parameter and returned as sent (pchar), a trailing slash is strict (trailing-slash),
and a path that matches only under another method gives 405 (method); the other cases of the
probe file (raw-bytes, catch-all, empty-segment) are reported too. H5(b) holds if v2 passes every
probe. Reported beside, deciding nothing: whether RegexMatcher v1 behind its wrapper
(regexmatcher-v1) fails the first two (at least one lookup of the specificity cases and at least
one of pchar). Every other arm's probes are listed per case. H5(a) and H5(c) are tests of
RegexMatcher's suite and of the minimal server's suite; their evidence is those suites' records.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from cells import V1, V2
from h1_stats import write_csv

SPECIFIC = ("static-then-param", "param-then-static")
PCHAR = ("pchar",)
STATED = SPECIFIC + PCHAR + ("trailing-slash", "method")


def per_case(probes: list[dict]) -> dict[str, dict[str, dict[str, int]]]:
    """arm: case: {"pass": n, "fail": n}."""
    out: dict = defaultdict(lambda: defaultdict(lambda: {"pass": 0, "fail": 0}))
    for p in probes:
        if "case" in p and p.get("status") in ("pass", "fail"):
            out[p["arm"]][p["case"]][p["status"]] += 1
    return out


def decide(probes: list[dict]) -> tuple[list[dict], dict]:
    cases = per_case(probes)
    rows = [{"arm": arm, "case": case, "passed": v["pass"], "failed": v["fail"]}
            for arm in sorted(cases) for case, v in cases[arm].items()]
    v2 = cases.get(V2, {})
    v1 = cases.get(V1, {})
    v2_all = bool(v2) and all(v["fail"] == 0 and v["pass"] > 0 for v in v2.values()) and all(c in v2 for c in STATED)
    v1_fails = (any(v1.get(c, {}).get("fail", 0) > 0 for c in SPECIFIC)
                and any(v1.get(c, {}).get("fail", 0) > 0 for c in PCHAR))
    summary = {"v2_passes_every_probe": v2_all, "v2_lookups": sum(v["pass"] + v["fail"] for v in v2.values()),
               "v1_fails_first_two": v1_fails, "holds": v2_all,
               "v1_failed_cases": sorted(c for c, v in v1.items() if v["fail"] > 0)}
    return rows, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    probes = [json.loads(x) for x in (a.run / "probes.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    rows, s = decide(probes)
    if a.out:
        write_csv(a.out, rows, ["arm", "case", "passed", "failed"])
    print(f"H5(b): v2 passes every probe: {s['v2_passes_every_probe']} ({s['v2_lookups']} lookups); v1 fails "
          f"the first two: {s['v1_fails_first_two']} (failed cases: {', '.join(s['v1_failed_cases']) or 'none'}); "
          f"H5(b) {'holds' if s['holds'] else 'does not hold'} (v2's part decides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
