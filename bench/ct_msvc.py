#!/usr/bin/env python3
"""MSVC's constant-evaluation budget, compile memory and object size per compile-time table (H7's
costs on W; hypotheses-round2.md, H7). Windows only.

    python bench/ct_msvc.py --rm-dir DIR --commit SHA --out DIR [--tables a,b] [--smoke]

The compiler is the MSVC of RegexMatcher's W record (regexmatcher-d1d73e99b-W-asan: MSVC
19.51.36246.0), from vcvarsall.bat x64 of the Visual Studio instance vswhere reports; the script
refuses another version. Its flags are those of route_ct_table_tests, the RegexMatcher target
that compiles compile-time tables, in a Release configure of RegexMatcher with the W record's
options and no sanitizer (OUT/rm-release, written here), with the bench directory in place of
tests/route/ct_tables on the include path and GoogleTest's include directories left out.

The tables are the 22 that bench/ct_steps.py covers for clang: table seed 111 of the seven shapes
at m = 10, 100 and 1,000, and the GitHub table (bench/gen/ct_<table>.cpp), each compiled alone
with -c, one at a time. For each, the budget is searched with bench/ct_steps.py's rule:
/constexpr:steps N, N = 1,048,576 (cl's default, per cl /?) times 4^k, k = 0, 1, ..., until it
compiles; if the last failure and the first pass are a factor of 4 apart, 2 times the last
failure is tried once. Each failure is classed from cl's output and exit code: budget (C2131
with "step limit"), crash (C1001, C1907, an internal compiler error, or an exit code of
0xC0000000 or above), out of memory (C1060, C1076, C3859), other. Then one more compile at the
harness budget, 33,554,432 (bench/cmake/arm-regexmatcher-v2-ct.cmake), gives the peak memory,
the wall time (information only) and the object size.

Peak memory: cl.exe is started suspended, assigned to a new Job Object and resumed; after it
exits, QueryInformationJobObject (JobObjectExtendedLimitInformation) gives PeakProcessMemoryUsed,
the peak committed private memory of a process in the job. The job's process count is kept, so a
compile that started another process shows. RegexMatcher's checkout must be at SHA before every
compile and clean. These are compiler measurements of code that is never executed, so they need
no sanitizer record.

Writes OUT/tables.jsonl (one line per table, with the method fields), OUT/logs/<table>/ (each
compile's command line and output), OUT/logs/steps.jsonl (one line per compile) and process
snapshots at the start and the end. Development: --tables static_10_s1 (table seed 1), --smoke
(one compile at the harness budget).
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import re
import shlex
import subprocess
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

BENCH = Path(__file__).resolve().parent
DEFAULT = 1 << 20
HARNESS = 33554432
MSVC_VERSION = "19.51.36246"
TABLES = [f"{s}_{m}_s111" for m in (10, 100, 1000)
          for s in ("static", "param_last", "param_first", "rest", "wild", "mixed_disjoint", "mixed_overlap")]
TABLES.append("github_203")
GEN = re.compile(r"^ct_([a-z_]+)_(\d+)(?:_s(\d+))?\.cpp$")
SEARCH_RULE = ("bench/ct_steps.py: N = 1,048,576 * 4^k (k = 0, 1, ...) until the table compiles; if the last "
               "failure and the first pass are 4 apart, 2 * the last failure is tried once")
MEMORY_METHOD = ("Job Object: JOBOBJECT_EXTENDED_LIMIT_INFORMATION.PeakProcessMemoryUsed (peak committed private "
                 "memory of a process in the job), read with QueryInformationJobObject after cl.exe exited; cl.exe "
                 "started suspended, assigned to the job, then resumed; one compile at the harness budget")

if sys.platform == "win32":
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOp", "WriteOp", "OtherOp", "ReadB", "WriteB", "OtherB")]


class BASIC_LIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]


class EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [("Basic", BASIC_LIMIT), ("Io", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class BASIC_ACCOUNTING(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                ("TotalPageFaultCount", wt.DWORD), ("TotalProcesses", wt.DWORD), ("ActiveProcesses", wt.DWORD),
                ("TotalTerminatedProcesses", wt.DWORD)]


class MEMSTATUS(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


if sys.platform == "win32":
    k32.CreateJobObjectW.restype = wt.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wt.LPCWSTR]
    k32.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
    k32.QueryInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p]
    k32.CloseHandle.argtypes = [wt.HANDLE]
    k32.GetSystemTimes.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)] * 3
    k32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMSTATUS)]
    ntdll.NtResumeProcess.argtypes = [wt.HANDLE]


def avail_phys() -> int:
    m = MEMSTATUS()
    m.dwLength = ctypes.sizeof(m)
    k32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys


def sys_times() -> tuple[int, int, int]:
    i, k, u = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
    k32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
    return i.value, k.value, u.value


def vcvars_env(out: Path, toolset: str) -> dict[str, str]:
    """The environment of vcvarsall.bat x64 -vcvars_ver=TOOLSET of the latest Visual Studio
    instance (OUT/env.cmd prints it)."""
    vswhere = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    inst = subprocess.run([str(vswhere), "-latest", "-products", "*", "-property", "installationPath"],
                          capture_output=True, text=True, check=True).stdout.strip()
    bat = Path(inst) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    cmd = out / "env.cmd"
    cmd.write_bytes(f'@echo off\r\ncall "{bat}" x64 -vcvars_ver={toolset} >nul || exit /b 1\r\nset\r\n'.encode("ascii"))
    text = subprocess.run(["cmd", "/d", "/c", str(cmd)], capture_output=True, text=True, check=True).stdout
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("="))


def cl_version(cl: str, env: dict[str, str]) -> str:
    banner = subprocess.run([cl], capture_output=True, text=True, env=env).stderr
    m = re.search(r"Version (\d+\.\d+\.\d+)", banner)
    return m.group(1) if m else ""


def configure(rm_dir: Path, build: Path, env: dict[str, str], gtest: str) -> list[dict]:
    """A Release configure of RegexMatcher with the W record's options and no sanitizer."""
    args = ["cmake", "-S", str(rm_dir), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_C_COMPILER=cl", "-DCMAKE_CXX_COMPILER=cl", "-DREGEXMATCHER_BUILD_TESTS=ON",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
    args.append(f"-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST={gtest}")
    log = build.parent / "configure.log"
    with open(log, "w", encoding="utf-8") as f:
        f.write(" ".join(args) + "\n\n")
        f.flush()
        subprocess.run(args, env=env, stdout=f, stderr=subprocess.STDOUT, check=True)
    return json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))


def flags_of(commands: list[dict], rm_dir: Path) -> tuple[str, list[str], str]:
    """(cl path, flags, source) from route_ct_table_tests' first command: the source, /Fo, /Fd, -c
    and the budget taken out, the bench directory in place of tests/route/ct_tables, GoogleTest's
    include directories left out."""
    ct_dir = str(rm_dir / "tests" / "route" / "ct_tables").lower().replace("/", "\\")
    entry = next(e for e in commands if str(Path(e["file"])).lower().startswith(ct_dir))
    argv = [a.strip('"') for a in shlex.split(entry["command"], posix=False)]
    cl, flags = str(Path(argv[0]).resolve()), []  # the long path, not CMake's 8.3 short name
    for a in argv[1:]:
        low = a.lower().replace("/", "\\")
        if a in ("-c", "/c", "/FS", "-FS") or a.startswith(("/Fo", "-Fo", "/Fd", "-Fd", "/constexpr:steps", "-constexpr:steps")):
            continue
        if low == str(Path(entry["file"])).lower():
            continue
        if ("googletest" in low or "gtest" in low or "gmock" in low) and ("-i" in low[:3] or "/i" in low[:3]
                                                                           or low.startswith(("-external:i", "/external:i"))):
            continue
        if low.rstrip("\\") in (f"-i{ct_dir}", f"/i{ct_dir}"):
            flags.append(f"-I{BENCH}")
            continue
        flags.append(a)
    if f"-I{BENCH}" not in flags:
        flags.append(f"-I{BENCH}")
    return cl, flags, entry["file"]


def classify(rc: int, text: str) -> str:
    if rc == 0:
        return "ok"
    if re.search(r"\bC1060\b|\bC1076\b|\bC3859\b|out of heap", text, re.I):
        return "out_of_memory"
    if re.search(r"\bC1001\b|\bC1907\b|access violation|internal compiler error", text, re.I) or rc >= 0xC0000000:
        return "crash"
    if "step limit" in text.lower():
        return "budget"
    return "other"


def error_lines(text: str) -> list[str]:
    return [l.rstrip() for l in text.splitlines()
            if re.search(r"error [A-Z]\d+|fatal error|step limit|access violation|internal compiler", l, re.I)][:12]


def run_cl(argv: list[str], env: dict[str, str], cwd: Path) -> dict:
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
    mem0 = avail_phys()
    s0, t0 = sys_times(), time.monotonic()
    p = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(cwd),
                         creationflags=0x4)  # CREATE_SUSPENDED
    h = wt.HANDLE(int(p._handle))
    if not k32.AssignProcessToJobObject(wt.HANDLE(job), h):
        p.kill()
        raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
    ntdll.NtResumeProcess(h)
    out, _ = p.communicate()
    wall, s1 = time.monotonic() - t0, sys_times()
    ext, acc = EXTENDED_LIMIT(), BASIC_ACCOUNTING()
    k32.QueryInformationJobObject(wt.HANDLE(job), 9, ctypes.byref(ext), ctypes.sizeof(ext), None)
    k32.QueryInformationJobObject(wt.HANDLE(job), 1, ctypes.byref(acc), ctypes.sizeof(acc), None)
    k32.CloseHandle(wt.HANDLE(job))
    rc = p.returncode & 0xFFFFFFFF
    text = out.decode("utf-8", errors="replace").replace("\r\n", "\n")
    busy = ((s1[1] - s0[1]) + (s1[2] - s0[2]) - (s1[0] - s0[0])) / 1e7
    cl_cpu = (acc.TotalUserTime + acc.TotalKernelTime) / 1e7
    return {"rc": rc, "rc_hex": f"0x{rc:08X}", "kind": classify(rc, text), "wall_s": round(wall, 3),
            "cl_cpu_s": round(cl_cpu, 3), "other_cpu_s": round(busy - cl_cpu, 3),
            "peak_memory_bytes": ext.PeakProcessMemoryUsed, "job_total_processes": acc.TotalProcesses,
            "avail_phys_before": mem0, "errors": error_lines(text), "output": text}


def git_head(rm_dir: Path, commit: str) -> None:
    head = subprocess.run(["git", "-C", str(rm_dir), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(rm_dir), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True).stdout.strip()
    if head != commit or dirty:
        sys.exit(f"ct_msvc: RegexMatcher at {rm_dir} is {head}{' with changes' if dirty else ''}, not {commit}")


def snapshot(logs: Path, tag: str) -> None:
    ps = ("Get-Date -Format o; $os=Get-CimInstance Win32_OperatingSystem; 'free_phys_kb=' + $os.FreePhysicalMemory; "
          "Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 Name,Id,"
          "@{n='WS_MB';e={[int]($_.WorkingSet64/1MB)}},@{n='CPU_s';e={[int]$_.CPU}} | Format-Table -AutoSize | "
          "Out-String -Width 200; Get-CimInstance Win32_Process -Filter \"Name='cl.exe' or Name='clang++.exe' or "
          "Name='ninja.exe'\" | Select-Object ProcessId,Name | Format-List | Out-String -Width 200")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    (logs / f"machine_{tag}.txt").write_text(out, encoding="utf-8")


class Driver:
    def __init__(self, a: argparse.Namespace, env: dict[str, str], cl: str, flags: list[str]) -> None:
        self.a, self.env, self.cl, self.flags = a, env, cl, flags
        self.logs, self.obj = a.out / "logs", a.out / "obj"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.obj.mkdir(exist_ok=True)
        self.raw = open(self.logs / "steps.jsonl", "a", encoding="utf-8")

    def compile(self, name: str, src: Path, steps: int, keep: bool) -> dict:
        git_head(self.a.rm_dir, self.a.commit)
        obj = self.obj / (f"{name}.obj" if keep else "search.obj")
        obj.unlink(missing_ok=True)
        argv = [self.cl, *self.flags, f"/constexpr:steps{steps}", f"/Fo{obj}", f"/Fd{self.obj}\\", "/FS", "-c", str(src)]
        r = run_cl(argv, self.env, self.a.out)
        r["object_bytes"] = obj.stat().st_size if r["rc"] == 0 and obj.exists() else None
        r.update({"table": name, "steps": steps, "at": dt.datetime.now().astimezone().isoformat(timespec="seconds")})
        (self.logs / name).mkdir(exist_ok=True)
        (self.logs / name / f"steps_{steps}.txt").write_text(subprocess.list2cmdline(argv) + "\n\n" + r["output"],
                                                              encoding="utf-8")
        rec = {k: v for k, v in r.items() if k != "output"}
        self.raw.write(json.dumps(rec) + "\n")
        self.raw.flush()
        print(f"  {name} steps={steps} {r['kind']} rc={r['rc_hex']} wall={r['wall_s']}s "
              f"peak={r['peak_memory_bytes']} procs={r['job_total_processes']}", flush=True)
        return rec

    def search(self, name: str, src: Path) -> dict:
        failed, passed, first_error, fails = 0, 0, "", []
        steps = DEFAULT
        while steps <= DEFAULT << 16:
            r = self.compile(name, src, steps, False)
            if r["kind"] == "ok":
                passed = steps
                break
            failed, first_error = steps, (r["errors"] or [""])[0][:200]
            fails.append({"steps": steps, "kind": r["kind"], "exit_code": r["rc_hex"], "first_error": first_error})
            if r["kind"] == "out_of_memory":
                break
            steps *= 4
        if passed and failed and passed // failed == 4:
            r = self.compile(name, src, failed * 2, False)
            if r["kind"] == "ok":
                passed = failed * 2
            else:
                failed, first_error = failed * 2, (r["errors"] or [""])[0][:200]
                fails.append({"steps": failed, "kind": r["kind"], "exit_code": r["rc_hex"], "first_error": first_error})
        return {"steps_min_passed": passed or None, "steps_max_failed": failed or None, "failures": fails}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rm-dir", type=Path, required=True, help="RegexMatcher checkout at --commit")
    ap.add_argument("--commit", required=True, help="the RegexMatcher commit measured, in full")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--googletest", required=True,
                    help="FETCHCONTENT_SOURCE_DIR_GOOGLETEST, the W record's local copy (no download)")
    ap.add_argument("--toolset", default="14.51.36231", help="vcvarsall -vcvars_ver (the W record's toolset)")
    ap.add_argument("--tables", default=",".join(TABLES))
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    a.rm_dir, a.out = a.rm_dir.resolve(), a.out.resolve()
    git_head(a.rm_dir, a.commit)
    a.out.mkdir(parents=True, exist_ok=True)
    env = vcvars_env(a.out, a.toolset)
    commands = configure(a.rm_dir, a.out / "rm-release", env, a.googletest)
    cl, flags, flags_file = flags_of(commands, a.rm_dir)
    version = cl_version(cl, env)
    if version != MSVC_VERSION:
        sys.exit(f"ct_msvc: cl is {version}, not {MSVC_VERSION} (the W record's)")
    d = Driver(a, env, cl, flags)
    common = {"compiler": f"MSVC {version}.0", "compiler_path": cl, "toolset": a.toolset, "flags": flags,
              "flags_source": f"route_ct_table_tests' command for {Path(flags_file).name} in a Release configure of "
                              f"RegexMatcher {a.commit[:9]} with the W record's options and no sanitizer, with the "
                              "bench directory in place of tests/route/ct_tables and without GoogleTest's include "
                              "directories",
              "search_rule": SEARCH_RULE, "steps_harness": HARNESS, "peak_memory_method": MEMORY_METHOD,
              "compile_s_note": "information only: wall time of one compile on W at the harness budget",
              "regexmatcher_commit": a.commit, "host": "W"}
    gen = BENCH / "gen"
    names = [t for t in a.tables.split(",") if t]
    if a.smoke:
        d.compile(names[0], gen / f"ct_{names[0]}.cpp", HARNESS, True)
        return 0
    done_path = a.out / "tables.jsonl"
    done = {json.loads(l)["table"] for l in done_path.read_text(encoding="utf-8").splitlines()
            if l.strip()} if done_path.exists() else set()
    snapshot(d.logs, "start_" + dt.datetime.now().strftime("%H%M%S"))
    with open(done_path, "a", encoding="utf-8", newline="\n") as out:
        for name in names:
            if name in done:
                continue
            src = gen / f"ct_{name}.cpp"
            m = GEN.match(src.name)
            if m is None or not src.exists():
                sys.exit(f"ct_msvc: no table {src}")
            print(f"{name}: search", flush=True)
            row = {"table": name, "shape": m.group(1).replace("_", "-"), "m": int(m.group(2)),
                   "table_seed": int(m.group(3)) if m.group(3) else None}
            row.update(d.search(name, src))
            h = d.compile(name, src, HARNESS, True)
            row.update({"harness_compile": h["kind"], "peak_memory_bytes": h["peak_memory_bytes"],
                        "job_total_processes": h["job_total_processes"], "compile_s_at_harness": h["wall_s"],
                        "cl_cpu_s_at_harness": h["cl_cpu_s"], "other_cpu_s_during_harness": h["other_cpu_s"],
                        "object_bytes": h["object_bytes"], "measured_at": h["at"]})
            row.update(common)
            out.write(json.dumps(row) + "\n")
            out.flush()
    snapshot(d.logs, "end_" + dt.datetime.now().strftime("%H%M%S"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
