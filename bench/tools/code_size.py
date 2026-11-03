#!/usr/bin/env python3
"""The normalized lookup code size of the ablation arms (design/review-runs/ablations.md), for
analysis/ablations.py: code-size.tsv, one row per arm.

    code_size.py --cxx CXX --regexmatcher DIR --out code-size.tsv [--label L] [FLAG...]

bench/objdump_check.sh compiles the out-of-line lookup of one header and of another at -O3 and the FLAGs
(the arms' own: -march=native), disassembles both, normalizes the text (no addresses, the namespace
mapped to NS) and reports, for each, its functions, its lines and the sha256 of the text. This runs it
for the renamed copy against the pinned headers (DIR/include, matcher/route.hpp), and for each variant
against the copy, and writes per arm: lines and functions of its normalized lookup code, the first 16
hex digits of its sha256, and whether it is the copy's code (IDENTICAL). The pinned arm's row comes from
the first comparison. Exits 1 if a header is missing, objdump_check.sh fails, a lookup has no function or
no line, or the copy's code is not the pinned code.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
ABLATION = BENCH / "arms" / "ablation"
VARIANTS = (("regexmatcher-v2-ab-linear", "ab_linear"), ("regexmatcher-v2-ab-hashed", "ab_hashed"),
            ("regexmatcher-v2-ab-noexact", "ab_noexact"), ("regexmatcher-v2-ab-bytes", "ab_bytes"))
SUMMARY = re.compile(r"functions (\d+) and (\d+), lines (\d+) and (\d+), sha256 ([0-9a-f]+) and ([0-9a-f]+)")


def compare(cxx: str, label: str, old: Path, old_ns: str, inc: Path, header: str, ns: str,
            flags: list[str]) -> tuple[dict, dict, bool]:
    """objdump_check.sh on two headers: each one's functions, lines and sha256, and whether they are equal."""
    for header_file in (old, inc / header):
        if not header_file.is_file():
            raise SystemExit(f"code_size: {label}: the header {header_file} does not exist")
    p = subprocess.run(["bash", str(BENCH / "objdump_check.sh"), cxx, label, str(old), old_ns, str(inc), header, ns]
                       + flags, capture_output=True, text=True)
    m = SUMMARY.search(p.stdout)
    if p.returncode != 0 or m is None:
        raise SystemExit(f"code_size: objdump_check.sh {label} failed (exit {p.returncode}): {p.stdout}{p.stderr}")
    a = {"functions": int(m.group(1)), "lines": int(m.group(3)), "sha256": m.group(5)}
    b = {"functions": int(m.group(2)), "lines": int(m.group(4)), "sha256": m.group(6)}
    for side in (a, b):
        if side["functions"] < 1 or side["lines"] < 1:
            raise SystemExit(f"code_size: objdump_check.sh {label} found {side['functions']} functions "
                             f"and {side['lines']} lines of lookup code: {p.stdout}")
    return a, b, "\nIDENTICAL" in p.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cxx", required=True)
    ap.add_argument("--regexmatcher", type=Path, required=True, help="RegexMatcher at the pinned commit")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--label", default="code-size", help="objdump_check.sh's work directory under ~/od")
    ap.add_argument("flags", nargs="*")
    a = ap.parse_args()
    a.out.unlink(missing_ok=True)  # a failed run leaves no table that an earlier one wrote
    copy_h = ABLATION / "route_copy.hpp"
    rows = []
    copy, pinned, same = compare(a.cxx, f"{a.label}-copy", copy_h, "matcher::route_copy", a.regexmatcher / "include",
                                 "matcher/route.hpp", "matcher::route", a.flags)
    rows.append(("regexmatcher-v2", pinned, same))
    rows.append(("regexmatcher-v2-copy", copy, True))
    for arm, tag in VARIANTS:
        _, var, eq = compare(a.cxx, f"{a.label}-{tag}", copy_h, "matcher::route_copy", ABLATION, f"route_{tag}.hpp",
                             f"matcher::route_{tag}", a.flags)
        rows.append((arm, var, eq))
    text = "arm\tlines\tfunctions\tsha256\tsame_as_copy\n" + "".join(
        f"{arm}\t{v['lines']}\t{v['functions']}\t{v['sha256']}\t{'yes' if eq else 'no'}\n" for arm, v, eq in rows)
    a.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if not same:
        print("code_size: the copy's normalized lookup code is NOT the pinned headers'", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
