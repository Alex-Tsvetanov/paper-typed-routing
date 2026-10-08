#!/usr/bin/env bash
# Sanitizer record for rbench on Linux (lab host L).
#
# Usage: sanitize_rbench.sh asan|tsan|msan [RECORDS_DIR]
#
# Builds rbench (every arm, RegexMatcher v2 from REGEXMATCHER_DIR) under the sanitizer, runs the
# agreement test, the probes and a quick cell of every arm on every shape at 10 and 1000
# routes (run_grid.sh with QUICK=1), and writes RECORDS_DIR/rbench-<code commit>-L-<san>.json
# (sanitizer_record.py). <code commit> is the last commit that changed rbench's sources; they
# must have no local changes. Runtime options are those of round 1's records. The record names
# what every target compiled, and the gate (check_records.py) matches records to a measured
# build by that, whatever the commit.
#
# Environment: REGEXMATCHER_DIR (required: a snapshot of the RegexMatcher commit measured, as
# git archive writes it) and REGEXMATCHER_COMMIT (that commit, in full), WORK (default
# ~/lab/p2/rbench-san), MSAN_LIBCXX (default $HOME/opt/libcxx-msan-gcc), RB_ARMS (a CMake list;
# default every arm, less those coverage.json exempts from the sanitizer), TAG (appended to the
# record's name), HOST_TAG (the record name's host, default L), EXTRA_CMAKE (more CMake arguments;
# recorded), RECORDS_LOGS (default ~/lab/records-logs). The logs (the build log, what the build
# compiled, and run_grid.sh's whole output directory; not the build tree) are copied to
# ~/lab/records-logs/<record name>/ and packed into <record name>.tar.gz beside it, whose sha256
# the record carries (bench/keep_record_logs.sh); the script refuses to start if that directory
# or archive exists.
set -euo pipefail

san=${1:?usage: sanitize_rbench.sh asan|tsan|msan [RECORDS_DIR]}
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
records=${2:-$repo/../../lab/sanitizer-records}
rm_dir=$(cd "${REGEXMATCHER_DIR:?REGEXMATCHER_DIR is required}" && pwd)
rm_commit=${REGEXMATCHER_COMMIT:?REGEXMATCHER_COMMIT is required (the commit of REGEXMATCHER_DIR)}
work=${WORK:-$HOME/lab/p2/rbench-san}/$san${TAG:+-$TAG}
sources=(main.cpp core arms cmake gen CMakeLists.txt coverage.json semantics.json)

case "$san" in
    asan) cmake_args=(-DRB_SANITIZER=address+undefined)
          export ASAN_OPTIONS="detect_leaks=1:detect_stack_use_after_return=1:strict_string_checks=1:symbolize=1"
          export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"
          options="ASAN_OPTIONS=$ASAN_OPTIONS;UBSAN_OPTIONS=$UBSAN_OPTIONS" ;;
    tsan) cmake_args=(-DRB_SANITIZER=thread)
          export TSAN_OPTIONS="halt_on_error=1:second_deadlock_stack=1"
          options="TSAN_OPTIONS=$TSAN_OPTIONS" ;;
    msan) libcxx=${MSAN_LIBCXX:-$HOME/opt/libcxx-msan-gcc}
          cmake_args=(-DRB_SANITIZER=memory -DRB_MSAN_LIBCXX="$libcxx")
          export MSAN_OPTIONS="halt_on_error=1:print_stats=1:fast_unwind_on_fatal=1"
          options="MSAN_OPTIONS=$MSAN_OPTIONS" ;;
    *) echo "unknown sanitizer '$san'" >&2; exit 2 ;;
esac
# Every arm, less those coverage.json exempts from this sanitizer.
if [ -z "${RB_ARMS:-}" ]; then
    RB_ARMS=$(python3 "$here/arms_for.py" "$san")
fi
cmake_args+=("-DRB_ARMS=$RB_ARMS" "-DREGEXMATCHER_COMMIT=$rm_commit")
read -r -a extra <<< "${EXTRA_CMAKE:-}"
cmake_args+=("${extra[@]}")
echo "sanitize_rbench: $san over arms [$RB_ARMS]"
note=""
if [ "$san" = asan ]; then
    note="The Go arms' code is built with go build -asan and the Rust arms' crate with -Zsanitizer=address (the stable rustc accepts it with RUSTC_BOOTSTRAP=1; the Rust standard library is the prebuilt, uninstrumented one)."
    if [[ ";$RB_ARMS;" == *";actix-router;"* ]]; then
        note="$note LeakSanitizer ignores a leak whose allocation stack has the frame <actix_router::resource::ResourceDef>::parse, and no other: actix-router 0.5.4 keeps the patterns it parses for the life of the process on purpose (src/resource.rs). The suppression is compiled into arms/actix_router.cpp under ASan only; every other leak is reported."
    fi
elif [ "$san" = tsan ]; then
    note="The Go and Rust code of the FFI arms is not instrumented under TSan; their C++ adapters are."
fi

code=$(git -C "$here" log -1 --format=%H -- "${sources[@]}")
if [ -n "$(git -C "$here" status --porcelain -- "${sources[@]}")" ]; then
    echo "rbench sources have local changes; a record must name committed code" >&2
    exit 2
fi
name=rbench-${code:0:9}-${HOST_TAG:-L}-$san${TAG:+-$TAG}
bash "$here/keep_record_logs.sh" check "$name"

rm -rf "$work"
mkdir -p "$work"
start=$(date +%s)
set +e
REGEXMATCHER_DIR="$rm_dir" bash "$here/build.sh" "$work/build" "${cmake_args[@]}"
build_rc=$?
grid_rc=1
if [ "$build_rc" -eq 0 ]; then
    PIN=none ALLOW_UNPINNED=1 QUICK=1 SIZES="10 1000" CELL_TIMEOUT=1800 PAIRS="1:2" SEED=none \
        bash "$here/run_grid.sh" "$work/build/rbench" "$work/out"
    grid_rc=$?
fi
set -e
seconds=$(( $(date +%s) - start ))
read -r archive archive_sha < <(bash "$here/keep_record_logs.sh" pack "$name" "$work/build.log" \
    "$work/build.inputs.json" "$work/build.v2-include.json" "$work/out")

python3 "$here/sanitizer_record.py" --build "$work/build" --out-dir "$work/out" \
    --record "$records/$name.json" --note "$note" --pins "$here/cmake/pins.cmake" \
    --logs-archive "$archive" --logs-sha256 "$archive_sha" \
    --repo "https://github.com/Alex-Tsvetanov/paper-typed-routing.git" --commit "$code" \
    --repo-head "$(git -C "$repo" rev-parse HEAD)" \
    --regexmatcher-commit "$rm_commit" \
    --sanitizer "$san" --cmake-args="${cmake_args[*]}" --options="$options" \
    --build-exit "$build_rc" --grid-exit "$grid_rc" --seconds "$seconds" --host "$(uname -n)"
