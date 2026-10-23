#!/usr/bin/env bash
# records.sh OUT_DIR: round 3's D5 records on the laptop's Arch (STATE.md, Laptop requests 0 and 4):
# t3/sanitize.sh under ASan+UBSan, TSan and MSan, in that order, one at a time, each record into
# OUT_DIR/records/, its logs into ~/lab/records-logs/<record>/ and <record>.tar.gz. The bring-up job
# (t3/jobs/bringup.sh) comes first: its request sets, P2R3/sets, are the suite's.
#
# A record that is not green, or a script that fails, stops the job (exit 1): nothing after it runs,
# and the record is kept as it is, never made again in silence (sanitize.sh refuses a record name
# whose logs exist). After the three records: whether any binary of them can use io_uring
# (MemorySanitizer cannot see the kernel's writes into an io_uring buffer; the programs use epoll):
# ldd, dynamic symbols and strings of each, into OUT_DIR/io_uring.txt.
#
# Environment as bringup.sh's (P2R3, INPUTS_HASH_PY, P2_GO, RUSTUP_HOME, CARGO_HOME,
# RUSTUP_TOOLCHAIN, JOBS, P2_CPU_*), plus MSAN_LIBCXX (~/opt/libcxx-msan-gcc) and RECORDS_LOGS
# (~/lab/records-logs). ONLY (default "asan tsan msan") names the sanitizers to record, in order.
set -uo pipefail

out=${1:?usage: records.sh OUT_DIR}
mkdir -p "$out/records"
out=$(cd "$out" && pwd)
here=$(cd "$(dirname "$0")/.." && pwd)
root=$(cd "$here/.." && pwd)
p2r3=${P2R3:-$HOME/lab/p2r3}
export INPUTS_HASH_PY=${INPUTS_HASH_PY:-${LAB_TOOLS:+$LAB_TOOLS/../bin/inputs_hash.py}}
export RUSTUP_HOME=${RUSTUP_HOME:-$HOME/opt/rustup} CARGO_HOME=${CARGO_HOME:-$HOME/opt/cargo}
export RUSTUP_TOOLCHAIN=${RUSTUP_TOOLCHAIN:-1.99.0}
export PATH=${P2_GO:-$HOME/opt/p2/go1.27.3/bin}:$CARGO_HOME/bin:$PATH
export WORK=${WORK:-$p2r3/san}
exec > >(tee -a "$out/records.log") 2>&1

echo "records start, paper $(git -C "$root" rev-parse HEAD), host $(uname -n) $(uname -r)"
echo "  $(clang++ --version | head -1); $(go version); $(rustc --version)"
for san in ${ONLY:-asan tsan msan}; do
    echo "== $san start"
    bash "$here/sanitize.sh" "$san" "$out/records" "$p2r3/sets" > "$out/$san.log" 2>&1
    rc=$?
    tail -25 "$out/$san.log"
    echo "$san $rc" >> "$out/steps.txt"
    if [ "$rc" -ne 0 ]; then
        echo "STOPPED: $san exited $rc (not green or failed; $out/$san.log)"
        exit 1
    fi
done

{
    for san in ${ONLY:-asan tsan msan}; do
        for b in "$WORK/$san/build/server/mserver" "$WORK/$san/build/t3/gen/p2gen" "$WORK/$san/progs/mserver-go" \
                 "$WORK/$san/progs/rust/x86_64-unknown-linux-gnu/release/mserver-rs"; do
            [ -f "$b" ] || { echo "$b: not built"; continue; }
            echo "$b"
            echo "  ldd, lines naming uring: $(ldd "$b" 2>&1 | grep -ci uring)"
            echo "  dynamic symbols naming uring: $(nm -D "$b" 2>/dev/null | grep -ci uring)"
            echo "  strings containing io_uring: $(strings -a "$b" | grep -ci io_uring)"
        done
    done
} > "$out/io_uring.txt"
cat "$out/io_uring.txt"
echo "records done"
