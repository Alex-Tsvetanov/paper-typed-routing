#!/usr/bin/env python3
"""The sanitizer gate of an H6 build (round 2): do green records cover what the server build compiled?

    check_h6_records.py --records DIR --inputs BUILD.inputs.json --compiler ID [--v2-include FILE]
                        [--pins bench/cmake/pins.cmake]

The rules are bench/gate_lib.py's (the Papers repo's rule D5; design/round2/minimal-server.md,
section 7):
1. For every target of the build (mserver, the libraries it links, and h6_targets; hashed in
   project mode with RegexMatcher v2 as the dependency root regexmatcher, as t1/run_h6.sh and
   t1/sanitize_h6.sh hash them) and
   every sanitizer (ASan+UBSan, TSan, MSan), a green server record made on L
   (mserver-*-L-<san>.json, t1/sanitize_h6.sh) compiled the same inputs, with the same compiler,
   configuration and pins (the sha256 of the pins.cmake the build used, --pins, and every archive
   both fetched with the same URL and hash). No gap is declared for the server.
2. The hash of mserver_arms's inputs under regexmatcher/include/ (FILE, default BUILD.v2-include.json
   next to --inputs) equals that of the test targets of a green RegexMatcher record on L for each
   sanitizer, with the same compiler (bench/sanitize_regexmatcher.sh).
t1gen is gated by its own record, which lab/t1's t1.py checks. Prints one "covered" line per
target on stderr and the gate as JSON on stdout; exits 1 with the reason if the records do not
cover the build.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
from gate_lib import (PREFIX, GateError, config_of, fetched_of, file_sha256, load,  # noqa: E402
                      regexmatcher_coverage, target_coverage)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, required=True)
    ap.add_argument("--v2-include", type=Path)
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--pins", type=Path, default=Path(__file__).resolve().parent.parent / "bench" / "cmake" / "pins.cmake",
                    help="the pins.cmake the build used (default: this tree's)")
    args = ap.parse_args()
    info = load(args.inputs)["builds"]["h6"]
    hashes = {t: v["inputs_hash"] for t, v in info["targets"].items()}
    config = config_of(info)
    include = args.v2_include or Path(str(args.inputs).removesuffix(".inputs.json") + ".v2-include.json")
    try:
        pins = file_sha256(args.pins)
        coverage, _, used = target_coverage(args.records, "mserver-*.json", hashes, config, args.compiler,
                                            pins=pins, fetched=fetched_of(info))
        if not include.exists():
            raise GateError(f"no {include.name}: the RegexMatcher headers of the server are not hashed")
        prefix = load(include)["builds"]["h6"]["targets"]["mserver_arms"]["prefix_hashes"][PREFIX]["hash"]
        rm = regexmatcher_coverage(args.records, prefix, args.compiler)
    except GateError as e:
        sys.exit(f"check_h6_records: {e}")
    print(json.dumps({"compiler": args.compiler, "pins_sha256": pins, "fetched": fetched_of(info),
                      "inputs_hash": hashes, "config": config, "coverage": coverage,
                      "regexmatcher": {"prefix_hash": prefix, "records": rm},
                      "records": sorted(set(used) | {n for ns in rm.values() for n in ns})}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
