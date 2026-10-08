#!/usr/bin/env python3
"""The cost of each compile-time table in a build of rbench (reported with H7).

    ct_costs.py BUILD_DIR [--out FILE.jsonl]

For every generated table (bench/gen/ct_<shape>_<m>_s<seed>.cpp, and ct_github_203.cpp) in BUILD_DIR: the wall time its
object took to compile, from Ninja's log (.ninja_log: start and end in ms), and the size of
the object file and of its loadable sections (the `size` tool): text (.text*), rodata
(.rodata* and .data.rel.ro*), data (the other .data*) and bss (.bss*), and their sum,
loadable_bytes, which is the object size H7 reports. The file size (object_bytes) is reported
beside it: it also holds the padding to each section's alignment, which a page-aligned table
adds to the file but not to memory the lookup touches. One JSON object per table, sorted by
shape and size. A build made with -j > 1 compiles several tables at
once, so the times are those of a busy machine; build with -j1 to compare them.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

GEN = re.compile(r"gen/ct_([a-z_]+)_(\d+)(?:_s(\d+))?\.cpp\.o$")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    latest: dict[str, tuple[int, int]] = {}
    for line in (args.build / ".ninja_log").read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and GEN.search(parts[3]):
            latest[parts[3]] = (int(parts[0]), int(parts[1]))  # the last entry of an output wins
    rows = []
    for output, (start, end) in latest.items():
        m = GEN.search(output)
        obj = args.build / output
        sections = {}
        if obj.exists():
            done = subprocess.run(["size", "-A", str(obj)], capture_output=True, text=True, check=False)
            for line in done.stdout.splitlines():
                f = line.split()
                if len(f) >= 2 and f[1].isdigit():
                    sections[f[0]] = int(f[1])
        text = sum(v for k, v in sections.items() if k.startswith(".text"))
        rodata = sum(v for k, v in sections.items() if k.startswith(".rodata") or k.startswith(".data.rel.ro"))
        data = sum(v for k, v in sections.items() if k.startswith(".data") and not k.startswith(".data.rel.ro"))
        bss = sum(v for k, v in sections.items() if k.startswith(".bss"))
        rows.append({"shape": m.group(1).replace("_", "-"), "m": int(m.group(2)),
                     "table_seed": int(m.group(3)) if m.group(3) else None, "compile_s": (end - start) / 1000,
                     "object_bytes": obj.stat().st_size if obj.exists() else None, "text_bytes": text,
                     "rodata_bytes": rodata, "data_bytes": data, "bss_bytes": bss,
                     "loadable_bytes": text + rodata + data + bss})
    rows.sort(key=lambda r: (r["shape"], r["m"], r["table_seed"] or 0))
    lines = [json.dumps(r) for r in rows]
    if args.out:
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
