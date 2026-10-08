#!/usr/bin/env bash
# The T1 run of H6 (design/round2/hypotheses-v2-proposal.md, H6), on the lab host L under
# lab/bin/lablock.
#
# Usage: run_h6.sh OUT_DIR
#
# Builds, fresh: the paper's root project (t1/h6_targets and the minimal server mserver, one binary
# with three router arms; clang, Release, RegexMatcher v2 from REGEXMATCHER_DIR), hashed as
# t1/sanitize_h6.sh hashes it, and t1gen from the Papers repo's lab/t1/gen (Release, clang, as its
# sanitizer record built it). Gates the server build with t1/check_h6_records.py and refuses to
# measure if it fails. Then, per cell (the seven shapes at m = 10; rest and param-last at
# m = 10,000): h6_targets writes the routes and one target per route (table seed 111, ring seed
# 211, the pair of H6), and lab/t1's t1.py measures the three arms (h6-v1, the reference; h6-v2;
# h6-null), which differ only in --router, in mirrored rounds: one server core, 64 connections,
# depth 1, a 1 s warm-up and a 5 s window, at least 6 and at most 20 pairs (6, so that an exact
# sign test can reach 2^-6 = 0.0156 < 0.025, rule D9), only rounds whose six windows are all valid
# counting toward the minimum and the stop (t1.py --valid-pairs-only), t1gen --paths with the cell's
# targets.
#
# Environment: REGEXMATCHER_DIR (required: a snapshot of the RegexMatcher commit measured) and
# REGEXMATCHER_COMMIT (that commit, in full), RECORDS (default the Papers repo's
# lab/sanitizer-records), INPUTS_HASH_PY, CHECK_ONLY=1 (build and gate, measure nothing; OUT_DIR
# then holds the builds and the gate only). RegexMatcher v1 is fetched, pinned (bench/cmake/pins.cmake).
set -euo pipefail

out=${1:?usage: run_h6.sh OUT_DIR}
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
papers=$(cd "$root/../.." && pwd)
records=${RECORDS:-$papers/lab/sanitizer-records}
ih=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
rm_dir=$(cd "${REGEXMATCHER_DIR:?REGEXMATCHER_DIR is required}" && pwd)
rm_commit=${REGEXMATCHER_COMMIT:?REGEXMATCHER_COMMIT is required}
refuse() { echo "run_h6: $*" >&2; exit 1; }

[ ! -e "$out" ] || refuse "$out exists; a run is never overwritten"
[ -z "$(git -C "$root" status --porcelain -- CMakeLists.txt t1 server bench/core bench/arms/regexmatcher_v1_wrap.hpp bench/cmake)" ] ||
    refuse "the server or the H6 tools have local changes"
[ -z "$(git -C "$papers" status --porcelain -- lab/t1)" ] || refuse "lab/t1 has local changes"
mkdir -p "$out"
out=$(cd "$out" && pwd)
bin=$out/bin
mkdir -p "$bin"

build=$out/build
cmake -S "$root" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    "-DREGEXMATCHER_DIR=$rm_dir" > "$build.log" 2>&1 && cmake --build "$build" -j"$(nproc)" >> "$build.log" 2>&1 ||
    refuse "the build failed (see $build.log)"
python3 "$ih" --build "h6=$build" --target mserver --target mserver_arms --target mserver_http1 --target mserver_loop \
    --target mserver_v1 --target h6_targets --root-label project \
    --dep-root regexmatcher=RegexMatcher_SOURCE_DIR --out "$build.inputs.json" > /dev/null
python3 "$ih" --build "h6=$build" --target mserver_arms --root-label project \
    --dep-root regexmatcher=RegexMatcher_SOURCE_DIR --label-hash regexmatcher/include/ --out "$build.v2-include.json" > /dev/null
gen_commit=$(git -C "$papers" log -1 --format=%H -- lab/t1/gen)
cmake -S "$papers/lab/t1/gen" -B "$out/build-t1gen" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang \
    -DT1GEN_COMMIT="$gen_commit" > "$out/build-t1gen.log" 2>&1
cmake --build "$out/build-t1gen" >> "$out/build-t1gen.log" 2>&1
compiler=$(sed -n 's/^-- The CXX compiler identification is //p' "$build.log" | head -1)
python3 "$here/check_h6_records.py" --records "$records" --inputs "$build.inputs.json" --compiler "$compiler" \
    --pins "$root/bench/cmake/pins.cmake" > "$out/gate.json" 2> "$out/gate.txt" ||
    refuse "the sanitizer records do not cover the server build ($(tail -1 "$out/gate.txt")); nothing measured"
echo "gate passed: the server, RegexMatcher $rm_commit, $compiler"
# t1gen: lab/t1's t1.py marks a window not citable unless t1gen-<its commit>.json is green; the
# same check here, so a missing or red generator record stops the run before it measures.
gen_record=$records/t1gen-${gen_commit:0:9}.json
python3 -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1])).get("green") is True else 1)' "$gen_record" ||
    refuse "no green t1gen record $gen_record for lab/t1/gen at $gen_commit; nothing measured"
echo "t1gen record green: $(basename "$gen_record")"
if [ "${CHECK_ONLY:-0}" = 1 ]; then
    echo "CHECK_ONLY: built and gated, nothing measured"
    exit 0
fi
ln -sf "$build/server/mserver" "$bin/mserver"
ln -sf "$out/build-t1gen/t1gen" "$bin/t1gen"
{
    echo "paper $(git -C "$root" rev-parse HEAD)"
    echo "papers $(git -C "$papers" rev-parse HEAD)"
    echo "regexmatcher_commit $rm_commit"
    echo "t1gen_commit $gen_commit"
    echo "compiler $compiler"
    echo "isa $(sed -n 's/^-- isa: //p' "$build.log" | head -1)"
    echo "pins_sha256 $(tr -d '\r' < "$root/bench/cmake/pins.cmake" | sha256sum | cut -d' ' -f1) (bench/cmake/pins.cmake, CRLF read as LF; the archives fetched as used are in build.inputs.json, third_party)"
    echo "mserver sha256 $(sha256sum "$build/server/mserver" | cut -d' ' -f1)"
    echo "t1gen sha256 $(sha256sum "$out/build-t1gen/t1gen" | cut -d' ' -f1)"
    echo "date $(date -Is)"
} > "$out/provenance.txt"

cells="static:10 param-last:10 param-first:10 rest:10 wild:10 mixed-disjoint:10 mixed-overlap:10 rest:10000 param-last:10000"
for c in $cells; do
    shape=${c%%:*}; m=${c##*:}; d=$out/$shape-$m
    mkdir -p "$d"
    "$build/h6_targets" --shape "$shape" --m "$m" --table-seed 111 --ring-seed 211 \
        --routes "$d/routes.txt" --targets "$d/targets.txt" > "$d/targets.out"
    python3 - "$d" <<'EOF'
import json, sys
from pathlib import Path
d = Path(sys.argv[1])
gate = json.loads((d.parent / "gate.json").read_text())
def arm(router, label):
    return {"label": label,
            "cmd": ["{build}/mserver", "--workers", "{workers}", "--port", "{port}", "--routes",
                    str(d / "routes.txt"), "--router", router],
            "env": {}, "self_written_cpp": True, "sanitizer_record": gate["records"]}
arms = {"_comment": "H6 arms (t1/run_h6.sh): one server binary, three router arms; the records are those the gate "
                    "matched by compiled inputs (gate.json).",
        "h6-v1": arm("v1", "mserver, RegexMatcher v1 behind its wrapper (the reference)"),
        "h6-v2": arm("v2", "mserver, RegexMatcher v2"),
        "h6-null": arm("null", "mserver, the null router")}
(d / "arms.json").write_text(json.dumps(arms, indent=1) + "\n")
EOF
    python3 "$papers/lab/t1/t1.py" --arms h6-v1,h6-v2,h6-null --arms-file "$d/arms.json" --build "$bin" \
        --out "$d/t1" --cores 1 --depth 1 --min-pairs 6 --max-pairs 20 --valid-pairs-only --paths "$d/targets.txt" \
        > "$d/t1.out" 2>&1 || echo "cell $shape-$m: t1.py exit $?" >> "$out/failures.txt"
    echo "$shape-$m done $(date -Is)" >> "$out/progress.txt"
done
