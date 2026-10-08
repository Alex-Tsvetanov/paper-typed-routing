#!/usr/bin/env bash
# slot2.sh OUT_DIR: round 2's second L slot (design/round2/schedule.md), two development jobs,
# nothing citable. Run from a clone of this repository at $R2/typed-routing, under the lab's
# lablock, with a pid file and a done file:
#     PAPER_COMMIT=... nohup ~/lab/Papers/lab/bin/lablock \
#         bash ~/lab/p2/r2/typed-routing/bench/jobs/slot2.sh ~/lab/p2/r2/slot2 > ~/lab/p2/r2/slot2.log 2>&1 &
#     echo $! > ~/lab/p2/r2/slot2.pid
# When it ends, the job writes OUT_DIR.done: the time and how it ended ("done", or "STOPPED:" and
# the reason, or "incomplete" if it was killed or failed elsewhere).
#
# The ten engineering pairs of both jobs: table seeds 1 to 5, ring seeds 2 and 3.
#
# (a) Target (a), adoption rule 2 (design/round2/engineering.md, 1.5): the build time of
#     RegexMatcher v2 before the build rework (A: 53e8dda) and after it (B: f48fa83). Two rbench
#     binaries with every arm, from the harness of paper commit 4bedc11 (the last one both build
#     with; a worktree of the clone), so that they differ only in RegexMatcher's code. Only the
#     regexmatcher-v2 arm runs from each: every shape at m = 1,000, 10,000 and 100,000 (21 cells),
#     one process per binary and pair (10 per binary and cell), the pairs of a cell in the order
#     A B, B A, A B, ... (A B B A), pinned by lab/bin/pin.sh, on CPU 2. Adopted if, in every cell,
#     the median over processes of build_s_median is lower in B (a-summary.txt).
# (c) C2's H7 iteration check (engineering.md, 3.5): rbench with every arm, from the harness of
#     PAPER_COMMIT (a worktree, where gen-ct --seeds 2,3,4,5 adds the compile-time tables of the
#     engineering seeds; nothing is committed) and RegexMatcher RM_C2 (default 45ab696).
#     run_grid.sh with the arms regexmatcher-v2 and regexmatcher-v2-ct, every shape at m = 10,
#     100 and 1,000 (21 cells), the ten pairs, the order shuffled as the main grid's. Passes if
#     no cell's median over pairs of the ratio compile-time / run-time (ns_median) exceeds 1.02
#     (c-summary.txt).
#
# Environment: PAPER_COMMIT (the harness of job (c), default the paper's main), RM_C2, R2
# (default ~/lab/p2/r2), PAPERS (a Papers clone, default $R2/Papers: lab/bin), PAPER (a
# paper-typed-routing clone, default $R2/typed-routing). RegexMatcher comes from the bare
# repository on L (the remote named lab on W; never GitHub). For a reduced test run only
# (WSL): BUILD_ARMS (RB_ARMS of every build; default every arm), A_SHAPES, A_SIZES, C_SHAPES,
# C_SIZES, PIN (default lab/bin/pin.sh), ALLOW_UNPINNED=1, EXTRA_CMAKE (more CMake arguments of
# every build). A run that sets any of them is not the job described above.
#
# Downloads: FetchContent archives from GitHub, each checked against its sha256 in
# cmake/pins.cmake; path-tree and smallvec from crates.io, checked against Cargo.lock; a Go
# module missing from L's cache from its repository, not a proxy; Go never fetches a toolchain.
#
# The whole job is one function, read completely before it runs: the checkout below may change
# this file while it runs.
set -uo pipefail
export GOPROXY=direct GOTOOLCHAIN=local

main() {
    local out=${1:?usage: slot2.sh OUT_DIR}
    mkdir -p "$out"
    out=$(cd "$out" && pwd)
    status=incomplete
    trap 'echo "$(date -Is) $status" > "'"$out"'.done"' EXIT
    exec > >(tee -a "$out/slot2.log") 2>&1
    local R2=${R2:-$HOME/lab/p2/r2}
    local PAPERS=${PAPERS:-$R2/Papers}
    local PAPER=${PAPER:-$R2/typed-routing}
    local RM=$R2/RegexMatcher
    local pin=${PIN:-$PAPERS/lab/bin/pin.sh}
    local ih=$PAPERS/lab/bin/inputs_hash.py
    local pairs="1:2 1:3 2:2 2:3 3:2 3:3 4:2 4:3 5:2 5:3"
    local arms_arg=() extra=()
    [ -n "${BUILD_ARMS:-}" ] && arms_arg=("-DRB_ARMS=$BUILD_ARMS")
    [ -n "${EXTRA_CMAKE:-}" ] && read -r -a extra <<< "$EXTRA_CMAKE"
    stop() { status="STOPPED: $*"; echo "$status"; exit 1; }

    git -C "$PAPERS" pull -q --ff-only || stop "cannot update $PAPERS"
    git -C "$PAPER" fetch -q origin || stop "cannot fetch $PAPER"
    local pc
    pc=$(git -C "$PAPER" rev-parse --verify "${PAPER_COMMIT:-origin/main}^{commit}") || stop "no commit ${PAPER_COMMIT:-origin/main}"
    git -C "$RM" fetch -q origin || stop "cannot fetch RegexMatcher from the bare repository"
    local ca cb cc
    ca=$(git -C "$RM" rev-parse --verify 53e8dda^{commit}) &&
        cb=$(git -C "$RM" rev-parse --verify f48fa83^{commit}) &&
        cc=$(git -C "$RM" rev-parse --verify "${RM_C2:-45ab696}^{commit}") || stop "a RegexMatcher commit is missing"
    echo "slot2 start $(date -Is), Papers $(git -C "$PAPERS" rev-parse HEAD), paper $pc, RegexMatcher A $ca B $cb C2 $cc, host $(uname -n) $(uname -r)"

    # Sources: RegexMatcher snapshots, and a worktree per harness commit.
    local c src
    for c in "$ca" "$cb" "$cc"; do
        src=$R2/rm-src-$c-full
        [ -d "$src" ] || { mkdir -p "$src" && git -C "$RM" archive "$c" | tar -x -C "$src"; } || stop "cannot export $c"
    done
    local wa=$R2/pt-4bedc11 wc=$R2/pt-c-${pc:0:9}
    [ -d "$wa" ] || git -C "$PAPER" worktree add -q --detach "$wa" 4bedc11 || stop "cannot add worktree 4bedc11"
    [ -d "$wc" ] || git -C "$PAPER" worktree add -q --detach "$wc" "$pc" || stop "cannot add worktree $pc"
    [ -z "$(git -C "$wa" status --porcelain)" ] || stop "$wa is not clean"

    # ------------------------------------------------------------ builds
    echo "== builds $(date -Is)"
    REGEXMATCHER_DIR=$R2/rm-src-$ca-full INPUTS_HASH_PY=$ih bash "$wa/bench/build.sh" "$out/build-a" "-DREGEXMATCHER_COMMIT=$ca" "${arms_arg[@]}" "${extra[@]}" ||
        { tail -40 "$out/build-a.log"; stop "build A failed"; }
    REGEXMATCHER_DIR=$R2/rm-src-$cb-full INPUTS_HASH_PY=$ih bash "$wa/bench/build.sh" "$out/build-b" "-DREGEXMATCHER_COMMIT=$cb" "${arms_arg[@]}" "${extra[@]}" ||
        { tail -40 "$out/build-b.log"; stop "build B failed"; }
    "$out/build-a/rbench" list | cut -f1 > "$out/arms-a.txt"
    "$out/build-b/rbench" list | cut -f1 > "$out/arms-b.txt"
    cmp -s "$out/arms-a.txt" "$out/arms-b.txt" || stop "binaries A and B hold different arms"
    # (c)'s binary: the engineering seeds' compile-time tables generated into its worktree first.
    if [ ! -f "$wc/bench/gen/ct_static_10_s2.cpp" ]; then
        INPUTS_HASH_PY=$ih bash "$wc/bench/build.sh" "$out/build-gen" "-DRB_ARMS=null" "${extra[@]}" || { tail -40 "$out/build-gen.log"; stop "gen build failed"; }
        "$out/build-gen/rbench" gen-ct --seeds 2,3,4,5 --out "$wc/bench/gen" > "$out/gen-ct.txt" || stop "gen-ct failed"
    fi
    echo "generated tables in $wc/bench/gen: $(ls "$wc/bench/gen" | wc -l)"
    REGEXMATCHER_DIR=$R2/rm-src-$cc-full INPUTS_HASH_PY=$ih bash "$wc/bench/build.sh" "$out/build-c" "-DREGEXMATCHER_COMMIT=$cc" "${arms_arg[@]}" "${extra[@]}" ||
        { tail -40 "$out/build-c.log"; stop "build C failed"; }
    "$out/build-c/rbench" list | grep regexmatcher

    # ------------------------------------------------------------ (a) build time, A against B
    echo "== (a) target (a), rule 2 $(date -Is)"
    local d=$out/a
    mkdir -p "$d"
    local b
    for b in a b; do
        "$out/build-$b/rbench" agree --arms regexmatcher-v2 --seeds 1,2,3,4,5 --sizes 1000 > "$d/agree-$b.jsonl" 2> "$d/agree-$b.err"
        python3 "$wa/bench/check_agree.py" "$d/agree-$b.jsonl" || stop "(a): binary $b does not agree"
    done
    if [ -f "$pin" ]; then
        bash "$pin" > "$d/pin.json" || [ "${ALLOW_UNPINNED:-0}" = 1 ] || stop "(a): the host is not pinned ($(cat "$d/pin.json"))"
    else
        [ "${ALLOW_UNPINNED:-0}" = 1 ] || stop "(a): no pin.sh at $pin"
    fi
    : > "$d/cells.jsonl"
    : > "$d/stderr.log"
    local s m k=0 p ts rs order line rc failed=0
    for s in ${A_SHAPES:-static param-last param-first rest wild mixed-disjoint mixed-overlap}; do
        for m in ${A_SIZES:-1000 10000 100000}; do
            k=0
            for p in $pairs; do
                ts=${p%%:*}; rs=${p##*:}
                if [ $((k % 2)) -eq 0 ]; then order="a b"; else order="b a"; fi
                for b in $order; do
                    line=$(timeout 1800 taskset -c 2 "$out/build-$b/rbench" cell --arm regexmatcher-v2 --shape "$s" --m "$m" \
                        --seed "$ts" --ring-seed "$rs" 2>>"$d/stderr.log")
                    rc=$?
                    if [ "$rc" -eq 0 ] && [ -n "$line" ]; then
                        printf '%s\n' "$line" | sed "s/^{/{\"binary\":\"$b\",/" >> "$d/cells.jsonl"
                    else
                        failed=$((failed + 1))
                        printf '{"binary":"%s","shape":"%s","m":%s,"table_seed":%s,"ring_seed":%s,"status":"failed","exit":%s}\n' \
                            "$b" "$s" "$m" "$ts" "$rs" "$rc" >> "$d/cells.jsonl"
                    fi
                done
                k=$((k + 1))
            done
        done
    done
    echo "(a) processes failed: $failed"
    python3 - "$d/cells.jsonl" > "$d/a-summary.txt" <<'EOF'
import collections, json, statistics, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
ok = [r for r in rows if r.get("status") == "ok"]
g = collections.defaultdict(list)
for r in ok:
    g[(r["shape"], r["m"], r["binary"])].append(r["build_s_median"])
cells = sorted({(r["shape"], r["m"]) for r in rows}, key=lambda c: (c[1], c[0]))
lower = 0
print("processes", len(rows), "ok", len(ok))
print("shape m | A median build (us) | B median build (us) | B/A | processes A, B")
for sh, m in cells:
    a, b = g[(sh, m, "a")], g[(sh, m, "b")]
    if not a or not b:
        print(f"{sh} {m} | missing"); continue
    ma, mb = statistics.median(a), statistics.median(b)
    lower += mb < ma
    print(f"{sh} {m} | {ma * 1e6:.1f} | {mb * 1e6:.1f} | {mb / ma:.3f} | {len(a)}, {len(b)}")
print(f"B lower in {lower} of {len(cells)} cells: rule 2 {'holds' if lower == len(cells) == 21 else 'does not hold' if len(cells) == 21 else 'not judged (not the 21 cells)'}")
EOF
    cat "$d/a-summary.txt"

    # ------------------------------------------------------------ (c) C2's H7 iteration check
    echo "== (c) C2, the H7 iteration check $(date -Is)"
    ARMS="regexmatcher-v2 regexmatcher-v2-ct" SHAPES="${C_SHAPES:-static param-last param-first rest wild mixed-disjoint mixed-overlap}"         SIZES="${C_SIZES:-10 100 1000}" REPS=10 PAIRS="$pairs" PIN=$pin CPU=2 \
        bash "$wc/bench/run_grid.sh" "$out/build-c/rbench" "$out/c" ||
        stop "(c): run_grid.sh failed ($(cat "$out/c/exit.txt" 2>/dev/null || echo 'no exit.txt'))"
    python3 - "$out/c/cells.jsonl" > "$out/c/c-summary.txt" <<'EOF'
import collections, json, statistics, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
ns = {(r["arm"], r["shape"], r["m"], r["table_seed"], r["ring_seed"]): r["ns_median"] for r in rows if r.get("status") == "ok"}
cells = sorted({(r["shape"], r["m"]) for r in rows}, key=lambda c: (c[1], c[0]))
worst = 0.0
over = 0
print("shape m | median ratio ct/rt over pairs | pairs | pairs above 1.02 | largest pair ratio")
for sh, m in cells:
    rs = []
    for (arm, s, mm, ts, r), v in ns.items():
        if arm == "regexmatcher-v2" and s == sh and mm == m and ("regexmatcher-v2-ct", s, mm, ts, r) in ns:
            rs.append(ns[("regexmatcher-v2-ct", s, mm, ts, r)] / v)
    if not rs:
        print(f"{sh} {m} | missing"); over += 1; continue
    med = statistics.median(rs)
    worst = max(worst, med)
    over += med > 1.02
    print(f"{sh} {m} | {med:.4f} | {len(rs)} | {sum(x > 1.02 for x in rs)} | {max(rs):.4f}")
print(f"cells with a median ratio above 1.02: {over} of {len(cells)}; largest median {worst:.4f}; "
      f"the check {('passes' if over == 0 else 'does not pass') if len(cells) == 21 else 'not judged (not the 21 cells)'}")
EOF
    cat "$out/c/c-summary.txt"
    status=done
    echo "slot2 jobs done $(date -Is)"
}

main "$@"
exit
