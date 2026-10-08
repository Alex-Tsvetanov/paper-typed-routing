#!/usr/bin/env bash
# Sanitizer record for the paper's minimal server and the H6 tools on Linux (lab host L;
# design/round2/minimal-server.md, section 7).
#
# Usage: sanitize_h6.sh asan|tsan|msan [RECORDS_DIR]
#
# Builds the paper's root project (t1/h6_targets, the server mserver with its three router arms,
# and the server's tests) under the sanitizer, clang, Release, against REGEXMATCHER_DIR; runs the
# whole CTest suite with every test's output kept (ctest -V; the HTTP layer, the loopback tests,
# lab/t1's contract for each arm, the arms' agreement on the nine H6 cells); then, for each of the
# nine H6 cells (the seven shapes at m = 10, rest and param-last at m = 10,000; table seed 111,
# ring seed 211) and each arm (v2, v1, null): h6_targets writes the routes and targets, mserver
# serves them on one worker, t1/h6_exercise.py requests every target once over one keep-alive
# connection, GET / and an unmatched path, then a pipelined burst; SIGTERM stops the server, which
# must exit 0. Writes RECORDS_DIR/mserver-<code commit, 9 characters>-<host>-<san>.json
# (t1/h6_record.py), with what every target of the server and h6_targets compiled
# (lab/bin/inputs_hash.py, project mode, RegexMatcher v2 as the dependency root regexmatcher:
# mserver and the libraries it links, mserver_arms, mserver_http1, mserver_loop, mserver_v1, since
# a target's hash covers its own translation units only) and the hash of mserver_arms's inputs
# (it includes RegexMatcher's umbrella header) under regexmatcher/include/. <code commit> is the last commit that changed the tools' sources, which
# must have no local changes.
#
# Environment: REGEXMATCHER_DIR (required: a snapshot of the RegexMatcher commit measured) and
# REGEXMATCHER_COMMIT (that commit, in full), WORK (default ~/lab/p2/mserver-san), MSAN_LIBCXX
# (default $HOME/opt/libcxx-msan-gcc), INPUTS_HASH_PY, HOST_TAG (default L), EXTRA_CMAKE (more
# CMake arguments; recorded), RECORDS_LOGS (default ~/lab/records-logs). RegexMatcher v1 is
# fetched, pinned by commit and sha256 (bench/cmake/pins.cmake). The logs (everything in the work
# directory but the build tree) are copied to ~/lab/records-logs/<record name>/ and packed into
# <record name>.tar.gz beside it, whose sha256 the record carries (bench/keep_record_logs.sh); the
# script refuses to start if that directory or archive exists.
set -euo pipefail

san=${1:?usage: sanitize_h6.sh asan|tsan|msan [RECORDS_DIR]}
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
papers=$(cd "$root/../.." && pwd)
records=${2:-$papers/lab/sanitizer-records}
rm_dir=$(cd "${REGEXMATCHER_DIR:?REGEXMATCHER_DIR is required}" && pwd)
rm_commit=${REGEXMATCHER_COMMIT:?REGEXMATCHER_COMMIT is required (the commit of REGEXMATCHER_DIR)}
ih=${INPUTS_HASH_PY:-$papers/lab/bin/inputs_hash.py}
work=${WORK:-$HOME/lab/p2/mserver-san}/$san
sources=(CMakeLists.txt t1 server bench/core bench/arms/regexmatcher_v1_wrap.hpp bench/cmake)
read -r -a extra <<< "${EXTRA_CMAKE:-}"

case "$san" in
    asan) cmake_san=(-DP2_SANITIZER=address+undefined)
          export ASAN_OPTIONS="detect_leaks=1:detect_stack_use_after_return=1:strict_string_checks=1:symbolize=1"
          export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"
          options="ASAN_OPTIONS=$ASAN_OPTIONS;UBSAN_OPTIONS=$UBSAN_OPTIONS" ;;
    tsan) cmake_san=(-DP2_SANITIZER=thread)
          export TSAN_OPTIONS="halt_on_error=1:second_deadlock_stack=1"
          options="TSAN_OPTIONS=$TSAN_OPTIONS" ;;
    msan) libcxx=${MSAN_LIBCXX:-$HOME/opt/libcxx-msan-gcc}
          cmake_san=(-DP2_SANITIZER=memory "-DP2_MSAN_LIBCXX=$libcxx")
          export MSAN_OPTIONS="halt_on_error=1:print_stats=1:fast_unwind_on_fatal=1"
          options="MSAN_OPTIONS=$MSAN_OPTIONS" ;;
    *) echo "unknown sanitizer '$san'" >&2; exit 2 ;;
esac

code=$(git -C "$root" log -1 --format=%H -- "${sources[@]}")
if [ -n "$(git -C "$root" status --porcelain -- "${sources[@]}")" ]; then
    echo "the server's sources have local changes; a record must name committed code" >&2
    exit 2
fi
name=mserver-${code:0:9}-${HOST_TAG:-L}-$san
keep=$root/bench/keep_record_logs.sh
bash "$keep" check "$name"

rm -rf "$work"
mkdir -p "$work/cells"
start=$(date +%s)
cmake_args=(-G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
            "-DREGEXMATCHER_DIR=$rm_dir" "${cmake_san[@]}" "${extra[@]}")
set +e
cmake -S "$root" -B "$work/build" "${cmake_args[@]}" > "$work/build.log" 2>&1 &&
    cmake --build "$work/build" -j"$(nproc)" >> "$work/build.log" 2>&1
build_rc=$?
ctest_rc=-1
if [ "$build_rc" -eq 0 ]; then
    (cd "$work/build" && ctest -V > "$work/ctest.log" 2> "$work/ctest.err")
    ctest_rc=$?
    python3 "$ih" --build "h6=$work/build" --target mserver --target mserver_arms --target mserver_http1 \
        --target mserver_loop --target mserver_v1 --target h6_targets --root-label project \
        --dep-root regexmatcher=RegexMatcher_SOURCE_DIR --out "$work/build.inputs.json" > /dev/null 2> "$work/inputs.err"
    python3 "$ih" --build "h6=$work/build" --target mserver_arms --root-label project \
        --dep-root regexmatcher=RegexMatcher_SOURCE_DIR --label-hash regexmatcher/include/ \
        --out "$work/build.v2-include.json" > /dev/null 2>> "$work/inputs.err"
fi
cells="static:10 param-last:10 param-first:10 rest:10 wild:10 mixed-disjoint:10 mixed-overlap:10 rest:10000 param-last:10000"
port=23600
: > "$work/steps.jsonl"
if [ "$build_rc" -eq 0 ]; then
    for c in $cells; do
        shape=${c%%:*}; m=${c##*:}; d=$work/cells/$shape-$m
        mkdir -p "$d"
        "$work/build/h6_targets" --shape "$shape" --m "$m" --table-seed 111 --ring-seed 211 \
            --routes "$d/routes.txt" --targets "$d/targets.txt" > "$d/targets.out" 2> "$d/targets.err"
        t_rc=$?
        for arm in v2 v1 null; do
            port=$((port + 1))
            "$work/build/server/mserver" --port "$port" --workers 1 --routes "$d/routes.txt" --router "$arm" \
                > "$d/server-$arm.out" 2> "$d/server-$arm.err" &
            pid=$!
            unmatched=404
            [ "$arm" = null ] && unmatched=200
            python3 "$here/h6_exercise.py" --port "$port" --targets "$d/targets.txt" --wait 120 \
                --unmatched-status "$unmatched" > "$d/exercise-$arm.json" 2> "$d/exercise-$arm.err"
            e_rc=$?
            kill -TERM "$pid" 2>/dev/null
            s_rc=""
            for _ in $(seq 1 60); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.5
            done
            if kill -0 "$pid" 2>/dev/null; then
                kill -KILL "$pid" 2>/dev/null
                s_rc=killed
            fi
            wait "$pid" 2>/dev/null
            rc=$?
            [ -n "$s_rc" ] || s_rc=$rc
            printf '{"cell":"%s-%s","arm":"%s","targets_exit":%d,"exercise_exit":%d,"server_exit":"%s","exercise":%s}\n' \
                "$shape" "$m" "$arm" "$t_rc" "$e_rc" "$s_rc" "$(cat "$d/exercise-$arm.json" 2>/dev/null || echo null)" \
                >> "$work/steps.jsonl"
        done
    done
fi
set -e
seconds=$(( $(date +%s) - start ))
kept=()
for f in "$work"/*; do
    [ "$(basename "$f")" = build ] || kept+=("$f")
done
read -r archive archive_sha < <(bash "$keep" pack "$name" "${kept[@]}")

python3 "$here/h6_record.py" --build "$work/build" --work "$work" \
    --record "$records/$name.json" --logs-archive "$archive" --logs-sha256 "$archive_sha" \
    --pins "$root/bench/cmake/pins.cmake" --repo "https://github.com/Alex-Tsvetanov/paper-typed-routing.git" --commit "$code" \
    --repo-head "$(git -C "$root" rev-parse HEAD)" --regexmatcher-commit "$rm_commit" \
    --sanitizer "$san" --cmake-args="${cmake_args[*]}" --options="$options" \
    --build-exit "$build_rc" --ctest-exit "$ctest_rc" --seconds "$seconds" --host "$(uname -n)"
