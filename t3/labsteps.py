"""Shared steps of round 3's laptop jobs (t3/jobs/bringup.py, t3/sanitize.py, t3/jobs/records.py), the
same on both systems of the laptop: Linux (its Arch, clang) and Windows (its Windows, clang-cl inside
the Visual Studio environment that vcvars64.bat sets).

  tool_env      the environment with the pinned toolchains first on PATH. Every location has a
                laptop default that an environment variable of the same name replaces:
                  both     P2_GO (Go's bin), RUSTUP_HOME, CARGO_HOME, RUSTUP_TOOLCHAIN (1.99.0)
                  Linux    MSAN_LIBCXX (the instrumented libc++ of round 2's records)
                  Windows  P2_LLVM (LLVM 22.1.8: clang-cl, lld-link, the ASan runtime), P2_BOOST_ROOT
                           (the Boost 1.92.0 tree), P2_MESON (meson.py of meson 1.12.1),
                           P2_LIBEVENT_SRC (libevent 2.1.13-stable's source), P2_RAPIDJSON_WRAP (the two
                           files of Pistache's RapidJSON wrap), LAB_VCVARS, LAB_CMAKE, LAB_NINJA (lab/laptop)
                and GOPROXY=direct, GOTOOLCHAIN=local (Go checks modules against go.sum and never
                fetches a toolchain).
  versions      the versions of every tool, checked against EXPECT_CLANG (22.1.8), EXPECT_GO
                (go1.27.3) and EXPECT_RUST (1.99.0).
  configure     the CMake configure and build of the paper's root project, Release, under a
                sanitizer or none.
  inputs        what each measured C++ target compiled (lab/bin/inputs_hash.py, project mode).
  keep_logs     a record's logs kept as round 2's bench/keep_record_logs.sh keeps them.
Untimed: nothing here reads a time.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

WINDOWS = os.name == "nt"
T3 = Path(__file__).resolve().parent
ROOT = T3.parent
PY = sys.executable
HOME = Path.home()
LAPTOP_DEFAULTS = {
    "P2_GO": str(HOME / "opt" / "go-1.27.3" / "bin") if WINDOWS else str(HOME / "opt" / "p2" / "go1.27.3" / "bin"),
    "RUSTUP_HOME": str(HOME / "opt" / "rustup"),
    "CARGO_HOME": str(HOME / "opt" / "cargo"),
    "RUSTUP_TOOLCHAIN": "1.99.0",
    "MSAN_LIBCXX": str(HOME / "opt" / "libcxx-msan-gcc"),
    "P2_LLVM": str(HOME / "opt" / "llvm-22.1.8"),
    "P2_BOOST_ROOT": str(HOME / "opt" / "boost-1.92.0"),
    "P2_MESON": str(HOME / "opt" / "meson-1.12.1" / "meson.py"),
    "P2_LIBEVENT_SRC": str(HOME / "opt" / "libevent-2.1.13-stable"),
    "P2_RAPIDJSON_WRAP": str(HOME / "opt" / "rapidjson-1.1.0"),
    "LAB_VCVARS": r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat",
    "LAB_CMAKE": r"C:\Program Files\CMake\bin\cmake.exe" if WINDOWS else "cmake",
    "LAB_NINJA": str(HOME / "opt" / "ninja-1.13.2" / "ninja.exe") if WINDOWS else "ninja",
}
EXPECT = {"EXPECT_CLANG": "22.1.8", "EXPECT_GO": "go1.27.3", "EXPECT_RUST": "1.99.0"}
SANITIZER_ENV = {
    "asan": {"ASAN_OPTIONS": "detect_leaks=1:detect_stack_use_after_return=1:strict_string_checks=1:symbolize=1",
             "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1"},
    "tsan": {"TSAN_OPTIONS": "halt_on_error=1:second_deadlock_stack=1", "GORACE": "halt_on_error=1"},
    "msan": {"MSAN_OPTIONS": "halt_on_error=1:print_stats=1:fast_unwind_on_fatal=1"},
}
# Windows' AddressSanitizer has no LeakSanitizer; the rest of the options are the Linux ones.
SANITIZER_ENV_W = {"asan": {"ASAN_OPTIONS": "detect_stack_use_after_return=1:strict_string_checks=1:symbolize=1"}}
REPO_URL = "https://github.com/Alex-Tsvetanov/paper-typed-routing.git"


class StepError(Exception):
    pass


def setting(name: str) -> str:
    return os.environ.get(name) or LAPTOP_DEFAULTS[name]


def vcvars_env(vcvars: str) -> dict:
    """The environment vcvars64.bat leaves, read from `set` in the same cmd."""
    if not Path(vcvars).is_file():
        raise StepError(f"no {vcvars}")
    p = subprocess.run(f'cmd /d /s /c ""{vcvars}" >nul && set"', capture_output=True, text=True)
    if p.returncode != 0:
        raise StepError(f"{vcvars} failed: {p.stderr.strip()[-300:]}")
    env = {}
    for line in p.stdout.splitlines():
        k, sep, v = line.partition("=")
        if sep and k:
            env[k] = v
    return env


def tool_env(sanitizer: str = "none") -> dict:
    env = vcvars_env(setting("LAB_VCVARS")) if WINDOWS else dict(os.environ)
    if WINDOWS:
        for k, v in os.environ.items():
            if k.upper().startswith(("LAB_", "P2_", "EXPECT_")) or k.upper() in ("INPUTS_HASH_PY", "RECORDS_LOGS"):
                env[k] = v
    for k in ("RUSTUP_HOME", "CARGO_HOME", "RUSTUP_TOOLCHAIN"):
        env[k] = setting(k)
    first = [setting("P2_GO"), str(Path(setting("CARGO_HOME")) / "bin")]
    if WINDOWS:
        llvm = Path(setting("P2_LLVM"))
        first += [str(llvm / "bin")]
        if sanitizer == "asan":
            first += [str(p) for p in sorted((llvm / "lib" / "clang").glob("*/lib/windows"))]
        first += [str(Path(setting("LAB_CMAKE")).parent), str(Path(setting("LAB_NINJA")).parent)]
    key = next((k for k in env if k.upper() == "PATH"), "PATH")
    env[key] = os.pathsep.join(first + [env.get(key, "")])
    env.update(GOPROXY="direct", GOTOOLCHAIN="local", PYTHONUTF8="1")
    env.update((SANITIZER_ENV_W if WINDOWS else SANITIZER_ENV).get(sanitizer, {}))
    return env


def output(cmd: list, env: dict) -> str:
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=env)
    except OSError as e:
        return f"(not found: {e})"
    return (p.stdout + p.stderr).strip()


def versions(env: dict, check: bool = True) -> dict:
    cxx = "clang-cl" if WINDOWS else "clang++"
    v = {"compiler": output([cxx, "--version"], env).splitlines()[0], "go": output(["go", "version"], env),
         "rustc": output(["rustc", "--version"], env), "cargo": output(["cargo", "--version"], env),
         "cmake": output([cmake_exe(), "--version"], env).splitlines()[0], "ninja": output([ninja_exe(), "--version"], env),
         "python": sys.version.split()[0]}
    if check:
        want = {k: os.environ.get(k) or d for k, d in EXPECT.items()}
        if f"clang version {want['EXPECT_CLANG']}" not in v["compiler"]:
            raise StepError(f"the compiler is not clang {want['EXPECT_CLANG']}: {v['compiler']}")
        if not v["go"].startswith(f"go version {want['EXPECT_GO']} "):
            raise StepError(f"go is not {want['EXPECT_GO']}: {v['go']}")
        if not v["rustc"].startswith(f"rustc {want['EXPECT_RUST']} "):
            raise StepError(f"rustc is not {want['EXPECT_RUST']}: {v['rustc']}")
    return v


def cmake_exe() -> str:
    return setting("LAB_CMAKE")


def ninja_exe() -> str:
    return setting("LAB_NINJA")


def ctest_exe() -> str:
    c = Path(cmake_exe())
    return str(c.with_name("ctest" + c.suffix)) if c.parent != Path(".") else "ctest"


def cmake_args(sanitizer: str, extra: list | None = None) -> list:
    args = ["-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_MAKE_PROGRAM={ninja_exe()}"]
    if WINDOWS:
        cl = (Path(setting("P2_LLVM")) / "bin" / "clang-cl.exe").as_posix()
        args += [f"-DCMAKE_C_COMPILER={cl}", f"-DCMAKE_CXX_COMPILER={cl}"]
        boost = Path(setting("P2_BOOST_ROOT"))
        if (boost / "boost" / "version.hpp").is_file():
            args.append(f"-DP2_BOOST_ROOT={boost.as_posix()}")
        if sanitizer == "asan":
            args.append("-DP2_SANITIZER=address")
        elif sanitizer != "none":
            raise StepError(f"Windows records are ASan only, not {sanitizer}")
    else:
        args += ["-DCMAKE_C_COMPILER=clang", "-DCMAKE_CXX_COMPILER=clang++"]
        args += {"none": [], "asan": ["-DP2_SANITIZER=address+undefined"], "tsan": ["-DP2_SANITIZER=thread"],
                 "msan": ["-DP2_SANITIZER=memory", f"-DP2_MSAN_LIBCXX={setting('MSAN_LIBCXX')}"]}[sanitizer]
    return args + list(extra or [])


def run(cmd: list, log: Path, env: dict, cwd: Path | None = None, append: bool = False) -> int:
    with open(log, "ab" if append else "wb") as f:
        f.write(("== " + " ".join(str(c) for c in cmd) + "\n").encode())
        f.flush()
        try:
            return subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT, env=env, cwd=cwd).returncode
        except OSError as e:
            f.write(f"cannot run: {e}\n".encode())
            return 127


def configure(build: Path, sanitizer: str, log: Path, env: dict, jobs: int, extra: list | None = None,
              targets: list | None = None) -> tuple[int, list]:
    args = cmake_args(sanitizer, extra)
    rc = run([cmake_exe(), "-S", ROOT, "-B", build, *args], log, env)
    if rc == 0:
        tgt = [x for t in (targets or []) for x in ("--target", t)]
        rc = run([cmake_exe(), "--build", build, "-j", str(jobs), *tgt], log, env, append=True)
    return rc, args


def compiler_of(log: Path) -> str:
    m = re.search(r"^-- The CXX compiler identification is (.+?)\s*$", log.read_text(errors="replace"), re.MULTILINE)
    return m.group(1) if m else "unknown"


def exe(path: Path) -> Path:
    return path.with_suffix(".exe") if WINDOWS else path


def mserver_arms(build: Path, env: dict) -> list:
    """Every router arm of a build's mserver (its --router '?' list), v1 included where built."""
    text = output([exe(build / "server" / "mserver"), "--router", "?"], env)
    line = next((l for l in text.splitlines() if l.startswith("router arms:")), "")
    if not line:
        raise StepError(f"{build}'s mserver lists no arm: {text[-300:]}")
    return line.split(":", 1)[1].split()


def inputs(build: Path, prefix: Path, env: dict, ih: Path) -> int:
    """PREFIX.inputs.json and PREFIX.v2-include.json for the measured C++ targets: mserver and the
    libraries it links (a target's hash covers its own translation units only), one arm_<name> per
    external arm, v2's C interface, p2gen with its libraries, and e2e_requests; RegexMatcher v2 is the
    dependency root "regexmatcher", hashed apart under regexmatcher/include/ for mserver_arms and
    p2v2_c. Returns the number of targets."""
    arms = mserver_arms(build, env)
    targets = ["mserver", "mserver_arms", "mserver_http1", "mserver_loop", "mserver_external", "p2v2_c", "p2v2",
               "p2gen", "p2gen_core", "p2gen_net", "e2e_requests"]
    if "v1" in arms:
        targets.append("mserver_v1")
    targets += ["arm_" + a.replace("-", "_") for a in arms if a not in ("v2", "v1", "null")]
    common = ["--root-label", "project", "--config-key", "CMAKE_BUILD_TYPE",
              "--dep-root", "regexmatcher=RegexMatcher_SOURCE_DIR"]
    log = Path(str(prefix) + ".inputs.log")
    t = [x for n in targets for x in ("--target", n)]
    if run([PY, ih, "--build", f"p2r3={build}", *t, *common, "--out", f"{prefix}.inputs.json"], log, env) != 0:
        raise StepError(f"inputs_hash.py failed; see {log}")
    if run([PY, ih, "--build", f"p2r3={build}", "--target", "mserver_arms", "--target", "p2v2_c", *common,
            "--label-hash", "regexmatcher/include/", "--out", f"{prefix}.v2-include.json"], log, env, append=True) != 0:
        raise StepError(f"inputs_hash.py --label-hash failed; see {log}")
    return len(targets)


def inputs_hash_py() -> Path:
    p = os.environ.get("INPUTS_HASH_PY")
    if not p and os.environ.get("LAB_TOOLS"):
        p = str(Path(os.environ["LAB_TOOLS"]).parent / "bin" / "inputs_hash.py")
    if not p or not Path(p).is_file():
        raise StepError("no inputs_hash.py: set INPUTS_HASH_PY, or run inside a lab job (LAB_TOOLS)")
    return Path(p)


def git(*args: str) -> str:
    p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise StepError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def records_logs() -> Path:
    root = Path(os.environ.get("RECORDS_LOGS") or HOME / "lab" / "records-logs")
    if root.as_posix().startswith("/tmp/"):
        raise StepError("record logs never go to /tmp")
    return root


def check_logs(name: str) -> None:
    root = records_logs()
    if (root / name).exists() or (root / f"{name}.tar.gz").exists():
        raise StepError(f"{root / name} or its archive exists; record logs are never overwritten")


def keep_logs(name: str, sources: list) -> tuple[str, str]:
    """Copies SOURCES into RECORDS_LOGS/NAME/, writes its SHA256SUMS, packs NAME.tar.gz and writes
    NAME.tar.gz.sha256, as bench/keep_record_logs.sh does. Returns the archive's path and sha256."""
    check_logs(name)
    root = records_logs()
    d = root / name
    d.mkdir(parents=True)
    for s in map(Path, sources):
        if s.is_dir():
            shutil.copytree(s, d / s.name)
        elif s.is_file():
            shutil.copy2(s, d / s.name)
    sums = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  ./{f.relative_to(d).as_posix()}"
            for f in sorted(p for p in d.rglob("*") if p.is_file())]
    (d / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    tar = root / f"{name}.tar.gz"
    with tarfile.open(tar, "w:gz") as t:
        t.add(d, arcname=name)
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    (root / f"{name}.tar.gz.sha256").write_text(f"{sha}  {name}.tar.gz\n", encoding="utf-8", newline="\n")
    return str(tar), sha


def load_plan(path: Path, p2gen: Path, sets: Path, programs: list, sizes: list, comment: str) -> None:
    """A count-mode plan for t3/p2run.py over PROGRAMS [(name, binary, arms, env)], pinned as the
    campaign is (P2_CPU_SERVER, P2_CPU_GEN, P2_CPU_HOUSE; default 14, 2-13, 0-1, lab/laptop/README.md)."""
    progs = []
    for name, binary, arms, penv in programs:
        p = {"name": name, "path": str(binary), "arms": list(arms)}
        if penv:
            p["env"] = dict(penv)
        progs.append(p)
    plan = {"_comment": comment, "p2gen": str(p2gen), "data_root": str(sets), "shapes": ["mixed-disjoint", "static"],
            "sizes": sizes, "pairs": [[111, 211]],
            "cpus": {"server": int(os.environ.get("P2_CPU_SERVER", "14")), "generator": os.environ.get("P2_CPU_GEN", "2-13")},
            "housekeeping_cpus": os.environ.get("P2_CPU_HOUSE", "0-1"), "connections": 64, "ready_timeout_s": 300,
            "stop_timeout_s": 60, "count_limit_s": 1200, "verify_sets": True, "programs": progs}
    path.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
