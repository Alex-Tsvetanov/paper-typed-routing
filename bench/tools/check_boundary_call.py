#!/usr/bin/env python3
"""Check, in a linked rbench, that the C-boundary arms of design/review-runs/boundary-arms.md reach their C
function through a real call from the harness's timed loop, and that the build has no link-time
optimisation that could have inlined it.

    check_boundary_call.py RBENCH BUILD_DIR

For each arm (regexmatcher-v2-capi and its C function rb_v2capi_at; capi-null and rb_capi_null_at):
1. the C function is defined in RBENCH (nm: a text symbol with a size);
2. the timed loop's function, ArmRunner<the arm's adapter class>::harness_pass (or, if the compiler inlined
   it, one_pass or measure), reaches a `call` to the C function by direct calls (objdump -d): in the loop
   itself, or in a function it calls (the adapter's lookup, or the harness's full(), if the compiler kept
   them out of line);
3. no compile command of BUILD_DIR/compile_commands.json has -flto, and BUILD_DIR/CMakeCache.txt does not
   turn on CMAKE_INTERPROCEDURAL_OPTIMIZATION.
Prints one line per check and exits 1 if any fails. An arm the binary does not have is skipped (and named).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ARMS = (("regexmatcher-v2-capi", "V2CapiArm", "rb_v2capi_at"), ("capi-null", "CapiNullArm", "rb_capi_null_at"))
FUNC = re.compile(r"^[0-9a-f]+ <(.+)>:$")
CALL = re.compile(r"\bcall\s+[0-9a-f]+ <([^>+]+)(\+0x[0-9a-f]+)?>")


def call_graph(binary: Path) -> dict[str, set[str]]:
    """Each function's direct callees, by demangled name, from objdump -d -C."""
    text = subprocess.run(["objdump", "-d", "-C", "--no-show-raw-insn", str(binary)], check=True,
                          capture_output=True, text=True).stdout
    graph: dict[str, set[str]] = defaultdict(set)
    current = ""
    for line in text.splitlines():
        m = FUNC.match(line)
        if m:
            current = m.group(1)
            continue
        c = CALL.search(line)
        if c and current:
            graph[current].add(c.group(1))
    return graph


def defined(binary: Path) -> dict[str, int]:
    """Text symbols with their sizes (nm -S)."""
    out = subprocess.run(["nm", "-S", "--defined-only", str(binary)], check=True, capture_output=True, text=True).stdout
    sizes = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[2] in ("T", "t"):
            sizes[parts[3]] = int(parts[1], 16)
    return sizes


def reaches(graph: dict[str, set[str]], start: str, target: str, depth: int = 3) -> list[str] | None:
    """A chain of direct calls from start to target, at most `depth` calls long."""
    frontier = [[start]]
    for _ in range(depth):
        nxt = []
        for path in frontier:
            for callee in sorted(graph.get(path[-1], ())):
                if callee == target:
                    return path + [callee]
                if callee not in path:
                    nxt.append(path + [callee])
        frontier = nxt
    return None


def short(name: str) -> str:
    """A function's own name, without its class, template arguments and parameters."""
    m = re.search(r"(\w+)\(", name)
    return m.group(1) if m else name


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    binary, build = Path(argv[1]), Path(argv[2])
    failures = 0

    def check(ok: bool, what: str) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok' if ok else 'FAIL'}: {what}")

    commands = json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))
    lto = [c["file"] for c in commands if "-flto" in c.get("command", " ".join(c.get("arguments", [])))]
    check(not lto, f"no compile command has -flto ({len(commands)} commands; {', '.join(lto[:3])})")
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    ipo = re.search(r"^CMAKE_INTERPROCEDURAL_OPTIMIZATION[^=]*=(ON|TRUE|1|YES)\s*$", cache, re.M | re.I)
    check(ipo is None, "CMAKE_INTERPROCEDURAL_OPTIMIZATION is not on")

    sizes = defined(binary)
    graph = call_graph(binary)
    for arm, cls, fn in ARMS:
        if fn not in sizes:
            print(f"skip: {arm} is not in {binary.name} (no {fn})")
            continue
        check(sizes[fn] > 0, f"{arm}: {fn} is a function of {sizes[fn]} bytes")
        # The timed loop is harness_pass; if the compiler inlined it, the function it was inlined into.
        runner = f"ArmRunner<(anonymous namespace)::{cls}>::"
        loops = []
        for name in ("harness_pass", "one_pass", "measure"):
            loops = [f for f in graph if runner + name in f]
            if loops:
                break
        chain = next((c for f in loops if (c := reaches(graph, f, fn))), None)
        check(chain is not None, f"{arm}: the timed loop calls {fn}"
              + (f" ({' -> '.join(short(n) for n in chain)})" if chain else
                 f" (loop functions found: {len(loops)})"))
    print(f"check_boundary_call: {'ok' if failures == 0 else f'{failures} failing'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
