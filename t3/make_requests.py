#!/usr/bin/env python3
"""Round 3's request sets (design/round3/end-to-end.md, section 4).

Runs e2e_requests for round 3's shapes (mixed-disjoint and static, Alex 2026-10-23) at the five
sizes and round 2's sixteen seed pairs (table seeds 111 to 126 with ring seeds 211 to 226), into
OUT/<shape>/m<m>/t<table seed>/, and writes OUT/manifest.tsv: one line per cell with every digest
e2e_requests prints.

    make_requests.py --bin BUILD/e2e_requests --out DIR [--shapes static] [--sizes 10,100] [--pairs 16]
                     [--all-pairs 1]
    make_requests.py --bin BUILD/e2e_requests --out DIR --pair-list 127:227[,128:228 ...] [--shapes ...]
                     [--sizes ...] [--all-pairs 1]
    make_requests.py --verify DIR --manifest t3/requests-manifest.tsv [--complete]

--pair-list names the seed pairs (table seed:ring seed) in place of the first --pairs of the sixteen;
the floor rerun's pair (127, 227) is made this way (design/review-runs/floor-rerun.md). The second
form compares a generated manifest with the committed one, so every program and run
reads the same request sets: every generated cell must be a committed one, and with --complete
every committed cell must have been generated too. The files themselves are not committed: at m = 100,000 a cell's
files hold some 10 MB. The set of every route (all.txt) is made for every pair up to m = 10,000,
and at m = 100,000 for the first --all-pairs pairs of the list only, as it takes minutes per cell there
(with the default 1, the first pair: (111, 211) of the sixteen, or the first of --pair-list).
"""
import argparse
import subprocess
import sys
from pathlib import Path

SHAPES = ("mixed-disjoint", "static")
SIZES = (10, 100, 1000, 10000, 100000)
PAIRS = tuple((111 + k, 211 + k) for k in range(16))


def parse_pairs(text: str) -> list[tuple[int, int]]:
    """'127:227,128:228' as [(127, 227), (128, 228)]: positive seeds, no table seed twice."""
    pairs = []
    for item in text.split(","):
        table, sep, ring = item.strip().partition(":")
        if not sep or not table.isdigit() or not ring.isdigit() or int(table) <= 0 or int(ring) <= 0:
            raise ValueError(f"a seed pair is TABLE:RING with positive whole seeds, not {item.strip()!r}")
        pairs.append((int(table), int(ring)))
    if len({t for t, _ in pairs}) != len(pairs):
        raise ValueError("a table seed is named twice: cells are kept by table seed")
    return pairs


def cell_dir(out: Path, shape: str, m: int, table_seed: int) -> Path:
    return out / shape / f"m{m}" / f"t{table_seed}"


def parse_line(line: str) -> dict:
    words = line.split()
    if len(words) % 2:
        raise ValueError(f"e2e_requests printed an odd number of words: {line!r}")
    return dict(zip(words[0::2], words[1::2]))


def generate(binary: Path, out: Path, shapes, sizes, pairs, all_pairs: int) -> int:
    rows = []
    for shape in shapes:
        for m in sizes:
            for k, (table_seed, ring_seed) in enumerate(pairs):
                d = cell_dir(out, shape, m, table_seed)
                d.mkdir(parents=True, exist_ok=True)
                cmd = [str(binary), "--shape", shape, "--m", str(m), "--table-seed", str(table_seed),
                       "--ring-seed", str(ring_seed), "--out", str(d)]
                if m == 100000 and k >= all_pairs:
                    cmd.append("--no-all")
                p = subprocess.run(cmd, capture_output=True, text=True)
                if p.returncode != 0:
                    print(f"make_requests: {shape} m {m} pair ({table_seed}, {ring_seed}): {p.stderr.strip()}",
                          file=sys.stderr)
                    return 1
                rows.append(parse_line(p.stdout.strip()))
    keys = list(rows[0].keys())
    with open(out / "manifest.tsv", "w", newline="\n") as f:
        f.write("\t".join(keys) + "\n")
        for r in rows:
            f.write("\t".join(r[k] for k in keys) + "\n")
    print(f"make_requests: {len(rows)} cells in {out}")
    return 0


def verify(out: Path, manifest: Path, complete: bool = False) -> int:
    got = (out / "manifest.tsv").read_text().splitlines()
    want = manifest.read_text().splitlines()
    if got[0] != want[0]:
        print("make_requests: manifest columns differ", file=sys.stderr)
        return 1
    want_rows = set(want[1:])
    missing = [r for r in got[1:] if r not in want_rows]
    if missing:
        for r in missing:
            print(f"make_requests: not in the committed manifest: {r}", file=sys.stderr)
        return 1
    if complete:
        absent = sorted(want_rows - set(got[1:]))
        if absent:
            for r in absent:
                print(f"make_requests: committed but not generated: {r}", file=sys.stderr)
            return 1
    print(f"make_requests: {len(got) - 1} cells match {manifest}" + (", all of its cells" if complete else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--shapes", default=",".join(SHAPES))
    ap.add_argument("--sizes", default=",".join(map(str, SIZES)))
    ap.add_argument("--pairs", type=int, help=f"the first N of the {len(PAIRS)} seed pairs (default all)")
    ap.add_argument("--pair-list", help="the seed pairs as TABLE:RING[,TABLE:RING ...], in place of --pairs")
    ap.add_argument("--all-pairs", type=int, default=1, help="at m = 100,000, the every-route set for the first N pairs")
    ap.add_argument("--verify", type=Path)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--complete", action="store_true", help="--verify: every committed cell must be there")
    a = ap.parse_args()
    if a.verify:
        if not a.manifest:
            ap.error("--verify needs --manifest")
        return verify(a.verify, a.manifest, a.complete)
    if not a.bin or not a.out:
        ap.error("--bin and --out are required")
    sizes = [int(s) for s in a.sizes.split(",")]
    shapes = a.shapes.split(",")
    if a.pair_list is not None and a.pairs is not None:
        ap.error("--pairs or --pair-list, not both")
    count = len(PAIRS) if a.pairs is None else a.pairs
    if any(s not in SIZES for s in sizes) or any(s not in SHAPES for s in shapes) or not 1 <= count <= len(PAIRS):
        ap.error("shapes among mixed-disjoint,static; sizes among 10,100,1000,10000,100000; pairs within 1 to 16")
    try:
        pairs = PAIRS[:count] if a.pair_list is None else parse_pairs(a.pair_list)
    except ValueError as e:
        ap.error(str(e))
    a.out.mkdir(parents=True, exist_ok=True)
    return generate(a.bin, a.out, shapes, sizes, pairs, a.all_pairs)


if __name__ == "__main__":
    sys.exit(main())
