#!/usr/bin/env bash
# slot1.sh OUT_DIR: round 2's first L slot (design/round2/schedule.md), four development jobs,
# nothing citable. Run from a clone of this repository at $R2/typed-routing, under the lab's
# lablock, with a pid file and a done file:
#     git clone -q git@github.com:Alex-Tsvetanov/paper-typed-routing.git ~/lab/p2/r2/typed-routing
#     ROUND1_HEADER=... ROUND1_NS=... nohup ~/lab/Papers/lab/bin/lablock \
#         bash ~/lab/p2/r2/typed-routing/bench/jobs/slot1.sh ~/lab/p2/r2/slot1 > ~/lab/p2/r2/slot1.log 2>&1 &
#     echo $! > ~/lab/p2/r2/slot1.pid
# When it ends, the job writes OUT_DIR.done: the time and how it ended ("done", or "STOPPED:" and
# the reason, or "incomplete" if it was killed or failed elsewhere).
#
# The jobs, in the order they run:
# 2. inputs, first, because it is the hard condition before any round-2 record: every stored
#    inputs.json of P2 (required) and P1 (if still present) on L recomputed by the new
#    lab/bin/inputs_hash.py (--stored), and the default mode against the script before
#    --dep-root (--old 2435e56~1) on P2's round-1 build directories. If any check fails, or a
#    P2 file or build directory is missing, the job stops here and nothing else runs.
# 1. objdump: RegexMatcher v2's lookup against the round-1 header with clang 22.1.8, at each
#    step (E1, E2, the checked front end, the branch head): lab/evidence/
#    2026-09-30-W-regexmatcher-v2-objdump/objdump_check.sh, as run on W with clang 18 and gcc 14.
# 3. baseline: rbench of this commit with the arms null, regexmatcher-v2 (at RM_COMMIT),
#    regexmatcher-v2-r1 and gin, every H1 shape at m = 10 to 100,000, the engineering pairs 1:2
#    and 1:3, pinned as run_grid.sh pins: the instruction baseline for adoption rules (a) and (b)
#    of design/round2/engineering.md.
# 4. every arm built and checked by agreement (below).
#
# Environment: ROUND1_HEADER and ROUND1_NS (job 1; required, checked before anything runs),
# RM_COMMIT (the RegexMatcher commit of jobs 3 and 4, default the branch head), R2 (default
# ~/lab/p2/r2), PAPERS (a Papers clone, default $R2/Papers, cloned if missing: its lab/ scripts),
# PAPER (a paper-typed-routing clone, default $R2/typed-routing, cloned if missing) and
# PAPER_COMMIT (the harness commit to run, default the paper's main).
#
# Downloads (jobs 3 and 4): FetchContent archives from GitHub (codeload.github.com, and one
# release archive), each checked against its sha256 in cmake/pins.cmake; path-tree and smallvec
# from crates.io, checked against Cargo.lock (cargo --locked). A Go module missing from L's cache
# comes from its repository, not a proxy, and Go never fetches a toolchain.
#
# The whole job is one function, read completely before it runs: the checkout below may change
# this file while it runs.
set -uo pipefail
export GOPROXY=direct GOTOOLCHAIN=local

main() {
    local out=${1:?usage: slot1.sh OUT_DIR}
    mkdir -p "$out"
    out=$(cd "$out" && pwd)
    status=incomplete
    trap 'echo "$(date -Is) $status" > "'"$out"'.done"' EXIT
    exec > >(tee -a "$out/slot1.log") 2>&1
    local old=${ROUND1_HEADER:-} oldns=${ROUND1_NS:-}
    [ -f "$old" ] && [ -n "$oldns" ] || {
        status="STOPPED: set ROUND1_HEADER to the round-1 header (a file) and ROUND1_NS to its namespace"
        echo "$status"; exit 2; }
    local R2=${R2:-$HOME/lab/p2/r2}
    local PAPERS=${PAPERS:-$R2/Papers}
    local PAPER=${PAPER:-$R2/typed-routing}
    local RM=$R2/RegexMatcher
    [ -d "$PAPERS/.git" ] || git clone -q git@github.com:Alex-Tsvetanov/Papers.git "$PAPERS"
    [ -d "$PAPER/.git" ] || git clone -q git@github.com:Alex-Tsvetanov/paper-typed-routing.git "$PAPER"
    git -C "$PAPERS" pull -q --ff-only
    git -C "$PAPER" fetch -q origin
    git -C "$PAPER" checkout -q "${PAPER_COMMIT:-origin/main}"
    echo "slot1 start $(date -Is), Papers $(git -C "$PAPERS" rev-parse HEAD), paper $(git -C "$PAPER" rev-parse HEAD), host $(uname -n) $(uname -r)"

    # ------------------------------------------------------------ 2. stored inputs (the gate)
    echo "== 2. stored inputs.json recomputed by the new inputs_hash.py (the hard condition)"
    local p2=$HOME/lab/p2/pub/Papers/papers/typed-routing/bench
    local p1=$HOME/lab/p1/Papers/papers/wake-defect/results/raw
    local stored=() f rc
    usable() {
        [ -f "$1" ] && python3 -c "import json,os,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if all(os.path.isdir(b['build_dir']) for b in d['builds'].values()) else 1)" "$1"
    }
    for f in "$p2/build-baseline.inputs.json" "$p2/build-baseline-v1.inputs.json"; do
        usable "$f" || { status="STOPPED: P2 stored inputs missing, or a build directory is gone: $f"; echo "$status"; exit 3; }
        stored+=(--stored "$f")
        echo "stored (P2): $f"
    done
    for f in "$p1/2026-09-29-L-publication-0af1ac4/inputs.json" "$p1/2026-09-29-L-random-gap-0af1ac4/inputs.json"; do
        if usable "$f"; then
            stored+=(--stored "$f")
            echo "stored (P1): $f"
        else
            echo "not checked (P1 file missing, or a build directory is gone): $f"
        fi
    done
    (cd "$PAPERS/lab/bin" && python3 test_inputs_hash.py --old 2435e56~1 "${stored[@]}") | tee "$out/inputs.txt"
    rc=${PIPESTATUS[0]}
    [ "$rc" -eq 0 ] || { status="STOPPED: stored inputs check failed (test_inputs_hash.py exit $rc, $out/inputs.txt)"; echo "$status"; exit 3; }
    # The default mode against the script before the change, on P2's round-1 build directories,
    # with every target each build hashed.
    local pair d targs
    for pair in "build-baseline:rbench" "build-baseline-v1:rbench-v1"; do
        d=$p2/${pair%%:*}
        mapfile -t targs < <(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); [print(a) for t in next(iter(d['builds'].values()))['targets'] for a in ('--target', t)]" "$d.inputs.json")
        (cd "$PAPERS/lab/bin" && python3 test_inputs_hash.py --old 2435e56~1 --build "${pair##*:}=$d" "${targs[@]}") | tee -a "$out/inputs.txt"
        rc=${PIPESTATUS[0]}
        [ "$rc" -eq 0 ] || { status="STOPPED: default-mode check failed on $d (test_inputs_hash.py exit $rc, $out/inputs.txt)"; echo "$status"; exit 3; }
    done
    echo "== 2 passed: every stored hash recomputed identically, default mode identical"

    # RegexMatcher v2 from the bare repository on L (the remote named lab on W; never GitHub).
    local head rm_commit
    { [ -d "$RM/.git" ] || git clone -q "$HOME/lab/git/RegexMatcher.git" "$RM"; } &&
        git -C "$RM" fetch -q origin &&
        head=$(git -C "$RM" rev-parse --verify origin/v2/route-matcher) &&
        rm_commit=$(git -C "$RM" rev-parse --verify "${RM_COMMIT:-$head}^{commit}") || {
        status="STOPPED: RegexMatcher v2 not found in $HOME/lab/git/RegexMatcher.git (branch v2/route-matcher, RM_COMMIT ${RM_COMMIT:-unset})"
        echo "$status"; exit 4; }
    echo "RegexMatcher branch head $head, jobs 3 and 4 at $rm_commit"

    # ------------------------------------------------------------ 1. objdump, clang 22
    echo "== 1. objdump check, $(clang++ --version | head -1)"
    # The round-1 header and its namespace are given, not named here; its checkout must be at
    # the measured commit, 6d28e3610.
    [ "$(git -C "$(dirname "$old")" rev-parse HEAD)" = 6d28e36109085af006281abd979e311bd7b03068 ] ||
        echo "WARNING: the round-1 header's checkout is not at 6d28e3610"
    local check=$PAPERS/lab/evidence/2026-09-30-W-regexmatcher-v2-objdump/objdump_check.sh
    local step c name src
    for step in 00a2053:E1 e20f185:E2 661b569:F1 "$head:head"; do
        c=${step%%:*}; name=${step##*:}
        src=$R2/rm-src-$c
        [ -d "$src" ] || { mkdir -p "$src"; git -C "$RM" archive "$c" include | tar -x -C "$src"; }
        bash "$check" clang++ "l-clang22-$name" "$old" "$oldns" "$src/include" \
            matcher/route.hpp matcher::route | tee -a "$out/objdump.txt"
    done
    cp -r "$HOME/od" "$out/objdump-files" 2>/dev/null || true

    # ------------------------------------------------------------ 3. instruction baseline
    echo "== 3. instruction baseline (rbench, null, regexmatcher-v2 at $rm_commit, regexmatcher-v2-r1, gin)"
    local src3=$R2/rm-src-$rm_commit-full
    [ -d "$src3" ] || { mkdir -p "$src3"; git -C "$RM" archive "$rm_commit" | tar -x -C "$src3"; }
    local bench=$PAPER/bench
    REGEXMATCHER_DIR=$src3 INPUTS_HASH_PY=$PAPERS/lab/bin/inputs_hash.py \
        bash "$bench/build.sh" "$out/build" "-DRB_ARMS=null;regexmatcher-v2;regexmatcher-v2-r1;gin" "-DREGEXMATCHER_COMMIT=$rm_commit" || {
        status="STOPPED: the build of job 3 failed"; echo "$status"; tail -40 "$out/build.log"; exit 1; }
    ARMS="null regexmatcher-v2 regexmatcher-v2-r1 gin" REPS=2 PAIRS="1:2 1:3" SEED=none \
        PIN=$PAPERS/lab/bin/pin.sh bash "$bench/run_grid.sh" "$out/build/rbench" "$out/grid"
    cat "$out/grid/exit.txt"
    echo "== 3 ended $(date -Is)"

    # ------------------------------------------------------------ 4. every arm, agreement only
    # The full arm set of round 2 (the five new competitors among them: chi and path-tree need L's
    # Go and Rust toolchains), built with clang 22.1.8 and checked by rbench agree on the
    # engineering table seed and two held-out ones, sizes 10 to 1,000. Nothing is timed. A failure
    # here is reported and does not undo jobs 1 to 3.
    echo "== 4. every arm: build and agreement"
    REGEXMATCHER_DIR=$src3 INPUTS_HASH_PY=$PAPERS/lab/bin/inputs_hash.py \
        bash "$bench/build.sh" "$out/build-all" "-DREGEXMATCHER_COMMIT=$rm_commit" && {
        "$out/build-all/rbench" list > "$out/arms-all.txt"
        "$out/build-all/rbench" agree --seeds 1,111,112 --sizes 10,100,1000 > "$out/agree-all.jsonl" 2> "$out/agree-all.err"
        python3 "$bench/check_agree.py" "$out/agree-all.jsonl"; echo "check_agree exit $?"
    } || { echo "build of every arm failed"; tail -40 "$out/build-all.log"; }
    status=done
    echo "slot1 jobs done $(date -Is)"
}

main "$@"
exit
