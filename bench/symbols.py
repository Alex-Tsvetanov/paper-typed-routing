#!/usr/bin/env python3
"""symbols.py BINARY OUT: where the timed code landed in BINARY (audit m29).

Code alignment moves timings: the same loop runs at a different speed when it starts at another
offset in a 64-byte line. So every build keeps, for each out-of-line function that a timed pass
calls or is, its address, the address modulo 64, and its size, from the binary's symbol table
(nm). The functions are those whose names contain harness_pass, one_pass, _pass (the arms' own
passes, the Go arms' rb_*_pass included), lookup, find_v2 or find_r1. A function the compiler
inlined has no symbol and is not listed. OUT is a tab-separated file, one function a line,
sorted by name, with a header.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TIMED = re.compile(r"harness_pass|one_pass|_pass\b|::pass\(|lookup|find_v2|find_r1")
CODE = {"t", "T", "w", "W"}


def rows(nm_text: str) -> list[tuple[int, int | None, str]]:
    """(address, size or None, demangled name) of each timed code symbol in nm -C -S output."""
    out = []
    for line in nm_text.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) == 4 and parts[2] in CODE:
            addr, size, name = int(parts[0], 16), int(parts[1], 16), parts[3]
        elif len(parts) >= 3 and parts[1] in CODE:
            addr, size, name = int(parts[0], 16), None, line.split(maxsplit=2)[2]
        else:
            continue
        if TIMED.search(name):
            out.append((addr, size, name))
    return sorted(out, key=lambda r: (r[2], r[0]))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    nm = subprocess.run(["nm", "-C", "-S", "--defined-only", argv[1]], check=True,
                        capture_output=True, text=True).stdout
    found = rows(nm)
    if not found:
        print(f"symbols.py: no timed symbol in {argv[1]}", file=sys.stderr)
        return 1
    lines = ["address\tmod64\tsize\tname"]
    lines += [f"{a:#x}\t{a % 64}\t{'' if s is None else s}\t{n}" for a, s, n in found]
    Path(argv[2]).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
