#!/usr/bin/env python3
"""D5's gate for round 3: is every first-party input of a measured build covered by a green record?

    check_records.py --build-dir OUT --host-tag L|W --records DIR [--coverage t3/coverage.json]
                     [--out gate.json]

OUT is a bring-up or campaign job's output folder with what the measured build compiled:
build.inputs.json (t3/inputs.sh), build-info.json (t3/build_programs.py) and build.log (the
configure, for the compiler). The records are round 3's (tool p2r3, t3/record.py) in DIR, the Papers
repo's lab/sanitizer-records once the lab has copied them there.

A record counts for a target and a sanitizer only if: it was made on the same host (host_tag), not
on the desktop (desktop_development false); it is green; its compiler and configuration equal the
build's; its pins (pins_sha256 of bench/cmake/pins.cmake and server/cmake/pins-round3.cmake, CRLF read
as LF) equal this checkout's; every archive both fetched has the same URL and hash; and its
inputs_hash for that target equals the build's. The sanitizers a host needs: L asan, tsan and msan; W
asan (CLAUDE.md, D5). Every C++ target needs every one; a Go or Rust program may lack one only where
t3/coverage.json declares the gap for that host. A red record that compiled the same inputs for a
target stops the gate. Exit 0 when every target is covered, 1 otherwise, 2 on bad input; the gate
JSON lists each target's records and the gaps used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NEEDED = {"L": ("asan", "tsan", "msan"), "W": ("asan",)}
PINS = ("bench/cmake/pins.cmake", "server/cmake/pins-round3.cmake")
COMPILER_ID = re.compile(r"^-- The CXX compiler identification is (.+?)\s*$", re.MULTILINE)


class GateError(Exception):
    pass


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def sha256_lf(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build_of(out: Path) -> dict:
    """The measured build: {inputs: {target: hash}, config, fetched, compiler}."""
    try:
        b = next(iter(load(out / "build.inputs.json")["builds"].values()))
        info = load(out / "build-info.json")
        log = (out / "build.log").read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError, StopIteration, KeyError) as e:
        raise GateError(f"{out}: {e}") from None
    m = COMPILER_ID.search(log)
    if not m:
        raise GateError(f"{out}/build.log names no CXX compiler")
    inputs = {t: v["inputs_hash"] for t, v in b["targets"].items()}
    for key, name in (("go", "mserver-go"), ("rust", "mserver-rs")):
        if key in info:
            if info[key].get("sanitizer", "none") != "none":
                raise GateError(f"build-info.json's {key} program was built under a sanitizer; a measured build never is")
            inputs[name] = info[key]["source"]["inputs_hash"]
    config = next((v for k, v in b.items() if k == "config" or k.endswith("_config")), None)
    fetched = ((b.get("third_party") or {}).get("fetched") or {})
    return {"inputs": inputs, "config": config, "fetched": fetched, "compiler": m.group(1)}


def why_not(r: dict, build: dict, host_tag: str, pins: dict) -> str:
    """Why record r cannot cover this build at all, or ""."""
    if r.get("tool") != "p2r3":
        return "not a round-3 record"
    if r.get("desktop_development"):
        return "a development run on the desktop"
    if r.get("host_tag") != host_tag:
        return f"host {r.get('host_tag')}"
    if r.get("compiler") != build["compiler"]:
        return f"compiler {r.get('compiler')}"
    if r.get("config") != build["config"]:
        return f"configuration {r.get('config')}"
    if r.get("pins_sha256") != pins:
        return "other pins"
    theirs = ((r.get("third_party") or {}).get("fetched") or {})
    for name in sorted(set(theirs) & set(build["fetched"])):
        if theirs[name] != build["fetched"][name]:
            return f"fetched {name} otherwise"
    return ""


def gate(build: dict, host_tag: str, records: Path, coverage: dict) -> dict:
    pins = {p: sha256_lf(ROOT / p) for p in PINS}
    gaps = coverage.get(host_tag) or {}
    needed = NEEDED[host_tag]
    cover: dict = {t: {} for t in build["inputs"]}
    left_out = []
    for f in sorted(records.glob("p2r3-*.json")):
        r = load(f)
        san = r.get("sanitizer")
        if san not in needed:
            continue
        theirs = r.get("inputs_hash") or {}
        same = [t for t, h in build["inputs"].items() if theirs.get(t) == h]
        if not same:
            continue
        why = why_not(r, build, host_tag, pins)
        if why:
            left_out.append(f"{f.name}: {why}")
            continue
        if r.get("green") is not True:
            raise GateError(f"{f.name} compiled the same inputs for {', '.join(same)} and is red")
        for t in same:
            cover[t].setdefault(san, []).append(f.name)
    result = {"host_tag": host_tag, "compiler": build["compiler"], "targets": {}, "gaps": {}, "left_out": left_out}
    missing = []
    for t, by_san in cover.items():
        declared = (gaps.get(t) or {}).get("not_covered_by", [])
        lacking = [s for s in needed if s not in by_san and s not in declared]
        if lacking:
            missing.append(f"{t} ({build['inputs'][t][:12]}): no green {', '.join(lacking)} record")
        result["targets"][t] = by_san
        used = [s for s in needed if s not in by_san and s in declared]
        if used:
            result["gaps"][t] = {"not_covered_by": used, "reason": gaps[t]["reason"]}
    result["green"] = not missing
    result["missing"] = missing
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-dir", type=Path, required=True)
    ap.add_argument("--host-tag", choices=sorted(NEEDED), required=True)
    ap.add_argument("--records", type=Path, required=True)
    ap.add_argument("--coverage", type=Path, default=HERE / "coverage.json")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    try:
        result = gate(build_of(a.build_dir), a.host_tag, a.records, load(a.coverage))
    except GateError as e:
        print(f"check_records: {e}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=1)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    for line in result["missing"]:
        print(f"check_records: {line}", file=sys.stderr)
    print(f"check_records: {'green' if result['green'] else 'NOT green'}, {len(result['targets'])} targets, "
          f"{len(result['gaps'])} declared gaps used, {len(result['left_out'])} records left out")
    return 0 if result["green"] else 1


if __name__ == "__main__":
    sys.exit(main())
