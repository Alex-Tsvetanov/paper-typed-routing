#!/usr/bin/env bash
# slot3.sh OUT_DIR: round 2's third L slot, development, nothing citable. Adoption rule (b) of
# design/round2/engineering.md, section 2.5, part 1 (instructions per lookup, net of the null
# arm), decided on L with clang 22.1.8 for the candidates built in WSL:
#     A    45ab696  C2, the state before target (b)
#     B1   2147f86  chained edges in linear nodes
#     B1a  0a94cdc  B1', chain nodes, first build
#     B1b  4282ba7  B1', second build (chain nodes for runs of two or more segments)
# Every candidate is built with the same arms (null, regexmatcher-v2, regexmatcher-v2-ct,
# regexmatcher-v2-r1, gin) from one harness (paper commit PAPER_COMMIT, a worktree). From each:
# run_grid.sh with the null arm and regexmatcher-v2, every shape at m = 10 to 100,000 (35 cells),
# table seed 1, ring seeds 2 and 3, pinned, CPU 2; gin once, from A's binary. Per candidate
# also: table_digest at table seed 1 (which cells have a chain), and, for the candidates with the
# backtracking hook, backtrack_check (rule (b), part 3, again on L). summary.txt applies the
# three clauses of part 1 as declared, a rise being 0.5 or more net instructions per lookup:
#   1. no rise in a cell whose table has no chain;
#   2. no rise in any cell;
#   3. at mixed-disjoint m = 10, the candidate's net count below gin's in both pairs.
# Part 2 (time) follows only for a candidate that passes part 1, in a job of its own.
#
# Run from a clone of this repository at $R2/typed-routing, under the lab's lablock, with a pid
# file and a done file (OUT_DIR.done: the time and "done", "STOPPED:" and the reason, or
# "incomplete"):
#     PAPER_COMMIT=... nohup ~/lab/Papers/lab/bin/lablock \
#         bash ~/lab/p2/r2/typed-routing/bench/jobs/slot3.sh ~/lab/p2/r2/slot3 > ~/lab/p2/r2/slot3.log 2>&1 &
#     echo $! > ~/lab/p2/r2/slot3.pid
#
# Environment: PAPER_COMMIT (default the paper's main), R2 (default ~/lab/p2/r2), PAPERS (a Papers
# clone, default $R2/Papers: lab/bin), PAPER (default $R2/typed-routing). RegexMatcher comes
# from the bare repository on L (the remote named lab on W; never GitHub). For a reduced test
# run only (WSL): CANDIDATES ("name:commit ..."), BUILD_ARMS, GIN (0: no gin), SHAPES, SIZES, PIN,
# ALLOW_UNPINNED=1, EXTRA_CMAKE. A run that sets any of them is not the job described above.
#
# Downloads: FetchContent archives from GitHub, each checked against its sha256 in
# cmake/pins.cmake; a Go module missing from L's cache from its repository, not a proxy; Go never
# fetches a toolchain.
#
# The whole job is one function, read completely before it runs.
set -uo pipefail
export GOPROXY=direct GOTOOLCHAIN=local

main() {
    local out=${1:?usage: slot3.sh OUT_DIR}
    mkdir -p "$out"
    out=$(cd "$out" && pwd)
    status=incomplete
    trap 'echo "$(date -Is) $status" > "'"$out"'.done"' EXIT
    exec > >(tee -a "$out/slot3.log") 2>&1
    local R2=${R2:-$HOME/lab/p2/r2}
    local PAPERS=${PAPERS:-$R2/Papers}
    local PAPER=${PAPER:-$R2/typed-routing}
    local RM=$R2/RegexMatcher
    local pin=${PIN:-$PAPERS/lab/bin/pin.sh}
    local ih=$PAPERS/lab/bin/inputs_hash.py
    local candidates=${CANDIDATES:-A:45ab696 B1:2147f86 B1a:0a94cdc B1b:4282ba7}
    local arms=${BUILD_ARMS:-null;regexmatcher-v2;regexmatcher-v2-ct;regexmatcher-v2-r1;gin}
    local gin=${GIN:-1}
    local shapes=${SHAPES:-static param-last param-first rest wild mixed-disjoint mixed-overlap}
    local sizes=${SIZES:-10 100 1000 10000 100000}
    local extra=()
    [ -n "${EXTRA_CMAKE:-}" ] && read -r -a extra <<< "$EXTRA_CMAKE"
    stop() { status="STOPPED: $*"; echo "$status"; exit 1; }

    git -C "$PAPERS" pull -q --ff-only || stop "cannot update $PAPERS"
    git -C "$PAPER" fetch -q origin || stop "cannot fetch $PAPER"
    local pc
    pc=$(git -C "$PAPER" rev-parse --verify "${PAPER_COMMIT:-origin/main}^{commit}") || stop "no commit ${PAPER_COMMIT:-origin/main}"
    git -C "$RM" fetch -q origin || stop "cannot fetch RegexMatcher from the bare repository"
    local wc=$R2/pt-c-${pc:0:9}
    [ -d "$wc" ] || git -C "$PAPER" worktree add -q --detach "$wc" "$pc" || stop "cannot add worktree $pc"
    [ -z "$(git -C "$wc" status --porcelain)" ] || stop "$wc is not clean"
    echo "slot3 start $(date -Is), Papers $(git -C "$PAPERS" rev-parse HEAD), paper $pc, host $(uname -n) $(uname -r)"

    # ------------------------------------------------------------ builds and tables
    local cand name c full src
    : > "$out/candidates.txt"
    for cand in $candidates; do
        name=${cand%%:*}; c=${cand##*:}
        full=$(git -C "$RM" rev-parse --verify "$c^{commit}") || stop "RegexMatcher $c is missing"
        echo "$name $full" >> "$out/candidates.txt"
        src=$R2/rm-src-$full-full
        [ -d "$src" ] || { mkdir -p "$src" && git -C "$RM" archive "$full" | tar -x -C "$src"; } || stop "cannot export $full"
        echo "== build $name ($full) $(date -Is)"
        REGEXMATCHER_DIR=$src INPUTS_HASH_PY=$ih bash "$wc/bench/build.sh" "$out/build-$name" "-DRB_ARMS=$arms" \
            "-DREGEXMATCHER_COMMIT=$full" "${extra[@]}" || { tail -40 "$out/build-$name.log"; stop "build $name failed"; }
        "$out/build-$name/rbench" list | cut -f1 > "$out/arms-$name.txt"
        cmp -s "$out/arms-$name.txt" "$out/arms-$(echo $candidates | cut -d: -f1).txt" || stop "binary $name holds other arms"
        cmake -S "$wc/bench/tools" -B "$out/tools-$name" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=clang++ \
            -DREGEXMATCHER_DIR="$src" > "$out/tools-$name.log" 2>&1 &&
            cmake --build "$out/tools-$name" --target table_digest >> "$out/tools-$name.log" 2>&1 || stop "table_digest $name failed"
        "$out/tools-$name/table_digest" --seed 1 > "$out/digest-$name.tsv" || stop "table_digest $name failed to run"
        if grep -q MATCHER_ROUTE_ON_BACKTRACK "$src/include/matcher/route/config.hpp"; then
            cmake --build "$out/tools-$name" --target backtrack_check >> "$out/tools-$name.log" 2>&1 || stop "backtrack_check $name failed to build"
            "$out/tools-$name/backtrack_check" --seeds 1,2,3,4,5 --ring-seeds 2,3 > "$out/backtrack-$name.txt"
            echo "backtrack_check $name exit $?: $(tail -1 "$out/backtrack-$name.txt")"
        fi
    done

    # ------------------------------------------------------------ grids
    local grid_arms
    for cand in $candidates; do
        name=${cand%%:*}
        grid_arms="null regexmatcher-v2"
        [ "$name" = "$(echo $candidates | cut -d: -f1)" ] && [ "$gin" = 1 ] && grid_arms="$grid_arms gin"
        echo "== grid $name ($grid_arms) $(date -Is)"
        ARMS="$grid_arms" SHAPES="$shapes" SIZES="$sizes" REPS=2 PAIRS="1:2 1:3" PIN=$pin CPU=2 \
            bash "$wc/bench/run_grid.sh" "$out/build-$name/rbench" "$out/grid-$name" ||
            echo "grid $name: run_grid.sh reported a failure ($(cat "$out/grid-$name/exit.txt" 2>/dev/null))"
        cat "$out/grid-$name/exit.txt"
    done

    # ------------------------------------------------------------ the clauses
    python3 - "$out" $candidates > "$out/summary.txt" <<'EOF'
import csv, json, sys
out, cands = sys.argv[1], [c.split(":")[0] for c in sys.argv[2:]]
base = cands[0]
net, cells, gin = {}, set(), {}
for name in cands:
    rows = [json.loads(l) for l in open(f"{out}/grid-{name}/cells.jsonl")]
    by = {(r["arm"], r["shape"], r["m"], r["ring_seed"]): r for r in rows if r.get("status") == "ok"}
    for (arm, sh, m, rs), r in by.items():
        nul = by.get(("null", sh, m, rs))
        if nul is None or r.get("instructions") is None:
            continue
        v = r["instructions"] - nul["instructions"]
        if arm == "regexmatcher-v2":
            net[(name, sh, m, rs)] = v; cells.add((sh, m))
        elif arm == "gin":
            gin[(sh, m, rs)] = v
def chains(name):
    out_ = {}
    for r in csv.DictReader(open(f"{out}/digest-{name}.tsv"), delimiter="\t"):
        out_[(r["shape"], int(r["m"]))] = int(r.get("chained_edges") or 0) + int(r.get("chain_nodes") or 0)
    return out_
order = ["static", "param-last", "param-first", "rest", "wild", "mixed-disjoint", "mixed-overlap"]
cells = sorted(cells, key=lambda c: (order.index(c[0]) if c[0] in order else 99, c[1]))
print(f"net instructions per lookup (regexmatcher-v2 minus null, same binary), rings 2 and 3; base {base}")
for name in cands:
    ch = chains(name)
    print(f"\n{name}: shape m | chains | {base} | {name} | {name} - {base}")
    rise_nochain = rise_any = missing = 0
    for sh, m in cells:
        a = [net.get((base, sh, m, rs)) for rs in (2, 3)]
        b = [net.get((name, sh, m, rs)) for rs in (2, 3)]
        if None in a or None in b:
            missing += 1; print(f"  {sh} {m} | missing"); continue
        d = [y - x for x, y in zip(a, b)]
        rise = max(d) >= 0.5
        rise_any += rise
        rise_nochain += rise and ch.get((sh, m), 0) == 0
        print(f"  {sh:15s} {m:>6} | {ch.get((sh, m), 0):>5} | {a[0]:7.1f} {a[1]:7.1f} | {b[0]:7.1f} {b[1]:7.1f} | {d[0]:+6.1f} {d[1]:+6.1f}")
    if name == base:
        continue
    g = [gin.get(("mixed-disjoint", 10, rs)) for rs in (2, 3)]
    b = [net.get((name, "mixed-disjoint", 10, rs)) for rs in (2, 3)]
    c3 = None if None in g or None in b else all(y < x for x, y in zip(g, b))
    c1, c2 = rise_nochain == 0, rise_any == 0
    ok = c1 and c2 and c3 is True and missing == 0 and len(cells) == 35
    print(f"  clause 1 (no rise without a chain): {'holds' if c1 else f'fails in {rise_nochain} cells'}")
    print(f"  clause 2 (no rise in any cell): {'holds' if c2 else f'fails in {rise_any} cells'}")
    print(f"  clause 3 (mixed-disjoint m = 10 below gin, both pairs): "
          f"{'no gin cell' if c3 is None else ('holds' if c3 else 'fails')} (gin {g}, {name} {b})")
    print(f"  {name}: part 1 {'passes' if ok else 'does not pass'}" + ("" if len(cells) == 35 else " (not the 35 cells: not judged)"))
EOF
    cat "$out/summary.txt"
    status=done
    echo "slot3 jobs done $(date -Is)"
}

main "$@"
exit
