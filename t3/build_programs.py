#!/usr/bin/env python3
"""Builds round 3's Go and Rust server programs, each as one binary that holds every arm of its
program, v2 included (design/round3/end-to-end.md, sections 1 and 6; hypotheses-round2.md,
Appendix B). Run it on the system the binaries are for: on Linux the Go program's v2 arm is cgo.

    build_programs.py --cxx-build DIR --out DIR [--goamd64 v3] [--no-go] [--no-rust] [-j 4]
                      [--sanitizer none|asan|race]

  --cxx-build  the C++ server's Release build tree (CMake) whose v2 library the v2 arms use:
               DIR/server/libp2v2_c.a (Linux) or p2v2_c.lib and p2v2.dll (Windows). So v2 in the
               Go and Rust programs is the build of the C++ server's v2 arm, compiler and flags
               included.
  --sanitizer  for D5's records only (t3/sanitize.sh, t3/sanitize_w.ps1), never for a measured
               build. asan: Go with `go build -asan` (Linux only; Go has no AddressSanitizer on
               Windows) and CGO_CFLAGS and CGO_LDFLAGS -fsanitize=address, against an ASan tree's
               libp2v2_c.a; Rust with -Zsanitizer=address (RUSTC_BOOTSTRAP=1, the stable rustc's
               switch for it; the standard library stays the prebuilt one) and --target the host's,
               so build scripts are not instrumented. race: Go with `go build -race` (Go's own
               ThreadSanitizer) against an uninstrumented libp2v2_c.a, since the race runtime and
               clang's ThreadSanitizer runtime cannot share a process; Rust is not built.
  Go     server/go, `go build -trimpath`, GOAMD64 from --goamd64 (default v3: the highest level the
         laptop's Ryzen 7 5800H runs; round 2 found that a v4 build refuses to start there). On Linux
         with cgo and the tag p2v2cgo against libp2v2_c.a (CC=clang, CXX=clang++); on Windows
         without cgo, with p2v2.dll copied next to the binary, where the program loads it.
  Rust   server/rust, `cargo build --release --locked --features v2` against p2v2_c;
         server/rust/.cargo/config.toml gives `-C target-cpu=native`, as round 2's.
Writes DIR/build-info.json: the toolchains, the settings, the path and sha256 of each binary and
of the v2 library it was built with, and each program's inputs hash (t3/source_hash.py), which
D5's gate matches with the records'. The C++ server is built by CMake (bench/cmake/isa.cmake sets
its instruction set).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_hash import program_hash  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = platform.system() == "Windows"
SANITIZERS = ("none", "asan", "race")


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


def build_go(out: Path, goamd64: str, cxx: Path, sanitizer: str) -> dict:
    env = dict(os.environ, GOAMD64=goamd64)
    exe = out / ("mserver-go.exe" if WINDOWS else "mserver-go")
    cmd = ["go", "build", "-trimpath", "-o", str(exe)]
    if WINDOWS:
        if sanitizer != "none":
            raise RuntimeError(f"--sanitizer {sanitizer}: the Go program is not built under a sanitizer on Windows")
        env["CGO_ENABLED"] = "0"
        shutil.copyfile(cxx / "server" / "p2v2.dll", out / "p2v2.dll")
    else:
        flags = {"none": "", "asan": "-fsanitize=address", "race": ""}[sanitizer]
        env.update(CGO_ENABLED="1", CC="clang", CXX="clang++", CGO_LDFLAGS=f"-L{cxx / 'server'} {flags}".strip())
        if flags:
            env["CGO_CFLAGS"] = flags
        cmd += ["-tags", "p2v2cgo"]
        cmd += {"none": [], "asan": ["-asan"], "race": ["-race"]}[sanitizer]
    run(cmd + ["."], ROOT / "server" / "go", env)
    return {"binary": str(exe), "sha256": sha256(exe), "go": run(["go", "version"], ROOT), "GOAMD64": goamd64,
            "cgo": not WINDOWS, "sanitizer": sanitizer, "command": cmd + ["."],
            "cgo_env": {k: env[k] for k in ("CGO_CFLAGS", "CGO_LDFLAGS") if k in env},
            "source": program_hash(ROOT, "mserver-go")}


def host_triple() -> str:
    for line in run(["rustc", "-vV"], ROOT).splitlines():
        if line.startswith("host: "):
            return line.split(" ", 1)[1].strip()
    raise RuntimeError("rustc -vV names no host")


def build_rust(out: Path, jobs: int, cxx: Path, sanitizer: str) -> dict:
    if sanitizer == "race":
        raise RuntimeError("--sanitizer race builds the Go program only")
    env = dict(os.environ, CARGO_TARGET_DIR=str(out / "rust"), P2V2_LIB_DIR=str(cxx / "server"))
    cmd = ["cargo", "build", "--release", "--locked", "--features", "v2", "-j", str(jobs)]
    release = out / "rust" / "release"
    if sanitizer == "asan":
        # RUSTFLAGS replaces .cargo/config.toml's rustflags, so it carries their target-cpu too.
        triple = host_triple()
        env.update(RUSTC_BOOTSTRAP="1", RUSTFLAGS="-C target-cpu=native -Zsanitizer=address")
        cmd += ["--target", triple]
        release = out / "rust" / triple / "release"
    run(cmd, ROOT / "server" / "rust", env)
    exe = release / ("mserver-rs.exe" if WINDOWS else "mserver-rs")
    config = (ROOT / "server" / "rust" / ".cargo" / "config.toml").read_text(encoding="utf-8")
    return {"binary": str(exe), "sha256": sha256(exe), "rustc": run(["rustc", "--version"], ROOT),
            "cargo": run(["cargo", "--version"], ROOT), "cargo_config": config, "features": ["v2"],
            "sanitizer": sanitizer, "command": cmd, "rustflags": env.get("RUSTFLAGS"),
            "source": program_hash(ROOT, "mserver-rs")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cxx-build", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--goamd64", default="v3")
    ap.add_argument("--no-go", action="store_true")
    ap.add_argument("--no-rust", action="store_true")
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("--sanitizer", choices=SANITIZERS, default="none", help="records only, never a measured build")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    cxx = a.cxx_build.resolve()
    info = {"host": platform.platform(), "cxx_build": str(cxx), "sanitizer": a.sanitizer}
    try:
        info["v2_library"] = v2_libs(cxx)
        if not a.no_go:
            info["go"] = build_go(a.out.resolve(), a.goamd64, cxx, a.sanitizer)
        if not a.no_rust:
            info["rust"] = build_rust(a.out.resolve(), a.j, cxx, a.sanitizer)
    except RuntimeError as e:
        print(f"build_programs: {e}", file=sys.stderr)
        return 1
    (a.out / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
