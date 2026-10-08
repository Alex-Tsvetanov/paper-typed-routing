#!/usr/bin/env bash
# build.sh BUILD_DIR [CMAKE_ARGS...]: configure and build rbench from a fresh directory with
# clang, Release, against REGEXMATCHER_DIR (RegexMatcher v2). Writes BUILD_DIR.log (configure and
# build output) and BUILD_DIR.inputs.json: what the build compiled (lab/bin/inputs_hash.py over
# rbench and every arm_* target, RegexMatcher v2's files included under the label regexmatcher/).
# When the build has v2's arms, BUILD_DIR.v2-include.json holds, for each target that compiles
# v2 (arm_regexmatcher_v2, arm_regexmatcher_v2_ct, arm_regexmatcher_v2_ct_heap), the hash of its inputs under
# regexmatcher/include/ (--label-hash), which the records gate matches with RegexMatcher's own
# sanitizer records (design/round2/regexmatcher-v2.md). BUILD_DIR.symbols.tsv holds the address
# modulo 64 of each timed function (symbols.py). BUILD_DIR/rb-isa/rb_isa.h holds the instruction
# set every arm was compiled for (cmake/isa.cmake).
#
# Environment: REGEXMATCHER_DIR (required while v2 is not public), INPUTS_HASH_PY (default: the
# Papers repo's lab/bin/inputs_hash.py), CC and CXX (default clang, clang++).
set -euo pipefail

build=${1:?usage: build.sh BUILD_DIR [CMAKE_ARGS...]}
shift
here=$(cd "$(dirname "$0")" && pwd)
rm_dir=${REGEXMATCHER_DIR:+$(cd "$REGEXMATCHER_DIR" && pwd)}
inputs_py=${INPUTS_HASH_PY:-$here/../../../lab/bin/inputs_hash.py}

rm -rf "${build:?}"
mkdir -p "$build"
build=$(cd "$build" && pwd)
cmake -S "$here" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER="${CC:-clang}" -DCMAKE_CXX_COMPILER="${CXX:-clang++}" \
    ${rm_dir:+-DREGEXMATCHER_DIR="$rm_dir"} -DCMAKE_EXPORT_COMPILE_COMMANDS=ON "$@" >"$build.log" 2>&1
cmake --build "$build" -j"$(nproc)" >>"$build.log" 2>&1

targets=(--target rbench)
arms=$("$build/rbench" list | grep -v '^#' | cut -f1)
for a in $arms; do
    targets+=(--target "arm_${a//-/_}")
done
# RegexMatcher v2 is first-party (the paper's subject): its checkout, or its fetched copy, is a
# dependency root, and its include directory is hashed on its own for the arms that compile it,
# to be matched with RegexMatcher's own records.
v2=()
v2_targets=()
for a in $arms; do
    case $a in
        regexmatcher-v2 | regexmatcher-v2-ct | regexmatcher-v2-ct-heap) v2_targets+=(--target "arm_${a//-/_}") ;;
    esac
done
[ ${#v2_targets[@]} -eq 0 ] || v2=(--dep-root regexmatcher=RegexMatcher_SOURCE_DIR)
python3 "$inputs_py" --build "rbench=$build" "${targets[@]}" "${v2[@]}" --out "$build.inputs.json" >/dev/null
if [ ${#v2_targets[@]} -gt 0 ]; then
    python3 "$inputs_py" --build "rbench=$build" "${v2_targets[@]}" "${v2[@]}" \
        --label-hash regexmatcher/include/ --out "$build.v2-include.json" >/dev/null
fi
# Where each timed function landed (address modulo 64; symbols.py, audit m29).
python3 "$here/symbols.py" "$build/rbench" "$build.symbols.tsv"
echo "built $build ($(sed -n 's/^-- The CXX compiler identification is //p' "$build.log" | head -1); $(sed -n 's/^-- isa: //p' "$build.log" | head -1))"
