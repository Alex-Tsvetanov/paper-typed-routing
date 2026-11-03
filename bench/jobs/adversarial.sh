#!/usr/bin/env bash
# adversarial.sh OUT_DIR: the timed job of design/review-runs/adversarial.md on L, after the tool's
# sanitizer records (bench/sanitize_rbench.sh, whose build with the regexmatcher-v2 arm has the tool)
# and the plan's freeze. Run from a Papers clone with this repository as its submodule at the frozen
# commit (the scripts find lab/bin and lab/sanitizer-records at ../../..), under the lab's lablock,
# with a pid file and a done file:
#     RM_COMMIT=<full sha> REGEXMATCHER_DIR=<git archive of it> nohup ~/lab/Papers/lab/bin/lablock \
#         bash <clone>/papers/typed-routing/bench/jobs/adversarial.sh <OUT_DIR> > <OUT_DIR>.log 2>&1 &
#     echo $! > <OUT_DIR>.pid
# 1. build and gate: rbench's build with the regexmatcher-v2 arm, which builds the tool (build.sh:
#    clang, Release, what every target compiled hashed, the tool's among them); then the records
#    gate (check_records.py against the committed records and pins). Nothing is timed unless it passes.
# 2. tests, untimed: the tool's ctest (the unit test, the self-test of every query of every table
#    through the pinned code and the counting copy, the copy against the pinned headers). A failure
#    stops the job before any timing.
# 3. the cells: the tool's 44 cells, REPS processes each (default 10), in an order shuffled with SEED
#    (default 20261103), one process per cell and replicate on CPU (default 2, as run_grid.sh) under
#    taskset, each `adversarial cell --cell ID --rep K` with the ring and epochs of rbench's defaults.
#    A process that crashes or runs past CELL_TIMEOUT (default 900 s) gets a line with its status and
#    exit code; every process is kept.
# 4. the analysis (analysis/adversarial.py): summary.json and adversarial.tex.
# OUT_DIR keeps cells.jsonl, stderr.log (with a "## cell" line before each process), plan.txt,
# cells.txt, env.txt, pin.json, gate.json, build.log, inputs.json, v2-include.json, rb_isa.h,
# symbols.tsv (where the tool's timed functions landed, build.sh), provenance.txt, ctest.txt,
# selftest.txt, exit.txt, analysis.txt, summary.json, adversarial.tex and adversarial.log.
# OUT_DIR.done holds the time and how the job ended ("done", or "STOPPED:" and the reason, or
# "incomplete" if it was killed or failed elsewhere).
#
# Environment: RM_COMMIT and REGEXMATCHER_DIR (required), RECORDS (default the Papers repo's
# lab/sanitizer-records), INPUTS_HASH_PY, REPS, SEED, CPU, CELL_TIMEOUT, PIN (pin.sh; default the
# Papers repo's lab/bin/pin.sh), ALLOW_UNPINNED=1, CHECK_ONLY=1 (build, gate and tests; time
# nothing), CELLS (cell ids to run instead of all 44, for development; never in the frozen run).
#
# Downloads: nanobench as rbench fetches it (pins.cmake, by sha256). Nothing else.
#
# The whole job is one function, read completely before it runs.
set -uo pipefail

main() {
    local out=${1:?usage: adversarial.sh OUT_DIR}
    mkdir -p "$out"
    out=$(cd "$out" && pwd)
    status=incomplete
    trap 'echo "$(date -Is) $status" > "'"$out"'.done"' EXIT
    exec > >(tee -a "$out/adversarial.log") 2>&1
    local here paper papers bench
    here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    paper=$(cd "$here/../.." && pwd)
    papers=$(cd "$paper/../.." && pwd)
    bench=$paper/bench
    local rm_commit=${RM_COMMIT:-} rm_dir=${REGEXMATCHER_DIR:-}
    [ -n "$rm_commit" ] && [ -d "$rm_dir" ] || {
        status="STOPPED: set RM_COMMIT (the full RegexMatcher commit) and REGEXMATCHER_DIR (a git archive of it)"
        echo "$status"; exit 2; }
    rm_dir=$(cd "$rm_dir" && pwd)
    local records=${RECORDS:-$papers/lab/sanitizer-records}
    local inputs_py=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
    local reps=${REPS:-10} seed=${SEED:-20261103} cpu=${CPU:-2} timeout_s=${CELL_TIMEOUT:-900}
    local pin=${PIN:-$papers/lab/bin/pin.sh}
    [ -z "$(git -C "$paper" status --porcelain -- bench analysis)" ] || {
        status="STOPPED: the paper clone has local changes under bench/ or analysis/"; echo "$status"; exit 2; }
    echo "adversarial start $(date -Is), Papers $(git -C "$papers" rev-parse HEAD), paper $(git -C "$paper" rev-parse HEAD),"
    echo "  RegexMatcher $rm_commit from $rm_dir, host $(uname -n) $(uname -r), $(clang++ --version | head -1)"

    # ------------------------------------------------------------ 1. build and gate
    local build=$out/build compiler
    REGEXMATCHER_DIR="$rm_dir" INPUTS_HASH_PY="$inputs_py" bash "$bench/build.sh" "$build" \
        "-DRB_ARMS=regexmatcher-v2" "-DREGEXMATCHER_COMMIT=$rm_commit" || {
        status="STOPPED: the build failed ($build.log)"; echo "$status"; tail -40 "$build.log"; exit 1; }
    [ -x "$build/adversarial" ] || { status="STOPPED: the build has no adversarial tool"; echo "$status"; exit 1; }
    compiler=$(sed -n 's/^-- The CXX compiler identification is //p' "$build.log" | head -1)
    python3 "$bench/check_records.py" --records "$records" --inputs "$build.inputs.json" --compiler "$compiler" \
        --pins "$bench/cmake/pins.cmake" --out "$out/gate.json" || {
        status="STOPPED: the sanitizer records do not cover what this build compiled; nothing timed"; echo "$status"; exit 1; }
    echo "gate passed: rbench with regexmatcher-v2 and the adversarial tool, RegexMatcher $rm_commit, $compiler"
    cp "$build.log" "$out/build.log"
    cp "$build.inputs.json" "$out/inputs.json"
    cp "$build.v2-include.json" "$out/v2-include.json"
    cp "$build/rb-isa/rb_isa.h" "$out/rb_isa.h"
    cp "$build.adversarial-symbols.tsv" "$out/symbols.tsv"
    {
        echo "code_commit: $(git -C "$bench" log -1 --format=%H -- tools core arms/rm_arm.hpp arms/rm_v2.hpp cmake CMakeLists.txt)"
        echo "repo_head: $(git -C "$paper" rev-parse HEAD)"
        echo "papers_head: $(git -C "$papers" rev-parse HEAD)"
        echo "regexmatcher_dir: $rm_dir"
        echo "regexmatcher_commit: $rm_commit"
        echo "compiler: $compiler"
        echo "isa: $(sed -n 's/^-- isa: //p' "$build.log" | head -1) (rb_isa.h)"
        echo "binary_sha256: $(sha256sum "$build/adversarial" | cut -d' ' -f1)"
        echo "seed: $seed"
        echo "reps: $reps"
        echo "cpu: $cpu"
        echo "cell_timeout_s: $timeout_s"
        echo "date: $(date -Is)"
    } >"$out/provenance.txt"

    # ------------------------------------------------------------ 2. tests (untimed)
    (cd "$build" && ctest --output-on-failure) >"$out/ctest.txt" 2>&1 || {
        status="STOPPED: the tool's tests failed ($out/ctest.txt); nothing timed"; echo "$status"; tail -20 "$out/ctest.txt"; exit 1; }
    "$build/adversarial" self-test >"$out/selftest.txt" 2>&1 || {
        status="STOPPED: the self-test failed ($out/selftest.txt); nothing timed"; echo "$status"; exit 1; }
    tail -1 "$out/selftest.txt"
    if [ "${CHECK_ONLY:-0}" = 1 ]; then
        status="done: CHECK_ONLY, built, gated and tested, nothing timed"
        echo "$status"
        exit 0
    fi

    # ------------------------------------------------------------ 3. the cells
    local rc
    if [ -f "$pin" ]; then
        bash "$pin" >"$out/pin.json"
        rc=$?
        if [ "$rc" -ne 0 ] && [ "${ALLOW_UNPINNED:-0}" != 1 ]; then
            status="STOPPED: the host is not pinned ($(cat "$out/pin.json")); set ALLOW_UNPINNED=1 to run anyway"
            echo "$status"; exit 1
        fi
    elif [ "${ALLOW_UNPINNED:-0}" != 1 ]; then
        status="STOPPED: no pin.sh at $pin"; echo "$status"; exit 1
    fi
    {
        echo "date: $(date -Is)"
        echo "binary: $build/adversarial"
        echo "cpu: $cpu (thread siblings: $(cat "/sys/devices/system/cpu/cpu$cpu/topology/thread_siblings_list" 2>/dev/null || echo na))"
        echo "uname: $(uname -a)"
        echo "cpu_model: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ //')"
        echo "perf_event_paranoid: $(cat /proc/sys/kernel/perf_event_paranoid)"
        echo "nmi_watchdog: $(cat /proc/sys/kernel/nmi_watchdog 2>/dev/null || echo na)"
        echo "thp_enabled: $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo na)"
        echo "governor: $(sort -u /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | tr '\n' ' ')"
        echo "boost: $(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo na)"
    } >"$out/env.txt"
    "$build/adversarial" list >"$out/cells.txt"
    python3 - "$seed" "$reps" "$out/cells.txt" "${CELLS:-}" >"$out/plan.txt" <<'EOF'
import random, sys
seed, reps, listing, only = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4].split()
cells = [line.split("\t")[0] for line in open(listing, encoding="utf-8") if line.strip()]
cells = [c for c in cells if not only or c in only]
plan = [(c, k) for k in range(reps) for c in cells]
random.Random(seed).shuffle(plan)
for c, k in plan:
    print(c, k)
EOF
    echo "plan: $(wc -l <"$out/plan.txt") processes, seed $seed, CPU $cpu"
    : >"$out/cells.jsonl"
    : >"$out/stderr.log"
    local c k line failed=0 timed_out=0 kind
    while read -r c k; do
        echo "## cell $c rep $k" >>"$out/stderr.log"
        line=$(timeout "$timeout_s" taskset -c "$cpu" "$build/adversarial" cell --cell "$c" --rep "$k" 2>>"$out/stderr.log")
        rc=$?
        if [ "$rc" -eq 0 ] && [ -n "$line" ]; then
            printf '%s\n' "$line" >>"$out/cells.jsonl"
        else
            kind=crash
            [ "$rc" -eq 124 ] && kind=timeout
            printf '{"cell":"%s","rep":%s,"status":"%s","exit":%s}\n' "$c" "$k" "$kind" "$rc" >>"$out/cells.jsonl"
            if [ "$kind" = timeout ]; then timed_out=$((timed_out + 1)); else failed=$((failed + 1)); fi
        fi
    done <"$out/plan.txt"
    echo "cells end $(date -Is): $(wc -l <"$out/cells.jsonl") lines, $failed crashed, $timed_out timed out"

    # ------------------------------------------------------------ 4. the analysis
    python3 "$paper/analysis/adversarial.py" "$out" --out "$out/summary.json" --macros "$out/adversarial.tex" \
        >"$out/analysis.txt" 2>&1
    rc=$?
    tail -1 "$out/analysis.txt"
    echo "failed_cells=$failed timed_out_cells=$timed_out analysis_exit=$rc" >"$out/exit.txt"
    status="done: $(cat "$out/exit.txt")"
    echo "adversarial $status $(date -Is)"
}

main "$@"
exit
