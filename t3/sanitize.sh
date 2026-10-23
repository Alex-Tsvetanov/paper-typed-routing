#!/usr/bin/env bash
# sanitize.sh asan|tsan|msan RECORDS_DIR SETS_DIR: one D5 sanitizer record of round 3 on Linux (the
# laptop's Arch; design/round3/end-to-end.md, section 8; STATE.md, Laptop requests 0 and 4).
#
# Steps, in order, each logged in WORK/steps.jsonl; a step that fails does not stop the later ones,
# and the record says which failed (t3/record.py):
#   build     the paper's root project (mserver with every external arm the build has, v2's C
#             interface, p2gen, e2e_requests, the tests), clang, Release, under the sanitizer;
#   ctest     its whole CTest suite, every test's output kept (ctest -V);
#   inputs    what each target compiled (lab/bin/inputs_hash.py, project mode, RegexMatcher v2 as
#             the dependency root regexmatcher), and the hash of mserver_arms's and p2v2_c's inputs
#             under regexmatcher/include/;
#   programs  the Go and Rust programs under the sanitizer where their toolchains can instrument
#             them (t3/build_programs.py --sanitizer): asan, Go -asan and Rust -Zsanitizer=address
#             against this tree's libp2v2_c.a; tsan, Go -race against an uninstrumented libp2v2_c.a
#             (WORK/capi-plain), Rust not (t3/coverage.json); msan, neither (t3/coverage.json);
#   sets      e2e_requests of this tree writes twelve cells (both shapes; m = 10, 1,000, 10,000;
#             the first two seed pairs), each checked against t3/requests-manifest.tsv;
#   suite     t3/run_checks.py over this tree's mserver, every arm, and the programs built, on the
#             request sets in SETS_DIR (the bring-up job's, checked there against the manifest),
#             every server's output kept;
#   load      t3/p2run.py in count mode with this tree's p2gen against every arm of every program
#             built, both shapes at m = 1,000, the pair (111, 211), 20,000 requests a window,
#             every log kept. Untimed: count mode reads no time.
# Then the logs (everything in WORK but the build trees and binaries) go to
# RECORDS_LOGS/<name>/ and RECORDS_LOGS/<name>.tar.gz (bench/keep_record_logs.sh, which refuses an
# existing name), and t3/record.py writes RECORDS_DIR/<name>.json, <name> being
# p2r3-<code commit, 9 characters>-<HOST_TAG>-<sanitizer>; the code commit is the last commit that
# changed the sources below, which must have no local changes. Exit status: record.py's (0 green).
#
# Environment: INPUTS_HASH_PY (required: the Papers repo's lab/bin/inputs_hash.py); WORK (default
# ~/lab/p2r3/san; the work directory is WORK/<sanitizer>, made afresh); MSAN_LIBCXX (default
# ~/opt/libcxx-msan-gcc, the instrumented libc++ of round 2's records); HOST_TAG (default L);
# RECORDS_LOGS (default ~/lab/records-logs); JOBS (default nproc); P2_CPU_SERVER, P2_CPU_GEN,
# P2_CPU_HOUSE (default 14, 2-13, 0-1: lab/laptop/README.md's placement); P2_DESKTOP=1 for a
# development run on the desktop (D7: no time is read, the record's seconds are -1, and its name
# ends in -desktop, so it can never pass for a record and never goes to lab/sanitizer-records); go, cargo and rustc
# from PATH (the job wrapper puts Go 1.27.3 and Rust 1.99.0 there). Downloads: the CMake
# FetchContent archives, each checked against its sha256 (bench/cmake/pins.cmake,
# server/cmake/pins-round3.cmake); Go modules checked against go.sum (GOPROXY=direct, Go never
# fetches a toolchain); crates checked against Cargo.lock (cargo --locked).
set -uo pipefail
export GOPROXY=direct GOTOOLCHAIN=local

usage="usage: sanitize.sh asan|tsan|msan RECORDS_DIR SETS_DIR"
san=${1:?$usage}
records=${2:?$usage}
sets=${3:?$usage}
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
ih=${INPUTS_HASH_PY:?INPUTS_HASH_PY is required (the Papers repo's lab/bin/inputs_hash.py)}
[ -f "$ih" ] || { echo "sanitize.sh: no $ih" >&2; exit 2; }
[ -f "$sets/manifest.tsv" ] || { echo "sanitize.sh: no request sets at $sets (the bring-up job makes them)" >&2; exit 2; }
mkdir -p "$records"
records=$(cd "$records" && pwd)
sets=$(cd "$sets" && pwd)
jobs=${JOBS:-$(nproc)}
host_tag=${HOST_TAG:-L}
work=${WORK:-$HOME/lab/p2r3/san}/$san
sources=(CMakeLists.txt server t3 bench/core bench/arms bench/cmake t1/h6_targets.cpp)

case "$san" in
    asan) cmake_san=(-DP2_SANITIZER=address+undefined)
          export ASAN_OPTIONS="detect_leaks=1:detect_stack_use_after_return=1:strict_string_checks=1:symbolize=1"
          export UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=1"
          options="ASAN_OPTIONS=$ASAN_OPTIONS;UBSAN_OPTIONS=$UBSAN_OPTIONS"
          programs=(--sanitizer asan) ;;
    tsan) cmake_san=(-DP2_SANITIZER=thread)
          export TSAN_OPTIONS="halt_on_error=1:second_deadlock_stack=1"
          export GORACE="halt_on_error=1"
          options="TSAN_OPTIONS=$TSAN_OPTIONS;GORACE=$GORACE"
          programs=(--sanitizer race --no-rust) ;;
    msan) libcxx=${MSAN_LIBCXX:-$HOME/opt/libcxx-msan-gcc}
          cmake_san=(-DP2_SANITIZER=memory "-DP2_MSAN_LIBCXX=$libcxx")
          export MSAN_OPTIONS="halt_on_error=1:print_stats=1:fast_unwind_on_fatal=1"
          options="MSAN_OPTIONS=$MSAN_OPTIONS"
          programs=() ;;
    *) echo "sanitize.sh: unknown sanitizer '$san'" >&2; exit 2 ;;
esac

code=$(git -C "$root" log -1 --format=%H -- "${sources[@]}")
if [ -n "$(git -C "$root" status --porcelain -- "${sources[@]}")" ]; then
    echo "sanitize.sh: the sources have local changes; a record must name committed code" >&2
    exit 2
fi
name=p2r3-${code:0:9}-$host_tag-$san
desktop=${P2_DESKTOP:-}
[ -z "$desktop" ] || name=$name-desktop
keep=$root/bench/keep_record_logs.sh
bash "$keep" check "$name" || exit 2

rm -rf "$work"
mkdir -p "$work"
[ -n "$desktop" ] || start=$(date +%s)
step() {  # step NAME EXIT [DETAIL] [EXTRA_JSON]: one line of steps.jsonl
    local extra=${4:-}
    [ -n "$extra" ] || extra='{}'
    python3 - "$work/steps.jsonl" "$1" "$2" "${3:-}" "$extra" <<'EOF'
import json, sys
path, name, rc, detail, extra = sys.argv[1:6]
line = {"step": name, "exit": int(rc), "detail": detail, **json.loads(extra)}
with open(path, "a", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps(line) + "\n")
EOF
    echo "== $1 exit $2 $3"
}

cmake_args=(-G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ "${cmake_san[@]}")
echo "sanitize.sh $san: $name, $(clang++ --version | head -1), host $(uname -n) $(uname -r)"
cmake -S "$root" -B "$work/build" "${cmake_args[@]}" > "$work/build.log" 2>&1 &&
    cmake --build "$work/build" -j"$jobs" >> "$work/build.log" 2>&1
build_rc=$?
step build "$build_rc" "$(sed -n 's/^-- mserver: external arms //p' "$work/build.log" | head -1)"

mserver=$work/build/server/mserver
arms=""
if [ "$build_rc" -eq 0 ]; then
    (cd "$work/build" && ctest -V > "$work/ctest.log" 2> "$work/ctest.err")
    step ctest $? "$(grep -Eo '[0-9]+% tests passed.*' "$work/ctest.log" | tail -1)"

    arms=$("$mserver" --router '?' 2>&1 | sed -n 's/^router arms://p')
    targets=(mserver mserver_arms mserver_http1 mserver_loop mserver_external p2v2_c p2v2 p2gen p2gen_core p2gen_net
             e2e_requests)
    [[ " $arms " == *" v1 "* ]] && targets+=(mserver_v1)
    for a in $arms; do
        case $a in v2 | v1 | null) ;; *) targets+=("arm_${a//-/_}") ;; esac
    done
    targs=()
    for t in "${targets[@]}"; do targs+=(--target "$t"); done
    python3 "$ih" --build "p2r3=$work/build" "${targs[@]}" --root-label project --config-key CMAKE_BUILD_TYPE \
        --dep-root regexmatcher=RegexMatcher_SOURCE_DIR --out "$work/build.inputs.json" > /dev/null 2> "$work/inputs.err" &&
    python3 "$ih" --build "p2r3=$work/build" --target mserver_arms --target p2v2_c --root-label project \
        --config-key CMAKE_BUILD_TYPE --dep-root regexmatcher=RegexMatcher_SOURCE_DIR \
        --label-hash regexmatcher/include/ --out "$work/build.v2-include.json" > /dev/null 2>> "$work/inputs.err"
    step inputs $? "${#targets[@]} targets"
fi

go_bin=""
rust_bin=""
if [ "$build_rc" -eq 0 ] && [ ${#programs[@]} -gt 0 ]; then
    cxx=$work/build
    rc=0
    if [ "$san" = tsan ]; then
        # The race runtime and clang's ThreadSanitizer runtime cannot share a process: Go -race links
        # an uninstrumented v2 library, built here from the same sources (v2 and its C interface only).
        cxx=$work/capi-plain
        cmake -S "$root" -B "$cxx" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang \
            -DCMAKE_CXX_COMPILER=clang++ "-DMSERVER_EXTERNALS=" > "$work/capi-plain.log" 2>&1 &&
            cmake --build "$cxx" --target p2v2_c -j"$jobs" >> "$work/capi-plain.log" 2>&1
        rc=$?
    fi
    if [ "$rc" -eq 0 ]; then
        GOCACHE=$work/gocache python3 "$here/build_programs.py" --cxx-build "$cxx" --out "$work/progs" -j "$jobs" \
            "${programs[@]}" > "$work/programs.log" 2>&1
        rc=$?
    fi
    cp "$work/progs/build-info.json" "$work/programs-build-info.json" 2>/dev/null
    step programs "$rc" "build_programs.py ${programs[*]}"
    if [ "$rc" -eq 0 ]; then
        go_bin=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("go", {}).get("binary", ""))' "$work/progs/build-info.json")
        rust_bin=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("rust", {}).get("binary", ""))' "$work/progs/build-info.json")
    fi
fi

if [ "$build_rc" -eq 0 ]; then
    python3 "$here/make_requests.py" --bin "$work/build/e2e_requests" --out "$work/sets-check" --sizes 10,1000,10000 \
        --pairs 2 > "$work/sets.log" 2>&1 &&
        python3 "$here/make_requests.py" --verify "$work/sets-check" --manifest "$here/requests-manifest.tsv" >> "$work/sets.log" 2>&1
    step sets $? "$(tail -1 "$work/sets.log")"

    suite=(--mserver "$mserver")
    [ -n "$go_bin" ] && suite+=(--go "$go_bin")
    [ -n "$rust_bin" ] && suite+=(--rust "$rust_bin")
    python3 "$here/run_checks.py" --data "$sets" "${suite[@]}" --out "$work/suite.jsonl" --logs "$work/suite-logs" \
        > "$work/suite.out" 2>&1
    rc=$?
    marms=$(python3 -c 'import json,sys; print(json.dumps([a for a in sys.argv[1].split() if a != "v1"]))' "$arms")
    step suite "$rc" "$(tail -1 "$work/suite.out")" "{\"mserver_arms\": $marms}"

    python3 - "$work/load-plan.json" "$work/build/t3/gen/p2gen" "$sets" "$mserver" "$marms" "$go_bin" "$rust_bin" \
        "${P2_CPU_SERVER:-14}" "${P2_CPU_GEN:-2-13}" "${P2_CPU_HOUSE:-0-1}" <<'EOF'
import json, sys
out, p2gen, sets, mserver, marms, go, rust, server, gen, house = sys.argv[1:11]
programs = [{"name": "mserver", "path": mserver, "arms": json.loads(marms)}]
if go:
    programs.append({"name": "mserver-go", "path": go, "arms": ["v2", "httprouter", "gin", "nethttp", "chi", "null"]})
if rust:
    programs.append({"name": "mserver-rs", "path": rust, "arms": ["v2", "matchit", "path-tree", "actix-router", "null"]})
plan = {"_comment": "t3/sanitize.sh's load step: count mode, untimed", "p2gen": p2gen, "data_root": sets,
        "shapes": ["mixed-disjoint", "static"], "sizes": [1000], "pairs": [[111, 211]],
        "cpus": {"server": int(server), "generator": gen}, "housekeeping_cpus": house, "connections": 64,
        "ready_timeout_s": 300, "stop_timeout_s": 60, "count_limit_s": 1200, "verify_sets": True, "programs": programs}
json.dump(plan, open(out, "w", encoding="utf-8"), indent=1)
EOF
    python3 "$here/p2run.py" "$work/load-plan.json" --out "$work/load.jsonl" --count 20000 --workdir "$work/load.work" \
        --keep-logs > "$work/load.out" 2>&1
    step load $? "$(tail -1 "$work/load.out")"
fi

seconds=-1
[ -n "$desktop" ] || seconds=$(( $(date +%s) - start ))
kept=()
for f in "$work"/*; do
    case "$(basename "$f")" in build | capi-plain | progs | gocache | sets-check) ;; *) kept+=("$f") ;; esac
done
read -r archive archive_sha < <(bash "$keep" pack "$name" "${kept[@]}")

rm_commit=$(sed -n 's/^set(RB_REGEXMATCHER_V2_COMMIT \([0-9a-f]*\))/\1/p' "$root/bench/cmake/pins.cmake")
python3 "$here/record.py" --work "$work" --record "$records/$name.json" --repo "https://github.com/Alex-Tsvetanov/paper-typed-routing.git" \
    --commit "$code" --repo-head "$(git -C "$root" rev-parse HEAD)" --sanitizer "$san" --host-tag "$host_tag" \
    --host "$(uname -n)" --cmake-args="${cmake_args[*]}" --options="$options" --seconds "$seconds" \
    --regexmatcher-commit "$rm_commit" --pins "$root/bench/cmake/pins.cmake" --pins "$root/server/cmake/pins-round3.cmake" \
    --logs-archive "$archive" --logs-sha256 "$archive_sha"
