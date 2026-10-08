#!/usr/bin/env bash
# gates.sh OUT_DIR: round 2's gates and the objdump check on L (design/round2/status.md, section 5,
# steps 6 and 7), after the sanitizer records are committed. Run from a fresh Papers clone at the
# commit that holds the records, with this repository as its submodule, under the lab's lablock,
# with a pid file and a done file:
#     RM_COMMIT=<full sha> REGEXMATCHER_DIR=<git archive of it> ROUND1_HEADER=<file> ROUND1_NS=<namespace> \
#     nohup ~/lab/Papers/lab/bin/lablock bash <clone>/papers/typed-routing/bench/jobs/gates.sh <OUT_DIR> \
#         > <OUT_DIR>.log 2>&1 &
#     echo $! > <OUT_DIR>.pid
# 1. rbench: CHECK_ONLY=1 bench/run_baseline.sh, the build and gate the main grid will run (every
#    arm, clang, Release; check_records.py against the committed records and pins).
# 2. the server: CHECK_ONLY=1 t1/run_h6.sh, the build and gate the H6 run will use
#    (check_h6_records.py, pins included), and t1gen's own record.
# 3. the objdump check at C2 with L's clang: find_v2 compiled against the round-1 header (given as
#    ROUND1_HEADER and ROUND1_NS, not named here) and against RegexMatcher at RM_COMMIT, both at
#    -march=native, the harness's flags (bench/objdump_check.sh, label l-clang22-c2-native). The
#    development baseline at the earlier flags is lab/evidence/2026-09-30-W-regexmatcher-v2-objdump.
# 4. H7's costs: CHECK_ONLY=1 bench/ct_cost_run.sh, the compile-time arm's build and gate.
# Each step runs whatever the others give; OUT_DIR.done says "done" with each exit code, or
# "STOPPED:" if a precondition is missing, or "incomplete".
#
# Downloads: as bench/jobs/records.sh (rbench's FetchContent archives by sha256, crates by
# Cargo.lock, Go modules from their repositories, RegexMatcher v1 by sha256).
#
# The whole job is one function, read completely before it runs.
set -uo pipefail
export GOPROXY=direct GOTOOLCHAIN=local

main() {
    local out=${1:?usage: gates.sh OUT_DIR}
    mkdir -p "$out"
    out=$(cd "$out" && pwd)
    status=incomplete
    trap 'echo "$(date -Is) $status" > "'"$out"'.done"' EXIT
    exec > >(tee -a "$out/gates.log") 2>&1
    local here paper papers
    here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    paper=$(cd "$here/../.." && pwd)
    papers=$(cd "$paper/../.." && pwd)
    local rm_commit=${RM_COMMIT:?RM_COMMIT is required} rm_dir=${REGEXMATCHER_DIR:?REGEXMATCHER_DIR is required}
    local old=${ROUND1_HEADER:-} oldns=${ROUND1_NS:-}
    [ -f "$old" ] && [ -n "$oldns" ] || {
        status="STOPPED: set ROUND1_HEADER to the round-1 header (a file) and ROUND1_NS to its namespace"
        echo "$status"; exit 2; }
    echo "gates start $(date -Is), Papers $(git -C "$papers" rev-parse HEAD), paper $(git -C "$paper" rev-parse HEAD),"
    echo "  RegexMatcher $rm_commit, host $(uname -n) $(uname -r), $(clang++ --version | head -1)"
    ls "$papers/lab/sanitizer-records" | grep -E '^(regexmatcher|rbench|mserver)-.*-L-' | tail -30 || true

    local rc1 rc2 rc3
    echo "== 1. rbench: CHECK_ONLY run_baseline.sh $(date -Is)"
    CHECK_ONLY=1 REGEXMATCHER_DIR="$rm_dir" REGEXMATCHER_COMMIT="$rm_commit" \
        bash "$paper/bench/run_baseline.sh" > "$out/rbench-gate.log" 2>&1
    rc1=$?
    tail -5 "$out/rbench-gate.log"
    cp "$paper/bench/build-publication.inputs.json" "$paper/bench/build-publication.v2-include.json" "$out/" 2>/dev/null
    echo "== 1. exit $rc1 $(date -Is)"

    echo "== 2. the server: CHECK_ONLY run_h6.sh $(date -Is)"
    CHECK_ONLY=1 REGEXMATCHER_DIR="$rm_dir" REGEXMATCHER_COMMIT="$rm_commit" \
        bash "$paper/t1/run_h6.sh" "$out/h6-check" > "$out/server-gate.log" 2>&1
    rc2=$?
    tail -5 "$out/server-gate.log"
    echo "== 2. exit $rc2 $(date -Is)"

    echo "== 3. objdump check at C2 $(date -Is)"
    [ "$(git -C "$(dirname "$old")" rev-parse HEAD)" = 6d28e36109085af006281abd979e311bd7b03068 ] ||
        echo "WARNING: the round-1 header's checkout is not at 6d28e3610"
    bash "$paper/bench/objdump_check.sh" clang++ l-clang22-c2-native \
        "$old" "$oldns" "$rm_dir/include" matcher/route.hpp matcher::route -march=native > "$out/objdump.txt" 2>&1
    rc3=$?
    if ! grep -q '^IDENTICAL$' "$out/objdump.txt" && [ "$rc3" -eq 0 ]; then rc3=1; fi
    cat "$out/objdump.txt"
    echo "== 3. exit $rc3 $(date -Is)"

    local rc4
    echo "== 4. H7's costs: CHECK_ONLY ct_cost_run.sh $(date -Is)"
    CHECK_ONLY=1 REGEXMATCHER_DIR="$rm_dir" REGEXMATCHER_COMMIT="$rm_commit" \
        bash "$paper/bench/ct_cost_run.sh" "$out/ct-check" > "$out/ct-gate.log" 2>&1
    rc4=$?
    tail -5 "$out/ct-gate.log"
    echo "== 4. exit $rc4 $(date -Is)"

    status="done: rbench gate $rc1, server gate $rc2, objdump $rc3, ct gate $rc4"
    echo "gates $status $(date -Is)"
}

main "$@"
exit
