#!/usr/bin/env bash
# gaps.sh OUT_DIR: two checks on L before the freeze (coordinator, 2026-09-30), development
# evidence only, engineering seeds only. Run from a Papers clone holding the committed records,
# with this repository as its submodule, under the lab's lablock, with a pid file and a done file:
#     RM_COMMIT=<full sha> REGEXMATCHER_DIR=<git archive of it> \
#     nohup ~/lab/Papers/lab/bin/lablock bash <clone>/papers/typed-routing/bench/jobs/gaps.sh <OUT_DIR> \
#         > <OUT_DIR>.log 2>&1 &
#     echo $! > <OUT_DIR>.pid
# 1. H7's cost build is gated: CHECK_ONLY=1 bench/ct_cost_run.sh (the compile-time arm built alone,
#    hashed, and checked against the committed records and pins; no cost read).
# 2. The check on every query covers every arm: tools/verify_answers linked from a plain build of
#    rbench (bench/build.sh, every arm; tools/build_verify.py), then tools/verify_cover.py: every
#    arm on every cell of its scope at the engineering pair (1, 2), each check's wall time, four at
#    once (nothing else runs; the times are for the estimate of the grid's re-check).
# 3. The re-check inside the grid: bench/run_grid.sh on one cell whose agreement pass is expected to
#    stop at its 120 s budget (regexmatcher-v1, param-first, m = 10,000, pair (1, 2), one process),
#    so that the grid's own re-check runs; unpinned, its times are not used.
# OUT_DIR.done: the time and "done" with each step's exit code, or "STOPPED:", or "incomplete".
#
# Downloads: rbench's FetchContent archives by sha256 (bench/cmake/pins.cmake), crates by
# Cargo.lock, Go modules from their repositories (GOPROXY=direct), as in bench/jobs/records.sh.
#
# The whole job is one function, read completely before it runs.
set -uo pipefail
export GOPROXY=direct GOTOOLCHAIN=local

main() {
    local out=${1:?usage: gaps.sh OUT_DIR}
    mkdir -p "$out"
    out=$(cd "$out" && pwd)
    status=incomplete
    trap 'echo "$(date -Is) $status" > "'"$out"'.done"' EXIT
    exec > >(tee -a "$out/gaps.log") 2>&1
    local here paper papers bench
    here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    paper=$(cd "$here/../.." && pwd)
    papers=$(cd "$paper/../.." && pwd)
    bench=$paper/bench
    local rm_commit=${RM_COMMIT:?RM_COMMIT is required} rm_dir=${REGEXMATCHER_DIR:?REGEXMATCHER_DIR is required}
    echo "gaps start $(date -Is), Papers $(git -C "$papers" rev-parse HEAD), paper $(git -C "$paper" rev-parse HEAD), $(clang++ --version | head -1)"

    local rc1 rc2 rc3
    echo "== 1. CHECK_ONLY ct_cost_run.sh $(date -Is)"
    CHECK_ONLY=1 REGEXMATCHER_DIR="$rm_dir" REGEXMATCHER_COMMIT="$rm_commit" \
        bash "$bench/ct_cost_run.sh" "$out/ct-check" > "$out/ct-check.txt" 2>&1
    rc1=$?
    cat "$out/ct-check.txt"; tail -8 "$out/ct-check/gate.txt" 2>/dev/null
    echo "== 1. exit $rc1 $(date -Is)"

    echo "== 2. verify_answers on every arm and cell $(date -Is)"
    REGEXMATCHER_DIR="$rm_dir" INPUTS_HASH_PY="$papers/lab/bin/inputs_hash.py" \
        bash "$bench/build.sh" "$out/build" "-DREGEXMATCHER_COMMIT=$rm_commit" > "$out/build.txt" 2>&1 &&
        python3 "$paper/tools/build_verify.py" "$out/build" "$out/verify" > "$out/verify-build.txt" 2>&1 &&
        python3 "$paper/tools/verify_cover.py" "$out/verify/verify_answers" "$out/build/rbench" \
            --out "$out/cover.jsonl" --jobs 4 --pair 1:2 > "$out/cover.txt" 2>&1
    rc2=$?
    cat "$out/build.txt" "$out/verify-build.txt" "$out/cover.txt" 2>/dev/null | tail -60
    echo "== 2. exit $rc2 $(date -Is)"

    echo "== 3. the grid's own re-check on a cut cell $(date -Is)"
    ARMS=regexmatcher-v1 SHAPES=param-first SIZES=10000 REPS=1 PAIRS=1:2 SEED=none SCOPE=regexmatcher-v1:10000:1 \
        PIN=/nonexistent ALLOW_UNPINNED=1 bash "$bench/run_grid.sh" "$out/build/rbench" "$out/grid" > "$out/grid.txt" 2>&1
    rc3=$?
    cat "$out/grid.txt"; cat "$out/grid/verify.txt" 2>/dev/null; cat "$out/grid/verified.jsonl" 2>/dev/null
    echo "== 3. exit $rc3 $(date -Is)"

    status="done: ct gate $rc1, cover $rc2, grid re-check $rc3"
    echo "gaps $status $(date -Is)"
}

main "$@"
exit
