#!/usr/bin/env python3
"""Builds round 3's Go and Rust server programs with round 2's instruction-set rule
(design/round3/end-to-end.md, section 6; hypotheses-round2.md, Appendix B).

    build_programs.py --out DIR [--goamd64 v3] [--goos linux] [--no-go] [--no-rust] [-j 4]

  Go     server/go, `go build -trimpath`, GOAMD64 from --goamd64 (default v3: the highest level the
         laptop's Ryzen 7 5800H runs; round 2 found that a v4 build refuses to start there). With
         --goos it cross-builds with CGO_ENABLED=0 (the desktop's Linux checks).
  Rust   server/rust, `cargo build --release --locked`; server/rust/.cargo/config.toml gives
         `-C target-cpu=native`, so the binary is for the build host's CPU, as round 2's.
Writes DIR/build-info.json with the toolchains and the settings used. The C++ server is built by
CMake (bench/cmake/isa.cmake sets its instruction set).
"""
import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, cwd, env=None) -> str:
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{p.stdout}\n{p.stderr}")
    return p.stdout.strip()


def build_go(out: Path, goamd64: str, goos: str) -> dict:
    env = dict(os.environ, GOAMD64=goamd64)
    name = "mserver-go"
    if goos:
        env.update(GOOS=goos, GOARCH="amd64", CGO_ENABLED="0")
        name += f"-{goos}"
    elif platform.system() == "Windows":
        name += ".exe"
    exe = out / name
    run(["go", "build", "-trimpath", "-o", str(exe), "."], ROOT / "server" / "go", env)
    return {"binary": str(exe), "go": run(["go", "version"], ROOT), "GOAMD64": goamd64, "GOOS": goos or "host"}


def build_rust(out: Path, jobs: int) -> dict:
    env = dict(os.environ, CARGO_TARGET_DIR=str(out / "rust"))
    run(["cargo", "build", "--release", "--locked", "-j", str(jobs)], ROOT / "server" / "rust", env)
    exe = out / "rust" / "release" / ("mserver-rs.exe" if platform.system() == "Windows" else "mserver-rs")
    config = (ROOT / "server" / "rust" / ".cargo" / "config.toml").read_text(encoding="utf-8")
    return {"binary": str(exe), "rustc": run(["rustc", "--version"], ROOT), "cargo": run(["cargo", "--version"], ROOT),
            "cargo_config": config}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--goamd64", default="v3")
    ap.add_argument("--goos", default="")
    ap.add_argument("--no-go", action="store_true")
    ap.add_argument("--no-rust", action="store_true")
    ap.add_argument("-j", type=int, default=4)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    info = {"host": platform.platform()}
    try:
        if not a.no_go:
            info["go"] = build_go(a.out, a.goamd64, a.goos)
        if not a.no_rust:
            info["rust"] = build_rust(a.out, a.j)
    except RuntimeError as e:
        print(f"build_programs: {e}", file=sys.stderr)
        return 1
    (a.out / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
