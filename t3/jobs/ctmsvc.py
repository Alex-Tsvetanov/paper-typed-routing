#!/usr/bin/env python3
"""H7's MSVC compile costs on the laptop's Windows (hypotheses-round3.md: round 2's H7 procedure, bench/ct_msvc.py,
with the laptop's MSVC). Windows only. The job times nothing itself; ct_msvc.py's wall times are information only.

    ctmsvc.py OUT_DIR

Steps, in order; the first that fails stops the job with exit 2, and OUT_DIR/steps.txt says which:
  clean    the paper clone has no local changes;
  sources  RegexMatcher and GoogleTest cloned into OUT_DIR/src (a fresh folder: the job stops if it exists), each
           checked out at its full commit: RM_COMMIT, the RegexMatcher round 2 measured, and GTEST_COMMIT, v1.15.2,
           RegexMatcher's own pin (external/CMakeLists.txt at RM_COMMIT); each must then give that commit to git
           rev-parse and have a clean working tree. The commit is the check: no archive sha256 is involved;
  ct       bench/ct_msvc.py --rm-dir OUT_DIR/src/RegexMatcher --commit RM_COMMIT --googletest OUT_DIR/src/googletest
           --msvc-version EXPECT_MSVC --out OUT_DIR/ct, its output in OUT_DIR/ct.log; ct_msvc.py refuses another cl.
Exit: 2 for a step that failed before ct_msvc.py, else ct_msvc.py's exit code.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
import labsteps as L  # noqa: E402

RM_URL = "https://github.com/cpp-for-everything/RegexMatcher.git"
RM_COMMIT = "d1d73e99b7b26f54ba75354f4880780ece32e8ed"
GTEST_URL = "https://github.com/google/googletest.git"
GTEST_COMMIT = "b514bdc898e2951020cbdca1304b75f5950d1f59"
EXPECT_MSVC = "19.51.36248"   # lab/laptop/versions.md: the laptop's cl for x64 (toolset 14.51.36231)


class Refused(Exception):
    pass


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise Refused(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def clone_at(url: str, commit: str, dest: Path) -> None:
    git("clone", "--quiet", "--no-checkout", url, str(dest))
    git("-C", str(dest), "checkout", "--quiet", "--detach", commit)
    head = git("-C", str(dest), "rev-parse", "HEAD")
    if head != commit or git("-C", str(dest), "status", "--porcelain"):
        raise Refused(f"{dest} is at {head}, or has changes, not a clean {commit}")


def ct_command(out: Path) -> list[str]:
    return [sys.executable, str(ROOT / "bench" / "ct_msvc.py"), "--rm-dir", str(out / "src" / "RegexMatcher"),
            "--commit", RM_COMMIT, "--googletest", str(out / "src" / "googletest"), "--msvc-version", EXPECT_MSVC,
            "--out", str(out / "ct")]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: ctmsvc.py OUT_DIR", file=sys.stderr)
        return 2
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    steps = out / "steps.txt"
    step = "clean"
    try:
        if os.name != "nt":
            raise Refused("Windows only")
        if L.git("status", "--porcelain", "--untracked-files=no"):
            raise Refused("the paper clone has local changes")
        step = "sources"
        src = out / "src"
        if src.exists():
            raise Refused(f"{src} exists")
        src.mkdir()
        clone_at(RM_URL, RM_COMMIT, src / "RegexMatcher")
        clone_at(GTEST_URL, GTEST_COMMIT, src / "googletest")
    except (Refused, L.StepError) as e:
        steps.write_text(f"{step}: refused: {e}\n", encoding="utf-8")
        print(f"ctmsvc: {step}: refused: {e}", file=sys.stderr)
        return 2
    steps.write_text("clean: ok\nsources: ok\n", encoding="utf-8")
    with open(out / "ct.log", "w", encoding="utf-8") as log:
        rc = subprocess.run(ct_command(out), stdout=log, stderr=subprocess.STDOUT).returncode
    with open(steps, "a", encoding="utf-8") as f:
        f.write(f"ct: exit {rc}\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
