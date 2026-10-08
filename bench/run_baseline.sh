#!/usr/bin/env bash
# The gated main grid of round 2 (H1 to H4, H7; design/round2/hypotheses-v2-proposal.md), on the
# lab host L under lab/bin/lablock.
#
# Usage: run_baseline.sh   (RUN_NAME names results/raw/<RUN_NAME>; default <date>-L-publication)
#
# Builds rbench fresh (build.sh: every arm, one binary, RegexMatcher v2 from REGEXMATCHER_DIR),
# which also hashes what every target compiled (lab/bin/inputs_hash.py) and the RegexMatcher
# headers of v2's arms (BUILD.v2-include.json), and gates the build (check_records.py): for
# every target and every sanitizer a green rbench record made on L compiled the same inputs,
# a gap only where coverage.json declares it; and green RegexMatcher records on L compiled the
# same RegexMatcher headers under every sanitizer. Only then does run_grid.sh measure, with
# its defaults (the sixteen held-out pairs, R = 16, every arm, the cell order shuffled with
# SEED). The run directory keeps the gate, the build log, the inputs, where each timed function
# landed (symbols.tsv, address modulo 64), the instruction set it was built for (rb_isa.h) and
# the provenance.
#
# Environment: REGEXMATCHER_DIR (required: a snapshot of the RegexMatcher commit measured) and
# REGEXMATCHER_COMMIT (that commit, in full), RECORDS (default the Papers repo's
# lab/sanitizer-records), INPUTS_HASH_PY, SEED (default 20261009, the order seed of hypotheses-round2.md; round 1 used 20260927), RUN_NAME,
# CHECK_ONLY=1 (build and gate, measure nothing), RB_ARMS (a CMake list of the arms to build;
# default every arm of RB_ALL_ARMS, as the main grid built them), and run_grid.sh's variables.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
papers=$(cd "$repo/../.." && pwd)
rm_dir=$(cd "${REGEXMATCHER_DIR:?REGEXMATCHER_DIR is required}" && pwd)
rm_commit=${REGEXMATCHER_COMMIT:?REGEXMATCHER_COMMIT is required (the commit of REGEXMATCHER_DIR)}
records=${RECORDS:-$papers/lab/sanitizer-records}
inputs_py=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
seed=${SEED:-20261009}
out=$repo/results/raw/${RUN_NAME:-$(date +%Y-%m-%d)-L-publication}
sources=(main.cpp core arms cmake gen CMakeLists.txt coverage.json semantics.json)

refuse() { echo "run_baseline: $*" >&2; exit 1; }

code=$(git -C "$here" log -1 --format=%H -- "${sources[@]}")
[ -z "$(git -C "$here" status --porcelain -- "${sources[@]}")" ] || refuse "rbench sources have local changes"
[ "${CHECK_ONLY:-0}" = 1 ] || [ ! -e "$out" ] || refuse "$out exists; a gated run is never overwritten"

build=$here/build-publication
REGEXMATCHER_DIR="$rm_dir" INPUTS_HASH_PY="$inputs_py" bash "$here/build.sh" "$build" "-DREGEXMATCHER_COMMIT=$rm_commit" \
    ${RB_ARMS:+"-DRB_ARMS=$RB_ARMS"}
compiler=$(sed -n 's/^-- The CXX compiler identification is //p' "$build.log" | head -1)
gate=$(python3 "$here/check_records.py" --records "$records" --inputs "$build.inputs.json" --compiler "$compiler" --pins "$here/cmake/pins.cmake") ||
    refuse "the sanitizer records do not cover what this build compiled (see above); nothing measured"
echo "gate passed: rbench, RegexMatcher $rm_commit, $compiler"
if [ "${CHECK_ONLY:-0}" = 1 ]; then
    echo "CHECK_ONLY: built and gated, nothing measured"
    exit 0
fi
mkdir -p "$out"
printf '%s\n' "$gate" >"$out/gate.json"
cp "$build.log" "$out/build.log"
cp "$build.inputs.json" "$out/inputs.json"
cp "$build.v2-include.json" "$out/v2-include.json"
cp "$build.symbols.tsv" "$out/symbols.tsv"
cp "$build/rb-isa/rb_isa.h" "$out/rb_isa.h"
{
    echo "code_commit: $code"
    echo "repo_head: $(git -C "$repo" rev-parse HEAD)"
    echo "papers_head: $(git -C "$papers" rev-parse HEAD)"
    echo "regexmatcher_dir: $rm_dir"
    echo "regexmatcher_commit: $rm_commit"
    echo "compiler: $compiler"
    echo "isa: $(sed -n 's/^-- isa: //p' "$build.log" | head -1) (rb_isa.h)"
    echo "pins_sha256: $(tr -d '\r' < "$here/cmake/pins.cmake" | sha256sum | cut -d' ' -f1) (bench/cmake/pins.cmake, CRLF read as LF; the archives fetched as used are in inputs.json, third_party)"
    echo "seed: $seed"
    echo "date: $(date -Is)"
} >"$out/provenance.txt"
SEED="$seed" bash "$here/run_grid.sh" "$build/rbench" "$out" || true
