#!/usr/bin/env bash
# review-grid.sh OUT_DIR: the timed grid of design/review-runs/ablations.md and boundary-arms.md on L, after the
# review build's sanitizer records (bench/sanitize_rbench.sh with REVIEW=1 and the pinned Go) and the plans'
# freeze. Run from a Papers clone with this repository as its submodule at the frozen commit (the scripts find
# lab/bin and lab/sanitizer-records at ../../..), under the lab's lablock, with a pid file and a done file:
#     GO=<the pinned go, bench/jobs/install-go.sh> RM_COMMIT=<full sha> REGEXMATCHER_DIR=<git archive of it> \
#         nohup ~/lab/Papers/lab/bin/lablock bash <clone>/papers/typed-routing/bench/jobs/review-grid.sh <OUT_DIR> \
#         > <OUT_DIR>.log 2>&1 &
#     echo $! > <OUT_DIR>.pid
# 1. build and gate: one rbench build with every arm, the default ones and the review ones (arms_for.py none
#    --review: 34 arms), which also builds the adversarial tool and the review tests (build.sh: clang,
#    Release, what every target compiled hashed); GO first on PATH and given as -DRB_GO, so the Go arms are
#    built with the pinned Go (cmake/arm-nethttp.cmake stops on any other). Then the records gate
#    (check_records.py against the committed records and pins). Nothing is timed unless it passes.
# 2. tests, untimed: every ctest of the build (the adversarial tool's, and the review arms': the ablation
#    copies against the pinned headers and their marked changes, every variant's answers against the pinned
#    code, the copy's normalized lookup code equal to the pinned code's (objdump), the C-boundary arms' real
#    call in the timed loop and no link-time optimisation); the normalized lookup code size of each ablation
#    arm (tools/code_size.py: code-size.tsv); and the grid's plan, written without running anything
#    (run_grid.sh with PLAN_ONLY=1), which must have the plan's 7,056 processes. A failure stops the job
#    before any timing. CHECK_ONLY=1 stops here.
# 3. the grid: run_grid.sh over 21 arms, one process per arm, cell and seed pair, in one order shuffled with
#    SEED (default 20261104), on CPU (default 2) under taskset, every process kept (a crash or a timeout is a
#    line with its status and exit code):
#      the ablation set (ablations.md): regexmatcher-v2, -copy, -ab-linear, -ab-hashed, -ab-noexact,
#        -ab-bytes and null, at the seven shapes and m = 10, 100, 1,000, 10,000 and 100,000;
#      the boundary set (boundary-arms.md): regexmatcher-v2-capi, capi-null, rust-null,
#        regexmatcher-v2-goloop, null-no405, matchit, actix-router, path-tree, gin, httprouter, nethttp, chi,
#        uwebsockets and glaze, at the seven shapes and m = 10 and 100 (run_grid.sh's SCOPE); v2 and null
#        at those cells come from the ablation set;
#    each on the sixteen seed pairs (table seeds 111 to 126, ring seeds 211 to 226): 7 x 35 x 16 + 14 x 14 x 16
#    = 7,056 processes. run_grid.sh also runs the agreement test and the probes of every arm, and checks every
#    query of any process whose agreement pass stopped at its budget (verified.jsonl).
# 4. the analysis (analysis/ablations.py, analysis/boundary.py): ablations.json, ablations.tex, ablations.csv,
#    boundary.json, boundary.tex, boundary.csv. The .tex files are the macros (Abl..., Bnd...) that go to
#    results/review-runs/ after the run.
# OUT_DIR keeps grid/ (run_grid.sh's whole output: cells.jsonl, plan.txt, env.txt, pin.json, toolchain.txt,
# stderr.log, agree.jsonl, probes.jsonl, verified.jsonl, exit.txt), gate.json, build.log, inputs.json,
# v2-include.json, rb_isa.h, symbols.tsv, adversarial-symbols.tsv, provenance.txt, ctest.txt, code-size.tsv,
# plan-check/ (the plan written without running), the analysis outputs and review-grid.log.
# OUT_DIR.done holds the time and how the job ended ("done", or "STOPPED:" and the reason, or "incomplete").
#
# Environment: GO, RM_COMMIT and REGEXMATCHER_DIR (required), RECORDS (default the Papers repo's
# lab/sanitizer-records), INPUTS_HASH_PY, SEED, CPU, CELL_TIMEOUT (default 1800, run_grid.sh's), PIN (pin.sh;
# default the Papers repo's lab/bin/pin.sh), ALLOW_UNPINNED=1, CHECK_ONLY=1 (build, gate, tests and the plan;
# time nothing).
#
# Downloads: what rbench's build fetches (pins.cmake, each by sha256; Cargo.lock and go.sum checked by cargo
# and go). Nothing else.
#
# The whole job is one function, read completely before it runs.
set -uo pipefail

ABLATION_ARMS="regexmatcher-v2 regexmatcher-v2-copy regexmatcher-v2-ab-linear regexmatcher-v2-ab-hashed \
regexmatcher-v2-ab-noexact regexmatcher-v2-ab-bytes null"
BOUNDARY_ARMS="regexmatcher-v2-capi capi-null rust-null regexmatcher-v2-goloop null-no405 matchit actix-router \
path-tree gin httprouter nethttp chi uwebsockets glaze"
PLANNED=7056  # 7 arms x 35 cells x 16 pairs + 14 arms x 14 cells x 16 pairs

main() {
    local out=${1:?usage: review-grid.sh OUT_DIR}
    mkdir -p "$out"
    out=$(cd "$out" && pwd)
    status=incomplete
    trap 'echo "$(date -Is) $status" > "'"$out"'.done"' EXIT
    exec > >(tee -a "$out/review-grid.log") 2>&1
    local here paper papers bench
    here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    paper=$(cd "$here/../.." && pwd)
    papers=$(cd "$paper/../.." && pwd)
    bench=$paper/bench
    local rm_commit=${RM_COMMIT:-} rm_dir=${REGEXMATCHER_DIR:-} go=${GO:-}
    [ -n "$rm_commit" ] && [ -d "$rm_dir" ] || {
        status="STOPPED: set RM_COMMIT (the full RegexMatcher commit) and REGEXMATCHER_DIR (a git archive of it)"
        echo "$status"; exit 2; }
    [ -n "$go" ] && [ -x "$go" ] || {
        status="STOPPED: set GO to the pinned go binary (bench/jobs/install-go.sh)"; echo "$status"; exit 2; }
    rm_dir=$(cd "$rm_dir" && pwd)
    export PATH="$(dirname "$go"):$PATH" GOTOOLCHAIN=local
    local records=${RECORDS:-$papers/lab/sanitizer-records}
    local inputs_py=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
    local seed=${SEED:-20261104} cpu=${CPU:-2} timeout_s=${CELL_TIMEOUT:-1800}
    local pin=${PIN:-$papers/lab/bin/pin.sh}
    [ -z "$(git -C "$paper" status --porcelain -- bench analysis)" ] || {
        status="STOPPED: the paper clone has local changes under bench/ or analysis/"; echo "$status"; exit 2; }
    echo "review-grid start $(date -Is), Papers $(git -C "$papers" rev-parse HEAD), paper $(git -C "$paper" rev-parse HEAD),"
    echo "  RegexMatcher $rm_commit from $rm_dir, $("$go" version), host $(uname -n) $(uname -r), $(clang++ --version | head -1)"

    # ------------------------------------------------------------ 1. build and gate
    local build=$out/build compiler arms
    arms=$(python3 "$bench/arms_for.py" none --review)
    REGEXMATCHER_DIR="$rm_dir" INPUTS_HASH_PY="$inputs_py" bash "$bench/build.sh" "$build" \
        "-DRB_ARMS=$arms" "-DREGEXMATCHER_COMMIT=$rm_commit" "-DRB_GO=$go" || {
        status="STOPPED: the build failed ($build.log)"; echo "$status"; tail -40 "$build.log"; exit 1; }
    local a missing=""
    for a in $ABLATION_ARMS $BOUNDARY_ARMS; do
        "$build/rbench" list | cut -f1 | grep -qx "$a" || missing="$missing $a"
    done
    [ -z "$missing" ] && [ -x "$build/adversarial" ] && [ -x "$build/test_ablation" ] || {
        status="STOPPED: the build lacks arms or tools:${missing:- adversarial or test_ablation}"; echo "$status"; exit 1; }
    compiler=$(sed -n 's/^-- The CXX compiler identification is //p' "$build.log" | head -1)
    python3 "$bench/check_records.py" --records "$records" --inputs "$build.inputs.json" --compiler "$compiler" \
        --pins "$bench/cmake/pins.cmake" --out "$out/gate.json" || {
        status="STOPPED: the sanitizer records do not cover what this build compiled; nothing timed"; echo "$status"; exit 1; }
    echo "gate passed: rbench with $(echo "$arms" | tr ';' '\n' | wc -l) arms and the adversarial tool, RegexMatcher $rm_commit, $compiler"
    cp "$build.log" "$out/build.log"
    cp "$build.inputs.json" "$out/inputs.json"
    cp "$build.v2-include.json" "$out/v2-include.json"
    cp "$build/rb-isa/rb_isa.h" "$out/rb_isa.h"
    cp "$build.symbols.tsv" "$out/symbols.tsv"
    cp "$build.adversarial-symbols.tsv" "$out/adversarial-symbols.tsv"
    {
        echo "code_commit: $(git -C "$bench" log -1 --format=%H -- main.cpp core arms cmake tools CMakeLists.txt coverage.json)"
        echo "repo_head: $(git -C "$paper" rev-parse HEAD)"
        echo "papers_head: $(git -C "$papers" rev-parse HEAD)"
        echo "regexmatcher_dir: $rm_dir"
        echo "regexmatcher_commit: $rm_commit"
        echo "compiler: $compiler"
        echo "go: $("$go" version) ($go)"
        echo "isa: $(sed -n 's/^-- isa: //p' "$build.log" | head -1) (rb_isa.h)"
        echo "binary_sha256: $(sha256sum "$build/rbench" | cut -d' ' -f1)"
        echo "arms_built: $arms"
        echo "seed: $seed"
        echo "cpu: $cpu"
        echo "cell_timeout_s: $timeout_s"
        echo "date: $(date -Is)"
    } >"$out/provenance.txt"

    # ------------------------------------------------------------ 2. tests, code size and the plan (untimed)
    (cd "$build" && ctest --output-on-failure) >"$out/ctest.txt" 2>&1 || {
        status="STOPPED: the build's tests failed ($out/ctest.txt); nothing timed"; echo "$status"; tail -30 "$out/ctest.txt"; exit 1; }
    tail -3 "$out/ctest.txt"
    local march
    march=$(sed -n 's/^RB_MARCH:STRING=//p' "$build/CMakeCache.txt")
    python3 "$bench/tools/code_size.py" --cxx "$(sed -n 's/^CMAKE_CXX_COMPILER:[A-Z]*=//p' "$build/CMakeCache.txt")" \
        --regexmatcher "$rm_dir" --out "$out/code-size.tsv" --label "review-grid-$(basename "$out")" \
        ${march:+-- "-march=$march"} >/dev/null || {
        status="STOPPED: the code size of the ablation arms could not be read, or the copy is not the pinned code"
        echo "$status"; exit 1; }
    local scope="" n_plan
    for a in $BOUNDARY_ARMS; do scope="$scope $a:100:16"; done
    ARMS="$ABLATION_ARMS $BOUNDARY_ARMS" SCOPE="$scope" REPS=16 SEED="$seed" CPU="$cpu" PIN=none ALLOW_UNPINNED=1 \
        PLAN_ONLY=1 bash "$bench/run_grid.sh" "$build/rbench" "$out/plan-check" >/dev/null || {
        status="STOPPED: the plan could not be written"; echo "$status"; exit 1; }
    n_plan=$(wc -l <"$out/plan-check/plan.txt")
    [ "$n_plan" -eq "$PLANNED" ] || {
        status="STOPPED: the plan has $n_plan processes, not $PLANNED"; echo "$status"; exit 1; }
    echo "plan: $n_plan processes, seed $seed, CPU $cpu"
    if [ "${CHECK_ONLY:-0}" = 1 ]; then
        status="done: CHECK_ONLY, built, gated and tested, plan of $n_plan processes written, nothing timed"
        echo "$status"
        exit 0
    fi

    # ------------------------------------------------------------ 3. the grid
    local rc
    ARMS="$ABLATION_ARMS $BOUNDARY_ARMS" SCOPE="$scope" REPS=16 SEED="$seed" CPU="$cpu" CELL_TIMEOUT="$timeout_s" \
        PIN="$pin" ALLOW_UNPINNED="${ALLOW_UNPINNED:-0}" bash "$bench/run_grid.sh" "$build/rbench" "$out/grid"
    rc=$?
    cmp -s "$out/plan-check/plan.txt" "$out/grid/plan.txt" || echo "WARNING: the grid's plan differs from the plan checked"
    echo "grid end $(date -Is): run_grid.sh exit $rc, $(wc -l <"$out/grid/cells.jsonl") lines of $(wc -l <"$out/grid/plan.txt") planned"

    # ------------------------------------------------------------ 4. the analysis
    local arc brc
    python3 "$paper/analysis/ablations.py" "$out/grid" --code-size "$out/code-size.tsv" --out "$out/ablations.json" \
        --macros "$out/ablations.tex" --csv "$out/ablations.csv" >"$out/ablations.txt" 2>&1
    arc=$?
    python3 "$paper/analysis/boundary.py" "$out/grid" --out "$out/boundary.json" --macros "$out/boundary.tex" \
        --csv "$out/boundary.csv" >"$out/boundary.txt" 2>&1
    brc=$?
    echo "grid_exit=$rc ablations_exit=$arc boundary_exit=$brc $(cat "$out/grid/exit.txt" 2>/dev/null)" >"$out/exit.txt"
    status="done: $(cat "$out/exit.txt")"
    echo "review-grid $status $(date -Is)"
}

main "$@"
exit
