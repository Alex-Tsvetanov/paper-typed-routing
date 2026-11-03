#!/usr/bin/env bash
# review-grid.sh OUT_DIR: the timed grid of design/review-runs/ablations.md and boundary-arms.md on L, after the
# review build's sanitizer records (bench/sanitize_rbench.sh with REVIEW=1 and the pinned Go) and the plans'
# freeze. Run from a Papers clone with this repository as its submodule at the frozen commit (the scripts find
# lab/bin and lab/sanitizer-records at ../../.., or in the clone PAPERS names), under the lab's lablock, with a
# pid file and a done file:
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
#    call in the timed loop and no link-time optimisation), with at least one test run and ctest.txt naming
#    each of those tests as passed; the normalized lookup code size of each ablation arm
#    (tools/code_size.py: code-size.tsv); the grid's plan, written without running anything (run_grid.sh
#    with PLAN_ONLY=1), which must have the plan's 7,056 processes; and the agreement test and the probes of
#    every arm of the grid, run as run_grid.sh runs them (pre-agree.jsonl, pre-probes.jsonl, pre-stderr.log),
#    so that a disagreement or a failing probe stops the job before the grid, not after it: check_agree.py
#    must pass the agreement rows (rbench agree itself exits 1 on a disagreement that semantics.json
#    declares), every arm with a router must have agreement rows, and every probe must exit 0 and print.
#    A failure stops the job before any timing. CHECK_ONLY=1 stops here.
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
#    = 7,056 processes. run_grid.sh also runs the agreement test and the probes of every arm again, and checks
#    every query of any process whose agreement pass stopped at its budget (verified.jsonl). It runs with
#    the environment knobs that change what it runs unset (MISS, RING, ZIPF, VOCAB, NO_DECOY, RING_LAYOUT,
#    QUICK, VERIFY, PAIRS, SHAPES, SIZES, PLAN_ONLY, and GOGC, which sets the Go arms' garbage collector), so
#    that the plan checked in step 2 is the plan run, and the job ends FAILED if the two plans differ.
# 4. the analysis (analysis/ablations.py, analysis/boundary.py): ablations.json, ablations.tex, ablations.csv,
#    boundary.json, boundary.tex, boundary.csv. The .tex files are the macros (Abl..., Bnd...) that go to
#    results/review-runs/ after the run. The analysis runs even when run_grid.sh failed, so that the processes
#    kept can be read, but the job then ends FAILED (below) and its macros are not results.
# OUT_DIR keeps grid/ (run_grid.sh's whole output: cells.jsonl, plan.txt, env.txt, pin.json, toolchain.txt,
# stderr.log, agree.jsonl, probes.jsonl, verified.jsonl, exit.txt), gate.json, build.log, inputs.json,
# v2-include.json, rb_isa.h, symbols.tsv, adversarial-symbols.tsv, provenance.txt, ctest.txt, code-size.tsv,
# plan-check/ (the plan written without running), the analysis outputs and review-grid.log.
# OUT_DIR.done holds the time and how the job ended: "done" (exit 0); "STOPPED:" and the reason (exit 1 or
# 2, before any timing); "FAILED:" and exit.txt (exit 1: run_grid.sh or an analysis exited nonzero, the
# grid's plan differs from the one checked, or the grid has not one line per planned process; the outputs
# are kept); or "incomplete" (the job was killed).
#
# Environment: GO, RM_COMMIT (exactly the commit of the plans, d1d73e99b7b26f54ba75354f4880780ece32e8ed) and
# REGEXMATCHER_DIR (required), PAPERS (the Papers clone whose lab/bin and lab/sanitizer-records are used;
# default the clone two levels above this repository, which is right only when this repository is its
# submodule: a job that clones this repository alone, as labrun does at $LAB_SRC, names the clone), RECORDS
# (default PAPERS/lab/sanitizer-records), INPUTS_HASH_PY, SEED, CPU, CELL_TIMEOUT (default 1800,
# run_grid.sh's), PIN (pin.sh; default PAPERS/lab/bin/pin.sh), ALLOW_UNPINNED=1, CHECK_ONLY=1 (build, gate,
# tests, the plan, the agreement test and the probes; time nothing).
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
RM_PINNED=d1d73e99b7b26f54ba75354f4880780ece32e8ed  # the RegexMatcher commit both plans pin
# The arms with no router: rbench agree has no row for them.
NULL_ARMS="null null-no405 capi-null rust-null"
# Every test the build must run and pass: cmake/tests-review.cmake (ablation_objdump_<v> for each variant v)
# and cmake/tool-adversarial.cmake.
REVIEW_TESTS="ablation_copies ablation_answers ablation_objdump_copy ablation_objdump_ab_linear \
ablation_objdump_ab_hashed ablation_objdump_ab_noexact ablation_objdump_ab_bytes boundary_call \
adversarial_unit adversarial_self_test adversarial_copy"
# The environment knobs of run_grid.sh (and of the Go runtime) that change what a process runs, unset for its
# calls: the job sets the others itself (ARMS, SCOPE, REPS, SEED, CPU, CELL_TIMEOUT, PIN).
GRID_ENV_UNSET="MISS RING ZIPF VOCAB NO_DECOY RING_LAYOUT QUICK VERIFY PAIRS SHAPES SIZES GOGC"

# stop CODE REASON...: end the job with this status line (the EXIT trap writes it to OUT_DIR.done).
stop() {
    local code=$1
    shift
    status="STOPPED: $*"
    echo "$status"
    exit "$code"
}

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
    papers=${PAPERS:-$(cd "$paper/../.." && pwd)}
    papers=$(cd "$papers" 2>/dev/null && pwd) ||
        stop 2 "PAPERS is not a directory (the Papers clone with lab/bin and lab/sanitizer-records)"
    bench=$paper/bench
    local rm_commit=${RM_COMMIT:-} rm_dir=${REGEXMATCHER_DIR:-} go=${GO:-}
    [ -n "$rm_commit" ] && [ -d "$rm_dir" ] || {
        status="STOPPED: set RM_COMMIT (the full RegexMatcher commit) and REGEXMATCHER_DIR (a git archive of it)"
        echo "$status"; exit 2; }
    [ "$rm_commit" = "$RM_PINNED" ] ||
        stop 2 "RM_COMMIT is '$rm_commit', not $RM_PINNED, the commit both plans pin"
    [ -n "$go" ] && [ -x "$go" ] || {
        status="STOPPED: set GO to the pinned go binary (bench/jobs/install-go.sh)"; echo "$status"; exit 2; }
    rm_dir=$(cd "$rm_dir" && pwd)
    export PATH="$(dirname "$go"):$PATH" GOTOOLCHAIN=local
    local records=${RECORDS:-$papers/lab/sanitizer-records}
    local inputs_py=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
    local seed=${SEED:-20261104} cpu=${CPU:-2} timeout_s=${CELL_TIMEOUT:-1800}
    local pin=${PIN:-$papers/lab/bin/pin.sh}
    local dirty paper_head papers_head
    dirty=$(git -C "$paper" status --porcelain -- bench analysis) || stop 2 "git status failed in the paper clone $paper"
    [ -z "$dirty" ] || stop 2 "the paper clone has local changes under bench/ or analysis/"
    paper_head=$(git -C "$paper" rev-parse HEAD) || stop 2 "git rev-parse failed in the paper clone $paper"
    papers_head=$(git -C "$papers" rev-parse HEAD) || stop 2 "git rev-parse failed in the Papers clone $papers"
    echo "review-grid start $(date -Is), Papers $papers_head, paper $paper_head,"
    echo "  RegexMatcher $rm_commit from $rm_dir, $("$go" version), host $(uname -n) $(uname -r), $(clang++ --version | head -1)"

    # ------------------------------------------------------------ 1. build and gate
    local build=$out/build compiler arms
    arms=$(python3 "$bench/arms_for.py" none --review)
    REGEXMATCHER_DIR="$rm_dir" INPUTS_HASH_PY="$inputs_py" bash "$bench/build.sh" "$build" \
        "-DRB_ARMS=$arms" "-DREGEXMATCHER_COMMIT=$rm_commit" "-DRB_GO=$go" || {
        status="STOPPED: the build failed ($build.log)"; echo "$status"; tail -40 "$build.log"; exit 1; }
    local a missing="" listed
    listed=$("$build/rbench" list | cut -f1)
    for a in $ABLATION_ARMS $BOUNDARY_ARMS; do
        grep -qx -- "$a" <<<"$listed" || missing="$missing $a"
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
        echo "repo_head: $paper_head"
        echo "papers_head: $papers_head"
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
    (cd "$build" && ctest --output-on-failure --no-tests=error) >"$out/ctest.txt" 2>&1 || {
        status="STOPPED: the build's tests failed ($out/ctest.txt); nothing timed"; echo "$status"; tail -30 "$out/ctest.txt"; exit 1; }
    tail -3 "$out/ctest.txt"
    local t unpassed=""
    for t in $REVIEW_TESTS; do
        grep -Eq "Test +#[0-9]+: $t +\.+ +Passed" "$out/ctest.txt" || unpassed="$unpassed $t"
    done
    [ -z "$unpassed" ] || {
        status="STOPPED: ctest did not report these tests as passed:$unpassed ($out/ctest.txt); nothing timed"
        echo "$status"; exit 1; }
    local march
    march=$(sed -n 's/^RB_MARCH:STRING=//p' "$build/CMakeCache.txt")
    python3 "$bench/tools/code_size.py" --cxx "$(sed -n 's/^CMAKE_CXX_COMPILER:[A-Z]*=//p' "$build/CMakeCache.txt")" \
        --regexmatcher "$rm_dir" --out "$out/code-size.tsv" --label "review-grid-$(basename "$out")" \
        ${march:+-- "-march=$march"} >/dev/null || {
        status="STOPPED: the code size of the ablation arms could not be read, or the copy is not the pinned code"
        echo "$status"; exit 1; }
    local scope="" n_plan v rc
    local -a clean=(env)
    for v in $GRID_ENV_UNSET; do clean+=(-u "$v"); done
    for a in $BOUNDARY_ARMS; do scope="$scope $a:100:16"; done
    "${clean[@]}" ARMS="$ABLATION_ARMS $BOUNDARY_ARMS" SCOPE="$scope" REPS=16 SEED="$seed" CPU="$cpu" PIN=none \
        ALLOW_UNPINNED=1 PLAN_ONLY=1 bash "$bench/run_grid.sh" "$build/rbench" "$out/plan-check" >/dev/null || {
        status="STOPPED: the plan could not be written"; echo "$status"; exit 1; }
    n_plan=$(wc -l <"$out/plan-check/plan.txt")
    [ "$n_plan" -eq "$PLANNED" ] || {
        status="STOPPED: the plan has $n_plan processes, not $PLANNED"; echo "$status"; exit 1; }
    echo "plan: $n_plan processes, seed $seed, CPU $cpu"
    # The agreement test and the probes of every arm of the grid, as run_grid.sh runs them: its arms and its
    # shapes (read from the plan's env.txt), the sizes 10, 100 and 1000, nothing timed. A disagreement or a
    # failing probe stops the job here, not after the grid.
    local g_arms g_shapes po
    g_arms=$(sed -n 's/^arms: //p' "$out/plan-check/env.txt")
    g_shapes=$(sed -n 's/^shapes: //p' "$out/plan-check/env.txt")
    [ -n "$g_arms" ] && [ -n "$g_shapes" ] || stop 1 "the plan's env.txt names no arms or no shapes"
    "$build/rbench" agree --arms "$(echo $g_arms | tr ' ' '\n' | tr '\n' ',' | sed 's/,$//')" \
        --shapes "$(echo $g_shapes | tr ' ' ',')" --sizes 10,100,1000 >"$out/pre-agree.jsonl" 2>"$out/pre-stderr.log"
    rc=$?
    [ "$rc" -le 1 ] || stop 1 "rbench agree failed (exit $rc, $out/pre-stderr.log); nothing timed"
    # rbench reports an exception (a table or a ring that could not be made) as "rbench: ..." and exit 1, as it
    # does a declared disagreement, with the rows so far: nothing else of agree writes to standard error.
    ! grep -q '^rbench: ' "$out/pre-stderr.log" ||
        stop 1 "rbench agree stopped on an error ($(grep -m1 '^rbench: ' "$out/pre-stderr.log")); nothing timed"
    python3 "$bench/check_agree.py" "$out/pre-agree.jsonl" 2>>"$out/pre-stderr.log" ||
        stop 1 "the agreement test failed (check_agree.py, $out/pre-stderr.log); nothing timed"
    python3 - "$out/pre-agree.jsonl" "$NULL_ARMS" $g_arms <<'EOF' ||
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.startswith("{")]
have = {r.get("arm") for r in rows}
missing = [a for a in sys.argv[3:] if a not in sys.argv[2].split() and a not in have]
if missing:
    sys.exit("no agreement row for: " + " ".join(missing))
EOF
        stop 1 "the agreement test has no rows for an arm ($out/pre-agree.jsonl); nothing timed"
    : >"$out/pre-probes.jsonl"
    for a in $g_arms; do
        po=$("$build/rbench" probe --arm "$a" 2>>"$out/pre-stderr.log") ||
            stop 1 "the probe of $a failed (exit $?, $out/pre-stderr.log); nothing timed"
        [ -n "$po" ] || stop 1 "the probe of $a printed nothing; nothing timed"
        printf '%s\n' "$po" >>"$out/pre-probes.jsonl"
    done
    echo "agreement test and probes passed: $(wc -l <"$out/pre-agree.jsonl") rows, $(wc -l <"$out/pre-probes.jsonl") probe lines"
    if [ "${CHECK_ONLY:-0}" = 1 ]; then
        status="done: CHECK_ONLY, built, gated and tested, plan of $n_plan processes written, nothing timed"
        echo "$status"
        exit 0
    fi

    # ------------------------------------------------------------ 3. the grid
    local problems="" n_cells
    "${clean[@]}" -u PLAN_ONLY ARMS="$ABLATION_ARMS $BOUNDARY_ARMS" SCOPE="$scope" REPS=16 SEED="$seed" CPU="$cpu" \
        CELL_TIMEOUT="$timeout_s" PIN="$pin" ALLOW_UNPINNED="${ALLOW_UNPINNED:-0}" \
        bash "$bench/run_grid.sh" "$build/rbench" "$out/grid"
    rc=$?
    n_cells=$(wc -l <"$out/grid/cells.jsonl" 2>/dev/null) || n_cells=0
    cmp -s "$out/plan-check/plan.txt" "$out/grid/plan.txt" && [ "$n_cells" -eq "$n_plan" ] ||
        problems="the grid's plan differs from the plan checked, or its cells.jsonl has $n_cells lines, not $n_plan"
    echo "grid end $(date -Is): run_grid.sh exit $rc, $n_cells lines of $n_plan planned"

    # ------------------------------------------------------------ 4. the analysis
    local arc brc
    python3 "$paper/analysis/ablations.py" "$out/grid" --code-size "$out/code-size.tsv" --out "$out/ablations.json" \
        --macros "$out/ablations.tex" --csv "$out/ablations.csv" >"$out/ablations.txt" 2>&1
    arc=$?
    python3 "$paper/analysis/boundary.py" "$out/grid" --out "$out/boundary.json" --macros "$out/boundary.tex" \
        --csv "$out/boundary.csv" >"$out/boundary.txt" 2>&1
    brc=$?
    echo "grid_exit=$rc ablations_exit=$arc boundary_exit=$brc $(cat "$out/grid/exit.txt" 2>/dev/null)" >"$out/exit.txt"
    [ -s "$out/ablations.json" ] && [ -s "$out/boundary.json" ] || problems="${problems:+$problems; }an analysis wrote no summary"
    if [ "$rc" -ne 0 ] || [ "$arc" -ne 0 ] || [ "$brc" -ne 0 ] || [ -n "$problems" ]; then
        status="FAILED: $(cat "$out/exit.txt")${problems:+ ($problems)}"
        echo "review-grid $status $(date -Is)"
        exit 1
    fi
    status="done: $(cat "$out/exit.txt")"
    echo "review-grid $status $(date -Is)"
}

main "$@"
exit
