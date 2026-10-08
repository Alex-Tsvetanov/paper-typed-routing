#!/usr/bin/env python3
"""The gated builds of round 2 against the sanitizer records published in lab/sanitizer-records.

    python analysis/records_cover.py RUNS [--out results/round2/records-cover.txt]

RUNS is the directory into which the tarballs of release data-2026-10 are unpacked
(results/round2/README.md). For each gated build (the main grid, H7's costs on L, the heap-block
follow-up and H6), the repository's own gate script (bench/check_records.py, t1/check_h6_records.py)
is run on the inputs that the run's archive records, twice:

- with the runs' pins file, results/round2/pins-of-the-runs.cmake: the gate as it ran. Where the run
  kept its gate.json, the gate written now must equal it once the records that the archived gate
  does not name (records made after the run) are set aside;
- with the root commit's pins file, bench/cmake/pins.cmake: the records made for the root commit.

Writes what each script prints on stderr, its exit status and the comparison. Run from the
repository root. Exits 1 if a gate fails or a comparison differs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

BUILDS = [
    ("the main grid (rbench and its 25 arms)", "bench/check_records.py",
     "2026-09-30-L-publication", "inputs.json", "v2-include.json", "gate.json"),
    ("H7's costs on L, the run's rbench build", "bench/check_records.py",
     "2026-09-30-L-publication-ct", "inputs.json", "v2-include.json", "gate.json"),
    ("H7's costs on L, the compile-time arm's cost build", "bench/check_records.py",
     "2026-09-30-L-publication-ct", "ct-build.inputs.json", "ct-build.v2-include.json", None),
    ("H7's heap-block follow-up (rbench, every arm and regexmatcher-v2-ct-heap)", "bench/check_records.py",
     "2026-10-02-L-exploratory-ct-heap", "inputs.json", "v2-include.json", "gate.json"),
    ("H6 (the minimal server and h6_targets)", "t1/check_h6_records.py",
     "2026-09-30-L-h6", "build.inputs.json", "build.v2-include.json", "gate.json"),
]
PINS = [("the runs' pins file, results/round2/pins-of-the-runs.cmake (the gate as it ran)",
         "results/round2/pins-of-the-runs.cmake"),
        ("the root commit's pins file, bench/cmake/pins.cmake", "bench/cmake/pins.cmake")]
RECORDS = Path("lab/sanitizer-records")
HEAD = """\
The gated builds of the runs against the sanitizer records published in lab/sanitizer-records,
written by `python analysis/records_cover.py RUNS --out results/round2/records-cover.txt` (on W,
2026-10-08). RUNS is the directory into which the tarballs that are the assets of release
data-2026-10 are unpacked. A record covers a build when, for a target and a sanitizer, it is green
and names the same inputs hash, compiler, configuration, pins file (its sha256, CRLF read as LF) and
fetched archives, whatever its commit (bench/gate_lib.py).

Each build is checked twice. With the runs' own pins file (sha256 fd987818804a..., the pins_sha256 of
every gated run), the records that gated the run at the time cover it, and the gate written now
equals the gate.json in the run's archive, where the run kept one, once the records made after the
run are set aside. With the root commit's pins file (sha256 51dd14076cb4...), the records made on
2026-10-08 for the root commit f626955eb cover it. The two pins files differ only in the pin of
RegexMatcher v2 (RB_REGEXMATCHER_V2_COMMIT and RB_REGEXMATCHER_V2_SHA256, empty in the runs' file)
and its comment; bench/cmake/regexmatcher-v2.cmake uses that pin only when no REGEXMATCHER_DIR is
given, and every gated build gave REGEXMATCHER_DIR.
"""


def only(x, kept: set[str]):
    """x with every list of record names reduced to the names in kept."""
    if isinstance(x, dict):
        return {k: only(v, kept) for k, v in x.items()}
    if isinstance(x, list) and all(isinstance(e, str) and e.endswith(".json") for e in x):
        return [e for e in x if e in kept]
    return x


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    lines = HEAD.splitlines() + [""]
    ok = True
    for label, script, run, inputs, v2, gate in BUILDS:
        rd = a.runs / run
        for pins_label, pins in PINS:
            cmd = [sys.executable, script, "--records", str(RECORDS), "--inputs", str(rd / inputs),
                   "--v2-include", str(rd / v2), "--compiler", "Clang 22.1.8", "--pins", pins]
            p = subprocess.run(cmd, capture_output=True, text=True, check=False)
            shown = " ".join(["python"] + cmd[1:]).replace(str(a.runs), "RUNS").replace("\\", "/")
            lines += [f"## {label}; {pins_label}", "$ " + shown.replace("Clang 22.1.8", '"Clang 22.1.8"')]
            lines += [l.replace(str(a.runs), "RUNS") for l in p.stderr.splitlines()]
            lines.append(f"exit {p.returncode}")
            ok &= p.returncode == 0
            if gate and pins.startswith("results/") and p.returncode == 0:
                now = json.loads(p.stdout)
                then = json.loads((rd / gate).read_text(encoding="utf-8"))
                kept = set(then["records"])
                same = only(now, kept) == then
                lines.append("the gate written now, without the records that the archived gate does not name, "
                             f"equals RUNS/{run}/{gate}: {same}")
                for name in sorted(set(now["records"]) - kept):
                    rec = json.loads((RECORDS / name).read_text(encoding="utf-8"))
                    lines.append(f"  also named now: {name}, made {rec.get('date', '?')}")
                ok &= same
            lines.append("")
    text = "\n".join(lines).rstrip("\n") + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
