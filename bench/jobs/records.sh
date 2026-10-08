#!/usr/bin/env bash
# records.sh OUT_DIR: round 2's sanitizer records on L (design/round2/status.md, section 5, steps
# 1 to 3): RegexMatcher v2's whole suite (bench/sanitize_regexmatcher.sh), rbench with every arm
# that bench/coverage.json does not exempt (bench/sanitize_rbench.sh), and the minimal server with
# its H6 exercise (t1/sanitize_h6.sh), each under ASan+UBSan, TSan and MSan (the instrumented
# libc++ at ~/opt/libcxx-msan-gcc), in that order, one at a time. Run from a Papers clone with
# this repository as its submodule at the commit to record (the scripts find lab/bin and
# lab/sanitizer-records at ../../..), under the lab's lablock, with a pid file and a done file:
#     RM_COMMIT=<full sha> REGEXMATCHER_DIR=<git archive of it> GTEST_DIR=<local GoogleTest> \
#     GTEST_NOTE=<where it came from> nohup ~/lab/Papers/lab/bin/lablock \
#         bash <clone>/papers/typed-routing/bench/jobs/records.sh <OUT_DIR> > <OUT_DIR>.log 2>&1 &
#     echo $! > <OUT_DIR>.pid
# ONLY (default "regexmatcher rbench mserver") names the kinds of record to make, in that order;
# a kind left out keeps its earlier records.
# A record that is not green, or a records script that fails, stops the job: nothing after it
# runs, and the record is reported as it is, never made again in silence (each script refuses to
# start over existing logs). When the job ends it writes OUT_DIR.done: the time and how it ended
# ("done", or "STOPPED:" and the reason, or "incomplete" if it was killed or failed elsewhere).
#
# After the nine records: whether any binary of the records can use io_uring (MemorySanitizer
# cannot see the kernel's writes into an io_uring buffer; the server uses epoll): ldd of the
# rbench, mserver and h6_targets binaries of each sanitizer build for liburing, and their dynamic
# symbols and strings for io_uring, into OUT_DIR/io_uring.txt.
#
# Downloads: rbench's FetchContent archives from GitHub (and one release archive), each checked
# against its sha256 in bench/cmake/pins.cmake; path-tree and smallvec from crates.io, checked
# against Cargo.lock (cargo --locked); a Go module missing from L's cache from its repository, not
# a proxy, and Go never fetches a toolchain; RegexMatcher v1 as rbench fetches it (pins.cmake).
# GoogleTest comes from GTEST_DIR, no download.
#
# The whole job is one function, read completely before it runs.
set -uo pipefail
export GOPROXY=direct GOTOOLCHAIN=local

main() {
    local out=${1:?usage: records.sh OUT_DIR}
    mkdir -p "$out"
    out=$(cd "$out" && pwd)
    status=incomplete
    trap 'echo "$(date -Is) $status" > "'"$out"'.done"' EXIT
    exec > >(tee -a "$out/records.log") 2>&1
    local here paper papers
    here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    paper=$(cd "$here/../.." && pwd)
    papers=$(cd "$paper/../.." && pwd)
    local rm_commit=${RM_COMMIT:?RM_COMMIT is required (the full RegexMatcher commit)}
    local rm_dir=${REGEXMATCHER_DIR:?REGEXMATCHER_DIR is required (a git archive of RM_COMMIT)}
    local gtest=${GTEST_DIR:?GTEST_DIR is required (a local GoogleTest v1.15.2)}
    [ -f "$gtest/CMakeLists.txt" ] || { status="STOPPED: no GoogleTest at $gtest"; echo "$status"; exit 2; }
    echo "records start $(date -Is), Papers $(git -C "$papers" rev-parse HEAD), paper $(git -C "$paper" rev-parse HEAD),"
    echo "  RegexMatcher $rm_commit from $rm_dir, host $(uname -n) $(uname -r), $(clang++ --version | head -1)"
    [ -z "$(git -C "$paper" status --porcelain)" ] || { status="STOPPED: the paper clone has local changes"; echo "$status"; exit 2; }

    local san step rc t0
    run() {  # run STEP COMMAND...: one records script; stops the job unless it exits 0 (green)
        step=$1; shift
        t0=$(date +%s)
        echo "== $step start $(date -Is)"
        "$@" > "$out/$step.log" 2>&1
        rc=$?
        tail -15 "$out/$step.log"
        echo "== $step exit $rc, $(( $(date +%s) - t0 )) s"
        echo "$step $rc $(( $(date +%s) - t0 ))" >> "$out/steps.txt"
        if [ "$rc" -ne 0 ]; then
            status="STOPPED: $step exited $rc (not green or failed; $out/$step.log)"
            echo "$status"
            exit 1
        fi
    }
    local only=" ${ONLY:-regexmatcher rbench mserver} "
    echo "records to make: $only"
    if [[ $only == *" regexmatcher "* ]]; then
        for san in asan tsan msan; do
            run "regexmatcher-$san" env EXTRA_CMAKE="-DFETCHCONTENT_SOURCE_DIR_GOOGLETEST=$gtest" NOTE="${GTEST_NOTE:-}" \
                bash "$paper/bench/sanitize_regexmatcher.sh" "$san" "$rm_commit"
        done
    fi
    if [[ $only == *" rbench "* ]]; then
        for san in asan tsan msan; do
            run "rbench-$san" env REGEXMATCHER_DIR="$rm_dir" REGEXMATCHER_COMMIT="$rm_commit" \
                bash "$paper/bench/sanitize_rbench.sh" "$san"
        done
    fi
    if [[ $only == *" mserver "* ]]; then
        for san in asan tsan msan; do
            run "mserver-$san" env REGEXMATCHER_DIR="$rm_dir" REGEXMATCHER_COMMIT="$rm_commit" \
                bash "$paper/t1/sanitize_h6.sh" "$san"
        done
    fi

    echo "== io_uring check $(date -Is)"
    local b
    {
        for san in asan tsan msan; do
            for b in "$HOME/lab/p2/rbench-san/$san/build/rbench" "$HOME/lab/p2/mserver-san/$san/build/server/mserver" \
                     "$HOME/lab/p2/mserver-san/$san/build/h6_targets"; do
                [ -f "$b" ] || { echo "$b: missing"; continue; }
                echo "$b"
                echo "  ldd, lines naming uring: $(ldd "$b" 2>&1 | grep -ci uring)"
                echo "  dynamic symbols naming uring: $(nm -D "$b" 2>/dev/null | grep -ci uring)"
                echo "  strings containing io_uring: $(strings -a "$b" | grep -ci io_uring)"
                strings -a "$b" | grep -i io_uring | sort -u | head -10 | sed 's/^/    /'
            done
        done
    } | tee "$out/io_uring.txt"
    status=done
    echo "records done $(date -Is)"
}

main "$@"
exit
