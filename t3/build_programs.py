#!/usr/bin/env python3
"""Builds round 3's Go and Rust server programs, each as one binary that holds every arm of its
program, v2 included (design/round3/end-to-end.md, sections 1 and 6; hypotheses-round2.md,
Appendix B). Run it on the system the binaries are for: on Linux the Go program's v2 arm is cgo.

    build_programs.py --cxx-build DIR --out DIR [--goamd64 v3] [--no-go] [--no-rust] [-j 4]

  --cxx-build  the C++ server's Release build tree (CMake) whose v2 library the v2 arms use:
               DIR/server/libp2v2_c.a (Linux) or p2v2_c.lib and p2v2.dll (Windows). So v2 in the
               Go and Rust programs is the build of the C++ server's v2 arm, compiler and flags
               included.
  Go     server/go, `go build -trimpath`, GOAMD64 from --goamd64 (default v3: the highest level the
         laptop's Ryzen 7 5800H runs; round 2 found that a v4 build refuses to start there). On Linux
         with cgo and the tag p2v2cgo against libp2v2_c.a (CC=clang, CXX=clang++); on Windows
         without cgo, with p2v2.dll copied next to the binary, where the program loads it.
  Rust   server/rust, `cargo build --release --locked --features v2` against p2v2_c;
         server/rust/.cargo/config.toml gives `-C target-cpu=native`, as round 2's.
Writes DIR/build-info.json: the toolchains, the settings, and the path and sha256 of each binary
and of the v2 library it was built with. The C++ server is built by CMake (bench/cmake/isa.cmake
sets its instruction set).
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = platform.system() == "Windows"


def run(cmd, cwd, env=None) -> str:
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{p.stdout}\n{p.stderr}")
    return p.stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def v2_libs(cxx: Path) -> dict:
    names = ["p2v2_c.lib", "p2v2.dll"] if WINDOWS else ["libp2v2_c.a"]
    libs = {}
    for name in names:
        p = cxx / "server" / name
        if not p.is_file():
            raise RuntimeError(f"{p} is missing: build the targets p2v2_c and p2v2 in {cxx}")
        libs[name] = {"path": str(p), "sha256": sha256(p)}
    return libs


def build_go(out: Path, goamd64: str, cxx: Path) -> dict:
    env = dict(os.environ, GOAMD64=goamd64)
    exe = out / ("mserver-go.exe" if WINDOWS else "mserver-go")
    cmd = ["go", "build", "-trimpath", "-o", str(exe)]
    if WINDOWS:
        env["CGO_ENABLED"] = "0"
        shutil.copyfile(cxx / "server" / "p2v2.dll", out / "p2v2.dll")
    else:
        env.update(CGO_ENABLED="1", CC="clang", CXX="clang++", CGO_LDFLAGS=f"-L{cxx / 'server'}")
        cmd += ["-tags", "p2v2cgo"]
    run(cmd + ["."], ROOT / "server" / "go", env)
    return {"binary": str(exe), "sha256": sha256(exe), "go": run(["go", "version"], ROOT), "GOAMD64": goamd64,
            "cgo": not WINDOWS}


def build_rust(out: Path, jobs: int, cxx: Path) -> dict:
    env = dict(os.environ, CARGO_TARGET_DIR=str(out / "rust"), P2V2_LIB_DIR=str(cxx / "server"))
    run(["cargo", "build", "--release", "--locked", "--features", "v2", "-j", str(jobs)], ROOT / "server" / "rust", env)
    exe = out / "rust" / "release" / ("mserver-rs.exe" if WINDOWS else "mserver-rs")
    config = (ROOT / "server" / "rust" / ".cargo" / "config.toml").read_text(encoding="utf-8")
    return {"binary": str(exe), "sha256": sha256(exe), "rustc": run(["rustc", "--version"], ROOT),
            "cargo": run(["cargo", "--version"], ROOT), "cargo_config": config, "features": ["v2"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cxx-build", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--goamd64", default="v3")
    ap.add_argument("--no-go", action="store_true")
    ap.add_argument("--no-rust", action="store_true")
    ap.add_argument("-j", type=int, default=4)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    cxx = a.cxx_build.resolve()
    info = {"host": platform.platform(), "cxx_build": str(cxx)}
    try:
        info["v2_library"] = v2_libs(cxx)
        if not a.no_go:
            info["go"] = build_go(a.out.resolve(), a.goamd64, cxx)
        if not a.no_rust:
            info["rust"] = build_rust(a.out.resolve(), a.j, cxx)
    except RuntimeError as e:
        print(f"build_programs: {e}", file=sys.stderr)
        return 1
    (a.out / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
