#!/usr/bin/env bash
# Sanitizer record for RegexMatcher v2's whole test suite, on the lab host L
# (design/round2/regexmatcher-v2.md, section 8.4).
#
# Usage: sanitize_regexmatcher.sh asan|tsan|msan COMMIT [RECORDS_DIR]
#
# Exports COMMIT from a RegexMatcher clone (RM, default ~/lab/p2/r2/RegexMatcher, which fetches
# from the bare repository on L; never GitHub while v2 is not public), configures it with its
# tests and the sanitizer (clang, Release), builds every target, and runs the whole CTest suite
# with every test's output kept (ctest -V): the regex engine's tests, the route matcher's, the
# compile-time tables and the negative-compilation cases. Green: the build succeeded, every test
# passed, and the output holds no sanitizer report (the shared report pattern,
# lab/bin/test_report_pattern.sh). Writes RECORDS_DIR/regexmatcher-<commit, 9 characters>-<host>-<san>.json
# (bench/regexmatcher_record.py), with what the test targets compiled (lab/bin/inputs_hash.py,
# project mode, root label regexmatcher) and the hash of their inputs under regexmatcher/include/,
# which the records gate matches with the v2 arms of rbench and the server's builds. The logs go
# to ~/lab/records-logs/<record name>/ with the sha256 of each, packed into <record name>.tar.gz
# beside it, whose sha256 the record carries (bench/keep_record_logs.sh); the script refuses to
# start if that directory or archive exists.
#
# Environment: HOST_TAG (the record name's host, default L), RM, WORK (default ~/lab/p2/rm-san),
# MSAN_LIBCXX (default $HOME/opt/libcxx-msan-gcc), INPUTS_HASH_PY (default the Papers repo's
# lab/bin/inputs_hash.py), EXTRA_CMAKE (more CMake arguments, e.g.
# -DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=<dir> for a local GoogleTest; recorded), RECORDS_LOGS
# (default ~/lab/records-logs), NOTE (copied into the record, e.g. where a local GoogleTest came
# from). Without a local copy, GoogleTest is fetched by RegexMatcher's own CMake from its
# official repository at the commit RegexMatcher pins (v1.15.2).
set -uo pipefail

san=${1:?usage: sanitize_regexmatcher.sh asan|tsan|msan COMMIT [RECORDS_DIR]}
commit_arg=${2:?usage: sanitize_regexmatcher.sh asan|tsan|msan COMMIT [RECORDS_DIR]}
here=$(cd "$(dirname "$0")" && pwd)
papers=$(cd "$here/../../.." && pwd)
records=${3:-$papers/lab/sanitizer-records}
rm_repo=${RM:-$HOME/lab/p2/r2/RegexMatcher}
ih=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
read -r -a extra <<< "${EXTRA_CMAKE:-}"

case "$san" in
    asan) cmake_san=(-DREGEXMATCHER_SANITIZER=address+undefined)
          export ASAN_OPTIONS="detect_leaks=1:detect_stack_use_after_return=1:strict_string_checks=1:symbolize=1"
          export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"
          options="ASAN_OPTIONS=$ASAN_OPTIONS;UBSAN_OPTIONS=$UBSAN_OPTIONS" ;;
    tsan) cmake_san=(-DREGEXMATCHER_SANITIZER=thread)
          export TSAN_OPTIONS="halt_on_error=1:second_deadlock_stack=1"
          options="TSAN_OPTIONS=$TSAN_OPTIONS" ;;
    msan) libcxx=${MSAN_LIBCXX:-$HOME/opt/libcxx-msan-gcc}
          cmake_san=(-DREGEXMATCHER_SANITIZER=memory "-DREGEXMATCHER_MSAN_LIBCXX=$libcxx")
          export MSAN_OPTIONS="halt_on_error=1:print_stats=1:fast_unwind_on_fatal=1"
          options="MSAN_OPTIONS=$MSAN_OPTIONS" ;;
    *) echo "unknown sanitizer '$san'" >&2; exit 2 ;;
esac

git -C "$rm_repo" fetch -q origin 2>/dev/null
commit=$(git -C "$rm_repo" rev-parse --verify "$commit_arg^{commit}") || { echo "no commit $commit_arg in $rm_repo" >&2; exit 2; }
name=regexmatcher-${commit:0:9}-${HOST_TAG:-L}-$san
work=${WORK:-$HOME/lab/p2/rm-san}/$name
logs=${RECORDS_LOGS:-$HOME/lab/records-logs}/$name
bash "$here/keep_record_logs.sh" check "$name" || exit 2
rm -rf "$work"
mkdir -p "$work/src" "$logs"
git -C "$rm_repo" archive "$commit" | tar -x -C "$work/src" || { echo "cannot export $commit" >&2; exit 2; }

start=$(date +%s)
cmake_args=(-G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
            -DREGEXMATCHER_BUILD_TESTS=ON "${cmake_san[@]}" "${extra[@]}")
cmake -S "$work/src" -B "$work/build" "${cmake_args[@]}" > "$logs/build.log" 2>&1 &&
    cmake --build "$work/build" -j"$(nproc)" >> "$logs/build.log" 2>&1
build_rc=$?
ctest_rc=-1
if [ "$build_rc" -eq 0 ]; then
    (cd "$work/build" && ctest -V > "$logs/ctest.log" 2>&1)
    ctest_rc=$?
fi
inputs_rc=-1
if [ "$build_rc" -eq 0 ]; then
    python3 "$ih" --build "rm=$work/build" --target route_tests --target route_checked_tests \
        --target route_ct_table_tests --target tests --root-label regexmatcher \
        --label-hash regexmatcher/include/ --out "$logs/inputs.json" > /dev/null 2> "$logs/inputs.err"
    inputs_rc=$?
fi
seconds=$(( $(date +%s) - start ))
read -r archive archive_sha < <(bash "$here/keep_record_logs.sh" pack "$name") ||
    { echo "cannot pack the logs of $name" >&2; exit 2; }

python3 "$here/regexmatcher_record.py" --record "$records/$name.json" --logs "$logs" \
    --logs-archive "$archive" --logs-sha256 "$archive_sha" \
    --repo "cpp-for-everything/RegexMatcher (local branch v2/route-matcher, from the bare repository on L)" \
    --commit "$commit" --sanitizer "$san" --options "$options" --cmake-args "${cmake_args[*]}" \
    --build-exit "$build_rc" --ctest-exit "$ctest_rc" --inputs-exit "$inputs_rc" \
    --seconds "$seconds" --host "$(uname -n)" --note "${NOTE:-}"
