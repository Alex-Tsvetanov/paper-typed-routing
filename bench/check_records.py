#!/usr/bin/env python3
"""The sanitizer gate of a gated rbench run (round 2): do green records cover what this build compiled?

    check_records.py --records DIR --inputs BUILD.inputs.json --compiler ID [--v2-include BUILD.v2-include.json]
                     [--pins bench/cmake/pins.cmake] [--out gate.json]

Records are matched by what they compiled, not by commit (the Papers repo's rule D5; the rules are
bench/gate_lib.py's):
1. For every target of the build (rbench and each arm_*; build.sh's inputs.json) and every
   sanitizer (ASan+UBSan, TSan, MSan), a green rbench record made on L (rbench-*-L-<san>[-TAG].json,
   bench/sanitize_rbench.sh) compiled the same first-party inputs for that target, with the same
   compiler, the same configuration and the same pins (the sha256 of the pins.cmake the build used,
   --pins, and every archive both fetched with the same URL and hash; bench/gate_lib.py). A gap
   is allowed only where coverage.json declares it.
2. RegexMatcher v2 (design/round2/regexmatcher-v2.md, section 8.4): when the build has v2's arms,
   the hash of their inputs under regexmatcher/include/ (build.sh's BUILD.v2-include.json, the
   default next to --inputs) equals that of the test targets of a green RegexMatcher record on L
   for each sanitizer, with the same compiler (bench/sanitize_regexmatcher.sh).

Prints one "covered" line per target on stderr and the gate as JSON on stdout or to --out; exits 1
with the reason if the records do not cover the build.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gate_lib import PREFIX, GateError, config_of, fetched_of, file_sha256, load, regexmatcher_coverage, target_coverage


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, required=True, help="build.sh's <build>.inputs.json")
    ap.add_argument("--v2-include", type=Path, help="build.sh's <build>.v2-include.json (default: next to --inputs)")
    ap.add_argument("--compiler", required=True, help="the build's CMake compiler identification")
    ap.add_argument("--coverage", type=Path, default=Path(__file__).with_name("coverage.json"))
    ap.add_argument("--pins", type=Path, default=Path(__file__).with_name("cmake") / "pins.cmake",
                    help="the pins.cmake the build used (default: this tree's)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    info = load(args.inputs)["builds"]["rbench"]
    hashes = {t: v["inputs_hash"] for t, v in info["targets"].items()}
    config = config_of(info)
    declared = {k: v for k, v in load(args.coverage).items() if k.startswith("arm_")}
    pins = file_sha256(args.pins)
    try:
        coverage, partial, used = target_coverage(args.records, "rbench-*.json", hashes, config, args.compiler, declared,
                                                  pins=pins, fetched=fetched_of(info))
        v2 = {}
        include = args.v2_include or Path(str(args.inputs).removesuffix(".inputs.json") + ".v2-include.json")
        if any(t.startswith("arm_regexmatcher_v2") and t != "arm_regexmatcher_v2_r1" for t in hashes):
            if not include.exists():
                raise GateError(f"the build has v2's arms and no {include.name}")
            targets = load(include)["builds"]["rbench"]["targets"]
            prefixes = {v["prefix_hashes"][PREFIX]["hash"] for v in targets.values()}
            if len(prefixes) != 1:
                raise GateError(f"v2's arms compiled different RegexMatcher headers ({len(prefixes)} prefix hashes)")
            prefix = prefixes.pop()
            v2 = {"prefix_hash": prefix, "records": regexmatcher_coverage(args.records, prefix, args.compiler)}
    except GateError as e:
        sys.exit(f"check_records: {e}")
    gate = {"compiler": args.compiler, "pins_sha256": pins, "fetched": fetched_of(info),
            "inputs_hash": hashes, "config": config, "coverage": coverage,
            "partial": partial, "regexmatcher": v2,
            "records": sorted(set(used) | {n for ns in (v2.get("records") or {}).values() for n in ns})}
    text = json.dumps(gate, indent=1)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
