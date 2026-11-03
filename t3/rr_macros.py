#!/usr/bin/env python3
"""Round 3's macros and table bodies for the paper, from its analysis files and record facts.

    python t3/rr_macros.py [--design design/round3] [--records results/round3/records.json] [--out results/round3]

Reads floor-L.json and floor-W.json (t3/rr_results.py's output wrapped with its inputs), records.json
(t3/rr_records.py) and the committed campaign plan t3/plans/rr-W.json (rr-L.json differs only in paths, arms and
its comment), and writes OUT/macros.tex and the table bodies OUT/tables/*.tex. records.json must hold exactly the
records the analysis files list (floor-L.json, floor-W.json and rr-W.json; job, file and sha256), and each A/A
round it names must give the floor's |d|; otherwise nothing is written (exit 2).

Nothing is typed by hand: every number comes from those files, rounded by analysis/macros_util.py's rules (half
away from zero: ns one decimal, req/s whole, percentages one decimal); a negative number gets a math minus and no
negative zero; a missing one (an SD of one value, a floor without a counted A/A pair) prints as "none" in a macro
and empty in a table. Macro names are letters only, start with RThree and repeat none of round 2's
(writing_pack.py pull refuses a repeated name). Systems are named as the paper names them, Linux and Windows;
programs by language, C++ (Cpp), Go and Rust; sizes by m, Thousand and HundredThousand.

Per system, program and size: v2's median and SD of ns per request, its median req/s and routing cost (against the
no-router baseline), the runner-up, v2's lead over it (ns, and percent of the runner-up's time), the rounds v2 is
ahead of it out of the rounds both count, the floor (the A/A run's largest |d|), whether the lead clears it, the
round that set the floor and its start after the A/A run's first window, the A/A entries' medians and d median,
and the k-server run's spread (range and SD of the entries' medians, pooled within-process SD, least and largest
median). Per system: contestants, routers, window counts by verdict, rounds run again, the system's uptime at the
campaign job's start, the overloaded contestants, the neighbour pairs other than v2's lead and how many clear.
Overall: the plan's settings, the cells where v2's lead clears, and t3/rr_records.py's start check (the Windows
A/A runs' first START_S, and the largest departure in the first seconds of every other record).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(HERE))
import p2run  # noqa: E402
from macros_util import Macros, SIZE_WORD, count, fixed, listing, nanoseconds, tt  # noqa: E402

SYSTEMS = (("linux", "Linux", "L"), ("windows", "Windows", "W"))
PROGRAMS = (("mserver", "Cpp", "C++"), ("mserver-go", "Go", "Go"), ("mserver-rs", "Rust", "Rust"))
ARM_TEXT = {"v2": "RegexMatcher", "null": "no router (baseline)"}
TOLERANCE_NS = 1e-6


class InputsError(Exception):
    """records.json does not belong to the analysis files: nothing is written."""


def cell_of(m: int) -> str:
    return f"mixed-disjoint/m{m}/t111"


def arm_text(arm: str) -> str:
    return ARM_TEXT.get(arm, tt(arm))


def whole(x: float) -> str:
    return fixed(x, 0)


def pct(x: float) -> str:
    return fixed(x, 1)


def num(x: float | None, fmt=nanoseconds, missing: str = "") -> str:
    """A number for LaTeX text: a math minus for a negative one, never a negative zero, `missing` for none."""
    if x is None:
        return missing
    s = fmt(x)
    if s.startswith("-"):
        s = s[1:] if float(s[1:].replace("{,}", "")) == 0 else "\\ensuremath{-}" + s[1:]
    return s


def mnum(x: float | None, fmt=nanoseconds) -> str:
    return num(x, fmt, "none")


def stat(s: dict, key: str, field: str) -> float | None:
    return s[key].get(field)


def contestant(prog: dict, arm: str) -> dict:
    return next(s for s in prog["contestants"] if s["arm"] == arm)


def add_settings(mc: Macros, plan: dict) -> None:
    mc.add("RThreeRounds", count(plan["rounds"]))
    mc.add("RThreeWindowSeconds", fixed(plan["window_s"], 1))
    mc.add("RThreeLeadInSeconds", fixed(plan["warmup_s"], 1), "p2gen's lead-in before each window")
    mc.add("RThreeServerWarmupSeconds", fixed(plan["server_warmup_s"], 0))
    mc.add("RThreeConnections", count(plan["connections"]))
    mc.add("RThreeOthersMaxPercent", count(plan["others_max_pct"]))
    mc.add("RThreeErrorShareMaxPercent", fixed(100 * plan["error_share_max"], 1))
    mc.add("RThreeGenBusyMaxPercent", whole(plan["generator_busy_max_pct"]), "the generator's CPUs, over a window")
    mc.add("RThreeClockDriftMaxPercent", whole(100 * plan["clock_drift_max"]), "from the session's clock reading")
    mc.add("RThreeSampleSpanMs", whole(1000 * p2run.SPAN_TOLERANCE_S), "the samples' span against the window")
    mc.add("RThreeSettleSharePercent", whole(100 * p2run.SETTLE_SHARE), "the runner's constant, the same in both runs")
    mc.add("RThreeSettleLimitSeconds", whole(p2run.SETTLE_LIMIT_S))
    small, large = plan["sizes"]
    mc.add("RThreeSizeSmall", count(small))
    mc.add("RThreeSizeLarge", count(large))
    (table, ring), = plan["pairs"]
    mc.add("RThreeTableSeed", count(table))
    mc.add("RThreeRingSeed", count(ring))


def add_setup(mc: Macros, plan: dict, systems: dict) -> None:
    """The measured systems and pins: the OS from the campaign records' session lines, the toolchains the bring-up
    refuses to differ from (t3/labsteps.py EXPECT), the routers round 3 changed against round 2 (the server's version
    labels in server/cmake/pins-round3.cmake, server/go/go.mod, server/rust/Cargo.lock), and the CPU placement."""
    import labsteps
    sessions = {s: systems[s]["rr"]["session"] for s in ("linux", "windows")}
    mc.add("RThreeCpu", sessions["linux"]["cpu_model"].removesuffix(" with Radeon Graphics"))
    mc.add("RThreeLinuxKernel", re.search(r"^Linux-(\d+\.\d+\.\d+)", sessions["linux"]["os"]).group(1))
    mc.add("RThreeWindowsBuild", re.search(r"^Windows-\d+-10\.0\.(\d+)", sessions["windows"]["os"]).group(1))
    mc.add("RThreeClangVersion", labsteps.EXPECT["EXPECT_CLANG"], "clang on Linux, clang-cl on Windows")
    mc.add("RThreeGoVersion", labsteps.EXPECT["EXPECT_GO"].removeprefix("go"), "also net/http's")
    mc.add("RThreeRustcVersion", labsteps.EXPECT["EXPECT_RUST"])
    pins = (ROOT / "server" / "cmake" / "pins-round3.cmake").read_text(encoding="utf-8")
    labels = re.search(r'set\(MSERVER_ROUND3_VERSIONS "([^"]+)"\)', pins).group(1)
    for arm, word in (("crow", "Crow"), ("cpp-httplib", "CppHttplib"), ("drogon", "Drogon")):
        mc.add(f"RThreeVer{word}", re.search(rf"(?:^|\|){re.escape(arm)}=\S+ (v[\d.]+)", labels).group(1))
    gomod = (ROOT / "server" / "go" / "go.mod").read_text(encoding="utf-8")
    for module, word in (("github.com/julienschmidt/httprouter", "Httprouter"), ("github.com/gin-gonic/gin", "Gin"),
                         ("github.com/go-chi/chi/v5", "Chi")):
        mc.add(f"RThreeVer{word}", re.search(rf"^\s*{re.escape(module)} (v\S+)$", gomod, re.M).group(1))
    lock = (ROOT / "server" / "rust" / "Cargo.lock").read_text(encoding="utf-8")
    for crate, word in (("matchit", "Matchit"), ("path-tree", "PathTree"), ("actix-router", "ActixRouter"),
                        ("hyper", "Hyper"), ("tokio", "Tokio")):
        mc.add(f"RThreeVer{word}", re.search(rf'^name = "{re.escape(crate)}"\nversion = "([^"]+)"', lock, re.M).group(1))
    gen_first, gen_last = plan["cpus"]["generator"].split("-")
    run_first, run_last = plan["housekeeping_cpus"].split("-")
    mc.add("RThreeServerCpu", count(plan["cpus"]["server"]))
    mc.add("RThreeGenCpuFirst", count(int(gen_first)))
    mc.add("RThreeGenCpuLast", count(int(gen_last)))
    mc.add("RThreeRunnerCpuFirst", count(int(run_first)))
    mc.add("RThreeRunnerCpuLast", count(int(run_last)))


def add_cell(mc: Macros, name: str, an: dict, rec: dict, program: str, m: int) -> bool:
    """One system, program and size; returns whether v2's lead clears the floor."""
    cell = cell_of(m)
    prog = an["rr"]["cells"][cell]["programs"][program]
    if not prog["ranking"] or prog["ranking"][0] != "v2" or len(prog["ranking"]) < 2:
        raise ValueError(f"{name}: v2 is not first, or has no runner-up")
    v2, runner = contestant(prog, "v2"), prog["ranking"][1]
    floor = an["floor"][cell][program]
    lead = floor["neighbours"][0]
    if (lead["ahead"], lead["behind"]) != ("v2", runner):
        raise ValueError(f"{name}: the floor's first pair is not v2 and the runner-up")
    runner_ns = contestant(prog, runner)["ns_per_request"]["median"]
    mc.add(f"{name}VtwoNs", mnum(stat(v2, "ns_per_request", "median")))
    mc.add(f"{name}VtwoNsSd", mnum(stat(v2, "ns_per_request", "sd")))
    mc.add(f"{name}VtwoReqs", mnum(stat(v2, "req_s", "median"), whole))
    mc.add(f"{name}VtwoCost", mnum(prog["routing_cost_ns_per_request"]["v2"].get("median")), "against no router")
    mc.add(f"{name}RunnerUp", tt(runner))
    mc.add(f"{name}RunnerUpNs", mnum(runner_ns))
    mc.add(f"{name}Lead", mnum(lead["gap_ns"]))
    mc.add(f"{name}LeadPercent", mnum(100 * lead["gap_ns"] / runner_ns, pct), "of the runner-up's time")
    ahead = prog["v2_above_competitor_in_rounds"][runner]
    mc.add(f"{name}AheadRounds", count(ahead["v2_above"]))
    mc.add(f"{name}AheadOf", count(ahead["rounds_both_count"]), "rounds both count")
    mc.add(f"{name}Floor", mnum(floor["aa_largest_abs_d_ns"]))
    mc.add(f"{name}Clears", "clears" if lead["clears"] else "does not clear")
    aa = an["aa"]["cells"][cell]["programs"][program]
    mc.add(f"{name}AaEntryZeroNs", mnum(stat(aa["entries"][0], "ns_per_request", "median")))
    mc.add(f"{name}AaEntryOneNs", mnum(stat(aa["entries"][1], "ns_per_request", "median")))
    mc.add(f"{name}AaDMedian", mnum(aa["d_ns"].get("median")), "entry 0 minus entry 1")
    fr = rec["floor_rounds"].get(cell, {}).get(program)
    mc.add(f"{name}FloorRound", count(fr["round"]) if fr else "none")
    mc.add(f"{name}FloorRoundOffset", mnum(fr and fr["offset_s"], whole), "s after the A/A run's first window")
    k = an["aak"]["cells"][cell]["programs"][program]
    medians = [e["ns_per_request"]["median"] for e in k["entries"] if e["ns_per_request"]["n"]]
    mc.add(f"{name}KSpan", mnum(k["medians_ns"].get("range")))
    mc.add(f"{name}KSd", mnum(k["medians_ns"].get("sd")))
    mc.add(f"{name}KWithin", mnum(k["within_process_sd_ns"]), "pooled within-process SD")
    mc.add(f"{name}KLow", mnum(min(medians) if medians else None))
    mc.add(f"{name}KHigh", mnum(max(medians) if medians else None))
    return lead["clears"]


def add_records(mc: Macros, word: str, recs: dict) -> None:
    for kind, label in (("aa", "Aa"), ("rr", "Campaign"), ("aak", "K")):
        w = recs[kind]["windows"]
        for status in ("valid", "invalid", "overloaded"):
            mc.add(f"RThree{word}{label}{status.capitalize()}", count(w["by_status"].get(status, 0)))
        mc.add(f"RThree{word}{label}RerunRounds", count(w["rerun_rounds"]))
    mc.add(f"RThree{word}UptimeSeconds", whole(recs["rr"]["job_record"]["uptime_s"]),
           "the system's uptime at the campaign job's start")


def add_system(mc: Macros, word: str, an: dict, recs: dict, sizes: list[int]) -> list[str]:
    """Returns the cells, in words, where v2's lead does not clear."""
    not_clear = []
    for program, pword, ptext in PROGRAMS:
        for m in sizes:
            if not add_cell(mc, f"RThree{word}{pword}{SIZE_WORD[m]}", an, recs["aa"], program, m):
                not_clear.append(f"{ptext} at $m={count(m)}$ on {word}")
    first = an["rr"]["cells"][cell_of(sizes[0])]["programs"]
    mc.add(f"RThree{word}Contestants", count(sum(len(p["contestants"]) for p in first.values())))
    mc.add(f"RThree{word}Routers", count(sum(len(p["contestants"]) - 2 for p in first.values())), "v2 and no router left out")
    over = sorted({s["arm"] for c in an["rr"]["cells"].values() for p in c["programs"].values()
                   for s in p["contestants"] if s["overloaded"]})
    mc.add(f"RThree{word}Overloaded", listing([tt(a) for a in over]) or "none")
    pairs = [n for c in an["floor"].values() for p in c.values() for n in p["neighbours"] if n["ahead"] != "v2"]
    mc.add(f"RThree{word}OtherPairs", count(len(pairs)))
    mc.add(f"RThree{word}OtherPairsClear", count(sum(n["clears"] for n in pairs)))
    add_records(mc, word, recs)
    return not_clear


def add_start(mc: Macros, records: list[dict], start_s: int) -> None:
    mc.add("RThreeStartSeconds", count(start_s))
    by = {(r["analysis"], r["kind"]): r for r in records}
    w, earlier = by[("floor-W.json", "aa")]["start"], by[("rr-W.json", "aa")]["start"]
    note = "percent above the campaign's median; valid windows, counted or run again"
    mc.add("RThreeStartWindows", count(w["first_windows"]), "windows of the Windows A/A run in its first seconds")
    mc.add("RThreeStartSlowLow", mnum(w["first_pct"][0], pct), note)
    mc.add("RThreeStartSlowHigh", mnum(w["first_pct"][1], pct))
    mc.add("RThreeStartLaterLow", mnum(w["later_pct"][0], pct), "the later windows of the same cells")
    mc.add("RThreeStartLaterHigh", mnum(w["later_pct"][1], pct))
    mc.add("RThreeStartEarlierLow", mnum(earlier["first_pct"][0], pct), "the Windows A/A run of the earlier job")
    mc.add("RThreeStartEarlierHigh", mnum(earlier["first_pct"][1], pct))
    mc.add("RThreeStartEarlierLaterLow", mnum(earlier["later_pct"][0], pct), "the earlier job's later windows")
    mc.add("RThreeStartEarlierLaterHigh", mnum(earlier["later_pct"][1], pct))
    mc.add("RThreeStartEarlierUptimeSeconds", whole(by[("rr-W.json", "aa")]["job_record"]["uptime_s"]),
           "the earlier Windows job's start")
    mc.add("RThreeStartClockLow", mnum(w["first_clock_mhz"][0], lambda x: fixed(x, 1)), "MHz, each window's reading")
    mc.add("RThreeStartClockHigh", mnum(w["first_clock_mhz"][1], lambda x: fixed(x, 1)))
    mc.add("RThreeStartOthersMax", mnum(w["first_others_max_pct"], lambda x: fixed(x, 2)), "percent of one CPU")
    rest = [abs(x) for key, r in by.items() if key not in (("floor-W.json", "aa"), ("rr-W.json", "aa"))
            for x in r["start"]["first_pct"] or []]
    mc.add("RThreeStartElsewhereMax", mnum(max(rest) if rest else None, pct),
           "largest |departure| in the first seconds of every other record")


def campaign_table(an: dict, m: int) -> str:
    lines = ["% Generated by t3/rr_macros.py. Columns: program, router, median req/s, SD req/s, median ns per request,",
             "% SD ns per request, routing cost ns (median, against no router), peak resident MiB, rank."]
    for i, (program, _, ptext) in enumerate(PROGRAMS):
        prog = an["rr"]["cells"][cell_of(m)]["programs"][program]
        order = prog["ranking"] + sorted(a["arm"] for a in prog["contestants"]
                                         if a["arm"] not in prog["ranking"] and a["arm"] != "null") + ["null"]
        if i:
            lines.append("\\midrule")
        for j, arm in enumerate(order):
            s = contestant(prog, arm)
            cost = prog["routing_cost_ns_per_request"].get(arm) or {}
            rank = (str(prog["ranking"].index(arm) + 1) if arm in prog["ranking"] else
                    "overloaded" if s["overloaded"] else "" if arm == "null" else "not counted")
            peak = s["peak_resident_kib"]
            lines.append(" & ".join([ptext if j == 0 else "", arm_text(arm), num(stat(s, "req_s", "median"), whole),
                                     num(stat(s, "req_s", "sd"), whole), num(stat(s, "ns_per_request", "median")),
                                     num(stat(s, "ns_per_request", "sd")), num(cost.get("median")),
                                     num(peak / 1024 if peak is not None else None, lambda x: fixed(x, 1)),
                                     rank]) + " \\\\")
    return "\n".join(lines) + "\n"


def floor_table(an: dict, sizes: list[int]) -> str:
    lines = ["% Generated by t3/rr_macros.py. Columns: program, m, ahead, behind, gap ns per request, floor ns per",
             "% request (the A/A run's largest |d|; empty without a counted A/A pair), clears."]
    for i, (program, _, ptext) in enumerate(PROGRAMS):
        if i:
            lines.append("\\midrule")
        for m in sizes:
            f = an["floor"][cell_of(m)][program]
            for n in f["neighbours"]:
                lines.append(" & ".join([ptext, count(m), arm_text(n["ahead"]), arm_text(n["behind"]),
                                         num(n["gap_ns"]), num(f["aa_largest_abs_d_ns"]),
                                         "yes" if n["clears"] else "no"]) + " \\\\")
    return "\n".join(lines) + "\n"


def kserver_table(systems: dict, sizes: list[int]) -> str:
    lines = ["% Generated by t3/rr_macros.py. Columns: system, program, m, range of the processes' medians, their SD,",
             "% pooled within-process SD, the A/A run's largest |d| (the floor); all ns per request."]
    for i, (system, word, _) in enumerate(SYSTEMS):
        an = systems[system]
        if i:
            lines.append("\\midrule")
        for program, _, ptext in PROGRAMS:
            for m in sizes:
                k = an["aak"]["cells"][cell_of(m)]["programs"][program]
                lines.append(" & ".join([word, ptext, count(m), num(k["medians_ns"].get("range")),
                                         num(k["medians_ns"].get("sd")), num(k["within_process_sd_ns"]),
                                         num(an["floor"][cell_of(m)][program]["aa_largest_abs_d_ns"])]) + " \\\\")
    return "\n".join(lines) + "\n"


def check_inputs(records: list[dict], wrapped: dict[str, dict]) -> None:
    """records.json holds exactly the analysis files' records, and each A/A round it names gives the floor's |d|."""
    for name, w in wrapped.items():
        want = {(i["job"], i["file"], i["sha256"]) for i in w["inputs"]}
        got = {(r["job"], r["file"], r["sha256"]) for r in records if r["analysis"] == name}
        if want != got:
            raise InputsError(f"records.json's records of {name} are not the ones it lists")
        for r in (r for r in records if r["analysis"] == name and r["kind"] == "aa"):
            floors = w["analysis"]["systems"][r["system"]].get("floor")
            for cell, programs in (r["floor_rounds"].items() if floors else ()):
                for program, fr in programs.items():
                    limit = floors[cell][program]["aa_largest_abs_d_ns"]
                    if limit is None or abs(abs(fr["d_ns"]) - limit) > TOLERANCE_NS:
                        raise InputsError(f"{name} {cell} {program}: the round's |d| is not the floor")
    if {r["analysis"] for r in records} - set(wrapped):
        raise InputsError("records.json holds records of another analysis file")


def generate(design: Path, records_path: Path, plan_path: Path) -> tuple[str, dict[str, str]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    sizes = plan["sizes"]
    records = json.loads(records_path.read_text(encoding="utf-8"))
    wrapped = {f"floor-{letter}.json": json.loads((design / f"floor-{letter}.json").read_text(encoding="utf-8"))
               for _, _, letter in SYSTEMS}
    wrapped["rr-W.json"] = json.loads((design / "rr-W.json").read_text(encoding="utf-8"))
    check_inputs(records["records"], wrapped)
    systems, recs = {}, {}
    for system, _, letter in SYSTEMS:
        systems[system] = wrapped[f"floor-{letter}.json"]["analysis"]["systems"][system]
        recs[system] = {r["kind"]: r for r in records["records"] if r["analysis"] == f"floor-{letter}.json"}
    mc = Macros()
    add_settings(mc, plan)
    add_setup(mc, plan, systems)
    mc.add("RThreeKCopies", count(len(systems["linux"]["aak"]["cells"][cell_of(sizes[0])]["programs"]["mserver"]["entries"])))
    not_clear = []
    for system, word, _ in SYSTEMS:
        not_clear += add_system(mc, word, systems[system], recs[system], sizes)
    cells = len(SYSTEMS) * len(PROGRAMS) * len(sizes)
    over = [f"{ptext} at $m={count(m)}$ on {word}" for system, word, _ in SYSTEMS for program, _, ptext in PROGRAMS
            for m in sizes
            if (systems[system]["aak"]["cells"][cell_of(m)]["programs"][program]["medians_ns"].get("range") or 0)
            > (systems[system]["floor"][cell_of(m)][program]["aa_largest_abs_d_ns"] or float("inf"))]
    mc.add("RThreeKSpanOverFloor", count(len(over)), "cells where the k processes' span exceeds the floor")
    mc.add("RThreeKSpanOverFloorList", listing(over) or "none")
    mc.add("RThreeCells", count(cells), "system, program and size")
    mc.add("RThreeCellsClear", count(cells - len(not_clear)))
    mc.add("RThreeNotClearList", listing(not_clear) or "none")
    add_start(mc, records["records"], records["start_s"])
    head = ("% Generated by t3/rr_macros.py from design/round3/floor-L.json, floor-W.json, rr-W.json, "
            "results/round3/records.json and t3/plans/rr-W.json. Do not edit.\n")
    tables = {f"campaign-{word.lower()}-{SIZE_WORD[m].lower()}.tex": campaign_table(systems[s], m)
              for s, word, _ in SYSTEMS for m in sizes}
    tables.update({f"floor-{word.lower()}.tex": floor_table(systems[s], sizes) for s, word, _ in SYSTEMS})
    tables["kserver.tex"] = kserver_table(systems, sizes)
    return head + mc.text(), tables


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--design", type=Path, default=ROOT / "design" / "round3")
    ap.add_argument("--records", type=Path, default=ROOT / "results" / "round3" / "records.json")
    ap.add_argument("--plan", type=Path, default=HERE / "plans" / "rr-W.json")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "round3")
    a = ap.parse_args(argv)
    try:
        macros, tables = generate(a.design, a.records, a.plan)
    except InputsError as e:
        print(f"rr_macros: refused: {e}", file=sys.stderr)
        return 2
    (a.out / "tables").mkdir(parents=True, exist_ok=True)
    (a.out / "macros.tex").write_text(macros, encoding="utf-8", newline="\n")
    for name, text in tables.items():
        (a.out / "tables" / name).write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
