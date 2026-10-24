#!/usr/bin/env python3
"""The inputs hash of round 3's Go and Rust server programs, for D5's records and gate.

The C++ targets are hashed by the Papers repo's lab/bin/inputs_hash.py from what Ninja compiled.
Go and Rust have no Ninja log, so a program's inputs are every file git tracks under its folder
(server/go: the .go files, go.mod, go.sum, and server/capi/p2v2.h, which cgo compiles on Linux;
server/rust: Cargo.toml, Cargo.lock, build.rs,
.cargo/config.toml, src/), whatever the build tags pick: a change to any of them makes a new hash.
The third-party code is pinned by go.sum and Cargo.lock, which are among the files. The v2 library
they link is the C++ target p2v2_c (or p2v2 on Windows), hashed with the C++ targets.

The hash has inputs_hash.py's form: the sha256 of the sorted lines "<path>\\t<sha256 of the file>\\n",
each path "project/" plus its path in the repository with forward slashes, file contents read with
CRLF as LF.

    source_hash.py [--root DIR] server/go server/rust     prints one JSON object
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The Linux Go program compiles server/capi/p2v2.h through cgo, so the header is among its inputs.
PROGRAMS = {"mserver-go": ("server/go", "server/capi/p2v2.h"), "mserver-rs": ("server/rust",)}


def tracked(root: Path, paths) -> list:
    paths = [paths] if isinstance(paths, str) else list(paths)
    p = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *paths], capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"git ls-files {' '.join(paths)} in {root}: {p.stderr.decode(errors='replace').strip()}")
    files = sorted(f for f in p.stdout.decode("utf-8").split("\0") if f)
    if not files:
        raise RuntimeError(f"git tracks no file under {' '.join(paths)} in {root}")
    return files


def folder_hash(root: Path, folder) -> dict:
    files = {}
    for f in tracked(root, folder):
        data = (root / f).read_bytes().replace(b"\r\n", b"\n")
        files[f"project/{f}"] = hashlib.sha256(data).hexdigest()
    text = "".join(f"{p}\t{h}\n" for p, h in sorted(files.items()))
    return {"folder": folder, "inputs_hash": hashlib.sha256(text.encode()).hexdigest(), "files": len(files)}


def program_hash(root: Path, program: str) -> dict:
    return folder_hash(root, PROGRAMS[program])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("folders", nargs="+")
    a = ap.parse_args()
    try:
        print(json.dumps({f: folder_hash(a.root.resolve(), f) for f in a.folders}, indent=1))
    except (RuntimeError, OSError) as e:
        print(f"source_hash: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
