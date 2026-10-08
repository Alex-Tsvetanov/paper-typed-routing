#!/usr/bin/env bash
# ct_cost_run.sh OUT_DIR: the costs H7 reports (hypotheses-round2.md, H7), from the sources the
# publication run measures, gated like every measured build.
#
# A fresh build of the compile-time arm alone (its adapter and every generated table, the target
# arm_regexmatcher_v2_ct; the configuration also names regexmatcher-v2, which defines the lookup
# both v2 arms call, but only the compile-time arm's target is built), one translation unit at a
# time (-j1), so that each compile-time table's compile time is that of a quiet machine. The
# build is hashed (lab/bin/inputs_hash.py, as bench/build.sh hashes rbench's targets, with
# RegexMatcher v2 as the dependency root and its headers hashed on their own) and gated
# (bench/check_records.py): green rbench records on L for ASan+UBSan, TSan and MSan compiled the
# same inputs for arm_regexmatcher_v2_ct with the same compiler and pins, and green RegexMatcher
# records compiled the same headers. Only then are the costs read: ct_costs.py reads each table's
# compile time from Ninja's log with its object's loadable sections (text, rodata, data, bss) and
# file size (OUT_DIR/ct_costs.jsonl), and ct_steps.py finds the constant-evaluation budget clang
# needs per table (OUT_DIR/ct_steps.jsonl), for table seed 111 of every shape and size and for the
# GitHub table. Run it under lab/bin/lablock, with REGEXMATCHER_DIR (a snapshot) and
# REGEXMATCHER_COMMIT at the RegexMatcher the run measures.
#
# Environment: REGEXMATCHER_DIR, REGEXMATCHER_COMMIT (both required), RECORDS (default the Papers
# repo's lab/sanitizer-records), INPUTS_HASH_PY, CC and CXX (default clang, clang++), CHECK_ONLY=1
# (build with every core and gate, read no cost: the gate alone).
set -euo pipefail

out=${1:?usage: ct_cost_run.sh OUT_DIR}
here=$(cd "$(dirname "$0")" && pwd)
papers=$(cd "$here/../../.." && pwd)
rm_dir=$(cd "${REGEXMATCHER_DIR:?REGEXMATCHER_DIR is required}" && pwd)
rm_commit=${REGEXMATCHER_COMMIT:?REGEXMATCHER_COMMIT is required}
records=${RECORDS:-$papers/lab/sanitizer-records}
inputs_py=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
sources=(main.cpp core arms cmake gen CMakeLists.txt coverage.json semantics.json)
refuse() { echo "ct_cost_run: $*" >&2; exit 1; }

[ -z "$(git -C "$here" status --porcelain -- "${sources[@]}")" ] || refuse "rbench sources have local changes"
mkdir -p "$out"
out=$(cd "$out" && pwd)
build=$out/ct-build
rm -rf "$build"
jobs=1
[ "${CHECK_ONLY:-0}" != 1 ] || jobs=$(nproc)
cmake -S "$here" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER="${CC:-clang}" \
    -DCMAKE_CXX_COMPILER="${CXX:-clang++}" -DREGEXMATCHER_DIR="$rm_dir" -DREGEXMATCHER_COMMIT="$rm_commit" \
    "-DRB_ARMS=regexmatcher-v2;regexmatcher-v2-ct" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON >"$out/ct-build.log" 2>&1 ||
    refuse "configure failed (see $out/ct-build.log)"
cmake --build "$build" -j"$jobs" --target arm_regexmatcher_v2_ct >>"$out/ct-build.log" 2>&1 ||
    refuse "build failed (see $out/ct-build.log)"
compiler=$(sed -n 's/^-- The CXX compiler identification is //p' "$out/ct-build.log" | head -1)

# What the build compiled, and the gate (as bench/build.sh and bench/run_baseline.sh do it).
python3 "$inputs_py" --build "rbench=$build" --target arm_regexmatcher_v2_ct \
    --dep-root regexmatcher=RegexMatcher_SOURCE_DIR --out "$build.inputs.json" >/dev/null
python3 "$inputs_py" --build "rbench=$build" --target arm_regexmatcher_v2_ct \
    --dep-root regexmatcher=RegexMatcher_SOURCE_DIR --label-hash regexmatcher/include/ --out "$build.v2-include.json" >/dev/null
python3 "$here/check_records.py" --records "$records" --inputs "$build.inputs.json" --compiler "$compiler" \
    --pins "$here/cmake/pins.cmake" --out "$out/gate.json" 2>"$out/gate.txt" ||
    refuse "the sanitizer records do not cover the compile-time arm's build ($(tail -1 "$out/gate.txt")); no cost read"
echo "gate passed: arm_regexmatcher_v2_ct, RegexMatcher $rm_commit, $compiler"
if [ "${CHECK_ONLY:-0}" = 1 ]; then
    echo "CHECK_ONLY: built with $jobs jobs and gated, no cost read"
    exit 0
fi
{
    echo "regexmatcher_commit: $rm_commit"
    echo "rbench_commit: $(git -C "$here" rev-parse HEAD)"
    echo "code_commit: $(git -C "$here" log -1 --format=%H -- "${sources[@]}")"
    echo "compiler: $compiler"
    echo "isa: $(sed -n 's/^-- isa: //p' "$out/ct-build.log" | head -1)"
    echo "jobs: 1"
    echo "pins_sha256: $(tr -d '\r' < "$here/cmake/pins.cmake" | sha256sum | cut -d' ' -f1) (bench/cmake/pins.cmake, CRLF read as LF)"
    echo "gate: $out/gate.json"
} >"$out/ct-provenance.txt"
cp "$build.inputs.json" "$out/inputs.json"
cp "$build.v2-include.json" "$out/v2-include.json"
python3 "$here/ct_costs.py" "$build" --out "$out/ct_costs.jsonl" >/dev/null
tables=$(cd "$here/gen" && ls ct_*_s111.cpp ct_github_*.cpp | sed 's/^ct_//; s/\.cpp$//' | tr '\n' ',' | sed 's/,$//')
python3 "$here/ct_steps.py" "$build" --tables "$tables" --out "$out/ct_steps.jsonl" >/dev/null
echo "ct_cost_run: $(wc -l <"$out/ct_costs.jsonl") tables costed, $(wc -l <"$out/ct_steps.jsonl") budgets found"
