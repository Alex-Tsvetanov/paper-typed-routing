#!/usr/bin/env bash
# adversarial.sh OUT_DIR: the timed job of design/review-runs/adversarial.md on L, after the tool's
# sanitizer records (bench/sanitize_rbench.sh, whose build with the regexmatcher-v2 arm has the tool)
# and the plan's freeze. Run from a Papers clone with this repository as its submodule at the frozen
# commit (the scripts find lab/bin and lab/sanitizer-records at ../../.., or in the clone PAPERS names),
# under the lab's lablock, with a pid file and a done file:
#     RM_COMMIT=<full sha> REGEXMATCHER_DIR=<git archive of it> nohup ~/lab/Papers/lab/bin/lablock \
#         bash <clone>/papers/typed-routing/bench/jobs/adversarial.sh <OUT_DIR> > <OUT_DIR>.log 2>&1 &
#     echo $! > <OUT_DIR>.pid
# The job fails closed: a command whose status it needs is checked, and it stops (a "STOPPED:" line)
# rather than go on with a plan, a build or a tree it did not verify.
# 1. build and gate: rbench's build with the regexmatcher-v2 arm, which builds the tool (build.sh:
#    clang, Release, what every target compiled hashed, the tool's among them); then the records
#    gate (check_records.py against the committed records and pins). Nothing is timed unless it passes.
#    The tool's code_commit is read from the file its cmake wrote (adversarial-code-commit.txt, from
#    cmake/tool-adversarial.cmake), the same commit every result line carries, so a run has one.
# 2. tests, untimed: the tool's ctest (the unit test, the self-test of every query of every table
#    through the pinned code and the counting copy, the copy against the pinned headers). A failure
#    stops the job before any timing.
# 3. the cells: the tool's 44 cells, REPS processes each (default 10), in an order shuffled with SEED
#    (default 20261103), one process per cell and replicate on CPU (default 2, as run_grid.sh) under
#    taskset, each `adversarial cell --cell ID --rep K --ring RING` with rbench's 21 epochs and a ring of
#    RING copies of the cell's query (default 4096, rbench's; always passed to the tool and recorded).
#    The plan must have REPS x 44 lines, or, with CELLS, REPS lines for each id of CELLS (all of them ids
#    the tool lists). A process that exits nonzero or runs past CELL_TIMEOUT (default 900 s) keeps its
#    raw stdout (stdout-failed.log) and its line, if it printed one, in cells.jsonl with status
#    "crash" or "timeout" and its exit code (tool_status holds the status the tool printed); one that
#    printed nothing gets a line with the status and the exit code alone. Every process is kept.
# 4. the analysis (analysis/adversarial.py, told the ring): summary.json and adversarial.tex. The job
#    ends with exit 0 whatever the bound is (a failing bound is a result); the decision, "bound holds",
#    "bound fails" or "undecided", is in the done line and in exit.txt. Only a run of all 44 cells,
#    21 epochs, not quick, can hold.
# OUT_DIR keeps cells.jsonl, stderr.log (with a "## cell" line before each process), stdout-failed.log
# (the raw stdout of each process that did not end well), plan.txt, cells.txt, env.txt, pin.json,
# gate.json, build.log, inputs.json, v2-include.json, rb_isa.h, symbols.tsv (where the tool's timed
# functions landed, build.sh), provenance.txt, ctest.txt, selftest.txt, exit.txt, analysis.txt,
# summary.json, adversarial.tex and adversarial.log. build.log is build.sh's own file (OUT_DIR/build.log).
# OUT_DIR.done holds the time and how the job ended ("done: <decision> (...)", or "STOPPED:" and the
# reason, or "incomplete" if it was killed or failed elsewhere).
#
# Environment: RM_COMMIT and REGEXMATCHER_DIR (required), PAPERS (the Papers clone whose lab/bin and
# lab/sanitizer-records are used; default the clone two levels above this repository, which is right only
# when this repository is its submodule: a job that clones this repository alone, as labrun does at
# $LAB_SRC, names the clone; the job stops if it is not a git repository), RECORDS (default
# PAPERS/lab/sanitizer-records), INPUTS_HASH_PY, REPS, SEED, CPU, RING, CELL_TIMEOUT, PIN (pin.sh; default
# PAPERS/lab/bin/pin.sh), ALLOW_UNPINNED=1, CHECK_ONLY=1 (build, gate and tests; time
# nothing), CELLS (cell ids to run instead of all 44, for development; never in the frozen run; it and
# ALLOW_UNPINNED are recorded in provenance.txt, and a CELLS run is never "bound holds").
#
# Downloads: nanobench as rbench fetches it (pins.cmake, by sha256). Nothing else.
#
# The whole job is one function, read completely before it runs.
set -uo pipefail

# stop CODE REASON...: end the job with this status line (the EXIT trap writes it to OUT_DIR.done).
stop() {
    local code=$1
    shift
    status="STOPPED: $*"
    echo "$status"
    exit "$code"
}

# A result line is one JSON object on one line.
is_result_line() {
    [[ $1 == \{*\} && $1 != *$'\n'* ]]
}

# failed_line KIND RC CELL REP RAW: the cells.jsonl line of a process that did not end well. It is
# RAW (what the process printed on stdout), if that is a JSON object, with status KIND, exit RC, and
# the status the tool printed under tool_status, so that it does not read as an ok line; else the
# cell, the replicate, the status and the exit code alone.
failed_line() {
    printf '%s' "$5" | python3 -c '
import json, sys
kind, rc, cell, rep = sys.argv[1:5]
try:
    r = json.loads(sys.stdin.read())
    if not isinstance(r, dict):
        raise ValueError
    r["tool_status"] = r.get("status")
except ValueError:
    r = {}
r.update(cell=cell, rep=int(rep), status=kind, exit=int(rc))
print(json.dumps(r, separators=(",", ":")))
' "$1" "$2" "$3" "$4" || printf '{"cell":"%s","rep":%s,"status":"%s","exit":%s}\n' "$3" "$4" "$1" "$2"
}

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
    papers=${PAPERS:-$(cd "$paper/../.." && pwd)}
    papers=$(cd "$papers" 2>/dev/null && pwd) ||
        stop 2 "PAPERS is not a directory (the Papers clone with lab/bin and lab/sanitizer-records)"
    bench=$paper/bench
    local rm_commit=${RM_COMMIT:-} rm_dir=${REGEXMATCHER_DIR:-}
    [ -n "$rm_commit" ] && [ -d "$rm_dir" ] || {
        stop 2 "set RM_COMMIT (the full RegexMatcher commit) and REGEXMATCHER_DIR (a git archive of it)"; }
    rm_dir=$(cd "$rm_dir" && pwd)
    local records=${RECORDS:-$papers/lab/sanitizer-records}
    local inputs_py=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
    local reps=${REPS:-10} seed=${SEED:-20261103} cpu=${CPU:-2} timeout_s=${CELL_TIMEOUT:-900} ring=${RING:-4096}
    local pin=${PIN:-$papers/lab/bin/pin.sh}
    local v
    for v in reps seed cpu timeout_s ring; do
        [[ ${!v} =~ ^[0-9]+$ ]] || stop 2 "$v must be a whole number, not '${!v}'"
    done
    { [ "$reps" -ge 1 ] && [ "$ring" -ge 1 ] && [ "$timeout_s" -ge 1 ]; } ||
        stop 2 "REPS, RING and CELL_TIMEOUT must be at least 1"
    local dirty paper_head papers_head
    dirty=$(git -C "$paper" status --porcelain -- bench analysis) || stop 2 "git status failed in the paper clone $paper"
    [ -z "$dirty" ] || stop 2 "the paper clone has local changes under bench/ or analysis/"
    paper_head=$(git -C "$paper" rev-parse HEAD) || stop 2 "git rev-parse failed in the paper clone $paper"
    papers_head=$(git -C "$papers" rev-parse HEAD) || stop 2 "git rev-parse failed in the Papers clone $papers"
    echo "adversarial start $(date -Is), Papers $papers_head, paper $paper_head,"
    echo "  RegexMatcher $rm_commit from $rm_dir, host $(uname -n) $(uname -r), $(clang++ --version | head -1)"

    # ------------------------------------------------------------ 1. build and gate
    local build=$out/build compiler code_commit
    REGEXMATCHER_DIR="$rm_dir" INPUTS_HASH_PY="$inputs_py" bash "$bench/build.sh" "$build" \
        "-DRB_ARMS=regexmatcher-v2" "-DREGEXMATCHER_COMMIT=$rm_commit" || {
        tail -40 "$build.log"; stop 1 "the build failed ($build.log)"; }
    [ -x "$build/adversarial" ] || stop 1 "the build has no adversarial tool"
    compiler=$(sed -n 's/^-- The CXX compiler identification is //p' "$build.log" | head -1)
    [ -n "$compiler" ] || stop 1 "the build log names no compiler ($build.log)"
    code_commit=$(cat "$build/adversarial-code-commit.txt" 2>/dev/null) || code_commit=
    [[ $code_commit =~ ^[0-9a-f]{40}$ ]] ||
        stop 1 "the build has no code commit for the tool ('$code_commit' in $build/adversarial-code-commit.txt)"
    python3 "$bench/check_records.py" --records "$records" --inputs "$build.inputs.json" --compiler "$compiler" \
        --pins "$bench/cmake/pins.cmake" --out "$out/gate.json" ||
        stop 1 "the sanitizer records do not cover what this build compiled; nothing timed"
    echo "gate passed: rbench with regexmatcher-v2 and the adversarial tool, RegexMatcher $rm_commit, $compiler"
    # build.log is build.sh's file already: $build.log is $out/build.log.
    { cp "$build.inputs.json" "$out/inputs.json" && cp "$build.v2-include.json" "$out/v2-include.json" &&
        cp "$build/rb-isa/rb_isa.h" "$out/rb_isa.h" && cp "$build.adversarial-symbols.tsv" "$out/symbols.tsv"; } ||
        stop 1 "could not copy the build's records into $out"
    {
        echo "code_commit: $code_commit"
        echo "repo_head: $paper_head"
        echo "papers_head: $papers_head"
        echo "regexmatcher_dir: $rm_dir"
        echo "regexmatcher_commit: $rm_commit"
        echo "compiler: $compiler"
        echo "isa: $(sed -n 's/^-- isa: //p' "$build.log" | head -1) (rb_isa.h)"
        echo "binary_sha256: $(sha256sum "$build/adversarial" | cut -d' ' -f1)"
        echo "seed: $seed"
        echo "reps: $reps"
        echo "cpu: $cpu"
        echo "cell_timeout_s: $timeout_s"
        echo "ring: $ring"
        echo "cells_only: ${CELLS:-(none: all 44 cells)}"
        echo "allow_unpinned: ${ALLOW_UNPINNED:-0}"
        echo "check_only: ${CHECK_ONLY:-0}"
        echo "date: $(date -Is)"
    } >"$out/provenance.txt" || stop 1 "could not write $out/provenance.txt"

    # ------------------------------------------------------------ 2. tests (untimed)
    (cd "$build" && ctest --output-on-failure) >"$out/ctest.txt" 2>&1 || {
        tail -20 "$out/ctest.txt"; stop 1 "the tool's tests failed ($out/ctest.txt); nothing timed"; }
    "$build/adversarial" self-test >"$out/selftest.txt" 2>&1 ||
        stop 1 "the self-test failed ($out/selftest.txt); nothing timed"
    tail -1 "$out/selftest.txt"
    if [ "${CHECK_ONLY:-0}" = 1 ]; then
        status="done: CHECK_ONLY, built, gated and tested, nothing timed"
        echo "$status"
        exit 0
    fi

    # ------------------------------------------------------------ 3. the cells
    local rc pinned=no
    if [ -f "$pin" ]; then
        bash "$pin" >"$out/pin.json"
        rc=$?
        if [ "$rc" -eq 0 ]; then
            pinned=yes
        elif [ "${ALLOW_UNPINNED:-0}" != 1 ]; then
            stop 1 "the host is not pinned ($(cat "$out/pin.json")); set ALLOW_UNPINNED=1 to run anyway"
        fi
    elif [ "${ALLOW_UNPINNED:-0}" != 1 ]; then
        stop 1 "no pin.sh at $pin"
    fi
    echo "pinned: $pinned" >>"$out/provenance.txt"
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
    "$build/adversarial" list >"$out/cells.txt" || stop 1 "adversarial list failed"
    [ "$(wc -l <"$out/cells.txt")" -eq 44 ] || stop 1 "the tool lists $(wc -l <"$out/cells.txt") cells, not 44"
    python3 - "$seed" "$reps" "$out/cells.txt" "${CELLS:-}" >"$out/plan.txt" <<'EOF' ||
import random, sys
seed, reps, listing, only = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4].split()
cells = [line.split("\t")[0] for line in open(listing, encoding="utf-8") if line.strip()]
unknown = sorted(set(only) - set(cells))
if unknown:
    sys.exit("CELLS names cells the tool does not list: " + " ".join(unknown))
cells = [c for c in cells if not only or c in only]
plan = [(c, k) for k in range(reps) for c in cells]
random.Random(seed).shuffle(plan)
for c, k in plan:
    print(c, k)
EOF
        stop 1 "the plan step failed (see above)"
    local want got
    if [ -n "${CELLS:-}" ]; then
        want=$((reps * $(printf '%s\n' ${CELLS:-} | sort -u | wc -l)))
    else
        want=$((reps * 44))
    fi
    got=$(wc -l <"$out/plan.txt")
    [ "$got" -ge 1 ] && [ "$got" -eq "$want" ] || stop 1 "the plan has $got processes, not $want ($out/plan.txt)"
    echo "plan: $got processes, seed $seed, CPU $cpu, ring $ring${CELLS:+, only the cells $CELLS}"
    : >"$out/cells.jsonl"
    : >"$out/stderr.log"
    : >"$out/stdout-failed.log"
    local c k line failed=0 timed_out=0 kind
    while read -r c k; do
        echo "## cell $c rep $k" >>"$out/stderr.log"
        line=$(timeout "$timeout_s" taskset -c "$cpu" "$build/adversarial" cell --cell "$c" --rep "$k" \
            --ring "$ring" 2>>"$out/stderr.log")
        rc=$?
        if [ "$rc" -eq 0 ] && is_result_line "$line"; then
            printf '%s\n' "$line" >>"$out/cells.jsonl"
            continue
        fi
        kind=crash
        [ "$rc" -eq 124 ] && kind=timeout
        { printf '## cell %s rep %s exit %s\n' "$c" "$k" "$rc"; printf '%s\n' "$line"; } >>"$out/stdout-failed.log"
        failed_line "$kind" "$rc" "$c" "$k" "$line" >>"$out/cells.jsonl"
        if [ "$kind" = timeout ]; then timed_out=$((timed_out + 1)); else failed=$((failed + 1)); fi
    done <"$out/plan.txt"
    echo "cells end $(date -Is): $(wc -l <"$out/cells.jsonl") lines, $failed crashed, $timed_out timed out"

    # ------------------------------------------------------------ 4. the analysis
    rm -f "$out/summary.json" "$out/adversarial.tex"
    python3 "$paper/analysis/adversarial.py" "$out" --ring "$ring" --out "$out/summary.json" \
        --macros "$out/adversarial.tex" >"$out/analysis.txt" 2>&1
    rc=$?
    tail -1 "$out/analysis.txt"
    # The decision is read from summary.json: the analysis exits 1 both when the bound fails and when
    # it crashed, and a run with no summary is undecided.
    local decision=undecided word=
    if [ -s "$out/summary.json" ]; then
        word=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["summary"]["decision"])' \
            "$out/summary.json") || word=
    fi
    case $word in
        holds) decision="bound holds" ;;
        fails) decision="bound fails" ;;
        undecided) decision=undecided ;;
        *) echo "the analysis left no decision (exit $rc, see $out/analysis.txt): undecided" ;;
    esac
    {
        echo "failed_cells=$failed timed_out_cells=$timed_out analysis_exit=$rc"
        echo "decision: $decision"
    } >"$out/exit.txt"
    status="done: $decision (failed_cells=$failed timed_out_cells=$timed_out analysis_exit=$rc)"
    echo "adversarial $status $(date -Is)"
    exit 0
}

main "$@"
exit
