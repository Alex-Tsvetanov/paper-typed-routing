#!/usr/bin/env python3
"""Check, in a linked rbench, that the C-boundary arms of design/review-runs/boundary-arms.md reach their C
function through a real call from the harness's timed loop, and that the build has no link-time
optimisation that could have inlined it.

    check_boundary_call.py RBENCH BUILD_DIR

For each arm the build has, that is, names in the RB_ARMS entry of BUILD_DIR/CMakeCache.txt
(regexmatcher-v2-capi and its C function rb_v2capi_at; capi-null and rb_capi_null_at):
1. the C function is defined in RBENCH (nm: a text symbol with a size);
2. the timed epochs, nanobench's Bench::run over ArmRunner<the arm's adapter>::measure's first lambda
   without parameters (core/runner.hpp: one_pass, whose loop is harness_pass), or harness_pass itself if the
   compiler kept it out of line, reach a `call` to the C function by direct calls (objdump -d): in the loop
   itself, or in a function it calls (the adapter's lookup, or the harness's full(), if the compiler kept
   them out of line), at most four calls deep;
3. no compile command of BUILD_DIR/compile_commands.json has -flto, and BUILD_DIR/CMakeCache.txt does not
   turn on CMAKE_INTERPROCEDURAL_OPTIMIZATION.
Prints one line per check and exits 1 if any fails. An arm the build does not have is skipped (and named); an
arm it has whose C function is not in RBENCH fails. The check also fails if no arm was checked, if the build
has no compile command, or if an input cannot be read: nothing checked is not a pass.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ARMS = (("regexmatcher-v2-capi", "V2CapiArm", "rb_v2capi_at"), ("capi-null", "CapiNullArm", "rb_capi_null_at"))
TIMED_RUN = "ankerl::nanobench::Bench& ankerl::nanobench::Bench::run<"
FUNC = re.compile(r"^[0-9a-f]+ <(.+)>:$")
# A direct call, or a tail call (a jmp to the start of a function, with no offset); a demangled name may
# hold '<' and '>' itself, so the target is everything between the first '<' and the line's last '>'.
CALL = re.compile(r"\b(call|jmp)\s+[0-9a-f]+ <(.+)>\s*$")
OFFSET = re.compile(r"\+0x[0-9a-f]+$")


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
            target = c.group(2)
            if OFFSET.search(target):
                if c.group(1) == "jmp":
                    continue  # a jump inside a function, not a call
                target = OFFSET.sub("", target)
            graph[current].add(target)
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


def built_arms(cache: str) -> list[str] | None:
    """The arms the build was configured with (CMakeCache.txt's RB_ARMS), or None if it names none."""
    m = re.search(r"^RB_ARMS:[A-Z]+=(.*)$", cache, re.M)
    return [a for a in m.group(1).strip().split(";") if a] if m else None


def reaches(graph: dict[str, set[str]], start: str, target: str, depth: int = 4) -> list[str] | None:
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
    if name.startswith(TIMED_RUN):
        return "nanobench Bench::run (the timed epochs)"
    m = re.search(r"(\w+)(\[abi:\w+\])?\(", name)
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

    try:
        commands = json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))
        cache = (build / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
        sizes = defined(binary)
        graph = call_graph(binary)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"FAIL: cannot read the build or the binary: {e}")
        return 1
    check(len(commands) > 0, f"the build has compile commands ({len(commands)})")
    lto = [c["file"] for c in commands if "-flto" in c.get("command", " ".join(c.get("arguments", [])))]
    check(not lto, f"no compile command has -flto ({len(commands)} commands; {', '.join(lto[:3])})")
    ipo = re.search(r"^CMAKE_INTERPROCEDURAL_OPTIMIZATION[^=]*=(ON|TRUE|1|YES)\s*$", cache, re.M | re.I)
    check(ipo is None, "CMAKE_INTERPROCEDURAL_OPTIMIZATION is not on")

    arms = built_arms(cache)
    check(arms is not None, "CMakeCache.txt names the build's arms (RB_ARMS)")
    checked = 0
    for arm, cls, fn in ARMS:
        if arm not in (arms or []):
            check(fn not in sizes, f"{arm} is not among the build's arms, so {binary.name} must not define {fn}")
            continue
        checked += 1
        check(fn in sizes, f"{arm}: {fn} is defined in {binary.name}")
        if fn not in sizes:
            continue
        check(sizes[fn] > 0, f"{arm}: {fn} is a function of {sizes[fn]} bytes")
        # The timed epochs: nanobench's Bench::run over measure's first lambda without parameters, whose
        # body is one_pass (core/runner.hpp); harness_pass, if the compiler kept it out of line, is the loop.
        runner = f"rb::ArmRunner<(anonymous namespace)::{cls}>::"
        loops = [f for f in graph if f.startswith(TIMED_RUN + runner + "measure") and "::{lambda()#1}>" in f]
        loops += [f for f in graph if runner + "harness_pass" in f]
        chain = next((c for f in loops if (c := reaches(graph, f, fn))), None)
        check(chain is not None, f"{arm}: the timed loop calls {fn}"
              + (f" ({' -> '.join(short(n) for n in chain)})" if chain else
                 f" (loop functions found: {len(loops)})"))
    check(checked > 0, f"at least one boundary arm was checked ({checked})")
    print(f"check_boundary_call: {'ok' if failures == 0 else f'{failures} failing'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
