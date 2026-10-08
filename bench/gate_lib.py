"""The rules the round-2 records gates share (bench/check_records.py for rbench, t1/check_h6_records.py
for the server; design/round2/regexmatcher-v2.md, section 8.4, and minimal-server.md, section 7).

Records are matched by what they compiled, not by commit (the Papers repo's rule D5):
- target_coverage: for every target of a build and every sanitizer (ASan+UBSan, TSan, MSan), a
  green record of the given name pattern, built on L, compiled the same first-party inputs for
  that target, with the same compiler and the same configuration. A gap is allowed only where
  `declared` names it, with its reason. A red record that compiled the same inputs stops the gate.
  A record counts only if it was also made with the build's pins: the same sha256 of
  bench/cmake/pins.cmake (pins_sha256, CRLF read as LF) and, for every archive both fetched, the
  same URL and hash as used (third_party.fetched of lab/bin/inputs_hash.py). A build whose pins
  differ from its records' is therefore refused; the error names the records left out for that.
  (The Go modules and Rust crates are pinned by go.sum and Cargo.lock, which the FFI arms' inputs
  hash already covers.)
- regexmatcher_coverage: the hash of a build's inputs under regexmatcher/include/ equals that of
  the test targets of a green RegexMatcher record (regexmatcher-*-L-<san>.json,
  bench/sanitize_regexmatcher.sh) for every sanitizer, with the same compiler; a red record with
  the same prefix hash stops the gate.
Every failure raises GateError with the reason.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SANITIZERS = ("asan", "tsan", "msan")
PREFIX = "regexmatcher/include/"


class GateError(Exception):
    pass


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def config_of(info: dict):
    """The build's configuration field of an inputs.json build: "config" (project mode) or
    "<name>_config" (default mode)."""
    for k, v in info.items():
        if k == "config" or k.endswith("_config"):
            return v
    return None


def file_sha256(path: Path) -> str:
    """The sha256 of a text file with CRLF read as LF (as lab/bin/inputs_hash.py reads inputs)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def fetched_of(info: dict) -> dict:
    """The archives a build fetched, as used: {name: {url, url_hash, ...}} (inputs_hash.py)."""
    return (info.get("third_party") or {}).get("fetched") or {}


def pins_differ(r: dict, pins: str, fetched: dict) -> str:
    """Why record R was made with other pins than the build's, or "" if it was not."""
    if r.get("pins_sha256") != pins:
        return f"pins.cmake {str(r.get('pins_sha256') or 'not recorded')[:12]}, the build's {pins[:12]}"
    theirs = fetched_of(r)
    for name in sorted(set(theirs) & set(fetched)):
        if theirs[name] != fetched[name]:
            return f"fetched {name} as {theirs[name]}, the build as {fetched[name]}"
    return ""


def l_records(records: Path, pattern: str) -> list[Path]:
    """The records of a name pattern made on L (the host part of the name is L)."""
    return [f for f in sorted(records.glob(pattern)) if "-L-" in f.name]


def target_coverage(records: Path, pattern: str, hashes: dict, config, compiler: str,
                    declared: dict | None = None, *, pins: str, fetched: dict) -> tuple[dict, dict, list[str]]:
    declared = declared or {}
    coverage: dict = {t: {} for t in hashes}
    used: set = set()
    other_pins: list[str] = []
    for f in l_records(records, pattern):
        r = load(f)
        san = r.get("sanitizer")
        if san not in SANITIZERS:
            continue
        theirs = r.get("inputs_hash") or {}
        same = [t for t, h in hashes.items() if theirs.get(t) == h]
        if not same:
            continue
        if r.get("green") is not True:
            raise GateError(f"{f.name} compiled the same inputs for {', '.join(same)} and is red")
        if r.get("compiler") != compiler or config_of(r) != config:
            continue
        why = pins_differ(r, pins, fetched)
        if why:
            other_pins.append(f"{f.name} ({why})")
            continue
        for t in same:
            coverage[t].setdefault(san, []).append(f.name)
            used.add(f.name)
    partial = {}
    for t, by_san in coverage.items():
        missing = [s for s in SANITIZERS if s not in by_san]
        allowed = (declared.get(t) or {}).get("not_covered_by", [])
        if any(s not in allowed for s in missing):
            raise GateError(f"{t} (inputs {hashes[t][:12]}) has no green {', '.join(s for s in missing if s not in allowed)} "
                            f"record on L with compiler {compiler} and pins {pins[:12]}, and no declared gap"
                            + (f"; left out for other pins: {'; '.join(other_pins)}" if other_pins else ""))
        if missing:
            partial[t] = {"covered_by": [s for s in SANITIZERS if s in by_san], "reason": declared[t]["reason"]}
        print(f"covered: {t} {hashes[t][:12]} by " + "; ".join(f"{s} {', '.join(n)}" for s, n in by_san.items()),
              file=sys.stderr)
    return coverage, partial, sorted(used)


def regexmatcher_coverage(records: Path, prefix_hash: str, compiler: str) -> dict:
    by_san: dict = {}
    for f in l_records(records, "regexmatcher-*.json"):
        r = load(f)
        hashes = {h for t in (r.get("prefix_hashes") or {}).values() for p, h in t.items() if p == PREFIX}
        if prefix_hash not in hashes:
            continue
        if r.get("green") is not True:
            raise GateError(f"{f.name} compiled the same RegexMatcher headers and is red")
        if r.get("compiler") != compiler or r.get("sanitizer") not in SANITIZERS:
            continue
        by_san.setdefault(r["sanitizer"], []).append(f.name)
    missing = [s for s in SANITIZERS if s not in by_san]
    if missing:
        raise GateError(f"no green RegexMatcher record on L with compiler {compiler} compiled {PREFIX} "
                        f"{prefix_hash[:12]} under {', '.join(missing)}")
    print(f"covered: {PREFIX} {prefix_hash[:12]} by " + "; ".join(f"{s} {', '.join(n)}" for s, n in by_san.items()),
          file=sys.stderr)
    return by_san
